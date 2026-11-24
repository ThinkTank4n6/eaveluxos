# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""4.24: game-day lights and score celebrations for the WNBA and college
football, basketball and hockey (men's and women's)."""
import json
import subprocess
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from eaveluxos import gameday, scores
from eaveluxos.schedule import CELEBRATE_POINTS

HERE = Path(__file__).resolve().parent


def board(*games):
    evs = []
    for gid, st, (ia, aa, a), (ib, ab, b) in games:
        comps = [{"homeAway": "home", "score": str(a), "team": {"id": ia, "abbreviation": aa}},
                 {"homeAway": "away", "score": str(b), "team": {"id": ib, "abbreviation": ab}}]
        evs.append({"id": gid, "date": "2026-11-28T17:00Z", "status": {"type": {"state": st, "shortDetail": ""}},
                    "competitions": [{"competitors": comps}]})
    return json.dumps({"events": evs}).encode()


class Leagues(unittest.TestCase):
    def test_1_the_new_leagues(self):
        for k, path in (("wnba", "basketball/wnba"), ("cfb", "football/college-football"),
                        ("mcbb", "basketball/mens-college-basketball"), ("wcbb", "basketball/womens-college-basketball"),
                        ("mchk", "hockey/mens-college-hockey"), ("wchk", "hockey/womens-college-hockey")):
            self.assertEqual(gameday.LEAGUES[k][0], path)
        self.assertEqual(set(CELEBRATE_POINTS), set(gameday.LEAGUES), "every league has a default")

    def test_codes_and_numbers(self):
        self.assertEqual(gameday.check_team({"league": "cfb", "team": "213"})["team"], "213")
        self.assertEqual(gameday.check_team({"league": "wnba", "team": "LV"})["team"], "lv")
        for bad in ("m-oh", "ta&m", "12345678", "x"):
            with self.assertRaises(gameday.GameDayError):
                gameday.check_team({"league": "cfb", "team": bad})

    def test_board_urls(self):
        self.assertEqual(scores.scoreboard_url("cfb", date(2026, 11, 28), "groups=80&limit=500"),
                         gameday.HOST + "football/college-football/scoreboard?dates=20261128&groups=80&limit=500")
        self.assertEqual(scores.scoreboard_url("nfl"), gameday.HOST + "football/nfl/scoreboard")


class Picker(unittest.TestCase):
    RAW = json.dumps({"sports": [{"leagues": [{"teams": [
        {"team": {"id": "213", "abbreviation": "PSU", "displayName": "Penn State Nittany Lions", "color": "061440", "alternateColor": "ffffff"}},
        {"team": {"id": "193", "abbreviation": "M-OH", "displayName": "Miami (OH) RedHawks", "color": "zz"}}]}]}]}).encode()

    def test_college_by_number_with_colors(self):
        ts = gameday.parse_teams(self.RAW, "cfb")
        self.assertEqual([t["team"] for t in ts], ["193", "213"], "by name; saved by number")
        self.assertEqual(ts[1]["colors"], ["#061440", "#FFFFFF"])
        self.assertEqual(ts[0]["colors"], ["#FFFFFF"], "no usable color: white")

    def test_pro_by_code(self):
        raw = json.dumps({"sports": [{"leagues": [{"teams": [{"team": {"id": "17", "abbreviation": "LV", "displayName": "Las Vegas Aces", "color": "000000"}}]}]}]}).encode()
        self.assertEqual(gameday.parse_teams(raw, "wnba")[0]["team"], "lv")

    def test_server_caches(self):
        from eaveluxos.server import App, ApiError
        app = App.__new__(App)
        calls = []
        with mock.patch.object(gameday, "_fetch", lambda u: calls.append(u) or self.RAW):
            r1 = app.gameday_teams("cfb")
            app.gameday_teams("cfb")
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(r1["teams"]), 2)
        with self.assertRaises(ApiError):
            app.gameday_teams("xfl")


class Celebrate(unittest.TestCase):
    def test_1_a_college_team_by_number_scores(self):
        boards = {"groups=80&limit=500": board(("401", "in", ("213", "PSU", 14), ("194", "OSU", 7)))}
        parties = []
        w = scores.ScoreWatch(lambda t, pts, g: parties.append(pts), fetch=lambda u: boards.get(u.split("?")[1], b'{"events": []}'),
                              now=lambda: 1000.0)
        team = {"cfb-213": {"league": "cfb", "team": "213", "name": "Penn State", "min_points": 3}}
        w.check(team, {"cfb-213": {date(2026, 11, 28)}}, date(2026, 11, 28), force=True, hour=13)
        self.assertEqual(w.summary()["cfb-213"]["state"], "in")
        boards["groups=80&limit=500"] = board(("401", "in", ("213", "PSU", 21), ("194", "OSU", 7)))
        w.now = lambda: 1100.0
        w.check(team, {"cfb-213": {date(2026, 11, 28)}}, date(2026, 11, 28), force=True, hour=13)
        self.assertEqual(parties, [7], "touchdown")

    def test_fcs_team_on_the_second_board(self):
        urls = []
        boards = {"groups=80&limit=500": board(("401", "in", ("213", "PSU", 0), ("194", "OSU", 0))),
                  "groups=81&limit=500": board(("402", "in", ("2655", "VILL", 3), ("2771", "DEL", 0)))}
        w = scores.ScoreWatch(lambda *a: None, fetch=lambda u: urls.append(u) or boards[u.split("?")[1]], now=lambda: 0.0)
        w.check({"cfb-2655": {"league": "cfb", "team": "2655", "name": "Villanova", "min_points": 3}},
                {"cfb-2655": {date(2026, 11, 28)}}, date(2026, 11, 28), force=True, hour=13)
        self.assertEqual(w.summary()["cfb-2655"]["score"], 3)
        self.assertEqual(len(urls), 2)
        urls.clear()
        w.check({"cfb-213": {"league": "cfb", "team": "213", "name": "Penn State", "min_points": 3}},
                {"cfb-213": {date(2026, 11, 28)}}, date(2026, 11, 28), force=True, hour=13)
        self.assertEqual(len(urls), 1, "found on the first board: the second isn't asked for")

    def test_1_the_standalone_repro(self):
        script = str(HERE / "repro_min_college_by_number.py")
        self.assertIn("BUG:", subprocess.run([sys.executable, script], capture_output=True, text=True, timeout=60).stdout)
        self.assertIn("OK:", subprocess.run([sys.executable, script, "--fixed"], capture_output=True, text=True, timeout=60).stdout)


try:
    from playwright.sync_api import sync_playwright
except ImportError:            # pragma: no cover
    sync_playwright = None

from tests.test_local43 import ServerBase   # noqa: E402


@unittest.skipIf(sync_playwright is None, "Playwright isn't installed")
class Browser(ServerBase):
    def test_pick_a_college_team(self):
        import threading
        import time
        from eaveluxos.server import make_server
        p = mock.patch.object(gameday, "_fetch", lambda u: Picker.RAW if "/teams?" in u else b'{"events": []}')
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
        if "closed" in (pg.get_attribute('[data-fold="game"]', "class") or ""):
            pg.click('[data-fold="game"] .foldbar')
        pg.wait_for_selector("#gdpick", timeout=20000)
        pg.select_option("#gdpick", "other")
        pg.select_option("#gdleague", "cfb")
        for _ in range(100):
            if pg.eval_on_selector_all("#gdteams option", "o => o.length") == 2:
                break
            time.sleep(0.05)
        pg.fill("#gdteam", "Penn State Nittany Lions (PSU)")
        pg.click("[data-gdadd]")
        for _ in range(100):
            teams = (self.app.store.settings.get("gameday") or {}).get("teams") or []
            if teams:
                break
            time.sleep(0.05)
        self.assertEqual([(t["league"], t["team"], t["name"]) for t in teams], [("cfb", "213", "Penn State Nittany Lions")])
        eff = self.app.store.settings["effects"][teams[0]["effect"]]
        self.assertEqual(eff["colors"], ["#061440", "#FFFFFF"])
        self.assertLessEqual(pg.evaluate("document.documentElement.scrollWidth"), 390)
        self.assertEqual(errs, [])


if __name__ == "__main__":
    unittest.main()
