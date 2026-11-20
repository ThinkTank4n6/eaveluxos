# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Review #1 (4.13): during a zone show, one keep-alive answered late (a
moment of busy Wi-Fi, a microwave, a phone joining) counted as the
controller falling behind: the show slowed down and never went back up to
the pace its speed test allowed, for the rest of the show. The controller is
a fake on this computer. Run: python3 tests/repro_zone_hiccup.py"""
import sys; from pathlib import Path; sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import os, time
os.environ["EAVELUXOS_LAN_TEST"] = "1"
from eaveluxos import lanlink as L, musicsync as M
from tests import fake_lan
from tests.test_local43 import factory_holds

ctl = fake_lan.FakeController(holds=factory_holds()); L.TCP_PORT = ctl.port
M.PING_EVERY, M.RISE_AFTER = 0.2, 0.8                # faster than real life, same rules
z = M.ZoneStreamer()
z.start("127.0.0.1", "tab", 4, "s1")
t0, k = time.monotonic(), 0
ctl.slow_pings = 1                                   # one hiccup, early on
while time.monotonic() - t0 < 4:
    k += 1
    z.feed(["#FF0000"], [1 + k % 200], "tab")
    time.sleep(0.05)
st = z.status()
z.stop(); ctl.close()
print(f"fps {st['fps']} of {st['max_fps']}, slowed {st['slowed']} time(s)")
print("OK: back to its pace after one late answer" if st["fps"] == 4 else "BUG: one late answer slowed the whole show")
