# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Safety net: copy the next few nights of the schedule into the controller's
own calendar timers, so the lights still come on and go off if this computer
or the internet goes down.

How it stays safe
- Before every write, the controller's full state is saved to
  data/controller-backups/ (last 20 kept).
- It only ever creates, changes or deletes calendar entries and saved
  patterns that it made itself (their ids are recorded in data/safety.json).
  Entries and patterns made in the Trimlight app are never touched.
- After writing, it reads the controller back and checks every entry. On any
  mismatch it deletes what it wrote and reports the problem; the lights then
  simply run without a safety net.
- While the app runs, it still drives the lights live. Between scheduled
  windows it leaves the controller in Timer mode (instead of Off) so the
  copied timers can take over if the app stops.

Limits (shown to the user)
- Fallback times are the planned start/end minutes; weather, minute-rotation,
  sliders and manual changes need the app.
- A window that runs past midnight is covered only until 23:59.
- If the app stops while the lights are on, they stay on until it returns,
  because during a window the controller is in Manual mode.
"""
import hashlib
import json
import logging
import os
import threading
from datetime import date, datetime, time, timedelta
from pathlib import Path

from .api import TrimlightError

log = logging.getLogger("eaveluxos.safety")
MAX_EFFECTS = 60
MAX_CALENDAR = 60
PREFIX = "Auto "


def _same_effect(a: dict, b: dict) -> bool:
    keys = ("category", "mode", "speed", "brightness")
    if any(a.get(k) != b.get(k) for k in keys):
        return False
    if b.get("category") == 0:
        return a.get("pixelLen") == b.get("pixelLen") and bool(a.get("reverse")) == bool(b.get("reverse"))
    def norm(px):  # merge adjacent equal runs, so a split (60+30) equals the original 90
        runs = []
        for p in sorted(px or [], key=lambda p: p.get("index", 0)):
            k = (p.get("color"), bool(p.get("disable")))
            if runs and runs[-1][0] == k:
                runs[-1][1] += p.get("count", 0)
            else:
                runs.append([k, p.get("count", 0)])
        return runs
    return norm(a.get("pixels")) == norm(b.get("pixels"))


class SafetyNet:
    def __init__(self, data_dir: Path):
        self.dir = data_dir
        self.path = data_dir / "safety.json"
        self.backup_dir = data_dir / "controller-backups"
        self.lock = threading.RLock()
        try:
            self.state = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.state = {}
        self.state.setdefault("devices", {})
        self.retry_at = 0.0

    # ---------------------------------------------------------------- state
    def _dev(self, dev_id: str) -> dict:
        d = self.state["devices"].setdefault(dev_id, {})
        d.setdefault("effects", {})     # slot key -> controller effect id
        d.setdefault("calendar", [])    # calendar ids we own
        return d

    def _save(self):
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)

    def ready(self, dev_id: str, today: date) -> bool:
        """True when this controller holds a verified copy covering today."""
        with self.lock:
            d = self.state["devices"].get(dev_id) or {}
            return bool(d.get("ok") and d.get("covers_until", "") >= today.isoformat())

    def summary(self) -> dict:
        with self.lock:
            return {k: {x: v.get(x) for x in ("ok", "message", "last_sync", "last_sync_label", "covers_until", "entries", "conflicts", "backup")}
                    for k, v in self.state["devices"].items()}

    # ---------------------------------------------------------------- plan
    def plan(self, cfg, now: datetime, offset_min: int = 0):
        """Calendar entries for today and the next days, plus the patterns
        they need. Today's entry is kept even after it ends, so the plan (and
        the writes) only change once a day or when settings change."""
        loc, sch = cfg.loc, cfg.schedule
        entries, slots = [], {}
        today = now.date()
        off = timedelta(minutes=offset_min)
        for i in range(cfg.safety["days"]):
            d = today + timedelta(days=i)
            # Every stretch the lights are on that day (for example a morning
            # and an evening rule), as the scheduler would run them.
            for p in sch.day_plans(d):
                w = p.window
                eff, _ = w.rule.pick(w.start, w.start)
                levels = dict(w.rule.levels)
                start = p.start + off
                last = datetime.combine(start.date(), time(23, 59), tzinfo=start.tzinfo)
                end = min(p.end + off, last)
                if end <= start:
                    continue
                slot = f"{eff.key}|{json.dumps(levels, sort_keys=True)}"
                slots[slot] = (eff, levels)
                entries.append({"month": start.month, "day": start.day, "start": [start.hour, start.minute],
                                "end": [end.hour, end.minute], "slot": slot, "label": eff.label, "rule": w.rule.name})
        return entries, slots

    @staticmethod
    def plan_hash(entries, slots) -> str:
        blob = json.dumps({"e": entries, "s": {k: (v[0].kind, v[0].payload, v[0].saved_name, v[0].saved_id, v[1])
                                               for k, v in slots.items()}}, sort_keys=True, default=str)
        return hashlib.sha256(blob.encode()).hexdigest()[:16]

    def due(self, dev_ids, h: str, today: date, now_ts: float) -> bool:
        with self.lock:
            for dev in dev_ids:
                d = self.state["devices"].get(dev) or {}
                if d.get("hash") != h or d.get("synced_on") != today.isoformat():
                    return now_ts >= self.retry_at
            return False

    # ---------------------------------------------------------------- writing
    def _backup(self, dev_id: str, detail: dict) -> str:
        """Save the controller's state. The very first backup (before this app
        ever wrote to the controller) is kept forever as <id>-original.json;
        the 20 most recent others are kept too."""
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        body = json.dumps(detail, indent=2)
        original = self.backup_dir / f"{dev_id}-original.json"
        if not original.exists():
            original.write_text(body, encoding="utf-8")
        name = f"{dev_id}-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.json"  # unique, sortable
        (self.backup_dir / name).write_text(body, encoding="utf-8")
        files = sorted(f for f in self.backup_dir.glob(f"{dev_id}-*.json") if f != original)
        for old in files[:-20]:
            old.unlink(missing_ok=True)
        return name

    def sync(self, api, cfg, dev_ids, now: datetime, note=lambda m, lvl=logging.INFO: None):
        entries, slots = self.plan(cfg, now, getattr(api, "clock_offset_min", 0))
        h = self.plan_hash(entries, slots)
        failed = False
        for dev in dev_ids:
            try:
                self._sync_one(api, dev, entries, slots, now)
                with self.lock:
                    d = self._dev(dev)
                    d.update(ok=True, hash=h, synced_on=now.date().isoformat(), last_sync=now.isoformat(timespec="minutes"),
                             last_sync_label=now.strftime("%b %d, %I:%M %p").replace(" 0", " "),
                             covers_until=(now.date() + timedelta(days=cfg.safety["days"] - 1)).isoformat(),
                             message=f"{len(d['calendar'])} nights copied to the controller.")
                    self._save()
                note(f"Safety net updated: {len(entries)} night(s) copied to the controller.")
            except (TrimlightError, ValueError) as e:
                failed = True
                with self.lock:
                    d = self._dev(dev)
                    d.update(ok=False, hash=None, message=str(e), last_sync=now.isoformat(timespec="minutes"),
                             last_sync_label=now.strftime("%b %d, %I:%M %p").replace(" 0", " "))
                    self._save()
                note(f"Safety net not updated: {e}", logging.WARNING)
        import time as _t
        self.retry_at = _t.time() + (1800 if failed else 0)
        return not failed

    def _sync_one(self, api, dev: str, entries, slots, now: datetime):
        det = api.get_device(dev, now)
        with self.lock:
            st = self._dev(dev)
            st["backup"] = self._backup(dev, det)
        lib = {e.get("id"): e for e in det.get("effects", [])}
        cal = {c.get("id"): c for c in det.get("calendar", [])}
        owned_eff = {k: v for k, v in st["effects"].items() if v in lib}
        owned_cal = [i for i in st["calendar"] if i in cal]
        conflicts = []
        if any(x.get("enable") for x in det.get("daily", [])):
            conflicts.append("daily")
        user_cal = [i for i in cal if i not in owned_cal]
        if user_cal:
            conflicts.append(f"calendar:{len(user_cal)}")

        # 1. patterns the entries need
        ids = {}
        new_needed = sum(1 for k, (e, _) in slots.items() if e.kind != "saved" and k not in owned_eff)
        dropping = sum(1 for k in owned_eff if k not in slots)
        if len(lib) - dropping + new_needed > MAX_EFFECTS:
            raise ValueError(f"The controller's pattern library is too full ({len(lib)}/{MAX_EFFECTS}). "
                             "Delete a few patterns in the Trimlight app or shorten the safety net.")
        def persist_effects():
            with self.lock:
                st["effects"] = dict(owned_eff)
                self._save()

        for k in [k for k in owned_eff if k not in slots]:   # free slots first
            api.effect_delete(dev, owned_eff[k])
            owned_eff.pop(k)
            persist_effects()
        for k, (eff, levels) in slots.items():
            if eff.kind == "saved":
                want = (eff.saved_name or "").strip().lower()
                found = next((e for e in lib.values() if (eff.saved_id is not None and e.get("id") == eff.saved_id)
                              or str(e.get("name", "")).strip().lower() == want), None)
                if not found:
                    raise ValueError(f"\u201c{eff.label}\u201d isn't saved on the controller any more.")
                ids[k] = found["id"]
                continue
            payload = {**eff.payload, **levels, "name": (PREFIX + eff.label)[:30]}
            if k in owned_eff and _same_effect(lib[owned_eff[k]], payload):
                ids[k] = owned_eff[k]
                continue
            payload["id"] = owned_eff.get(k, -1)
            r = api.save_effect(dev, payload) or {}
            if r.get("id") is None:
                raise ValueError(f"The controller didn't confirm saving \u201c{eff.label}\u201d.")
            ids[k] = owned_eff[k] = r["id"]
            persist_effects()  # record ownership right away, so a failure later can't orphan it

        # 2. calendar entries: reuse our ids, then free ones; never touch the user's
        free = [i for i in range(MAX_CALENDAR) if i not in cal]
        pool = owned_cal + free
        if len(entries) > len(pool):
            raise ValueError("Not enough free calendar entries on the controller. Delete some in the Trimlight app.")
        owned_set = set(owned_cal)

        def persist_calendar():
            with self.lock:
                st["calendar"] = sorted(owned_set)
                self._save()

        written = []
        for entry, cid in zip(entries, pool):
            payload = {"id": cid, "effectId": ids[entry["slot"]],
                       "startDate": {"month": entry["month"], "day": entry["day"]},
                       "endDate": {"month": entry["month"], "day": entry["day"]},
                       "startTime": {"hours": entry["start"][0], "minutes": entry["start"][1]},
                       "endTime": {"hours": entry["end"][0], "minutes": entry["end"][1]}}
            owned_set.add(cid)          # claim before writing: if the reply is lost, we still own it
            persist_calendar()
            r = api.calendar_save(dev, payload) or {}
            rid = r.get("id", cid)
            if rid != cid:
                owned_set.add(rid)
                persist_calendar()
            written.append((rid, payload))
        keep = {c for c, _ in written}
        for cid in sorted(owned_set - keep):
            api.calendar_delete(dev, cid)
            owned_set.discard(cid)
            persist_calendar()
        with self.lock:
            st["conflicts"] = conflicts
            st["entries"] = [{"date": f"{e['month']:02d}-{e['day']:02d}", "on": "%02d:%02d" % tuple(e["start"]),
                              "off": "%02d:%02d" % tuple(e["end"]), "pattern": e["label"]} for e in entries]
            self._save()

        # 3. read back and verify every entry
        det2 = api.get_device(dev, now)
        cal2 = {c.get("id"): c for c in det2.get("calendar", [])}
        lib2 = {e.get("id") for e in det2.get("effects", [])}
        bad = []
        for cid, p in written:
            c = cal2.get(cid)
            if not c or any(c.get(k) != p[k] for k in ("effectId", "startDate", "endDate", "startTime", "endTime")):
                bad.append(cid)
        missing_eff = [i for i in ids.values() if i not in lib2]
        if bad or missing_eff:
            for cid in sorted(owned_set):  # take back what we wrote; leave everything else alone
                try:
                    api.calendar_delete(dev, cid)
                    owned_set.discard(cid)
                except TrimlightError:
                    pass                    # still recorded as ours; removed on the next sync
            persist_calendar()
            raise ValueError("The controller's timers didn't read back as written, so the copy was removed "
                             f"({len(bad)} entr{'y' if len(bad) == 1 else 'ies'} differed). The app keeps running the lights.")

    def remove(self, api, dev_ids, now: datetime, note=lambda m, lvl=logging.INFO: None) -> bool:
        """Turn the safety net off: delete only what it created. False if
        something couldn't be removed yet (it's retried later)."""
        ok = True
        for dev in dev_ids:
            with self.lock:
                st = self.state["devices"].get(dev)
            if not st or not (st.get("calendar") or st.get("effects")):
                continue
            try:
                det = api.get_device(dev, now)
                with self.lock:
                    st["backup"] = self._backup(dev, det)
                cal = {c.get("id") for c in det.get("calendar", [])}
                lib = {e.get("id") for e in det.get("effects", [])}
                for cid in st.get("calendar", []):
                    if cid in cal:
                        api.calendar_delete(dev, cid)
                for eid in st.get("effects", {}).values():
                    if eid in lib:
                        api.effect_delete(dev, eid)
                with self.lock:
                    self.state["devices"][dev] = {"ok": False, "message": "Safety net is off.", "effects": {}, "calendar": []}
                    self._save()
                note("Safety net removed from the controller.")
            except TrimlightError as e:
                ok = False
                note(f"Couldn't remove the safety net yet: {e}", logging.WARNING)
        return ok

    def disable_app_daily_timers(self, api, dev: str, now: datetime) -> int:
        """Turn off the Trimlight app's daily timers (they'd also run in Timer mode)."""
        det = api.get_device(dev, now)
        with self.lock:
            self._dev(dev)["backup"] = self._backup(dev, det)
        n = 0
        for x in det.get("daily", []):
            if x.get("enable"):
                payload = {k: x[k] for k in ("id", "effectId", "repetition", "startTime", "endTime") if k in x}
                payload.update(enable=False, currentDate={"month": now.month, "day": now.day})
                api.daily_save(dev, payload)
                n += 1
        return n
