# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""4.10: the House tab with two or more controllers. A side, landmark or zone
can be one controller's; the bulb finder, scenes and zone checks light only
that controller (the others keep showing what they were) and count its own
bulbs; Combine patterns by zone makes one pattern for each controller, saved
together as a Split by controller pattern."""
import copy
import threading
import time
import unittest

from tests.test_each48 import DECK, FRONT, OneByHand
from tests.test_multi45 import DECK as TL_DECK, FRONT as TL_FRONT, TwoBase

try:
    from playwright.sync_api import sync_playwright
except ImportError:            # pragma: no cover
    sync_playwright = None


class OnePreview(OneByHand):
    """A preview for one controller (the finder): it ends by itself."""

    def test_lights_one_and_ends_by_itself(self):
        self.at(19)
        n = len(self.api.calls)
        eff = self.cfg.effects["christmas"]
        self.c.manual_one(FRONT, True, obj=eff, expires_min=10)
        self.assertEqual([c for c in self.api.since(n) if c[0] == DECK], [], "the Deck keeps what it shows")
        self.assertTrue(self.c._target(commit=False).parts[FRONT]["manual"])
        self.c.dev_override[FRONT]["expires"] = time.time() - 1
        notes = []
        self.c.note = lambda m, *a, **k: notes.append(m)
        t = self.at(19, 1)
        self.assertIsNone(t.parts, "both back on the schedule")
        self.assertTrue(any("Preview ended on Front" in m for m in notes), notes)

    def test_moving_the_finder_sends_again(self):
        self.at(19)
        eff = self.cfg.effects["christmas"]
        self.c.manual_one(FRONT, True, obj=eff, expires_min=10)
        k1 = self.c.applied_key
        time.sleep(0.01)
        self.c.manual_one(FRONT, True, obj=self.cfg.effects["warm_white"], expires_min=10)
        self.assertNotEqual(self.c.applied_key, k1)


class Review(unittest.TestCase):
    def test_1_the_finder_on_one_doesnt_wake_the_others(self):
        import subprocess
        import sys
        from pathlib import Path
        root = Path(__file__).resolve().parent.parent
        r = subprocess.run([sys.executable, str(root / "tests" / "repro_finder_wakes_others.py")], capture_output=True,
                           text=True, encoding="utf-8", timeout=60, cwd=root)
        self.assertIn("OK:", r.stdout, r.stdout + r.stderr)


class MapChecks(TwoBase):
    def test_controller_tags_are_checked(self):
        from eaveluxos.server import ApiError, App
        good = {"sides": [{"id": "front", "name": "Front", "device": TL_FRONT}],
                "landmarks": [{"name": "Peak", "bulb": 3, "device": TL_DECK}],
                "zones": [{"name": "Roof", "start": 1, "end": 40, "device": TL_DECK},
                          {"name": "Roof", "start": 1, "end": 50, "device": TL_FRONT}]}
        App._validate_map(good)          # one "Roof" for each controller is fine
        for bad in ({"zones": [{"name": "Roof", "start": 1, "end": 4, "device": 5}]},
                    {"sides": [{"id": "x", "name": "X", "device": ""}]},
                    {"zones": [{"name": "Roof", "start": 1, "end": 4}, {"name": "roof", "start": 5, "end": 9}]}):
            with self.subTest(bad=bad), self.assertRaises(ApiError):
                App._validate_map(bad)


@unittest.skipIf(sync_playwright is None, "Playwright isn't installed")
class Browser(TwoBase):
    SHOTS = None

    def test_finder_zones_and_combine(self):
        from eaveluxos.server import make_server
        s = copy.deepcopy(self.app.store.settings)
        s["effects"].update({"red": {"label": "Red", "colors": ["#FF0000"], "counts": [4]},
                             "blue": {"label": "Blue", "colors": ["#0000FF", "#FFFFFF"], "counts": [3, 3]}})
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
        mp = lambda: self.app.store.settings.get("map") or {}
        pg = br.new_page(viewport={"width": 1300, "height": 900})
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(base + "#map")
        pg.wait_for_selector("#hdev")
        # The two controllers, of different lengths, as Jeff's
        pg.evaluate("""() => { const [a, b] = S.devices.filter(x => x.selected);
            a.ports = [{port: 1, start: 1, end: 96}]; b.ports = [{port: 1, start: 1, end: 106}]; VIEWS.mapRender(); }""")
        pg.wait_for_selector("#hdev")
        self.assertIn("every controller at once", pg.inner_text("#main"))
        # This side is the Front's: choosing it chooses the Front
        pg.select_option("#sidedev", TL_FRONT)
        until(lambda: any(x.get("device") == TL_FRONT for x in mp().get("sides", [])), "the side is the Front's")
        until(lambda: pg.eval_on_selector("#hdev", "e => e.value") == TL_FRONT, "the Front chosen")
        self.assertIn("of 106 addresses", pg.inner_text(".finder"))
        pg.click("[data-show]")
        until(lambda: TL_FRONT in self.app.ctrl.dev_override, "the finder lit the Front only")
        self.assertNotIn(TL_DECK, self.app.ctrl.dev_override)
        self.assertIsNone(self.app.ctrl.override, "not a preview on every controller")
        # A zone for the Front
        if "closed" in (pg.get_attribute('[data-fold="zones"]', "class") or ""):
            pg.click('[data-fold="zones"] .foldbar')
        pg.check("#frange")
        pg.fill("#zname", "Porch")
        pg.click("[data-savezone]")
        until(lambda: any(z.get("device") == TL_FRONT for z in mp().get("zones", [])), "the zone is the Front's")
        # and one for the Deck
        pg.select_option("#hdev", TL_DECK)
        until(lambda: "of 96 addresses" in pg.inner_text(".finder"), "the Deck's 96")
        pg.fill("#zname", "Rail")
        pg.click("[data-savezone]")
        until(lambda: any(z.get("device") == TL_DECK for z in mp().get("zones", [])), "the Deck's zone")
        self.assertIn("Porch", pg.inner_text("#main"))
        if self.SHOTS:
            pg.screenshot(path=f"{self.SHOTS}/house.png", full_page=True)
        # Combine by zone: a part for each controller, as a split
        pg.evaluate("go('create')")
        pg.wait_for_selector("[data-combinezones]")
        pg.click("[data-combinezones]")
        pg.wait_for_selector("#dlg select[name=p0]")
        zs = [z["name"] for z in mp()["zones"]]
        pg.select_option(f"#dlg select[name=p{zs.index('Porch')}]", "red")
        pg.select_option(f"#dlg select[name=p{zs.index('Rail')}]", "blue")
        pg.fill("#dlg input[name=nm]", "Two homes")
        until(lambda: "(106 bulbs)" in pg.inner_text("[data-cmprev]") and "(96 bulbs)" in pg.inner_text("[data-cmprev]"), "both previews")
        if self.SHOTS:
            pg.screenshot(path=f"{self.SHOTS}/combine.png")
        pg.locator("#dlg .primary").last.click()
        effs = lambda: self.app.store.settings["effects"]
        until(lambda: any(e.get("label") == "Two homes" for e in effs().values()), "the split saved")
        sp = next(e for e in effs().values() if e.get("label") == "Two homes")["split"]
        self.assertEqual(set(sp), {TL_DECK, TL_FRONT})
        front, deck = effs()[sp[TL_FRONT]], effs()[sp[TL_DECK]]
        self.assertEqual(sum(front["counts"]), 106)
        self.assertEqual(sum(deck["counts"]), 96)
        self.assertIn("#FF0000", front["colors"])
        self.assertNotIn("#FF0000", deck["colors"], "the Front's zone isn't on the Deck")
        self.assertEqual(front.get("folder"), "Zone parts")
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
