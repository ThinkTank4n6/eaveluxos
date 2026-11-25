# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""4.26: Share to the community library: the app writes the file, GitHub's
own page makes the pull request."""
import json
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.parse
from pathlib import Path

from eaveluxos import community

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools" / "community-library"))
import build_index  # noqa: E402

FALL = {"label": "Fall", "colors": ["#341202", "#561003", "#ff6300"], "counts": [4, 4, 4], "custom_mode": 0,
        "speed": 128, "brightness": 139, "exact_colors": True, "folder": "Seasons"}


class File(unittest.TestCase):
    def test_0_library_layout(self):
        name, text = community.share_file(FALL, "Fall", "ThinkTank4n6", "Autumn.", "fall, autumn")
        lines = text.splitlines()
        self.assertEqual(lines[0], "{")
        self.assertEqual(lines[4], ' "tags": ["fall", "autumn"],')
        self.assertTrue(lines[5].startswith(' "pattern": {"label": "Fall", "colors": ['))
        self.assertEqual(lines[6:], ["}"])
        self.assertTrue(text.endswith("}\n"))

    def test_1_passes_the_librarys_own_check(self):
        name, text = community.share_file(FALL, "Fall Colors!", "ThinkTank4n6", "Autumn browns.", "fall, Autumn, fall, ")
        self.assertEqual(name, "fall-colors.json")
        d = json.loads(text)
        self.assertEqual(d["tags"], ["fall", "autumn"])
        self.assertNotIn("folder", d["pattern"], "only the pattern itself, nothing about this home")
        self.assertEqual(d["pattern"]["colors"][2], "#FF6300")
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / name
            p.write_text(text, encoding="utf-8")
            entry, errs = build_index.check_file(p)
        self.assertEqual(errs, [])
        self.assertEqual(entry["id"], "fall-colors")

    def test_newer_animations_pass_too(self):
        name, text = community.share_file({**FALL, "custom_mode": 22}, "Juggle")
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / name
            p.write_text(text, encoding="utf-8")
            self.assertEqual(build_index.check_file(p)[1], [])

    def test_refuses(self):
        for pat, nm, tags in (({"saved": "Fall"}, "x", ()), (FALL, "  ", ()), (FALL, "x", [str(i) for i in range(9)]),
                              ({**FALL, "custom_mode": 40}, "x", ())):
            with self.assertRaises(community.CommunityError):
                community.share_file(pat, nm, tags=tags)

    def test_github_page(self):
        url = community.new_file_url({}, "fall.json", '{"name": "Fall"}\n')
        u = urllib.parse.urlparse(url)
        self.assertEqual((u.netloc, u.path), ("github.com", "/ThinkTank4n6/eaveluxos-patterns/new/main"))
        q = urllib.parse.parse_qs(u.query)
        self.assertEqual(q["filename"], ["patterns/fall.json"])
        self.assertEqual(q["value"], ['{"name": "Fall"}\n'])
        self.assertIsNone(community.new_file_url({"community": {"url": "https://example.org/lib/"}}, "a.json", "{}"))

    def test_1_the_standalone_repro(self):
        script = str(HERE / "repro_min_library_rejects_juggle.py")
        self.assertIn("BUG:", subprocess.run([sys.executable, script], capture_output=True, text=True, timeout=60).stdout)
        self.assertIn("OK:", subprocess.run([sys.executable, script, "--fixed"], capture_output=True, text=True, timeout=60).stdout)


try:
    from playwright.sync_api import sync_playwright
except ImportError:            # pragma: no cover
    sync_playwright = None

from tests.test_local43 import ServerBase   # noqa: E402


@unittest.skipIf(sync_playwright is None, "Playwright isn't installed")
class Browser(ServerBase):
    def test_share_dialog_to_github(self):
        from eaveluxos.server import make_server
        s = self.app.store.settings
        s.setdefault("effects", {})["fall"] = {k: v for k, v in FALL.items() if k != "folder"}
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
        pg.wait_for_selector("[data-share='fall']", timeout=20000)
        pg.click("[data-share='fall']")
        pg.click("[data-community='fall']", timeout=20000)
        pg.fill("#dlg input[name=au]", "ThinkTank4n6")
        pg.fill("#dlg input[name=tg]", "fall, autumn")
        pg.click("#dlg button.primary")
        pg.wait_for_selector("#dlg a.btn.primary", timeout=20000)
        href = pg.get_attribute("#dlg a.btn.primary", "href")
        self.assertTrue(href.startswith("https://github.com/ThinkTank4n6/eaveluxos-patterns/new/main?filename=patterns%2Ffall.json"), href)
        self.assertEqual(pg.get_attribute("#dlg a.btn.primary", "target"), "_blank")
        self.assertLessEqual(pg.evaluate("document.documentElement.scrollWidth"), 390)
        self.assertEqual(errs, [])


if __name__ == "__main__":
    unittest.main()
