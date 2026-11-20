# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Run a tests/repro_*.py script in its own Python and check it printed "OK:".

4.16.1: the same on every computer GitHub tests on.
- Windows: the script's output is read as UTF-8 and the script is told to
  write UTF-8 (Windows' own code page turned a curly quote into a byte the
  reader couldn't decode, and the test saw no output at all).
- macOS: only 127.0.0.1 answers there, so scripts that need a second
  controller at 127.0.0.2 can't run; that's a skip, as it is for the tests
  they come from, not a failure. A script can also print "SKIP: why"."""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(test, name: str, timeout: int = 120):
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    r = subprocess.run([sys.executable, str(ROOT / "tests" / name)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout, cwd=ROOT, env=env)
    out, err = r.stdout or "", r.stderr or ""
    if out.startswith("SKIP:"):
        test.skipTest(out.strip())
    if "unittest.case.SkipTest:" in err:
        test.skipTest(err.strip().splitlines()[-1].split("SkipTest:", 1)[1].strip())
    test.assertIn("OK:", out, out + err)
    return r
