# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Hours on per month (3.15)."""
import copy
import shutil
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from eaveluxos.runtime import Runtime
from eaveluxos.schedule import ConfigError, build_config
from eaveluxos.store import DEFAULT_SETTINGS

NY = ZoneInfo("America/New_York")


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.t = [datetime(2026, 11, 30, 23, 0, tzinfo=NY).timestamp()]
        self.r = Runtime(self.dir, now=lambda: self.t[0], tz=NY)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def passes(self, n, on, step=20):
        for _ in range(n):
            self.r.add(on)
            self.t[0] += step

    def hours(self, month):
        return round(self.r.months.get(month, 0) / 3600, 2)

    def test_counts_only_while_on(self):
        self.passes(180, True)            # one hour on, at 20-second passes
        self.passes(180, False)           # one hour off
        self.assertAlmostEqual(self.hours("2026-11") + self.hours("2026-12"), 1.0, places=1)

    def test_split_at_the_month_boundary(self):
        self.passes(360, True)            # 11 PM Nov 30 to 1 AM Dec 1
        self.assertAlmostEqual(self.hours("2026-11"), 1.0, places=1)
        self.assertAlmostEqual(self.hours("2026-12"), 1.0, places=1)

    def test_a_sleeping_computer_adds_nothing_for_the_gap(self):
        self.passes(3, True)
        self.t[0] += 8 * 3600              # asleep all night
        self.passes(1, True)
        self.assertLess(self.r.months.get("2026-12", 0) + self.r.months.get("2026-11", 0), 60)

    def test_saved_and_kept(self):
        self.passes(180, True)
        self.r.save()
        again = Runtime(self.dir, now=lambda: self.t[0], tz=NY)
        self.assertEqual(round(sum(again.months.values()) / 60), 60)
        s = again.summary(12)
        self.assertEqual(len(s), 12)
        self.assertEqual(s[-1]["month"], "2026-12")

    def test_damaged_file(self):
        (self.dir / "runtime.json").write_text('{"2026-11": 3600, "x": 5, "2026-10": -4, "2026-09": "a", "2026-08": 99999999}', encoding="utf-8")
        self.assertEqual(Runtime(self.dir).months, {"2026-11": 3600.0})

    def test_follows_a_changed_time_zone(self):
        """Review #8 (3.15.1): the zone was fixed when the app started."""
        zone = [NY]
        r = Runtime(self.dir, now=lambda: self.t[0], tz=lambda: zone[0])
        self.t[0] = datetime(2026, 12, 1, 3, 0, tzinfo=ZoneInfo("UTC")).timestamp()   # Nov 30, 10 PM in New York
        r.add(True); self.t[0] += 60; r.add(True)
        zone[0] = ZoneInfo("UTC")
        self.t[0] += 60; r.add(True)
        self.assertEqual(sorted(r.months), ["2026-11", "2026-12"])

    def test_cost_settings(self):
        s = copy.deepcopy(DEFAULT_SETTINGS)
        s["location"].update(latitude=39.95, longitude=-75.16)
        s["usage"] = {"watts": 150, "rate": 0.19}
        build_config(s, {"client_id": "x", "client_secret": "y"})
        for bad in ({"watts": -1}, {"rate": 99}, {"watts": "lots"}, {"rate": True}, "cheap"):
            s["usage"] = bad
            with self.assertRaises(ConfigError, msg=bad):
                build_config(s, {"client_id": "x", "client_secret": "y"})

    def test_screen(self):
        js = (Path(__file__).resolve().parent.parent / "eaveluxos" / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn("async function usagePanel", js)
        self.assertIn("api('runtime')", js)


if __name__ == "__main__":
    unittest.main()
