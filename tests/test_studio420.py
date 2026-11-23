# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""4.20 Studio: layers, gradients, keyframes and a timeline, and shows
described in words, played on the lights and approved."""
import copy
import threading
import time
import unittest
from unittest import mock

from eaveluxos import studio as ST
from tests.test_local43 import ServerBase


class Compose(unittest.TestCase):
    def test_gradient(self):
        g = ST.gradient(["#000000", "#FFFFFF"], 3)
        self.assertEqual(g, ["#000000", "#808080", "#FFFFFF"])
        self.assertEqual(ST.gradient([{"color": "#FF0000", "at": 0.5}], 3), ["#FF0000"] * 3)

    def test_layers(self):
        p = ST.compose({"length": 10, "base": {"type": "solid", "color": "#FF0000"},
                        "layers": [{"type": "accent", "color": "#FFFFFF", "every": 5, "width": 1},
                                   {"type": "band", "color": "#00FF00", "start": 7, "width": 2}]})
        self.assertEqual(p["bulbs"], ["#FFFFFF", "#FF0000", "#FF0000", "#FF0000", "#FF0000",
                                      "#FFFFFF", "#FF0000", "#00FF00", "#00FF00", "#FF0000"])
        self.assertEqual(sum(p["counts"]), 10)

    def test_never_more_than_the_controller_takes(self):
        p = ST.compose({"length": 300, "base": {"type": "gradient", "stops": ["#FF0000", "#00FF00", "#0000FF", "#FFFF00"]},
                        "layers": [{"type": "accent", "color": "#FFFFFF", "every": 50, "width": 1}]})
        self.assertLessEqual(len(p["colors"]), 30)
        self.assertTrue(all(1 <= n <= 90 for n in p["counts"]))
        self.assertEqual(sum(p["counts"]), 300, "the repeat keeps its length")
        self.assertIn("#FFFFFF", p["colors"], "a layer survives the merging")

    def test_refused(self):
        for bad in ({"length": 1}, {"base": {"type": "plaid"}}, {"base": {"type": "solid", "color": "red"}},
                    {"layers": [{"type": "accent", "color": "#FFFFFF", "every": 1}]}, {"motion": "Moonwalk"},
                    {"layers": [{"type": "band", "color": "#FFFFFF"}] * 5}):
            with self.assertRaises(ValueError, msg=bad):
                ST.compose(bad)


class Words(unittest.TestCase):
    def test_a_show_from_words(self):
        s = ST.from_words("warm white for 30 minutes, then fade to candy cane twinkle over 5 seconds, then deep blue for 2 hours")
        self.assertEqual([k["minutes"] for k in s["keyframes"]], [30, 10, 120])
        self.assertEqual(s["fade"], 5)
        self.assertEqual(len(s["keyframes"]), 3)
        ST.check_show(s)

    def test_one_part_has_no_fade_and_nothing_is_refused(self):
        self.assertEqual(ST.from_words("christmas")["fade"], 0)
        with self.assertRaises(ValueError):
            ST.from_words("   ")

    def test_check_show(self):
        good = {"keyframes": [{"pattern": {"colors": ["#FF0000"]}, "minutes": 5}], "fade": 3}
        self.assertEqual(ST.check_show(good)["name"], "Studio show")
        for bad in ({"keyframes": []}, {"keyframes": [{"pattern": {"colors": ["x"]}}]}, {**good, "fade": 4},
                    {"keyframes": [{"pattern": {"colors": ["#FF0000"]}, "minutes": 0}]}):
            with self.assertRaises(ValueError, msg=bad):
                ST.check_show(bad)

    def test_save_plan_never_replaces_yours(self):
        show = ST.check_show({"name": "Eve!", "keyframes": [{"pattern": {"colors": ["#FF0000"]}}] * 2, "fade": 0})
        add, keys = ST.save_plan(show, {"studio_eve_1": {}})
        self.assertEqual(keys, ["studio_eve_1_2", "studio_eve_2"])


class Server(ServerBase):
    SHOW = {"name": "Christmas Eve", "fade": 3, "keyframes": [
        {"pattern": {"label": "Warm", "colors": ["#E0A060"], "counts": [3]}, "minutes": 30},
        {"pattern": {"label": "Candy", "colors": ["#FF0000", "#FFFFFF"], "counts": [3, 3], "custom_mode": 1}, "minutes": 20}]}

    def test_approve(self):
        r = self.app.studio("save", {"show": self.SHOW, "schedule": True, "on": "sunset", "off": "22:00"})
        self.assertEqual(len(r["patterns"]), 2)
        self.assertEqual(r["rule"], "Studio: Christmas Eve")
        rule = next(x for x in self.app.store.settings["rules"] if x["name"] == r["rule"])
        self.assertEqual((rule["effect"], rule["rotate_each"], rule["off"]), (r["patterns"], [30, 20], "22:00"))
        self.assertEqual(self.app.ctrl.cfg.fade_seconds, 3, "fades turned on for it")
        self.assertEqual(self.app.studio("save", {"show": self.SHOW, "schedule": True})["rule"], "Studio: Christmas Eve (2)")

    def test_play_once_then_the_last_look_stays(self):
        c = self.app.ctrl
        sent = []
        with mock.patch.object(c, "tick", lambda maintenance=True: sent.append(c.override and c.override.get("obj").label)):
            self.app.studio("play", {"show": self.SHOW, "hold": 2})
            for _ in range(100):
                if len(sent) == 2 and c.show_state is None:
                    break
                time.sleep(0.05)
        self.assertEqual(sent, ["Warm", "Candy"])

    def test_a_press_ends_a_show(self):
        c = self.app.ctrl
        sent = []
        with mock.patch.object(c, "tick", lambda maintenance=True: sent.append(c.override and c.override.get("obj") and c.override["obj"].label)):
            self.app.studio("play", {"show": self.SHOW, "hold": 10})
            time.sleep(0.4)
            c.manual(False)
            time.sleep(0.6)
        self.assertNotIn("Candy", sent, "the second look never came")
        self.assertIsNone(c.show_state)

    def test_review_1_a_press_during_a_fade_wins(self):
        import subprocess
        import sys
        from pathlib import Path
        script = str(Path(__file__).with_name("repro_min_show_overrides_press.py"))
        self.assertIn("BUG:", subprocess.run([sys.executable, script], capture_output=True, text=True, timeout=60).stdout)
        self.assertIn("OK:", subprocess.run([sys.executable, script, "--fixed"], capture_output=True, text=True, timeout=60).stdout)
        c = self.app.ctrl
        labels = []
        c.lan = mock.Mock()                       # fades "happen", and a press comes in the middle of one

        def fade(dev, fr, every, cancel=None):
            c.manual(False)
        c.lan.fade = fade
        c.devices = [{"deviceId": "TL-EDGE-01", "name": "T"}]
        with mock.patch.object(c, "tick", lambda maintenance=True: labels.append(c.override and c.override.get("obj") and c.override["obj"].label)):
            self.app.studio("play", {"show": self.SHOW, "hold": 2})
            for _ in range(100):
                if c.show_state is None:
                    break
                time.sleep(0.05)
        self.assertNotIn("Candy", labels)
        self.assertFalse(c.override.get("on"), "Lights off stays")

    def test_refused(self):
        from eaveluxos.server import ApiError
        with self.assertRaises(ApiError):
            self.app.studio("play", {"show": self.SHOW, "hold": 1})
        with self.assertRaises(ApiError):
            self.app.studio("compose", {"spec": {"length": 0}})


try:
    from playwright.sync_api import sync_playwright
except ImportError:            # pragma: no cover
    sync_playwright = None


@unittest.skipIf(sync_playwright is None, "Playwright isn't installed")
class Browser(ServerBase):
    SHOTS = None

    def test_describe_layers_and_approve(self):
        from eaveluxos.server import make_server
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
        ctx = br.new_context(viewport={"width": 1300, "height": 900})
        pg = ctx.new_page()
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(base + "#patterns")
        pg.click("[data-studio]")
        pg.wait_for_selector("#stwords")
        pg.fill("#stwords", "warm white for 30 minutes, then fade to candy cane")
        pg.click("[data-stwords]")
        pg.wait_for_selector('[data-kf="1"]')
        self.assertIn("fade", pg.inner_text("#stwhy"))
        pg.click("[data-kfnew]")
        pg.wait_for_selector("#dlg [data-lform]")
        pg.click("#dlg [data-addly]")
        pg.wait_for_selector('#dlg [data-ly="0.color"]')
        pg.wait_for_selector("#dlg [data-lprev] .strand")
        pg.locator("#dlg .primary").last.click()
        pg.wait_for_selector('[data-kf="2"]')
        if self.SHOTS:
            pg.screenshot(path=f"{self.SHOTS}/studio.png", full_page=True)
        pg.fill("#stname", "Test show")
        pg.click("[data-stsave]")
        until(lambda: any(r.get("name") == "Studio: Test show" for r in self.app.store.settings.get("rules", [])), "approved")
        ph = ctx.new_page()
        ph.set_viewport_size({"width": 390, "height": 844})
        ph.on("pageerror", lambda e: errors.append(str(e)))
        ph.goto(base + "#studio")
        ph.wait_for_selector('[data-kf="0"]')
        self.assertEqual(ph.evaluate("document.documentElement.scrollWidth"), 390, "fits a phone")
        if self.SHOTS:
            ph.screenshot(path=f"{self.SHOTS}/studio-phone.png", full_page=True)
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
