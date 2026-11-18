# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Keep the computer from going to sleep while the app runs (4.4.4).

A sleeping computer can't follow the schedule. On Nov 16 the mini PC slept
from 5:33 to 8:03 AM, past sunrise, when 0-Security should have turned the
lights off; Windows put it to sleep on its own after a while untouched.

On Windows this asks for what a video player asks for while it plays
(SetThreadExecutionState with ES_SYSTEM_REQUIRED): Windows doesn't sleep on
its own, the screen can still turn off, and pressing the power button or
choosing Sleep still works. The request belongs to the thread that made it
and ends with it, so a thread of its own holds it, and quitting the app
lets the computer sleep again.

On a Mac (4.7.2) it asks the way the built-in caffeinate -i command does: an
IOKit power assertion, PreventUserIdleSystemSleep, named for this app (it
shows in `pmset -g assertions`). The Mac doesn't sleep on its own; the screen
can still turn off, and closing a laptop's lid, the Apple menu's Sleep and
the power button still work. It ends when the app lets go or quits.

Elsewhere (Linux) it does nothing.

On by default; the choice is kept in keepawake.json in the data folder."""
import json
import logging
import os
import platform
import threading
from pathlib import Path

log = logging.getLogger("eaveluxos.keepawake")

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001


def _windows_setter():
    if platform.system() != "Windows":
        return None
    try:
        import ctypes
        fn = ctypes.windll.kernel32.SetThreadExecutionState
        fn.argtypes = [ctypes.c_uint32]
        fn.restype = ctypes.c_uint32
        return fn
    except Exception:          # no ctypes or no kernel32: nothing to do
        return None


class _MacAssertion:
    """A caffeinate -i style power assertion (IOKit), called like Windows'
    SetThreadExecutionState so KeepAwake treats both alike: asked with
    ES_SYSTEM_REQUIRED it takes the assertion (non-zero when it got it),
    asked with ES_CONTINUOUS alone it lets go."""
    NAME = "EaveLuxOS: following the lights' schedule"
    LEVEL_ON = 255                       # kIOPMAssertionLevelOn
    UTF8 = 0x08000100                    # kCFStringEncodingUTF8

    def __init__(self, iokit, cf):
        import ctypes
        self.c = ctypes
        self.cf, self.iokit = cf, iokit
        cf.CFStringCreateWithCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]
        cf.CFStringCreateWithCString.restype = ctypes.c_void_p
        cf.CFRelease.argtypes = [ctypes.c_void_p]
        cf.CFRelease.restype = None
        iokit.IOPMAssertionCreateWithName.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p,
                                                      ctypes.POINTER(ctypes.c_uint32)]
        iokit.IOPMAssertionCreateWithName.restype = ctypes.c_int32
        iokit.IOPMAssertionRelease.argtypes = [ctypes.c_uint32]
        iokit.IOPMAssertionRelease.restype = ctypes.c_int32
        self.id = None

    def _cfstr(self, text):
        return self.cf.CFStringCreateWithCString(None, text.encode("utf-8"), self.UTF8)

    def __call__(self, flags):
        if flags & ES_SYSTEM_REQUIRED:
            if self.id is not None:
                return 1
            kind, name = self._cfstr("PreventUserIdleSystemSleep"), self._cfstr(self.NAME)
            try:
                if not kind or not name:
                    return 0
                out = self.c.c_uint32(0)
                rc = self.iokit.IOPMAssertionCreateWithName(kind, self.LEVEL_ON, name, self.c.byref(out))
            finally:
                for x in (kind, name):
                    if x:
                        self.cf.CFRelease(x)
            if rc != 0:
                log.warning("The Mac refused to stay awake (IOKit error %#x).", rc & 0xFFFFFFFF)
                return 0
            self.id = out.value
            return 1
        if self.id is not None:
            self.iokit.IOPMAssertionRelease(self.id)
            self.id = None
        return 1


def _mac_setter():
    if platform.system() != "Darwin":
        return None
    try:
        import ctypes
        iokit = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/IOKit.framework/IOKit")
        cf = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
        return _MacAssertion(iokit, cf)
    except Exception as e:     # an unusual Mac: nothing to do, and the switch is hidden
        log.info("Keep awake isn't available on this Mac: %s", e)
        return None


def _system_setter():
    return _windows_setter() or _mac_setter()


class KeepAwake:
    def __init__(self, data_dir, setter="auto"):
        self.path = Path(data_dir) / "keepawake.json"
        self.setter = {"auto": _system_setter, "windows": _windows_setter, "mac": _mac_setter}[setter]() \
            if isinstance(setter, str) else setter
        self.lock = threading.Lock()
        self.stop = None              # threading.Event of the holding thread
        self.thread = None            # the holding thread, kept until it has let go
        self.holding = False

    @property
    def supported(self) -> bool:
        return self.setter is not None

    def enabled(self) -> bool:
        try:
            return bool(json.loads(self.path.read_text(encoding="utf-8")).get("enabled", True))
        except (OSError, ValueError, AttributeError):
            return True

    def status(self) -> dict:
        return {"supported": self.supported, "enabled": self.enabled(), "holding": self.holding}

    def set_enabled(self, on: bool) -> dict:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"enabled": bool(on)}), encoding="utf-8")
        os.replace(tmp, self.path)
        self.apply()
        return self.status()

    def apply(self):
        """Hold or let go, as the setting says."""
        with self.lock:
            want = self.supported and self.enabled()
            if want and self.stop is None:
                # Review #1 (4.7.2): turned off and straight back on, the last
                # holder lets go first; otherwise it could release what the
                # new one holds (one assertion on a Mac) and clear "holding".
                if self.thread is not None:
                    self.thread.join(5)
                    if self.thread.is_alive():
                        log.warning("Keep awake: the last request is still being let go of; not asking again yet.")
                        return
                self.stop = threading.Event()
                ready = threading.Event()
                self.thread = threading.Thread(target=self._hold, args=(self.stop, ready), daemon=True,
                                               name="keep-awake")
                self.thread.start()
                ready.wait(2)
            elif not want and self.stop is not None:
                self.stop.set()
                self.stop = None

    def _hold(self, stop, ready):
        try:
            got = self.setter(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
        except Exception as e:
            got = 0
            log.warning("Couldn't ask this computer to stay awake: %s", e)
        self.holding = bool(got)
        if self.holding:
            log.info("Keeping this computer awake while the app runs, so the schedule is followed "
                     "(the screen can still turn off).")
        ready.set()
        stop.wait()
        try:
            self.setter(ES_CONTINUOUS)
        except Exception:
            pass
        if self.holding:
            log.info("This computer may sleep again on its own.")
        self.holding = False
