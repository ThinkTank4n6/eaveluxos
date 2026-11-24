# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""4.22.7: every standalone repro runs where the console can't print beyond
ASCII (Windows prints through cp1252; 4.22.6's repro printed a lightning-bolt
sign there and came out empty)."""
import os
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent


class AsciiConsole(unittest.TestCase):
    def test_every_min_repro(self):
        env = {**os.environ, "PYTHONIOENCODING": "ascii"}
        for script in sorted(HERE.glob("repro_min_*.py")):
            for args in ([], ["--fixed"]):
                with self.subTest(script=script.name, args=args):
                    r = subprocess.run([sys.executable, str(script), *args], capture_output=True, text=True,
                                       timeout=120, env=env, cwd=str(HERE.parent))
                    self.assertNotIn("Traceback", r.stderr, r.stderr[-400:])      # some exit 1 on BUG, on purpose
                    self.assertRegex(r.stdout, r"\b(BUG|OK)\b", r.stdout[-200:])


if __name__ == "__main__":
    unittest.main()
