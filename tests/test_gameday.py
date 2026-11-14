# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Game-day lights (3.15)."""
import copy
import json
import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo

from eaveluxos import gameday
from eaveluxos.gameday import GameDayError, GameDays, parse_dates, schedule_url
from eaveluxos.schedule import ConfigError, build_config
from eaveluxos.store import DEFAULT_SETTINGS

NY = ZoneInfo("America/New_York")
SECRETS = {"client_id": "x", "client_secret": "y"}

# The shape of ESPN's team schedule answer (trimmed).
ESPN = {"team": {"abbreviation": "PHI"}, "events": [
    {"id": "1", "date": "2026-12-06T18:00Z", "name": "Chicago Bears at Philadelphia Eagles",
     "competitions": [{"date": "2026-12-06T18:00Z", "competitors": [{"homeAway": "home", "team": {"abbreviation": "PHI"}}]}]},
    {"id": "2", "date": "2026-12-15T01:15Z", "name": "Philadelphia Eagles at Dallas Cowboys"},   # Mon night: Dec 14 local
    {"id": "3", "competitions": [{"date": "2026-12-20T21:25:00Z"}]},                        # date only inside competitions
    {"id": "4", "date": "TBD"}, "junk", {"id": "5"},
]}


def settings(**kw):
    s = copy.deepcopy(DEFAULT_SETTINGS)
    s["location"].update(latitude=39.95, longitude=-75.16)
    s["effects"]["eagles"] = {"label": "Eagles colors", "colors": ["#004C54", "#FFFFFF"], "counts": [4, 4], "custom_mode": 0}
    s.update(kw)
    return s


EAGLES = {"enabled": True, "teams": [{"league": "nfl", "team": "phi", "name": "Eagles", "effect": "eagles", "on": "sunset", "off": "23:00"}]}


class Parsing(unittest.TestCase):
    def test_local_game_dates(self):
        self.assertEqual(parse_dates(json.dumps(ESPN).encode(), NY), ["2026-12-06", "2026-12-14", "2026-12-20"])

    def test_unreadable_answers(self):
        for bad in (b"<html>", b"[]", b'{"events": "none"}'):
            with self.assertRaises(GameDayError):
                parse_dates(bad, NY)
        self.assertEqual(parse_dates(b'{"events": []}', NY), [])

    def test_urls_only_to_the_schedule_service(self):
        self.assertEqual(schedule_url("nfl", "phi"), "https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/phi/schedule")
        self.assertTrue(schedule_url("mlb", "phi", 3).endswith("?seasontype=3"))
        with self.assertRaises(GameDayError):
            gameday._fetch("https://evil.example/x")
        for bad in ({"league": "xfl", "team": "phi"}, {"league": "nfl", "team": "../x"}, "phi"):
            with self.assertRaises(GameDayError):
                gameday.check_team(bad)


class Refresh(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.answer = json.dumps(ESPN).encode()
        self.urls = []

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def fetch(self, url):
        self.urls.append(url)
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer

    def test_fetch_keep_and_survive_failures(self):
        g = GameDays(self.dir, fetch=self.fetch)
        teams = [gameday.check_team({"league": "nfl", "team": "phi", "name": "Eagles"})]
        self.assertTrue(g.refresh(teams, NY))
        self.assertEqual(len(self.urls), 2)                                  # regular season and playoffs
        self.assertEqual(g.dates()["nfl-phi"], {date(2026, 12, 6), date(2026, 12, 14), date(2026, 12, 20)})
        self.answer = GameDayError("Couldn't reach the schedule service: offline")
        self.assertFalse(g.refresh(teams, NY))
        self.assertEqual(len(g.dates()["nfl-phi"]), 3)                        # last dates kept
        s = g.summary(teams, date(2026, 12, 10))[0]
        self.assertEqual(s["next"], ["2026-12-14", "2026-12-20"])
        self.assertIn("offline", s["error"])
        self.assertEqual(len(GameDays(self.dir).dates()["nfl-phi"]), 3)       # kept across restarts

    def test_damaged_file(self):
        (self.dir / "gamedays.json").write_text('{"nfl-phi": {"dates": ["2026-12-06", "soon", 5]}, "x": 3}', encoding="utf-8")
        self.assertEqual(GameDays(self.dir).dates(), {"nfl-phi": {date(2026, 12, 6)}})


class Rules(unittest.TestCase):
    DATES = {"nfl-phi": {date(2026, 12, 6), date(2026, 12, 14)}}

    def test_game_nights_win_even_over_christmas(self):
        c = build_config(settings(gameday=EAGLES), SECRETS, gamedates=self.DATES)
        self.assertEqual(c.schedule.day_plan(date(2026, 12, 6)).rule.name, "Eagles game day")
        self.assertEqual(c.schedule.day_plan(date(2026, 12, 7)).rule.name, "Christmas season")
        self.assertEqual(c.schedule.day_plan(date(2027, 2, 14)).rule.name, "Every night")

    def test_off_or_no_dates_changes_nothing(self):
        for gd, dates in ((EAGLES, None), ({**EAGLES, "enabled": False}, self.DATES)):
            c = build_config(settings(gameday=gd), SECRETS, gamedates=dates)
            self.assertEqual(c.schedule.day_plan(date(2026, 12, 6)).rule.name, "Christmas season")

    def test_names_never_clash(self):
        """Review #4 (3.15.1): NFL "phi" and NBA "phi" both added as "PHI", or
        a rule of your own called "Eagles game day", made saving fail with
        "Two schedule rules have the same name"."""
        s = settings(gameday={"enabled": True, "teams": [
            {"league": "nfl", "team": "phi", "name": "PHI", "effect": "eagles"},
            {"league": "nba", "team": "phi", "name": "PHI", "effect": "eagles"},
            {"league": "nhl", "team": "phi", "name": "Eagles", "effect": "eagles"}]})
        s["rules"].append({"name": "Eagles game day", "on": "18:00", "off": "19:00", "effect": "eagles"})
        c = build_config(s, SECRETS, gamedates={"nfl-phi": {date(2026, 12, 6)}})
        names = [r.name for r in c.schedule.rules]
        self.assertEqual(len(names), len(set(names)))
        self.assertIn("PHI game day", names)
        self.assertIn("PHI (NBA) game day", names)
        self.assertIn("Eagles (NHL) game day", names)

    def test_bad_settings(self):
        team = EAGLES["teams"][0]
        for bad in ({"enabled": True, "teams": [{**team, "effect": "nope"}]}, {"enabled": True, "teams": [{**team, "league": "xfl"}]},
                    {"enabled": True, "teams": [team] * 7}, {"enabled": True, "teams": "eagles"}, "on"):
            with self.assertRaises(ConfigError, msg=bad):
                build_config(settings(gameday=bad), SECRETS)

    def test_screen(self):
        js = (Path(__file__).resolve().parent.parent / "eaveluxos" / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn("async function gamePanel", js)
        self.assertIn("game-day lights for ${t.name}", js)              # its pattern can't be deleted while used


if __name__ == "__main__":
    unittest.main()
