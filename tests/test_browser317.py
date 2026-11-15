# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""3.17.1 review #12: the House view and split dialog in a real browser
(Playwright with Chromium). Skipped where Playwright isn't installed, such as
on the GitHub test machines."""
import copy
import io
import os
import shutil
import tempfile
import threading
import unittest
from pathlib import Path

from tests import fake_trimlight as F

try:
    from playwright.sync_api import sync_playwright
except ImportError:          # pragma: no cover
    sync_playwright = None


@unittest.skipIf(sync_playwright is None, "Playwright isn't installed")
class BrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import eaveluxos.api
        from PIL import Image
        from eaveluxos.server import App, make_server
        cls.cloud = F.start()
        cls._saved = eaveluxos.api.BASE_URL
        eaveluxos.api.BASE_URL = f"http://127.0.0.1:{cls.cloud.server_address[1]}/trimlight"
        cls.dir = Path(tempfile.mkdtemp())
        cls.app = App(cls.dir, start=False)
        b = io.BytesIO()
        Image.new("RGB", (600, 400), (90, 110, 150)).save(b, "JPEG")
        cls.app.save_photo(cls.app.photo_path("front"), b.getvalue())
        s = copy.deepcopy(cls.app.store.settings)
        s["location"].update(latitude=39.95, longitude=-75.16)
        s["setup_done"] = True
        s["map"] = {"rooflines": {"front": [{"id": "a", "kind": "edge", "points": [[10, 40], [90, 40]], "wire": [],
                                              "bulbs": {"from": 1, "to": 138}}]}}
        s["effects"]["sp"] = {"label": "Split", "split": {"GONE-1": "christmas", "TL-EDGE-01": "warm_white"}}
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

    def page(self, view):
        pg = self.browser.new_page(viewport={"width": 1300, "height": 1000})
        self.errors = []
        pg.on("pageerror", lambda e: self.errors.append(str(e)))
        pg.goto(self.base + "#" + view)
        pg.wait_for_timeout(2000)
        self.addCleanup(pg.close)
        return pg

    def test_scene_from_typed_bulbs_is_saved_for_the_whole_house(self):
        pg = self.page("map")
        self.assertEqual(pg.evaluate("document.querySelector('#pimg').naturalWidth"), 600, "the main photo loads (#5)")
        pg.click("[data-hvmode=scene]")
        pg.fill("#hvnums", "10-12, 40")
        pg.click("[data-hvnums]")
        pg.fill("#hvname", "Accents")
        pg.click("[data-hvsave]")
        pg.wait_for_timeout(1200)
        e = self.app.store.settings["effects"]["accents"]
        self.assertEqual(e["scene"]["groups"][0]["bulbs"], [10, 11, 12, 40])
        self.assertEqual(sum(e["counts"]), 138)
        self.assertIn("(4)", pg.inner_text("[data-hvg='0']"))
        self.assertEqual(self.errors, [])

    def test_split_dialog_keeps_a_controller_not_shown(self):
        real = self.app.devices
        self.app.devices = lambda *a, **k: [
            {"id": "TL-EDGE-01", "name": "Upstairs", "selected": True},
            {"id": "TL-EDGE-02", "name": "Garage", "selected": True}]
        self.addCleanup(setattr, self.app, "devices", real)
        pg = self.page("patterns")
        pg.click("[data-edit=sp]")
        pg.wait_for_timeout(800)
        self.assertIn("Also kept", pg.inner_text("#dlg"))
        pg.select_option("#dlg select[name=d1]", "security_white")
        pg.click("#dlg button.primary")
        pg.wait_for_timeout(1200)
        self.assertEqual(self.app.store.settings["effects"]["sp"]["split"],
                         {"GONE-1": "christmas", "TL-EDGE-01": "warm_white", "TL-EDGE-02": "security_white"})
        self.assertEqual(self.errors, [])


if __name__ == "__main__":
    unittest.main()
