# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""4.14: EaveLuxOS as an app on a phone's home screen (a Progressive Web App).

- The manifest: a maskable icon, Quick as the start screen, and shortcuts on
  the icon (Lights on, Lights off, Back to the schedule, Security flash).
- A service worker keeps the app's own files on the device (https:// or this
  computer), never anything from /api/, and says plainly when the app
  computer can't be reached.
- Quick: big buttons the household chooses, with brightness.
- An install button where the browser offers one."""
import copy
import json
import re
import struct
import threading
import time
import unittest
from pathlib import Path

from eaveluxos.server import ApiError
from tests.test_multi45 import TwoBase

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "eaveluxos" / "static"

try:
    from playwright.sync_api import sync_playwright
except ImportError:            # pragma: no cover
    sync_playwright = None


def png_size(p: Path):
    b = p.read_bytes()
    assert b[:8] == b"\x89PNG\r\n\x1a\n", p
    return struct.unpack(">II", b[16:24])


class Manifest(unittest.TestCase):
    def setUp(self):
        self.m = json.loads((STATIC / "manifest.webmanifest").read_text(encoding="utf-8"))

    def test_installable(self):
        m = self.m
        self.assertEqual((m["display"], m["scope"], m["start_url"]), ("standalone", "./", "./?app=1#quick"))
        sizes = {(i["sizes"], i.get("purpose", "any")) for i in m["icons"]}
        self.assertIn(("512x512", "maskable"), sizes)
        self.assertIn(("192x192", "any"), sizes)
        for i in m["icons"]:
            f = STATIC / i["src"]
            self.assertTrue(f.is_file(), i)
            if i["sizes"] != "any":
                self.assertEqual("%dx%d" % png_size(f), i["sizes"])

    def test_shortcuts(self):
        sc = self.m["shortcuts"]
        self.assertEqual([re.search(r"do=(\w+)", s["url"]).group(1) for s in sc], ["on", "off", "resume", "flash"])
        for s in sc:
            self.assertTrue(s["url"].startswith("./"), "inside the app's scope")
            self.assertEqual(png_size(STATIC / s["icons"][0]["src"]), (96, 96))


class Worker(unittest.TestCase):
    def test_keeps_every_file_the_page_loads_and_never_the_api(self):
        sw = (STATIC / "sw.js").read_text(encoding="utf-8")
        files = json.loads("[" + re.search(r"const FILES = \[(.*?)\];", sw, re.S).group(1).replace("'", '"') + "]")
        for f in files:
            if f != "./":
                self.assertTrue((STATIC / f).is_file(), f)
        page = (STATIC / "index.html").read_text(encoding="utf-8")
        for f in re.findall(r'(?:src|href)="([^":]+\.(?:js|css|svg|png|webmanifest))"', page):
            self.assertIn(f, files, f"{f} is loaded by the page, so it must be kept for offline")
        self.assertIn("url.pathname.includes('/api/')) return;", sw)
        self.assertIn("'eaveluxos-' + VERSION", sw)


class Review(unittest.TestCase):
    def test_1_a_link_asks_first(self):
        from tests import reprorun
        reprorun.run(self, "repro_link_acts.py", 120)

    def test_2_files_come_fresh_first(self):
        sw = (STATIC / "sw.js").read_text(encoding="utf-8")
        self.assertIn("fetch(req).then(r => { clearTimeout(t);", sw)
        self.assertNotIn("if (hit) { fresh.catch", sw)


class Settings(TwoBase):
    def test_quick_buttons_are_checked(self):
        s = copy.deepcopy(self.app.store.settings)
        s["quick"] = [{"type": "off"}, {"type": "pattern", "key": "warm_white"}, {"type": "auto", "id": "a1"}]
        self.app.save_settings(s)
        for bad in ([{"type": "reboot"}], [{"type": "pattern"}], [{"type": "off", "extra": 1}], [{"type": "on"}] * 13, "x"):
            s2 = copy.deepcopy(self.app.store.settings)
            s2["quick"] = bad
            with self.subTest(bad=bad), self.assertRaises(ApiError):
                self.app.save_settings(s2)


@unittest.skipIf(sync_playwright is None, "Playwright isn't installed")
class Browser(TwoBase):
    SHOTS = None

    def test_phone(self):
        from eaveluxos.server import make_server
        from eaveluxos.version import VERSION
        s = copy.deepcopy(self.app.store.settings)
        s["effects"]["porch"] = {"label": "Porch scene", "colors": ["#FFC58A", "off"], "counts": [3, 30], "scene": {"groups": [{"color": "#FFC58A", "level": 100, "bulbs": [1, 2, 3]}]}}
        s["favorites"] = ["warm_white"]
        self.app.save_settings(s)
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

        def until(cond, what, n=200):
            for _ in range(n):
                if cond():
                    return
                time.sleep(0.05)
            self.fail(f"never: {what}")
        ctx = br.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True, device_scale_factor=2)
        self.addCleanup(ctx.close)
        # As opened from the home-screen icon: the installed app (display-mode: standalone)
        ctx.add_init_script("""const mm = window.matchMedia.bind(window); window.matchMedia = q => q.includes('display-mode: standalone')
            ? { matches: !!window.__app, media: q, addEventListener() {}, removeEventListener() {} } : mm(q);
            window.__app = new URLSearchParams(location.search).has('app') || sessionStorage.getItem('app') === '1';
            if (window.__app) sessionStorage.setItem('app', '1');""")
        pg = ctx.new_page()
        pg.on("pageerror", lambda e: errors.append(str(e)))
        # The home-screen icon's address, with the Lights off shortcut
        pg.goto(base + "?app=1&do=off#quick")
        pg.wait_for_selector(".qtile")
        until(lambda: self.app.ctrl.override is not None and self.app.ctrl.override["on"] is False, "the shortcut turned the lights off")
        self.assertEqual(pg.evaluate("location.search"), "", "the shortcut runs once")
        names = pg.locator(".qtile b").all_inner_texts()
        self.assertEqual(names[:3], ["Lights on", "Lights off", "Back to the schedule"])
        self.assertIn("Porch scene", names, "scenes are there until the household chooses")
        self.assertEqual(pg.evaluate("document.documentElement.scrollWidth"), 390, "fits a phone")
        self.assertEqual(pg.locator("#installbar").count(), 0, "not in the installed app")
        if self.SHOTS:
            pg.screenshot(path=f"{self.SHOTS}/quick.png")
        # In the phone's browser: an offer to put it on the home screen, and a link asks before acting
        br2 = br.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
        self.addCleanup(br2.close)
        p2 = br2.new_page()
        p2.on("pageerror", lambda e: errors.append(str(e)))
        self.app.ctrl.resume()
        p2.goto(base + "?do=off#home")
        p2.wait_for_selector("#installbar")
        p2.wait_for_selector("#dlg[open]")
        self.assertIn("Lights off?", p2.inner_text("#dlg"))
        self.assertIsNone(self.app.ctrl.override, "nothing until asked")
        p2.click("#dlg button.primary")
        until(lambda: (self.app.ctrl.override or {}).get("on") is False, "after Yes")
        p2.click("#installbar [data-insthide]")
        self.assertEqual(p2.locator("#installbar").count(), 0)
        # A tile
        pg.locator(".qtile", has_text="Porch scene").click()
        until(lambda: (self.app.ctrl.override or {}).get("effect") == "porch", "the scene is on")
        # Choose the buttons
        pg.click("[data-qedit]")
        pg.wait_for_selector("#dlg [data-qlist]")
        for _ in range(pg.locator("#dlg [data-qdel]").count()):
            pg.locator("#dlg [data-qdel]").first.click()
        pg.select_option("#dlg select[name=add]", "p:porch")
        pg.click("#dlg [data-qadd]")
        pg.select_option("#dlg select[name=add]", "flash")
        pg.click("#dlg [data-qadd]")
        pg.locator("#dlg .primary").last.click()
        until(lambda: self.app.store.settings.get("quick") == [{"type": "pattern", "key": "porch"}, {"type": "flash"}], "saved")
        until(lambda: pg.locator(".qtile").count() == 2, "Quick shows them")
        # Brightness
        pg.wait_for_selector("#qbright")
        pg.eval_on_selector("#qbright", "e => { e.value = 100; e.dispatchEvent(new Event('input', {bubbles: true})); }")
        until(lambda: self.app.ctrl.status()["levels"]["brightness"] == 100, "brightness")
        # Kept on the device: the service worker (this computer counts as secure)
        until(lambda: pg.evaluate("!!navigator.serviceWorker.controller") or (pg.reload() and False), "the service worker", n=60)
        keys = pg.evaluate("caches.keys()")
        self.assertEqual(keys, [f"eaveluxos-{VERSION}"])
        kept = pg.evaluate("caches.open(%s).then(c => c.keys()).then(r => r.map(x => x.url))" % json.dumps(keys[0]))
        self.assertTrue(any(u.endswith("/app.js") for u in kept))
        self.assertFalse(any("/api/" in u for u in kept), "nothing from the app computer's data")
        # Away from home: the app opens and says so
        ctx.set_offline(True)
        pg.goto(base + "?app=1#quick")
        pg.wait_for_selector("text=Can’t reach EaveLuxOS")
        self.assertIn("home Wi-Fi", pg.inner_text("body"))
        pg.click("[data-retry]")           # the button works (no inline handler, which the security policy blocks)
        pg.wait_for_selector("[data-retry]")
        if self.SHOTS:
            pg.screenshot(path=f"{self.SHOTS}/away.png")
        ctx.set_offline(False)
        # Setup › App: On your phone
        pg.goto(base + "#app")
        pg.wait_for_selector("#pwabox h2")
        self.assertIn("app’s files are kept on this device", pg.inner_text("#pwabox"))
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
