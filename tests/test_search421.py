# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""4.2.1: the feature search at the top of every page."""
import copy
import json
import re
import shutil
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "eaveluxos" / "static"

try:
    from playwright.sync_api import sync_playwright
except ImportError:             # pragma: no cover
    sync_playwright = None


def node(js):
    r = subprocess.run(["node", "-e", f"const S = require({json.dumps(str(STATIC / 'search.js'))}); {js}"],
                       capture_output=True, text=True, encoding="utf-8", timeout=30)
    if r.returncode:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


class Index(unittest.TestCase):
    """Every entry must point at something that's really there."""
    @classmethod
    def setUpClass(cls):
        # 4.18.2: views and panels in the later page scripts count too
        cls.app = "\n".join((STATIC / f).read_text(encoding="utf-8") for f in ("app.js", "security.js", "triggers.js"))
        cls.index = (STATIC / "index.html").read_text(encoding="utf-8")

    @unittest.skipUnless(shutil.which("node"), "Node.js isn't installed")
    def test_every_entry_points_at_a_real_place(self):
        feats = node("console.log(JSON.stringify(S.FEATURES))")
        self.assertGreater(len(feats), 50)
        views = set(re.findall(r"^VIEWS\.(\w+) = ", self.app, re.M))
        folds = set(re.findall(r"fold\('(\w+)'", self.app))
        for f in feats:
            self.assertIn(f["v"], views, f)
            if "f" in f:
                self.assertIn(f["f"], folds, f)
            if "h" in f:
                self.assertTrue(re.search(r"<(h2|h3|summary)[^>]*>" + re.escape(f["h"]), self.app), f)
        self.assertEqual(len({f["t"] for f in feats}), len(feats), "titles are unique")

    @unittest.skipUnless(shutil.which("node"), "Node.js isn't installed")
    def test_finds_what_people_type(self):
        q = lambda s: node(f"console.log(JSON.stringify(S.find({json.dumps(s)}).map(f => f.t)))")
        self.assertEqual(q("backup")[0], "Backup timer")
        self.assertEqual(q("gam")[0], "Game-day lights")
        self.assertEqual(q("eagles")[0], "Game-day lights")
        self.assertEqual(q("restore")[0], "Pattern backups")
        self.assertEqual(q("PORTS")[0], "Ports and bulbs")
        self.assertEqual(q("web hook")[0], "Webhooks")
        self.assertEqual(q("  "), [])
        self.assertEqual(q("xyzzy"), [])
        self.assertLessEqual(len(q("a")), 8)

    def test_on_every_page(self):
        self.assertIn('id="q"', self.index)
        self.assertLess(self.index.index("search.js"), self.index.index("app.js"))
        self.assertIn("setupSearch()", self.app)


@unittest.skipUnless(sync_playwright, "Playwright isn't installed")
class Browser(unittest.TestCase):
    def test_search_goes_to_the_feature(self):
        import eaveluxos.api
        from eaveluxos.server import App, make_server
        from tests import fake_trimlight as F
        cloud = F.start()
        saved = eaveluxos.api.BASE_URL
        eaveluxos.api.BASE_URL = f"http://127.0.0.1:{cloud.server_address[1]}/trimlight"
        self.addCleanup(setattr, eaveluxos.api, "BASE_URL", saved)
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d, True)
        app = App(d, start=False)
        self.addCleanup(app.store.close)
        s = copy.deepcopy(app.store.settings)
        s["location"].update(latitude=39.95, longitude=-75.16)
        s["setup_done"] = True
        app.store.save_settings(s)
        app.store.save_secrets(client_id=F.CID, client_secret=F.SECRET)
        app.rebuild()
        srv = make_server(app, "127.0.0.1", 0)
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
        for size in ({"width": 1300, "height": 900}, {"width": 390, "height": 844}):
            ctx = br.new_context(viewport=size)
            self.addCleanup(ctx.close)
            pg = ctx.new_page()
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.goto(base + "#home")
            pg.wait_for_selector("#q", state="visible")
            # A closed panel on another page: opened, outlined.
            pg.fill("#q", "backup")
            pg.wait_for_selector("#qres button")
            self.assertIn("Backup timer", pg.inner_text("#qres button[aria-selected=true]"))
            pg.press("#q", "Enter")
            pg.wait_for_selector('[data-fold="safety"].found')
            self.assertTrue(pg.url.endswith("#lights"))
            self.assertFalse(pg.eval_on_selector('[data-fold="safety"]', "e => e.classList.contains('closed')"))
            self.assertTrue(pg.is_hidden("#qres"))
            self.assertEqual(pg.input_value("#q"), "")
            # 4.5.1: typing again right after picking one keeps the new results
            # (a close left over from picking used to hide them).
            pg.fill("#q", "backup")
            pg.wait_for_selector("#qres button")
            pg.press("#q", "Enter")
            pg.fill("#q", "sun")
            pg.wait_for_timeout(400)
            self.assertTrue(pg.is_visible("#qres"), "the new results stay open")
            pg.fill("#q", "")
            # Arrow keys, and a heading rather than a panel.
            pg.fill("#q", "sun")
            pg.wait_for_selector("#qres button")
            titles = pg.eval_on_selector_all("#qres button span", "b => b.map(x => x.textContent)")
            pg.press("#q", "ArrowDown")
            pg.press("#q", "Enter")
            pg.wait_for_selector(".found")
            self.assertIn(titles[1], pg.inner_text(".found"))
            # / jumps to the box; Escape empties it.
            pg.evaluate("document.activeElement && document.activeElement.blur()")   # not in a field
            pg.keyboard.press("/")
            self.assertEqual(pg.evaluate("document.activeElement.id"), "q")
            pg.keyboard.type("zzzz")
            self.assertIn("No feature matches", pg.inner_text("#qres"))
            pg.keyboard.press("Escape")
            self.assertEqual(pg.input_value("#q"), "")
            if size["width"] == 390:
                self.assertEqual(pg.evaluate("document.documentElement.scrollWidth"), 390, "fits a phone")
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
