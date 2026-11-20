# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Review #1 (4.12): with the House tab open on the computer, a night photo
uploaded for a version from the phone, then the version deleted on the
computer: the computer's page didn't know about the new photo, so it didn't
delete it. The photo stayed on disk, and the next version given the same
name ("Night" again) showed that old photo, with no rooflines on it.
Needs Playwright (Chromium); prints SKIP without it.
Run: python3 tests/repro_version_photo_left.py"""
import sys; from pathlib import Path; sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import copy, io, threading, time
try:
    from playwright.sync_api import sync_playwright
    from PIL import Image
except ImportError:
    print("SKIP: Playwright or Pillow isn't installed"); sys.exit(0)
from eaveluxos.server import make_server
from tests.test_multi45 import TwoBase

t = TwoBase("run"); TwoBase.run = lambda s: None; t.setUp()
app = t.app
s = copy.deepcopy(app.store.settings)
s["map"] = {"sides": [{"id": "front", "name": "Front elevation"}, {"id": "front-night", "name": "Night", "of": "front"}]}
app.save_settings(s)
srv = make_server(app, "127.0.0.1", 0); threading.Thread(target=srv.serve_forever, daemon=True).start()
try:
    pw = sync_playwright().start(); br = pw.chromium.launch()
except Exception as e:
    print(f"SKIP: Chromium can't start: {e}"); sys.exit(0)
pg = br.new_page(viewport={"width": 1300, "height": 1000})
pg.goto(f"http://localhost:{srv.server_address[1]}/#map")
pg.wait_for_selector('[data-ver="front-night"]')
b = io.BytesIO(); Image.new("RGB", (60, 40), (9, 9, 30)).save(b, "JPEG")
app.save_photo(app.photo_path("front-night"), b.getvalue())        # from the phone, after this page loaded
pg.click('[data-ver="front-night"]'); pg.wait_for_selector("[data-delver]")
pg.click("[data-delver]"); pg.click("#dlg button.danger")
for _ in range(100):
    if not any(x.get("id") == "front-night" for x in app.store.settings["map"]["sides"]): break
    time.sleep(0.05)
time.sleep(0.3)
left = app.photo_path("front-night").exists()
br.close(); pw.stop(); srv.shutdown()
print("BUG: the deleted version's photo stayed, for the next version named Night" if left else "OK: deleting a version deletes its photo")
