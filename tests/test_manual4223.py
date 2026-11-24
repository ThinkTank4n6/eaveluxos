# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""4.22.3: the manual (what's new, Lightning and Snowflake, alert boxes),
and the same-look fix found while writing it."""
import subprocess
import sys
import unittest
from pathlib import Path

from eaveluxos import lanlink as L
from eaveluxos.localmode import pick_same_look
from tests.test_local43 import ServerBase
from tests.test_local44 import DEV, FALL

HERE = Path(__file__).resolve().parent
MANUAL = (HERE.parent / "MANUAL.md").read_text(encoding="utf-8")


class SameLook(unittest.TestCase):
    PATS = [{"id": 20, "name": "Test Lightning"}, {"id": 22, "name": "Test w/o lightning"}]

    def test_pick(self):
        self.assertEqual(pick_same_look(self.PATS, "test w/o LIGHTNING ", [(0, 20)]), 22, "the same name wins")
        self.assertEqual(pick_same_look(self.PATS, "Test Lightning", [(0, 20)]), 20)
        self.assertEqual(pick_same_look(self.PATS, "Porch", [(0, 20)]), 22, "else one without an effect")
        self.assertEqual(pick_same_look(self.PATS, None, None), 20, "else the lowest number")
        self.assertEqual(pick_same_look(self.PATS, "Porch", [(0, 20), (1, 22)]), 20)
        self.assertIsNone(pick_same_look([], "x", []))


class OnTheController(ServerBase):
    def setUp(self):
        super().setUp()
        self.app.local_commands(True)
        self.app.ctrl.devices = [{"deviceId": DEV, "name": "Trimlight"}]
        rec = [(4, (0xFF, 0x63, 0x00), True), (2, (0x56, 0x10, 0x03), True)]
        self.ctl.holds["patterns"][20] = L.pattern_record(20, "Test Lightning", 0, 128, 139, rec)
        self.ctl.holds["patterns"][22] = L.pattern_record(22, "Test w/o lightning", 0, 128, 139, rec)
        self.ctl.holds["effects"] = [(0, 20)]

    def shown_for(self, label):
        from eaveluxos.schedule import Effect
        n = len(self.ctl.frames(L.CMD_REQUEST))
        self.app.ctrl.known_on = True
        self.app.ctrl._apply(True, Effect("k", label, "custom", payload=dict(FALL), colors=[]))
        return [b[3] for _, _, b in self.ctl.frames(L.CMD_REQUEST)[n:] if b[0] == L.SUB_SHOW]

    def test_1_the_one_meant_is_shown(self):
        self.assertEqual(self.shown_for("Test w/o lightning"), [22])
        self.assertEqual(self.shown_for("Test Lightning"), [20])
        self.assertEqual(self.shown_for("Fall"), [22], "a copy named otherwise: the one without an effect")


class Manual(unittest.TestCase):
    def test_whats_new_and_the_effects(self):
        self.assertIn("## What's new", MANUAL)
        self.assertIn("### Lightning and Snowflake (4.22)", MANUAL)
        self.assertIn("(#lightning-and-snowflake-422)", MANUAL)
        self.assertIn("> [!TIP]", MANUAL)
        self.assertIn("> [!IMPORTANT]", MANUAL)
        self.assertNotIn("the **backup timer** is now the **backup timer**", MANUAL)

    def test_1_the_standalone_repro(self):
        script = str(HERE / "repro_min_same_look_wrong_effect.py")
        self.assertIn("BUG:", subprocess.run([sys.executable, script], capture_output=True, text=True, timeout=60).stdout)
        self.assertIn("OK:", subprocess.run([sys.executable, script, "--fixed"], capture_output=True, text=True, timeout=60).stdout)


if __name__ == "__main__":
    unittest.main()
