# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""4.22.6: when a controller's effects list can't be read (a Mac owner's
controller, Nov 24), Local mode says so and offers the details to send,
instead of quietly leaving the Effect choice out."""
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path

from eaveluxos import lanlink as L
from tests.test_local43 import ServerBase

HERE = Path(__file__).resolve().parent
GOOD = bytes.fromhex("02ff00003c030000001a0b1010033901")       # Nov 16: no effects set


class Why(unittest.TestCase):
    def test_reasons(self):
        self.assertEqual(L._effects_fields(GOOD)["effects"], [])
        self.assertNotIn("effects_why", L._effects_fields(GOOD))
        no_clock = GOOD[:-7] + bytes(7)
        f = L._effects_fields(no_clock)
        self.assertIsNone(f["effects"])
        self.assertIn("time may not be set", f["effects_why"])
        self.assertEqual(f["effects_tail"], no_clock.hex(" "))
        self.assertIn("follows", L.effects_problem(GOOD[:-8] + b"\x05" + GOOD[-7:]))
        self.assertIn("laid out", L.effects_problem(bytes.fromhex("02ff00003c040000001a0b1010033901")))
        self.assertIn("ends early", L.effects_problem(b"\x01\x02"))

    def test_1_the_standalone_repro(self):
        script = str(HERE / "repro_min_fx_hidden_silently.py")
        self.assertIn("BUG:", subprocess.run([sys.executable, script], capture_output=True, text=True, timeout=60).stdout)
        self.assertIn("OK:", subprocess.run([sys.executable, script, "--fixed"], capture_output=True, text=True, timeout=60).stdout)


class Server(ServerBase):
    def test_state_says_why_and_logs_once(self):
        with self.assertLogs("eaveluxos", "INFO") as cm:
            st = self.app.local_state(fresh=True)
            self.app.local_state(fresh=True)
        self.assertFalse(st["effects_readable"])
        self.assertIn("time may not be set", st["effects_why"])
        self.assertTrue(st["effects_tail"])
        self.assertEqual(sum("couldn't be read" in m for m in cm.output), 1)


try:
    from playwright.sync_api import sync_playwright
except ImportError:            # pragma: no cover
    sync_playwright = None


@unittest.skipIf(sync_playwright is None, "Playwright isn't installed")
class Browser(ServerBase):
    def test_note_and_copy(self):
        from eaveluxos.server import make_server
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
        ctx = br.new_context(viewport={"width": 390, "height": 900})
        ctx.grant_permissions(["clipboard-read", "clipboard-write"], origin=f"http://localhost:{srv.server_address[1]}")
        pg = ctx.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(f"http://localhost:{srv.server_address[1]}/#local")
        pg.wait_for_selector("#lcfxwhy", timeout=20000)
        self.assertIn("aren’t available", pg.inner_text("#lcfxwhy"))
        self.assertFalse(pg.query_selector("select[data-lceff]"))
        pg.click("[data-lcfxcopy]")
        for _ in range(50):
            t = pg.evaluate("navigator.clipboard.readText()")
            if t:
                break
            time.sleep(0.1)
        self.assertIn("effects: no clock", t)
        self.assertLessEqual(pg.evaluate("document.documentElement.scrollWidth"), 390)
        self.assertEqual(errs, [])


if __name__ == "__main__":
    unittest.main()
