# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""4.9.2: Color correction, Local mode and Pattern backups have their own
buttons in Setup's row, instead of folded panels under Lights & controller."""
import json
import subprocess
import threading
import time
import unittest
from pathlib import Path

from tests.test_multi45 import DECK, FRONT, TwoBase

ROOT = Path(__file__).resolve().parent.parent

try:
    from playwright.sync_api import sync_playwright
except ImportError:            # pragma: no cover
    sync_playwright = None


class Nav(unittest.TestCase):
    def test_sections(self):
        js = ("const N = require(%s); console.log(JSON.stringify({secs: N.SETUP_SECS.map(s => s[0]), admin: N.ADMIN_SECS,"
              " r: ['color', 'local', 'backups'].map(v => N.resolve(v, () => true, 'lights'))}));"
              % json.dumps(str(ROOT / "eaveluxos" / "static" / "nav.js")))
        try:
            out = subprocess.run(["node", "-e", js], capture_output=True, text=True, encoding="utf-8", timeout=30)
        except FileNotFoundError:
            self.skipTest("Node isn't installed")
        got = json.loads(out.stdout)
        self.assertEqual(got["secs"][:4], ["lights", "color", "local", "backups"])
        self.assertEqual(got["admin"], ["local", "backups"])
        self.assertTrue(all(r["tab"] == "setup" and r["setup"] for r in got["r"]))


@unittest.skipIf(sync_playwright is None, "Playwright isn't installed")
class Browser(TwoBase):
    def test_own_sections(self):
        from eaveluxos.server import make_server
        self.app.local_address(DECK, "127.0.0.1")
        self.app.local_address(FRONT, "127.0.0.2")
        srv = make_server(self.app, "127.0.0.1", 0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        base = f"http://localhost:{srv.server_address[1]}/"
        try:
            pw = sync_playwright().start()
            br = pw.chromium.launch()
        except Exception as e:
            self.skipTest(f"Chromium can't start: {e}")
        self.addCleanup(pw.stop)
        self.addCleanup(br.close)
        errors = []
        for size in ({"width": 390, "height": 844}, {"width": 1300, "height": 900}):
            pg = br.new_page(viewport=size)
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.goto(base + "#lights")
            pg.wait_for_selector("#subnav [data-sec=color]")
            self.assertEqual(pg.locator("#subnav [data-sec]").all_inner_texts()[:4],
                             ["Lights & controller", "Color correction", "Local mode", "Pattern backups"])
            for f in ("color", "local", "backups"):
                self.assertEqual(pg.locator(f'[data-fold="{f}"]').count(), 0, f"{f} isn't folded under Lights any more")
            pg.click("#subnav [data-sec=color]")
            pg.wait_for_selector("#gbox h2")
            self.assertEqual(pg.evaluate("location.hash"), "#color")
            self.assertIn("Color correction", pg.inner_text("#gbox h2"))
            pg.click("#subnav [data-sec=local]")
            pg.wait_for_selector("#lcbox [data-lcsavedev]")
            self.assertEqual(pg.locator("#lcbox [data-lcsavedev]").count(), 2)
            pg.click("#subnav [data-sec=backups]")
            pg.wait_for_selector("#bkdev")
            pg.wait_for_selector("#bkbox h2")
            pg.select_option("#bkdev", FRONT)
            for _ in range(100):
                if pg.locator("#bkdev").count() and pg.eval_on_selector("#bkdev", "e => e.value") == FRONT and pg.locator("#bkbox h2").count():
                    break
                time.sleep(0.05)
            self.assertEqual(pg.eval_on_selector("#bkdev", "e => e.value"), FRONT)
            if size["width"] == 390:
                self.assertEqual(pg.evaluate("document.documentElement.scrollWidth"), 390, "fits a phone")
            pg.close()
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
