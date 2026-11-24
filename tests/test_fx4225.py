# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""4.22.5: Lightning and Snowflake badges on Patterns › In the Trimlight app
and My patterns."""
import threading
import time
import unittest
from pathlib import Path

from eaveluxos import lanlink as L
from eaveluxos.schedule import Effect
from tests.test_local43 import ServerBase
from tests.test_local44 import DEV, FALL

HERE = Path(__file__).resolve().parent
REC = [(4, (0xFF, 0x63, 0x00), True), (2, (0x56, 0x10, 0x03), True)]


class Fx(ServerBase):
    def setUp(self):
        super().setUp()
        self.app.local_commands(True)
        self.app.ctrl.devices = [{"deviceId": DEV, "name": "Trimlight"}]
        self.ctl.holds["patterns"][20] = L.pattern_record(20, "Test Lightning", 0, 128, 139, REC)
        self.ctl.holds["patterns"][22] = L.pattern_record(22, "Test w/o lightning", 0, 128, 139, REC)
        self.ctl.holds["effects"] = [(0, 20), (1, 3)]
        self.app.ctrl.cfg.effects = {
            "copy_l": Effect("copy_l", "Test Lightning", "custom", payload=dict(FALL), colors=[]),
            "copy_plain": Effect("copy_plain", "Test w/o lightning", "custom", payload=dict(FALL), colors=[]),
            "by_name": Effect("by_name", "Third", "saved", saved_name=next(
                p["name"] for p in self.app.local_state(fresh=True)["patterns"] if p["id"] == 3).upper()),
            "other": Effect("other", "Mine", "custom", payload={**FALL, "speed": 50}, colors=[]),
            "builtin": Effect("builtin", "Rainbow", "builtin", payload={"category": 0, "mode": 3}),
        }

    def test_1_badges(self):
        r = self.app.patterns_fx()
        self.assertTrue(r["known"])
        self.assertEqual(r["by_id"], {"20": "lightning", "3": "snowflake"})
        self.assertEqual(r["mine"].get("copy_l"), "lightning")
        self.assertNotIn("copy_plain", r["mine"], "its look-alike without Lightning is the one shown")
        self.assertNotIn("other", r["mine"], "changed speed: shown live, no effect")
        self.assertNotIn("builtin", r["mine"])
        self.assertEqual(r["mine"].get("by_name"), "snowflake", "saved by name, any case")
        self.assertTrue(r["plays"])

    def test_nothing_without_the_home_network(self):
        self.ctl.holds["effects"] = None
        self.app._local_seen = (0, None, None)
        self.assertEqual(self.app.patterns_fx()["mine"], {})
        self.assertFalse(self.app.patterns_fx()["known"])

    def test_1_the_standalone_repro(self):
        import subprocess
        import sys
        script = str(HERE / "repro_min_card_hides_effect.py")
        self.assertIn("BUG:", subprocess.run([sys.executable, script], capture_output=True, text=True, timeout=60).stdout)
        self.assertIn("OK:", subprocess.run([sys.executable, script, "--fixed"], capture_output=True, text=True, timeout=60).stdout)

    def test_route_and_page(self):
        src = (HERE.parent / "eaveluxos" / "server.py").read_text(encoding="utf-8")
        self.assertIn('if path == "/api/patterns/fx"', src)
        js = (HERE.parent / "eaveluxos" / "static" / "app.js").read_text(encoding="utf-8")
        for s in ("data-fxk=", "data-fxid=", "_fx: p.extra", "function fxBadge"):
            self.assertIn(s, js)


try:
    from playwright.sync_api import sync_playwright
except ImportError:            # pragma: no cover
    sync_playwright = None


@unittest.skipIf(sync_playwright is None, "Playwright isn't installed")
class Browser(ServerBase):
    def test_in_the_trimlight_app(self):
        from eaveluxos.server import make_server
        self.ctl.holds["effects"] = [(0, 2), (1, 4)]
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
        pg = br.new_page(viewport={"width": 390, "height": 900})
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(f"http://localhost:{srv.server_address[1]}/#patterns")
        pg.wait_for_selector("[data-ptab=controller]", timeout=20000)
        pg.click("[data-ptab=controller]")
        pg.wait_for_selector(".fxbadge", timeout=20000)
        badges = pg.eval_on_selector_all(".cards .card", "cs => cs.map(c => [c.querySelector('b').textContent, (c.querySelector('.fxbadge') || {}).textContent || ''])")
        got = [b for _, b in badges if b]
        self.assertEqual(len(got), 2, badges)
        self.assertTrue(any("Lightning" in b for b in got) and any("Snowflake" in b for b in got), badges)
        self.assertLessEqual(pg.evaluate("document.documentElement.scrollWidth"), 390)
        self.assertEqual(errs, [])


if __name__ == "__main__":
    unittest.main()
