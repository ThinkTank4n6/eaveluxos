# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""4.28: the Mac .dmg step tries again after "Resource busy"."""
import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def load():
    spec = importlib.util.spec_from_file_location("elx_build", ROOT / "packaging" / "build.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class Dmg(unittest.TestCase):
    def setUp(self):
        self.b = load()
        self.tmp = Path(tempfile.mkdtemp())
        self.app = self.tmp / "EaveLuxOS.app"
        (self.app / "Contents").mkdir(parents=True)
        self.b.DIST = self.tmp / "dist"
        self.b.ROOT = ROOT
        self.calls = []

    def fake(self, fails):
        def run(cmd, **kw):
            self.calls.append(cmd[:2])
            if cmd[:2] == ["hdiutil", "create"] and fails:
                fails.pop()
                return subprocess.CompletedProcess(cmd, 1, "", "hdiutil: create failed - Resource busy")
            return subprocess.CompletedProcess(cmd, 0, "created\n", "")
        return run

    def test_busy_twice_then_made(self):
        with mock.patch.object(self.b.subprocess, "run", self.fake([1, 1])), mock.patch.object(self.b.time, "sleep") as sl:
            self.b.make_dmg(self.app, self.tmp / "x.dmg")
        self.assertEqual([c for c in self.calls if c[1] == "create"], [["hdiutil", "create"]] * 3)
        self.assertEqual([c for c in self.calls if c[1] == "detach"], [["hdiutil", "detach"]] * 2)
        self.assertEqual([a.args[0] for a in sl.call_args_list], [10, 20])

    def test_gives_up_after_6(self):
        with mock.patch.object(self.b.subprocess, "run", self.fake([1] * 10)), mock.patch.object(self.b.time, "sleep"):
            with self.assertRaises(subprocess.CalledProcessError):
                self.b.make_dmg(self.app, self.tmp / "x.dmg")
        self.assertEqual(len([c for c in self.calls if c[1] == "create"]), 6)


if __name__ == "__main__":
    unittest.main()
