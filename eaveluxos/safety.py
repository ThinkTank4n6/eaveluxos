# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Safety net: copy the next few nights of the schedule into the controller's
own calendar timers, so the lights still come on and go off if this computer
or the internet goes down.

How it stays safe (4.2.1, after a pattern save through Trimlight's cloud
left a controller unreadable, error 12006, and a reset lost its patterns)
- It never saves or deletes patterns (4.3: not even its own old "Auto"
  copies when it is turned off). Each night uses a pattern already saved on the
  controller with the same name; a night whose pattern isn't there is
  skipped and listed. Only calendar entries are written, and only its own
  (their ids are recorded in data/safety.json).
- It writes only when the controller is settled: two readings at least
  SETTLE seconds apart must match (patterns, calendar, daily timers), and
  never within HOLD seconds of a music show or the local link.
- Before every write, the controller's full state is saved to
  data/controller-backups/ (last 20 kept).
- After writing, it reads the controller back and checks every entry. On any
  mismatch, or if Trimlight's cloud can't read the controller (12006), it
  takes back what it wrote and halts: no more writes until it is turned off
  and on again.
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
import time as _time
from datetime import date, datetime, time, timedelta
from pathlib import Path

from .api import TrimlightError

log = logging.getLogger("eaveluxos.safety")


def _is_auto(e) -> bool:
    """A pattern this app saved (its name starts with "Auto "). Numbers can be
    reused after a delete, so a number alone never proves a pattern is ours."""
    return str((e or {}).get("name", "")).startswith(PREFIX)


class CalendarConflict(ValueError):
    """The Trimlight app's own calendar timers cover the coming nights."""


class Halt(ValueError):
    """Something looked wrong on the controller: stop writing until the
    backup timer is turned off and on again (4.2.1)."""


class Waiting(Exception):
    """The controller isn't settled yet; try again in `seconds`."""
    def __init__(self, msg, seconds):
        super().__init__(msg)
        self.seconds = seconds


def one_per_day(entries: list) -> tuple[list, list]:
    """At most one calendar timer per date (4.3.9). The controller won't take
    two on the same date ("The calendar schedules cannot be crossed", code
    12000, Nov 13, 2026); the Trimlight app's own timers are avoided for the
    same reason. Two stretches with the same pattern become one from the
    first on to the last off; otherwise the longest stays. Returns (kept,
    dropped)."""
    by_day: dict = {}
    for e in entries:
        by_day.setdefault((e["month"], e["day"]), []).append(e)
    kept, dropped = [], []
    for day in by_day.values():
        if len(day) == 1:
            kept.append(day[0])
            continue
        mins = lambda e: (e["end"][0] * 60 + e["end"][1]) - (e["start"][0] * 60 + e["start"][1])
        if len({e["slot"] for e in day}) == 1:
            first, last = min(day, key=lambda e: e["start"]), max(day, key=lambda e: e["end"])
            kept.append({**first, "end": last["end"]})
            continue
        best = max(day, key=mins)
        kept.append(best)
        dropped += [e for e in day if e is not best]
    return kept, dropped


def fingerprint(detail: dict) -> str:
    """What must stay the same between two readings before a write: the
    patterns (numbers and names), calendar entries and daily timers."""
    eff = sorted([e.get("id"), str(e.get("name", ""))] for e in detail.get("effects", []) or [])
    blob = json.dumps({"e": eff, "c": detail.get("calendar") or [], "d": detail.get("daily") or []},
                      sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]
_CAL_KEYS = ("effectId", "startDate", "endDate", "startTime", "endTime")
MAX_CALENDAR = 60
PREFIX = "Auto "
# 4.3.9: paused. Every "can't read the controller" (12006) so far came within
# minutes of the backup timer writing calendar timers through Trimlight's
# cloud: Nov 13 17:22 -> 17:26, Nov 15 17:52 -> 17:56, Nov 16 13:46 -> 13:50.
# Until that is understood it writes nothing; turned on, it stays off and
# says why. (Its own entries are still removed as before.)
PAUSED = True
SETTLE = 120      # seconds between the two matching readings before a write
READBACK_PAUSES = (0, 5, 20)   # seconds before each read-back (4.3.8: the cloud's copy can lag behind)
HOLD = 900        # no writes this long after a music show or local-link use


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


def for_device(entries, slots, dev: str):
    """The plan as one controller runs it: a split pattern (3.17) becomes
    that controller's own pattern, and its nights are left out where the
    split has this controller off."""
    out_slots, keep = {}, []
    for k, (eff, levels) in slots.items():
        part = eff.for_device(dev) if eff.kind == "split" else eff
        if part is not None:
            out_slots[k] = (part, levels)
    for e in entries:
        if e["slot"] in out_slots:
            keep.append(dict(e, label=out_slots[e["slot"]][0].label))
    return keep, out_slots


def _same_effect(a: dict, b: dict) -> bool:
    keys = ("category", "mode", "speed", "brightness")
    if any(a.get(k) != b.get(k) for k in keys):
        return False
    if b.get("category") == 0:
        return a.get("pixelLen") == b.get("pixelLen") and bool(a.get("reverse")) == bool(b.get("reverse"))
    def norm(px):  # merge adjacent equal runs, so a split (60+30) equals the original 90
        runs = []
        for p in sorted(px or [], key=lambda p: p.get("index", 0)):
            if not p.get("count"):
                continue          # 4.28.2: an empty slot (the controller reports all 30) shows nothing
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
        self.hold_until = 0.0
        self.clock = _time.time      # tests replace it
        self.settle = SETTLE
        self.readback_pauses = READBACK_PAUSES

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

    # ---------------------------------------------------------------- guards
    def hold(self, seconds: float = HOLD):
        """No writes for `seconds` (a music show or the local link is busy
        with the controller)."""
        with self.lock:
            self.hold_until = max(self.hold_until, self.clock() + seconds)

    def held(self) -> bool:
        return self.clock() < self.hold_until

    @property
    def halted(self) -> dict | None:
        return self.state.get("halted")

    def _halt(self, why: str):
        with self.lock:
            self.state["halted"] = {"at": datetime.now().isoformat(timespec="minutes"), "why": why}
            for d in self.state["devices"].values():
                d["ok"] = False
            self._save()

    def clear_halt(self):
        with self.lock:
            if self.state.pop("halted", None) is not None:
                self._save()

    def ready(self, dev_id: str, today: date) -> bool:
        """True when this controller holds a verified copy covering today and
        nothing else on it would run in Timer mode (the Trimlight app's daily
        timers, or its calendar events on the coming nights): those would turn
        the lights on while the schedule says off, and the app can't tell."""
        with self.lock:
            d = self.state["devices"].get(dev_id) or {}
            return bool(d.get("ok") and not d.get("conflicts") and d.get("covers_until", "") >= today.isoformat())

    def _prune(self, dev_id: str, detail: dict):
        """After every successful read: forget pattern numbers that no longer
        hold one of this app's "Auto" patterns (deleted, or reused by a
        pattern made in the Trimlight app). The repair deletes by number while
        names can't be read, so it must only ever know numbers last seen as
        "Auto". A successful read also ends a "delete it by hand" notice."""
        lib = {e.get("id"): e for e in detail.get("effects", []) or []}
        with self.lock:
            d = self.state["devices"].get(dev_id)
            if not d:
                return
            keep = {k: v for k, v in (d.get("effects") or {}).items() if v in lib and _is_auto(lib[v])}
            if keep != (d.get("effects") or {}) or "stuck" in d or d.get("unconfirmed"):
                d["effects"] = keep
                d.pop("stuck", None)
                d["unconfirmed"] = []          # a good read since our last save: none of ours is the cause
                self._save()

    def check_live(self, dev_id: str, detail: dict) -> str | None:
        """Compare a fresh read of the controller with what the last sync
        wrote. If the copy was changed or cleared since (the Trimlight app, a
        reset), stop relying on it and have it written again. Returns a
        message when that happened."""
        self._prune(dev_id, detail)
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
            lib = {e.get("id"): str(e.get("name", "")) for e in detail.get("effects", []) or []}
            changed = [cid for cid, p in written.items()
                       if cid not in cal or any(cal[cid].get(k) != p[k] for k in _CAL_KEYS)]
            # A pattern gone, or its number now holding another pattern (a
            # reset renumbers them): the copy would show the wrong lights.
            names = d.get("written_names") or {}
            gone = [i for i in d.get("written_effects", []) if i not in lib
                    or (str(i) in names and lib[i].strip().lower() != names[str(i)].strip().lower())]
            if not (changed or gone):
                return None
            msg = "The timer copy on the controller was changed outside this app, so it's being copied again."
            d.update(ok=False, hash=None, message=msg)
            self.retry_at = 0
            self._save()
            return msg

    def summary(self) -> dict:
        with self.lock:
            out = {k: {x: v.get(x) for x in ("ok", "message", "last_sync", "last_sync_label", "covers_until", "entries",
                                             "conflicts", "backup", "skipped", "not_copied")}
                   for k, v in self.state["devices"].items()}
            for v in out.values():   # a copy held back by the Trimlight app's own timers isn't armed
                v["ok"] = bool(v["ok"] and not v["conflicts"])
            return out

    # ---------------------------------------------------------------- plan
    def plan(self, cfg, now: datetime, offset_min: int = 0, dev: str | None = None):
        """Calendar entries for today and the next days, plus the patterns
        they need. Today's entry is kept even after it ends, so the plan (and
        the writes) only change once a day or when settings change. dev
        (4.8): the nights as that controller runs them, when some rules run
        only some controllers."""
        loc, sch = cfg.loc, cfg.schedule.for_controller(dev)
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
                k = None
                if w.rule.curve:
                    # A night curve (3.18) needs the app to change it; the
                    # controller's own copy holds the curve's opening look.
                    from .circadian import curve_at, curve_levels, with_white
                    k, lvl = curve_at(w.rule.curve, w, w.start, loc)
                    eff = with_white(eff, k, cfg.gamma)
                    levels = curve_levels(eff.payload.get("brightness") if eff.kind in ("custom", "builtin") else None,
                                          levels, lvl)
                start = p.start + off
                last = datetime.combine(start.date(), time(23, 59), tzinfo=start.tzinfo)
                end = min(p.end + off, last)
                if end <= start:
                    continue
                slot = f"{eff.key}|{json.dumps(levels, sort_keys=True)}" + (f"|k{k}" if k else "")
                slots[slot] = (eff, levels)
                entries.append({"month": start.month, "day": start.day, "start": [start.hour, start.minute],
                                "end": [end.hour, end.minute], "slot": slot, "label": eff.label, "rule": w.rule.name})
        return entries, slots

    @staticmethod
    def plan_hash(entries, slots) -> str:
        blob = json.dumps({"e": entries, "s": {k: (v[0].kind, v[0].payload, v[0].saved_name, v[0].saved_id, v[1])
                                               for k, v in slots.items()}}, sort_keys=True, default=str)
        return hashlib.sha256(blob.encode()).hexdigest()[:16]

    def due(self, dev_ids, h, today: date, now_ts: float) -> bool:
        """h: the plan's hash, or (4.8) a hash for each controller."""
        if self.halted or self.held():
            return False
        with self.lock:
            for dev in dev_ids:
                d = self.state["devices"].get(dev) or {}
                if d.get("hash") != (h.get(dev) if isinstance(h, dict) else h) or d.get("synced_on") != today.isoformat():
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
        if self.halted:
            return False
        offset = getattr(api, "clock_offset_min", 0)
        entries, slots = self.plan(cfg, now, offset)
        h = self.plan_hash(entries, slots)
        failed, wait = False, None
        for dev in dev_ids:
            if cfg.schedule.per_controller:      # 4.8: each controller's own nights
                entries, slots = self.plan(cfg, now, offset, dev)
                h = self.plan_hash(entries, slots)
            if self.halted:
                break                    # one controller looked wrong: touch no other either
            if self.held():
                wait = max(wait or 0, self.hold_until - self.clock() + 1)
                continue
            try:
                self._sync_one(api, dev, entries, slots, now, cfg.safety["days"])
                with self.lock:
                    d = self._dev(dev)
                    n = len(d.get("entries") or [])
                    msg = f"{n} night{'s' if n != 1 else ''} copied to the controller."
                    if d.get("not_copied"):
                        msg += (" Only one timer per day fits on the controller (Trimlight's calendar won't take two on "
                                f"one date), so the longest was copied; not copied: {', '.join(d['not_copied'])}.")
                    if d.get("skipped"):
                        msg += (f" Not copied: nights showing {', '.join(chr(8220) + x + chr(8221) for x in d['skipped'])}, "
                                "because the controller has no saved pattern with that name. The backup timer never saves "
                                "patterns itself: save one under the same name in the Trimlight app, then choose Update now.")
                    if d.get("conflicts"):
                        msg += (" Not used yet: the Trimlight app's own timers would also run when the controller is "
                                "left in Timer mode. Turn them off (see below), then choose Update now.")
                    d.update(ok=n > 0, hash=h, synced_on=now.date().isoformat(), last_sync=now.isoformat(timespec="minutes"),
                             last_sync_label=now.strftime("%b %d, %I:%M %p").replace(" 0", " "),
                             covers_until=(now.date() + timedelta(days=cfg.safety["days"] - 1)).isoformat(),
                             message=msg)
                    self._save()
                note(f"Backup timer updated: {n} night(s) copied to the controller."
                     + (f" Skipped (no saved pattern with that name): {', '.join(d['skipped'])}." if d.get("skipped") else "")
                     + (" It stays off until the Trimlight app's own timers are turned off." if d.get("conflicts") else ""),
                     logging.WARNING if d.get("conflicts") else logging.INFO)
            except Waiting as e:
                wait = max(wait or 0, e.seconds)
                with self.lock:          # an armed copy stays armed meanwhile
                    d = self._dev(dev)
                    if not d.get("ok"):
                        d["message"] = str(e)
                        self._save()
            except Halt as e:
                failed = True
                self._halt(str(e))
                with self.lock:
                    self._dev(dev).update(ok=False, hash=None, message=str(e))
                    self._save()
                note(f"Backup timer stopped itself: {e} Turn it off and on again to try again.", logging.WARNING)
            except CalendarConflict as e:
                # Not a failure to retry every 30 minutes (each retry reads the
                # controller and writes a backup, pushing older backups out):
                # nothing changes until the settings or the Trimlight app's
                # calendar do. Done for today; "Update now" checks again.
                with self.lock:
                    d = self._dev(dev)
                    same = d.get("message") == str(e) and d.get("synced_on") == now.date().isoformat()
                    d.update(ok=False, hash=h, synced_on=now.date().isoformat(), message=str(e),
                             last_sync=now.isoformat(timespec="minutes"),
                             last_sync_label=now.strftime("%b %d, %I:%M %p").replace(" 0", " "))
                    self._save()
                if not same:
                    note(f"Backup timer not armed: {e}", logging.WARNING)
            except (TrimlightError, ValueError) as e:
                failed = True
                if isinstance(e, TrimlightError) and e.unreadable:
                    why = ("Trimlight's cloud can't read the controller (code 12006), so the backup timer won't write "
                           "to it. Tap Resync with Trimlight's cloud (Setup \u203a Lights & controller).")
                    self._halt(why)
                    with self.lock:
                        self._dev(dev).update(ok=False, hash=None, message=why)
                        self._save()
                    note(f"Backup timer stopped itself: {why} Turn it off and on again to try again.", logging.WARNING)
                    continue
                with self.lock:
                    d = self._dev(dev)
                    d.update(ok=False, hash=None, message=str(e), last_sync=now.isoformat(timespec="minutes"),
                             last_sync_label=now.strftime("%b %d, %I:%M %p").replace(" 0", " "))
                    self._save()
                note(f"Backup timer not updated: {e}", logging.WARNING)
        self.retry_at = self.clock() + (1800 if failed else (wait or 0))
        return not failed

    def _read(self, api, dev: str, now: datetime) -> dict:
        """Read the controller. If Trimlight's cloud can't read its copy of it
        (12006), the error goes up and the backup timer halts: it no longer
        deletes patterns by number to repair it (4.2.1), since after a reset
        a number can belong to any pattern."""
        det = api.get_device(dev, now)
        self._prune(dev, det)
        return det

    def _sync_one(self, api, dev: str, entries, slots, now: datetime, days: int = 7):
        entries, slots = for_device(entries, slots, dev)
        det = self._read(api, dev, now)
        fp, t = fingerprint(det), self.clock()
        with self.lock:
            st = self._dev(dev)
            calm = st.get("calm") or {}
            if calm.get("fp") != fp:
                st["calm"] = {"fp": fp, "at": t}
                self._save()
            since = t - st["calm"]["at"]
            if since < self.settle:
                raise Waiting("Checking that the controller is settled before writing to it "
                              f"(about {int(self.settle - since) // 60 + 1} min).", self.settle - since + 1)
            st["backup"] = self._backup(dev, det)
        lib = {e.get("id"): e for e in det.get("effects", [])}
        cal = {c.get("id"): c for c in det.get("calendar", [])}
        owned_eff = {k: v for k, v in st["effects"].items() if v in lib and _is_auto(lib[v])}
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
            # Assumption (seen on firmware 1.17.77, Nov 2026; not documented by
            # Trimlight): any shared date counts as crossing, whatever the times.
            for cid in list(owned_cal):
                try:
                    api.calendar_delete(dev, cid)
                    owned_cal.remove(cid)
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

        # 1. the patterns the nights need: only ones already on the controller.
        # Saving patterns through Trimlight's cloud can number two the same,
        # which leaves the controller unreadable (12006); so it never saves.
        byname = {}
        for e in lib.values():
            nm = str(e.get("name", "")).strip().lower()
            if nm and not _is_auto(e):
                byname.setdefault(nm, e)
        ids, skipped = {}, []
        for k, (eff, levels) in slots.items():
            want = ((eff.saved_name if eff.kind == "saved" else None) or eff.label or "").strip().lower()
            found = byname.get(want)
            if found is None and eff.kind == "saved" and not eff.saved_name and eff.saved_id in lib:
                found = lib[eff.saved_id]
            if found is None and k in owned_eff and eff.kind != "saved" \
                    and _same_effect(lib[owned_eff[k]], {**eff.payload, **levels}):
                found = lib[owned_eff[k]]    # an unchanged copy an older version saved
            if found is None:
                if eff.label not in skipped:
                    skipped.append(eff.label)
                continue
            ids[k] = found["id"]
        entries = [e for e in entries if e["slot"] in ids]
        entries, dropped = one_per_day(entries)
        with self.lock:
            st["skipped"] = skipped
            st["not_copied"] = sorted({f"{e['label']} {e['start'][0]:02d}:{e['start'][1]:02d}"
                                       f"\u2013{e['end'][0]:02d}:{e['end'][1]:02d}" for e in dropped})
            self._save()

        # 2. calendar entries: reuse our ids, then free ones; never touch the user's
        # 4.3.9: from 1, as the Trimlight app numbers its own; 0 only last.
        free = [i for i in list(range(1, MAX_CALENDAR)) + [0] if i not in cal]
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

        # 3. read back and verify every entry. 4.3.8: Trimlight's cloud
        # updates its copy after the controller confirms, so the first read
        # can come too soon (Nov 16: all 14 entries "differed" at once); read
        # again after a pause before calling it a mismatch, and log what
        # differed.
        for pause in self.readback_pauses:
            if pause:
                _time.sleep(pause)
            det2 = self._read(api, dev, now)
            cal2 = {c.get("id"): c for c in det2.get("calendar", [])}
            lib2 = {e.get("id"): str(e.get("name", "")) for e in det2.get("effects", [])}
            bad = []
            for cid, p in written:
                c = cal2.get(cid)
                if not c or any(c.get(k) != p[k] for k in _CAL_KEYS):
                    bad.append(cid)
            missing_eff = [i for i in ids.values() if i not in lib2]
            if not (bad or missing_eff):
                break
        if bad:
            cid = bad[0]
            want = next(p for c, p in written if c == cid)
            log.warning("Backup timer read-back: entry %s was written as %s, read back as %s (calendar holds ids %s)",
                        cid, {k: want[k] for k in _CAL_KEYS}, cal2.get(cid), sorted(cal2)[:20])
        if not (bad or missing_eff):
            with self.lock:   # what the live check compares against later
                st["written"] = {str(cid): {k: p[k] for k in _CAL_KEYS} for cid, p in written}
                st["written_effects"] = sorted(set(ids.values()))
                st["written_names"] = {str(i): lib2[i] for i in st["written_effects"]}
                st["calm"] = {"fp": fingerprint(det2), "at": self.clock() - self.settle}   # our own write is settled
                self._save()
        if bad or missing_eff:
            self._take_back(api, dev, owned_set, persist_calendar)
            raise Halt("The controller's timers didn't read back as written, so the copy was removed "
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
        self.clear_halt()          # off and on again is how a halt is cleared
        ok = True
        for dev in dev_ids:
            with self.lock:
                st = self.state["devices"].get(dev)
            if not st or not (st.get("calendar") or st.get("effects") or st.get("stuck")):
                continue
            try:
                det = self._read(api, dev, now)
                with self.lock:
                    st["backup"] = self._backup(dev, det)
                cal = {c.get("id") for c in det.get("calendar", [])}
                lib = {e.get("id"): e for e in det.get("effects", [])}
                for cid in st.get("calendar", []):
                    if cid in cal:
                        api.calendar_delete(dev, cid)
                # 4.3: patterns are never deleted through the cloud any more
                # (deleting by number while the cloud's copy was out of step
                # removed the owner's patterns, Nov 13, 2026). An "Auto" copy an
                # older version saved is named, to delete over the home network
                # (Local mode) or in the Trimlight app.
                left = sorted({lib[eid].get("name") for eid in set(st.get("effects", {}).values())
                               if eid in lib and _is_auto(lib[eid])})
                msg = "Backup timer is off."
                if left:
                    msg += (f" Patterns an older version saved are still on the controller: {', '.join(left)}. Delete "
                            "them in Setup \u203a Local mode, or in the Trimlight Edge app.")
                with self.lock:
                    self.state["devices"][dev] = {"ok": False, "message": msg, "effects": {}, "calendar": []}
                    self._save()
                note("Backup timer removed from the controller." + (f" {msg[21:]}" if left else ""))
            except (TrimlightError, ValueError) as e:
                ok = False
                note(f"Couldn't remove the backup timer yet: {e}", logging.WARNING)
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
