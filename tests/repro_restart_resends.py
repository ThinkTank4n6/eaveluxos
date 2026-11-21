# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Review #2 (4.16.3), from Chris's log on Nov 20: every time the app
started, it logged "Trimlight's pattern was changed outside this app (power
blip or the Trimlight app). Restoring it." and sent the pattern again. The
pattern had gone over the home network (saved pattern 19), and Trimlight's
cloud doesn't hear about that; before the restart the app knew to leave the
cloud's view of the pattern alone. After the restart (4.15 keeps what was
sent) it had forgotten which way things went, compared the pattern with the
cloud's, and "restored" one that was right all along.
Run: python3 tests/repro_restart_resends.py"""
import sys; from pathlib import Path; sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from eaveluxos.controller import Controller
from tests.test_local43 import ServerBase

t = ServerBase("run"); ServerBase.run = lambda s: None; t.setUp()
c = t.app.ctrl
c.next_try = 0
c.tick()
c.lan_sent = {"TL-EDGE-01": {"switch", "pattern"}}     # on, and saved pattern 19, over the home network
c.lan_state = {"TL-EDGE-01": 1}
c._save_state()
n = Controller(c.cfg, c.api, data_dir=t.app.store.dir)    # the app starts again
got = n.lan_sent.get("TL-EDGE-01", set())
print("OK: after the restart it still knows the pattern went over the home network" if "pattern" in got and n.lan_state
      else f"BUG: after the restart it forgot ({got or 'nothing'}), so it checks the pattern with the cloud and resends it")
