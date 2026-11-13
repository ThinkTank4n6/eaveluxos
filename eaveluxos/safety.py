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


def _resync(api, dev, now):
    f = getattr(api, "resync", None)
    if f:
        f(dev, now)


class CalendarConflict(ValueError):
    """The Trimlight app's own calendar timers cover the coming nights."""
_CAL_KEYS = ("effectId", "startDate", "endDate", "startTime", "endTime")
MAX_EFFECTS = 60
MAX_CALENDAR = 60
PREFIX = "Auto "


def _cal_overlaps(c: dict, days: list) -> bool:
    """Does a calendar entry (month/day range, no year) fall on any of days?
    An entry whose dates can't be read counts as overlapping."""
    try:
        s = (int(c["startDate"]["month"]), int(c["startDate"]["day"]))
        e = (int(c["endDate"]["month"]), int(c["endDate"]["day"]))
    except (KeyError, TypeError, ValueError):
        return True
    for d in days:
        md = (d.month, d.day)
        if (s <= md <= e) if s <= e else (md >= s or md <= e):   # wraps New Year
            return True
    return False


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
        self.repaired = False

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
        """True when this controller holds a verified copy covering today and
        nothing else on it would run in Timer mode (the Trimlight app's daily
        timers, or its calendar events on the coming nights): those would turn
        the lights on while the schedule says off, and the app can't tell."""
        with self.lock:
            d = self.state["devices"].get(dev_id) or {}
            return bool(d.get("ok") and not d.get("conflicts") and d.get("covers_until", "") >= today.isoformat())

    def check_live(self, dev_id: str, detail: dict) -> str | None:
        """Compare a fresh read of the controller with what the last sync
        wrote. If the copy was changed or cleared since (the Trimlight app, a
        reset), stop relying on it and have it written again. Returns a
        message when that happened."""
        with self.lock:
            d = self.state["devices"].get(dev_id)
            if not (d and d.get("ok")):
                return None
            written = d.get("written")
            if written is None:      # synced by an older version: copy it again to start checking
                d["hash"] = None
                self.retry_at = 0
                self._save()
                return None
            cal = {str(c.get("id")): c for c in detail.get("calendar", []) or []}
            lib = {e.get("id") for e in detail.get("effects", []) or []}
            changed = [cid for cid, p in written.items()
                       if cid not in cal or any(cal[cid].get(k) != p[k] for k in _CAL_KEYS)]
            gone = [i for i in d.get("written_effects", []) if i not in lib]
            if not (changed or gone):
                return None
            msg = "The timer copy on the controller was changed outside this app, so it's being copied again."
            d.update(ok=False, hash=None, message=msg)
            self.retry_at = 0
            self._save()
            return msg

    def summary(self) -> dict:
        with self.lock:
            out = {k: {x: v.get(x) for x in ("ok", "message", "last_sync", "last_sync_label", "covers_until", "entries", "conflicts", "backup")}
                   for k, v in self.state["devices"].items()}
            for v in out.values():   # a copy held back by the Trimlight app's own timers isn't armed
                v["ok"] = bool(v["ok"] and not v["conflicts"])
            return out

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
        # Unique, sortable names. Windows' clock can return the same
        # microsecond for backups made in quick succession, so never reuse a
        # name: step forward a microsecond until it's free ("x" refuses to
        # overwrite).
        t = datetime.now()
        while True:
            name = f"{dev_id}-{t.strftime('%Y%m%d-%H%M%S-%f')}.json"
            try:
                with open(self.backup_dir / name, "x", encoding="utf-8") as f:
                    f.write(body)
                break
            except FileExistsError:
                t += timedelta(microseconds=1)
        files = sorted(f for f in self.backup_dir.glob(f"{dev_id}-*.json") if f != original)
        for old in files[:-20]:
            old.unlink(missing_ok=True)
        return name

    def sync(self, api, cfg, dev_ids, now: datetime, note=lambda m, lvl=logging.INFO: None):
        entries, slots = self.plan(cfg, now, getattr(api, "clock_offset_min", 0))
        h = self.plan_hash(entries, slots)
        failed = False
        for dev in dev_ids:
            self.repaired = False
            try:
                self._sync_one(api, dev, entries, slots, now, cfg.safety["days"])
                with self.lock:
                    d = self._dev(dev)
                    msg = f"{len(d['calendar'])} nights copied to the controller."
                    if d.get("conflicts"):
                        msg += (" Not used yet: the Trimlight app's own timers would also run when the controller is "
                                "left in Timer mode. Turn them off (see below), then choose Update now.")
                    d.update(ok=True, hash=h, synced_on=now.date().isoformat(), last_sync=now.isoformat(timespec="minutes"),
                             last_sync_label=now.strftime("%b %d, %I:%M %p").replace(" 0", " "),
                             covers_until=(now.date() + timedelta(days=cfg.safety["days"] - 1)).isoformat(),
                             message=msg)
                    self._save()
                note(f"Safety net updated: {len(entries)} night(s) copied to the controller."
                     + (" It stays off until the Trimlight app's own timers are turned off." if d.get("conflicts") else ""),
                     logging.WARNING if d.get("conflicts") else logging.INFO)
            except (TrimlightError, ValueError) as e:
                failed = True
                with self.lock:
                    d = self._dev(dev)
                    d.update(ok=False, hash=None, message=str(e), last_sync=now.isoformat(timespec="minutes"),
                             last_sync_label=now.strftime("%b %d, %I:%M %p").replace(" 0", " "))
                    self._save()
                note(f"Safety net not updated: {e}", logging.WARNING)
            if self.repaired:
                note("Trimlight couldn't read the controller because two of the safety net's patterns had the same "
                     "number; they were removed and it reads normally again.", logging.WARNING)
        import time as _t
        self.retry_at = _t.time() + (1800 if failed else 0)
        return not failed

    def _user_effect_ids(self, dev: str) -> set:
        """Pattern ids that were on the controller before this app ever wrote
        to it (the -original backup): never deleted by a repair."""
        try:
            det = json.loads((self.backup_dir / f"{dev}-original.json").read_text(encoding="utf-8"))
            return {e.get("id") for e in det.get("effects", []) or []}
        except (OSError, ValueError, AttributeError):
            return set()

    def _read(self, api, dev: str, now: datetime) -> dict:
        """Read the controller. If Trimlight's cloud can't read its copy of it
        (two patterns with the same number: a save that the cloud numbered
        twice), delete the patterns this app saved there and read again."""
        try:
            return api.get_device(dev, now)
        except TrimlightError as e:
            if not e.unreadable:
                raise
            first = e
        with self.lock:
            st = self._dev(dev)
            mine = sorted(set(st["effects"].values()) - self._user_effect_ids(dev), key=str)
        if not mine:
            raise first
        log.warning("Trimlight can't read the controller; removing the safety net's own patterns %s to repair it.", mine)
        todo = list(mine)
        for _ in range(4):   # a duplicate number needs one delete per copy
            for eid in todo:
                try:
                    api.effect_delete(dev, eid)
                except TrimlightError:
                    pass
            _resync(api, dev, now)
            try:
                det = api.get_device(dev, now, resync=False)
            except TrimlightError as e:
                if not e.unreadable:
                    raise
                continue
            lib = {x.get("id") for x in det.get("effects", [])}
            todo = [eid for eid in mine if eid in lib]
            if todo:
                continue        # readable again, but a copy of ours is still there
            with self.lock:
                st["effects"] = {k: v for k, v in st["effects"].items() if v in lib and v not in mine}
                self._save()
            self.repaired = True
            log.warning("Repaired: Trimlight can read the controller again.")
            return det
        raise first

    def _sync_one(self, api, dev: str, entries, slots, now: datetime, days: int = 7):
        det = self._read(api, dev, now)
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
        span = [now.date() + timedelta(days=k) for k in range(days)]
        user_cal = [i for i in cal if i not in owned_cal and _cal_overlaps(cal[i], span)]
        if user_cal:
            conflicts.append(f"calendar:{len(user_cal)}")
            # The controller refuses timers that cross its own calendar events
            # ("The calendar schedules cannot be crossed"), and in Timer mode
            # both would run anyway. Write nothing; take back what's ours.
            for cid in list(owned_cal):
                try:
                    api.calendar_delete(dev, cid)
                    owned_cal.remove(cid)
                except TrimlightError:
                    pass
            for k, eid in list(owned_eff.items()):
                try:
                    api.effect_delete(dev, eid)
                    owned_eff.pop(k)
                except TrimlightError:
                    pass
            names = {e.get("id"): e.get("name") for e in det.get("effects", [])}
            what = ", ".join(sorted({str(names.get(cal[i].get("effectId")) or "a pattern") for i in user_cal}))
            with self.lock:
                st.update(effects=dict(owned_eff), calendar=sorted(owned_cal), conflicts=conflicts, entries=[])
                st.pop("written", None)
                self._save()
            raise CalendarConflict(
                f"Not armed: the controller already has {len(user_cal)} calendar timer{'s' if len(user_cal) != 1 else ''} "
                f"from the Trimlight app on the coming nights ({what}), and it won't take a second set on the same "
                "nights. Those timers already run the lights without this computer. To use the safety net instead, "
                "delete them in the Trimlight Edge app (your schedule here is unaffected), then choose Update now.")

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
        taken = set(lib)
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
            new = payload["id"] == -1
            r = api.save_effect(dev, payload) or {}
            if r.get("id") is None:
                raise ValueError(f"The controller didn't confirm saving \u201c{eff.label}\u201d.")
            if new and r["id"] in taken:
                # Trimlight numbered a new pattern with a number already in
                # use, which leaves its copy of the controller unreadable.
                # Remove it (never the user's) and stop.
                if r["id"] in set(owned_eff.values()) - self._user_effect_ids(dev):
                    with self.lock:
                        st["effects"] = {**owned_eff, k: r["id"]}
                        self._save()
                    self._read(api, dev, now)
                raise ValueError("Trimlight gave a new pattern a number that was already in use, so the safety net "
                                 "stopped. It will try again later.")
            ids[k] = owned_eff[k] = r["id"]
            taken.add(r["id"])
            persist_effects()  # record ownership right away, so a failure later can't orphan it
            if new:
                # Let the cloud catch up before the next new pattern: saving
                # two in a row can get both the same number.
                _resync(api, dev, now)

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
        try:
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
        except TrimlightError:
            # Part of the new copy is on the controller next to part of the old
            # one. Don't leave that mix to run if this app stops: take back
            # everything of ours (the lights are driven live meanwhile).
            self._take_back(api, dev, owned_set, persist_calendar)
            raise
        with self.lock:
            st["conflicts"] = conflicts
            st["entries"] = [{"date": f"{e['month']:02d}-{e['day']:02d}", "on": "%02d:%02d" % tuple(e["start"]),
                              "off": "%02d:%02d" % tuple(e["end"]), "pattern": e["label"]} for e in entries]
            self._save()

        # 3. read back and verify every entry
        det2 = self._read(api, dev, now)
        cal2 = {c.get("id"): c for c in det2.get("calendar", [])}
        lib2 = {e.get("id") for e in det2.get("effects", [])}
        bad = []
        for cid, p in written:
            c = cal2.get(cid)
            if not c or any(c.get(k) != p[k] for k in _CAL_KEYS):
                bad.append(cid)
        missing_eff = [i for i in ids.values() if i not in lib2]
        if not (bad or missing_eff):
            with self.lock:   # what the live check compares against later
                st["written"] = {str(cid): {k: p[k] for k in _CAL_KEYS} for cid, p in written}
                st["written_effects"] = sorted(set(ids.values()))
                self._save()
        if bad or missing_eff:
            self._take_back(api, dev, owned_set, persist_calendar)
            raise ValueError("The controller's timers didn't read back as written, so the copy was removed "
                             f"({len(bad)} entr{'y' if len(bad) == 1 else 'ies'} differed). The app keeps running the lights.")

    @staticmethod
    def _take_back(api, dev, owned_set, persist):
        """Delete every calendar entry of ours; leave everything else alone."""
        for cid in sorted(owned_set):
            try:
                api.calendar_delete(dev, cid)
                owned_set.discard(cid)
            except TrimlightError:
                pass                    # still recorded as ours; removed on the next sync
        persist()

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
                det = self._read(api, dev, now)
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
