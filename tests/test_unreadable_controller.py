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
        self.net.state["devices"][DEV] = {"effects": {"p_0_security|{}": eid, "fall|{}": eid}, "calendar": [],
                                          "unconfirmed": [eid]}   # saved, never confirmed by a good read
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

    def test_routine_reads_resync_at_most_every_5_minutes(self):
        """Review #5 (3.14.1): each read of a broken copy waited for a resync
        while holding the command lock, every few minutes."""
        self.break_it()
        F.STATE["log"].clear()
        for _ in range(3):
            with self.assertRaises(TrimlightError):
                self.api.get_device(DEV, self.now)
        self.assertEqual([p for p, _ in F.STATE["log"]].count("/device/notify-update-shadow"), 1)
        self.api._resynced[DEV] -= TrimlightAPI.RESYNC_EVERY            # 5 minutes later
        with self.assertRaises(TrimlightError):
            self.api.get_device(DEV, self.now)
        self.assertEqual([p for p, _ in F.STATE["log"]].count("/device/notify-update-shadow"), 2)

    # ---- 4.2.1: no repairs by number; it halts instead -------------------------

    def paths(self):
        return [p for p, _ in F.STATE["log"]]

    def test_halts_on_12006_and_deletes_nothing(self):
        """Nov 15, 2026: a repair by number is a guess once a controller has
        been reset (numbers then belong to other patterns). It stops instead."""
        self.break_it()
        F.STATE["log"].clear()
        notes = []
        self.assertFalse(self.net.sync(self.api, self.cfg, [DEV], self.now, lambda m, lvl=0: notes.append(m)))
        self.assertFalse([p for p in self.paths() if p.endswith(("/delete", "/save"))])
        self.assertTrue(self.net.halted)
        self.assertIn("12006", self.net.halted["why"])
        self.assertIn("stopped itself", notes[-1])
        self.assertFalse(self.net.due([DEV], "x", self.now.date(), 10 ** 12))
        F.STATE["log"].clear()
        self.assertFalse(self.net.sync(self.api, self.cfg, [DEV], self.now))
        self.assertEqual(self.paths(), [], "halted: not even a read")

    def test_turning_it_off_and_on_clears_the_halt(self):
        self.net._halt("test")
        self.net.remove(self.api, [DEV], self.now)
        self.assertIsNone(self.net.halted)
        self.assertTrue(self.net.sync(self.api, self.cfg, [DEV], self.now), self.net.summary())

    def test_never_saves_or_deletes_patterns(self):
        F.STATE["log"].clear()
        self.assertTrue(self.net.sync(self.api, self.cfg, [DEV], self.now), self.net.summary())
        self.assertFalse([p for p in self.paths() if p.startswith("/device/effect/")])
        self.assertEqual(sorted(self.ids()), sorted(e["id"] for e in self.user_effects))

    def test_a_sync_read_also_forgets_reused_numbers(self):
        self.net.state["devices"][DEV] = {"effects": {"fall|{}": 20}, "calendar": []}
        self.net._save()
        F.STATE["dev"]["effects"].append(auto(20, "My Pattern"))
        self.assertTrue(self.net.sync(self.api, self.cfg, [DEV], self.now), self.net.summary())
        self.assertIn("My Pattern", [e["name"] for e in F.STATE["dev"]["effects"]])
        self.assertNotIn(20, self.net.state["devices"][DEV]["effects"].values())

    def test_a_number_now_holding_another_pattern_is_noticed(self):
        """After a reset the controller's patterns are numbered afresh: the
        copy's pattern number can then show something else entirely."""
        self.assertTrue(self.net.sync(self.api, self.cfg, [DEV], self.now), self.net.summary())
        self.assertIsNone(self.net.check_live(DEV, self.api.get_device(DEV, self.now)))
        used = self.net.state["devices"][DEV]["written_effects"][0]
        next(e for e in F.STATE["dev"]["effects"] if e["id"] == used)["name"] = "Thanksgiving"
        self.assertIn("changed outside this app", self.net.check_live(DEV, self.api.get_device(DEV, self.now)))


class LightsTabGuard(unittest.TestCase):
    def test_lights_tab_turns_saving_off_when_unreadable(self):
        js = (Path(__file__).resolve().parent.parent / "eaveluxos" / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn("data-saveports ${d.error && !lanAddr() ? 'disabled' : ''}", js)   # 4.3: unless saved over the home network
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
