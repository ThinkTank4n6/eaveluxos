# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""4.28: game time is the default (15 minutes before to 15 after), and games
of followed teams show under Schedule › Coming up."""
import threading
import unittest
from datetime import date, timedelta
from unittest import mock

from eaveluxos import gameday
from eaveluxos.schedule import build_config
from tests.test_gameday import SECRETS, settings
from tests.test_gametime425 import MON, SUN

try:
    from playwright.sync_api import sync_playwright
except ImportError:            # pragma: no cover
    sync_playwright = None
from tests.test_local43 import ServerBase   # noqa: E402


def gd(enabled=True, celebrate=True, **kw):
    return {"enabled": enabled, "celebrate_enabled": celebrate,
            "teams": [{"league": "nfl", "team": "phi", "name": "Eagles", "effect": "eagles", "celebrate": True, **kw}]}


class Default(unittest.TestCase):
    DATES = {"nfl-phi": {SUN, MON}}
    STARTS = {"nfl-phi": {SUN: "13:00", MON: "20:15"}}

    def setUp(self):
        gameday.ENDED.clear()
        self.addCleanup(gameday.ENDED.clear)

    def build(self, g):
        return build_config(settings(gameday=g), SECRETS, gamedates=self.DATES, gamestarts=self.STARTS)

    def test_a_team_without_a_choice_gets_game_time(self):
        c = self.build(gd())                           # saved before 4.25: no "during"
        rs = [r for r in c.schedule.rules if r.game_key]
        self.assertEqual([r.name for r in rs], ["Eagles game time (8:00 PM)", "Eagles game time (sunset)"])
        w = rs[0].window(MON, c.loc)
        self.assertEqual(w.start.strftime("%H:%M"), "20:00")     # 15 minutes before 8:15
        self.assertIn("nfl-phi", c.watch)                        # the final score ends them

    def test_all_evening_only_when_chosen(self):
        c = self.build(gd(during="evening", on="sunset", off="23:00"))
        rs = [r for r in c.schedule.rules if "game day" in r.name]
        self.assertEqual(len(rs), 1)
        self.assertFalse([r for r in c.schedule.rules if r.game_key])


class ComingUp(ServerBase):
    def setUp(self):
        super().setUp()
        today = self.app.cfg.loc.now().date()
        self.d1, self.d2 = today + timedelta(days=1), today + timedelta(days=2)
        self.app.gameday.cache = {"nfl-phi": {"dates": [self.d1.isoformat(), self.d2.isoformat()],
                                              "starts": {self.d1.isoformat(): "20:15", self.d2.isoformat(): None}}}

    def put(self, g):
        s = dict(self.app.store.settings)
        s["effects"] = {**s.get("effects", {}), "eagles": {"label": "Eagles", "colors": ["#004C54", "#FFFFFF"]}}
        s["gameday"] = g
        self.app.store.save_settings(s)
        self.app.rebuild()

    def days(self):
        return {d["date"]: d for d in self.app.upcoming(5)}

    def test_celebrations_only(self):
        self.put(gd(enabled=False))
        got = self.days()
        self.assertEqual(got[self.d1.isoformat()]["games"],
                         [{"team": "Eagles", "league": "NFL", "sport": "football", "start": "20:15", "lights": False, "celebrate": True}])
        self.assertEqual(got[self.d2.isoformat()]["games"][0]["start"], None)
        self.assertFalse([w for w in got[self.d1.isoformat()]["windows"] if "Eagles" in w["rule"]])

    def test_game_time_lights_show_both(self):
        self.put(gd())
        day = self.days()[self.d1.isoformat()]
        self.assertTrue(day["games"][0]["lights"])
        self.assertIn("Eagles game time (8:00 PM)", [w["rule"] for w in day["windows"]])

    def test_neither_shows_nothing(self):
        self.put(gd(enabled=False, celebrate=False))
        self.assertFalse(any(d["games"] for d in self.days().values()))

    @unittest.skipIf(sync_playwright is None, "Playwright isn't installed")
    def test_calendar_and_list_show_the_game(self):
        from eaveluxos.server import make_server
        self.put(gd(enabled=False))
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
        pg = br.new_page(viewport={"width": 1100, "height": 900})
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(f"http://localhost:{srv.server_address[1]}/#schedule")
        pg.wait_for_selector('[data-fold="upcoming"]', timeout=20000)
        if "closed" in (pg.get_attribute('[data-fold="upcoming"]', "class") or ""):
            pg.click('[data-fold="upcoming"] .foldbar')
        if self.d1.month != self.app.cfg.loc.now().month:
            pg.click("[data-calm='1']")
        pg.wait_for_selector(".calday .gamechip", timeout=20000)
        self.assertIn("8:15", pg.inner_text(".calday .gamechip"))
        pg.click("[data-upv=list]")
        pg.wait_for_selector(".win.game", timeout=20000)
        txt = pg.inner_text(".win.game")
        self.assertIn("Eagles game", txt)
        self.assertIn("celebrate scores", txt)
        self.assertNotIn("game-time lights", txt)
        self.assertEqual(errs, [])


if __name__ == "__main__":
    unittest.main()


@unittest.skipIf(sync_playwright is None, "Playwright isn't installed")
class FirstTeam(ServerBase):
    def test_adding_a_first_team_turns_on_game_time_lights_only(self):
        from eaveluxos.server import make_server
        for p in (mock.patch.object(gameday, "_fetch", lambda u: b'{"events": []}'),
                  mock.patch.object(gameday.GameDays, "_refresh", lambda *a, **k: False)):
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
        pg = br.new_page(viewport={"width": 1100, "height": 900})
        pg.goto(f"http://localhost:{srv.server_address[1]}/#schedule")
        pg.wait_for_selector('[data-fold="game"]', timeout=20000)
        if "closed" in (pg.get_attribute('[data-fold="game"]', "class") or ""):
            pg.click('[data-fold="game"] .foldbar')
        pg.select_option("#gdpick", "nfl-phi")
        pg.click("[data-gdadd]")
        pg.wait_for_selector("[data-gdeff='0']", timeout=20000)
        g = self.app.store.settings["gameday"]
        self.assertTrue(g["enabled"])
        self.assertIs(g["celebrate_enabled"], False)
        self.assertFalse(pg.is_checked("#gdparty"))
