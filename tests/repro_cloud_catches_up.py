# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Review #1 (4.18.1), from Chris's log on Nov 22: the lights came on over the
home network at 4:40 PM and at 4:48 the app said "Trimlight was changed
outside this app (power blip or the Trimlight app). Restoring it." Nothing
had changed: the cloud doesn't hear about home-network commands, so its first
report after one was still the old state, and when it caught up with what
this app had sent, that counted as a change from outside.
Run: python3 tests/repro_cloud_catches_up.py"""
import sys; from pathlib import Path; sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import unittest
from tests.test_local43 import ServerBase

DEV = "TL-EDGE-01"
said = []


class Repro(ServerBase):
    def test(self):
        c = self.app.ctrl
        self.app.local_commands(True)
        c.devices = [{"deviceId": DEV, "name": "Trimlight"}]
        self.F.STATE["dev"]["switchState"] = 0            # the cloud: still off, from before
        c.manual(True, "christmas")
        c.next_try = 0
        c.tick()

        def check():
            before = {id(e) for e in list(c.events)}
            c.last_verify = 0
            c.tick()
            said.extend(e["msg"] for e in list(c.events) if id(e) not in before)
        check()
        check()                                            # the stale report is the baseline
        sent = c.sent_effect.get(DEV) or {}
        self.F.STATE["dev"]["switchState"] = 1             # the cloud catches up with what was sent
        self.F.STATE["dev"]["currentEffect"] = {**sent, "id": sent.get("id", -1), "category": sent.get("category", 1)}
        for _ in range(3):
            check()


unittest.TextTestRunner(stream=open(__import__("os").devnull, "w")).run(unittest.TestLoader().loadTestsFromTestCase(Repro))
bad = [m for m in said if "changed outside" in m]
print(f"BUG: {bad[0]}" if bad else "OK: the cloud catching up with a home-network send isn't a change from outside")
