# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""3.4 house rooflines: the browser detection code (run with Node when it's
installed) and the server's checks on saved roofline sections."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from eaveluxos.server import ApiError, App

HERE = Path(__file__).resolve().parent


class DetectionInBrowserCode(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node.js isn't installed")
    def test_roofline_js(self):
        r = subprocess.run(["node", str(HERE / "roofline_check.js")], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("roofline ok", r.stdout)


class SavedRooflines(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.app = App(self.dir, start=False)

    def tearDown(self):
        self.app.store.close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def check(self, rooflines):
        self.app._validate_map({"rooflines": rooflines})

    def test_valid_sections_are_saved_with_the_map(self):
        line = {"id": "r1", "kind": "edge", "points": [[0, 40.5], [50, 10], [100, 40]], "wire": [1]}
        s = self.app.store.settings
        s["map"] = {"sides": [{"id": "front", "name": "Front"}, {"id": "shed", "name": "Shed"}],
                    "rooflines": {"front": [line], "shed": []}}
        self.app.save_settings(s, s["_rev"])
        self.assertEqual(self.app.store.settings["map"]["rooflines"]["front"], [line])

    def test_bad_sections_refused(self):
        ok = {"id": "r1", "kind": "edge", "points": [[0, 0], [10, 10]]}
        for bad in ([{**ok, "kind": "gutter"}], [{**ok, "points": [[0, 0]]}], [{**ok, "points": [[0, 0], [101, 5]]}],
                    [{**ok, "points": [[0, 0], [True, 5]]}], [{**ok, "wire": [1]}], [{**ok, "wire": [0, 0]}],
                    [ok, dict(ok)], [{**ok, "id": "<b>"}], [{**ok, "html": "x"}], [ok] * 41,
                    [{**ok, "points": [[i % 100, 1] for i in range(101)]}]):
            with self.assertRaises(ApiError, msg=str(bad)[:80]):
                self.check({"front": bad})
        for bad in ({"../x": [ok]}, [], {"front": {}}):
            with self.assertRaises(ApiError):
                self.check(bad)


if __name__ == "__main__":
    unittest.main()
