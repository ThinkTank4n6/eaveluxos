# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""4.23: the newer Trimlight Edge animations (Chris's backup and capture,
Nov 24, 2026: A1 Twinkle fade 5, A2 Fade 6, A3 Full strobe 17, A4 Twinkle 18,
A5 Firework 19, A6 Inside out 20, A7 Dissolve 21, A8 Juggle 22)."""
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from eaveluxos import catalog, lanlink as L, studio, textpattern
from eaveluxos.api import TrimlightAPI
from eaveluxos.schedule import ConfigError, Effect

HERE = Path(__file__).resolve().parent
SEEN = {"Twinkle fade": 5, "Fade": 6, "Full strobe": 17, "Twinkle": 18, "Firework": 19,
        "Inside out": 20, "Dissolve": 21, "Juggle": 22}


class Names(unittest.TestCase):
    def test_1_as_the_controller_numbers_them(self):
        self.assertEqual(len(catalog.CUSTOM_MODES), 23)
        for name, n in SEEN.items():
            self.assertEqual(catalog.CUSTOM_MODES[n], name)
        self.assertEqual(catalog.CUSTOM_MODES[16], "Solid fade")

    def test_old_names(self):
        self.assertEqual(catalog.mode_index("Stars"), 5)
        self.assertEqual(catalog.mode_index(" breath "), 6)
        self.assertEqual(catalog.mode_index("JUGGLE"), 22)
        self.assertIsNone(catalog.mode_index("Rainbow"))
        self.assertEqual(studio.compose({"length": 10, "base": {"type": "solid", "color": "#FF0000"},
                                         "motion": "Stars"})["custom_mode"], 5, "Studio looks saved before 4.23")

    def test_words(self):
        self.assertEqual(textpattern.generate("red and green fireworks")["custom_mode"], 19)
        self.assertEqual(textpattern.generate("blue twinkle")["custom_mode"], 5)


class Saving(unittest.TestCase):
    def test_pattern_accepts_17_to_22(self):
        for n in (17, 22):
            e = Effect.from_config("k", {"colors": ["#FF0000", "#00FF00"], "counts": [3, 3], "custom_mode": n})
            self.assertEqual(e.payload["mode"], n)
        with self.assertRaises(ConfigError):
            Effect.from_config("k", {"colors": ["#FF0000"], "counts": [3], "custom_mode": 23})

    def test_home_network_carries_the_number(self):
        sub, data = L.preview_message({"category": 1, "mode": 22, "speed": 128, "brightness": 255,
                                       "pixels": [{"index": 0, "count": 3, "color": 0xFF0000, "disable": False}]})
        self.assertEqual((sub, data[0]), (L.SUB_PREVIEW, 22), "as the Trimlight app previewed A8 Juggle")
        rec = L.record_from_effect(29, {"name": "A8 Juggle", "category": 1, "mode": 22, "speed": 128, "brightness": 255,
                                        "pixels": [{"index": 0, "count": 3, "color": 0xFF0000, "disable": False}]})
        self.assertEqual(L.read_record(rec)["mode"], 22)


class Cloud(unittest.TestCase):
    def test_stand_ins_are_ones_the_cloud_lists(self):
        self.assertEqual(sorted(catalog.CLOUD_STANDIN), list(range(17, 23)))
        self.assertTrue(all(0 <= v <= catalog.CLOUD_MAX_MODE for v in catalog.CLOUD_STANDIN.values()))
        self.assertEqual(catalog.cloud_safe({"category": 2, "mode": 17})["mode"], 15)
        self.assertEqual(catalog.cloud_safe({"category": 2, "mode": 9}), {"category": 2, "mode": 9})
        self.assertEqual(catalog.cloud_safe({"category": 0, "mode": 150}), {"category": 0, "mode": 150}, "built-ins: their own numbers")

    def test_api_never_sends_17_to_22(self):
        api = TrimlightAPI.__new__(TrimlightAPI)
        sent = []
        with mock.patch.object(TrimlightAPI, "_with_slot_fallback", lambda self, path, dev, p: sent.append((path, p))):
            api.preview_effect("d", {"category": 2, "mode": 22})
            api.save_effect("d", {"category": 2, "mode": 19, "id": -1})
        self.assertEqual([p["mode"] for _, p in sent], [1, 5])


class Page(unittest.TestCase):
    def test_copy_keeps_the_number_and_preview_draws_them(self):
        js = (HERE.parent / "eaveluxos" / "static" / "app.js").read_text(encoding="utf-8")
        self.assertNotIn("Math.min(16, e.mode", js)
        self.assertIn("custom_mode: e.mode || 0", js)
        fx = (HERE.parent / "eaveluxos" / "static" / "housefx.js").read_text(encoding="utf-8")
        for n in range(17, 23):
            self.assertIn(f"mode === {n}", fx)

    def test_1_the_standalone_repro(self):
        script = str(HERE / "repro_min_new_animation_clamped.py")
        self.assertIn("BUG:", subprocess.run([sys.executable, script], capture_output=True, text=True, timeout=60).stdout)
        self.assertIn("OK:", subprocess.run([sys.executable, script, "--fixed"], capture_output=True, text=True, timeout=60).stdout)


if __name__ == "__main__":
    unittest.main()
