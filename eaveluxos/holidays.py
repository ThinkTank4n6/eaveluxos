# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Holiday calendar (3.19): holidays that move from year to year, worked out
on this computer, so a holiday's lights never need entering again.

- Fixed dates (July 4, Halloween, Christmas).
- Rules ("fourth Thursday of November", "last Monday of May").
- Easter, and the days counted from it (Mardi Gras, Good Friday).
- Rosh Hashanah and Hanukkah, from the arithmetic of the Hebrew calendar
  (exact for any year).
- Holidays set by the moon in ways no short rule captures (Diwali, Holi,
  Lunar New Year, the two Eids): a table of published dates through
  TABLE_LAST. The Eids depend on the sighting of the new moon, so their dates
  are the expected ones and can be a day off where you live; any holiday's
  date can be moved for a year in its settings.

A holiday's lights are a schedule rule (Rule) that runs only on its nights,
with a priority above seasonal rules (HOLIDAY_PRIORITY) and below game days.
Jewish holidays begin at sundown, so their first night is the evening before
the first day; Lights show the night of every other holiday.

Other countries' public holidays come from the free Nager.Date service
(CountryHolidays), fetched once a day at most and kept in a file, so the
lights still run when it can't be reached.
"""
import json
import logging
import os
import re
import threading
import time
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path

from .trust import client_context


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None

log = logging.getLogger("eaveluxos")

HOLIDAY_PRIORITY = 210       # above seasonal (dated) rules at 200, below game days at 250
COUNTRY_PRIORITY = 205       # another country's public holidays: below the holidays picked by name
TABLE_LAST = 2035            # the moon-set holidays' table runs through this year
MAX_AROUND = 45              # days before / after a holiday (a season)


# ---------------------------------------------------------------- calendar math
def nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """n-th weekday (Mon=0) of the month; n=-1 is the last."""
    if n > 0:
        d = date(year, month, 1)
        return d + timedelta(days=(weekday - d.weekday()) % 7 + 7 * (n - 1))
    d = date(year + (month == 12), month % 12 + 1, 1) - timedelta(days=1)
    return d - timedelta(days=(d.weekday() - weekday) % 7)


def easter(year: int) -> date:
    """Western Easter (the anonymous Gregorian algorithm)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    return date(year, month, (h + l - 7 * m + 114) % 31 + 1)


# The Hebrew calendar (from Reingold & Dershowitz, Calendrical Calculations).
# Day numbers are Python's date ordinals (1 = January 1 of year 1).
_HEBREW_EPOCH = -1373427


def _elapsed(y: int) -> int:
    months = (235 * y - 234) // 19
    parts = 12084 + 13753 * months
    day = 29 * months + parts // 25920
    return day + 1 if (3 * (day + 1)) % 7 < 3 else day


def _new_year(y: int) -> int:
    ny0, ny1, ny2 = _elapsed(y - 1), _elapsed(y), _elapsed(y + 1)
    fix = 2 if ny2 - ny1 == 356 else 1 if ny1 - ny0 == 382 else 0
    return _HEBREW_EPOCH + ny1 + fix


def rosh_hashanah(year: int) -> date:
    """1 Tishri falling in this Gregorian year."""
    return date.fromordinal(_new_year(year + 3761))


def hanukkah(year: int) -> date:
    """25 Kislev falling in this Gregorian year (the first candle is lit the
    evening before)."""
    y = year + 3761
    length = _new_year(y + 1) - _new_year(y)
    heshvan = 30 if length % 10 == 5 else 29       # a "complete" year has a long Heshvan
    return date.fromordinal(_new_year(y) + 30 + heshvan + 24)


# Published dates (main day), checked against several almanacs: Diwali
# (Lakshmi Puja), Holi (Rangwali Holi / Dhulandi), Lunar New Year, and the
# expected dates of Eid al-Fitr and Eid al-Adha (moon sighting can move them
# a day). Some places keep Diwali and Holi a day apart from India's date.
TABLE = {
    "diwali": {2026: ["11-08"], 2027: ["10-29"], 2028: ["10-17"], 2029: ["11-05"], 2030: ["10-26"],
               2031: ["11-14"], 2032: ["11-02"], 2033: ["10-22"], 2034: ["11-10"], 2035: ["10-30"]},
    "holi": {2026: ["03-04"], 2027: ["03-22"], 2028: ["03-11"], 2029: ["03-01"], 2030: ["03-20"],
             2031: ["03-09"], 2032: ["03-27"], 2033: ["03-16"], 2034: ["03-05"], 2035: ["03-24"]},
    "lunar_new_year": {2026: ["02-17"], 2027: ["02-06"], 2028: ["01-26"], 2029: ["02-13"], 2030: ["02-03"],
                       2031: ["01-23"], 2032: ["02-11"], 2033: ["01-31"], 2034: ["02-19"], 2035: ["02-08"]},
    "eid_al_fitr": {2026: ["03-20"], 2027: ["03-09"], 2028: ["02-26"], 2029: ["02-14"], 2030: ["02-04"],
                    2031: ["01-24"], 2032: ["01-14"], 2033: ["01-02", "12-23"], 2034: ["12-12"], 2035: ["12-01"]},
    "eid_al_adha": {2026: ["05-27"], 2027: ["05-16"], 2028: ["05-05"], 2029: ["04-24"], 2030: ["04-13"],
                    2031: ["04-02"], 2032: ["03-22"], 2033: ["03-11"], 2034: ["03-01"], 2035: ["02-19"]},
}

# key -> (name, group, how, nights, eve, approximate)
#   how: ("fixed", m, d) | ("nth", month, weekday, n) | ("easter", offset) |
#        ("rosh_hashanah",) | ("hanukkah",) | ("table",)
#   nights: how many nights it lasts; eve: lights start the evening before
HOLIDAYS = {
    "new_years_day": ("New Year's Day", "U.S.", ("fixed", 1, 1), 1, False, False),
    "mlk_day": ("Martin Luther King Jr. Day", "U.S.", ("nth", 1, 0, 3), 1, False, False),
    "valentines": ("Valentine's Day", "U.S.", ("fixed", 2, 14), 1, False, False),
    "presidents_day": ("Presidents' Day", "U.S.", ("nth", 2, 0, 3), 1, False, False),
    "st_patricks": ("St. Patrick's Day", "U.S.", ("fixed", 3, 17), 1, False, False),
    "mothers_day": ("Mother's Day", "U.S.", ("nth", 5, 6, 2), 1, False, False),
    "memorial_day": ("Memorial Day", "U.S.", ("nth", 5, 0, -1), 1, False, False),
    "fathers_day": ("Father's Day", "U.S.", ("nth", 6, 6, 3), 1, False, False),
    "juneteenth": ("Juneteenth", "U.S.", ("fixed", 6, 19), 1, False, False),
    "independence_day": ("Independence Day", "U.S.", ("fixed", 7, 4), 1, False, False),
    "labor_day": ("Labor Day", "U.S.", ("nth", 9, 0, 1), 1, False, False),
    "columbus_day": ("Columbus / Indigenous Peoples' Day", "U.S.", ("nth", 10, 0, 2), 1, False, False),
    "halloween": ("Halloween", "U.S.", ("fixed", 10, 31), 1, False, False),
    "veterans_day": ("Veterans Day", "U.S.", ("fixed", 11, 11), 1, False, False),
    "thanksgiving": ("Thanksgiving", "U.S.", ("nth", 11, 3, 4), 1, False, False),
    "christmas_eve": ("Christmas Eve", "Christian", ("fixed", 12, 24), 1, False, False),
    "christmas": ("Christmas Day", "Christian", ("fixed", 12, 25), 1, False, False),
    "new_years_eve": ("New Year's Eve", "U.S.", ("fixed", 12, 31), 1, False, False),
    "mardi_gras": ("Mardi Gras", "Christian", ("easter", -47), 1, False, False),
    "good_friday": ("Good Friday", "Christian", ("easter", -2), 1, False, False),
    "easter": ("Easter", "Christian", ("easter", 0), 1, False, False),
    "rosh_hashanah": ("Rosh Hashanah", "Jewish", ("rosh_hashanah",), 2, True, False),
    "hanukkah": ("Hanukkah", "Jewish", ("hanukkah",), 8, True, False),
    "lunar_new_year": ("Lunar New Year", "Asian", ("table",), 1, False, False),
    "holi": ("Holi", "Hindu", ("table",), 1, False, False),
    "diwali": ("Diwali", "Hindu", ("table",), 1, False, False),
    "eid_al_fitr": ("Eid al-Fitr", "Muslim", ("table",), 1, False, True),
    "eid_al_adha": ("Eid al-Adha", "Muslim", ("table",), 1, False, True),
    "kwanzaa": ("Kwanzaa", "U.S.", ("fixed", 12, 26), 7, False, False),
}
GROUPS = ["U.S.", "Christian", "Jewish", "Hindu", "Muslim", "Asian"]


def _p(label, colors, counts=None, mode=0, speed=100, brightness=220):
    return {"label": label, "colors": colors, "counts": counts or [3] * len(colors),
            "custom_mode": mode, "speed": speed, "brightness": brightness}


# Ready-made themed patterns for each holiday (a short playlist), added to
# the user's patterns when a holiday is picked without patterns of its own.
THEMES = {
    "new_years_day": [_p("New Year sparkle", ["#FFD700", "#FFFFFF", "#C0C0C0"], mode=5, speed=150)],
    "mlk_day": [_p("MLK Day", ["#FFFFFF", "#FFC58A"], [4, 4], mode=6, speed=40)],
    "valentines": [_p("Valentine hearts", ["#FF0030", "#FF60A0", "#FFFFFF"], mode=6, speed=60),
                   _p("Valentine chase", ["#FF0030", "#FF60A0"], [4, 2], mode=1, speed=60)],
    "presidents_day": [_p("Presidents' Day", ["#FF0000", "#FFFFFF", "#0030FF"], [4, 4, 4])],
    "st_patricks": [_p("Shamrock", ["#00C000", "#FFFFFF", "#FF9000"], [4, 2, 2]),
                    _p("Shamrock twinkle", ["#00C000", "#80FF00"], [3, 3], mode=5, speed=120)],
    "mothers_day": [_p("Mother's Day", ["#FF60A0", "#C0A0FF", "#FFFFFF"], mode=6, speed=50)],
    "memorial_day": [_p("Memorial Day", ["#FF0000", "#FFFFFF", "#0030FF"], [4, 4, 4], brightness=180)],
    "fathers_day": [_p("Father's Day", ["#0030FF", "#60C0FF", "#FFFFFF"], mode=11, speed=60)],
    "juneteenth": [_p("Juneteenth", ["#FF0000", "#FFFFFF", "#0030FF"], [4, 4, 4], mode=6, speed=50)],
    "independence_day": [_p("Fourth of July", ["#FF0000", "#FFFFFF", "#0030FF"], [4, 4, 4]),
                         _p("Fireworks", ["#FF0000", "#FFFFFF", "#0030FF"], [2, 2, 2], mode=9, speed=200)],
    "labor_day": [_p("Labor Day", ["#FF0000", "#FFFFFF", "#0030FF"], [4, 4, 4], mode=11, speed=50)],
    "columbus_day": [_p("Autumn day", ["#FF5000", "#FFD700", "#DC143C"], mode=6, speed=40)],
    "halloween": [_p("Halloween", ["#FF5000", "#8000FF", "#00C000"], [4, 3, 2], mode=5, speed=120),
                  _p("Spooky chase", ["#FF5000", "#8000FF"], [5, 5], mode=1, speed=90)],
    "veterans_day": [_p("Veterans Day", ["#FF0000", "#FFFFFF", "#0030FF"], [4, 4, 4], brightness=200)],
    "thanksgiving": [_p("Harvest", ["#FF5000", "#FFD700", "#DC143C", "#FF9000"], mode=6, speed=40),
                     _p("Harvest glow", ["#FF9000", "#FFC58A"], [4, 4], mode=11, speed=40)],
    "christmas_eve": [_p("Christmas Eve", ["#FF0000", "#00C000", "#FFC58A"], mode=5, speed=80)],
    "christmas": [_p("Christmas", ["#FF0000", "#00C000"], [3, 3]),
                  _p("Christmas twinkle", ["#FF0000", "#00C000", "#FFFFFF"], mode=5, speed=100)],
    "new_years_eve": [_p("Countdown", ["#FFD700", "#FFFFFF", "#8000FF"], mode=5, speed=180),
                      _p("Midnight chase", ["#FFD700", "#FFFFFF"], [3, 3], mode=1, speed=150)],
    "mardi_gras": [_p("Mardi Gras", ["#8000FF", "#00C000", "#FFD700"], [3, 3, 3], mode=1, speed=120)],
    "good_friday": [_p("Good Friday", ["#8000FF", "#FFFFFF"], [3, 3], brightness=150)],
    "easter": [_p("Easter pastels", ["#FFB0D0", "#C0A0FF", "#A0E0FF", "#FFF0A0", "#B0FFC0"], mode=6, speed=40),
               _p("Easter chase", ["#FFB0D0", "#A0E0FF", "#FFF0A0"], mode=11, speed=40)],
    "rosh_hashanah": [_p("Rosh Hashanah", ["#FFD700", "#FFFFFF", "#FF9000"], mode=6, speed=40)],
    "hanukkah": [_p("Hanukkah", ["#0030FF", "#FFFFFF"], [3, 3]),
                 _p("Hanukkah candles", ["#0030FF", "#FFFFFF", "#FFD700"], mode=5, speed=60)],
    "lunar_new_year": [_p("Lunar New Year", ["#FF0000", "#FFD700"], [4, 2]),
                       _p("Lantern glow", ["#FF0000", "#FF5000", "#FFD700"], mode=6, speed=50)],
    "holi": [_p("Holi colors", ["#FF00C0", "#FFE000", "#00C000", "#0030FF", "#FF5000", "#8000FF"], mode=1, speed=120)],
    "diwali": [_p("Diwali lamps", ["#FFD700", "#FF9000", "#FF5000"], mode=5, speed=60),
               _p("Diwali rangoli", ["#FF00C0", "#FFD700", "#00C060", "#FF5000"], mode=6, speed=50)],
    "eid_al_fitr": [_p("Eid al-Fitr", ["#00C060", "#FFD700", "#FFFFFF"], mode=5, speed=60)],
    "eid_al_adha": [_p("Eid al-Adha", ["#00C060", "#FFD700", "#FFFFFF"], mode=6, speed=40)],
    "kwanzaa": [_p("Kwanzaa", ["#FF0000", "#000000", "#00C000"], [3, 3, 3])],
}


class HolidayError(ValueError):
    pass


def occurrences(key: str, year: int) -> list[date]:
    """The holiday's main day(s) in this Gregorian year ([] if not known)."""
    how = HOLIDAYS[key][2]
    kind = how[0]
    if kind == "fixed":
        return [date(year, how[1], how[2])]
    if kind == "nth":
        return [nth_weekday(year, how[1], how[2], how[3])]
    if kind == "easter":
        return [easter(year) + timedelta(days=how[1])]
    if kind == "rosh_hashanah":
        return [rosh_hashanah(year)]
    if kind == "hanukkah":
        return [hanukkah(year)]
    return [date(year, *map(int, md.split("-"))) for md in TABLE.get(key, {}).get(year, [])]


def known_until(key: str) -> int | None:
    """The last year a table holiday's date is known (None: any year)."""
    return TABLE_LAST if HOLIDAYS[key][2][0] == "table" else None


def first_nights(key: str, year: int, moved: dict | None = None) -> list[date]:
    """The first night of each occurrence in this year: the evening before
    for holidays that begin at sundown; a date moved for this year wins."""
    m = (moved or {}).get(str(year))
    if m:
        return [date.fromisoformat(m)]
    eve = HOLIDAYS[key][4]
    return [d - timedelta(days=1) if eve else d for d in occurrences(key, year)]


class HolidayNights:
    """The nights a holiday's rule runs, for any year (Rule.only_dates):
    `night in HolidayNights(...)`. Worked out per year when first asked."""

    def __init__(self, key: str, before: int = 0, after: int = 0, moved: dict | None = None):
        self.key, self.before, self.after, self.moved = key, before, after, dict(moved or {})
        self.nights = HOLIDAYS[key][3]
        self._years: dict[int, frozenset] = {}

    def year(self, y: int) -> frozenset:
        if y not in self._years:
            out = set()
            for first in first_nights(self.key, y, self.moved):
                start = first - timedelta(days=self.before)
                for k in range(self.before + self.nights + self.after):
                    out.add(start + timedelta(days=k))
            self._years[y] = frozenset(out)
        return self._years[y]

    def __contains__(self, d) -> bool:
        return any(d in self.year(y) for y in (d.year - 1, d.year, d.year + 1))


class DateSet:
    """Fixed dates (another country's public holidays) in the same shape."""

    def __init__(self, dates):
        self.dates = frozenset(dates)

    def __contains__(self, d) -> bool:
        return d in self.dates


def check_entry(e: dict, effects: dict, where: str = "Holiday") -> dict:
    """One picked holiday from settings -> its parts, or HolidayError."""
    if not isinstance(e, dict):
        raise HolidayError(f"{where}: malformed.")
    key = e.get("key")
    if key not in HOLIDAYS:
        raise HolidayError(f"{where}: unknown holiday '{key}'.")
    name = HOLIDAYS[key][0]
    effs = e.get("effects")
    if not isinstance(effs, list) or not 1 <= len(effs) <= 6 or not all(isinstance(k, str) and k in effects for k in effs):
        raise HolidayError(f"{name}: choose 1 to 6 of your patterns.")
    out = {"key": key, "name": name, "effects": effs}
    for k in ("before", "after"):
        v = e.get(k, 0)
        if isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= MAX_AROUND:
            raise HolidayError(f"{name}: days {k} is 0 to {MAX_AROUND}.")
        out[k] = v
    rot = e.get("rotate", 15)
    if isinstance(rot, bool) or not isinstance(rot, int) or not 1 <= rot <= 240:
        raise HolidayError(f"{name}: each pattern shows 1 to 240 minutes.")
    out["rotate"] = rot
    moved = e.get("moved") or {}
    if isinstance(moved, dict):
        # Dates moved for years gone by don't count (they'd pile up; 3.19.1).
        this = date.today().year
        moved = {y: d for y, d in moved.items() if not (re.fullmatch(r"\d{4}", str(y)) and int(y) < this - 1)}
    if not isinstance(moved, dict) or len(moved) > 20:
        raise HolidayError(f"{name}: moved dates are malformed.")
    for y, d in moved.items():
        try:
            ok = re.fullmatch(r"\d{4}", str(y)) and date.fromisoformat(str(d)).year in (int(y) - 1, int(y), int(y) + 1)
        except ValueError:
            ok = False
        if not ok:
            raise HolidayError(f"{name}: the date moved for {y} should be a date like {y}-11-26.")
    out["moved"] = {str(y): str(d) for y, d in moved.items()}
    out["on"] = str(e.get("on") or "sunset")
    out["off"] = str(e.get("off") or "23:00")
    return out


def summary(today: date, picked: dict, years: int = 2) -> list[dict]:
    """Every holiday with its coming nights (the Holidays panel)."""
    out = []
    for key, (name, group, how, nights, eve, approx) in HOLIDAYS.items():
        e = picked.get(key) or {}
        hn = HolidayNights(key, e.get("before", 0), e.get("after", 0), e.get("moved"))
        nxt, starts = [], []
        for y in range(today.year, today.year + years + 1):
            for first in first_nights(key, y, hn.moved):
                if first + timedelta(days=nights - 1 + hn.after) >= today:
                    nxt.append(first.isoformat())
                    starts.append((first - timedelta(days=hn.before)).isoformat())   # lights start (3.19.1)
        out.append({"key": key, "name": name, "group": group, "nights": nights, "eve": eve, "approximate": approx,
                    "known_until": known_until(key), "next": nxt[:3], "starts": starts[:3],
                    "missing": known_until(key) is not None and today.year + 1 > TABLE_LAST,
                    "theme": THEMES.get(key, [])})
    return out


# ---------------------------------------------------------------- other countries (Nager.Date)
NAGER = "https://date.nager.at/api/v3/PublicHolidays/"
MAX_BYTES = 200_000
EVERY = 7 * 86400            # a country's holidays rarely change; once a week is plenty
RETRY = 6 * 3600


def _fetch(url: str) -> bytes:
    if not url.startswith(NAGER):
        raise HolidayError("Not a holiday service address.")
    req = urllib.request.Request(url, headers={"User-Agent": "EaveLuxOS", "Accept": "application/json"})
    # Never follow a redirect elsewhere, like the other services (3.19.1).
    opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=client_context()), _NoRedirect)
    try:
        with opener.open(req, timeout=20) as r:
            raw = r.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as e:
        e.close()
        if e.code == 404:
            raise HolidayError("The holiday service doesn't know that country.") from None
        raise HolidayError(f"The holiday service answered {e.code}.") from None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise HolidayError(f"Couldn't reach the holiday service: {getattr(e, 'reason', e)}") from None
    if len(raw) > MAX_BYTES:
        raise HolidayError("The holiday service's answer was too large.")
    return raw


def parse_public(raw: bytes) -> list[dict]:
    """Nager.Date's answer -> [{"date": "YYYY-MM-DD", "name": ...}] (data only)."""
    try:
        data = json.loads(raw)
    except ValueError:
        raise HolidayError("The holiday service's answer wasn't readable.") from None
    if not isinstance(data, list):
        raise HolidayError("The holiday service's answer wasn't a list.")
    out = []
    for h in data[:100]:
        if not isinstance(h, dict) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(h.get("date", ""))):
            continue
        if h.get("global") is False:          # one region only (a state's holiday)
            continue
        name = re.sub(r"\s+", " ", str(h.get("name") or h.get("localName") or "Holiday")).strip()[:60]
        out.append({"date": h["date"], "name": name})
    return out


class CountryHolidays:
    """Public holidays (this year and next) per country, kept in a file.
    3.19.1: one entry per country, so checking another country never wipes
    the chosen one's dates; and a newly chosen country (or one whose last
    check failed) is checked on the next pass, not a week later."""

    MAX_CODES = 8

    def __init__(self, data_dir: Path, fetch=None, now=time.time, today=date.today, on_change=None):
        self.path = Path(data_dir) / "country-holidays.json"
        self.fetch = fetch or _fetch
        self.now, self.today, self.on_change = now, today, on_change
        self.lock = threading.Lock()
        self.cache = self._load()           # code -> {"holidays": [...], "fetched", "error"}
        self.next_at = 0.0
        self.last_code = None
        self.thread = None
        self.stop = threading.Event()

    @staticmethod
    def _entry(raw) -> dict:
        hs = [h for h in (raw.get("holidays") or []) if isinstance(h, dict)
              and re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(h.get("date", "")))][:300]
        return {"holidays": hs, "fetched": raw.get("fetched") if isinstance(raw.get("fetched"), (int, float)) else 0,
                "error": raw.get("error") if isinstance(raw.get("error"), str) else None}

    def _load(self) -> dict:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if not isinstance(raw, dict):
            return {}
        if "code" in raw and "holidays" in raw:               # 3.19.0's file: one country
            code = str(raw.get("code") or "")
            return {code: self._entry(raw)} if re.fullmatch(r"[A-Z]{2}", code) else {}
        return {k: self._entry(v) for k, v in raw.items() if re.fullmatch(r"[A-Z]{2}", k) and isinstance(v, dict)}

    def _save(self):
        try:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.cache, indent=1), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError as e:
            log.warning("Couldn't save the public holidays: %s", e)

    def dates(self, code: str) -> list[date]:
        with self.lock:
            c = self.cache.get(code) or {}
            return [date.fromisoformat(h["date"]) for h in c.get("holidays", [])]

    def state(self, code: str) -> dict:
        with self.lock:
            c = self.cache.get(code) or {"holidays": [], "fetched": 0, "error": None}
            today = self.today().isoformat()
            return {"code": code, "fetched": c["fetched"], "error": c["error"],
                    "next": [h for h in c["holidays"] if h["date"] >= today][:6]}

    def due(self, code: str) -> bool:
        """Never checked, or the last check failed: check on the next pass."""
        with self.lock:
            c = self.cache.get(code)
        return not c or not c["fetched"] or bool(c["error"])

    def refresh(self, code: str) -> bool:
        """Fetch this year's and next year's; True if the dates changed. A
        failure keeps what was known."""
        if not re.fullmatch(r"[A-Z]{2}", code or ""):
            return False
        y = self.today().year
        try:
            hs = parse_public(self.fetch(f"{NAGER}{y}/{code}")) + parse_public(self.fetch(f"{NAGER}{y + 1}/{code}"))
            hs = sorted({h["date"]: h for h in hs}.values(), key=lambda h: h["date"])     # each date once
        except HolidayError as e:
            with self.lock:
                old = self.cache.get(code) or {"holidays": [], "fetched": 0}
                self.cache[code] = {**old, "error": str(e)}
                self._save()
            log.info("Public holidays for %s: %s", code, e)
            return False
        with self.lock:
            old = (self.cache.get(code) or {}).get("holidays")
            self.cache[code] = {"holidays": hs, "fetched": self.now(), "error": None}
            if len(self.cache) > self.MAX_CODES:                # forget the countries checked longest ago
                for k in sorted((k for k in self.cache if k != code), key=lambda k: self.cache[k]["fetched"])[
                        :len(self.cache) - self.MAX_CODES]:
                    del self.cache[k]
            self._save()
        return hs != old

    def step(self, code) -> None:
        """One pass of the background loop (tests call it directly)."""
        if not code:
            return
        if code != self.last_code:
            self.last_code = code
            if self.due(code):
                self.next_at = 0.0                  # a newly chosen country: now, not next week
        if self.now() < self.next_at:
            return
        changed = self.refresh(code)
        self.next_at = self.now() + (RETRY if self.due(code) else EVERY)
        if changed and self.on_change:
            self.on_change()

    def _loop(self, code_fn):
        while not self.stop.wait(60):
            try:
                self.step(code_fn())
            except Exception:
                log.exception("Public holiday refresh failed")
                self.next_at = self.now() + RETRY

    def start(self, code_fn):
        if self.thread is None:
            self.thread = threading.Thread(target=self._loop, args=(code_fn,), daemon=True, name="holidays")
            self.thread.start()
