# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Review #1 (4.3.6): reads of the controller take one connection at a time
(lan_io), but starting Music from this computer didn't wait its turn. A show
started while a panel was reading opened a second connection, which the
controller doesn't answer: the show failed with "didn't answer". The
controller and the show are mocked. Run: python3 tests/repro_show_vs_read.py"""
import os, sys, tempfile, threading
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent)); os.environ["EAVELUXOS_PORTABLE"] = "1"
from eaveluxos.server import App

app = App(Path(tempfile.mkdtemp()), start=False)
app.lan_io.acquire()                                   # a panel is reading the controller now
read_done, seen = threading.Event(), []
app.lanshow.start = lambda *a, **k: seen.append(read_done.is_set())     # the show connects
app.ctrl = type("C", (), {"other_show_on": lambda s, by=None: None, "start_music": lambda s, *a, **k: None,
                          "note": print, "stop_music": lambda s: None, "music": None})()
app._lan_address = lambda: "10.0.0.5"
t = threading.Thread(target=lambda: app.musiclink({"op": "start", "tab": "t1", "pattern": 0, "sensitivity": 8}), daemon=True)
t.start(); t.join(0.5); read_done.set(); app.lan_io.release(); t.join(5)
print("OK: the show waited for the read to finish" if seen == [True] else "BUG: the show connected during a read")
