# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Review #1 (4.7.1): a backup taken over the home network called a built-in
effect saved in the Trimlight app (say "Fire", effect 5) a pattern of its own
colors, with the empty color slots of a built-in record. Put back from that
backup, it would have been written as a blank pattern of its own colors
named "Fire". Now the backup calls it a built-in, and putting back skips it
by name. No controller needed. Run: python3 tests/repro_backup_builtin.py"""
import sys; from pathlib import Path; sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from eaveluxos import lanlink as L, localmode
r = bytearray(L.pattern_record(1, "Fire", 0, 0, 0, [])); r[26:32] = bytes([1, 0, 120, 200, 5, 0])
e = localmode.as_backup({"ports": [], "patterns": [L.read_record(bytes(r))]})["effects"][0]
try:
    L.record_from_effect(1, e)
    print("BUG: the built-in effect would be put back as a blank pattern of its own colors")
except ValueError:
    print("OK: the backup calls it a built-in; putting back skips it")
