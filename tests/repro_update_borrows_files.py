# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Review #1 (4.16.3): Setup › App › Install on Windows left EaveLuxOS
answering {"error": "not found"} with no page, and "Failed to remove temp
directory". The download is one file that unpacks itself to a temporary
folder and tells the copy it runs where that is through the environment
(_PYI_... variables). The updater started the new version with this
copy's environment, so the new version used this copy's folder, which was
deleted when this copy closed. Here: what the updater hands the new copy.
Run: python3 tests/repro_update_borrows_files.py"""
import sys; from pathlib import Path; sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import os, subprocess, tempfile
from unittest import mock
from eaveluxos.server import App

os.environ.update(_PYI_APPLICATION_HOME_DIR=r"C:\Users\x\AppData\Local\Temp\_MEI12345", _PYI_PARENT_PROCESS_LEVEL="1",
                  _MEIPASS2=r"C:\Users\x\AppData\Local\Temp\_MEI12345")
app = App(Path(tempfile.mkdtemp()), start=False)
with mock.patch.object(subprocess, "Popen") as popen:
    app._update_spawn()
env = popen.call_args.kwargs.get("env")
seen = env if env is not None else dict(os.environ)       # no env given: the child gets this one
left = sorted(k for k in seen if k.startswith(("_PYI_", "_MEIPASS")))
app.store.close()
if left or seen.get("PYINSTALLER_RESET_ENVIRONMENT") != "1":
    print("BUG: the new version is told to use this copy's unpacked files:", left or "no reset"); sys.exit(1)
print("OK: the new version unpacks its own files")
