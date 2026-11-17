# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""4.4.4: keep the computer awake while the app runs (Nov 16: the mini PC
slept from 5:33 to 8:03 AM, past the time 0-Security turns the lights off)."""
import tempfile
import threading
import time
import unittest
from pathlib import Path

from eaveluxos import keepawake as K

ROOT = Path(__file__).resolve().parent.parent


class Fake:
    def __init__(self):
        self.calls = []                 # (flags, thread name)

    def __call__(self, flags):
        self.calls.append((flags, threading.current_thread().name))
        return 0x80000000


def settle(cond):
    for _ in range(100):
        if cond():
            return True
        time.sleep(0.01)
    return False


class KeepAwakeTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.fake = Fake()
        self.k = K.KeepAwake(self.dir.name, setter=self.fake)

    def tearDown(self):
        if self.k.stop is not None:
            self.k.stop.set()
        self.dir.cleanup()

    def test_on_by_default_and_held_by_its_own_thread(self):
        self.assertTrue(self.k.enabled())
        self.k.apply()
        self.assertEqual(self.fake.calls, [(K.ES_CONTINUOUS | K.ES_SYSTEM_REQUIRED, "keep-awake")])
        self.assertTrue(self.k.status()["holding"])
        self.k.apply()                                   # again: still one request
        self.assertEqual(len(self.fake.calls), 1)

    def test_turned_off_lets_it_sleep_from_the_same_thread(self):
        self.k.apply()
        r = self.k.set_enabled(False)
        self.assertFalse(r["enabled"])
        self.assertTrue(settle(lambda: len(self.fake.calls) == 2))
        self.assertEqual(self.fake.calls[1], (K.ES_CONTINUOUS, "keep-awake"))
        self.assertTrue(settle(lambda: not self.k.holding))
        self.assertFalse(K.KeepAwake(self.dir.name, setter=self.fake).enabled(), "the choice is kept")
        self.k.set_enabled(True)
        self.assertEqual(self.fake.calls[-1][0], K.ES_CONTINUOUS | K.ES_SYSTEM_REQUIRED)

    def test_off_when_started_asks_nothing(self):
        self.k.set_enabled(False)
        self.k.apply()
        self.assertEqual(self.fake.calls, [])

    def test_elsewhere_does_nothing(self):
        k = K.KeepAwake(self.dir.name, setter=None)
        k.apply()
        self.assertEqual(k.status(), {"supported": False, "enabled": True, "holding": False})

    def test_a_damaged_file_means_on(self):
        (Path(self.dir.name) / "keepawake.json").write_text("{nope", encoding="utf-8")
        self.assertTrue(self.k.enabled())

    def test_windows_refusing_isnt_holding(self):
        k = K.KeepAwake(self.dir.name, setter=lambda flags: 0)
        k.apply()
        self.assertFalse(k.status()["holding"])
        k.stop.set()

    def test_wired_in(self):
        server = (ROOT / "eaveluxos" / "server.py").read_text(encoding="utf-8")
        self.assertIn("self.awake.apply()", server)
        self.assertIn('"/api/awake"', server)
        self.assertIn('"awake": app.awake.status()', server)
        js = (ROOT / "eaveluxos" / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="awake"', js)
        self.assertIn("api('awake'", js)


if __name__ == "__main__":
    unittest.main()
