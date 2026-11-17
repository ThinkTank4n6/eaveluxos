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
lets the computer sleep again. Elsewhere it does nothing.

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


class KeepAwake:
    def __init__(self, data_dir, setter="windows"):
        self.path = Path(data_dir) / "keepawake.json"
        self.setter = _windows_setter() if setter == "windows" else setter
        self.lock = threading.Lock()
        self.stop = None              # threading.Event of the holding thread
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
                self.stop = threading.Event()
                ready = threading.Event()
                threading.Thread(target=self._hold, args=(self.stop, ready), daemon=True,
                                 name="keep-awake").start()
                ready.wait(2)
            elif not want and self.stop is not None:
                self.stop.set()
                self.stop = None

    def _hold(self, stop, ready):
        try:
            got = self.setter(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
        except Exception as e:
            got = 0
            log.warning("Couldn't ask Windows to stay awake: %s", e)
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
