# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""4.21.1: the Off button always turns the lights off (reported from an
Intel Mac; nothing in the Off button's way is different by computer)."""
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path

from tests.test_local43 import ServerBase

HERE = Path(__file__).resolve().parent


class Review(unittest.TestCase):
    def test_1_the_standalone_repro(self):
        script = str(HERE / "repro_min_off_greyed.py")
        self.assertIn("BUG:", subprocess.run([sys.executable, script], capture_output=True, text=True, timeout=60).stdout)
        self.assertIn("OK:", subprocess.run([sys.executable, script, "--fixed"], capture_output=True, text=True, timeout=60).stdout)

    def test_1_nothing_in_the_way_differs_by_computer(self):
        src = "".join((HERE.parent / "eaveluxos" / f).read_text(encoding="utf-8") for f in ("controller.py", "localmode.py", "lanlink.py", "api.py"))
        for word in ("darwin", "Darwin", "platform.machine", "x86_64", "arm64"):
            self.assertNotIn(word, src)


class Off(ServerBase):
    def cloud(self):
        return self.F.STATE["dev"]

    def settle(self):
        c = self.app.ctrl
        c.next_try = 0
        c.tick()
        return c

    def test_off_when_the_app_already_thinks_off(self):
        c = self.settle()
        c.manual(False)
        self.cloud()["switchState"] = 1          # turned on outside: the Trimlight app, a timer
        c.manual(False)                        # Off pressed again
        self.assertEqual(self.cloud()["switchState"], 0)

    def test_2_on_by_hand_sends_the_switch_even_if_the_app_thinks_on(self):
        c = self.settle()
        key = next(iter(c.cfg.effects))
        c.manual(True, key)
        self.assertTrue(c.known_on)
        self.cloud()["switchState"] = 0          # turned off outside
        other = [k for k in c.cfg.effects if k != key][0]
        c.manual(True, other)
        self.assertEqual(self.cloud()["switchState"], 1, "a pattern by hand switches them on too")

    def test_3_off_during_a_flash(self):
        c = self.settle()
        c.manual(True, next(iter(c.cfg.effects)))
        c.start_flash(minutes=5)
        self.assertEqual(c._target(commit=False).reason, "flash")
        c.manual(False)
        self.assertIsNone(c.flash)
        self.assertFalse(c._target(commit=False).on)
        self.assertEqual(self.cloud()["switchState"], 0)

    def test_off_over_the_home_network(self):
        from eaveluxos import lanlink as L
        self.app.local_commands(True)
        c = self.settle()
        c.manual(True, next(iter(c.cfg.effects)))
        n = len(self.ctl.frames(L.CMD_REQUEST))
        c.manual(False)
        sent = [f for f in self.ctl.frames(L.CMD_REQUEST)[n:] if f[2][:1] == bytes([L.SUB_POWER])]
        self.assertTrue(sent, "the off went over the home network")
        self.assertEqual(sent[-1][2][1:2], bytes([L.POWER_OFF]))


try:
    from playwright.sync_api import sync_playwright
except ImportError:            # pragma: no cover
    sync_playwright = None


@unittest.skipIf(sync_playwright is None, "Playwright isn't installed")
class Browser(ServerBase):
    def test_off_is_never_greyed_out(self):
        from eaveluxos.server import make_server
        self.app.ctrl.manual(False)
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
        pg = br.new_page()
        pg.goto(f"http://localhost:{srv.server_address[1]}/#home")
        pg.wait_for_selector("#quick [data-q=off]")
        for _ in range(100):
            if pg.get_attribute("#quick [data-q=off]", "aria-pressed") == "true":
                break
            time.sleep(0.05)
        self.assertEqual(pg.get_attribute("#quick [data-q=off]", "aria-pressed"), "true", "marked: the app wants off")
        self.assertTrue(pg.is_enabled("#quick [data-q=off]"), "and still clickable")
        dev = self.F.STATE["dev"]
        dev["switchState"] = 1
        pg.click("#quick [data-q=off]")
        for _ in range(100):
            if dev["switchState"] == 0:
                break
            time.sleep(0.05)
        self.assertEqual(dev["switchState"], 0)


if __name__ == "__main__":
    unittest.main()
