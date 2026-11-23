# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""4.21 sharing and energy: shows and automation templates shared by code
and in the community library, sports extras (lights for a win, a team's own
celebration length), controllers started together, and energy estimates."""
import copy
import threading
import time
import unittest
from datetime import date
from unittest import mock

from eaveluxos import community, energy, marketplace as M, sharecode as SC
from eaveluxos import lanlink as L
from eaveluxos.schedule import ConfigError, Effect
from tests.test_community import SET, opener_for
from tests.test_local43 import ServerBase

DEV = "TL-EDGE-01"
EFF = {"red": {"label": "Red", "colors": ["#FF0000"], "counts": [3]},
       "mine": {"label": "On my controller", "saved": "X"}}
AUTO = {"id": "x1", "name": "Doorbell", "when": {"type": "webhook", "name": "doorbell"},
        "if": [{"type": "dark", "from": "sunset", "to": "sunrise"}, {"type": "rule", "name": "Every night"}],
        "then": [{"type": "flash", "effect": "red", "seconds": 20, "zone": "Porch", "device": DEV},
                 {"type": "sound", "team": "nfl-phi"}]}


class Energy(unittest.TestCase):
    def test_colors(self):
        white = {"category": 1, "pixels": [{"count": 2, "color": 0xFFFFFF}]}
        red = {"category": 1, "pixels": [{"count": 2, "color": 0xFF0000}]}
        half = {"category": 1, "pixels": [{"count": 1, "color": 0xFFFFFF}, {"count": 1, "color": 0, "disable": True}]}
        self.assertAlmostEqual(energy.white_share(white), 1)
        self.assertAlmostEqual(energy.white_share(red), 1 / 3)
        self.assertAlmostEqual(energy.white_share(half), 0.5)
        self.assertEqual(energy.white_share({"category": 0, "mode": 4}), energy.BUILTIN_SHARE)

    def test_watts(self):
        e = Effect.from_config("w", {"colors": ["#FFFFFF"], "brightness": 255})
        self.assertAlmostEqual(energy.pattern_watts(e, 100, 0.3), 30 + energy.CONTROLLER_WATTS, places=1)
        self.assertAlmostEqual(energy.pattern_watts(e, 100, 0.3, brightness=51), 6 + energy.CONTROLLER_WATTS, places=1)
        self.assertEqual(energy.pattern_watts(e, 0), 0)


class Templates(unittest.TestCase):
    def test_nothing_of_the_home_travels(self):
        t, pats = M.make_template(AUTO, EFF)
        self.assertEqual(t["then"], [{"type": "flash", "effect": "@0", "seconds": 20, "zone": "Porch"}])
        self.assertEqual([c["type"] for c in t["if"]], ["dark"], "your rule's name stays home")
        self.assertEqual(pats[0]["colors"], ["#FF0000"])
        with self.assertRaises(M.TemplateError):
            M.make_template({**AUTO, "then": [{"type": "flash", "effect": "mine", "seconds": 5}]}, EFF)
        with self.assertRaises(M.TemplateError):
            M.make_template({**AUTO, "then": [{"type": "sound", "team": "nfl-phi"}]}, EFF)
        t2, _ = M.make_template({**AUTO, "when": {"type": "score", "team": "nfl-phi"}}, EFF)
        self.assertEqual(t2["when"]["team"], "any")

    def test_refused_from_someone_else(self):
        good = M.make_template(AUTO, EFF)[0]
        for bad in ({**good, "when": {"type": "launch"}}, {**good, "then": [{"type": "flash", "effect": "@3", "seconds": 5}]},
                    {**good, "then": [{"type": "flash", "color": "#FF0000", "seconds": 5, "device": "x"}]},
                    {**good, "if": [{"type": "rule", "name": "x"}]}, {**good, "when": {"type": "arrive", "person": "Chris"}},
                    {**good, "then": []}, "nope"):
            with self.assertRaises(M.TemplateError, msg=bad):
                M.check_template(bad, 1)

    def test_installed_turned_off_and_zones_checked(self):
        t, pats = M.make_template(AUTO, EFF)
        s, name = M.install(t, pats, {"effects": {"shared_doorbell_1": {}}, "automations": [{"name": "Doorbell (shared)"}]})
        a = s["automations"][-1]
        self.assertEqual(name, "Doorbell (shared 2)")
        self.assertFalse(a["enabled"])
        self.assertEqual(a["then"][0]["effect"], "shared_doorbell_1_2", "never replaces one of yours")
        self.assertNotIn("zone", a["then"][0], "no Porch zone here: the whole house")
        s2, _ = M.install(t, pats, {"map": {"zones": [{"name": "Porch", "start": 1, "end": 9}]}})
        self.assertEqual(s2["automations"][-1]["then"][0]["zone"], "Porch")


class Codes(unittest.TestCase):
    def test_round_trips(self):
        r = SC.decode(SC.encode_automation(AUTO, EFF)["code"])
        self.assertEqual(r["kind"], "automation")
        self.assertEqual(len(r["patterns"]), 1)
        show = {"name": "Eve", "fade": 3, "keyframes": [{"pattern": {"colors": ["#00FF00"]}, "minutes": 5}]}
        r = SC.decode("Look: " + SC.encode_show(show)["code"] + " enjoy")
        self.assertEqual((r["kind"], r["show"]["name"]), ("show", "Eve"))
        self.assertEqual(SC.decode(SC.encode([EFF["red"]]))["kind"], "patterns", "pattern codes are as before")

    def test_a_bad_show_or_template_is_refused(self):
        with self.assertRaises(SC.ShareError):
            SC.decode(SC.encode([], extra={"s": {"keyframes": []}}))
        with self.assertRaises(SC.ShareError):
            SC.decode(SC.encode([], extra={"a": [{"when": {"type": "nope"}}]}))
        with self.assertRaises(SC.ShareError):
            SC.decode(SC.encode([], extra={"a": "x"}))


class Community(unittest.TestCase):
    def test_kinds(self):
        code = SC.encode_automation(AUTO, EFF)["code"]
        idx = {"patterns": [{"id": "door", "kind": "automation", "name": "Doorbell"}, {"id": "cc", "name": "Candy"},
                            {"id": "fut", "kind": "hologram", "name": "Later"}]}
        lib = community.Library(opener=opener_for({"index.json": idx, "automations/door.json": {"code": code},
                                                   "shows/door.json": {"code": code}}))
        got = lib.index(SET)["patterns"]
        self.assertEqual([(p["id"], p["kind"]) for p in got], [("door", "automation"), ("cc", "pattern")])
        self.assertEqual(lib.item(SET, "door", "automation")["kind"], "automation")
        with self.assertRaises(community.CommunityError):
            lib.item(SET, "door", "show")              # a file that says it's something else
        with self.assertRaises(community.CommunityError):
            lib.item(SET, "../x", "show")


class Server(ServerBase):
    def settings(self, **kw):
        s = copy.deepcopy(self.app.store.settings)
        s.update(kw)
        self.app.save_settings(s)

    def test_share_and_install_an_automation(self):
        eff = next(k for k, e in self.app.store.settings["effects"].items() if "colors" in e)
        self.settings(automations=[{**AUTO, "then": [{"type": "flash", "effect": eff, "seconds": 20}]}])
        code = self.app.share_more("automation", {"id": "x1"})["code"]
        r = self.app.share_more("install", {"code": code})
        self.assertEqual(r["kind"], "automation")
        a = next(x for x in self.app.store.settings["automations"] if x["name"] == r["name"])
        self.assertFalse(a["enabled"])
        self.assertTrue(any(x["id"] == a["id"] for x in self.app.ctrl.cfg.automations), "it's a valid automation here")

    def test_energy(self):
        self.settings(usage={"bulbs": 200, "watts_per_bulb": 0.3, "rate": 0.2})
        r = self.app.energy_estimate()
        self.assertEqual(r["bulbs"], 200)
        self.assertEqual(r["month"]["days"], 30)
        self.assertGreater(r["month"]["kwh"], 0)
        self.assertAlmostEqual(r["month"]["cost"], round(r["month"]["kwh"] * 0.2, 2), places=1)
        self.assertTrue(r["hungriest"])

    def test_wins_and_a_teams_own_length(self):
        effs = list(self.app.store.settings["effects"])
        gd = {"enabled": False, "celebrate_enabled": False, "celebrate_seconds": 15,
              "teams": [{"league": "nfl", "team": "phi", "name": "Eagles", "effect": effs[0], "celebrate": True, "seconds": 45},
                        {"league": "nhl", "team": "phi", "name": "Flyers", "effect": effs[0], "win_effect": effs[1], "win_minutes": 60}]}
        self.settings(gameday=gd)
        cel = self.app.ctrl.cfg.celebrate
        self.assertNotIn("nfl-phi", cel, "score celebrations are off")
        self.assertEqual(cel["nhl-phi"]["win_effect"], effs[1])
        self.assertTrue(cel["nhl-phi"]["automation_only"], "no score flashes, only the win")
        gd["celebrate_enabled"] = True
        self.settings(gameday=gd)
        self.assertEqual(self.app.ctrl.cfg.celebrate["nfl-phi"]["seconds"], 45)
        bad = copy.deepcopy(gd)
        bad["teams"][1]["win_minutes"] = 2
        with self.assertRaises(Exception):
            self.settings(gameday=bad)

    def test_win_lights(self):
        effs = list(self.app.store.settings["effects"])
        c = self.app.ctrl
        team = {"key": "nhl-phi", "team": "phi", "name": "Flyers", "win_effect": effs[1], "win_minutes": 60, "only_when_on": True}
        game = {"teams": {"phi": 4, "nyr": 2}}
        with mock.patch.object(c, "_target", return_value=mock.Mock(on=False, reason="schedule", hands_off=False)):
            self.app.on_game(team, "end", game)
        self.assertIsNone(c.override, "the lights are off: no win lights")
        with mock.patch.object(c, "_target", return_value=mock.Mock(on=True, reason="schedule", hands_off=False)), \
                mock.patch.object(c, "tick"):
            self.app.on_game(team, "end", game)
        self.assertEqual(c.override["effect"], effs[1])
        self.assertAlmostEqual(c.override["expires"] - time.time(), 3600, delta=30)
        c.override = None
        with mock.patch.object(c, "_target", return_value=mock.Mock(on=True, reason="schedule", hands_off=False)):
            self.app.on_game(team, "end", {"teams": {"phi": 1, "nyr": 2}})
        self.assertIsNone(c.override, "a loss: nothing")

    def test_review_1_the_winning_goals_flash_doesnt_skip_the_win(self):
        import subprocess
        import sys
        from pathlib import Path
        script = str(Path(__file__).with_name("repro_min_win_skipped.py"))
        self.assertIn("BUG:", subprocess.run([sys.executable, script], capture_output=True, text=True, timeout=60).stdout)
        self.assertIn("OK:", subprocess.run([sys.executable, script, "--fixed"], capture_output=True, text=True, timeout=60).stdout)
        effs = list(self.app.store.settings["effects"])
        c = self.app.ctrl
        team = {"key": "nhl-phi", "team": "phi", "name": "Flyers", "win_effect": effs[1], "win_minutes": 30, "only_when_on": True}
        for kind, wins in (("score", True), ("security", False)):
            c.override = None
            c.flash = {"kind": kind}
            with mock.patch.object(c, "_target", return_value=mock.Mock(on=True, reason="flash", hands_off=False)), \
                    mock.patch.object(c, "tick"):
                self.app.on_game(team, "end", {"teams": {"phi": 3, "nyr": 2}})
            self.assertEqual(bool(c.override), wins, kind)
        c.flash = None

    def test_sync(self):
        c = self.app.ctrl
        with self.assertRaises(ValueError):
            c.sync_now()                              # no home network commands
        self.app.local_commands(True)
        c = self.app.ctrl
        c.devices = [{"deviceId": DEV, "name": "A"}, {"deviceId": "B", "name": "B"}]
        p = {"category": 1, "mode": 1, "speed": 100, "brightness": 200, "pixels": [{"index": 0, "count": 3, "color": 0xFF0000, "disable": False}]}
        c.sent_effect = {DEV: dict(p), "B": dict(p)}
        got = []
        with mock.patch.object(c.lan, "preview_many", lambda items: got.extend(d for d, _ in items) or [d for d, _ in items]):
            r = c.sync_now()
        self.assertEqual((r["started"], sorted(got)), (2, ["B", DEV]))
        # for real, over the (fake) home network: both sent back to back
        n = len(self.ctl.frames(L.CMD_REQUEST))
        self.assertEqual(c.lan.preview_many([(DEV, p)]), [DEV])
        self.assertEqual(len(self.ctl.frames(L.CMD_REQUEST)), n + 1)


try:
    from playwright.sync_api import sync_playwright
except ImportError:            # pragma: no cover
    sync_playwright = None


@unittest.skipIf(sync_playwright is None, "Playwright isn't installed")
class Browser(ServerBase):
    def test_share_an_automation_and_add_it_back(self):
        from eaveluxos.server import make_server
        eff = next(k for k, e in self.app.store.settings["effects"].items() if "colors" in e)
        s = copy.deepcopy(self.app.store.settings)
        s["automations"] = [{**AUTO, "then": [{"type": "flash", "effect": eff, "seconds": 20}]}]
        s["usage"] = {"bulbs": 150}
        self.app.save_settings(s)
        srv = make_server(self.app, "127.0.0.1", 0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        base = f"http://localhost:{srv.server_address[1]}/"
        try:
            pw = sync_playwright().start()
            br = pw.chromium.launch()
        except Exception as e:
            self.skipTest(f"Chromium can't start: {e}")
        self.addCleanup(pw.stop)
        self.addCleanup(br.close)
        errors = []

        def until(cond, what):
            for _ in range(200):
                if cond():
                    return
                time.sleep(0.05)
            self.fail(f"never: {what}")

        def unfold(pg, key):
            pg.wait_for_selector(f'[data-fold="{key}"]')
            if "closed" in (pg.get_attribute(f'[data-fold="{key}"]', "class") or ""):
                pg.click(f'[data-fold="{key}"] .foldbar')
        pg = br.new_page(viewport={"width": 1300, "height": 900})
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(base + "#alerts")
        unfold(pg, "autos")
        pg.click('[data-autoshare="0"]')
        pg.wait_for_selector("#dlg #sharecode")
        code = pg.input_value("#dlg #sharecode")
        self.assertTrue(code.startswith("ELX1:"))
        pg.keyboard.press("Escape")
        pg.click("[data-autoopen]")
        pg.wait_for_selector("#dlg textarea[name=code]")
        pg.fill("#dlg textarea[name=code]", code)
        pg.locator("#dlg .primary").last.click()
        pg.wait_for_selector("text=An automation: “Doorbell”")
        pg.locator("#dlg .primary").last.click()
        until(lambda: any(a["name"] == "Doorbell (shared)" for a in self.app.store.settings.get("automations", [])), "added")
        # energy in Lights usage
        pg.wait_for_selector("text=turned off: check it")     # it has gone on to Alerts
        pg.goto(base + "#app")
        pg.reload()
        unfold(pg, "usage")
        pg.wait_for_selector("#energybox h3")
        self.assertIn("next 30 nights", pg.inner_text("#energybox"))
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
