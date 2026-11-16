# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Review #1 (4.3.0): switching a port off over the home network was judged
by its start and end read back, but nobody has seen what the controller
reports for a port that is off. If it reports anything but the numbers sent
(0-0, say), a correct save is called a failure and stops midway: ports 1-2
changed, port 4 not. Run: python3 tests/repro_off_port_readback.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from eaveluxos.localmode import LocalError, _check

ports = lambda *p: [{"port": i + 1, "start": a, "end": b} for i, (a, b) in enumerate(p)]
before = {"patterns": [], "ports": ports((1, 83), (84, 138), (1, 600), (1, 600))}
after = {"patterns": [], "ports": ports((1, 83), (84, 138), (0, 0), (1, 600))}   # port 3 now off
try:
    _check(before, after, port=(2, 1, 600, False))
    print("OK: an off port is not judged by numbers the controller may not report")
except (LocalError, TypeError) as e:
    print("BUG: a correct 'port 3 off' is reported as a failure:", e)
