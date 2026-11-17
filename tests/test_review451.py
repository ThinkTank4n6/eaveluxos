# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""4.5.1: review of 4.5.0, with the controllers' health first."""
import subprocess
import sys
import unittest
from pathlib import Path

from tests.test_multi45 import DECK, FRONT, TwoBase

ROOT = Path(__file__).resolve().parent.parent


class Repros(unittest.TestCase):
    def test_no_reads_while_the_cloud_agrees(self):
        """Review #1: hundreds of full reads a night per controller."""
        out = subprocess.run([sys.executable, str(ROOT / "tests" / "repro_verify_reads.py")],
                             capture_output=True, text=True, cwd=ROOT).stdout
        self.assertIn("OK: no home-network reads", out)

    def test_mixed_paths_still_fine(self):
        out = subprocess.run([sys.executable, str(ROOT / "tests" / "repro_mixed_paths.py")],
                             capture_output=True, text=True, cwd=ROOT).stdout
        self.assertIn("OK: no false restores", out)


class Fixes(TwoBase):

    def test_2_ports_never_land_on_the_wrong_controller(self):
        """Review #2: the router gives the Front the Deck's old address."""
        from eaveluxos.server import ApiError
        self.app.local_address(FRONT, "127.0.0.1", force=True)        # really the Deck
        deck_ports = list(self.ctl.holds["ports"])
        with self.assertRaises(ApiError) as cm:
            self.app.update_device({"deviceId": FRONT, "ports": [{"id": 0, "start": 1, "end": 150},
                                    {"id": 1, "start": 0, "end": 0}, {"id": 2, "start": 0, "end": 0},
                                    {"id": 3, "start": 0, "end": 0}]})
        self.assertIn("Nothing was changed", str(cm.exception))
        self.assertIn("may be another controller", str(cm.exception))
        self.assertEqual(self.ctl.holds["ports"], deck_ports)

    def test_2_its_own_ports_twice_in_a_row(self):
        """...but the right controller can be changed again before the cloud
        catches up (what this app set last counts)."""
        self.app.local_address(DECK, "127.0.0.1")
        self.app.local_address(FRONT, "127.0.0.2")
        for end in (150, 160):
            r = self.app.update_device({"deviceId": FRONT, "ports": [{"id": 0, "start": 1, "end": end},
                                        {"id": 1, "start": 0, "end": 0}, {"id": 2, "start": 0, "end": 0},
                                        {"id": 3, "start": 0, "end": 0}]})
            self.assertTrue(r["local"])
        self.assertEqual(self.front.holds["ports"][0], (1, 160, 1))

    def test_3_no_quiet_yes_when_the_cloud_cant_tell(self):
        """Review #3: the cloud couldn't be read (12006, offline): ask."""
        self.F.STATE["fail_get"] = (FRONT,)
        self.addCleanup(self.F.STATE.pop, "fail_get", None)
        r = self.app.local_address(FRONT, "127.0.0.2")
        self.assertFalse(r["ok"])
        self.assertIn("Couldn't check", r["confirm"])
        self.assertTrue(self.app.local_address(FRONT, "127.0.0.2", force=True)["ok"])

    def test_4_commands_need_a_controllers_address(self):
        """Review #4: the old address isn't any controller's yet."""
        from eaveluxos.server import ApiError
        with self.assertRaises(ApiError) as cm:
            self.app.local_commands(True)
        self.assertIn("choose which controller the saved one is", str(cm.exception))
        self.app.local_address(DECK, "127.0.0.1")
        self.assertTrue(self.app.local_commands(True)["commands"])


if __name__ == "__main__":
    unittest.main()
