# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Review #1 (4.7.2): turning keep-awake off and straight back on (two taps
on the switch, or two phones) started a new holding thread while the old one
was still letting go. On a Mac both share one power assertion: the new one
saw it still held and kept it, then the old one released it, so the Mac
could sleep while the app said it was being kept awake. (On Windows the
request is per thread, but the old thread still cleared "holding" after the
new one set it.) The Mac is faked. Run: python3 tests/repro_awake_reenable.py"""
import sys, tempfile, time; from pathlib import Path; sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from eaveluxos import keepawake as K
from tests.test_keepawake import FakeMac
f = FakeMac()
slow = f.IOPMAssertionRelease.impl
f.IOPMAssertionRelease.impl = lambda i: (time.sleep(0.2), slow(i))[1]      # letting go takes a moment
k = K.KeepAwake(tempfile.mkdtemp(), setter=K._MacAssertion(f, f))
k.apply()
k.set_enabled(False)
k.set_enabled(True)
time.sleep(0.6)
held, says = bool(f.held), k.status()["holding"]
print("OK: the Mac is kept awake" if held and says else
      f"BUG: assertion held: {held}, app says holding: {says}")
k.stop.set()
