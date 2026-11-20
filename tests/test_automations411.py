# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""4.11: automations. When something happens, if the conditions hold, then
the lights do what they're told, by priority, with a cooldown, and not over
a choice made by hand unless allowed."""
import copy
import json
import os
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from eaveluxos import automations as AU
from eaveluxos.schedule import ConfigError, build_config
from eaveluxos.store import DEFAULT_SETTINGS
from tests.test_each48 import DECK, FRONT, Base

FLY = "nhl-phi"


def auto(**kw):
    a = {"id": kw.pop("id", "a1"), "name": kw.pop("name", "Flyers goal"), "when": {"type": "score", "team": FLY},
         "if": [{"type": "dark"}], "then": [{"type": "flash", "color": "#FF6600", "seconds": 20}]}
    a.update(kw)
    return a


def settings(autos, rules=None):
    s = copy.deepcopy(DEFAULT_SETTINGS)
    s["location"].update(latitude=39.95, longitude=-75.17)
    s["gameday"] = {"enabled": False, "teams": [{"league": "nhl", "team": "phi", "name": "Flyers"},
                                                {"league": "nfl", "team": "phi", "name": "Eagles"}]}
    s["automations"] = autos
    if rules is not None:
        s["rules"] = rules
    return s


class Parse(unittest.TestCase):
    def cfg(self, autos):
        return build_config(settings(autos), {"client_id": "x", "client_secret": "y"})

    def test_the_example(self):
        c = self.cfg([auto()])
        a = c.automations[0]
        self.assertEqual((a["priority"], a["cooldown"], a["beats_manual"]), (100, 30, False))
        self.assertEqual(AU.describe(a, lambda k, v: {"nhl-phi": "Flyers"}.get(v, v)),
                         "When Flyers scores, if it's dark, then flash #FF6600 for 20 s.")
        self.assertIn(FLY, c.watch, "the scoreboard follows the Flyers for it")
        self.assertTrue(c.watch[FLY]["automation_only"])

    def test_refused(self):
        bad = [auto(name=""), auto(when={"type": "score", "team": "nba-lal"}),
               auto(**{"if": [{"type": "home"}], "when": {"type": "time", "at": "sunset"}}),
               auto(then=[]), auto(then=[{"type": "flash", "seconds": 20}]), auto(then=[{"type": "flash", "color": "#FF6600", "seconds": 2}]),
               auto(then=[{"type": "show", "effect": "nope"}]), auto(**{"if": [{"type": "days", "days": []}]}),
               auto(**{"if": [{"type": "dates", "from": "13-01", "to": "12-31"}]}),
               auto(when={"type": "webhook", "name": "door<bell>"}), auto(when={"type": "time", "at": "teatime"}),
               auto(priority=5000), [auto(), auto()][0] | {"then": [{"type": "sound", "team": "nfl-dal"}]}]
        for a in bad:
            with self.subTest(a=a), self.assertRaises(ConfigError):
                self.cfg([a])
        with self.assertRaises(ConfigError):
            self.cfg([auto(), auto()])          # the same id twice


class FakeApp:
    def __init__(self, ctrl):
        self.ctrl = ctrl
        self.did = []

    def __getattr__(self, name):
        if name.startswith("auto_"):
            return lambda x, a, ev: self.did.append((a["name"], x["type"]))
        raise AttributeError(name)


class EngineBase(Base):
    AUTOS = [auto()]
    RULES = [{"name": "Night", "on": "18:00", "off": "23:00", "effect": "warm_white"}]

    def setUp(self):
        super().setUp()
        s = settings(copy.deepcopy(self.AUTOS), self.RULES)
        self.c.cfg = self.cfg = build_config(s, {"client_id": "x", "client_secret": "y"})
        self.app = FakeApp(self.c)
        self.clock_s = [1000.0]
        self.eng = AU.Engine(self.app, now=lambda: self.clock_s[0])

    def score(self, **kw):
        return self.eng.event({"type": "score", "team": FLY, "abbr": "phi", "game": kw.get("game"), "points": 1})


class Conditions(EngineBase):
    def test_runs_after_dark_not_at_noon(self):
        self.at(12)
        out = self.score()
        self.assertIn("skipped", out[0])
        self.assertEqual(self.app.did, [])
        self.at(20)
        self.clock_s[0] += 100
        self.assertIn("ran", self.score()[0])
        self.assertEqual(self.app.did, [("Flyers goal", "flash")])

    def test_cooldown(self):
        self.at(20)
        self.score()
        self.clock_s[0] += 10
        self.assertIn("cooldown", self.score()[0])
        self.clock_s[0] += 30
        self.assertIn("ran", self.score()[0])

    def test_check_it_now(self):
        self.at(12)
        self.assertEqual(self.eng.check(self.cfg.automations[0]), [("it's dark", False)])
        self.at(21)
        self.assertEqual(self.eng.check(self.cfg.automations[0]), [("it's dark", True)])

    def test_try_it_now_ignores_conditions(self):
        self.at(12)
        self.assertIn("tried", self.eng.try_now(self.cfg.automations[0]))
        self.assertEqual(len(self.app.did), 1)


class Priorities(EngineBase):
    AUTOS = [auto(id="lo", name="Low", **{"if": []}), auto(id="hi", name="High", priority=200, **{"if": []}),
             auto(id="deck", name="Deck only", priority=50, **{"if": []},
                  then=[{"type": "flash", "color": "#00FF00", "seconds": 10, "device": DECK}])]

    def test_higher_first_and_the_same_lights_once(self):
        self.at(20)
        out = self.score()
        self.assertIn("High", out[0])
        self.assertIn("ran", out[0])
        self.assertTrue(all("skipped" in x for x in out[1:]), out)
        self.assertEqual(self.app.did, [("High", "flash")])

    def test_a_lower_one_waits_for_a_higher_flash(self):
        self.at(20)
        self.score()
        self.clock_s[0] += 5
        out = self.eng.event({"type": "score", "team": FLY, "abbr": "phi", "game": None})
        self.assertTrue(all("skipped" in x for x in out), out)


class Manual(EngineBase):
    AUTOS = [auto(**{"if": []}), auto(id="b", name="Beats", beats_manual=True, priority=40, when={"type": "webhook", "name": "doorbell"},
                                       **{"if": []})]

    def test_not_over_a_choice_by_hand(self):
        self.at(20)
        self.c.manual(False)
        self.assertIn("set by hand", self.score()[0])
        self.assertIn("ran", self.eng.event({"type": "webhook", "name": "doorbell"})[0])


class Events(EngineBase):
    AUTOS = [auto(id="t", name="Sunset", when={"type": "time", "at": "sunset"}, **{"if": []}),
             auto(id="l", name="Lights on", when={"type": "lights", "on": True}, **{"if": []}),
             auto(id="w", name="Tornado", when={"type": "weather", "event": "tornado"}, **{"if": []}),
             auto(id="g", name="Win", when={"type": "game_end", "team": "any", "result": "win"},
                  **{"if": [{"type": "home"}, {"type": "winning"}]})]

    def test_time_fires_once(self):
        sun = self.cfg.loc.sun(datetime(2026, 11, 20).date())["sunset"]
        self.clock[0] = sun.replace(second=0, microsecond=0) + (sun - sun)
        from datetime import timedelta
        self.clock[0] = sun + timedelta(seconds=30)
        self.eng.tick()
        self.clock[0] = sun + timedelta(seconds=60)
        self.eng.tick()
        self.assertEqual([d for d in self.app.did if d[0] == "Sunset"], [("Sunset", "flash")])

    def test_the_schedule_turning_on(self):
        self.at(17)
        self.eng.tick()
        self.at(18, 1)
        self.eng.tick()
        self.assertIn(("Lights on", "flash"), self.app.did)

    def test_a_new_weather_warning(self):
        warn = [{"event": "Tornado Warning"}]
        self.c.wx_alerts = type("W", (), {"active": lambda s, now=None: list(warn)})()
        cur = list(warn)
        warn.clear()
        self.eng.tick()
        warn.extend(cur)
        self.eng.tick()
        self.assertIn(("Tornado", "flash"), self.app.did)

    def test_a_home_win(self):
        self.at(22)
        g = {"teams": {"phi": 4, "nyr": 2}, "home": "phi"}
        out = self.eng.event({"type": "game_end", "team": FLY, "abbr": "phi", "game": g, "result": "win"})
        self.assertIn("ran", out[0])
        self.clock_s[0] += 100
        g2 = {"teams": {"phi": 4, "nyr": 2}, "home": "nyr"}
        out = self.eng.event({"type": "game_end", "team": FLY, "abbr": "phi", "game": g2, "result": "win"})
        self.assertIn("skipped", out[0])
        self.assertEqual(self.eng.event({"type": "game_end", "team": FLY, "abbr": "phi", "game": g, "result": "loss"}), [])


class GameStates(unittest.TestCase):
    def test_start_and_end_are_announced(self):
        from eaveluxos.scores import ScoreWatch
        seen = []
        w = ScoreWatch(lambda *a: None, on_game=lambda t, kind, g: seen.append(kind), now=lambda: 0)
        t = {"key": FLY, "team": "phi", "min_points": 1}
        for st in ("pre", "pre", "in", "in", "post"):
            w._see(t, {"id": "1", "state": st, "detail": "", "teams": {"phi": 1, "nyr": 0}, "start": None}, 0)
        self.assertEqual(seen, ["start", "end"])
        seen.clear()
        w2 = ScoreWatch(lambda *a: None, on_game=lambda t, kind, g: seen.append(kind), now=lambda: 0)
        w2._see(t, {"id": "2", "state": "post", "detail": "", "teams": {"phi": 1, "nyr": 0}, "start": None}, 0)
        self.assertEqual(seen, [], "a game first seen already over isn't announced")


class Server(unittest.TestCase):
    """The actions through the real app, and a webhook event."""
    TOKEN = "t" * 32

    @classmethod
    def setUpClass(cls):
        import eaveluxos.api
        from tests import fake_trimlight as F
        cls.F = F
        cls.cloud = F.start()
        cls._saved = (os.environ.get("TRIMLIGHT_API_BASE"), eaveluxos.api.BASE_URL)
        os.environ["TRIMLIGHT_API_BASE"] = f"http://127.0.0.1:{cls.cloud.server_address[1]}/trimlight"
        eaveluxos.api.BASE_URL = os.environ["TRIMLIGHT_API_BASE"]
        from eaveluxos.server import App, make_server
        cls.dir = Path(tempfile.mkdtemp())
        cls.app = App(cls.dir, start=False)
        s = settings([auto(id="door", name="Doorbell", when={"type": "webhook", "name": "doorbell"}, **{"if": []},
                           then=[{"type": "flash", "color": "#0040FF", "seconds": 15}])])
        s["setup_done"] = True
        cls.app.store.save_settings(s)
        cls.app.store.save_secrets(client_id=F.CID, client_secret=F.SECRET, webhook_token=cls.TOKEN)
        cls.app.rebuild()
        cls.srv = make_server(cls.app, "127.0.0.1", 0)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        import eaveluxos.api
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.app.store.close()
        cls.cloud.shutdown()
        if cls._saved[0] is None:
            os.environ.pop("TRIMLIGHT_API_BASE", None)
        else:
            os.environ["TRIMLIGHT_API_BASE"] = cls._saved[0]
        eaveluxos.api.BASE_URL = cls._saved[1]

    def test_a_webhook_event_flashes(self):
        self.app.ctrl.stop_flash()
        r = urllib.request.Request(f"{self.base}/api/hook/event", method="POST",
                                   headers={"Content-Type": "application/json", "X-Token": self.TOKEN},
                                   data=json.dumps({"name": "Doorbell"}).encode())
        with urllib.request.urlopen(r, timeout=30) as x:
            out = json.loads(x.read())
        self.assertIn("ran", out["automations"][0])
        self.assertEqual(self.app.ctrl.flash["kind"], "automation")
        self.assertEqual(self.app.ctrl.flash["label"], "Doorbell")
        hist = self.app.automation_history()
        self.assertIn("Doorbell", hist[0]["text"])
        self.app.ctrl.stop_flash()

    def test_try_and_check(self):
        self.app.ctrl.stop_flash()
        self.assertIn("tried", self.app.automation_try("door")["result"])
        self.assertEqual(self.app.automation_check("door")["conditions"], [])
        self.app.ctrl.stop_flash()

    def test_an_action_for_one_controller(self):
        devs = [d["deviceId"] for d in self.app.ctrl.devices] or [None]
        if devs[0] is None:
            self.skipTest("no controller listed")
        self.app.auto_show({"type": "show", "effect": next(iter(self.app.ctrl.cfg.effects)), "minutes": 5, "device": devs[0]},
                           {"name": "x"}, {})
        self.assertIn(devs[0], self.app.ctrl.dev_override)
        self.app.ctrl.resume()



class Review(EngineBase):
    """Fixes from the 4.11 code review."""
    AUTOS = [auto(**{"if": []}), auto(id="b", name="Show", when={"type": "webhook", "name": "game"}, **{"if": []},
                                       then=[{"type": "show", "effect": "christmas"}])]

    def test_1_a_weather_warning_stays_on_top(self):
        import subprocess
        import sys
        root = Path(__file__).resolve().parent.parent
        r = subprocess.run([sys.executable, str(root / "tests" / "repro_auto_dismisses_alert.py")], capture_output=True,
                           text=True, encoding="utf-8", timeout=60, cwd=root)
        self.assertIn("OK:", r.stdout, r.stdout + r.stderr)

    def flash_and_end(self, dev):
        self.c.flash_one(dev, self.cfg.effects["snowfall"], 10)
        self.assertIsNotNone(self.c.dev_override[dev]["obj"])
        self.c.dev_override[dev]["expires"] = time.time() - 1
        self.at(20, 1)

    def test_3_a_flash_on_one_controller_goes_back_to_the_choice_by_hand(self):
        self.at(20)
        self.c.manual_one(FRONT, True, "christmas")
        self.flash_and_end(FRONT)
        o = self.c.dev_override[FRONT]
        self.assertEqual((o["effect"], o["obj"], o["expires"]), ("christmas", None, None))
        # and to one made for all of them
        self.c.manual(False)
        self.flash_and_end(DECK)
        self.assertFalse(self.c.dev_override[DECK]["on"], "the Deck back off, as set by hand")
        # with nothing chosen by hand, back to the schedule
        self.c.resume()
        self.flash_and_end(FRONT)
        self.assertNotIn(FRONT, self.c.dev_override)

    def test_3_a_flash_keeps_the_choice_it_covers_by_hand(self):
        self.at(20)
        self.c.manual_one(FRONT, False)
        self.c.flash_one(FRONT, self.cfg.effects["snowfall"], 10)
        self.assertTrue(AU._by_hand(self.c.dev_override[FRONT]))

    def test_4_an_automations_own_show_isnt_a_choice_by_hand(self):
        from eaveluxos.server import App
        self.at(20)
        self.app.auto_show = lambda x, a, ev: App.auto_show(self.app, x, a, ev)
        self.assertIn("ran", self.eng.event({"type": "webhook", "name": "game"})[0])
        self.assertTrue(self.c.override["auto"])
        self.assertIn("ran", self.score()[0], "a goal may still flash over it")

    def test_5_try_it_now_doesnt_start_the_cooldown(self):
        self.at(20)
        self.eng.try_now(self.cfg.automations[0])
        self.assertIn("ran", self.score()[0])


class ReviewServer(Server):
    """Review #2 and #6, through the real app."""

    def test_2_history_is_sent(self):
        self.app.automation_try("door")
        self.app.ctrl.stop_flash()
        r = urllib.request.Request(f"{self.base}/api/automations/history")
        try:
            with urllib.request.urlopen(r, timeout=30) as x:
                status, body = x.status, json.loads(x.read())
        except urllib.error.HTTPError as e:
            status, body = e.code, json.loads(e.read())
        self.assertEqual(status, 200, body)        # it was an empty reply
        self.assertIn("Doorbell", body[0]["text"])

    def test_6_a_failing_automation_doesnt_stop_the_scoreboard(self):
        orig = self.app.autos.event
        self.app.autos.event = lambda ev: 1 / 0
        try:
            self.app.on_score({"key": "nhl-phi", "team": "phi", "automation_only": True}, 1, {"teams": {"phi": 1}})
        finally:
            self.app.autos.event = orig


try:
    from playwright.sync_api import sync_playwright
except ImportError:            # pragma: no cover
    sync_playwright = None

from tests.test_multi45 import TwoBase  # noqa: E402


@unittest.skipIf(sync_playwright is None, "Playwright isn't installed")
class Browser(TwoBase):
    SHOTS = None

    def test_build_one_and_convert_a_celebration(self):
        from eaveluxos.server import make_server
        s = copy.deepcopy(self.app.store.settings)
        s["effects"]["fly"] = {"label": "Flyers", "colors": ["#F74902", "#000000"], "counts": [4, 4]}
        s["gameday"] = {"enabled": False, "celebrate_enabled": True, "celebrate_seconds": 20,
                        "teams": [{"league": "nhl", "team": "phi", "name": "Flyers", "effect": "fly", "celebrate": True}]}
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
            for _ in range(160):
                if cond():
                    return
                time.sleep(0.05)
            self.fail(f"never: {what}")
        autos = lambda: self.app.store.settings.get("automations") or []
        for size in ({"width": 390, "height": 844}, {"width": 1300, "height": 900}):
            pg = br.new_page(viewport=size)
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.goto(base + "#alerts")
            pg.wait_for_selector('[data-fold="autos"]')
            if "closed" in (pg.get_attribute('[data-fold="autos"]', "class") or ""):
                pg.click('[data-fold="autos"] .foldbar')
            pg.wait_for_selector("[data-autoadd]")
            if size["width"] == 390:
                pg.click("[data-autoadd]")
                pg.wait_for_selector("#dlg [data-autoform]")
                self.assertEqual(pg.evaluate("document.documentElement.scrollWidth"), 390, "fits a phone")
                if self.SHOTS:
                    pg.screenshot(path=f"{self.SHOTS}/builder-390.png", full_page=True)
                pg.click("#dlg [data-close]")
                pg.close()
                continue
            pg.click("[data-autoadd]")
            pg.wait_for_selector("#dlg [data-autoform]")
            pg.fill('#dlg input[data-k="name"]', "Flyers goal")
            pg.select_option('#dlg select[data-k="when.team"]', "nhl-phi")
            pg.select_option('#dlg select[data-k="then.0.effect"]', "fly")
            pg.fill('#dlg input[data-k="then.0.seconds"]', "20")
            pg.click("#dlg [data-addthen]")
            pg.select_option('#dlg select[data-k="then.1.type"]', "off")
            pg.click('#dlg [data-rmthen="1"]')
            until(lambda: "When Flyers scores, if it’s dark, then flash Flyers for 20 s." in pg.inner_text("#dlg [data-autosum]"), "the sentence")
            if self.SHOTS:
                pg.screenshot(path=f"{self.SHOTS}/builder.png")
            pg.locator("#dlg .primary").last.click()
            until(lambda: len(autos()) == 1, "saved")
            a = autos()[0]
            self.assertEqual((a["when"], a["then"]), ({"type": "score", "team": "nhl-phi"}, [{"type": "flash", "seconds": 20, "effect": "fly"}]))
            self.assertEqual(a["if"][0]["type"], "dark")
            pg.wait_for_selector('[data-autochk="0"]')
            pg.click('[data-autochk="0"]')
            until(lambda: "dark" in pg.inner_text('[data-autoout="0"]'), "checked")
            pg.click('[data-autotry="0"]')
            until(lambda: "tried" in pg.inner_text('[data-autoout="0"]'), "tried")
            if self.SHOTS:
                pg.screenshot(path=f"{self.SHOTS}/list.png", full_page=True)
            # The Flyers' score celebration as an automation
            pg.goto(base + "#schedule")
            pg.wait_for_selector('[data-fold="game"]')
            if "closed" in (pg.get_attribute('[data-fold="game"]', "class") or ""):
                pg.click('[data-fold="game"] .foldbar')
            pg.wait_for_selector("[data-gdauto]")
            pg.click("[data-gdauto]")
            until(lambda: len(autos()) == 2, "converted")
            b = autos()[1]
            self.assertEqual(b["when"], {"type": "score", "team": "nhl-phi"})
            self.assertEqual(b["then"], [{"type": "flash", "effect": "fly", "seconds": 20}])
            self.assertEqual(b["if"], [{"type": "lights", "on": True}])
            self.assertFalse(self.app.store.settings["gameday"]["teams"][0]["celebrate"])
            pg.close()
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
