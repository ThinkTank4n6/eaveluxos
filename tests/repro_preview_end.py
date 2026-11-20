# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Review #1 (4.16): with Christmas chosen by hand on the Deck, calibrating
the Deck with the camera (or using the bulb finder on it) ended with the
Deck back on the schedule: the choice made by hand was gone. Previews on one
controller now remember what they cover, and ending them puts it back. The
cloud is a fake on this computer; the requests are the page's own.
Run: python3 tests/repro_preview_end.py"""
import sys; from pathlib import Path; sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import json, threading, urllib.request
from eaveluxos.server import make_server
from tests.test_multi45 import DECK, FRONT, TwoBase

t = TwoBase("run"); TwoBase.run = lambda s: None; t.setUp()
app = t.app
app.ctrl.devices = [{"deviceId": DECK, "name": "Deck"}, {"deviceId": FRONT, "name": "Front"}]
srv = make_server(app, "127.0.0.1", 0); threading.Thread(target=srv.serve_forever, daemon=True).start()
def act(**b):
    r = urllib.request.Request(f"http://127.0.0.1:{srv.server_address[1]}/api/action", data=json.dumps(b).encode(),
                               headers={"Content-Type": "application/json", "X-Requested-With": "eaveluxos"})
    urllib.request.urlopen(r, timeout=30).read()
app.ctrl.manual_one(DECK, True, "christmas")                   # chosen by hand
frame = {"label": "Calibration", "colors": ["#000000", "#FFFFFF"], "counts": [4, 4], "custom_mode": 0, "speed": 0, "brightness": 255}
for _ in range(3):
    act(action="try", effect=frame, minutes=10, device=DECK)     # the frames
calib = Path(__file__).resolve().parent.parent / "eaveluxos" / "static" / "app.js"
uses_end = "action: 'end_preview'" in calib.read_text(encoding="utf-8")
act(**({"action": "end_preview", "device": DECK} if uses_end else {"action": "one", "device": DECK, "state": "schedule"}))   # as the page ends it
o = app.ctrl.dev_override.get(DECK)
srv.shutdown()
print("OK: back to Christmas, chosen by hand" if o and o.get("effect") == "christmas" and o.get("obj") is None
      else f"BUG: the Deck's choice made by hand was lost ({o})")
