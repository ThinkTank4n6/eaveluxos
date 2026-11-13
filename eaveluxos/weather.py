# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Current weather from the US National Weather Service (api.weather.gov).

Free, no API key. Two readings are combined:
  observed  - the latest report from the nearest NWS station
  forecast  - the hourly forecast for the coming hour
Text like "Light Snow and Fog" is turned into tags (snow, fog, ...).
If NWS can't be reached, the last good reading is kept for up to 2 hours,
after which weather rules simply stop applying until it's back.
"""
import json
import logging
import re
import threading
import time
import urllib.error
import urllib.request

from .trust import CERT_HELP, client_context, is_cert_failure
from .version import VERSION

log = logging.getLogger("eaveluxos.weather")
NWS = "https://api.weather.gov"
STALE_AFTER = 2 * 3600

_PATTERNS = [
    ("storm", r"thunder|t-?storm|tstm"),
    ("snow", r"snow|flurr|sleet|ice pellet|wintry|blizzard|freezing (rain|drizzle)"),
    ("rain", r"rain|shower|drizzle"),   # see _RAIN
    ("fog", r"fog|haze|mist|smoke"),
    ("wind", r"wind|breezy|blustery"),
    ("cloudy", r"cloud|overcast"),
    ("clear", r"clear|sunny|fair"),
]


_RAIN = r"rain|shower|drizzle"


def classify(text: str, forecast: bool = False) -> set:
    t = (text or "").lower()
    if forecast:
        # "Chance Snow" / "Slight Chance Rain And Snow" are possibilities, not
        # weather. A qualifier covers its whole phrase, so split only on "then"
        # ("Chance Rain then Snow" -> the later "Snow" still counts).
        parts = [p for p in re.split(r"\s+then\s+", t) if "chance" not in p]
        t = " ".join(parts)
    tags = {tag for tag, pat in _PATTERNS if re.search(pat, t)}
    # "Snow Showers" / "Snow Shower" is snow, not rain: only call it rain if
    # rain is named some other way too ("Rain and Snow Showers").
    if "rain" in tags and not re.search(_RAIN, re.sub(r"snow\s+showers?", "snow", t)):
        tags.discard("rain")
    if "partly" in t or "mostly sunny" in t or "mostly clear" in t:
        tags.discard("cloudy")
    return tags


def c_to_f(c):
    return None if c is None else round(c * 9 / 5 + 32, 1)


class WeatherService:
    def __init__(self, lat: float, lon: float, use: str, check_minutes: int, contact: str = "", fetch=None):
        self.lat, self.lon = round(lat, 4), round(lon, 4)
        self.use = use
        self.every = check_minutes * 60
        self.ua = f"EaveLuxOS/{VERSION} ({contact or 'home lighting'})"
        self.fetch = fetch or self._fetch_json
        self.lock = threading.Lock()           # guards the readings only (never held across network calls)
        self._refresh_lock = threading.Lock()  # one refresh at a time
        self.endpoints = None  # (hourly forecast URL, stations URL)
        self.station = None
        self.observed = None   # {"text","temp_f","time"}
        self.forecast = None   # {"text","temp_f","time"}
        self.updated = 0.0
        self.next_try = 0.0
        self.error = None

    def _fetch_json(self, url: str):
        req = urllib.request.Request(url, headers={"User-Agent": self.ua, "Accept": "application/geo+json"})
        try:
            with urllib.request.urlopen(req, timeout=15, context=client_context()) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"NWS returned HTTP {e.code} for {url.split('?')[0]}") from None
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
            if is_cert_failure(e):
                raise RuntimeError(CERT_HELP.format(who="the weather service")) from None
            raise RuntimeError(f"NWS unreachable: {getattr(e, 'reason', e)}") from None

    def refresh(self, force=False):
        """Fetch new readings. The network calls happen with no lock held:
        current() is called by the scheduler and every status request, and
        must never wait on a slow NWS. Only one refresh runs at a time."""
        now = time.time()
        if not force and now < self.next_try:
            return
        if not self._refresh_lock.acquire(blocking=False):
            return  # another refresh is already in progress
        try:
            with self.lock:
                endpoints, station = self.endpoints, self.station
            observed = forecast = None
            bad = (RuntimeError, KeyError, IndexError, TypeError)

            def describe(e):
                return str(e) if isinstance(e, RuntimeError) else f"Unexpected NWS data ({e.__class__.__name__})"

            def failed(err):
                with self.lock:
                    self.endpoints, self.station = endpoints, station   # keep what was learned
                    self.error = err
                    self.next_try = now + min(self.every, 300)
                log.warning("Weather check failed: %s", err)

            try:
                if endpoints is None:
                    p = self.fetch(f"{NWS}/points/{self.lat},{self.lon}")["properties"]
                    endpoints = (p["forecastHourly"], p["observationStations"])
                hourly_url, stations_url = endpoints
            except bad as e:
                return failed(describe(e))
            # The two readings are fetched separately: with "either", a station
            # that's down mustn't throw away a good forecast (or the reverse).
            errors = []
            if self.use in ("observed", "either"):
                try:
                    if station is None:
                        feats = self.fetch(stations_url)["features"]
                        station = feats[0]["properties"]["stationIdentifier"]
                    o = self.fetch(f"{NWS}/stations/{station}/observations/latest")["properties"]
                    observed = {"text": o.get("textDescription") or "",
                                "temp_f": c_to_f((o.get("temperature") or {}).get("value")),
                                "time": o.get("timestamp")}
                except bad as e:
                    errors.append(describe(e))
            if self.use in ("forecast", "either"):
                try:
                    per = self.fetch(hourly_url)["properties"]["periods"][0]
                    t = per.get("temperature")
                    if per.get("temperatureUnit") == "C" and t is not None:
                        t = c_to_f(t)
                    forecast = {"text": per.get("shortForecast") or "", "temp_f": t, "time": per.get("startTime")}
                except bad as e:
                    errors.append(describe(e))
            if observed is None and forecast is None:
                return failed(errors[0] if errors else "No weather readings")
            if errors:
                log.warning("Weather check partly failed (using the other reading): %s", "; ".join(errors))
            with self.lock:
                self.endpoints, self.station = endpoints, station
                if observed is not None:
                    self.observed = observed
                if forecast is not None:
                    self.forecast = forecast
                self.updated = now
                self.error = None
                self.next_try = now + (min(self.every, 300) if errors else self.every)
        finally:
            self._refresh_lock.release()

    def _obs_fresh(self) -> bool:
        """Some stations report hours late; ignore observations over 2 hours old."""
        ts = (self.observed or {}).get("time")
        if not ts:
            return False
        try:
            from datetime import datetime, timezone
            age = datetime.now(timezone.utc) - datetime.fromisoformat(ts.replace("Z", "+00:00"))
            return age.total_seconds() < STALE_AFTER
        except ValueError:
            return False

    def current(self) -> dict:
        """{"tags": set, "temp_f": float|None, "summary": str, "fresh": bool}"""
        with self.lock:
            fresh = self.updated and time.time() - self.updated < STALE_AFTER
            if not fresh:
                return {"tags": set(), "temp_f": None, "summary": "", "fresh": False, "error": self.error}
            tags, texts = set(), []
            obs = self.observed if self._obs_fresh() else None
            for r, is_fc in ((obs, False), (self.forecast, True)):
                if r and r["text"]:
                    tags |= classify(r["text"], forecast=is_fc)
                    texts.append(r["text"])
            temp = (obs or {}).get("temp_f")
            if temp is None:
                temp = (self.forecast or {}).get("temp_f")
            if temp is not None and temp <= 32:
                tags.add("freezing")
            uniq = list(dict.fromkeys(texts))
            summary = " / next hour: ".join(uniq) if len(uniq) > 1 else (uniq[0] if uniq else "")
            if temp is not None:
                summary += f", {round(temp)}°F"
            return {"tags": tags, "temp_f": temp, "summary": summary.strip(", "), "fresh": True, "error": self.error}
