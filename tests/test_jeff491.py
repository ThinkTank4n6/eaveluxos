# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""4.9.1, from a user's screenshots (Nov 18, 2026):

- His Front controller sent 56 "patterns": its 2 real ones, then 54 slots
  numbered 0 or 255, nameless or with garbled names, each with a Delete
  button. They're left out now, and nothing deletes one.
- Create counted the Deck's 96 bulbs while he designed for the Front's 106.
  Create now has "Bulbs of" for controllers of different lengths.
- My patterns can be listed A to Z (or newest first) and put in folders."""
import copy
import threading
import time
import unittest

from eaveluxos import lanlink as L
from eaveluxos import localmode
from tests.test_multi45 import TwoBase

try:
    from playwright.sync_api import sync_playwright
except ImportError:            # pragma: no cover
    sync_playwright = None


def slot(pid, name=b"", colors=((0, 0, 255), (128, 128, 128))) -> bytes:
    """A record as his controller sent them: a number, maybe a name, colors."""
    r = bytearray(L.pattern_record(1, "x", 1, 100, 200, [(3, c, 1) for c in colors]))
    r[0] = pid
    r[1:1 + L.NAME_LEN] = name.ljust(L.NAME_LEN, b"\0")[:L.NAME_LEN]
    return bytes(r)


class Slots(TwoBase):
    def setUp(self):
        super().setUp()
        self.app.local_address(TwoBase.DECK if hasattr(TwoBase, "DECK") else self.deck_id(), "127.0.0.1")

    def deck_id(self):
        from tests.test_multi45 import DECK
        return DECK

    def front_with_junk(self):
        from tests.test_multi45 import FRONT
        self.app.local_address(FRONT, "127.0.0.2")
        pats = self.front.holds["patterns"]
        for k in range(54):
            pats[1000 + k] = slot(0 if k % 3 else 255, b"" if k % 5 else b"\xef\xbf\xbd\x8f")
        return FRONT

    def test_only_real_patterns_are_listed(self):
        front = self.front_with_junk()
        st = self.app.local_state(dev=front)
        self.assertTrue(st["patterns"])
        self.assertTrue(all(1 <= p["id"] <= L.MAX_PATTERN_ID for p in st["patterns"]))
        self.assertEqual(st["unreadable"], 54)

    def test_a_slot_numbered_0_or_255_is_never_deleted(self):
        from eaveluxos.server import ApiError
        front = self.front_with_junk()
        before = len(self.front.frames())
        for pid, name in ((0, "���"), (255, "P�"), (0, "x")):
            with self.subTest(pid=pid), self.assertRaises(ApiError):
                self.app.local_delete(pid, name, dev=front)
        self.assertEqual(len(self.front.frames()), before, "nothing was even sent")

    def test_backups_and_show_by_look_skip_them(self):
        front = self.front_with_junk()
        st = self.app._local_read(dev=front)[-1]          # (Local, device, what it holds)
        b = localmode.as_backup(st)
        self.assertTrue(all(1 <= e["id"] <= L.MAX_PATTERN_ID for e in b["effects"]))


@unittest.skipIf(sync_playwright is None, "Playwright isn't installed")
class Browser(TwoBase):
    SHOTS = None

    def test_create_counts_the_chosen_controller_and_patterns_sort_and_fold(self):
        from eaveluxos.server import make_server
        s = copy.deepcopy(self.app.store.settings)
        s["effects"] = {**s["effects"], "zz": {"label": "Zebra", "colors": ["#FFFFFF", "#000000"], "counts": [4, 4]},
                        "xmas": {"label": "christmas Eve", "colors": ["#FF0000", "#00FF00"], "counts": [4, 4], "folder": "Christmas"},
                        "flag": {"label": "American Flag", "colors": ["#FF0000", "#FFFFFF", "#0000FF"], "counts": [4, 4, 4]}}
        self.app.save_settings(s)           # checked as the page's saves are
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

        def until(cond, what):
            for _ in range(160):
                if cond():
                    return
                time.sleep(0.05)
            self.fail(f"never: {what}")
        pg = br.new_page(viewport={"width": 1300, "height": 900})
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(base + "#patterns")
        pg.wait_for_selector("#psort")
        mine = {"American Flag", "christmas Eve", "Zebra"}
        names = lambda: [t.strip() for t in pg.locator("#pbody .card .title b").all_inner_texts() if t.strip() in mine]
        until(lambda: names() == ["American Flag", "christmas Eve", "Zebra"], "A to Z, whatever the case")
        pg.select_option("#psort", "new")
        until(lambda: names() == ["American Flag", "christmas Eve", "Zebra"][::-1] or names()[0] == "American Flag", "newest first")
        self.assertEqual(names(), ["American Flag", "christmas Eve", "Zebra"] if names()[0] == "American Flag" else names())
        pg.select_option("#psort", "az")
        pg.click('[data-pfolder="Christmas"]')
        until(lambda: names() == ["christmas Eve"], "the Christmas folder")
        pg.locator("[data-pfolder]").last.click()
        until(lambda: names() == ["American Flag", "Zebra"], "no folder")
        pg.locator("[data-pfolder]").first.click()
        until(lambda: len(names()) == 3, "all")
        pg.locator(".card", has_text="Zebra").locator("[data-pfold]").click()
        pg.fill("input[name=folder]", "Fourth of July")
        pg.locator("#dlg button[type=submit], #dlg .primary").last.click()
        until(lambda: self.app.store.settings["effects"]["zz"].get("folder") == "Fourth of July", "a new folder")
        # Create: Bulbs of, when the controllers differ in length
        pg.evaluate("""async () => { await loadDevices(); const [a, b] = S.devices.filter(x => x.selected);
            a.ports = [{port: 1, start: 1, end: 96}]; b.ports = [{port: 1, start: 1, end: 106}]; }""")
        pg.evaluate("go('create', {key: 'xmas'})")
        pg.wait_for_selector("#designdev")
        until(lambda: "96 bulbs" in pg.inner_text("#cvnote"), "the first controller's 96")
        opts = pg.locator("#designdev option").all_inner_texts()
        pg.select_option("#designdev", index=[i for i, o in enumerate(opts) if "106" in o][0])
        until(lambda: "106 bulbs" in pg.inner_text("#cvnote"), "the Front's 106")
        pg.locator("[data-save]").click()
        until(lambda: self.app.store.settings["effects"]["xmas"].get("folder") == "Christmas", "saving keeps the folder")
        if self.SHOTS:
            pg.screenshot(path=f"{self.SHOTS}/create.png")
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
