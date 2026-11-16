# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Review #1 (4.3.8): Trimlight's calendar won't take two timers on the same
date ("The calendar schedules cannot be crossed", code 12000, Nov 13), and
the backup timer already avoids the Trimlight app's own timers for that
reason, but it wrote two of its own on each date (a morning rule and an
evening rule). On Nov 15 and 16 all 14 entries for 7 nights "differed" and it
stopped itself. Nothing external is called. Run: python3 tests/repro_calendar_same_day.py"""
import sys
from collections import Counter
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from eaveluxos import safety
one_per_day = getattr(safety, "one_per_day", lambda e: (e, []))    # before the fix: every window written

entries = [{"month": 11, "day": d, "start": s, "end": e, "slot": k, "label": k}
           for d in range(16, 23) for s, e, k in (([6, 0], [6, 48], "0-Security"), ([16, 44], [23, 0], "Fall"))]
kept, dropped = one_per_day(entries)
per_day = Counter((e["month"], e["day"]) for e in kept)
print("OK: one timer per date" if max(per_day.values()) == 1 and len(kept) == 7
      else f"BUG: {len(kept)} timers for {len(per_day)} dates")
