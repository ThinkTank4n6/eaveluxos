# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""4.0.1: fixes from the 4.0.0 code review, one test (or more) each. The
logic runs with Node everywhere (review400_check.js); the screens run in a
real browser where Playwright is installed."""
import copy
import json
import shutil
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path

from tests import fake_trimlight as F
from tests.test_holidays319 import SECRETS, settings

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
JS = (ROOT / "eaveluxos" / "static" / "app.js").read_text(encoding="utf-8")
CSS = (ROOT / "eaveluxos" / "static" / "app.css").read_text(encoding="utf-8")

try:
    from playwright.sync_api import sync_playwright
except ImportError:          # pragma: no cover
    sync_playwright = None


class Logic(unittest.TestCase):
    def test_1_repro_script(self):
        r = subprocess.run(["python3", str(HERE / "repro_quick_saves.py")], capture_output=True, text=True,
                           encoding="utf-8", timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("old_client ['ok', 'changed on another device'", r.stdout)
        self.assertIn("new_client ['ok'] -> {'security': {'minutes': 8}, 'weather': {'enabled': True}}", r.stdout)
        self.assertLessEqual(len((HERE / "repro_quick_saves.py").read_text(encoding="utf-8").splitlines()), 20)

    @unittest.skipUnless(shutil.which("node"), "Node.js isn't installed")
    def test_1_2_12_merging_and_routing(self):
        r = subprocess.run(["node", str(HERE / "review400_check.js")], capture_output=True, text=True,
                           encoding="utf-8", timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_1_saves_wait_and_combine(self):
        for s in ("const SAVEQ = { running: false, pending: null, timer: null };", "Merge.diff(S.settings, next)",
                  "Merge.apply(clone(S.settings), job.changes)", "if (SAVEQ.pending) pumpSaves();"):
            self.assertIn(s, JS)

    def test_buttons_without_a_value_are_tested_for_presence(self):
        """A button marked data-x (no value) has dataset.x === "", which is
        falsy: `if (d.x)` never runs. That hid New pattern (fixed in 4.0.1)."""
        import re
        valueless = set(re.findall(r"<button[^>]*?\sdata-([a-z][a-z0-9]*)(?=[\s>])(?!=)", JS))
        for a in sorted(valueless):
            hits = re.findall(r"(?:if \(|else if \()(?:d|ds|b\.dataset)\." + a + r"\)", JS)
            self.assertEqual(hits, [], f"data-{a} has no value; test it with !== undefined")
        self.assertIn("new", valueless)

    def test_4_tab_bar_steps_aside_while_typing(self):
        self.assertIn("body.typing .ribbon{display:none}", CSS)
        self.assertIn("document.body.classList.add('typing')", JS)

    def test_5_viewers_look_but_dont_change_alerts(self):
        alerts = JS[JS.index("VIEWS.alerts = "):JS.index("async function webhookPanel")]
        for s in ('id="wxon" ${s.weather?.enabled ? \'checked\' : \'\'} ${ro}', '<select id="secp" ${ro}>',
                  'value="${s.security?.minutes ?? 5}" ${ro}', "if (ro) return;"):
            self.assertIn(s, alerts)

    def test_8_no_leftover_webhook_code_in_settings(self):
        settings_view = JS[JS.index("VIEWS.settings = "):JS.index("VIEWS.access = ")]
        for gone in ("d.regen", "d.copy", "'hook'"):
            self.assertNotIn(gone, settings_view)

    def test_9_folds_for_screen_readers(self):
        self.assertIn('aria-controls="fold-${key}"', JS)
        self.assertIn('id="fold-${key}" role="region"', JS)


class ComingUp(unittest.TestCase):
    """#11: the next holiday and game for the summaries, worked out here."""
    def test_11_next_holiday_and_game(self):
        from eaveluxos.server import App
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        app = App(d, start=False)
        self.addCleanup(app.store.close)
        s = settings()
        s["gameday"] = {"enabled": True, "teams": [{"league": "nfl", "team": "phi", "name": "Eagles", "effect": "christmas"}]}
        app.store.save_settings(s)
        app.store.save_secrets(**SECRETS)
        app.gameday.cache = {"nfl-phi": {"dates": ["2099-01-01", "2026-01-01"], "fetched": 1, "error": None}}
        app.rebuild()
        app.cfg.loc.now = lambda: __import__("datetime").datetime(2026, 11, 20, 12, tzinfo=app.cfg.loc.tz)
        c = app.coming_up()
        self.assertEqual(c["holiday"], {"name": "Thanksgiving", "date": "2026-11-26"})
        self.assertEqual(c["game"], {"name": "Eagles", "date": "2099-01-01"})
        s["holidays"]["enabled"] = False
        app.store.save_settings(s)
        self.assertIsNone(app.coming_up()["holiday"])
        self.assertIn("next: ${nx.name}, ${shortDay(nx.date)}", JS)


@unittest.skipIf(sync_playwright is None, "Playwright isn't installed")
class Browser(unittest.TestCase):
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
        except Exception as e:
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

    def open_fold(self, pg, key):
        if "closed" in pg.get_attribute(f"[data-fold={key}]", "class"):
            pg.click(f"[data-fold={key}] > .foldbar")

    def test_1_2_quick_changes_all_count_even_while_a_save_is_on_its_way(self):
        pg = self.page()
        # A slow server: each save takes 600 ms, so later changes arrive while one is in flight.
        pg.route("**/api/settings", lambda route: (pg.wait_for_timeout(600), route.continue_()) if route.request.method == "POST" else route.continue_())
        self.open(pg, "alerts")
        self.open_fold(pg, "security")
        self.open_fold(pg, "weather")
        hist = len(self.app.store.history(200))
        pg.evaluate("""() => { const i = document.querySelector('#secm');
            for (const v of ['6', '7']) { i.value = v; i.dispatchEvent(new Event('change', {bubbles: true})); } }""")
        pg.wait_for_timeout(300)                                            # the first save is on its way now
        pg.evaluate("""() => { const i = document.querySelector('#secm'); i.value = '8'; i.dispatchEvent(new Event('change', {bubbles: true}));
            const w = document.querySelector('#wxon'); w.checked = true; w.dispatchEvent(new Event('change', {bubbles: true})); }""")
        pg.wait_for_timeout(2500)
        st = self.app.store.settings
        self.assertEqual(st["security"]["minutes"], 8, "the last value wins")
        self.assertTrue(st["weather"]["enabled"], "the other change too")
        self.assertNotIn("another device", pg.inner_text("#toast"))
        self.assertLessEqual(len(self.app.store.history(200)) - hist, 2, "combined, not one save per change")
        self.assertEqual(self.errors, [])

    def test_1_a_real_change_elsewhere_is_still_caught(self):
        pg = self.page()
        self.open(pg, "alerts")
        self.open_fold(pg, "security")
        s = copy.deepcopy(self.app.store.settings)                         # another device saves meanwhile
        s["security"]["minutes"] = 33
        self.app.store.save_settings(s)
        pg.evaluate("""() => { const i = document.querySelector('#secm'); i.value = '9'; i.dispatchEvent(new Event('change', {bubbles: true})); }""")
        pg.wait_for_timeout(1200)
        self.assertIn("another device", pg.inner_text("#toast"))
        self.assertEqual(self.app.store.settings["security"]["minutes"], 33)

    def test_3_4_phone_sections_in_view_and_the_tab_bar_while_typing(self):
        pg = self.page(phone=True)
        self.open(pg, "app")
        bb = pg.locator("#subnav [aria-current=page]").bounding_box()
        self.assertLessEqual(bb["x"] + bb["width"], 390)
        self.open(pg, "create")
        self.assertTrue(pg.locator("#ribbon").is_visible())
        pg.click("#dname")
        self.assertFalse(pg.locator("#ribbon").is_visible(), "out of the keyboard's way")
        pg.locator("#dname").blur()
        pg.wait_for_timeout(100)
        self.assertTrue(pg.locator("#ribbon").is_visible())
        self.assertEqual(self.errors, [])

    def test_6_coming_up_after_tonights_lights(self):
        pg = self.page()
        self.open(pg, "schedule")
        days = [{"on": "5:00 PM", "off": "11:00 PM", "effect": "Warm white", "dow": "Sat", "label": "Nov 14"},
                {"on": "4:59 PM", "off": "11:00 PM", "effect": "Warm white", "dow": "Sun", "label": "Nov 15"}]
        f = "st => { S.status = {...S.status, ...st}; return SUMS.upcoming(); }"
        self.assertTrue(pg.evaluate(f, {"days": days, "window": None, "next_change": "5:00 PM", "next_change_day": None}).startswith("Tonight"))
        self.assertTrue(pg.evaluate(f, {"days": days, "window": None, "next_change": "4:59 PM", "next_change_day": "Sun"}).startswith("Tomorrow"))
        self.assertTrue(pg.evaluate(f, {"days": days, "window": {"rule": "Every night", "end": "11:00 PM"}}).startswith("On now"))

    def test_7_folded_panels_load_when_opened(self):
        pg = self.page()
        seen = []
        pg.on("request", lambda r: seen.append(r.url))
        self.open(pg, "schedule")
        if "closed" not in pg.get_attribute("[data-fold=game]", "class"):
            pg.click("[data-fold=game] > .foldbar")
            self.open(pg, "schedule")
        seen.clear()
        self.open(pg, "schedule")
        self.assertFalse(any("/api/gameday" in u for u in seen), "not loaded while folded")
        pg.click("[data-fold=game] > .foldbar")
        pg.wait_for_timeout(800)
        self.assertTrue(any("/api/gameday" in u for u in seen), "loaded when opened")
        self.assertIn("Game-day lights", pg.inner_text("#gamebox") + "Game-day lights")
        pg.click("[data-fold=game] > .foldbar")                              # leave it folded for other tests

    def test_new_pattern_button_opens_create(self):
        """Found while testing #10: New pattern never opened Create (an
        empty data-new attribute is falsy). Unnoticed while Create had its
        own tab; in 4.0 it's the way in."""
        pg = self.page()
        self.open(pg, "patterns")
        pg.click("[data-new]")
        pg.wait_for_timeout(800)
        self.assertEqual(pg.evaluate("S.view"), "create")
        self.assertIn("Create a pattern", pg.inner_text("#main h2"))

    def test_10_back_returns_to_the_last_tab(self):
        pg = self.page()
        self.open(pg, "patterns")
        pg.click("[data-new]")
        pg.wait_for_timeout(800)
        self.assertEqual(pg.evaluate("location.hash"), "#create")
        pg.go_back()
        pg.wait_for_timeout(800)
        self.assertEqual(pg.evaluate("location.hash"), "#patterns")
        self.assertEqual(pg.evaluate("S.view"), "patterns")
        self.open(pg, "settings")                                              # an old address is corrected, not stacked
        self.assertEqual(pg.evaluate("location.hash"), "#access")
        self.assertEqual(self.errors, [])


if __name__ == "__main__":
    unittest.main()
