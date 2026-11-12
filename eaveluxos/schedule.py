# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Config, effects and the rules engine.

A rule says: on these dates / days, lights go on at <time> and off at <time>.
A time is either a clock time ("23:30", "11:30 pm") or a sun event with an
optional offset in minutes ("sunset", "sunset + 15", "sunrise - 30",
"dusk", "dawn"). If the off time is at or before the on time, the off time is
taken from the NEXT day, so "on = sunset, off = sunrise" uses tomorrow's real
sunrise.

When several rules cover the same moment, the highest priority wins; ties go
to the rule listed first. Default priorities: rules with dates 200, everyday
rules 100, weather rules 150. Manual control and the security flash sit above
all of them.
"""
import os
import re
import tomllib
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .sun import sun_times


class ConfigError(Exception):
    pass


# ---------------------------------------------------------------- time exprs
_SUN_RE = re.compile(r"^(sunrise|sunset|dawn|dusk)\s*(?:([+-])\s*(\d+)\s*(?:m|min|mins|minutes)?)?$", re.I)
_CLOCK_RE = re.compile(r"^(\d{1,2}):(\d{2})\s*(am|pm)?$", re.I)


@dataclass(frozen=True)
class TimeExpr:
    text: str
    sun_event: str | None = None
    offset_min: int = 0
    clock: time | None = None

    @classmethod
    def parse(cls, text: str) -> "TimeExpr":
        s = str(text).strip()
        m = _SUN_RE.match(s)
        if m:
            off = int(m.group(3) or 0) * (-1 if m.group(2) == "-" else 1)
            return cls(s, sun_event=m.group(1).lower(), offset_min=off)
        m = _CLOCK_RE.match(s)
        if m:
            h, mi, ap = int(m.group(1)), int(m.group(2)), (m.group(3) or "").lower()
            if ap:
                if not 1 <= h <= 12:
                    raise ConfigError(f"'{s}': hour must be 1-12 with am/pm")
                h = (h % 12) + (12 if ap == "pm" else 0)
            if h == 24 and mi == 0:
                h, mi = 0, 0  # "24:00" means midnight
            if not (0 <= h <= 23 and 0 <= mi <= 59):
                raise ConfigError(f"'{s}' is not a valid time")
            return cls(s, clock=time(h, mi))
        raise ConfigError(f"Can't read time '{s}'. Use e.g. '23:30', '11:30 pm', 'sunset', 'sunset + 15', 'sunrise - 30', 'dusk'.")

    def resolve(self, d: date, loc) -> datetime | None:
        if self.clock is not None:
            # zoneinfo picks the right offset for that date (EST vs EDT).
            return datetime.combine(d, self.clock, tzinfo=loc.tz)
        base = loc.sun(d)[self.sun_event]
        if base is None:
            return None
        return base + timedelta(minutes=self.offset_min)


# ---------------------------------------------------------------- location
def make_tz(name: str, dst_mode: str = "auto"):
    """auto: follow the official rules for the zone (recommended).
    on / off: hold daylight or standard time all year, for people whose
    controller, area or preference doesn't follow the rules."""
    zone = ZoneInfo(name)
    if dst_mode == "auto":
        return zone
    samples = [datetime(2026, 1, 15, 12, tzinfo=zone), datetime(2026, 7, 15, 12, tzinfo=zone)]
    offs = sorted(samples, key=lambda d: d.utcoffset())
    std, dst = offs[0], offs[-1]
    base = std.utcoffset()
    if dst_mode == "on":
        off = base + timedelta(hours=1)
        label = dst.tzname() if dst.utcoffset() == off else f"{std.tzname()}+1"
    else:
        off, label = base, std.tzname()
    return timezone(off, label)


def tz_info(name: str) -> dict:
    """Facts about a zone for the Date & Time screen."""
    zone = ZoneInfo(name)
    now = datetime.now(zone)
    std = min((datetime(now.year, m, 15, 12, tzinfo=zone) for m in (1, 7)), key=lambda d: d.utcoffset())
    has_dst = any(datetime(now.year, m, 15, 12, tzinfo=zone).dst() for m in range(1, 13))
    nxt = None
    if has_dst:  # find the next offset change, hour by hour then minute by minute
        t, off = now.replace(minute=0, second=0, microsecond=0), now.utcoffset()
        for _ in range(24 * 370):
            t2 = (t.astimezone(timezone.utc) + timedelta(hours=1)).astimezone(zone)
            if t2.utcoffset() != off:
                lo = t.astimezone(timezone.utc)
                for _ in range(60):
                    lo += timedelta(minutes=1)
                    if lo.astimezone(zone).utcoffset() != off:
                        break
                nxt = lo.astimezone(zone)
                before = (lo - timedelta(minutes=1)).astimezone(zone)
                nxt = {"at": nxt.isoformat(), "from": before.tzname(), "to": nxt.tzname(),
                       "clock_from": (before + timedelta(minutes=1)).strftime("%H:%M"), "clock_to": nxt.strftime("%H:%M")}
                break
            t = t2
    return {"name": name, "has_dst": has_dst, "in_dst_now": bool(now.dst()), "abbr_now": now.tzname(),
            "std_abbr": std.tzname(), "next_change": nxt}


@dataclass
class Location:
    lat: float
    lon: float
    tz: object
    tz_name: str = "America/New_York"
    dst_mode: str = "auto"

    def sun(self, d: date) -> dict:
        return sun_times(d, self.lat, self.lon, self.tz)

    def now(self) -> datetime:
        return datetime.now(self.tz).replace(microsecond=0)


# ---------------------------------------------------------------- effects
MAX_PER_COLOR = 90  # bulbs per sequence slot (Trimlight Edge user guide)


def _hex_to_int(h: str) -> int:
    s = str(h).strip().lstrip("#")
    if not re.fullmatch(r"[0-9a-fA-F]{6}", s):
        raise ConfigError(f"Color '{h}' should look like #FF8800")
    return int(s, 16)


@dataclass
class Effect:
    key: str
    label: str
    kind: str                    # "saved" | "builtin" | "custom"
    saved_name: str | None = None
    saved_id: int | None = None
    payload: dict = field(default_factory=dict)

    @classmethod
    def from_config(cls, key: str, c: dict) -> "Effect":
        label = c.get("label", key.replace("_", " ").capitalize())
        speed = int(c.get("speed", 100))
        bright = int(c.get("brightness", 200))
        for name, v, lo, hi in (("speed", speed, 0, 255), ("brightness", bright, 0, 255)):
            if not lo <= v <= hi:
                raise ConfigError(f"effects.{key}: {name} must be {lo}-{hi}")
        if "saved" in c or "saved_id" in c:
            return cls(key, label, "saved", saved_name=c.get("saved"),
                       saved_id=int(c["saved_id"]) if "saved_id" in c else None)
        if "builtin" in c:
            mode = int(c["builtin"])
            if not 0 <= mode <= 179:
                raise ConfigError(f"effects.{key}: builtin must be 0-179")
            pl = int(c.get("pixel_len", 30))
            if not 1 <= pl <= 90:
                raise ConfigError(f"effects.{key}: pixel_len must be 1-90")
            return cls(key, label, "builtin", payload={
                "category": 0, "mode": mode, "speed": speed, "brightness": bright,
                "pixelLen": pl, "reverse": bool(c.get("reverse", False))})
        if "colors" in c:
            colors = c["colors"]
            if not 1 <= len(colors) <= 30:
                raise ConfigError(f"effects.{key}: give 1-30 colors")
            counts = c.get("counts") or [3] * len(colors)
            if len(counts) != len(colors):
                raise ConfigError(f"effects.{key}: counts must have one number per color")
            mode = int(c.get("custom_mode", 0))
            if not 0 <= mode <= 16:
                raise ConfigError(f"effects.{key}: custom_mode must be 0-16")
            pixels = []
            for i, (col, n) in enumerate(zip(colors, counts)):
                # Trimlight's user guide: each of the 30 slots holds up to 90 bulbs.
                if not 1 <= int(n) <= MAX_PER_COLOR:
                    raise ConfigError(f"effects.{key}: each count must be 1-{MAX_PER_COLOR}")
                # "off" is the Trimlight app's zoning "X": those bulbs stay dark and
                # are skipped by any movement (API field "disable"). Black ("BK")
                # is different: it's a dark color that moves with the pattern.
                zone_off = str(col).strip().lower() in ("off", "x")
                pixels.append({"index": i, "count": int(n), "color": 0 if zone_off else _hex_to_int(col),
                               "disable": zone_off})
            return cls(key, label, "custom", payload={
                "category": 1, "mode": mode, "speed": speed, "brightness": bright, "pixels": pixels})
        raise ConfigError(f"effects.{key}: needs one of saved / saved_id / builtin / colors")

    def swatches(self) -> list[str]:
        if self.kind == "custom":
            return ["off" if p["disable"] else f"#{p['color']:06X}" for p in self.payload["pixels"]]
        return []


# ---------------------------------------------------------------- rules
_DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
_DAY_ALIASES = {"all": _DAYS, "everyday": _DAYS, "weekdays": _DAYS[:5], "weekends": _DAYS[5:]}


def _parse_md(s: str, where: str) -> tuple[int, int]:
    m = re.fullmatch(r"\s*(\d{1,2})-(\d{1,2})\s*", s)
    if not m:
        raise ConfigError(f"{where}: date '{s}' should be MM-DD")
    mo, dy = int(m.group(1)), int(m.group(2))
    try:
        date(2024, mo, dy)  # leap year, so 02-29 is allowed
    except ValueError:
        raise ConfigError(f"{where}: '{s}' isn't a real date") from None
    return mo, dy


# A window whose off time comes before its on time continues into the next
# day ("sunset to 00:30"), but never for longer than this. Without the limit, a
# morning rule like "06:00 to sunrise" would run 06:00 to the NEXT day's
# sunrise (about 23 hours) on summer days when sunrise is before 06:00; now it
# simply doesn't run those days, the same as when it's already light out.
MAX_WINDOW_HOURS = 20
DEFAULT_PRIORITY_DATED = 200
DEFAULT_PRIORITY_DAILY = 100
DEFAULT_PRIORITY_WEATHER = 150


def _levels(c: dict, where: str) -> dict:
    """Optional brightness/speed overrides on a rule (0-255)."""
    out = {}
    for k in ("brightness", "speed"):
        if k in c:
            v = int(c[k])
            if not 0 <= v <= 255:
                raise ConfigError(f"{where}: {k} must be 0-255")
            out[k] = v
    return out


def _effect_list(c: dict, effects: dict, where: str) -> list:
    raw = c.get("effect")
    names = raw if isinstance(raw, list) else [raw]
    if not names or any(n is None for n in names):
        raise ConfigError(f"{where}: missing 'effect'")
    out = []
    for n in names:
        if n not in effects:
            raise ConfigError(f"{where}: effect '{n}' isn't defined under [effects]")
        out.append(effects[n])
    return out


def _rotate(c: dict, n_effects: int, where: str) -> int:
    if n_effects > 1 and str(c.get("rotate", "")).lower() == "nightly":
        return 0
    r = int(c.get("rotate_minutes", 0) or 0)
    if n_effects > 1 and r < 1:
        raise ConfigError(f"{where}: several patterns are listed, so set rotate_minutes (1 or more) or rotate = \"nightly\"")
    return r if n_effects > 1 else 0


@dataclass
class Window:
    rule: "Rule"
    start: datetime
    end: datetime

    @property
    def key(self) -> str:
        return f"on|{self.rule.name}|{self.start.isoformat()}"



@dataclass
class Rule:
    name: str
    on: TimeExpr
    off: TimeExpr
    effects: list
    priority: int
    order: int
    rotate_minutes: int = 0
    levels: dict = field(default_factory=dict)
    date_start: tuple[int, int] | None = None
    date_end: tuple[int, int] | None = None
    weekdays: frozenset = frozenset(range(7))

    @property
    def effect(self):
        return self.effects[0]

    nightly: bool = False

    @property
    def effect_label(self) -> str:
        if len(self.effects) == 1:
            return self.effects[0].label
        how = "a different one each night" if self.nightly else f"every {self.rotate_minutes} min"
        return " / ".join(e.label for e in self.effects) + f" ({how})"

    def night_index(self, night: date) -> int:
        """For nightly rotation: which pattern a night gets. Counts only the
        nights this rule runs (its days of the week), from the first night of
        its date range (or Jan 1), so the order holds even for "Fri and Sat"."""
        anchor = None
        if self.date_start:
            mo, dy = self.date_start
            for y in (night.year, night.year - 1):
                try:
                    cand = date(y, mo, dy)
                except ValueError:  # Feb 29 in a non-leap year
                    cand = date(y, mo, 28)
                if cand <= night:
                    anchor = cand
                    break
        if anchor is None:
            anchor = date(night.year, 1, 1)
        nights = sum(1 for k in range((night - anchor).days) if self.applies_on(anchor + timedelta(days=k)))
        return nights % len(self.effects)

    def pick(self, window_start: datetime, now: datetime):
        """(effect, step) to show now for a window that started at window_start.
        step changes whenever the pattern should change."""
        if len(self.effects) == 1:
            return self.effects[0], 0
        if self.nightly:
            i = self.night_index(window_start.date())
            return self.effects[i], f"n{window_start.date().isoformat()}"
        if not self.rotate_minutes:
            return self.effects[0], 0
        elapsed = max(0, int((now - window_start).total_seconds() // 60))
        step = elapsed // self.rotate_minutes
        return self.effects[step % len(self.effects)], step

    @classmethod
    def from_config(cls, i: int, c: dict, effects: dict) -> "Rule":
        name = c.get("name") or f"Rule {i + 1}"
        where = f"rule '{name}'"
        for k in ("on", "off", "effect"):
            if k not in c:
                raise ConfigError(f"{where}: missing '{k}'")
        effs = _effect_list(c, effects, where)
        ds = de = None
        if c.get("dates"):
            parts = str(c["dates"]).split("..")
            ds = _parse_md(parts[0], where)
            de = _parse_md(parts[1], where) if len(parts) > 1 else ds
        days = c.get("days", "all")
        if isinstance(days, str):
            days = _DAY_ALIASES.get(days.lower())
            if days is None:
                raise ConfigError(f"{where}: days should be all / weekdays / weekends or a list like ['fri','sat']")
        wd = set()
        for dname in days:
            dn = str(dname).lower()[:3]
            if dn not in _DAYS:
                raise ConfigError(f"{where}: unknown day '{dname}'")
            wd.add(_DAYS.index(dn))
        prio = int(c.get("priority", DEFAULT_PRIORITY_DATED if ds else DEFAULT_PRIORITY_DAILY))
        rule = cls(name, TimeExpr.parse(c["on"]), TimeExpr.parse(c["off"]), effs, prio, i,
                   _rotate(c, len(effs), where), _levels(c, where), ds, de, frozenset(wd))
        rule.nightly = len(effs) > 1 and str(c.get("rotate", "")).lower() == "nightly"
        return rule

    def applies_on(self, d: date) -> bool:
        if d.weekday() not in self.weekdays:
            return False
        if self.date_start is None:
            return True
        md = (d.month, d.day)
        if self.date_start <= self.date_end:
            return self.date_start <= md <= self.date_end
        return md >= self.date_start or md <= self.date_end  # wraps New Year

    def window(self, d: date, loc: Location) -> Window | None:
        """The on/off window that STARTS on local date d."""
        if not self.applies_on(d):
            return None
        start = self.on.resolve(d, loc)
        if start is None:
            return None
        end = self.off.resolve(d, loc)
        if end is None or end <= start:
            end = self.off.resolve(d + timedelta(days=1), loc)
            if end is not None and end - start > timedelta(hours=MAX_WINDOW_HOURS):
                return None
        if end is None or end <= start:
            return None
        return Window(self, start, end)


@dataclass
class Plan:
    """A stretch [start, end) during which `window` is the one running."""
    window: Window
    start: datetime
    end: datetime

    @property
    def rule(self) -> "Rule":
        return self.window.rule

    def effect_label(self) -> str:
        r = self.window.rule
        return r.pick(self.window.start, self.window.start)[0].label if r.nightly else r.effect_label


def _rank(w: Window):
    return (-w.rule.priority, w.rule.order)


class Schedule:
    def __init__(self, rules: list[Rule], loc: Location):
        self.rules = rules
        self.loc = loc
        self._wcache: dict = {}

    def _window(self, rule: Rule, d: date) -> Window | None:
        """rule.window(d), remembered: windows depend only on the rule, the
        date and the location, and the same ones are asked for many times."""
        k = (rule.order, d)
        if k not in self._wcache:
            if len(self._wcache) > 20000:
                self._wcache.clear()
            self._wcache[k] = rule.window(d, self.loc)
        return self._wcache[k]

    def active_window(self, now: datetime) -> Window | None:
        """Highest-priority window covering now (ties: earliest in the file)."""
        today = now.date()
        live = []
        for rule in self.rules:
            for d in (today, today - timedelta(days=1)):
                w = self._window(rule, d)
                if w and w.start <= now < w.end:
                    live.append(w)
        return min(live, key=_rank) if live else None

    def day_plan(self, d: date) -> Window | None:
        """The highest-priority window starting on date d. A day can have
        several separate windows (for example 06:00-sunrise and
        sunset-23:00); day_plans() lists them all."""
        ws = [w for r in self.rules if (w := self._window(r, d))]
        return min(ws, key=_rank) if ws else None

    def day_plans(self, d: date) -> list["Plan"]:
        """Every stretch of time the lights are on for windows that start on
        date d, in order, exactly as the scheduler will run them: where windows
        overlap, the higher priority wins and the other only fills the gaps."""
        ws = [w for dd in (d - timedelta(days=1), d, d + timedelta(days=1))
              for r in self.rules if (w := self._window(r, dd))]
        edges = sorted({t for w in ws for t in (w.start, w.end)})
        plans: list[Plan] = []
        for a, b in zip(edges, edges[1:]):
            w = self.active_window(a + (b - a) / 2)
            if not w:
                continue
            if plans and plans[-1].window.key == w.key and plans[-1].end == a:
                plans[-1].end = b
            else:
                plans.append(Plan(w, a, b))
        return [p for p in plans if p.window.start.date() == d]

    def next_change(self, now: datetime) -> datetime | None:
        """Next moment the scheduled window changes (ignores rotation steps)."""
        cur = self.active_window(now)
        cur_key = cur.key if cur else "off"
        edges = set()
        for i in range(-1, 9):
            d = now.date() + timedelta(days=i)
            for r in self.rules:
                w = self._window(r, d)
                if w:
                    edges.update(t for t in (w.start, w.end) if t > now)
        for t in sorted(edges):
            w = self.active_window(t)
            if (w.key if w else "off") != cur_key:
                return t
        return None


# ---------------------------------------------------------------- weather rules
WEATHER_TAGS = {"snow", "rain", "storm", "fog", "clear", "cloudy", "wind", "freezing"}


@dataclass
class WeatherRule:
    name: str
    tags: frozenset
    below_f: float | None
    above_f: float | None
    effects: list
    rotate_minutes: int
    priority: int
    order: int
    levels: dict

    @property
    def effect_label(self) -> str:
        if len(self.effects) == 1:
            return self.effects[0].label
        return " / ".join(e.label for e in self.effects) + f" (every {self.rotate_minutes} min)"

    @classmethod
    def from_config(cls, i: int, c: dict, effects: dict) -> "WeatherRule":
        name = c.get("name") or f"Weather {i + 1}"
        where = f"weather rule '{name}'"
        when = c.get("when", [])
        when = [when] if isinstance(when, str) else list(when)
        tags = {str(t).lower().strip() for t in when}
        bad = tags - WEATHER_TAGS
        if bad:
            raise ConfigError(f"{where}: unknown condition {sorted(bad)}; use {sorted(WEATHER_TAGS)}")
        below = float(c["below_f"]) if "below_f" in c else None
        above = float(c["above_f"]) if "above_f" in c else None
        if not tags and below is None and above is None:
            raise ConfigError(f"{where}: give 'when' and/or below_f / above_f")
        effs = _effect_list(c, effects, where)
        return cls(name, frozenset(tags), below, above, effs, _rotate(c, len(effs), where),
                   int(c.get("priority", DEFAULT_PRIORITY_WEATHER)), i, _levels(c, where))

    def matches(self, tags: set, temp_f: float | None) -> bool:
        if self.tags and not (self.tags & tags):
            return False
        if self.below_f is not None and (temp_f is None or temp_f > self.below_f):
            return False
        if self.above_f is not None and (temp_f is None or temp_f < self.above_f):
            return False
        return True


# ---------------------------------------------------------------- config
@dataclass
class Config:
    loc: Location
    effects: dict
    schedule: Schedule
    weather_rules: list
    weather: dict
    security: dict
    safety: dict
    devices: list[str]
    web_host: str
    web_port: int
    interval: int
    client_id: str
    client_secret: str
    ui_password: str | None
    webhook_token: str | None


def _load_dotenv(path: Path):
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


class SetupNeeded(ConfigError):
    """Settings are valid so far but something essential isn't filled in."""


def build_config(raw: dict, secrets: dict, need_secrets: bool = True) -> Config:
    """raw: the settings document (same shape as config.toml).
    secrets: client_id, client_secret, ui_password, webhook_token."""
    loc_c = raw.get("location", {})
    try:
        lat, lon = float(loc_c.get("latitude", 0)), float(loc_c.get("longitude", 0))
    except (TypeError, ValueError):
        raise ConfigError("Latitude and longitude must be numbers.") from None
    if lat == 0 and lon == 0:
        raise SetupNeeded("Set your location on the Date & Time screen.")
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ConfigError("Latitude must be -90..90 and longitude -180..180.")
    tzname = loc_c.get("timezone", "America/New_York")
    dst_mode = str(loc_c.get("dst_mode", "auto")).lower()
    if dst_mode not in ("auto", "on", "off"):
        raise ConfigError("Daylight saving mode must be auto, on or off.")
    try:
        tz = make_tz(tzname, dst_mode)
    except (ZoneInfoNotFoundError, ValueError):
        raise ConfigError(f"Unknown time zone '{tzname}'. On Windows run: pip install tzdata") from None
    loc = Location(lat, lon, tz, tzname, dst_mode)

    eff_c = raw.get("effects", {})
    if not eff_c:
        raise SetupNeeded("Create at least one pattern.")
    effects = {k: Effect.from_config(k, v) for k, v in eff_c.items()}

    rules = [Rule.from_config(i, r, effects) for i, r in enumerate(raw.get("rules", []))]
    names = [r.name for r in rules]
    if len(names) != len(set(names)):
        raise ConfigError("Two schedule rules have the same name. Give each one its own name.")
    wrules = [WeatherRule.from_config(i, r, effects) for i, r in enumerate(raw.get("weather_rules", []))]

    wc = raw.get("weather", {})
    use = str(wc.get("use", "either")).lower()
    if use not in ("observed", "forecast", "either"):
        raise ConfigError("Weather 'use' must be observed, forecast or either")
    weather = {"enabled": bool(wc.get("enabled", bool(wrules))) and bool(wrules), "use": use,
               "check_minutes": max(5, int(wc.get("check_minutes", 15))),
               "contact": str(wc.get("contact", "")).strip()}

    sc = raw.get("security", {})
    sec_eff = sc.get("effect") or None
    if sec_eff is not None and sec_eff not in effects:
        raise ConfigError(f"Security flash pattern '{sec_eff}' doesn't exist")
    security = {"effect": sec_eff, "minutes": max(1, min(240, int(sc.get("minutes", 5))))}
    sf = raw.get("safety", {}) or {}
    safety = {"enabled": bool(sf.get("enabled", False)), "days": max(1, min(14, int(sf.get("days", 7))))}

    svc = raw.get("service", {})
    cid = (os.environ.get("TRIMLIGHT_CLIENT_ID") or secrets.get("client_id") or "").strip()
    secret = (os.environ.get("TRIMLIGHT_CLIENT_SECRET") or secrets.get("client_secret") or "").strip()
    if need_secrets and not (cid and secret):
        raise SetupNeeded("Enter your Trimlight Client ID and Client Secret on the Settings screen.")
    hook = (os.environ.get("TRIMLIGHT_WEBHOOK_TOKEN") or secrets.get("webhook_token") or "").strip() or None
    if hook and len(hook) < 16:
        raise ConfigError("The webhook token should be at least 16 characters.")

    return Config(
        loc=loc, effects=effects, schedule=Schedule(rules, loc), weather_rules=wrules,
        weather=weather, security=security, safety=safety,
        devices=[str(d) for d in svc.get("devices", [])],
        web_host=str(svc.get("web_host", "0.0.0.0")),
        web_port=int(svc.get("web_port", 8787)),
        interval=max(5, int(svc.get("check_interval_seconds", 20))),
        client_id=cid, client_secret=secret,
        ui_password=os.environ.get("TRIMLIGHT_UI_PASSWORD") or None,
        webhook_token=hook,
    )


def read_toml(path: Path) -> dict:
    try:
        return tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path.name} has a syntax error: {e}") from None


def load_config(path: Path, need_secrets: bool = True) -> Config:
    """Legacy entry point: config.toml + .env."""
    _load_dotenv(path.parent / ".env")
    if not path.exists():
        raise ConfigError(f"No config at {path}.")
    return build_config(read_toml(path), {}, need_secrets)
