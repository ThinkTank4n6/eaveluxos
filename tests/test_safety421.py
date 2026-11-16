# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""4.2.1: the backup timer writes only to a settled controller, never next
to a music show, and never saves patterns (Nov 15, 2026: a pattern save
through the cloud left a controller unreadable, 12006, and a reset lost the
owner's patterns)."""
import copy
import shutil
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from tests import fake_trimlight as F
from tests.test_safety import BASE, WARM, settings
from eaveluxos.api import TrimlightAPI
from eaveluxos.controller import Controller
from eaveluxos.safety import SafetyNet

SETTLE = 120      # tests/__init__.py sets the module's to 0 for every other test
from eaveluxos.schedule import Location, build_config

NY = ZoneInfo("America/New_York")
DEV = "TL-EDGE-01"


class Settled(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.saved = copy.deepcopy(F.STATE["dev"])
        d = F.STATE["dev"]
        d["calendar"] = []
        for x in d["daily"]:
            x["enable"] = False
        d["effects"] = [e for e in d["effects"] if not e["name"].startswith("Auto ")] + [copy.deepcopy(WARM)]
        self.api = TrimlightAPI(F.CID, F.SECRET, base_url=BASE)
        self.cfg = build_config(settings(), {"client_id": F.CID, "client_secret": F.SECRET})
        self.t = [1_000_000.0]
        self.net = SafetyNet(self.dir)
        self.net.clock = lambda: self.t[0]
        self.net.settle = SETTLE
        self.now = datetime(2026, 12, 29, 12, 0, tzinfo=NY)

    def tearDown(self):
        F.STATE["dev"] = self.saved
        shutil.rmtree(self.dir, ignore_errors=True)

    def writes(self):
        return [p for p, _ in F.STATE["log"] if p.endswith(("/save", "/delete"))]

    def test_two_matching_readings_two_minutes_apart(self):
        F.STATE["log"].clear()
        self.assertTrue(self.net.sync(self.api, self.cfg, [DEV], self.now))
        self.assertEqual(self.writes(), [])
        self.assertIn("settled", self.net.summary()[DEV]["message"])
        self.assertAlmostEqual(self.net.retry_at, self.t[0] + SETTLE + 1, delta=1)
        self.assertFalse(list((self.dir / "controller-backups").glob("*.json")) if (self.dir / "controller-backups").exists() else [],
                         "no backup for a reading that only waits")
        self.t[0] += 60
        self.net.sync(self.api, self.cfg, [DEV], self.now)
        self.assertEqual(self.writes(), [], "only a minute: still waiting")
        F.STATE["dev"]["effects"][0]["name"] = "Renamed in the Trimlight app"     # still changing
        self.t[0] += 90
        self.net.sync(self.api, self.cfg, [DEV], self.now)
        self.assertEqual(self.writes(), [], "changed since: the wait starts again")
        self.t[0] += SETTLE
        self.assertTrue(self.net.sync(self.api, self.cfg, [DEV], self.now))
        self.assertTrue(self.writes())
        self.assertTrue(self.net.ready(DEV, self.now.date()))
        self.assertFalse([p for p in self.writes() if "/effect/" in p], "never saves or deletes a pattern")
        # The next day, nothing changed: its own write counts as settled.
        F.STATE["log"].clear()
        self.t[0] += 5
        self.net.sync(self.api, self.cfg, [DEV], self.now.replace(day=30))
        self.assertTrue(self.writes())

    def test_a_late_cloud_copy_is_read_again_4_3_8(self):
        """Nov 16, 2026: all 14 entries "differed" on the first read-back."""
        self.net.settle = 0
        real, reads = self.api.get_device, []

        def lagging(dev, now, **k):
            det = real(dev, now, **k)
            reads.append(1)
            if any(p.endswith("/calendar/save") for p, _ in F.STATE["log"]) and len(reads) == 2:
                det = {**det, "calendar": []}           # the first read after writing: not there yet
            return det
        self.api.get_device = lagging
        self.assertTrue(self.net.sync(self.api, self.cfg, [DEV], self.now), self.net.summary())
        self.assertEqual(len(reads), 3, "read once more")
        self.assertIsNone(self.net.halted)
        self.assertTrue(self.net.ready(DEV, self.now.date()))

    def test_a_real_mismatch_still_halts_and_says_what_differed(self):
        self.net.settle = 0
        real = self.api.get_device
        F.STATE["log"].clear()

        def wrong(dev, now, **k):
            det = real(dev, now, **k)
            if any(p.endswith("/calendar/save") for p, _ in F.STATE["log"]):
                det = {**det, "calendar": [{**c, "effectId": 99} for c in det.get("calendar", [])]}
            return det
        self.api.get_device = wrong
        with self.assertLogs("eaveluxos.safety", "WARNING") as cm:
            self.net.sync(self.api, self.cfg, [DEV], self.now)
        self.assertTrue(self.net.halted)
        self.assertIn("read back as", "".join(cm.output))

    def test_no_writes_while_held(self):
        self.net.settle = 0
        self.net.hold()
        h = self.net.plan_hash(*self.net.plan(self.cfg, self.now))
        self.assertFalse(self.net.due([DEV], h, self.now.date(), self.t[0]))
        F.STATE["log"].clear()
        self.net.sync(self.api, self.cfg, [DEV], self.now)
        self.assertEqual(F.STATE["log"], [])
        self.assertGreaterEqual(self.net.retry_at, self.t[0] + 900)
        self.t[0] += 901
        self.assertTrue(self.net.due([DEV], h, self.now.date(), self.t[0]))

    def test_a_music_show_holds_it(self):
        self.net.settle = 0
        clock = [datetime(2026, 12, 29, 12, 0, tzinfo=NY)]
        orig = Location.now
        Location.now = lambda loc: clock[0]
        try:
            c = Controller(self.cfg, self.api, safety=self.net)
            c.tick()                    # finds the controller
            c.start_music(30)
            F.STATE["log"].clear()
            c.tick()
            self.assertTrue(self.net.held())
            self.assertFalse([p for p in self.writes() if "/calendar/" in p])
        finally:
            Location.now = orig

    def test_turning_it_off_clears_a_halt_even_during_a_hold(self):
        self.net._halt("test")
        self.net.hold()
        clock = [datetime(2026, 12, 29, 12, 0, tzinfo=NY)]
        orig = Location.now
        Location.now = lambda loc: clock[0]
        try:
            cfg = build_config(settings(safety={"enabled": False, "days": 5}), {"client_id": F.CID, "client_secret": F.SECRET})
            c = Controller(cfg, self.api, safety=self.net)
            c.tick()
            c.tick()
            self.assertIsNone(self.net.halted)
        finally:
            Location.now = orig


class Panel(unittest.TestCase):
    def test_switching_it_on_asks_first(self):
        js = (Path(__file__).resolve().parent.parent / "eaveluxos" / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn("never saves patterns", js)
        self.assertIn("st.halted", js)


if __name__ == "__main__":
    unittest.main()
