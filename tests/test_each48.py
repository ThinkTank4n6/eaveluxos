# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""4.8: each controller on its own. A rule can run some controllers only,
and Home's controller cards turn one controller on or off, or show a pattern
on it, without the others. The parts go out the way Split by controller
does, and a controller whose part didn't change isn't sent anything."""
import copy
import time
import unittest
from datetime import datetime

from eaveluxos.controller import Controller
from eaveluxos.schedule import ConfigError, Location, build_config
from eaveluxos.store import DEFAULT_SETTINGS
from tests.test_controller import NY, FakeWeather

DECK, FRONT = "DECK1", "FRONT1"


class TwoAPI:
    """Trimlight's cloud with two controllers; remembers what each was sent."""
    def __init__(self):
        self.switch = {DECK: 0, FRONT: 0}
        self.calls = []                     # (device, what, value)
        self.clock_offset_min = 0

    def list_devices(self):
        return [{"deviceId": DECK, "name": "Deck"}, {"deviceId": FRONT, "name": "Front"}]

    def get_device(self, d, now):
        return {"name": d, "connectivity": 1, "switchState": self.switch[d], "effects": []}

    def set_switch(self, d, v):
        self.switch[d] = v
        self.calls.append((d, "switch", v))

    def preview_effect(self, d, p):
        self.calls.append((d, "preview", (p.get("category"), p.get("mode"), p.get("brightness"))))

    def run_saved_effect(self, d, pid):
        self.calls.append((d, "saved", pid))

    def since(self, n):
        return self.calls[n:]


class Base(unittest.TestCase):
    RULES = []

    def setUp(self):
        s = copy.deepcopy(DEFAULT_SETTINGS)
        s["location"].update(latitude=39.95, longitude=-75.17)
        s["rules"] = copy.deepcopy(self.RULES)
        self.settings = s
        self.cfg = build_config(s, {"client_id": "x", "client_secret": "y"})
        self.clock = [datetime(2026, 11, 20, 12, 0, tzinfo=NY)]
        self._orig_now = Location.now
        Location.now = lambda loc: self.clock[0]
        self.addCleanup(setattr, Location, "now", self._orig_now)
        self.api = TwoAPI()
        self.c = Controller(self.cfg, self.api, weather=FakeWeather())

    def at(self, h, m=0, day=20):
        self.clock[0] = datetime(2026, 11, day, h, m, tzinfo=NY)
        self.c.next_try = 0
        self.c.tick()
        return self.c._target(commit=False)

    def shown(self, dev, n=0):
        """What dev was last sent, from call n on: (switch, pattern)."""
        sw = pat = None
        for d, what, v in self.api.since(n):
            if d == dev:
                if what == "switch":
                    sw = v
                else:
                    pat = v
        return sw, pat


class Rules(Base):
    RULES = [
        {"name": "Deck evening", "on": "18:00", "off": "21:00", "effect": "warm_white", "brightness": 80,
         "controllers": [DECK]},
        {"name": "Front night", "on": "18:00", "off": "23:00", "effect": "christmas", "brightness": 200,
         "controllers": [FRONT]},
    ]

    def test_each_follows_its_own_rule(self):
        self.assertFalse(self.at(12).on)
        t = self.at(18, 1)
        self.assertTrue(t.on)
        self.assertEqual(t.parts[DECK]["rule"], "Deck evening")
        self.assertEqual(t.parts[FRONT]["rule"], "Front night")
        self.assertEqual(self.api.switch, {DECK: 1, FRONT: 1})
        deck, front = self.shown(DECK)[1], self.shown(FRONT)[1]
        self.assertEqual(deck[2], 80, "the Deck's rule's brightness")
        self.assertEqual(front[2], 200, "the Front's own")
        self.assertNotEqual(deck[1:], front[1:], "different patterns")

    def test_one_ends_and_the_other_isnt_sent_again(self):
        self.at(18, 1)
        n = len(self.api.calls)
        t = self.at(21, 1)
        self.assertTrue(t.on)
        self.assertFalse(t.parts[DECK]["on"])
        self.assertEqual(self.api.switch[DECK], 0)
        self.assertEqual([c for c in self.api.since(n) if c[0] == FRONT], [], "the Front keeps going untouched")
        self.assertFalse(self.at(23, 1).on)
        self.assertEqual(self.api.switch, {DECK: 0, FRONT: 0})

    def test_all_off_when_neither_rule_runs(self):
        self.at(18, 1)
        t = self.at(23, 30)
        self.assertFalse(t.on)
        self.assertIsNone(t.effect)

    def test_verification_expects_the_deck_off(self):
        """The 5-minute check doesn't take the Deck being off for a change
        made outside the app (that would turn it back on)."""
        self.at(18, 1)
        self.at(21, 1)
        notes = []
        self.c.note = lambda m, *a, **k: notes.append(m)
        for m in (6, 12, 18):
            self.c.last_verify = 0
            self.at(21, m)
        self.assertEqual(self.api.switch, {DECK: 0, FRONT: 1})
        self.assertFalse([m for m in notes if "outside this app" in m], notes)

    def test_backup_timer_plans_each_controllers_nights(self):
        if self.c.safety is None:
            from eaveluxos.safety import SafetyNet
            import tempfile
            net = SafetyNet(__import__("pathlib").Path(tempfile.mkdtemp()))
        else:
            net = self.c.safety
        now = datetime(2026, 11, 20, 12, 0, tzinfo=NY)
        deck = net.plan(self.cfg, now, 0, DECK)[0]
        front = net.plan(self.cfg, now, 0, FRONT)[0]
        self.assertEqual({e["rule"] for e in deck}, {"Deck evening"})
        self.assertEqual({e["rule"] for e in front}, {"Front night"})
        self.assertEqual(deck[0]["end"], [21, 0])
        self.assertEqual(front[0]["end"], [23, 0])

    def test_each_controllers_day(self):
        d = datetime(2026, 11, 20).date()
        self.assertEqual([p.rule.name for p in self.cfg.schedule.for_controller(DECK).day_plans(d)], ["Deck evening"])
        self.assertEqual([p.rule.name for p in self.cfg.schedule.for_controller(FRONT).day_plans(d)], ["Front night"])


class AllAndSome(Base):
    RULES = [
        {"name": "Everyday", "on": "18:00", "off": "23:00", "effect": "warm_white"},
        {"name": "Front game", "on": "19:00", "off": "22:00", "effect": "christmas", "controllers": [FRONT],
         "priority": 200},
    ]

    def test_a_higher_rule_for_one_controller(self):
        t = self.at(18, 30)
        self.assertNotIn("multi", t.key, "both follow Everyday: one window, as before")
        self.assertIsNone(t.parts)
        t = self.at(19, 1)
        self.assertEqual((t.parts[DECK]["rule"], t.parts[FRONT]["rule"]), ("Everyday", "Front game"))
        n = len(self.api.calls)
        t = self.at(22, 1)
        self.assertNotIn("multi", t.key)
        self.assertEqual([c for c in self.api.since(n) if c[0] == DECK], [],
                         "the Deck already shows Everyday; not sent again")


class Unchanged(Base):
    RULES = [{"name": "Night", "on": "18:00", "off": "23:00", "effect": "warm_white", "brightness": 60}]

    def test_without_rules_for_some_the_key_is_as_before(self):
        t = self.at(18, 1)
        self.assertTrue(t.key.startswith("on|Night|"))
        self.assertIsNone(t.parts)
        self.assertFalse(self.cfg.schedule.per_controller)
        self.assertIs(self.cfg.schedule.for_controller(DECK), self.cfg.schedule)


class OneByHand(Base):
    RULES = [{"name": "Night", "on": "18:00", "off": "23:00", "effect": "warm_white"}]

    def test_one_controller_on_by_itself(self):
        self.at(12)
        n = len(self.api.calls)
        self.c.manual_one(FRONT, True, "christmas")
        t = self.c._target(commit=False)
        self.assertEqual(t.reason, "manual")
        self.assertTrue(t.parts[FRONT]["manual"])
        self.assertFalse(t.parts[DECK]["on"])
        self.assertEqual(self.api.switch, {DECK: 0, FRONT: 1})
        self.assertEqual(self.shown(FRONT, n)[0], 1)

    def test_it_ends_when_that_controllers_schedule_changes(self):
        self.at(12)
        self.c.manual_one(FRONT, False)
        self.assertFalse(self.at(17).parts[FRONT]["on"])
        t = self.at(18, 1)
        self.assertIsNone(t.parts, "Night runs both again")
        self.assertEqual(self.api.switch, {DECK: 1, FRONT: 1})
        self.assertEqual(self.c.dev_override, {})

    def test_off_tonight_for_one(self):
        self.at(19)
        n = len(self.api.calls)
        self.c.manual_one(DECK, False)
        self.assertEqual(self.api.switch, {DECK: 0, FRONT: 1})
        self.assertEqual([c for c in self.api.since(n) if c[0] == FRONT], [], "the Front isn't touched")
        self.c.manual_one(DECK, None)                   # back on the schedule
        self.assertEqual(self.api.switch, {DECK: 1, FRONT: 1})

    def test_the_top_buttons_mean_all(self):
        self.at(19)
        self.c.manual_one(DECK, False)
        self.c.manual(False)
        self.assertEqual(self.c.dev_override, {})
        self.assertEqual(self.api.switch, {DECK: 0, FRONT: 0})
        self.c.manual_one(FRONT, True, "christmas")
        self.assertIsNone(self.c.override, "a choice for all ends when one controller gets its own")
        self.c.resume()
        self.assertEqual(self.c.dev_override, {})
        self.assertEqual(self.api.switch, {DECK: 1, FRONT: 1})

    def test_only_a_controller_this_app_runs(self):
        self.at(12)
        with self.assertRaises(ValueError):
            self.c.manual_one("SOMEONE-ELSES", True, "christmas")
        with self.assertRaises(ValueError):
            self.c.manual_one(FRONT, True, "no_such_pattern")

    def test_a_split_pattern_chosen_for_one_shows_its_part(self):
        s = copy.deepcopy(self.settings)
        s["effects"]["halves"] = {"label": "Halves", "split": {DECK: "christmas", FRONT: "warm_white"}}
        self.c.cfg = self.cfg = build_config(s, {"client_id": "x", "client_secret": "y"})
        self.at(12)
        n = len(self.api.calls)
        self.c.manual_one(FRONT, True, "halves")
        ww = self.cfg.effects["warm_white"].payload
        self.assertEqual(self.shown(FRONT, n)[1], (ww["category"], ww["mode"], ww["brightness"]))


class Review(Base):
    """The code review of 4.8, before release."""
    RULES = [{"name": "Night", "on": "18:00", "off": "23:00", "effect": "warm_white"}]

    def test_1_no_cloud_requests_while_waiting_to_retry(self):
        import subprocess
        import sys
        from pathlib import Path
        root = Path(__file__).resolve().parent.parent
        r = subprocess.run([sys.executable, str(root / "tests" / "repro_list_backoff.py")], capture_output=True,
                           text=True, encoding="utf-8", timeout=60, cwd=root)
        self.assertIn("OK:", r.stdout, r.stdout + r.stderr)

    def test_2_a_choice_for_a_controller_no_longer_run_waits(self):
        self.at(12)
        self.c.manual_one(FRONT, False)
        self.c.devices = [d for d in self.c.devices if d["deviceId"] == DECK]     # the Front unticked
        t = self.at(19)
        self.assertIsNone(t.parts, "the Deck alone: one window, as before")
        self.assertIn(FRONT, self.c.dev_override, "kept for when the Front is run again")

    def test_3_a_preview_leaves_each_controllers_choice(self):
        self.at(19)
        self.c.manual_one(DECK, False)
        eff = self.cfg.effects["christmas"]
        self.c.manual(True, obj=eff, expires_min=15)
        self.assertIn(DECK, self.c.dev_override)
        self.assertEqual(self.c._target(commit=False).reason, "manual")
        self.c.override["expires"] = time.time() - 1                 # the preview ends
        t = self.at(19, 5)
        self.assertFalse(t.parts[DECK]["on"], "the Deck is still off by hand")


class Config(unittest.TestCase):
    def test_an_empty_list_is_refused(self):
        s = copy.deepcopy(DEFAULT_SETTINGS)
        s["rules"] = [{"name": "X", "on": "18:00", "off": "23:00", "effect": "warm_white", "controllers": []}]
        with self.assertRaises(ConfigError):
            build_config(s, {"client_id": "x", "client_secret": "y"})


if __name__ == "__main__":
    unittest.main()


try:
    from playwright.sync_api import sync_playwright
except ImportError:            # pragma: no cover
    sync_playwright = None

from tests.test_multi45 import DECK as TL_DECK, FRONT as TL_FRONT, TwoBase  # noqa: E402


@unittest.skipIf(sync_playwright is None, "Playwright isn't installed")
class Browser(TwoBase):
    """Home's controller cards and the Schedule tab, with the Deck and the
    Front of the 4.5 tests."""
    SHOTS = None

    def test_cards_rules_and_the_month(self):
        import threading
        from eaveluxos.server import make_server
        s = copy.deepcopy(self.app.store.settings)
        s["rules"] = [{"name": "Everyday", "on": "00:00", "off": "23:59", "effect": "warm_white"},
                      {"name": "Front only", "on": "00:00", "off": "23:59", "effect": "christmas",
                       "controllers": [TL_FRONT], "priority": 200}]
        self.app.store.save_settings(s)
        self.app.rebuild()
        self.app.ctrl.tick()
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
        for size in ({"width": 390, "height": 844}, {"width": 1300, "height": 900}):   # the phone first: the end edits a rule
            ctx = br.new_context(viewport=size)
            self.addCleanup(ctx.close)
            pg = ctx.new_page()
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.goto(base + "#home")
            pg.wait_for_selector(".ctlcards .item.active .owncontrols")
            until(lambda: pg.locator(".ctlcards .item.active").count() == 2, "both run here")
            deck = pg.locator(".ctlcards .item.active", has_text="Deck")
            front = pg.locator(".ctlcards .item.active", has_text="Front")
            self.assertIn("Everyday", deck.locator(".ownline").inner_text())
            self.assertIn("Front only", front.locator(".ownline").inner_text())
            if size["width"] == 390:
                self.assertEqual(pg.evaluate("document.documentElement.scrollWidth"), 390, "fits a phone")
            if self.SHOTS:
                pg.screenshot(path=f"{self.SHOTS}/home-{size['width']}.png", full_page=True)
            if size["width"] == 390:
                continue
            deck.locator('[data-one="off"]').click()
            until(lambda: TL_DECK in self.app.ctrl.dev_override, "the Deck off by itself")
            self.assertNotIn(TL_FRONT, self.app.ctrl.dev_override)
            until(lambda: "Off" in pg.locator(".ctlcards .item.active", has_text="Deck").locator(".ownline").inner_text(),
                  "its card says so")
            pg.locator(".ctlcards .item.active", has_text="Deck").locator('[data-one="schedule"]').click()
            until(lambda: not self.app.ctrl.dev_override, "back on the schedule")
            pg.select_option(f'[data-onepat="{TL_FRONT}"]', "warm_white")
            until(lambda: (self.app.ctrl.dev_override.get(TL_FRONT) or {}).get("effect") == "warm_white", "a pattern for one")
            # Schedule: the rule says whose it is, and the month has a choice
            pg.goto(base + "#schedule")
            pg.wait_for_selector("#upcdev")
            self.assertIn("Front only", pg.inner_text(".list"))
            self.assertIn("Front only", pg.locator(".badge", has_text="only").first.inner_text())
            pg.select_option("#upcdev", TL_DECK)
            until(lambda: "Front only" not in pg.inner_text("#upc") and "Everyday" in pg.inner_text("#upc"), "the Deck's month")
            if self.SHOTS:
                pg.screenshot(path=f"{self.SHOTS}/schedule.png", full_page=True)
            pg.locator('[data-editrule="1"]').click()
            pg.wait_for_selector("input[name=ctl]")
            self.assertEqual(pg.locator("input[name=ctl]:checked").count(), 1)
            pg.locator(f'input[name=ctl][value="{TL_DECK}"]').check()
            pg.locator("dialog button[type=submit], dialog .primary").last.click()
            until(lambda: "controllers" not in self.app.store.settings["rules"][1], "all ticked is all")
        self.assertEqual(errors, [])
