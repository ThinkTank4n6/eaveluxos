# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Safety net and nightly rotation, against the fake Trimlight cloud."""
import copy
import shutil
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from tests import fake_trimlight as F
from eaveluxos.api import TrimlightAPI
from eaveluxos.controller import Controller
from eaveluxos.safety import SafetyNet
from eaveluxos.schedule import Location, build_config
from eaveluxos.store import DEFAULT_SETTINGS

NY = ZoneInfo("America/New_York")
_cloud = F.start()
BASE = f"http://127.0.0.1:{_cloud.server_address[1]}/trimlight"


def settings(**extra):
    s = copy.deepcopy(DEFAULT_SETTINGS)
    s["location"].update(latitude=39.95, longitude=-75.17)
    s["rules"] = [{"name": "Night", "on": "sunset", "off": "22:00", "effect": "warm_white", "brightness": 90},
                  {"name": "Late", "dates": "12-31", "on": "20:00", "off": "00:30", "effect": "christmas"}]
    s["safety"] = {"enabled": True, "days": 5}
    s.update(extra)
    return s


class Nightly(unittest.TestCase):
    def test_each_night_gets_the_next_pattern_from_season_start(self):
        s = settings(rules=[{"name": "Season", "dates": "12-01..12-31", "on": "sunset", "off": "23:00",
                             "effect": ["christmas", "warm_white", "snowfall"], "rotate": "nightly"}])
        cfg = build_config(s, {"client_id": "x", "client_secret": "y"})
        pick = lambda d: cfg.schedule.day_plan(d).rule.pick(cfg.schedule.day_plan(d).start, cfg.schedule.day_plan(d).start)[0].key
        self.assertEqual([pick(date(2026, 12, n)) for n in (1, 2, 3, 4)], ["christmas", "warm_white", "snowfall", "christmas"])

    def test_nightly_pattern_holds_all_night(self):
        s = settings(rules=[{"name": "Season", "on": "18:00", "off": "01:00", "effect": ["christmas", "warm_white"], "rotate": "nightly"}])
        cfg = build_config(s, {"client_id": "x", "client_secret": "y"})
        w = cfg.schedule.active_window(datetime(2026, 12, 5, 23, 0, tzinfo=NY))
        a = w.rule.pick(w.start, datetime(2026, 12, 5, 23, 0, tzinfo=NY))
        b = w.rule.pick(w.start, datetime(2026, 12, 6, 0, 45, tzinfo=NY))
        self.assertEqual(a, b)


class Safety(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        F.STATE["corrupt_calendar"] = False
        d = F.STATE["dev"]
        self.user_cal = {"id": 0, "effectId": 3, "startDate": {"month": 12, "day": 1}, "endDate": {"month": 12, "day": 31},
                         "startTime": {"hours": 17, "minutes": 0}, "endTime": {"hours": 23, "minutes": 0}}
        d["calendar"] = [copy.deepcopy(self.user_cal)]
        d["effects"] = [e for e in d["effects"] if not str(e.get("name", "")).startswith("Auto ")]
        self.user_effects = copy.deepcopy(d["effects"])
        self.api = TrimlightAPI(F.CID, F.SECRET, base_url=BASE)
        self.cfg = build_config(settings(), {"client_id": F.CID, "client_secret": F.SECRET})
        self.net = SafetyNet(self.dir)
        self.now = datetime(2026, 12, 29, 12, 0, tzinfo=NY)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_sync_writes_verified_copy_and_leaves_user_items_alone(self):
        self.assertTrue(self.net.sync(self.api, self.cfg, ["TL-EDGE-01"], self.now))
        d = F.STATE["dev"]
        mine = [c for c in d["calendar"] if c["id"] != 0]
        self.assertEqual(len(mine), 5)
        self.assertIn(self.user_cal, d["calendar"])
        dec31 = next(c for c in mine if c["startDate"] == {"month": 12, "day": 31})
        self.assertEqual(dec31["endTime"], {"hours": 23, "minutes": 59})   # past-midnight tail trimmed
        autos = [e for e in d["effects"] if str(e.get("name", "")).startswith("Auto ")]
        self.assertEqual({e["name"] for e in autos}, {"Auto Warm white", "Auto Christmas"})
        self.assertEqual(next(e for e in autos if e["name"] == "Auto Warm white")["brightness"], 90)  # rule level baked in
        for e in self.user_effects:
            self.assertIn(e, d["effects"])
        self.assertTrue(self.net.ready("TL-EDGE-01", self.now.date()))
        self.assertTrue(list((self.dir / "controller-backups").glob("TL-EDGE-01-*.json")))

    def test_resync_reuses_slots(self):
        self.net.sync(self.api, self.cfg, ["TL-EDGE-01"], self.now)
        n_eff = len(F.STATE["dev"]["effects"])
        self.net.sync(self.api, self.cfg, ["TL-EDGE-01"], self.now.replace(day=30))
        self.assertEqual(len(F.STATE["dev"]["effects"]), n_eff)
        self.assertEqual(len([c for c in F.STATE["dev"]["calendar"] if c["id"] != 0]), 5)

    def test_bad_readback_rolls_back(self):
        F.STATE["corrupt_calendar"] = True
        self.assertFalse(self.net.sync(self.api, self.cfg, ["TL-EDGE-01"], self.now))
        self.assertEqual(F.STATE["dev"]["calendar"], [self.user_cal])
        self.assertFalse(self.net.ready("TL-EDGE-01", self.now.date()))
        self.assertIn("didn't read back", self.net.summary()["TL-EDGE-01"]["message"])

    def test_remove_deletes_only_its_own(self):
        self.net.sync(self.api, self.cfg, ["TL-EDGE-01"], self.now)
        self.net.remove(self.api, ["TL-EDGE-01"], self.now)
        self.assertEqual(F.STATE["dev"]["calendar"], [self.user_cal])
        self.assertEqual(F.STATE["dev"]["effects"], self.user_effects)

    def test_full_library_refuses_cleanly(self):
        d = F.STATE["dev"]
        d["effects"] += [{"id": 100 + i, "name": f"filler {i}", "category": 0, "mode": 1} for i in range(60 - len(d["effects"]))]
        try:
            self.assertFalse(self.net.sync(self.api, self.cfg, ["TL-EDGE-01"], self.now))
            self.assertIn("too full", self.net.summary()["TL-EDGE-01"]["message"])
            self.assertEqual(F.STATE["dev"]["calendar"], [self.user_cal])
        finally:
            d["effects"] = copy.deepcopy(self.user_effects)

    def test_scheduler_uses_timer_mode_only_when_armed(self):
        clock = [datetime(2026, 12, 29, 12, 0, tzinfo=NY)]
        orig = Location.now
        Location.now = lambda loc: clock[0]
        try:
            c = Controller(self.cfg, self.api, safety=self.net)
            c.tick()                       # first pass: finds devices, syncs safety net
            c.tick()
            self.assertEqual(F.STATE["dev"]["switchState"], 2)
            c.manual(False)                # off by hand means really off
            self.assertEqual(F.STATE["dev"]["switchState"], 0)
        finally:
            Location.now = orig


if __name__ == "__main__":
    unittest.main()
