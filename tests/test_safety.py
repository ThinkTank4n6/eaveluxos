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
        # A Trimlight-app calendar event on other dates (left alone, and no
        # conflict), and its daily timers off: either would otherwise run in
        # Timer mode too, so the copy isn't used while they're on (see below).
        self.user_cal = {"id": 0, "effectId": 3, "startDate": {"month": 2, "day": 1}, "endDate": {"month": 2, "day": 14},
                         "startTime": {"hours": 17, "minutes": 0}, "endTime": {"hours": 23, "minutes": 0}}
        d["calendar"] = [copy.deepcopy(self.user_cal)]
        self.saved_daily = copy.deepcopy(d["daily"])
        for x in d["daily"]:
            x["enable"] = False
        d["effects"] = [e for e in d["effects"] if not str(e.get("name", "")).startswith("Auto ")]
        self.user_effects = copy.deepcopy(d["effects"])
        self.api = TrimlightAPI(F.CID, F.SECRET, base_url=BASE)
        self.cfg = build_config(settings(), {"client_id": F.CID, "client_secret": F.SECRET})
        self.net = SafetyNet(self.dir)
        self.now = datetime(2026, 12, 29, 12, 0, tzinfo=NY)

    def tearDown(self):
        F.STATE["dev"]["daily"] = self.saved_daily
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_trimlight_app_timers_hold_the_copy_back(self):
        d = F.STATE["dev"]
        # its daily timer on: copied and verified, but not used
        d["daily"][0]["enable"] = True
        self.assertTrue(self.net.sync(self.api, self.cfg, ["TL-EDGE-01"], self.now))
        self.assertFalse(self.net.ready("TL-EDGE-01", self.now.date()))
        self.assertFalse(self.net.summary()["TL-EDGE-01"]["ok"])
        self.assertIn("Not used yet", self.net.summary()["TL-EDGE-01"]["message"])
        # turned off: armed after the next sync
        self.net.disable_app_daily_timers(self.api, "TL-EDGE-01", self.now)
        self.assertTrue(self.net.sync(self.api, self.cfg, ["TL-EDGE-01"], self.now))
        self.assertTrue(self.net.ready("TL-EDGE-01", self.now.date()))
        # a calendar event of its own on the coming nights holds it back too
        d["calendar"].append({"id": 59, "effectId": 3, "startDate": {"month": 12, "day": 20}, "endDate": {"month": 1, "day": 2},
                              "startTime": {"hours": 17, "minutes": 0}, "endTime": {"hours": 23, "minutes": 0}})
        try:
            # The real controller refuses timers that cross its own calendar
            # events (code 12000), so nothing is written and ours are taken back.
            self.assertFalse(self.net.sync(self.api, self.cfg, ["TL-EDGE-01"], self.now))
            sm = self.net.summary()["TL-EDGE-01"]
            self.assertEqual(sm["conflicts"], ["calendar:1"])
            self.assertIn("calendar timer from the Trimlight app", sm["message"])
            self.assertFalse(self.net.ready("TL-EDGE-01", self.now.date()))
            self.assertEqual([c["id"] for c in d["calendar"]], [0, 59])                 # only the user's
            self.assertFalse([e for e in d["effects"] if str(e.get("name", "")).startswith("Auto ")])
            for e in self.user_effects:
                self.assertIn(e, d["effects"])
        finally:
            d["calendar"] = [c for c in d["calendar"] if c["id"] != 59]

    def test_sync_writes_verified_copy_and_leaves_user_items_alone(self):
        self.assertTrue(self.net.sync(self.api, self.cfg, ["TL-EDGE-01"], self.now))
        d = F.STATE["dev"]
        mine = [c for c in d["calendar"] if c["id"] != 0]
        # 5 days, and Dec 31 has two stretches (3.6): "Night" from sunset until
        # "Late" takes over at 20:00, then "Late" until midnight.
        self.assertEqual(len(mine), 6)
        self.assertIn(self.user_cal, d["calendar"])
        dec31 = sorted((c for c in mine if c["startDate"] == {"month": 12, "day": 31}), key=lambda c: c["startTime"]["hours"])
        self.assertEqual([c["endTime"] for c in dec31], [{"hours": 20, "minutes": 0}, {"hours": 23, "minutes": 59}])  # tail trimmed
        self.assertEqual(dec31[1]["startTime"], {"hours": 20, "minutes": 0})
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
        self.assertEqual(len([c for c in F.STATE["dev"]["calendar"] if c["id"] != 0]), 6)

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
