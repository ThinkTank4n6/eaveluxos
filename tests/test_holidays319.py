# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""3.19: the holiday calendar. Dates are checked against published ones."""
import copy
import json
import shutil
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

from eaveluxos import holidays as H
from eaveluxos.controller import Controller
from eaveluxos.schedule import ConfigError, Location, build_config
from eaveluxos.server import ApiError, App
from eaveluxos.store import DEFAULT_SETTINGS
from tests.test_controller import FakeAPI
from tests.test_triggers316 import NY

SECRETS = {"client_id": "x", "client_secret": "y"}
D = date.fromisoformat


class CalendarMath(unittest.TestCase):
    def test_rule_based_us_holidays(self):
        want = {
            "thanksgiving": ["2026-11-26", "2027-11-25", "2028-11-23", "2030-11-28"],
            "memorial_day": ["2026-05-25", "2027-05-31", "2028-05-29"],
            "mlk_day": ["2026-01-19", "2027-01-18", "2028-01-17"],
            "mothers_day": ["2026-05-10", "2027-05-09", "2028-05-14"],
            "fathers_day": ["2026-06-21", "2027-06-20", "2028-06-18"],
            "labor_day": ["2026-09-07", "2027-09-06", "2028-09-04"],
            "presidents_day": ["2026-02-16", "2027-02-15", "2028-02-21"],
            "columbus_day": ["2026-10-12", "2027-10-11", "2028-10-09"],
        }
        for key, dates in want.items():
            for d in dates:
                self.assertEqual(H.occurrences(key, D(d).year), [D(d)], key)

    def test_easter_and_the_days_from_it(self):
        for d in ("2024-03-31", "2025-04-20", "2026-04-05", "2027-03-28", "2028-04-16", "2029-04-01", "2030-04-21", "2038-04-25"):
            self.assertEqual(H.easter(D(d).year), D(d))
        self.assertEqual(H.occurrences("mardi_gras", 2026), [D("2026-02-17")])
        self.assertEqual(H.occurrences("good_friday", 2026), [D("2026-04-03")])

    def test_hebrew_calendar(self):
        rh = {2024: "2024-10-03", 2025: "2025-09-23", 2026: "2026-09-12", 2027: "2027-10-02", 2028: "2028-09-21",
              2029: "2029-09-10", 2030: "2030-09-28", 2031: "2031-09-18"}
        for y, d in rh.items():
            self.assertEqual(H.rosh_hashanah(y), D(d), y)
        # The first candle (the evening before 25 Kislev), as published.
        first = {2024: "2024-12-25", 2025: "2025-12-14", 2026: "2026-12-04", 2027: "2027-12-24", 2028: "2028-12-12",
                 2029: "2029-12-01", 2030: "2030-12-20", 2031: "2031-12-09", 2032: "2032-11-27"}
        for y, d in first.items():
            self.assertEqual(H.first_nights("hanukkah", y), [D(d)], y)
        self.assertEqual(H.first_nights("rosh_hashanah", 2026), [D("2026-09-11")], "begins at sundown")

    def test_table_holidays_are_known_through_the_last_year(self):
        for key in H.TABLE:
            for y in range(2026, H.TABLE_LAST + 1):
                self.assertTrue(H.occurrences(key, y), f"{key} {y}")
            self.assertEqual(H.occurrences(key, H.TABLE_LAST + 1), [], "unknown, not guessed")
            self.assertEqual(H.known_until(key), H.TABLE_LAST)
        # Spot checks against published dates and their weekdays.
        self.assertEqual(H.occurrences("diwali", 2026), [D("2026-11-08")])
        self.assertEqual(D("2026-11-08").weekday(), 6)
        self.assertEqual(H.occurrences("holi", 2031), [D("2031-03-09")])
        self.assertEqual(H.occurrences("lunar_new_year", 2027), [D("2027-02-06")])
        self.assertEqual(len(H.occurrences("eid_al_fitr", 2033)), 2, "twice in 2033")
        self.assertTrue(H.HOLIDAYS["eid_al_fitr"][5] and H.HOLIDAYS["eid_al_adha"][5], "marked approximate")
        self.assertIsNone(H.known_until("thanksgiving"))

    def test_every_holiday_has_a_theme_that_is_a_valid_pattern(self):
        from eaveluxos.schedule import Effect
        for key in H.HOLIDAYS:
            self.assertIn(key, H.THEMES)
            for p in H.THEMES[key]:
                Effect.from_config("t", p)

    def test_nights(self):
        hn = H.HolidayNights("hanukkah")
        nights = [D("2026-12-04") + __import__("datetime").timedelta(days=k) for k in range(8)]
        self.assertTrue(all(n in hn for n in nights))
        self.assertNotIn(D("2026-12-03"), hn)
        self.assertNotIn(D("2026-12-12"), hn)
        kw = H.HolidayNights("kwanzaa")
        self.assertIn(D("2027-01-01"), kw, "across New Year")
        self.assertNotIn(D("2027-01-02"), kw)
        season = H.HolidayNights("halloween", before=6)
        self.assertIn(D("2026-10-25"), season)
        self.assertNotIn(D("2026-10-24"), season)
        moved = H.HolidayNights("diwali", moved={"2026": "2026-11-09"})
        self.assertIn(D("2026-11-09"), moved)
        self.assertNotIn(D("2026-11-08"), moved)
        self.assertIn(D("2027-10-29"), moved, "only that year moves")

    def test_entry_checks(self):
        eff = {"a": 1, "b": 1}
        ok = H.check_entry({"key": "easter", "effects": ["a"]}, eff)
        self.assertEqual((ok["on"], ok["off"], ok["before"], ok["rotate"]), ("sunset", "23:00", 0, 15))
        for bad in ({"key": "nope", "effects": ["a"]}, {"key": "easter", "effects": []},
                    {"key": "easter", "effects": ["zzz"]}, {"key": "easter", "effects": ["a"], "before": 46},
                    {"key": "easter", "effects": ["a"], "before": True}, {"key": "easter", "effects": ["a"], "rotate": 0},
                    {"key": "easter", "effects": ["a"], "moved": {"2026": "2030-01-01"}},
                    {"key": "easter", "effects": ["a"], "moved": {"2026": "soon"}}, "easter"):
            with self.assertRaises(H.HolidayError, msg=bad):
                H.check_entry(bad, eff)


def settings(**hol):
    s = copy.deepcopy(DEFAULT_SETTINGS)
    s["location"].update(latitude=39.95, longitude=-75.17)
    s["rules"] = [{"name": "Night", "on": "sunset", "off": "23:00", "effect": "warm_white"},
                  {"name": "Christmas season", "on": "sunset", "off": "23:00", "effect": "christmas", "dates": "11-20..01-06"}]
    s["effects"]["harvest"] = H.THEMES["thanksgiving"][0]
    s["holidays"] = {"enabled": True, "list": [{"key": "thanksgiving", "effects": ["harvest", "warm_white"], "rotate": 20}], **hol}
    return s


class HolidayRules(unittest.TestCase):
    def setUp(self):
        self.clock = [datetime(2026, 11, 26, 7, 0, tzinfo=NY)]
        orig = Location.now
        self.addCleanup(setattr, Location, "now", orig)
        Location.now = lambda loc: self.clock[0]

    def ctrl(self, s, **kw):
        c = Controller(build_config(s, SECRETS, **kw), FakeAPI())
        c.devices = [{"deviceId": "D1", "name": "House"}]
        return c

    def at(self, c, *dt):
        self.clock[0] = datetime(*dt, tzinfo=NY)
        c.next_try = 0
        c.tick()
        return c._target()

    def test_holiday_beats_the_season_and_comes_back_every_year(self):
        c = self.ctrl(settings())
        t = self.at(c, 2026, 11, 26, 19)
        self.assertEqual(t.source, "Thanksgiving")
        self.assertIn(t.effect.key, ("harvest", "warm_white"), "its playlist")
        self.assertEqual(self.at(c, 2026, 11, 27, 19).source, "Christmas season")
        self.assertEqual(self.at(c, 2027, 11, 25, 19).source, "Thanksgiving", "next year's date, worked out")
        self.assertEqual(self.at(c, 2027, 11, 26, 19).source, "Christmas season")
        rule = next(r for r in c.cfg.schedule.rules if r.holiday)
        self.assertEqual(rule.priority, H.HOLIDAY_PRIORITY)

    def test_the_playlist_is_loaded_in_the_morning(self):
        c = self.ctrl(settings())
        self.at(c, 2026, 11, 26, 5, 30)
        self.assertFalse(any("Today is" in e["msg"] for e in c.events), "not before 6 AM")
        self.at(c, 2026, 11, 26, 6, 1)
        self.at(c, 2026, 11, 26, 9, 0)
        notes = [e["msg"] for e in c.events if "Today is" in e["msg"]]
        self.assertEqual(len(notes), 1, "once a day")
        self.assertIn("Thanksgiving", notes[0])
        self.assertIn("Harvest", notes[0])
        h = c.status()["holiday"]
        self.assertEqual((h["name"], h["patterns"]), ("Thanksgiving", ["Harvest", "Warm white"]))
        self.at(c, 2026, 11, 27, 9, 0)
        self.assertIsNone(c.status()["holiday"])

    def test_off_holiday_lights_and_game_days_win(self):
        s = settings()
        s["holidays"]["enabled"] = False
        c = self.ctrl(s)
        self.assertEqual(self.at(c, 2026, 11, 26, 19).source, "Christmas season")
        s = settings()
        s["gameday"] = {"enabled": True, "teams": [{"league": "nfl", "team": "phi", "name": "Eagles", "effect": "christmas"}]}
        c = self.ctrl(s, gamedates={"nfl-phi": {date(2026, 11, 26)}})
        self.assertIn("game day", self.at(c, 2026, 11, 26, 19).source)

    def test_country_holidays_rank_below_picked_ones(self):
        s = settings(country={"code": "CA", "effects": ["warm_white"]})
        c = self.ctrl(s, country_dates={"CA": [date(2026, 11, 26), date(2026, 12, 26)]})
        self.assertEqual(self.at(c, 2026, 11, 26, 19).source, "Thanksgiving")
        self.assertEqual(self.at(c, 2026, 12, 26, 19).source, "Public holidays (CA)")
        with self.assertRaises(ConfigError):
            build_config(settings(country={"code": "Canada", "effects": ["warm_white"]}), SECRETS)

    def test_bad_settings_are_refused_and_names_dont_clash(self):
        s = settings()
        s["holidays"]["list"].append({"key": "thanksgiving", "effects": ["harvest"]})
        with self.assertRaises(ConfigError):
            build_config(s, SECRETS)
        s = settings()
        s["rules"].append({"name": "Thanksgiving", "on": "18:00", "off": "22:00", "effect": "warm_white", "dates": "11-26"})
        names = [r.name for r in build_config(s, SECRETS).schedule.rules]
        self.assertIn("Thanksgiving (holiday)", names)


class CountryService(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.d, ignore_errors=True)

    def test_fetch_parse_keep_and_fail_safe(self):
        calls = []
        ans = [{"date": "2026-07-01", "name": "Canada Day", "global": True},
               {"date": "2026-08-03", "name": "Civic Holiday", "global": False},
               {"date": "bad"}, "junk"]

        def fetch(url):
            calls.append(url)
            return json.dumps(ans).encode()
        ch = H.CountryHolidays(self.d, fetch=fetch, today=lambda: date(2026, 6, 1))
        self.assertTrue(ch.refresh("CA"))
        self.assertEqual(calls, [H.NAGER + "2026/CA", H.NAGER + "2027/CA"])
        self.assertEqual(ch.dates("CA"), [date(2026, 7, 1)], "each date once")
        self.assertEqual(ch.dates("GB"), [], "another country's dates aren't used")
        self.assertEqual(ch.state("CA")["next"][0]["name"], "Canada Day")

        def down(url):
            raise H.HolidayError("Couldn't reach the holiday service")
        ch2 = H.CountryHolidays(self.d, fetch=down, today=lambda: date(2026, 6, 1))
        self.assertEqual(ch2.dates("CA")[0], date(2026, 7, 1), "kept in the file")
        self.assertFalse(ch2.refresh("CA"))
        self.assertTrue(ch2.dates("CA"), "a failure keeps what was known")
        self.assertIn("Couldn't reach", ch2.state("CA")["error"])
        self.assertFalse(ch2.refresh("ca"), "codes are checked")
        with self.assertRaises(H.HolidayError):
            H._fetch("https://example.com/api")

    def test_parse_refuses_junk(self):
        for raw in (b"not json", b'{"a": 1}'):
            with self.assertRaises(H.HolidayError):
                H.parse_public(raw)


class ServerHolidays(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.app = App(self.d, start=False)
        s = settings()
        self.app.store.save_settings(s)
        self.app.store.save_secrets(**SECRETS)
        self.app.rebuild()

    def tearDown(self):
        self.app.store.close()
        shutil.rmtree(self.d, ignore_errors=True)

    def test_status_lists_every_holiday(self):
        st = self.app.holidays_status()
        self.assertEqual(len(st["holidays"]), len(H.HOLIDAYS))
        tg = next(h for h in st["holidays"] if h["key"] == "thanksgiving")
        self.assertTrue(tg["next"])
        self.assertEqual(st["groups"], H.GROUPS)

    def test_country_refresh(self):
        with self.assertRaises(ApiError):
            self.app.holidays_refresh("canada")
        self.app.country.fetch = lambda url: json.dumps([{"date": "2026-12-26", "name": "Boxing Day"}]).encode()
        s = copy.deepcopy(self.app.store.settings)
        s["holidays"]["country"] = {"code": "CA", "effects": ["warm_white"]}
        self.app.store.save_settings(s)
        self.app.holidays_refresh("CA")
        rule = next(r for r in self.app.cfg.schedule.rules if r.name == "Public holidays (CA)")
        self.assertIn(date(2026, 12, 26), rule.only_dates, "the new dates are used right away")
        self.app.country.fetch = lambda url: (_ for _ in ()).throw(H.HolidayError("down"))
        self.app._country_checked["CA"] -= 61          # Check now works once a minute (3.19.1)
        with self.assertRaises(ApiError) as cm:
            self.app.holidays_refresh("CA")
        self.assertEqual(cm.exception.code, 502)

    def test_editors_can_use_it(self):
        from eaveluxos.server import EDITOR_POSTS
        self.assertTrue({"/api/holidays/refresh", "/api/share", "/api/share/open"} <= EDITOR_POSTS)


if __name__ == "__main__":
    unittest.main()
