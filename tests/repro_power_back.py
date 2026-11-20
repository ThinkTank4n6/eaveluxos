# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Review #1 (4.15): a controller that lost power (Trimlight's cloud says
it's offline) and came back with its lights in another state waited for two
read-backs in a row to disagree, five minutes apart, before the app put the
lights back: up to ten minutes of the wrong lights after every power blip.
A controller coming back online is now set again at once, and while one is
offline it's looked at every minute. The cloud is a fake on this computer.
Run: python3 tests/repro_power_back.py"""
import sys; from pathlib import Path; sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.test_multi45 import TwoBase

t = TwoBase("run"); TwoBase.run = lambda s: None; t.setUp()
c, F = t.app.ctrl, t.F
c.manual(True, "christmas")
c.next_try = 0
c.tick()                                   # sent: on, Christmas
dev = F.STATE["dev"]
dev["connectivity"] = 0                    # the power goes out
c.last_verify = 0
c.tick()
dev["connectivity"], dev["switchState"] = 1, 0   # back, with its lights off
c.last_verify = 0
n = len(F.STATE["log"])
c.tick()                                   # the first read-back after it's back
c.tick()                                   # and the pass after it
sent = [p for p, _ in F.STATE["log"][n:] if p.endswith("/device/update")]
print("OK: set again as soon as it was back online" if sent else "BUG: the lights stayed wrong after the controller came back")
