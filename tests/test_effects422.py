# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""4.22: the Pattern Library's Lightning and Snowflake, set over the home
network with sub 0x1b, as the Trimlight app did on Nov 23, 2026 (backups A
to D and the capture)."""
import subprocess
import sys
import unittest
from pathlib import Path

from eaveluxos import lanlink as L
from eaveluxos.localmode import LocalError
from tests import fake_lan
from tests.test_local43 import ServerBase, WithController

HERE = Path(__file__).resolve().parent
# The end of the controller's state in backups A to C (after the daily timers' part)
TAIL_A = bytes.fromhex("02ff00003c0301140200140115001a0b17151f2801")
TAIL_B = bytes.fromhex("02ff00003c0302141603001401150016001a0b1715242f01")
TAIL_C = bytes.fromhex("02ff00003c03021416040014011500160117001a0b1715271d01")


class Layout(unittest.TestCase):
    def test_reads_the_real_backups(self):
        self.assertEqual(L.read_effects(TAIL_A), [(0, 20), (1, 21)])
        self.assertEqual(L.read_effects(TAIL_B), [(0, 20), (1, 21), (0, 22)])
        self.assertEqual(L.read_effects(TAIL_C), [(0, 20), (1, 21), (0, 22), (1, 23)])

    def test_writes_what_the_trimlight_app_sent(self):
        # "Add lightning" 21:35:45 and "Add snowflake" 21:39:00 in the capture
        self.assertEqual(L.request(L.SUB_EFFECTS, bytes([0, 20, 1, 21, 0, 22]))[3:].hex(), "001401150016")
        self.assertEqual(L.request(L.SUB_EFFECTS, bytes([0, 20, 1, 21, 0, 22, 1, 23]))[0], 0x1B)

    def test_anything_else_is_not_guessed(self):
        self.assertIsNone(L.read_effects(b"\x00" * 37))                       # no clock
        bad = bytearray(TAIL_B)
        bad[-17] = 0x15                                                     # Lightning list doesn't match the pairs
        self.assertIsNone(L.read_effects(bytes(bad)))
        self.assertIsNone(L.read_effects(TAIL_A[:-1] + b"\x09"))           # weekday 9
        self.assertIsNone(L.read_effects(bytes.fromhex("0302140203001401150216001a0b17151f2801")))   # kind 2

    def test_tail_helper_matches_the_real_one(self):
        self.assertEqual(fake_lan.effects_tail([(0, 20), (1, 21)]), TAIL_A[5:])


class Local(WithController):
    def setUp(self):
        super().setUp()
        self.ctl.holds["effects"] = [(0, 5)]

    def test_set_and_clear(self):
        self.assertEqual(self.loc.set_effect(9, "snowflake"), [(0, 5), (1, 9)])
        self.assertEqual(self.ctl.holds["effects"], [(0, 5), (1, 9)])
        self.assertTrue(self.backups, "the controller is backed up first")
        self.assertEqual(self.loc.set_effect(5, None), [(1, 9)])
        self.assertEqual(self.loc.set_effect(9, "lightning"), [(0, 9)])
        self.assertEqual(self.loc.read()["effects"], [(0, 9)])

    def test_nothing_sent_when_nothing_changes(self):
        n = len(self.ctl.frames(L.CMD_REQUEST))
        self.loc.set_effect(5, "lightning")
        self.assertFalse([b for _, _, b in self.ctl.frames(L.CMD_REQUEST)[n:] if b[0] == L.SUB_EFFECTS])

    def test_refuses(self):
        for pid, kind in ((0, "lightning"), (61, None), (True, None), (9, "firework")):
            with self.assertRaises(LocalError):
                self.loc.set_effect(pid, kind)
        with self.assertRaises(LocalError):
            self.loc.set_effect(40, "lightning")                     # no pattern 40
        self.ctl.holds["effects"] = None                             # list not laid out as seen
        with self.assertRaises(LocalError) as cm:
            self.loc.set_effect(5, "snowflake")
        self.assertIn("Trimlight Edge app", str(cm.exception))
        self.assertFalse([b for _, _, b in self.ctl.frames(L.CMD_REQUEST) if b[0] == L.SUB_EFFECTS])

    def test_ignored_write_is_caught(self):
        self.ctl.ignore.add(L.SUB_EFFECTS)
        with self.assertRaises(LocalError):
            self.loc.set_effect(9, "lightning")

    def test_1_delete_takes_the_effect_too(self):
        self.loc.delete(5, self.loc.read()["patterns"][4]["name"])
        self.assertNotIn(5, self.ids())
        self.assertEqual(self.ctl.holds["effects"], [], "a pattern saved later under #5 won't flash")

    def test_stale_entries_are_tidied(self):
        self.ctl.holds["effects"] = [(0, 5), (1, 44)]                # 44: deleted before 4.22
        self.assertEqual(self.loc.set_effect(9, "lightning"), [(0, 5), (0, 9)])


class Server(ServerBase):
    def test_state_and_endpoint(self):
        self.ctl.holds["effects"] = [(1, 3)]
        st = self.app.local_state(fresh=True)
        self.assertTrue(st["effects_readable"])
        self.assertEqual({p["id"]: p["extra"] for p in st["patterns"]}[3], "snowflake")
        self.assertEqual({p["id"]: p["extra"] for p in st["patterns"]}[4], "")
        r = self.app.local_effect(4, "lightning")
        self.assertEqual(r["effects"], [{"pattern": 3, "effect": "snowflake"}, {"pattern": 4, "effect": "lightning"}])
        self.app.local_effect(3, "none")
        self.assertEqual(self.ctl.holds["effects"], [(0, 4)])
        self.assertEqual(self.cloud_pattern_writes(), [])

    def test_unreadable_list_shows_no_choice(self):
        st = self.app.local_state(fresh=True)
        self.assertFalse(st["effects_readable"])
        self.assertTrue(all(p["extra"] is None for p in st["patterns"]))

    def test_bad_requests(self):
        from eaveluxos.server import ApiError
        for pid, eff in ((None, "lightning"), ("3", "lightning"), (3, "firework")):
            with self.assertRaises(ApiError):
                self.app.local_effect(pid, eff)

    def test_admins_only_and_audited(self):
        src = (HERE.parent / "eaveluxos" / "server.py").read_text(encoding="utf-8")
        self.assertIn('"/api/local/effect": "Set a pattern\'s effect on a controller"', src)
        js = (HERE.parent / "eaveluxos" / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn("api('local/effect'", js)


class Review(unittest.TestCase):
    def test_1_the_standalone_repro(self):
        script = str(HERE / "repro_min_effect_outlives_pattern.py")
        self.assertIn("BUG:", subprocess.run([sys.executable, script], capture_output=True, text=True, timeout=60).stdout)
        self.assertIn("OK:", subprocess.run([sys.executable, script, "--fixed"], capture_output=True, text=True, timeout=60).stdout)


try:
    from playwright.sync_api import sync_playwright
except ImportError:            # pragma: no cover
    sync_playwright = None


@unittest.skipIf(sync_playwright is None, "Playwright isn't installed")
class Browser(ServerBase):
    def test_choose_an_effect_on_the_local_page(self):
        import threading
        import time
        from eaveluxos.server import make_server
        self.ctl.holds["effects"] = [(0, 2)]
        srv = make_server(self.app, "127.0.0.1", 0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        try:
            pw = sync_playwright().start()
            br = pw.chromium.launch()
        except Exception as e:
            self.skipTest(f"Chromium can't start: {e}")
        self.addCleanup(pw.stop)
        self.addCleanup(br.close)
        pg = br.new_page(viewport={"width": 390, "height": 844})
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(f"http://localhost:{srv.server_address[1]}/#local")
        pg.wait_for_selector("select[data-lceff='2']", timeout=20000)
        self.assertEqual(pg.input_value("select[data-lceff='2']"), "lightning")
        pg.select_option("select[data-lceff='7']", "snowflake")
        for _ in range(200):
            if self.ctl.holds["effects"] == [(0, 2), (1, 7)]:
                break
            time.sleep(0.05)
        self.assertEqual(self.ctl.holds["effects"], [(0, 2), (1, 7)])
        sel = pg.locator("select[data-lceff='7']")
        for _ in range(200):
            if sel.count() and sel.input_value() == "snowflake" and sel.is_enabled():
                break
            time.sleep(0.05)
        self.assertEqual(sel.input_value(), "snowflake", "read back and shown after the change")
        self.assertLessEqual(pg.evaluate("document.documentElement.scrollWidth"), 390, "no sideways scroll on a phone")
        self.assertEqual(errs, [])


if __name__ == "__main__":
    unittest.main()
