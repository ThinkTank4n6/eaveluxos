# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Home's Tonight timeline (3.15)."""
import copy
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from eaveluxos.controller import Controller
from eaveluxos.schedule import Location, build_config
from eaveluxos.store import DEFAULT_SETTINGS
from tests.test_review5 import FakeAPI

NY = ZoneInfo("America/New_York")


class Tonight(unittest.TestCase):
    def setUp(self):
        self.clock = [datetime(2026, 12, 5, 12, 0, tzinfo=NY)]
        self._now = Location.now
        Location.now = lambda loc: self.clock[0]
        s = copy.deepcopy(DEFAULT_SETTINGS)
        s["location"].update(latitude=39.95, longitude=-75.16)
        # A switch: a second rule takes over at 22:00 (higher priority).
        s["rules"].insert(0, {"name": "Late", "dates": "12-01..12-31", "on": "22:00", "off": "23:30",
                              "effect": "warm_white", "priority": 300})
        self.c = Controller(build_config(s, {"client_id": "x", "client_secret": "y"}), FakeAPI())

    def tearDown(self):
        Location.now = self._now

    def tl(self):
        return self.c.status()["tonight"]

    def test_midday(self):
        ev = self.tl()
        self.assertEqual([e["kind"] for e in ev], ["sunset", "on", "switch", "switch", "off"])
        self.assertEqual(ev[1]["text"], "Christmas season: Christmas")
        self.assertEqual(ev[2]["text"], "Late: Warm white")
        self.assertEqual(ev[2]["at"], "10:00 PM")
        self.assertEqual(ev[2]["in_min"], 600)                         # from the app computer's clock
        # 23:30: Late ends while Christmas season (until 00:30) still runs: a switch back, then off.
        self.assertEqual((ev[3]["kind"], ev[3]["text"], ev[3]["at"]), ("switch", "Christmas season: Christmas", "11:30 PM"))
        self.assertEqual((ev[4]["kind"], ev[4]["at"], ev[4]["day"]), ("off", "12:30 AM", "Sun"))

    def test_while_on(self):
        self.clock[0] = datetime(2026, 12, 5, 21, 0, tzinfo=NY)
        ev = self.tl()
        self.assertEqual(ev[0]["kind"], "switch")
        self.assertEqual(ev[0]["in_min"], 60)
        self.assertNotIn("sunset", [e["kind"] for e in ev[:3]])

    def test_nothing_scheduled(self):
        s = copy.deepcopy(DEFAULT_SETTINGS)
        s["location"].update(latitude=39.95, longitude=-75.16)
        s["rules"] = []
        c = Controller(build_config(s, {"client_id": "x", "client_secret": "y"}), FakeAPI())
        self.assertEqual([e["kind"] for e in c.status()["tonight"]], ["sunset"])

    def test_screen(self):
        js = (Path(__file__).resolve().parent.parent / "eaveluxos" / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn("function tonightPanel", js)
        self.assertIn("${tonightPanel(st)}", js)


if __name__ == "__main__":
    unittest.main()
