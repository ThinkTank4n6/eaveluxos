# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Patterns › Built-in › Recreate with my colors (catalog.recreate)."""
import copy
import re
import unittest

from eaveluxos import catalog
from eaveluxos.schedule import build_config
from eaveluxos.store import DEFAULT_SETTINGS


class RecreateTests(unittest.TestCase):
    def test_every_builtin_gives_a_pattern_the_app_accepts(self):
        s = copy.deepcopy(DEFAULT_SETTINGS)
        s["location"].update(latitude=39.95, longitude=-75.16)
        for i, entry in enumerate(catalog.builtin_list()):
            r = entry["recreate"]
            with self.subTest(builtin=entry["name"]):
                self.assertEqual(r, catalog.recreate(i))
                self.assertTrue(r["colors"])
                self.assertLessEqual(len(r["colors"]), 30)
                self.assertTrue(all(re.fullmatch(r"#[0-9A-F]{6}", c) for c in r["colors"]))
                self.assertEqual(len(r["counts"]), len(r["colors"]))
                self.assertTrue(all(1 <= n <= 90 for n in r["counts"]))
                self.assertIn(r["custom_mode"], range(len(catalog.CUSTOM_MODES)))
                s["effects"] = {**DEFAULT_SETTINGS["effects"], "mine": r}
                build_config(s, {}, need_secrets=False)        # the same validation as saving

    def motion(self, name):
        return catalog.CUSTOM_MODES[catalog.recreate(catalog.BUILTIN.index(name))["custom_mode"]]

    def colors(self, name):
        return catalog.recreate(catalog.BUILTIN.index(name))["colors"]

    def test_closest_motion(self):
        for name, motion in (("Red Green Wave", "Wave forward"), ("Blue Comet", "Comet forward"),
                             ("Green Meteor", "Comet forward"), ("Red Stars", "Stars"), ("White Breath", "Breath"),
                             ("Purple Strobe", "Strobe"), ("Red Yellow Fire", "Stars"), ("Red Green Gradual Snake", "Chase forward"),
                             ("Rainbow Wave", "Wave forward"), ("Rainbow Fade In Out", "Breath"),
                             ("Rainbow Gradual", "Solid fade"), ("Rainbow Gradual Chase", "Chase forward")):
            self.assertEqual(self.motion(name), motion, name)

    def test_colors_from_the_name(self):
        self.assertEqual(self.colors("Red Blue White Strobe"), ["#FF0000", "#0000FF", "#FFFFFF"])
        self.assertEqual(self.colors("Rainbow Stars"), ["#FF0000", "#FFFF00", "#00FF00", "#0000FF", "#8000FF"])
        self.assertEqual(self.colors("Full Color Strobe")[0], "#FF0000")
        self.assertEqual(self.colors("Red White Blank Snake"), ["#FF0000", "#000000", "#FFFFFF", "#000000"])
        self.assertEqual(self.colors("White White Background Stars"), ["#FFFFFF"])

    def test_label_says_it_is_a_copy(self):
        self.assertEqual(catalog.recreate(0)["label"], "Rainbow Gradual Chase (my colors)")

    def test_catalog_sends_it(self):
        b = catalog.catalog()["builtin"]
        self.assertEqual(len(b), 180)
        self.assertTrue(all("recreate" in x for x in b))


if __name__ == "__main__":
    unittest.main()
