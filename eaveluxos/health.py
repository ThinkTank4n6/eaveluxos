# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Controller health (4.15): how each controller has been answering.

Every request to Trimlight's cloud that names a controller is counted here
(api.py calls record()): whether it worked, how long it took, and what went
wrong if it didn't. Kept per controller and per day for the last 14 days in
data/health.json (written at most once a minute), with the last request and
the last error. The Health page adds what the cloud says now (online,
firmware) and a check over the home network."""
from __future__ import annotations

import json
import os
import threading
import time
from datetime import date, timedelta
from pathlib import Path

DAYS = 14
SAVE_EVERY = 60.0


class Health:
    def __init__(self, folder: Path | None, today=date.today, now=time.time):
        self.path = Path(folder) / "health.json" if folder else None
        self.today, self.now = today, now
        self.lock = threading.Lock()
        self.data = {"days": {}, "last": {}, "errors": {}, "lan": {}}
        self.dirty, self.saved = False, 0.0
        if self.path and self.path.is_file():
            try:
                d = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(d, dict):
                    for k in self.data:
                        if isinstance(d.get(k), dict):
                            self.data[k] = d[k]
            except (OSError, ValueError):
                pass

    def record(self, dev: str, path: str, ms: float, ok: bool, error: str | None = None, code=None):
        if not isinstance(dev, str) or not dev:
            return
        day = self.today().isoformat()
        with self.lock:
            days = self.data["days"].setdefault(dev, {})
            d = days.setdefault(day, {"ok": 0, "fail": 0, "ms": 0.0, "max": 0.0})
            d["ok" if ok else "fail"] += 1
            if ok:
                d["ms"] += ms
                d["max"] = max(d["max"], ms)
            if len(days) > DAYS:
                for k in sorted(days)[:-DAYS]:
                    del days[k]
            self.data["last"][dev] = {"at": self.now(), "ok": ok, "ms": round(ms), "what": path.rsplit("/", 1)[-1]}
            if not ok:
                self.data["errors"][dev] = {"at": self.now(), "error": str(error or "")[:300], "code": code,
                                            "what": path.rsplit("/", 1)[-1]}
            self.dirty = True
        self.save()

    def record_lan(self, dev: str, ms: float | None, error: str | None = None):
        with self.lock:
            self.data["lan"][dev] = {"at": self.now(), "ms": None if ms is None else round(ms), "error": error}
            self.dirty = True
        self.save(force=True)

    def save(self, force: bool = False):
        if not self.path:
            return
        with self.lock:
            if not self.dirty or (not force and self.now() - self.saved < SAVE_EVERY):
                return
            text = json.dumps(self.data)
            self.dirty, self.saved = False, self.now()
        try:
            tmp = self.path.with_name(f".health.{os.getpid()}.tmp")
            tmp.write_text(text, encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError:
            pass

    def summary(self, dev: str) -> dict:
        """The last 14 days (oldest first, days without requests included),
        the last day's numbers, the last request and the last error."""
        t = self.today()
        with self.lock:
            days = dict(self.data["days"].get(dev, {}))
            last, err, lan = self.data["last"].get(dev), self.data["errors"].get(dev), self.data["lan"].get(dev)
        rows = []
        for i in range(DAYS - 1, -1, -1):
            k = (t - timedelta(days=i)).isoformat()
            d = days.get(k) or {"ok": 0, "fail": 0, "ms": 0.0, "max": 0.0}
            rows.append({"day": k, "ok": d["ok"], "fail": d["fail"], "avg": round(d["ms"] / d["ok"]) if d["ok"] else None,
                         "max": round(d["max"]) if d["ok"] else None})
        today = rows[-1]
        total = today["ok"] + today["fail"]
        week = rows[-7:]
        wok, wfail = sum(r["ok"] for r in week), sum(r["fail"] for r in week)
        return {"days": rows, "today": today, "success": round(100 * today["ok"] / total) if total else None,
                "week": {"ok": wok, "fail": wfail, "success": round(100 * wok / (wok + wfail)) if wok + wfail else None},
                "last": last, "error": err, "lan": lan}
