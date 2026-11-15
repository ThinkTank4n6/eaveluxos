# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""3.17.1: fixes from the code review of 3.17.0, one test (or more) each."""
import copy
import shutil
import subprocess
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from eaveluxos.controller import Controller
from eaveluxos.schedule import Location, build_config
from eaveluxos.server import ApiError, App
from tests.test_controller import FakeWeather
from tests.test_house317 import NY, SECRETS, TwoControllerAPI, split_settings

ROOT = Path(__file__).resolve().parent.parent
JS = (ROOT / "eaveluxos" / "static" / "app.js").read_text(encoding="utf-8")


class SplitLevelsTests(unittest.TestCase):
    """#1: a rule's brightness and speed flattened every part of a split."""

    def setUp(self):
        orig = Location.now
        self.addCleanup(setattr, Location, "now", orig)
        Location.now = lambda loc: datetime(2026, 11, 20, 19, 0, tzinfo=NY)

    def run_rule(self, **levels):
        s = split_settings({"D1": "tw", "D2": "security_white"})
        s["effects"]["tw"] = {"label": "Twinkle", "colors": ["#FFC58A"], "counts": [1], "custom_mode": 5, "speed": 20, "brightness": 80}
        s["effects"]["security_white"].update(speed=0, brightness=255)
        s["rules"][0].update(levels)
        api = TwoControllerAPI()
        c = Controller(build_config(s, SECRETS), api, weather=FakeWeather())
        c.tick()
        return c, {d: (p["brightness"], p["speed"]) for d, p in c.sent_effect.items()}

    def test_each_part_keeps_its_own_speed_and_relative_brightness(self):
        _, sent = self.run_rule(brightness=40, speed=200)
        self.assertEqual(sent["D1"][1], 20)
        self.assertEqual(sent["D2"][1], 0)
        self.assertEqual(sent["D1"][0], 40)                      # the first part takes the rule's brightness
        self.assertEqual(sent["D2"][0], round(255 * 40 / 80))    # the garage dims by the same ratio
        self.assertLess(sent["D1"][0], sent["D2"][0])

    def test_without_levels_nothing_changes(self):
        _, sent = self.run_rule()
        self.assertEqual(sent, {"D1": (80, 20), "D2": (255, 0)})

    def test_brightness_stays_in_range(self):
        _, sent = self.run_rule(brightness=255)
        self.assertEqual(sent["D2"][0], 255)

    def test_slider_brightness_scales_too(self):
        c, _ = self.run_rule()
        c.set_levels(brightness=160)
        b = {d: p["brightness"] for d, p in c.sent_effect.items()}
        self.assertEqual(b, {"D1": 160, "D2": 255})

    def test_the_standalone_reproduction_passes(self):
        import sys
        r = subprocess.run([sys.executable, str(ROOT / "tests" / "repro_split_levels.py")], capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)


class SixtyBulbSlotTests(unittest.TestCase):
    """#2: scenes that fit at 90 bulbs per slot failed on 60-bulb controllers."""

    @unittest.skipUnless(shutil.which("node"), "Node.js isn't installed")
    def test_counter_counts_at_the_learned_limit(self):
        r = subprocess.run(["node", str(ROOT / "tests" / "review317_check.js")], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("sceneSlots(T)", JS)
        self.assertIn("S.status.slot_limit", JS)

    def test_refusal_that_can_not_fit_at_60_says_why(self):
        from eaveluxos import api as apimod
        px = []
        for _ in range(14):
            px += [{"index": 0, "count": 75, "color": 0, "disable": True}, {"index": 0, "count": 3, "color": 1, "disable": False}]
        payload = {"category": 1, "mode": 0, "speed": 0, "brightness": 255, "pixels": px}
        calls = []

        class T(apimod.TrimlightAPI):
            def _request(self, method, path, body=None):
                calls.append(len(body["payload"]["pixels"]))
                raise apimod.TrimlightError("code 1001", "api")
        saved = apimod.TrimlightAPI.slot_limit
        try:
            with self.assertRaises(apimod.TrimlightError) as cm:
                T("a", "b").preview_effect("d1", payload)
            self.assertIn("60 bulbs per color slot", str(cm.exception))
            self.assertEqual(calls, [28])                      # no pointless second try
            self.assertEqual(apimod.TrimlightAPI.slot_limit, 60)
        finally:
            apimod.TrimlightAPI.slot_limit = saved

    def test_status_reports_the_limit(self):
        src = (ROOT / "eaveluxos" / "server.py").read_text(encoding="utf-8")
        self.assertIn('st["slot_limit"] = TrimlightAPI.slot_limit', src)


class SceneValidationTests(unittest.TestCase):
    """#3: a malformed scene was accepted and broke the House view."""

    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.app = App(self.d, start=False)

    def tearDown(self):
        self.app.store.close()
        shutil.rmtree(self.d, ignore_errors=True)

    def save(self, scene):
        s = copy.deepcopy(self.app.store.settings)
        s["effects"]["sc"] = {"label": "Sc", "colors": ["off", "#FFFFFF"], "counts": [9, 3], "scene": scene}
        self.app.save_settings(s, s["_rev"])

    def test_good_scene_is_kept(self):
        self.save({"groups": [{"color": "#FFC58A", "level": 50, "bulbs": [10, 11, 12]}]})
        self.assertEqual(self.app.store.settings["effects"]["sc"]["scene"]["groups"][0]["level"], 50)

    def test_malformed_scenes_are_refused(self):
        bad = ["junk", {}, {"groups": []}, {"groups": "x"}, {"groups": [{"color": "red", "bulbs": [1]}]},
               {"groups": [{"color": "#FFFFFF", "bulbs": [0]}]}, {"groups": [{"color": "#FFFFFF", "bulbs": "1-3"}]},
               {"groups": [{"color": "#FFFFFF", "level": 0, "bulbs": [1]}]}, {"groups": [{"color": "#FFFFFF", "bulbs": [1], "x": 1}]},
               {"groups": [{"color": "#FFFFFF", "bulbs": [1]}] * 15}, {"groups": [{"color": "#FFFFFF", "bulbs": [True]}]},
               {"groups": [{"color": "#FFFFFF", "bulbs": [1]}], "extra": 1}]
        for sc in bad:
            with self.subTest(scene=sc), self.assertRaises(ApiError):
                self.save(sc)

    def test_import_with_a_malformed_scene_is_refused(self):
        with self.assertRaises(ApiError):
            self.app.import_settings({"mode": "merge", "settings": {"effects": {"x": {"label": "X", "colors": ["#FFFFFF"], "scene": "junk"}}}})


class HouseViewSourceTests(unittest.TestCase):
    """#4-#9, #11: in the browser code (the logic itself is in review317_check.js)."""

    def test_4_editing_a_split_keeps_hidden_controllers(self):
        self.assertIn("const split = { ...(cur.split || {}) };", JS)

    def test_5_one_shared_photo_load(self):
        self.assertIn("if (photoLoads[key]) return photoLoads[key];", JS)
        self.assertIn("k !== key) { URL.revokeObjectURL", JS)

    def test_6_still_pictures_are_not_redrawn_60_times_a_second(self):
        self.assertIn("if (hvMoving(def)) requestAnimationFrame(frame); else setTimeout(", JS)

    def test_7_8_mismatches_are_shown(self):
        self.assertIn("This scene was made for", JS)
        self.assertIn("Made for ${HouseFX.sceneTotal(e)} bulbs", JS)
        self.assertIn("if (p.b > T) continue;", JS)
        self.assertIn("(past bulb ${addressSpace()})", JS)

    def test_9_11_effective_counts_and_typed_bulbs(self):
        self.assertIn("HouseFX.sceneOwners(T, HV.groups)", JS)
        self.assertIn("HouseFX.parseBulbs($('#hvnums', box).value, T)", JS)


if __name__ == "__main__":
    unittest.main()
