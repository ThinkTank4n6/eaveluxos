# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""4.22.4: the Effect choice disappeared on Chris's controller after the
test patterns were deleted (its two effects lists stopped agreeing)."""
import subprocess
import sys
import unittest
from pathlib import Path

from eaveluxos import lanlink as L
from eaveluxos.localmode import Local as Loc, leftover_effects
from tests.test_local43 import ServerBase, WithController

HERE = Path(__file__).resolve().parent
# The end of the controller's state at 23:36:33 on Nov 23 (backup), after #20 was deleted
TAIL_AFTER = bytes.fromhex("02ff00003c030114010115001a0b1717242101")


class Layout(unittest.TestCase):
    def test_1_reads_the_lists_that_disagree(self):
        self.assertEqual(L.read_effects_full(TAIL_AFTER), ([20], [(1, 21)]))
        self.assertEqual(L.read_effects(TAIL_AFTER), [(1, 21)])

    def test_leftovers_and_new_numbers(self):
        st = {"patterns": [{"id": i} for i in range(1, 20)], "effects": [(1, 21)], "effects_lightning": [20]}
        self.assertEqual(leftover_effects(st), {20, 21})
        self.assertEqual(Loc.free_id(st), 22, "a new pattern doesn't land on 20 or 21")
        self.assertEqual(Loc.free_id(st, 20), 20, "putting back #20 from a backup keeps its number")
        full = {"patterns": [{"id": i} for i in range(1, 61) if i not in (20, 21)], "effects": [(1, 21)], "effects_lightning": [20]}
        self.assertEqual(Loc.free_id(full), 20, "only when nothing else is free")


class Local(WithController):
    def test_choice_works_with_lists_that_disagree(self):
        self.ctl.holds["effects"] = [(1, 44)]
        self.ctl.holds["lightning"] = [43]
        st = self.loc.read()
        self.assertEqual(st["effects"], [(1, 44)])
        self.assertEqual(leftover_effects(st), {43, 44})
        self.assertEqual(self.loc.set_effect(9, "lightning"), [(0, 9)], "the stale 44 is tidied")
        self.assertEqual(self.ctl.holds["effects"], [(0, 9)])


class Server(ServerBase):
    def test_shown_with_a_note(self):
        self.ctl.holds["effects"] = [(1, 44)]
        self.ctl.holds["lightning"] = [43]
        st = self.app.local_state(fresh=True)
        self.assertTrue(st["effects_readable"])
        self.assertEqual(st["effects_leftover"], [43, 44])
        js = (HERE.parent / "eaveluxos" / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn("st.effects_leftover", js)


class Review(unittest.TestCase):
    def test_1_the_standalone_repro(self):
        script = str(HERE / "repro_min_effects_lists_disagree.py")
        self.assertIn("BUG:", subprocess.run([sys.executable, script], capture_output=True, text=True, timeout=60).stdout)
        self.assertIn("OK:", subprocess.run([sys.executable, script, "--fixed"], capture_output=True, text=True, timeout=60).stdout)


if __name__ == "__main__":
    unittest.main()
