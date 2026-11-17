# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""4.4: everyday commands over the home network (opt-in), Resync with
Trimlight's cloud, a pause after the greeting, and the reachability check
taking its turn for the connection."""
import copy
import time
import unittest
from pathlib import Path

from eaveluxos import lanlink as L
from tests.test_local43 import ServerBase

ROOT = Path(__file__).resolve().parent.parent
DEV = "TL-EDGE-01"


class Commands(ServerBase):
    def setUp(self):
        super().setUp()
        self.app.ctrl.devices = [{"deviceId": DEV, "name": "Trimlight"}]

    def turn(self, on):
        self.app.local_commands(on)              # saving settings can make a new controller object
        self.app.ctrl.devices = [{"deviceId": DEV, "name": "Trimlight"}]

    def subs(self):
        return [b[0] for _, _, b in self.ctl.frames(L.CMD_REQUEST)]

    def cloud(self):
        return [p for p, _ in self.F.STATE["log"] if p in ("/device/update", "/device/effect/view")]

    def test_off_by_default_everything_through_the_cloud(self):
        self.app.ctrl._switch(DEV, 1)
        self.assertEqual(self.subs(), [])
        self.assertEqual(self.cloud(), ["/device/update"])

    def test_on_off_and_saved_patterns_over_the_home_network(self):
        self.turn(True)
        self.app.ctrl._switch(DEV, 1)
        self.app.ctrl._show_saved(DEV, 9)
        self.app.ctrl._switch(DEV, 0)
        reqs = [b for _, _, b in self.ctl.frames(L.CMD_REQUEST)]
        self.assertEqual(reqs, [L.request(L.SUB_POWER, bytes([1])), L.request(L.SUB_SHOW, bytes([9])), L.request(L.SUB_POWER, bytes([0]))])
        self.assertEqual(self.cloud(), [])
        self.assertTrue(self.app.ctrl.lan_sent[DEV])
        self.assertEqual(self.app.ctrl.lan.switch(DEV), 1)       # what the controller says

    def test_right_after_the_computer_starts(self):
        """No failure yet means usable, even when the clock that counts
        from start-up is still under 5 minutes."""
        from unittest import mock
        self.turn(True)
        with mock.patch("eaveluxos.localmode.time.monotonic", return_value=12.0):
            self.assertTrue(self.app.ctrl.lan.usable(DEV))

    def test_timer_mode_always_through_the_cloud(self):
        self.turn(True)
        self.app.ctrl._switch(DEV, 2)
        self.assertEqual(self.subs(), [])
        self.assertEqual(self.cloud(), ["/device/update"])

    def test_no_answer_falls_back_to_the_cloud_for_a_while(self):
        self.turn(True)
        self.ctl.close()
        with self.assertLogs("eaveluxos.localmode", "WARNING"):
            self.app.ctrl._switch(DEV, 1)
        self.assertEqual(self.cloud(), ["/device/update"])
        self.assertNotIn(DEV, self.app.ctrl.lan_sent)
        self.assertFalse(self.app.ctrl.lan.usable(DEV))           # the cloud for 5 minutes

    def test_not_during_a_show_or_a_local_job(self):
        self.turn(True)
        self.app.lanshow.running = lambda: True
        self.app.ctrl._switch(DEV, 1)
        self.assertEqual(self.subs(), [])
        self.app.lanshow.running = lambda: False
        with self.app.local_busy:
            self.app.ctrl._switch(DEV, 1)
        self.assertEqual(self.subs(), [])

    def test_the_setting_survives_a_new_address(self):
        self.turn(True)
        self.app.musiclink_address("127.0.0.1")
        self.assertTrue(self.app.store.settings["lan"]["commands"])

    def test_panel(self):
        js = (ROOT / "eaveluxos" / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="lccmd"', js)
        self.assertIn("api('local/commands'", js)


class Resync(ServerBase):
    def test_asks_the_controller_to_send_the_cloud_a_fresh_copy(self):
        r = self.app.resync_cloud()
        self.assertTrue(r["ok"])
        self.assertIn("/device/notify-update-shadow", [p for p, _ in self.F.STATE["log"]])
        self.assertFalse([p for p, _ in self.F.STATE["log"] if p.endswith(("/save", "/delete", "/update"))],
                         "changes nothing on the controller")

    def test_messages_point_to_it_not_to_the_trimlight_app(self):
        from eaveluxos.api import UNREADABLE_HELP
        self.assertIn("Resync with Trimlight's cloud", UNREADABLE_HELP)
        for f in ("api.py", "safety.py"):
            self.assertNotIn("Open the Trimlight Edge app", (ROOT / "eaveluxos" / f).read_text(encoding="utf-8"))
        js = (ROOT / "eaveluxos" / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn("data-resync", js)


class Connection(ServerBase):
    def test_a_pause_after_the_greeting(self):
        old, L.GREET_PAUSE = L.GREET_PAUSE, 0.3
        self.addCleanup(setattr, L, "GREET_PAUSE", old)
        t = time.monotonic()
        L.Link("127.0.0.1").open().close()
        self.assertGreaterEqual(time.monotonic() - t, 0.3)
        self.assertIn("GREET_PAUSE = 0.5", (ROOT / "eaveluxos" / "lanlink.py").read_text(encoding="utf-8"))

    def test_the_reachability_check_waits_its_turn(self):
        before = len(self.ctl.got)
        n_conn = self.ctl.most_active
        with self.app.lan_io:
            self.app.lan_seen.update(at=0.0, checking=False)
            self.app.lan_home()
            time.sleep(0.3)
        self.assertTrue(self.app.lan_seen["ok"])
        self.assertEqual(self.ctl.most_active, n_conn, "no connection opened while busy")


if __name__ == "__main__":
    unittest.main()
