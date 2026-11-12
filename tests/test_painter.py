# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""3.5 bulb painter (static/painter.js), run with Node when it's installed,
and the server accepting what the painter produces."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from eaveluxos.server import ApiError, App

HERE = Path(__file__).resolve().parent


class Painter(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node.js isn't installed")
    def test_painter_js(self):
        r = subprocess.run(["node", str(HERE / "painter_check.js")], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_server_accepts_painted_patterns_and_enforces_limits(self):
        d = Path(tempfile.mkdtemp())
        app = App(d, start=False)
        try:
            s = app.store.settings
            # whole house of 100: dark, bulbs 10-20 red, every 4th of 40-60 white, 70-75 zoned off
            colors = ["#000000", "#FF0000", "#000000"] + ["#FFFFFF", "#000000"] * 5 + ["#FFFFFF", "#000000", "off", "#000000"]
            counts = [9, 11, 19] + [1, 3] * 5 + [1, 9, 6, 25]
            self.assertEqual(sum(counts), 100)
            s["effects"]["painted"] = {"label": "Painted", "colors": colors, "counts": counts, "custom_mode": 0}
            app.save_settings(s, s["_rev"])
            self.assertEqual(app.store.settings["effects"]["painted"]["counts"], counts)
            s = app.store.settings
            s["effects"]["too_many"] = {"label": "Too many", "colors": ["#FFFFFF", "#000000"] * 16, "counts": [1, 1] * 16}
            with self.assertRaises(ApiError):
                app.save_settings(s, s["_rev"])
        finally:
            app.store.close()
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
