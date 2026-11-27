# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""4.25: game-time lights: the team's colors only while the game is on."""
import json
import subprocess
import sys
import unittest
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from eaveluxos import gameday
from eaveluxos.schedule import ConfigError, build_config
from tests.test_gameday import SECRETS, settings

HERE = Path(__file__).resolve().parent
NY = ZoneInfo("America/New_York")
SUN = date(2026, 12, 6)          # 1:00 PM game, sunset about 4:35 PM
MON = date(2026, 12, 14)         # 8:15 PM game


def team(**kw):
    return {"enabled": True, "teams": [{"league": "nfl", "team": "phi", "name": "Eagles", "effect": "eagles",
                                         "during": "game", **kw}]}


class Starts(unittest.TestCase):
    def test_1_start_times_from_espn(self):
        raw = json.dumps({"events": [
            {"date": "2026-12-06T18:00Z"}, {"date": "2026-12-15T01:15Z"},               # Monday night: Dec 14 local
            {"date": "2026-12-20T18:00Z", "competitions": [{"timeValid": False}]},      # time not set yet
            {"date": "2026-07-04T17:05Z"}, {"date": "2026-07-04T23:10Z"}]}).encode()      # a doubleheader
        st = gameday.parse_starts(raw, NY)
        self.assertEqual(st, {"2026-12-06": "13:00", "2026-12-14": "20:15", "2026-12-20": None, "2026-07-04": "13:05"})
        self.assertEqual(gameday.parse_dates(raw, NY), sorted(st))


class Rules(unittest.TestCase):
    DATES = {"nfl-phi": {SUN, MON}}
    STARTS = {"nfl-phi": {SUN: "13:00", MON: "20:15"}}

    def setUp(self):
        gameday.ENDED.clear()
        self.addCleanup(gameday.ENDED.clear)

    def build(self, gd):
        return build_config(settings(gameday=gd), SECRETS, gamedates=self.DATES, gamestarts=self.STARTS)

    def game_rules(self, c):
        return [r for r in c.schedule.rules if r.game_key]

    def test_1_from_before_the_start_to_after_the_longest_game(self):
        c = self.build(team())
        rs = self.game_rules(c)
        # the 1 PM game could still be on at sunset (4:35 PM): from then, until the final
        self.assertEqual([r.name for r in rs], ["Eagles game time (8:00 PM)", "Eagles game time (sunset)"])
        w = rs[0].window(MON, c.loc)
        self.assertEqual((w.start.strftime("%H:%M"), w.end.strftime("%m-%d %H:%M")), ("20:00", "12-15 00:30"))

    def test_day_games_from_sunset_or_too(self):
        c = self.build(team(daytime=True, before=30, after=0))
        names = sorted(r.name for r in self.game_rules(c))
        self.assertEqual(names, ["Eagles game time (12:30 PM)", "Eagles game time (7:45 PM)"])
        c = self.build(team())
        r = next(r for r in self.game_rules(c) if SUN in r.only_dates)
        self.assertTrue(16 <= r.window(SUN, c.loc).start.hour <= 17, "from sunset")
        gameday.ENDED[("nfl-phi", "2026-12-06")] = datetime(2026, 12, 6, 16, 5, tzinfo=NY).timestamp()
        self.assertIsNone(r.window(SUN, c.loc), "over before dark: no lights at all")
        early = {"nfl-phi": {SUN: "11:00", MON: "20:15"}}                    # over by 3:15 PM at the latest
        c = build_config(settings(gameday=team()), SECRETS, gamedates=self.DATES, gamestarts=early)
        self.assertFalse(any(SUN in r.only_dates for r in self.game_rules(c)))

    def test_ends_with_the_game(self):
        c = self.build(team(after=10))
        r = self.game_rules(c)[0]
        final = datetime(2026, 12, 14, 23, 32, tzinfo=NY)
        gameday.ENDED[("nfl-phi", "2026-12-14")] = final.timestamp()
        self.assertEqual(r.window(MON, c.loc).end.strftime("%H:%M"), "23:42")
        gameday.ENDED[("nfl-phi", "2026-12-14")] = datetime(2026, 12, 14, 19, 0, tzinfo=NY).timestamp()
        self.assertIsNone(r.window(MON, c.loc), "a game over before the lights would start")

    def test_no_time_yet_no_lights(self):
        c = build_config(settings(gameday=team()), SECRETS, gamedates=self.DATES, gamestarts={"nfl-phi": {MON: "20:15"}})
        self.assertFalse(any(SUN in r.only_dates for r in self.game_rules(c)))

    def test_all_evening_as_before(self):
        c = self.build(team(during="evening", on="sunset", off="23:00"))
        self.assertEqual([r.name for r in c.schedule.rules if "Eagles" in r.name], ["Eagles game day"])
        old = {"enabled": True, "teams": [{"league": "nfl", "team": "phi", "name": "Eagles", "effect": "eagles"}]}
        # 4.28: a team saved without a choice now gets game time (15 before, 15 after)
        self.assertEqual([r.name for r in self.build(old).schedule.rules if "Eagles" in r.name],
                         ["Eagles game time (8:00 PM)", "Eagles game time (sunset)"])

    def test_followed_on_the_scoreboard(self):
        c = self.build(team())
        self.assertIn("nfl-phi", c.watch)
        self.assertTrue(c.watch["nfl-phi"]["automation_only"])

    def test_bad_settings(self):
        for bad in ({"during": "night"}, {"before": 500}, {"after": -1}, {"after": True}):
            with self.assertRaises(ConfigError, msg=bad):
                self.build(team(**bad))


class Server(unittest.TestCase):
    def test_final_score_ends_them(self):
        from eaveluxos.server import App
        gameday.ENDED.clear()
        self.addCleanup(gameday.ENDED.clear)
        app = App.__new__(App)
        app.cfg, app.ctrl, app._auto_event = None, None, lambda ev: None
        app.on_game({"key": "nfl-phi", "team": "phi"}, "end", {"teams": {"phi": 24, "dal": 17}})
        (k, d), = gameday.ENDED
        self.assertEqual(k, "nfl-phi")
        self.assertRegex(d, r"\d{4}-\d{2}-\d{2}")

    def test_1_the_standalone_repro(self):
        script = str(HERE / "repro_min_lights_all_evening.py")
        self.assertIn("BUG:", subprocess.run([sys.executable, script], capture_output=True, text=True, timeout=60).stdout)
        self.assertIn("OK:", subprocess.run([sys.executable, script, "--fixed"], capture_output=True, text=True, timeout=60).stdout)


try:
    from playwright.sync_api import sync_playwright
except ImportError:            # pragma: no cover
    sync_playwright = None

from tests.test_local43 import ServerBase   # noqa: E402


@unittest.skipIf(sync_playwright is None, "Playwright isn't installed")
class Browser(ServerBase):
    def test_choose_during_the_game(self):
        import threading
        import time
        from unittest import mock
        from eaveluxos.server import make_server
        p = mock.patch.object(gameday, "_fetch", lambda u: b'{"events": []}')
        p.start()
        self.addCleanup(p.stop)
        srv = make_server(self.app, "127.0.0.1", 0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        try:
            pw = sync_playwright().start()
            br = pw.chromium.launch()
        except Exception as e:
            self.skipTest(f"Chromium can't start: {e}")
        self.addCleanup(pw.stop)
        self.addCleanup(br.close)
        pg = br.new_page(viewport={"width": 390, "height": 900})
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(f"http://localhost:{srv.server_address[1]}/#schedule")
        pg.wait_for_selector('[data-fold="game"]', timeout=20000)
        self.assertIn("Game-time lights", pg.inner_text('[data-fold="game"] .foldbar'))
        if "closed" in (pg.get_attribute('[data-fold="game"]', "class") or ""):
            pg.click('[data-fold="game"] .foldbar')
        pg.wait_for_selector("#gdpick", timeout=20000)
        first = pg.eval_on_selector("#gdpick", "s => [...s.options].map(o => o.value).find(v => v && v !== 'other')")
        pg.select_option("#gdpick", first)
        pg.click("[data-gdadd]")

        def team():
            ts = (self.app.store.settings.get("gameday") or {}).get("teams") or []
            return ts[0] if ts else None
        for _ in range(100):
            if team():
                break
            time.sleep(0.05)
        self.assertEqual((team()["during"], team()["before"], team()["after"]), ("game", 15, 15), "new teams: during the game")
        pg.wait_for_selector("[data-gdbefore='0']", timeout=20000)
        self.assertFalse(pg.query_selector("[data-gdon='0']"), "no On/Off times for game time")
        pg.select_option("[data-gdduring='0']", "evening")
        for _ in range(100):
            if team()["during"] == "evening":
                break
            time.sleep(0.05)
        pg.wait_for_selector("[data-gdon='0']", timeout=20000)
        self.assertLessEqual(pg.evaluate("document.documentElement.scrollWidth"), 390)
        self.assertEqual(errs, [])


if __name__ == "__main__":
    unittest.main()
