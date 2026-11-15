# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""3.20: the web's named colors (the RGB charts Trimlight owners share)."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from eaveluxos import catalog, colornames as CN, textpattern

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


class Names(unittest.TestCase):
    def test_every_value_matches_the_standard(self):
        from PIL import ImageColor                       # an independent copy of the standard table
        self.assertEqual(len(CN.NAMES), 141)
        for c in CN.NAMES:
            self.assertEqual(ImageColor.colormap[c["name"].replace(" ", "").lower()].upper(), c["hex"], c["name"])
        self.assertEqual(len({c["name"] for c in CN.NAMES}), 141)
        self.assertEqual({c["group"] for c in CN.NAMES}, set(CN.GROUPS))

    def test_led_notes(self):
        def note(n):
            return CN.lookup(n)["led"]
        for name, kind in (("Crimson", "great"), ("Deep Pink", "great"), ("Lavender", "white"), ("Snow", "white"),
                           ("Pink", "pale"), ("Light Coral", "washed"), ("Chocolate", "shift"), ("Navy", "dim"),
                           ("Maroon", "dim"), ("Gray", "dimwhite"), ("Silver", "dimwhite"), ("Black", "off")):
            self.assertEqual(note(name)["kind"], kind, name)
        self.assertIn("orange", note("Chocolate")["text"])
        self.assertIn("blue", note("Navy")["text"])
        self.assertTrue(all(c["led"]["text"] for c in CN.NAMES))

    def test_lookup(self):
        for typed in ("forest green", "Forest-Green", "FORESTGREEN", "forestgreen"):
            self.assertEqual(CN.lookup(typed)["hex"], "#228B22")
        self.assertEqual(CN.lookup("light slate grey")["hex"], "#778899")
        self.assertIsNone(CN.lookup("blurple"))

    def test_in_the_catalog(self):
        cat = catalog.catalog()
        self.assertEqual(len(cat["names"]), 141)
        self.assertEqual(cat["name_groups"], CN.GROUPS)


class DescribeIt(unittest.TestCase):
    def test_names_in_descriptions(self):
        g = textpattern.generate
        self.assertEqual(g("crimson and forest green chase")["colors"], ["#DC143C", "#228B22"])
        self.assertEqual(g("midnight blue twinkle")["colors"], ["#191970"])
        self.assertEqual(g("deep sky blue and white")["colors"], ["#00BFFF", "#FFFFFF"])
        self.assertEqual(g("slate grey")["colors"], ["#708090"])

    def test_the_apps_own_words_and_themes_win(self):
        self.assertEqual(textpattern.generate("green")["colors"], ["#00C000"], "bright green, tuned for lights")
        self.assertNotEqual(textpattern.generate("snow")["colors"], ["#FFFAFA"], "snow is still the winter theme")
        self.assertNotIn("snow", textpattern.NAMED)
        for w, h in textpattern.NAMED.items():
            textpattern.check_pattern({"label": w, "colors": [h], "counts": [3], "custom_mode": 0})

    def test_a_color_name_isnt_a_modifier(self):
        self.assertEqual(textpattern.generate("dim gray")["brightness"], 220, "dim gray is a color, not 'dim'")
        self.assertEqual(textpattern.generate("dark green")["colors"], ["#006400"], "not darkened twice")
        self.assertEqual(textpattern.generate("dark night, red")["colors"], ["#B20000"], "but 'dark' still darkens")


class Page(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node.js isn't installed")
    def test_reading_names_and_codes(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(CN.NAMES, f)
        self.addCleanup(Path(f.name).unlink)
        r = subprocess.run(["node", str(HERE / "colors_check.js"), f.name], capture_output=True, text=True,
                           encoding="utf-8", timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_screens(self):
        html = (ROOT / "eaveluxos" / "static" / "index.html").read_text(encoding="utf-8")
        self.assertLess(html.index("colors.js"), html.index("app.js"))
        js = (ROOT / "eaveluxos" / "static" / "app.js").read_text(encoding="utf-8")
        for s in ('id="cname"', "data-cnames", "function namedColorsDialog", "Colors.parse(text, S.catalog.names)",
                  'title="${esc(colorName(c))}"', "data-addafter"):
            self.assertIn(s, js)


if __name__ == "__main__":
    unittest.main()
