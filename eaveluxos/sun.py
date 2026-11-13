# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Sunrise, sunset and civil twilight for any date and place.

Uses the NOAA solar position equations (the same math as NOAA's solar
calculator spreadsheet), iterated so each event is computed at its own
moment rather than at noon. Accurate to about a minute at mid latitudes.
Results are timezone-aware datetimes in the zone you pass in, so daylight
saving time is handled by the IANA tz database, not by hand.
"""
import math
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache

ZENITH_SUN = 90.833    # sunrise/sunset: sun's upper edge on the horizon, with refraction
ZENITH_CIVIL = 96.0    # civil dawn/dusk: sun 6 degrees below the horizon


def _julian_day(d: date) -> float:
    y, m = d.year, d.month
    if m <= 2:
        y -= 1
        m += 12
    a = y // 100
    b = 2 - a + a // 4
    return math.floor(365.25 * (y + 4716)) + math.floor(30.6001 * (m + 1)) + d.day + b - 1524.5


def _solar(jd: float):
    """Returns (declination in radians, equation of time in minutes)."""
    t = (jd - 2451545.0) / 36525.0
    l0 = (280.46646 + t * (36000.76983 + t * 0.0003032)) % 360.0
    m = 357.52911 + t * (35999.05029 - 0.0001537 * t)
    e = 0.016708634 - t * (0.000042037 + 0.0000001267 * t)
    mr = math.radians(m)
    c = (math.sin(mr) * (1.914602 - t * (0.004817 + 0.000014 * t))
         + math.sin(2 * mr) * (0.019993 - 0.000101 * t)
         + math.sin(3 * mr) * 0.000289)
    omega = math.radians(125.04 - 1934.136 * t)
    app_long = math.radians(l0 + c - 0.00569 - 0.00478 * math.sin(omega))
    eps0 = 23 + (26 + (21.448 - t * (46.815 + t * (0.00059 - t * 0.001813))) / 60) / 60
    eps = math.radians(eps0 + 0.00256 * math.cos(omega))
    decl = math.asin(math.sin(eps) * math.sin(app_long))
    y = math.tan(eps / 2) ** 2
    l0r = math.radians(l0)
    eqt = 4 * math.degrees(
        y * math.sin(2 * l0r)
        - 2 * e * math.sin(mr)
        + 4 * e * y * math.sin(mr) * math.cos(2 * l0r)
        - 0.5 * y * y * math.sin(4 * l0r)
        - 1.25 * e * e * math.sin(2 * mr)
    )
    return decl, eqt


def _event_utc_minutes(d: date, lat: float, lon: float, zenith, rising):
    """Minutes after 00:00 UTC on date d (may be <0 or >1440). None if the
    sun never reaches that altitude that day (polar day/night)."""
    jd0 = _julian_day(d)
    lat_r = math.radians(lat)
    t = 720 - 4 * lon  # first guess: local solar noon
    for _ in range(4):
        decl, eqt = _solar(jd0 + t / 1440.0)
        if zenith is None:  # solar noon
            t = 720 - 4 * lon - eqt
            continue
        cos_ha = (math.cos(math.radians(zenith)) / (math.cos(lat_r) * math.cos(decl))
                  - math.tan(lat_r) * math.tan(decl))
        if cos_ha > 1 or cos_ha < -1:
            return None
        ha = math.degrees(math.acos(cos_ha))
        t = 720 - 4 * (lon + ha) - eqt if rising else 720 - 4 * (lon - ha) - eqt
    return t


@lru_cache(maxsize=512)
def sun_times(d: date, lat: float, lon: float, tz) -> dict:
    """Dict of aware datetimes in tz: dawn, sunrise, noon, sunset, dusk.
    A value is None if that event doesn't happen on that date."""
    def at(day, minutes):
        if minutes is None:
            return None
        # rounded to the nearest minute so displayed and actual switch times match
        exact = datetime(day.year, day.month, day.day, tzinfo=timezone.utc) + timedelta(minutes=minutes)
        rounded = (exact + timedelta(seconds=30)).replace(second=0, microsecond=0)
        return rounded.astimezone(tz)

    def event(zenith, rising):
        # The equations find the event nearest solar noon of a UTC date. Where
        # the clock is far from the sun's time (UTC+13/+14 in Samoa, Tonga,
        # Kiribati), that lands on the next or previous local day, so step
        # the UTC date until the event falls on local date d.
        dt = at(d, _event_utc_minutes(d, lat, lon, zenith, rising))
        if dt is not None and dt.date() != d:
            other = d + (d - dt.date())
            alt = at(other, _event_utc_minutes(other, lat, lon, zenith, rising))
            if alt is not None and alt.date() == d:
                return alt
        return dt

    return {
        "dawn": event(ZENITH_CIVIL, True),
        "sunrise": event(ZENITH_SUN, True),
        "noon": event(None, True),
        "sunset": event(ZENITH_SUN, False),
        "dusk": event(ZENITH_CIVIL, False),
    }
