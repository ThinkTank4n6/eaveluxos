# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Review #1 (4.10): with every controller turned Off by hand during a
scheduled evening, using the House tab's finder on one controller ended that
"Off" for all of them, so the other controller came back on with the
schedule while you were only looking for a bulb on the first. The cloud is
mocked. Run: python3 tests/repro_finder_wakes_others.py"""
import sys; from pathlib import Path; sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.test_each48 import DECK, FRONT, OneByHand
t = OneByHand("test_one_controller_on_by_itself"); t.setUp()
t.at(19)                                          # the schedule has both on
t.c.manual(False)                                 # Off, by hand, for all
t.c.manual_one(FRONT, True, obj=t.cfg.effects["christmas"], expires_min=10)   # the finder, on the Front
deck = t.api.switch[DECK]
print("OK: the Deck stays off" if deck == 0 else "BUG: the Deck came back on while the finder lit the Front")
