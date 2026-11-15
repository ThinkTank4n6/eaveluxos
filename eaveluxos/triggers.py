# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Lights that react to events (3.16).

- Alert patterns: ready-made patterns for webhooks (package, alarm, ...),
  usable by name without adding them to your patterns.
- Zones: light only part of the house. Trimlight's cloud has no command for
  that, so a zone flash is a custom pattern with every bulb outside the zone
  set to the Trimlight app's "X" (disable: dark, and skipped by movement) and
  the pattern's colors spread over the zone.
- Severe weather alerts: active NWS warnings for your location (free, no key):
  https://api.weather.gov/alerts/active?point=<lat>,<lon>
"""
import json
import logging
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

from .schedule import MAX_PER_COLOR, ConfigError, Effect, _hex_to_int, gamma_correct
from .trust import CERT_HELP, client_context, is_cert_failure
from .version import VERSION

log = logging.getLogger("eaveluxos.triggers")
MAX_SLOTS = 30
FLASH_MIN_S, FLASH_MAX_S = 5, 4 * 3600

# Ready-made alert patterns. Mode numbers are Trimlight's custom motions
# (catalog.CUSTOM_MODES): 0 static, 6 breath, 15 strobe, 1 chase forward.
PRESETS = {
    "package": {"label": "Package (green)", "colors": ["#00FF00"], "counts": [1], "custom_mode": 6, "speed": 180, "brightness": 255},
    "alarm": {"label": "Alarm (red)", "colors": ["#FF0000"], "counts": [1], "custom_mode": 15, "speed": 230, "brightness": 255},
    "doorbell": {"label": "Doorbell (blue and white)", "colors": ["#0040FF", "#FFFFFF"], "counts": [4, 4], "custom_mode": 1, "speed": 200, "brightness": 255},
    "delivery": {"label": "Delivery (cyan)", "colors": ["#00FFFF"], "counts": [1], "custom_mode": 6, "speed": 160, "brightness": 255},
    "severe": {"label": "Severe weather (amber)", "colors": ["#FF7A00"], "counts": [1], "custom_mode": 6, "speed": 120, "brightness": 255},
    "security": {"label": "Bright white", "colors": ["#FFFFFF"], "counts": [1], "custom_mode": 0, "brightness": 255},
}


def preset_list() -> list[dict]:
    return [{"key": k, "label": v["label"], "colors": v["colors"]} for k, v in PRESETS.items()]


def _runs_to_pixels(runs) -> list[dict]:
    """[(color_int, count, disable)] -> Trimlight pixels, each at most 90 bulbs."""
    out = []
    for color, n, off in runs:
        while n > 0:
            k = min(MAX_PER_COLOR, n)
            out.append({"index": len(out), "count": k, "color": 0 if off else color, "disable": off})
            n -= k
    return out


def zone_payload(payload: dict, start: int, end: int, total: int) -> dict:
    """A custom pattern's payload shown only on bulbs start..end (1-based) of
    an address space of `total` bulbs; every other bulb is off ("X"). The
    pattern's colors are spread over the zone, repeated where there's room
    and stretched where 30 color slots aren't enough to repeat them."""
    if payload.get("category") != 1 or not payload.get("pixels"):
        raise ValueError("A zone needs a pattern made of colors, not a built-in effect or a pattern saved in the Trimlight app.")
    if not (1 <= start <= end <= total):
        raise ValueError(f"The zone (bulbs {start}–{end}) is outside the {total} bulbs of your lights.")
    seq = [(p["color"], max(1, int(p["count"])), bool(p.get("disable"))) for p in payload["pixels"]]
    n_zone = end - start + 1
    before, after = start - 1, total - end
    outside = sum(-(-x // MAX_PER_COLOR) for x in (before, after) if x)
    avail = MAX_SLOTS - outside
    if len(seq) > avail:
        raise ValueError(f"This pattern has {len(seq)} colors; a zone here has room for {max(0, avail)}. Use a simpler pattern.")
    unit = sum(n for _, n, _ in seq)
    reps = max(1, min(-(-n_zone // unit), avail // len(seq)))
    # Lay the colors out reps times over the zone, scaled to fill it exactly.
    want = [n for _ in range(reps) for _, n, _ in seq]
    colors = [(c, off) for _ in range(reps) for c, _, off in seq]
    scale = n_zone / sum(want)
    counts, acc, done = [], 0.0, 0
    for n in want:
        acc += n * scale
        k = round(acc) - done
        counts.append(k)
        done += k
    inner = [(c, k, off) for (c, off), k in zip(colors, counts) if k > 0]
    runs = ([(0, before, True)] if before else []) + inner + ([(0, after, True)] if after else [])
    pixels = _runs_to_pixels(runs)
    if len(pixels) > MAX_SLOTS:
        raise ValueError(f"That zone needs {len(pixels)} color slots; the controller allows {MAX_SLOTS}.")
    return {**payload, "pixels": pixels}


def find_zone(zones, name: str) -> dict:
    want = str(name or "").strip().lower()
    for z in zones or []:
        if str(z.get("name", "")).strip().lower() == want:
            return z
    names = ", ".join(str(z.get("name")) for z in zones or []) or "none yet (make them on the House tab)"
    raise ValueError(f"No zone named “{name}”. Zones: {names}.")


def flash_effect(effects: dict, gamma, effect: str | None = None, color: str | None = None,
                 zone: str | None = None, zones=None, total: int | None = None) -> Effect | None:
    """The pattern for a flash asked for by a webhook or the app: one of your
    patterns (by key or name), an alert pattern (package, alarm, ...), or a
    plain color; optionally only in a zone. None = the security flash pattern."""
    eff = None
    if color:
        try:
            c = gamma_correct(_hex_to_int(color), gamma)
        except ConfigError as e:
            raise ValueError(str(e)) from None
        eff = Effect("_flash", f"Color {('#' + str(color).strip().lstrip('#')).upper()}", "custom", payload={
            "category": 1, "mode": 0, "speed": 0, "brightness": 255,
            "pixels": [{"index": 0, "count": 1, "color": c, "disable": False}]})
    elif effect:
        e = str(effect).strip()
        if e in effects:
            eff = effects[e]
        else:
            low = e.lower()
            eff = next((x for x in effects.values() if x.label.strip().lower() == low), None)
            if eff is None and low in PRESETS:
                eff = Effect.from_config("_flash", PRESETS[low], gamma)
                eff.label = PRESETS[low]["label"]
            if eff is None:
                raise ValueError(f"No pattern named “{effect}”. Alert patterns: {', '.join(PRESETS)}.")
    if zone:
        z = find_zone(zones, zone)
        if eff is None:
            raise ValueError("Name a pattern or a color for a zone flash.")
        if not total:
            raise ValueError("The number of bulbs isn't known yet. Open Setup › Lights & controller once, then try again.")
        eff = Effect("_flash", f"{eff.label} · {z['name']}", "custom",
                     payload=zone_payload(eff.payload, int(z["start"]), int(z["end"]), int(total)))
    return eff


# ---------------------------------------------------------------- severe weather alerts
# NWS event names grouped into the choices shown in the app. Warnings only:
# watches and advisories are too frequent to change the house lights for.
ALERT_GROUPS = {
    "tornado": ("Tornado", ["Tornado Warning", "Tornado Emergency"]),
    "storm": ("Severe thunderstorm", ["Severe Thunderstorm Warning"]),
    "winter": ("Winter storm, blizzard or ice", ["Winter Storm Warning", "Blizzard Warning", "Ice Storm Warning"]),
    "flood": ("Flash flood", ["Flash Flood Warning", "Flash Flood Emergency"]),
    "hurricane": ("Hurricane or tropical storm", ["Hurricane Warning", "Tropical Storm Warning", "Storm Surge Warning"]),
    "temperature": ("Extreme heat or cold", ["Extreme Heat Warning", "Excessive Heat Warning", "Extreme Cold Warning", "Wind Chill Warning"]),
    "wind": ("High wind", ["High Wind Warning", "Extreme Wind Warning"]),
}
ALERT_STALE = 2 * 3600


def build_alert_settings(raw: dict, effects: dict) -> dict:
    """settings["weather_alerts"], checked."""
    a = raw.get("weather_alerts") or {}
    if not isinstance(a, dict):
        raise ConfigError("Severe weather alert settings must be an object.")
    groups = a.get("groups", ["tornado", "storm"])
    if not isinstance(groups, list) or not all(g in ALERT_GROUPS for g in groups):
        raise ConfigError("Unknown kind of weather alert.")
    eff = a.get("effect") or "severe"
    if eff not in effects and eff not in PRESETS:
        raise ConfigError(f"Weather alert pattern '{eff}' doesn't exist.")
    return {"enabled": bool(a.get("enabled")) and bool(groups), "groups": list(dict.fromkeys(groups)),
            "effect": eff, "turn_on": bool(a.get("turn_on", False))}


def parse_alerts(data, groups) -> list[dict]:
    """Active alerts from an NWS alerts answer that belong to the chosen groups."""
    names = {n.lower(): g for g in groups for n in ALERT_GROUPS[g][1]}
    out = []
    feats = data.get("features") if isinstance(data, dict) else None
    for f in (feats if isinstance(feats, list) else [])[:200]:
        p = f.get("properties") if isinstance(f, dict) else None
        if not isinstance(p, dict):
            continue
        ev = str(p.get("event") or "")
        g = names.get(ev.lower())
        if g is None or str(p.get("status", "Actual")) != "Actual" or str(p.get("messageType", "")) == "Cancel":
            continue
        ends = p.get("ends") or p.get("expires")
        try:
            end_dt = datetime.fromisoformat(str(ends).replace("Z", "+00:00")) if ends else None
        except ValueError:
            end_dt = None
        if end_dt is not None and end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=timezone.utc)
        out.append({"id": str(p.get("id") or f.get("id") or ev), "event": ev, "group": g,
                    "headline": str(p.get("headline") or ev)[:200], "ends": end_dt})
    return out


class AlertWatch:
    """Polls NWS for active warnings at one point (every 5 minutes)."""
    EVERY = 300

    def __init__(self, lat, lon, groups, contact="", fetch=None):
        self.lat, self.lon = round(lat, 4), round(lon, 4)
        self.groups = list(groups)
        self.ua = f"EaveLuxOS/{VERSION} ({contact or 'home lighting'})"
        self.fetch = fetch or self._fetch_json
        self.lock = threading.Lock()
        self.alerts: list[dict] = []
        self.raw = None                 # the last good answer, to re-sort with other choices
        self.updated = 0.0
        self.next_try = 0.0
        self.error = None

    def _fetch_json(self, url):
        req = urllib.request.Request(url, headers={"User-Agent": self.ua, "Accept": "application/geo+json"})
        try:
            with urllib.request.urlopen(req, timeout=15, context=client_context()) as r:
                return json.loads(r.read(5_000_001)[:5_000_000])
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"NWS alerts returned HTTP {e.code}") from None
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
            if is_cert_failure(e):
                raise RuntimeError(CERT_HELP.format(who="the weather service")) from None
            raise RuntimeError(f"NWS alerts unreachable: {getattr(e, 'reason', e)}") from None

    def refresh(self, force=False):
        now = time.time()
        if not force and now < self.next_try:
            return
        self.next_try = now + self.EVERY
        try:
            data = self.fetch(f"https://api.weather.gov/alerts/active?point={self.lat},{self.lon}")
            found = parse_alerts(data, self.groups)
        except (RuntimeError, AttributeError, TypeError) as e:
            with self.lock:
                self.error = str(e)
            log.warning("Weather alert check failed: %s", e)
            return
        with self.lock:
            new = {a["id"] for a in found} - {a["id"] for a in self.alerts}
            self.alerts, self.raw, self.updated, self.error = found, data, now, None
        for a in found:
            if a["id"] in new:
                log.info("Weather alert: %s", a["headline"])

    def adopt(self, old: "AlertWatch"):
        """Carry over the last answer from the checker this one replaces
        (same location), re-sorted for this one's choice of warnings."""
        if (old.lat, old.lon) != (self.lat, self.lon):
            return
        with old.lock:
            raw, updated, error = old.raw, old.updated, old.error
        with self.lock:
            if raw is not None:
                self.alerts, self.raw, self.updated = parse_alerts(raw, self.groups), raw, updated
            self.error = error

    def fresh(self) -> bool:
        with self.lock:
            return bool(self.updated) and time.time() - self.updated <= ALERT_STALE

    def active(self, now_dt) -> list[dict]:
        """Current alerts (not ended); none once the last good check is over
        2 hours old, so a lost connection can't leave an alert on for good."""
        with self.lock:
            if not self.updated or time.time() - self.updated > ALERT_STALE:
                return []
            return [a for a in self.alerts if a["ends"] is None or a["ends"] > now_dt]

    def state(self) -> dict:
        with self.lock:
            return {"checked": self.updated or None, "error": self.error}
