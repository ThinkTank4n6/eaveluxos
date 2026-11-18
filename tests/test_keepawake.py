# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""4.4.4: keep the computer awake while the app runs (Nov 16: the mini PC
slept from 5:33 to 8:03 AM, past the time 0-Security turns the lights off)."""
import platform
import subprocess
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


class Fn:
    """A stand-in for a C function (ctypes sets argtypes and restype on it)."""
    def __init__(self, impl):
        self.impl = impl

    def __call__(self, *a):
        return self.impl(*a)


class FakeMac:
    """IOKit and CoreFoundation, as far as the keep-awake assertion uses them."""
    def __init__(self, rc=0):
        self.rc, self.held, self.released, self.strings, self.freed = rc, {}, [], {}, []
        self.next = 41

        def cfstr(_alloc, text, _enc):
            self.next += 1
            self.strings[self.next] = text.decode()
            return self.next

        def create(kind, level, name, out):
            if self.rc:
                return self.rc
            self.next += 1
            out._obj.value = self.next
            self.held[self.next] = (self.strings[kind], level, self.strings[name])
            return 0
        self.CFStringCreateWithCString = Fn(cfstr)
        self.CFRelease = Fn(self.freed.append)
        self.IOPMAssertionCreateWithName = Fn(create)
        self.IOPMAssertionRelease = Fn(lambda i: self.released.append(self.held.pop(i)) or 0)


class Mac(unittest.TestCase):
    """4.7.2: on a Mac, the caffeinate -i power assertion."""
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)

    def test_held_and_let_go(self):
        f = FakeMac()
        k = K.KeepAwake(self.dir.name, setter=K._MacAssertion(f, f))
        k.apply()
        self.assertTrue(k.status()["holding"])
        self.assertEqual(list(f.held.values()), [("PreventUserIdleSystemSleep", 255, K._MacAssertion.NAME)])
        self.assertEqual(len(f.freed), 2, "its two strings are let go of")
        k.apply()
        self.assertEqual(len(f.held), 1, "asked again: still one")
        k.set_enabled(False)
        self.assertTrue(settle(lambda: not f.held and f.released))
        self.assertTrue(settle(lambda: not k.holding))
        k.set_enabled(True)
        self.assertTrue(settle(lambda: len(f.held) == 1 and k.holding), "and again when turned back on")
        k.stop.set()
        self.assertTrue(settle(lambda: not f.held))

    def test_off_and_straight_back_on_stays_held(self):
        """Review #1 (4.7.2): the old holder letting go slowly didn't take
        the new one's assertion with it (tests/repro_awake_reenable.py)."""
        f = FakeMac()
        slow = f.IOPMAssertionRelease.impl
        f.IOPMAssertionRelease.impl = lambda i: (time.sleep(0.15), slow(i))[1]
        k = K.KeepAwake(self.dir.name, setter=K._MacAssertion(f, f))
        k.apply()
        k.set_enabled(False)
        k.set_enabled(True)
        time.sleep(0.4)
        self.assertEqual(len(f.held), 1)
        self.assertTrue(k.status()["holding"])
        k.stop.set()

    def test_refused_isnt_holding(self):
        f = FakeMac(rc=-536870201)          # kIOReturnNotPermitted, as a signed 32-bit number
        k = K.KeepAwake(self.dir.name, setter=K._MacAssertion(f, f))
        with self.assertLogs("eaveluxos.keepawake", "WARNING") as logs:
            k.apply()
        self.assertFalse(k.status()["holding"])
        self.assertIn("0xe00002c7", logs.output[0])
        k.stop.set()

    def test_not_a_mac_asks_nothing(self):
        if platform.system() == "Darwin":
            self.skipTest("this is a Mac")
        self.assertIsNone(K._mac_setter())

    @unittest.skipUnless(platform.system() == "Darwin", "a Mac only")
    def test_on_a_real_mac(self):
        """GitHub's Mac test run: the Mac lists the assertion while it's held
        (as `pmset -g assertions` does for caffeinate) and not after."""
        k = K.KeepAwake(self.dir.name, setter="mac")
        self.assertTrue(k.supported)
        listed = lambda: K._MacAssertion.NAME in subprocess.run(["pmset", "-g", "assertions"], capture_output=True,
                                                                text=True, encoding="utf-8", timeout=20).stdout
        k.apply()
        self.addCleanup(lambda: k.stop and k.stop.set())
        self.assertTrue(k.status()["holding"])
        self.assertTrue(listed(), "pmset lists it")
        k.set_enabled(False)
        self.assertTrue(settle(lambda: not k.holding))
        self.assertFalse(listed(), "and not after")


if __name__ == "__main__":
    unittest.main()
