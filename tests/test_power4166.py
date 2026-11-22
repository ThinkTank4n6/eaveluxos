# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""4.16.6: a short power cut between two read-backs is noticed (Chris's
test, Nov 21), and the controller's own Timer mode counts as a state."""
import unittest

from eaveluxos import lanlink as L
from tests.test_local43 import ServerBase

DEV = "TL-EDGE-01"


def time_left(c):
    import time
    from eaveluxos.controller import VERIFY_EVERY
    return c.last_verify + VERIFY_EVERY - time.time()


class ShortPowerCut(ServerBase):
    def setUp(self):
        super().setUp()
        self.app.local_commands(True)
        self.c = self.app.ctrl
        self.c.devices = [{"deviceId": DEV, "name": "Trimlight"}]
        self.c.manual(True, "christmas")
        self.c.next_try = 0
        self.c.tick()
        self.assertTrue(self.c.lan_sent.get(DEV), "sent over the home network")
        self.check(2)                                        # settled, and the cloud's report noted

    def check(self, n=1):
        before = {id(e) for e in list(self.c.events)}       # (a bounded list: compare entries, not lengths)
        for _ in range(n):
            self.c.last_verify = 0
            self.c.tick()
        return [e["msg"] for e in list(self.c.events) if id(e) not in before]

    def test_a_steady_report_changes_nothing(self):
        for _ in range(4):
            self.assertFalse([m for m in self.check() if "Restoring" in m])

    def test_a_changed_report_puts_the_lights_back_at_once(self):
        self.F.STATE["dev"]["currentEffect"] = {"id": 19, "name": "Fall", "category": 2}
        self.F.STATE["dev"]["switchState"] = 2
        n = len(self.ctl.frames(L.CMD_REQUEST))
        self.assertFalse([m for m in self.check() if "changed outside" in m], "one odd report isn't enough")
        self.assertLess(time_left(self.c), 90, "but it looks again within a minute or so")
        said = self.check()
        self.assertTrue(any("changed outside this app" in m for m in said), said)
        self.c.tick()
        self.assertGreater(len(self.ctl.frames(L.CMD_REQUEST)), n, "sent again over the home network")

    def test_the_cloud_catching_up_costs_one_resend_at_most(self):
        self.check()
        self.F.STATE["dev"]["currentEffect"] = {"id": -1, "name": "Christmas", "category": 1}
        said = self.check(4)
        self.assertLessEqual(sum("Restoring" in m for m in said), 1, said)

    def test_a_send_starts_a_new_baseline(self):
        self.check()
        self.c._sent(DEV, "pattern", True)
        self.assertNotIn(DEV, self.c.cloud_seen)

    def test_offline_isnt_a_change(self):
        self.check()
        self.F.STATE["dev"]["connectivity"] = 0
        self.F.STATE["dev"]["currentEffect"] = {"id": 19}
        said = self.check()
        self.assertFalse([m for m in said if "changed outside" in m], said)


class Pause(ServerBase):
    """4.16.6 (Chris, Nov 21): pause the schedule until it's resumed."""

    def setUp(self):
        super().setUp()
        self.c = self.app.ctrl
        self.c.devices = [{"deviceId": DEV, "name": "Trimlight"}]

    def set_paused(self, on):
        import copy
        s = copy.deepcopy(self.app.store.settings)
        if on:
            s["paused"] = {"since": "2026-11-21T17:00:00-05:00"}
        else:
            s.pop("paused", None)
        self.app.save_settings(s)
        self.c = self.app.ctrl
        self.c.devices = [{"deviceId": DEV, "name": "Trimlight"}]

    def sends(self):
        return [p for p, _ in self.F.STATE["log"] if p in ("/device/update", "/device/effect/view", "/device/effect/preview")]

    def test_paused_sends_nothing_and_says_so(self):
        self.set_paused(True)
        n = len(self.sends())
        self.c.next_try = 0
        self.c.tick()
        t = self.c._target(commit=False)
        self.assertEqual((t.reason, t.hands_off), ("paused", True))
        self.assertEqual(self.sends()[n:], [])
        self.assertTrue(any("Schedule paused" in e["msg"] for e in list(self.c.events)), list(self.c.events)[-3:])
        st = self.c.status()
        self.assertEqual(st["target"]["reason"], "paused")

    def test_by_hand_still_works_while_paused(self):
        self.set_paused(True)
        self.c.manual(True, "christmas")
        self.assertEqual(self.c._target(commit=False).reason, "manual")

    def test_automations_wait_the_security_flash_doesnt(self):
        self.set_paused(True)
        self.c.next_try = 0
        self.c.tick()
        eff = next(iter(self.c.cfg.effects.values()))
        self.assertFalse(self.c.start_flash(seconds=30, effect=eff, kind="automation"))
        self.assertTrue(any("the schedule is paused" in e["msg"] for e in list(self.c.events)))

    def test_resume_runs_the_schedule_again(self):
        self.set_paused(True)
        self.set_paused(False)
        self.assertNotEqual(self.c._target(commit=False).reason, "paused")

    def test_a_bad_pause_is_refused(self):
        import copy
        from eaveluxos.schedule import ConfigError
        s = copy.deepcopy(self.app.store.settings)
        s["paused"] = True
        with self.assertRaises(Exception):
            self.app.save_settings(s)

    def test_kept_out_of_shared_settings(self):
        from eaveluxos import server
        self.assertIn("paused", server.PRIVATE_KEYS)


class Review(unittest.TestCase):
    def test_1_a_short_power_cut_is_noticed(self):
        from tests import reprorun
        reprorun.run(self, "repro_short_power_cut.py", 120)



class NotRunningHere(unittest.TestCase):
    def test_the_app_computer_gets_its_own_words(self):
        from pathlib import Path
        js = (Path(__file__).resolve().parent.parent / "eaveluxos" / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn("!COARSE && /^(localhost|127\\.0\\.0\\.1|\\[::1\\])$/.test(location.hostname)", js)
        self.assertIn("EaveLuxOS isn\\u2019t running on this computer", js)


if __name__ == "__main__":
    unittest.main()
