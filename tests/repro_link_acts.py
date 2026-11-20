# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Review #1 (4.14): the home-screen icon's shortcuts (Lights off, Security
flash...) are addresses like http://192.168.1.20:8787/?do=off. Opened as an
ordinary link (in an email, a chat, another web page) by someone signed in,
the app turned the lights off at once, without asking. Only the installed
app's own shortcuts should act at once; a link asks first.
Needs Playwright (Chromium); prints SKIP without it.
Run: python3 tests/repro_link_acts.py"""
import sys; from pathlib import Path; sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import threading, time
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("SKIP: Playwright isn't installed"); sys.exit(0)
from eaveluxos.server import make_server
from tests.test_multi45 import TwoBase

t = TwoBase("run"); TwoBase.run = lambda s: None; t.setUp()
app = t.app
srv = make_server(app, "127.0.0.1", 0); threading.Thread(target=srv.serve_forever, daemon=True).start()
try:
    pw = sync_playwright().start(); br = pw.chromium.launch()
except Exception as e:
    print(f"SKIP: Chromium can't start: {e}"); sys.exit(0)
pg = br.new_page()
pg.goto(f"http://localhost:{srv.server_address[1]}/?do=off#home")       # an ordinary browser tab, not the installed app
pg.wait_for_selector("#ribbon button")
time.sleep(1.5)
off = app.ctrl.override is not None and app.ctrl.override.get("on") is False
br.close(); pw.stop(); srv.shutdown()
print("BUG: a link turned the lights off without asking" if off else "OK: a link asks first; only the installed app's shortcuts act at once")
