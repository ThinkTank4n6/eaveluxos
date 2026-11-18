# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Review #1 (4.5.1): with home-network commands on, the 5-minute check read
each controller over the home network every time (a full state read, which
also sets its clock), all night, even when Trimlight's cloud already agreed.
On Nov 17 the controller stopped answering reads at 2:56 AM after hours of
these. Now it reads only when the cloud disagrees with what was sent.
The cloud and the controller are mocked. Run: python3 tests/repro_verify_reads.py"""
import sys; from pathlib import Path; sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.test_controller import ControllerTests
t = ControllerTests("test_schedule_on_off_and_levels"); t.setUp()
c, api = t.c, t.api
c.devices = [{"deviceId": "D1", "name": "House"}]
reads = []
c.lan = type("Lan", (), {"power": lambda s, d, on: True, "show": lambda s, d, p: True, "show_like": lambda s, d, p: None, "preview": lambda s, d, p: False,
                         "switch": lambda s, d: reads.append(d) or 1})()
api.switch = 1                                 # the cloud hears about it from the controller
t.at(19)                                       # lights on over the home network
for m in (5, 11, 17, 23, 29, 35):              # six regular checks, half an hour
    c.last_verify = 0; t.at(19, m)
print(f"BUG: {len(reads)} home-network reads in half an hour with the cloud agreeing" if reads else
      "OK: no home-network reads while the cloud agrees")
t.tearDown()
