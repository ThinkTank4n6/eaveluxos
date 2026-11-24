# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""4.22.1: Start automatically on a Mac (both downloads, Apple silicon and
Intel) never points at a copy of the app that's gone after a restart."""
import plistlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from eaveluxos import autostart

HERE = Path(__file__).resolve().parent
TRANSLOCATED = "/private/var/folders/x1/T/AppTranslocation/9F3A-11/d/EaveLuxOS.app/Contents/MacOS/EaveLuxOS"
DMG = "/Volumes/EaveLuxOS/EaveLuxOS.app/Contents/MacOS/EaveLuxOS"


class Location(unittest.TestCase):
    def test_places_that_dont_last(self):
        for exe in (TRANSLOCATED, DMG):
            msg = autostart.mac_location_problem(exe, "Darwin", True)
            self.assertIn("Applications", msg)
        self.assertIsNone(autostart.mac_location_problem("/Applications/EaveLuxOS.app/Contents/MacOS/EaveLuxOS", "Darwin", True))
        self.assertIsNone(autostart.mac_location_problem(TRANSLOCATED, "Darwin", False), "run from source: not this")
        self.assertIsNone(autostart.mac_location_problem(TRANSLOCATED, "Windows", True))


class OnAMac(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.home, True)
        self.apps = self.home / "Applications" / "EaveLuxOS.app" / "Contents" / "MacOS"
        self.apps.mkdir(parents=True)
        (self.apps / "EaveLuxOS").write_text("")
        for p in (mock.patch("platform.system", return_value="Darwin"), mock.patch.object(Path, "home", return_value=self.home),
                  mock.patch.object(sys, "frozen", True, create=True)):
            p.start()
            self.addCleanup(p.stop)
        self.plist = self.home / "Library/LaunchAgents/com.eaveluxos.plist"

    def run_as(self, exe):
        p = mock.patch.object(sys, "executable", str(exe))
        p.start()
        self.addCleanup(p.stop)

    def target(self):
        with open(self.plist, "rb") as f:
            return plistlib.load(f)["ProgramArguments"][0]

    def test_1_refuses_a_temporary_copy(self):
        self.run_as(TRANSLOCATED)
        with self.assertRaises(RuntimeError) as cm:
            autostart.set_enabled(Path(TRANSLOCATED).parent, True)
        self.assertIn("Applications", str(cm.exception))
        self.assertFalse(self.plist.exists())
        st = autostart.status(Path(TRANSLOCATED).parent)
        self.assertIn("temporary copy", st["problem"])
        autostart.set_enabled(Path(TRANSLOCATED).parent, False)     # turning it off always works

    def test_from_applications(self):
        exe = self.apps / "EaveLuxOS"
        self.run_as(exe)
        st = autostart.set_enabled(self.apps, True)
        self.assertTrue(st["enabled"])
        self.assertIsNone(st["problem"])
        self.assertEqual(self.target(), str(exe))
        self.assertIn("log in", st["note"])

    def test_an_entry_to_a_vanished_copy_is_flagged_and_repointed(self):
        self.run_as(TRANSLOCATED)
        self.plist.parent.mkdir(parents=True)
        self.plist.write_bytes(plistlib.dumps({"Label": "com.eaveluxos", "ProgramArguments": [TRANSLOCATED, "run"]}))
        self.assertFalse(autostart.repoint(Path(TRANSLOCATED).parent), "never toward another temporary copy")
        exe = self.apps / "EaveLuxOS"
        self.run_as(exe)
        self.assertIn("isn't there any more", autostart.status(self.apps)["problem"])
        self.assertTrue(autostart.repoint(self.apps), "opened from Applications: it takes over")
        self.assertEqual(self.target(), str(exe))
        self.assertIsNone(autostart.status(self.apps)["problem"])
        self.assertFalse(autostart.repoint(self.apps), "nothing to change the second time")


class Review(unittest.TestCase):
    def test_1_the_standalone_repro(self):
        script = str(HERE / "repro_min_mac_translocated.py")
        self.assertIn("BUG:", subprocess.run([sys.executable, script], capture_output=True, text=True, timeout=60).stdout)
        self.assertIn("OK:", subprocess.run([sys.executable, script, "--fixed"], capture_output=True, text=True, timeout=60).stdout)

    def test_shown_on_home_and_in_setup(self):
        main = (HERE.parent / "main.py").read_text(encoding="utf-8")
        self.assertIn("autostart.mac_location_problem()", main)
        js = (HERE.parent / "eaveluxos" / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn("a.autostart.problem", js)


if __name__ == "__main__":
    unittest.main()
