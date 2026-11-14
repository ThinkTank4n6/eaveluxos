# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""How long the lights were on, per month (3.15).

The scheduler calls add() on every pass (about every 20 seconds) with whether
the lights are on as far as this app knows. Time between passes counts only
when it's short (a computer that slept or an app that was stopped adds
nothing for the gap), so the totals can only be an undercount, never inflated.
Kept in data/runtime.json, 24 months at most.
"""
import json
import logging
import os
import re
import threading
import time
from datetime import datetime
from pathlib import Path

log = logging.getLogger("eaveluxos.runtime")
MAX_GAP = 120          # seconds between passes that still count
SAVE_EVERY = 300
KEEP = 24
MONTH_RE = re.compile(r"\d{4}-\d{2}")


class Runtime:
    def __init__(self, data_dir: Path | None, now=time.time, tz=None):
        self.path = Path(data_dir) / "runtime.json" if data_dir else None
        self.now = now
        self.tz = tz
        self.lock = threading.Lock()
        self.months = self._load()
        self.last = None            # (time, on) of the previous pass
        self.saved_at = now()

    def _load(self) -> dict:
        if not self.path:
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if not isinstance(raw, dict):
            return {}
        return {k: float(v) for k, v in raw.items()
                if MONTH_RE.fullmatch(str(k)) and isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v <= 31 * 86400}

    def _tz(self):
        """tz may be a zone or a function returning the current one (the
        controller passes one, so a changed time zone applies at once)."""
        return self.tz() if callable(self.tz) else self.tz

    def _month(self, t: float) -> str:
        return datetime.fromtimestamp(t, self._tz()).strftime("%Y-%m")

    def add(self, on: bool):
        t = self.now()
        with self.lock:
            prev, self.last = self.last, (t, bool(on))
            if prev is None or not prev[1]:
                return
            gap = t - prev[0]
            if not 0 < gap <= MAX_GAP:
                return
            m = self._month(t)
            self.months[m] = min(31 * 86400, self.months.get(m, 0.0) + gap)
            for old in sorted(self.months)[:-KEEP]:
                self.months.pop(old)
            due = t - self.saved_at >= SAVE_EVERY
        if due:
            self.save()

    def save(self):
        if not self.path:
            return
        with self.lock:
            body = json.dumps({k: round(v) for k, v in sorted(self.months.items())})
            self.saved_at = self.now()
        try:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(body, encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError as e:
            log.debug("couldn't save runtime: %s", e)

    def summary(self, months: int = 12) -> list[dict]:
        """The last `months` months, oldest first, hours rounded to 0.1."""
        t = self.now()
        cur = datetime.fromtimestamp(t, self._tz())
        y, mo = cur.year, cur.month
        keys = []
        for _ in range(months):
            keys.append(f"{y:04d}-{mo:02d}")
            mo -= 1
            if mo == 0:
                y, mo = y - 1, 12
        with self.lock:
            return [{"month": k, "hours": round(self.months.get(k, 0.0) / 3600, 1)} for k in reversed(keys)]
