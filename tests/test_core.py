# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Core logic: sun math, auth signing, DST, rules, weather wording.
Run all tests from the app folder with:  python3 -m unittest -v"""
import copy
import unittest
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from eaveluxos.api import make_token, trimlight_date
from eaveluxos.schedule import ConfigError, TimeExpr, build_config, make_tz
from eaveluxos.store import DEFAULT_SETTINGS, check_password, hash_password
from eaveluxos.sun import sun_times
from eaveluxos.weather import classify

NY = ZoneInfo("America/New_York")
PHILLY = (39.9526, -75.1652)


def cfg_with(rules, **extra):
    s = copy.deepcopy(DEFAULT_SETTINGS)
    s["location"].update(latitude=PHILLY[0], longitude=PHILLY[1])
    s["rules"] = rules
    s.update(extra)
    return build_config(s, {"client_id": "x", "client_secret": "y"})


class Sun(unittest.TestCase):
    def test_published_philadelphia_times(self):
        # Published times (NOAA / timeanddate) to the minute.
        for d, rise, sset in [(date(2026, 6, 21), "05:32", "20:33"), (date(2026, 12, 21), "07:18", "16:38"),
                              (date(2026, 11, 11), "06:41", "16:48")]:
            s = sun_times(d, *PHILLY, NY)
            self.assertAlmostEqual(_mins(s["sunrise"]), _mins_s(rise), delta=1, msg=f"sunrise {d}")
            self.assertAlmostEqual(_mins(s["sunset"]), _mins_s(sset), delta=1, msg=f"sunset {d}")

    def test_polar_day_has_no_sunset(self):
        s = sun_times(date(2026, 6, 21), 78.2, 15.6, ZoneInfo("Europe/Oslo"))
        self.assertIsNone(s["sunset"])
        self.assertIsNotNone(s["noon"])


def _mins(dt):
    return dt.hour * 60 + dt.minute


def _mins_s(s):
    h, m = map(int, s.split(":"))
    return h * 60 + m


class Auth(unittest.TestCase):
    def test_trimlight_documented_vector(self):
        self.assertEqual(make_token("tester", "test_secret", 1713166849256),
                         "z02N77XySuOwv5OSUe0vrPwprRITb656xKPulS9ooXI=")

    def test_controller_weekday_numbering(self):
        self.assertEqual(trimlight_date(datetime(2026, 11, 15, tzinfo=NY))["weekday"], 1)  # Sunday
        self.assertEqual(trimlight_date(datetime(2026, 11, 14, tzinfo=NY))["weekday"], 7)  # Saturday

    def test_password_hash(self):
        h = hash_password("porchlights1")
        self.assertTrue(check_password("porchlights1", h))
        self.assertFalse(check_password("porchlights2", h))
        self.assertFalse(check_password("x", "garbage"))


class DaylightSaving(unittest.TestCase):
    def test_sunset_rule_switches_at_right_local_minute_both_weekends(self):
        c = cfg_with([{"name": "Night", "on": "sunset + 15", "off": "23:00", "effect": "warm_white"}])
        for d in (date(2026, 3, 7), date(2026, 3, 8), date(2026, 10, 31), date(2026, 11, 1)):
            w = c.schedule.day_plan(d)
            expected = sun_times(d, *PHILLY, NY)["sunset"] + timedelta(minutes=15)
            self.assertEqual(w.start, expected)
            self.assertEqual(w.end.hour, 23)
        self.assertEqual(c.schedule.day_plan(date(2026, 3, 8)).start.tzname(), "EDT")
        self.assertEqual(c.schedule.day_plan(date(2026, 3, 7)).start.tzname(), "EST")

    def test_manual_modes(self):
        self.assertEqual(datetime(2026, 1, 10, 12, tzinfo=make_tz("America/New_York", "on")).tzname(), "EDT")
        self.assertEqual(datetime(2026, 7, 10, 12, tzinfo=make_tz("America/New_York", "off")).tzname(), "EST")

    def test_clock_rule_on_spring_forward_gap(self):
        # 02:30 doesn't exist on Mar 8 2026; it must still produce a usable window.
        c = cfg_with([{"name": "Odd", "on": "02:30", "off": "04:00", "effect": "warm_white"}])
        w = c.schedule.day_plan(date(2026, 3, 8))
        self.assertIsNotNone(w)
        self.assertLess(w.start, w.end)


class Rules(unittest.TestCase):
    def test_time_expressions(self):
        self.assertEqual(TimeExpr.parse("sunset + 15").offset_min, 15)
        self.assertEqual(TimeExpr.parse("sunrise-30").offset_min, -30)
        self.assertEqual(TimeExpr.parse("11:30 pm").clock.hour, 23)
        self.assertEqual(TimeExpr.parse("24:00").clock.hour, 0)
        for bad in ("whenever", "25:00", "13:00 pm", "sunset + x"):
            with self.assertRaises(ConfigError):
                TimeExpr.parse(bad)

    def test_holiday_beats_everyday_and_wraps_new_year(self):
        c = cfg_with([{"name": "Every night", "on": "sunset", "off": "23:00", "effect": "warm_white"},
                      {"name": "Season", "dates": "12-15..01-05", "on": "sunset", "off": "23:00", "effect": "christmas"}])
        at = lambda *a: c.schedule.active_window(datetime(*a, tzinfo=NY))
        self.assertEqual(at(2026, 12, 31, 20, 0).rule.name, "Season")
        self.assertEqual(at(2027, 1, 3, 20, 0).rule.name, "Season")
        self.assertEqual(at(2027, 1, 6, 20, 0).rule.name, "Every night")

    def test_overnight_until_next_sunrise(self):
        c = cfg_with([{"name": "All night", "on": "sunset", "off": "sunrise", "effect": "warm_white"}])
        w = c.schedule.day_plan(date(2026, 12, 24))
        self.assertEqual(w.end, sun_times(date(2026, 12, 25), *PHILLY, NY)["sunrise"])
        self.assertIsNotNone(c.schedule.active_window(datetime(2026, 12, 25, 3, 0, tzinfo=NY)))

    def test_rotation_requires_interval(self):
        with self.assertRaises(ConfigError):
            cfg_with([{"name": "R", "on": "sunset", "off": "23:00", "effect": ["warm_white", "christmas"]}])

    def test_unknown_pattern_and_duplicate_names_rejected(self):
        with self.assertRaises(ConfigError):
            cfg_with([{"name": "A", "on": "sunset", "off": "23:00", "effect": "missing"}])
        with self.assertRaises(ConfigError):
            cfg_with([{"name": "A", "on": "sunset", "off": "23:00", "effect": "warm_white"}] * 2)

    def test_trimlight_guide_front_peak_zoning(self):
        # Trimlight user guide example: 26 red, 22 green, 18 zoned off (X), 25 blue.
        from eaveluxos.schedule import Effect
        e = Effect.from_config("peak", {"colors": ["#FF0000", "#00FF00", "off", "#0000FF"], "counts": [26, 22, 18, 25]})
        px = e.payload["pixels"]
        self.assertEqual([p["count"] for p in px], [26, 22, 18, 25])
        self.assertEqual([p["disable"] for p in px], [False, False, True, False])

    def test_guide_allows_90_bulbs_per_slot(self):
        from eaveluxos.schedule import Effect
        Effect.from_config("pulse", {"colors": ["#FF0000"] + ["#00FF00"] * 6, "counts": [5] + [90] * 6})
        with self.assertRaises(ConfigError):
            Effect.from_config("big", {"colors": ["#FF0000"], "counts": [91]})

    def test_bad_colors_rejected(self):
        s = copy.deepcopy(DEFAULT_SETTINGS)
        s["location"].update(latitude=40, longitude=-75)
        s["effects"]["bad"] = {"colors": ["red"], "counts": [1]}
        with self.assertRaises(ConfigError):
            build_config(s, {}, need_secrets=False)


class Weather(unittest.TestCase):
    def test_chance_forecasts_do_not_trigger(self):
        self.assertEqual(classify("Slight Chance Snow Showers", forecast=True), set())
        self.assertEqual(classify("Chance Rain And Snow", forecast=True), set())
        self.assertEqual(classify("Snow Likely", forecast=True), {"snow"})
        self.assertEqual(classify("Light Snow and Fog"), {"snow", "fog"})
        self.assertIn("storm", classify("Thunderstorms"))


if __name__ == "__main__":
    unittest.main()
