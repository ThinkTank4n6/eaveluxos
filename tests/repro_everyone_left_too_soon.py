# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Review #1 (4.18): with two people under Who's home, only one of whose
phones has reported so far, that one leaving counted as "everyone has left"
(and "Nobody is home" was true), although the other may well be home. An
"Everyone left: lights off" automation would turn the lights off on them.
Run: python3 tests/repro_everyone_left_too_soon.py"""
import sys; from pathlib import Path; sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import shutil, tempfile
from eaveluxos.presence import Presence

d = tempfile.mkdtemp()
try:
    p, people = Presence(d), ["Chris", "Ann"]
    p.set(people, "Chris", "home")
    r = p.set(people, "Chris", "away")          # Ann's phone hasn't said anything yet
    nobody = p.nobody_home(people) if hasattr(p, "nobody_home") else not p.home(people)
    print("BUG: Chris leaving counted as everyone gone while Ann isn't known"
          if r["last"] or nobody is True else "OK: nobody is home only once everyone's phone has said so")
finally:
    shutil.rmtree(d, ignore_errors=True)
