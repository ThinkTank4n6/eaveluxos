# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Whites by color temperature (static/whites.js)."""
import re
import shutil
import subprocess
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATIC = HERE.parent / "eaveluxos" / "static"


class WhitesTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node.js isn't installed")
    def test_whites(self):
        r = subprocess.run(["node", str(HERE / "whites_check.js")], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr or r.stdout)

    def test_loaded_before_the_app(self):
        scripts = re.findall(r'<script src="([^"]+)"', (STATIC / "index.html").read_text(encoding="utf-8"))
        self.assertLess(scripts.index("whites.js"), scripts.index("app.js"))

    def test_app_uses_it_in_both_pickers(self):
        js = (STATIC / "app.js").read_text(encoding="utf-8")
        self.assertIn("whitesRow('data-color', 'ckelvin'", js)
        self.assertIn("whitesRow('data-pcolor', 'pkelvin'", js)


if __name__ == "__main__":
    unittest.main()
