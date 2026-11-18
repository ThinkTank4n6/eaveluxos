# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Review #1 (4.9): each celebration rewrote the team's clip file before
playing it. On Windows the player still has that file open while it plays,
so a second goal within the clip's length (or Listen, then a goal) failed to
write it, and the error went up through the score check. The file system
is mocked. Run: python3 tests/repro_sound_locked.py"""
import sys; from pathlib import Path; sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from unittest import mock
from tests.test_sound49 import Server, mp3
t = Server("test_upload_listen_play_remove"); t.setUp()
t.app.sound_upload("nhl-phi", mp3(30), "horn.mp3"); t.set_sound()
t.app._play_sound("nhl-phi", {"seconds": 20})               # the first goal: the clip is open in the player
real = Path.write_bytes
def locked(self, data):
    if self.name.startswith("nhl-phi-"):
        raise PermissionError(13, "The process cannot access the file because it is being used by another process")
    return real(self, data)
try:
    with mock.patch.object(Path, "write_bytes", locked):
        ok = t.app._play_sound("nhl-phi", {"seconds": 20})   # the second goal
    print("OK: the second goal plays" if ok else "BUG: the second goal plays nothing")
except OSError as e:
    print(f"BUG: {e.__class__.__name__} went up to the score check: {e}")
t.tearDown()
