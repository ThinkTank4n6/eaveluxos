# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""4.7.1: Patterns › In the Trimlight app shows any controller's library
(read over the home network when it has an address), built-in effects saved
on a controller are read as built-in effects, and Home marks the controllers
this app runs as Active and greys out the others on the account. Here the
Deck (run by this app) is 127.0.0.1 and the Front (not run) 127.0.0.2."""
import copy
import threading
import time
import unittest

from eaveluxos import lanlink as L
from eaveluxos import localmode
from tests.test_multi45 import DECK, FRONT, TwoBase

try:
    from playwright.sync_api import sync_playwright
except ImportError:            # pragma: no cover
    sync_playwright = None


def builtin_record(pid, name, effect, speed=120, brightness=200, reverse=False) -> bytes:
    """A built-in effect saved on a controller, laid out as the Trimlight app
    saves one (Nov 17, 2026 capture): [26]=1, [27]=0, speed, brightness,
    effect number, direction."""
    r = bytearray(L.pattern_record(pid, name, 0, 0, 0, []))
    r[26:32] = bytes([1, 0, speed, brightness, effect, int(reverse)])
    return bytes(r)


class Records(unittest.TestCase):
    def test_builtin_record_is_read_as_one(self):
        p = L.read_record(builtin_record(4, "Rainbow Chase", 17, 90, 180, True))
        self.assertEqual((p["kind"], p["effect"], p["reverse"], p["speed"], p["brightness"]), (1, 17, True, 90, 180))
        e = localmode.cloud_effect(p)
        self.assertEqual(e, {"name": "Rainbow Chase", "speed": 90, "brightness": 180, "category": 0, "mode": 17,
                             "reverse": True, "pixelLen": 30})

    def test_own_colors_keep_their_off_gaps(self):
        rec = L.pattern_record(2, "Gaps", 3, 100, 255, [(4, (255, 0, 0), 1), (2, (0, 0, 0), 0), (4, (0, 255, 0), 1)])
        p = L.read_record(rec)
        self.assertEqual(p["kind"], 2)
        e = localmode.cloud_effect(p)
        self.assertEqual(e["category"], 1)
        self.assertEqual([(x["count"], x["disable"]) for x in e["pixels"]], [(4, False), (2, True), (4, False)])
        self.assertEqual(len(localmode.cloud_effect(p, every_slot=True)["pixels"]), L.SLOTS)

    def test_a_backup_calls_a_builtin_a_builtin(self):
        """Before 4.7.1 a backup called it a pattern of its own colors; put
        back, it would have been written as one (wrong colors)."""
        st = {"ports": [], "patterns": [L.read_record(builtin_record(1, "Fire", 5))]}
        self.assertEqual(localmode.as_backup(st)["effects"][0]["category"], 0)

    def test_two_builtins_dont_look_the_same(self):
        a, b = (L.read_record(builtin_record(1, "A", 5)), L.read_record(builtin_record(2, "B", 6)))
        self.assertNotEqual(localmode._look(a), localmode._look(b))


class Server(TwoBase):
    def setUp(self):
        super().setUp()
        self.front.holds["patterns"][2] = builtin_record(2, "Christmas", 31, 100, 220)
        self.app.local_address(DECK, "127.0.0.1")
        self.app.local_address(FRONT, "127.0.0.2")
        s = copy.deepcopy(self.app.store.settings)
        s["service"] = {**s["service"], "devices": [DECK]}         # this app runs the Deck only
        self.app.store.save_settings(s)
        self.app.rebuild()

    def test_each_library_in_the_cloud_layout(self):
        front = self.app.local_state(dev=FRONT)
        by = {p["name"]: p["effect"] for p in front["patterns"]}
        self.assertEqual(by["Front Porch"]["category"], 1)
        self.assertEqual(by["Front Porch"]["pixels"][0]["color"], 0xFFB46B)
        self.assertEqual((by["Christmas"]["category"], by["Christmas"]["mode"]), (0, 31))

    def test_status_names_the_account_and_who_runs(self):
        st = self.status()
        self.assertEqual(sorted(d["id"] for d in st["account"]), sorted([DECK, FRONT]))
        self.assertEqual(st["controlled"], [DECK])

    def status(self):
        from eaveluxos.server import make_server
        import json
        import urllib.request
        srv = make_server(self.app, "127.0.0.1", 0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        req = urllib.request.Request(f"http://127.0.0.1:{srv.server_address[1]}/api/status",
                                     headers={"X-Requested-With": "eaveluxos"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())


@unittest.skipIf(sync_playwright is None, "Playwright isn't installed")
class Browser(Server):
    SHOTS = None             # a folder to save screenshots in, when looking at them by hand

    def test_home_and_the_trimlight_app_tab(self):
        from eaveluxos.server import make_server
        srv = make_server(self.app, "127.0.0.1", 0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        base = f"http://localhost:{srv.server_address[1]}/"
        # The Deck already has a "Christmas" of this app's own.
        s = copy.deepcopy(self.app.store.settings)
        s["effects"] = {**s.get("effects", {}), "christmas": {"label": "Christmas", "colors": ["#FF0000", "#00FF00"], "counts": [3, 3]}}
        self.app.store.save_settings(s)
        try:
            pw = sync_playwright().start()
            br = pw.chromium.launch()
        except Exception as e:
            self.skipTest(f"Chromium can't start: {e}")
        self.addCleanup(pw.stop)
        self.addCleanup(br.close)
        errors = []

        def until(cond, what):
            for _ in range(160):
                if cond():
                    return
                time.sleep(0.05)
            self.fail(f"never: {what}: " + (pg.inner_text("#pbody") if "pbody" in what or "library" in what else ""))
        for size in ({"width": 1300, "height": 900}, {"width": 390, "height": 844}):
            ctx = br.new_context(viewport=size)
            self.addCleanup(ctx.close)
            pg = ctx.new_page()
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.goto(base + "#home")
            pg.wait_for_selector(".ctlcards .item")
            until(lambda: pg.locator(".ctlcards .item").count() == 2, "both controllers")
            self.assertIn("Deck", pg.inner_text(".ctlcards .item.active"))
            self.assertIn("Active", pg.inner_text(".ctlcards .item.active"))
            self.assertIn("Front", pg.inner_text(".ctlcards .item.idle"))
            self.assertIn("Not run by this app", pg.inner_text(".ctlcards .item.idle"))
            self.assertLess(float(pg.eval_on_selector(".ctlcards .item.idle", "e => getComputedStyle(e).opacity")), 1)
            if size["width"] == 390:
                self.assertEqual(pg.evaluate("document.documentElement.scrollWidth"), 390, "fits a phone")
            if self.SHOTS:
                pg.screenshot(path=f"{self.SHOTS}/home-{size['width']}.png", full_page=True)
            pg.goto(base + "#patterns")
            pg.click('[data-ptab="controller"]')
            pg.wait_for_selector("#ptdev")
            pg.select_option("#ptdev", FRONT)
            until(lambda: "over your home network" in pg.inner_text("#pbody") and pg.locator("#pbody .card").count() == 2,
                  "the Front's library, read over the home network")
            text = pg.inner_text("#pbody")
            self.assertIn("Front Porch", text)
            self.assertIn("not on Front", text)
            if self.SHOTS:
                pg.screenshot(path=f"{self.SHOTS}/library-{size['width']}.png", full_page=True)
            if size["width"] == 390:
                self.assertEqual(pg.evaluate("document.documentElement.scrollWidth"), 390, "fits a phone")
                continue
            card = pg.locator("#pbody .card", has_text="Christmas")
            card.locator("[data-cadd]").click()
            until(lambda: any(e.get("label") == "Christmas (Front)" for e in self.app.store.settings["effects"].values()),
                  "added as Christmas (Front)")
            added = next(e for e in self.app.store.settings["effects"].values() if e.get("label") == "Christmas (Front)")
            self.assertEqual((added.get("builtin"), added.get("speed"), added.get("brightness")), (31, 100, 220))
            card = pg.locator("#pbody .card", has_text="Front Porch")
            card.locator("[data-cadd]").click()
            until(lambda: any(e.get("label") == "Front Porch" for e in self.app.store.settings["effects"].values()),
                  "no conflict, no suffix")
            pg.select_option("#ptdev", DECK)
            until(lambda: "Deck" in pg.inner_text("#pbody") and "Front Porch" not in pg.inner_text("#pbody"), "the Deck's")
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
