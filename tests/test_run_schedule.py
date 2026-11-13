# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""The Schedule tab's "Run the schedule" button (resume with force)."""
import unittest
from datetime import datetime
from pathlib import Path

from eaveluxos.controller import Controller
from eaveluxos.schedule import Location, build_config
from tests.test_music import NY, CountingAPI, settings

ROOT = Path(__file__).resolve().parent.parent


class RunScheduleTests(unittest.TestCase):
    def setUp(self):
        self.clock = [datetime(2026, 12, 4, 18, 0, tzinfo=NY)]   # a Friday, inside "Night"
        self._orig_now = Location.now
        Location.now = lambda loc: self.clock[0]
        self.api = CountingAPI()
        self.c = Controller(build_config(settings(), {"client_id": "x", "client_secret": "y"}), self.api)
        self.c.tick(maintenance=False)
        self.assertEqual(self.c._target(commit=False).reason, "schedule")
        self.assertEqual(self.c.applied_key, self.c._target(commit=False).key)

    def tearDown(self):
        Location.now = self._orig_now

    def sends(self):
        return [x for x in self.api.calls if x[0] in ("preview", "switch")]

    def test_plain_resume_sends_nothing_when_already_on_schedule(self):
        self.api.calls.clear()
        self.c.resume()
        self.assertEqual(self.sends(), [])

    def test_run_the_schedule_sends_again(self):
        # Someone changed the lights in the Trimlight Edge app; this app can't see that.
        self.api.calls.clear()
        self.c.resume(force=True)
        self.assertTrue(self.sends(), self.api.calls)
        t = self.c._target(commit=False)
        self.assertEqual(t.reason, "schedule")
        self.assertEqual(self.c.applied_key, t.key)

    def test_run_the_schedule_ends_manual_and_flash(self):
        self.c.manual(False)
        self.assertEqual(self.c._target(commit=False).reason, "manual")
        self.c.resume(force=True)
        self.assertEqual(self.c._target(commit=False).reason, "schedule")
        self.c.start_flash(5)
        self.assertEqual(self.c._target(commit=False).reason, "flash")
        self.c.resume()                                        # Home's "Return to schedule" leaves a flash alone
        self.assertEqual(self.c._target(commit=False).reason, "flash")
        self.c.resume(force=True)
        self.assertEqual(self.c._target(commit=False).reason, "schedule")

    def test_run_the_schedule_ends_a_music_button_show(self):
        self.c.start_music(None)
        self.c.resume(force=True)
        self.assertEqual(self.c._target(commit=False).reason, "schedule")

    def test_schedule_tab_has_the_button(self):
        js = (ROOT / "eaveluxos" / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn("data-runsched", js)
        self.assertIn("action: 'resume', force: true", js)
        srv = (ROOT / "eaveluxos" / "server.py").read_text(encoding="utf-8")
        self.assertIn('ctrl.resume(force=', srv)


if __name__ == "__main__":
    unittest.main()
