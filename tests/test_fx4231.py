# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""4.23.1: a newer controller (Mac owner, firmware 4.17.79, Nov 24) sends 0F
before its effects lists where Chris's sends 03: more effects offered."""
import subprocess
import sys
import unittest
from pathlib import Path

from eaveluxos import lanlink as L
from tests.test_local43 import ServerBase, WithController

HERE = Path(__file__).resolve().parent
MAC = bytes.fromhex("0b02052d070f02000144000005dc641401ff00003c0f0000001a0b1807191602")
CHRIS = bytes.fromhex("00000102ff00003c0301140200140115001a0b180d061802")


class Offered(unittest.TestCase):
    def test_1_the_mac_owners_controller(self):
        f = L._effects_fields(MAC)
        self.assertEqual(f["effects"], [])
        self.assertEqual(f["effects_offered"], 0x0F)
        self.assertNotIn("effects_why", f)

    def test_his_lightning_and_snowflake(self):
        # 4.23.2: his backup after setting both in the Trimlight app (Nov 24, 4:25 PM)
        f = L._effects_fields(bytes.fromhex("01ff00003c0f01110201100011001a0b1810192802"))
        self.assertEqual((f["effects_lightning"], f["effects"], f["effects_offered"]), ([17], [(1, 16), (0, 17)], 0x0F))

    def test_chris_unchanged(self):
        f = L._effects_fields(CHRIS)
        self.assertEqual((f["effects"], f["effects_lightning"], f["effects_offered"]), ([(0, 20), (1, 21)], [20], 3))

    def test_kinds_must_be_offered(self):
        with2 = bytes.fromhex("3c0f00010203001a0b1807191602")            # (kind 2, #3) on a 0F controller
        self.assertEqual(L.read_effects(with2), [(2, 3)])
        self.assertIsNone(L.read_effects(bytes.fromhex("3c0300010203001a0b1807191602")), "kind 2 not offered by 03")
        self.assertIsNone(L.read_effects(bytes.fromhex("3c050000001a0b1807191602")), "Snowflake not offered")
        self.assertEqual(L.effect_name(2), "effect 2")

    def test_1_the_standalone_repro(self):
        script = str(HERE / "repro_min_newer_firmware_offered.py")
        self.assertIn("BUG:", subprocess.run([sys.executable, script], capture_output=True, text=True, timeout=60).stdout)
        self.assertIn("OK:", subprocess.run([sys.executable, script, "--fixed"], capture_output=True, text=True, timeout=60).stdout)


class Kept(WithController):
    def test_unknown_kinds_are_kept(self):
        self.ctl.holds["offered"] = 0x0F
        self.ctl.holds["effects"] = [(2, 5)]                       # set in the Trimlight app; not known here
        self.assertEqual(self.loc.read()["effects"], [(2, 5)])
        self.assertEqual(self.loc.set_effect(9, "snowflake"), [(2, 5), (1, 9)])
        self.assertEqual(self.ctl.holds["effects"], [(2, 5), (1, 9)])
        self.assertEqual(self.loc.set_effect(5, "lightning"), [(0, 5), (1, 9)], "choosing one replaces it")


class Shown(ServerBase):
    def test_badge_name_for_an_unknown_kind(self):
        self.ctl.holds["offered"] = 0x0F
        self.ctl.holds["effects"] = [(3, 4)]
        st = self.app.local_state(fresh=True)
        self.assertEqual({p["id"]: p["extra"] for p in st["patterns"]}[4], "effect 3")
        self.assertEqual(self.app.patterns_fx()["by_id"], {"4": "effect 3"})
        js = (HERE.parent / "eaveluxos" / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn("Another effect (set in the Trimlight app)", js)


if __name__ == "__main__":
    unittest.main()
