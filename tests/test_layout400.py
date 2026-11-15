# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""4.0: the new layout. Seven tabs, Alerts and Setup, folding panels, the
phone tab bar, old links, consistent saving and plainer names. The browser
part runs every tab at computer and phone size (skipped where Playwright
isn't installed, such as on the GitHub test machines)."""
import copy
import re
import shutil
import tempfile
import threading
import unittest
from pathlib import Path

from tests import fake_trimlight as F

ROOT = Path(__file__).resolve().parent.parent
JS = (ROOT / "eaveluxos" / "static" / "app.js").read_text(encoding="utf-8")
CSS = (ROOT / "eaveluxos" / "static" / "app.css").read_text(encoding="utf-8")
MANUAL = (ROOT / "MANUAL.md").read_text(encoding="utf-8")

try:
    from playwright.sync_api import sync_playwright
except ImportError:          # pragma: no cover
    sync_playwright = None


def view_src(name):
    a = JS.index(f"VIEWS.{name} = ")
    b = JS.index("\nVIEWS.", a + 10) if "\nVIEWS." in JS[a + 10:] else len(JS)
    return JS[a:b]


class Source(unittest.TestCase):
    def test_seven_tabs(self):
        nav = (ROOT / "eaveluxos" / "static" / "nav.js").read_text(encoding="utf-8")     # 4.0.1: the routing table
        tabs = re.search(r"const TABS = (\[.*?\]);", nav).group(1)
        self.assertEqual(re.findall(r"\['(\w+)','([^']+)'\]", tabs),
                         [("home", "Home"), ("patterns", "Patterns"), ("schedule", "Schedule"), ("alerts", "Alerts"),
                          ("music", "Music"), ("map", "House"), ("setup", "Setup")])
        for v in ("alerts", "access", "app", "create", "lights", "time", "manual"):
            self.assertIn(f"VIEWS.{v} = ", JS)
        self.assertIn("const VIEW_ALIAS = { settings: 'access', setup: null };", nav)
        self.assertIn("= Nav;", JS)

    def test_things_moved_where_they_belong(self):
        sched = JS[JS.index("VIEWS.schedule = "):JS.index("VIEWS.alerts = ")]
        for gone in ('id="wxon"', 'id="secp"', 'id="wxalertbox"', 'id="safetybox"'):
            self.assertNotIn(gone, sched)
        for kept in ("Every night", "Special days", "fold('holidays'", "fold('game'", "fold('away'", "fold('upcoming'"):
            self.assertIn(kept, sched)
        alerts = JS[JS.index("VIEWS.alerts = "):JS.index("async function webhookPanel")]
        for here in ('id="wxon"', 'id="secp"', "wxalertbox", "hookbox", "alertbox"):
            self.assertIn(here, alerts)
        settings = JS[JS.index("VIEWS.settings = "):JS.index("VIEWS.access = ")]
        self.assertNotIn("<h2>Webhooks</h2>", settings)
        self.assertNotIn("alertPanel(", settings)
        self.assertIn("fold('safety', 'Backup timer'", JS)

    def test_consistent_saving_and_plainer_names(self):
        self.assertNotIn("data-savesec", JS)
        self.assertNotIn("data-msavedef", JS)
        self.assertIn("e.target.id === 'secp' || e.target.id === 'secm'", JS)
        self.assertIsNone(re.search(r"[^/*\w]Safety net", JS.replace("the safety net; Setup", "")))
        self.assertNotIn("<h2>Address space</h2>", JS)
        self.assertIn("'Theme: auto'", JS)

    def test_phone_tab_bar_and_folds(self):
        phone = CSS[CSS.index("@media (max-width:760px){\n  .ribbon{position:fixed"):]
        self.assertIn("bottom:0", phone[:300])
        for c in (".fold.closed .foldbody{display:none}", ".cols>*,.stack>*{min-width:0}"):
            self.assertIn(c, CSS)

    def test_manual_matches(self):
        self.assertIn("### Where things are (version 4.0)", MANUAL)
        self.assertIsNone(re.search(r"(?<!System )(?<!Windows )Settings ›", MANUAL), "the app's own Settings tab is gone")
        self.assertNotIn("Lights tab", MANUAL)
        self.assertIn("## 17. Backup timer (safety net)", MANUAL)


@unittest.skipIf(sync_playwright is None, "Playwright isn't installed")
class Browser(unittest.TestCase):
    VIEWS = ["home", "patterns", "schedule", "alerts", "music", "map", "lights", "time", "access", "app", "create"]

    @classmethod
    def setUpClass(cls):
        import eaveluxos.api
        from eaveluxos.server import App, make_server
        cls.cloud = F.start()
        cls._saved = eaveluxos.api.BASE_URL
        eaveluxos.api.BASE_URL = f"http://127.0.0.1:{cls.cloud.server_address[1]}/trimlight"
        cls.dir = Path(tempfile.mkdtemp())
        cls.app = App(cls.dir, start=False)
        s = copy.deepcopy(cls.app.store.settings)
        s["location"].update(latitude=39.95, longitude=-75.16)
        s["setup_done"] = True
        cls.app.store.save_settings(s)
        cls.app.store.save_secrets(client_id=F.CID, client_secret=F.SECRET)
        cls.app.rebuild()
        cls.srv = make_server(cls.app, "127.0.0.1", 0)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}/"
        try:
            cls.pw = sync_playwright().start()
            cls.browser = cls.pw.chromium.launch()
        except Exception as e:        # no browser on this machine
            cls.tearDownClass()
            raise unittest.SkipTest(f"Chromium can't start: {e}")

    @classmethod
    def tearDownClass(cls):
        import eaveluxos.api
        for close in (lambda: cls.browser.close(), lambda: cls.pw.stop()):
            try:
                close()
            except Exception:
                pass
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.app.store.close()
        shutil.rmtree(cls.dir, ignore_errors=True)
        eaveluxos.api.BASE_URL = cls._saved

    def page(self, phone=False):
        ctx = self.browser.new_context(**(self.pw.devices["iPhone 13"] if phone else {"viewport": {"width": 1300, "height": 900}}))
        self.addCleanup(ctx.close)
        pg = ctx.new_page()
        self.errors = []
        pg.on("pageerror", lambda e: self.errors.append(str(e)))
        return pg

    def open(self, pg, view):
        pg.goto(self.base + "#" + view)
        pg.reload()
        pg.wait_for_timeout(1500)

    def test_every_tab_on_a_computer_and_a_phone(self):
        for phone in (False, True):
            pg = self.page(phone)
            for v in self.VIEWS:
                self.open(pg, v)
                tab = pg.evaluate("document.querySelector('#ribbon [aria-current=page]')?.dataset.tab")
                self.assertEqual(tab, {"create": "patterns", "lights": "setup", "time": "setup", "access": "setup",
                                       "app": "setup"}.get(v, v), v)
                if phone:
                    self.assertEqual(pg.evaluate("document.documentElement.scrollWidth"), 390, f"#{v} fits the phone")
            if phone:
                box = pg.locator("#ribbon").bounding_box()
                self.assertGreater(box["y"], 500, "the tabs are at the bottom of a phone screen")
        self.assertEqual(self.errors, [])

    def test_old_links_and_the_manual_button(self):
        pg = self.page()
        self.open(pg, "setup")
        self.assertEqual(pg.evaluate("location.hash"), "#lights", "Setup opens on Lights & controller")
        for old, new in (("settings", "#access"), ("lights", "#lights"), ("time", "#time"), ("create", "#create")):
            self.open(pg, old)
            self.assertEqual(pg.evaluate("location.hash"), new, old)
        self.open(pg, "app")
        self.assertIn("App", pg.inner_text("#subnav [aria-current=page]"))
        pg.click("[data-q=help]")
        pg.wait_for_timeout(800)
        self.assertEqual(pg.evaluate("location.hash"), "#manual")
        self.assertEqual(self.errors, [])

    def test_folds_remember_and_security_flash_saves_as_you_go(self):
        pg = self.page()
        self.open(pg, "alerts")
        self.assertIn("closed", pg.get_attribute("[data-fold=security]", "class"))
        self.assertIn("Security white", pg.inner_text("[data-sum=security]"))
        pg.click("[data-fold=security] .foldbar")
        pg.select_option("#secp", "warm_white")
        pg.wait_for_timeout(800)
        self.assertEqual(self.app.store.settings["security"]["effect"], "warm_white")
        self.open(pg, "alerts")
        self.assertNotIn("closed", pg.get_attribute("[data-fold=security]", "class"), "remembered open")
        pg.select_option("#secp", "security_white")
        pg.wait_for_timeout(800)
        self.assertEqual(self.errors, [])


if __name__ == "__main__":
    unittest.main()
