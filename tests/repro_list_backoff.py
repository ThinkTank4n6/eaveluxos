# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Review #1 (4.8): before working out each controller's rules, every pass
asked Trimlight's cloud for the account's controllers while it didn't know
them yet, even while waiting out a failure. With the cloud down, that was a
request every pass instead of backing off (30 s, 60 s, ... up to 5 minutes).
The cloud is mocked. Run: python3 tests/repro_list_backoff.py"""
import sys; from pathlib import Path; sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from eaveluxos.api import TrimlightError
from tests.test_each48 import Rules
t = Rules("test_each_follows_its_own_rule"); t.setUp()
asked = []
def down():
    asked.append(1)
    raise TrimlightError("Trimlight's cloud didn't answer")
t.api.list_devices = down
t.at(18, 1)                                     # first pass: fails, waits 30 s
first = len(asked)
for _ in range(10):                             # ten passes during the wait
    t.c.tick()
extra = len(asked) - first
print(f"BUG: {extra} more requests while waiting to retry" if extra else "OK: no requests while waiting to retry")
