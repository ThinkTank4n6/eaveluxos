# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Review #1 (4.16.6), Chris's power-cut test on Nov 21: Christmas picked
by hand (sent over the home network), the controller unplugged at 4:46:00
and plugged back in at 4:47:17. It came back in its own Timer mode (dark,
then its own Fall at 4:53), and EaveLuxOS never put Christmas back: the
outage fell between two read-backs (every 5 minutes), so it never saw the
controller offline, and with the pattern and the switch sent over the home
network it ignored what Trimlight's cloud reported. The cloud's report had
changed, though: a controller that restarts tells the cloud its state again.
Run: python3 tests/repro_short_power_cut.py"""
import sys; from pathlib import Path; sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.test_local43 import ServerBase

DEV = "TL-EDGE-01"
t = ServerBase("run"); ServerBase.run = lambda s: None; t.setUp()
t.app.local_commands(True)                 # everyday commands over the home network (Chris has this on)
c, F = t.app.ctrl, t.F
c.devices = [{"deviceId": DEV, "name": "Trimlight"}]
c.manual(True, "christmas")
c.next_try = 0
c.tick()                                   # on, Christmas, over the home network
if not c.lan_sent:
    print("SKIP: nothing went over the home network here"); sys.exit(0)
c.last_verify = 0
c.tick()                                   # a read-back: all as sent
dev = F.STATE["dev"]
# Out and back between two read-backs: online again, reporting its own Timer mode and its own pattern
dev["switchState"] = 2
dev["currentEffect"] = {"id": 19, "name": "Fall", "category": 2, "mode": 0}
before = {id(e) for e in list(c.events)}
for _ in range(2):                         # the next two read-backs (5 minutes apart)
    c.last_verify = 0
    c.tick()
said = [e["msg"] for e in list(c.events) if id(e) not in before]
print("OK: put back after a short power cut" if any("Restoring" in m for m in said)
      else f"BUG: the lights stayed as the controller left them ({said or 'nothing logged'})")
