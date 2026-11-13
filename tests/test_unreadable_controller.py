# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Trimlight code 12006, "Device data could not be parsed ... declared 21 and
scanned 20 effect records" (3.13.1). Two new safety-net patterns saved back to
back were given the same number by the cloud, which then couldn't read the
controller at all: the safety net, the Lights tab and read-backs all failed."""
import copy
import json
import shutil
import tempfile
import unittest
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from tests import fake_trimlight as F
from tests.test_safety import BASE, settings
from eaveluxos.api import TrimlightAPI, TrimlightError
from eaveluxos.safety import SafetyNet
from eaveluxos.schedule import build_config

NY = ZoneInfo("America/New_York")
DEV = "TL-EDGE-01"


def auto(eid, name):
    return {"id": eid, "name": name, "category": 1, "mode": 0, "speed": 100, "brightness": 100,
            "pixels": [{"index": 0, "count": 3, "color": 0xFF0000, "disable": False}]}


class Unreadable(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.saved = copy.deepcopy(F.STATE["dev"])
        d = F.STATE["dev"]
        d["calendar"] = []
        for x in d["daily"]:
            x["enable"] = False
        d["effects"] = [e for e in d["effects"] if not str(e.get("name", "")).startswith("Auto ")]
        self.user_effects = copy.deepcopy(d["effects"])
        self.api = TrimlightAPI(F.CID, F.SECRET, base_url=BASE)
        self.cfg = build_config(settings(), {"client_id": F.CID, "client_secret": F.SECRET})
        self.net = SafetyNet(self.dir)
        self.now = datetime(2026, 12, 29, 12, 0, tzinfo=NY)
        # The first backup, from before this app wrote anything.
        (self.dir / "controller-backups").mkdir()
        (self.dir / "controller-backups" / f"{DEV}-original.json").write_text(json.dumps(d), encoding="utf-8")

    def tearDown(self):
        F.STATE["dev"] = self.saved
        for k in ("stale_shadow", "shadow", "fail_12006"):
            F.STATE.pop(k, None)
        shutil.rmtree(self.dir, ignore_errors=True)

    def ids(self):
        return [e["id"] for e in F.STATE["dev"]["effects"]]

    def break_it(self, eid=20):
        """The controller as found on Nov 13: two safety-net patterns numbered alike."""
        F.STATE["dev"]["effects"] += [auto(eid, "Auto 0-Security"), auto(eid, "Auto Fall")]
        self.net.state["devices"][DEV] = {"effects": {"p_0_security|{}": eid, "fall|{}": eid}, "calendar": []}
        self.net._save()

    def test_message_explains_and_keeps_details(self):
        self.break_it()
        with self.assertRaises(TrimlightError) as cm:
            self.api.get_device(DEV, self.now)
        self.assertTrue(cm.exception.unreadable)
        self.assertIn("Trimlight Edge app", str(cm.exception))
        self.assertIn("code 12006", str(cm.exception))

    def test_a_passing_problem_is_retried_after_a_resync(self):
        F.STATE["fail_12006"] = 1
        F.STATE["log"].clear()
        self.assertEqual(self.api.get_device(DEV, self.now)["name"], "Trimlight")
        self.assertIn("/device/notify-update-shadow", [p for p, _ in F.STATE["log"]])

    def test_safety_net_repairs_its_own_duplicate_patterns(self):
        self.break_it()
        self.assertTrue(self.net.sync(self.api, self.cfg, [DEV], self.now), self.net.summary())
        self.assertEqual(len(self.ids()), len(set(self.ids())))       # readable again
        for e in self.user_effects:                                    # the user's patterns untouched
            self.assertIn(e, F.STATE["dev"]["effects"])
        self.assertFalse([e for e in F.STATE["dev"]["effects"] if e["name"] in ("Auto 0-Security", "Auto Fall")])
        self.assertTrue(self.net.ready(DEV, self.now.date()))
        self.api.get_device(DEV, self.now)

    def test_turning_the_safety_net_off_also_repairs(self):
        self.break_it()
        self.assertTrue(self.net.remove(self.api, [DEV], self.now))
        self.assertEqual(sorted(self.ids()), sorted(e["id"] for e in self.user_effects))

    def test_never_deletes_the_users_patterns(self):
        # Two of the user's own patterns share a number: not ours to fix.
        uid = self.user_effects[1]["id"]
        F.STATE["dev"]["effects"].append(auto(uid, "Copy made in the Trimlight app"))
        self.net.state["devices"][DEV] = {"effects": {"x|{}": uid}, "calendar": []}   # even if recorded as ours
        self.net._save()
        F.STATE["log"].clear()
        self.assertFalse(self.net.sync(self.api, self.cfg, [DEV], self.now))
        self.assertNotIn("/device/effect/delete", [p for p, _ in F.STATE["log"]])
        self.assertIn("Trimlight Edge app", self.net.summary()[DEV]["message"])

    def test_new_patterns_wait_for_the_cloud_to_catch_up(self):
        # The cloud numbers new patterns from a stale copy, as on Nov 13.
        F.STATE["stale_shadow"] = True
        F.STATE["shadow"] = set(self.ids())
        self.assertTrue(self.net.sync(self.api, self.cfg, [DEV], self.now), self.net.summary())
        autos = [e for e in F.STATE["dev"]["effects"] if e["name"].startswith("Auto ")]
        self.assertEqual(len(autos), 2)
        self.assertEqual(len(self.ids()), len(set(self.ids())))
        self.api.get_device(DEV, self.now)


class LightsTabGuard(unittest.TestCase):
    def test_lights_tab_turns_saving_off_when_unreadable(self):
        js = (Path(__file__).resolve().parent.parent / "eaveluxos" / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn("data-saveports ${d.error ? 'disabled' : ''}", js)
        self.assertIn("data-savedev ${d.error ? 'disabled' : ''}", js)

    def test_server_refuses_every_port_off(self):
        from eaveluxos.server import ApiError, App
        d = Path(tempfile.mkdtemp())
        try:
            app = App(d)
            with self.assertRaises(ApiError) as cm:
                app.update_device({"deviceId": DEV, "ports": [{"id": i, "start": 0, "end": 0} for i in range(4)]})
            self.assertIn("At least one port", str(cm.exception))
            app.store.close()
        finally:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
