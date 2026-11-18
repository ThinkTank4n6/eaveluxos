# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Review #1 (4.4.1): with home-network commands on, a rule showing a pattern
of its own colors turned the lights on over the home network but sent the
pattern through Trimlight's cloud, which then made the app trust the cloud's
on/off again. The cloud never heard about the local "on", so every check
saw "off", warned "changed outside this app" and sent everything again.
The cloud and the controller are mocked. Run: python3 tests/repro_mixed_paths.py"""
import sys; from pathlib import Path; sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.test_controller import ControllerTests
t = ControllerTests("test_schedule_on_off_and_levels"); t.setUp()
c, api = t.c, t.api
c.devices = [{"deviceId": "D1", "name": "House"}]
c.lan = type("Lan", (), {"power": lambda s, d, on: True, "show": lambda s, d, p: True, "show_like": lambda s, d, p: None, "preview": lambda s, d, p: False, "switch": lambda s, d: 1})()
warnings = []; c.note = lambda msg, *a, **k: warnings.append(msg)
t.at(19)                                     # lights on: "on" went over the home network, the pattern via the cloud
for m in (5, 11, 17, 23):                    # four regular checks; the cloud still says off (0)
    c.last_verify = 0; t.at(19, m)
restores = [w for w in warnings if "outside this app" in w]
print(f"BUG: {len(restores)} false 'changed outside this app' restores" if restores else "OK: no false restores")
t.tearDown()
