# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""The always-on part: decides what the lights should be doing right now and
makes it so. It drives the controller directly in manual mode, so the
controller's own clock and timers never matter.

What wins, highest first:
  1. Security flash        (timed; then everything below resumes)
  2. Manual on/off         (holds until the next scheduled change)
  3. Weather rule          (only while a rule has the lights on, and only if
                            its priority beats that rule's priority)
  4. Scheduled rules       (highest priority; ties go to the first listed)
Brightness/speed slider changes apply on top of 2-4 until the next
scheduled change.

- Checks every few seconds; only sends a command when the target changes.
- After a reboot or outage it catches up to whatever should be on right now.
- Failed commands retry with backoff (30s, 60s, 2m, then every 5m).
- Once a day it sends the correct local time to the controller.
"""
import hashlib
import json
import logging
import os
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .api import TrimlightAPI, TrimlightError
from .runtime import Runtime
from .safety import _same_effect
from .schedule import add_real, ts
from .weather import WeatherService

log = logging.getLogger("eaveluxos")
VERIFY_EVERY = 300  # seconds between read-backs of the controllers


def effect_fp(obj) -> str | None:
    """A short fingerprint of a pattern as sent or as reported back."""
    if not isinstance(obj, dict) or not obj:
        return None
    try:
        return hashlib.sha1(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]
    except (TypeError, ValueError):
        return None


def effect_matches(current, sent) -> bool | None:
    """Is the controller showing what this app sent? `current` is the
    controller's currentEffect ("Device current running effect" in
    Trimlight's API; its id is -1 while a preview runs), `sent` what was sent
    (with "id" when a saved pattern was run by id). None when it can't be
    told: the controller didn't report it, or nothing was sent."""
    if not isinstance(current, dict) or not current or not isinstance(sent, dict):
        return None
    cid, sid = current.get("id"), sent.get("id")
    if sid is not None and cid is not None:
        return cid == sid
    if cid is not None and cid >= 0 and sid is None:
        return False                 # a saved pattern runs, but this app sent a preview
    try:
        return _same_effect(current, sent)
    except (TypeError, AttributeError):
        return None


@dataclass
class Target:
    key: str
    on: bool
    effect: object = None
    levels: dict = field(default_factory=dict)
    reason: str = "schedule"     # flash | manual | weather | schedule
    source: str | None = None    # rule or weather-rule name
    until: datetime | None = None
    delegated: bool = False      # the controller runs this night from its own timer
    weather_match: str | None = None  # best-matching weather rule (shown even when it doesn't win)
    adjusted: bool = False       # slider levels set by hand apply to this target
    hands_off: bool = False      # a music show: the controller's music mode runs the lights


class Controller:
    def __init__(self, cfg, api: TrimlightAPI, weather: WeatherService | None = None, safety=None, data_dir=None):
        self.cfg = cfg
        self.api = api
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.devices: list[dict] = []
        self.saved: dict[str, dict] = {}      # deviceId -> {name lower: effect dict}
        self.override = None                  # {"on": bool, "effect": key, "since": dt}
        self.adjust: dict = {}                # slider levels {"brightness": n, "speed": n}
        self.flash = None                     # {"until": dt}
        self.music = None                     # music show from the button: {"until": dt | None, "since": dt}
        self.music_skipped = None             # key of a show night stopped early (don't restart it)
        self.last_on = None                   # last pattern turned on by hand (for the On button)
        self.sched_key = None
        self.applied_key = None
        self.fail_count = 0
        self.next_try = 0.0
        self.last_error = None
        self.read_error = None                # the last read-back's failure (alerts: code 12006)
        self.last_clock_sync = None
        self.status_cache = {"at": 0.0, "data": []}
        self.events = deque(maxlen=150)
        if weather is None and cfg.weather["enabled"]:
            w = cfg.weather
            weather = WeatherService(cfg.loc.lat, cfg.loc.lon, w["use"], w["check_minutes"], w["contact"])
        self.weather = weather
        self.safety = safety                  # SafetyNet or None
        self.weather_match = None             # name of the matching weather rule, for display
        self.known_on = False                 # True once we've switched the controller on
        self.apply_lock = threading.Lock()    # serializes commands to the cloud
        self.last_verify = 0.0
        self.mismatches = 0
        self._strip_cache = (None, None)
        self.cfg_gen = 0                      # bumps on every settings reload (cache key)
        # Bumps whenever something asks for the target to be sent again (new
        # settings, a stopped show, a restore). A send that was already in
        # flight only records itself as applied if this didn't change while it
        # ran; otherwise it would overwrite the request and the new settings
        # would never be sent.
        self.apply_gen = 0
        self.sent_effect: dict = {}           # deviceId -> what was last sent (for the pattern check)
        self.pattern_mismatches = 0
        self.pattern_restored = None          # target key restored for a pattern change, until a reading matches
        # How each controller reports back a pattern this app sent, when that
        # differs from what was sent (learned once, kept across restarts, so a
        # restart doesn't "restore" a pattern that never changed). 3.15.
        self.reported_path = os.path.join(str(data_dir), "reported-patterns.json") if data_dir else None
        self.reported = self._load_reported()
        self.runtime = Runtime(data_dir, tz=lambda: self.cfg.loc.tz)    # hours on per month; follows a changed time zone
        self.pattern_unverified = set()       # target keys the controller doesn't report back as sent

    def _invalidate(self):
        """Send the target again on the next pass, in full. Lock held."""
        self.applied_key = None
        self.known_on = False
        self.apply_gen += 1
        self._kick()

    def refresh_devices(self):
        """Controllers changed (added, removed, ports or names edited): list
        them again and send the target to every one, switch-on included."""
        with self.lock:
            self.devices = []
            self.last_verify = 0.0
            self._invalidate()

    # ------------------------------------------------------------ logging
    def note(self, msg: str, level=logging.INFO):
        log.log(level, msg)
        now = self.cfg.loc.now()
        self.events.appendleft({"t": now.isoformat(), "label": now.strftime("%b %d, %I:%M %p").replace(" 0", " "), "msg": msg,
                                "level": logging.getLevelName(level).lower()})

    # ------------------------------------------------------------ devices
    def _ensure_devices(self):
        if self.devices:
            return
        found = self.api.list_devices()
        if self.cfg.devices:
            wanted = set(self.cfg.devices)
            chosen = [d for d in found if d.get("deviceId") in wanted]
            missing = wanted - {d.get("deviceId") for d in chosen}
            if missing:
                self.note(f"These device IDs aren't on your account: {', '.join(sorted(missing))}", logging.WARNING)
        else:
            chosen = found
        if not chosen:
            raise TrimlightError("No Trimlight controllers found on this account.")
        self.devices = chosen
        self.known_on = False   # a controller new to this list hasn't been switched on yet
        self.note("Controlling: " + ", ".join(f"{d.get('name')} ({d.get('deviceId')})" for d in chosen))

    def _saved_effect(self, dev_id: str, effect, refresh=False) -> dict:
        lib = self.saved.get(dev_id)
        want_name = (effect.saved_name or "").strip().lower()

        def find(lib):
            if effect.saved_id is not None:
                return next((e for e in lib.values() if e.get("id") == effect.saved_id), None)
            return lib.get(want_name)

        if lib is None or refresh or find(lib) is None:
            detail = self.api.get_device(dev_id, self.cfg.loc.now())
            lib = {str(e.get("name", "")).strip().lower(): e for e in detail.get("effects", [])}
            self.saved[dev_id] = lib
        found = find(lib)
        if found is None:
            what = f"id {effect.saved_id}" if effect.saved_id is not None else f"named '{effect.saved_name}'"
            raise TrimlightError(f"No saved pattern {what} on this controller. "
                                 "Open Patterns \u203a In the Trimlight app to see what's saved.")
        return found

    @staticmethod
    def _payload_from_saved(e: dict) -> dict:
        p = {"category": e.get("category", 1), "mode": e.get("mode", 0),
             "speed": e.get("speed", 100), "brightness": e.get("brightness", 200)}
        if e.get("category") == 0:
            p["pixelLen"] = e.get("pixelLen", 30)
            p["reverse"] = bool(e.get("reverse", False))
        else:
            p["pixels"] = e.get("pixels", [])
        return p

    def base_levels(self, effect) -> dict:
        """The effect's own brightness/speed, if known without a network call."""
        if effect is None:
            return {}
        if effect.kind != "saved":
            return {"brightness": effect.payload["brightness"], "speed": effect.payload["speed"]}
        want = (effect.saved_name or "").strip().lower()
        for lib in self.saved.values():
            for e in lib.values():
                # By id when the pattern names one (as _saved_effect does), else by
                # name; an id-only pattern used to match any pattern with no name.
                if (e.get("id") == effect.saved_id) if effect.saved_id is not None else \
                        (want and str(e.get("name", "")).strip().lower() == want):
                    return {"brightness": e.get("brightness"), "speed": e.get("speed")}
        return {}

    # ------------------------------------------------------------ actions
    def _apply(self, on: bool, effect, levels: dict | None = None, timer_off: bool = False, delegated: bool = False):
        """timer_off: when off, use Timer mode (safety net) instead of Off.
        delegated: lights on, run by the controller's own timer (Timer mode).
        Returns whether the controllers are now switched on by this app; the
        caller records it (with applied_key) under the lock."""
        self._ensure_devices()
        levels = levels or {}
        if delegated:
            for d in self.devices:
                self.api.set_switch(d["deviceId"], 2)
                self.sent_effect.pop(d["deviceId"], None)   # the controller's timer picks the pattern
            self.status_cache["at"] = 0.0
            return False
        for d in self.devices:
            dev = d["deviceId"]
            self.sent_effect.pop(dev, None)
            if not on:
                self.api.set_switch(dev, 2 if timer_off else 0)
                continue
            # (switch-on is skipped when we already turned it on; effect calls follow)
            if not self.known_on:
                self.api.set_switch(dev, 1)
            if effect.kind == "saved" and not levels:
                saved = self._saved_effect(dev, effect)
                self.api.run_saved_effect(dev, int(saved.get("id")))
                self.sent_effect[dev] = {**self._payload_from_saved(saved), "id": int(saved.get("id"))}
            else:
                payload = (self._payload_from_saved(self._saved_effect(dev, effect))
                           if effect.kind == "saved" else dict(effect.payload))
                payload.update(levels)
                self.api.preview_effect(dev, payload)
                self.sent_effect[dev] = payload
        self.status_cache["at"] = 0.0
        return on

    def _safety_ready(self) -> bool:
        """Leave the controller in Timer mode between windows only when every
        controller holds a verified copy of the coming nights."""
        if not (self.safety and self.cfg.safety["enabled"] and self.devices):
            return False
        today = self.cfg.loc.now().date()
        return all(self.safety.ready(d["deviceId"], today) for d in self.devices)

    def _weather_pick(self, window):
        """(rule, match): the highest-priority matching weather rule if it
        outranks the window's rule, and the name of the best match (for
        display). Reads only; never changes state."""
        if not (self.weather and self.cfg.weather_rules):
            return None, None
        cur = self.weather.current()
        if not cur["fresh"]:
            return None, None
        for wr in sorted(self.cfg.weather_rules, key=lambda r: (-r.priority, r.order)):
            if wr.matches(cur["tags"], cur["temp_f"]):
                return (wr if window and wr.priority > window.rule.priority else None), wr.name
        return None, None

    def _target(self, commit: bool = True) -> Target:
        """What the lights should be doing now. Only the scheduler (and the
        actions that call tick) commit the transitions found on the way
        (a flash or preview ending, manual settings ending at a scheduled
        change); status reads pass commit=False and change nothing."""
        now = self.cfg.loc.now()
        w = self.cfg.schedule.active_window(now)
        sched_key = w.key if w else "off"
        override, adjust, flash, notes = self.override, self.adjust, self.flash, []
        if sched_key != self.sched_key:
            # The first check after startup isn't a scheduled *change*; don't
            # throw away something the user set in the app's first seconds.
            if self.sched_key is not None:
                if override or adjust:
                    notes.append("Scheduled change reached, so manual settings ended.")
                override, adjust = None, {}

        def done(t: Target) -> Target:
            t.adjusted = bool(adjust) and t.reason != "flash" and t.on
            if commit:
                self.sched_key = sched_key
                self.override, self.adjust, self.flash = override, adjust, flash
                self.weather_match = t.weather_match
                for n in notes:
                    self.note(n)
            return t

        # 1. security flash
        if flash:
            # The flash pattern can be cleared or replaced in settings while a
            # flash runs; with none left, end the flash instead of failing
            # every pass (and every status read) until it would have ended.
            eff = self.cfg.effects.get(self.cfg.security["effect"] or "")
            if eff is not None and ts(now) < ts(flash["until"]):
                return done(Target(f"flash|{flash['until'].isoformat()}", True, eff, {}, "flash", "Security flash",
                                   flash["until"]))
            flash = None
            notes.append("Security flash ended." if eff is not None
                         else "Security flash ended: no flash pattern is set up any more.")

        # 2. music show (button, then show nights): this app steps aside
        music, skipped = self.music, self.music_skipped
        if music and music.get("until") and ts(now) >= ts(music["until"]):
            music = None
            notes.append("Music show ended; back on the schedule.")
        show_w = None
        msched = self.cfg.music.get("schedule")
        if msched is not None:
            show_w = msched.active_window(now)
            if show_w is not None and show_w.key == skipped:
                show_w = None
        if music:
            t = Target(f"music|button|{music['since'].isoformat()}", True, None, {}, "music", "Music show",
                       music.get("until"), hands_off=True)
        elif show_w is not None:
            t = Target(f"music|{show_w.key}", True, None, {}, "music", show_w.rule.name, show_w.end, hands_off=True)
        else:
            t = None
        if commit:
            self.music = music
        if t is not None:
            return done(t)

        # 3. manual
        if override and override.get("expires") and time.time() > override["expires"]:
            override, adjust = None, {}
            notes.append("Preview ended; back on the schedule.")
        if override:
            o = override
            eff = (o.get("obj") or self.cfg.effects.get(o.get("effect"))) if o["on"] else None
            if o["on"] and eff is None:  # pattern was deleted
                override = None
            else:
                lv = json.dumps(adjust, sort_keys=True)
                return done(Target(f"manual|{o['on']}|{o.get('effect')}|{o['since'].isoformat()}|{lv}",
                                   o["on"], eff, dict(adjust) if o["on"] else {}, "manual"))
        if not w:
            _, match = self._weather_pick(None)
            return done(Target("off|timer" if self._safety_ready() else "off", False, weather_match=match))
        # 4. weather / 5. schedule, with rotation
        wr, match = self._weather_pick(w)
        rule = wr or w.rule
        eff, step = rule.pick(w.start, now)   # the weather rule's own rotation, or the schedule's
        # A weather rule keeps the scheduled rule's levels (e.g. late-night dim)
        # unless it sets its own.
        levels = {**w.rule.levels, **(wr.levels if wr else {}), **adjust}
        reason = "weather" if wr else "schedule"
        # Hand plain scheduled nights to the controller's own timer (safety
        # net), so the lights still go OFF if this app dies mid-evening. Only
        # when entering the window from armed-off (or already handed over):
        # switching to Timer mode part-way through a night is avoided because
        # it isn't confirmed that the controller re-lights immediately.
        if not wr and not adjust:
            entry_end = self._delegation_end(w, eff, now)
            prev = self.applied_key or ""
            if entry_end and ts(now) < ts(entry_end) - 120 and (prev == "off|timer" or prev.startswith(w.key + "|timer")):
                return done(Target(f"{w.key}|timer|{step}", True, eff, levels, "schedule", rule.name, w.end,
                                   delegated=True, weather_match=match))
        key = f"{w.key}|{reason}|{rule.name}|{step}|{json.dumps(levels, sort_keys=True)}"
        return done(Target(key, True, eff, levels, reason, rule.name, w.end, weather_match=match))

    def _delegation_end(self, w, eff, now):
        """When the controller holds a verified timer entry matching this
        window and pattern, return when that entry ends (real time); else None."""
        if not self._safety_ready():
            return None
        if len(w.rule.effects) > 1 and not w.rule.nightly:
            return None  # minute-by-minute rotation needs the app
        off = timedelta(minutes=getattr(self.api, "clock_offset_min", 0) or 0)
        start = w.start + off
        last = start.replace(hour=23, minute=59, second=0, microsecond=0)
        end = min(w.end + off, last)
        want = {"date": f"{start.month:02d}-{start.day:02d}", "on": start.strftime("%H:%M"),
                "off": end.strftime("%H:%M"), "pattern": eff.label}
        with self.safety.lock:
            for d in self.devices:
                if want not in (self.safety.state["devices"].get(d["deviceId"], {}).get("entries") or []):
                    return None
        return end - off

    def tick(self, maintenance: bool = True):
        """One scheduling pass. Network calls happen under apply_lock only, so
        status reads (which need just self.lock) never wait on the cloud.
        maintenance=False (buttons, settings changes): just send the lights;
        the read-back and safety-net copy (a dozen cloud calls) are left to
        the scheduler's own pass a few seconds later, so a button press never
        waits on them."""
        with self.apply_lock:
            with self.lock:
                t = self._target()
                due = t.key != self.applied_key and time.time() >= self.next_try
                gen = self.apply_gen
            if due and t.hands_off:
                # A music show: send nothing, so the controller's music mode
                # isn't interrupted. What it shows afterward is unknown, so the
                # next pattern is sent in full.
                with self.lock:
                    if self.apply_gen == gen:
                        self.applied_key = t.key
                    self.known_on = False
                    self.fail_count = 0
                    self.last_error = None
                self.note(f"Music show: this app is leaving the lights to the controller's music mode [{t.source}]")
                return
            if t.hands_off:
                return                       # no checks or timer copies during a show either
            if due:
                try:
                    switched_on = self._apply(t.on, t.effect, t.levels, timer_off=t.key == "off|timer",
                                              delegated=t.delegated)
                    with self.lock:
                        if self.apply_gen == gen:
                            self.applied_key = t.key
                            self.known_on = switched_on
                        # else: new settings (or a resend request) arrived while
                        # this was being sent; leave applied_key unset so the
                        # next pass sends what they say.
                        self.fail_count = 0
                        self.last_error = None
                        self.mismatches = 0
                        self.last_verify = time.time() - VERIFY_EVERY + 30  # confirm soon
                    lv = "".join(f", {k} {v}" for k, v in t.levels.items())
                    what = (f"on ({t.effect.label}{lv}), run by the controller's own timer" if t.delegated
                            else f"on ({t.effect.label}{lv})" if t.on else ("off (safety net armed)" if t.key == "off|timer" else "off"))
                    self.note(f"Lights {what} [{t.source or t.reason}]")
                except TrimlightError as e:
                    with self.lock:
                        self.known_on = False
                        self.fail_count += 1
                        wait = min(300, 30 * 2 ** (self.fail_count - 1))
                        self.next_try = time.time() + wait
                        self.last_error = str(e)
                    self.note(f"Couldn't reach the lights: {e}. Retrying in {wait}s.", logging.WARNING)
            if maintenance:
                self._maintenance(t)

    def _safety_step(self, now_ts: float):
        """Keep the controller's copy of the coming nights current (daily, and
        whenever settings change). Runs under apply_lock, like all writes."""
        if not self.safety or not self.devices:
            return
        ids = [d["deviceId"] for d in self.devices]
        now = self.cfg.loc.now()
        # A sync is a dozen cloud calls under the command lock. Don't start one
        # right before a scheduled on/off; it runs on the next pass after it.
        nxt = self.cfg.schedule.next_change(now)
        if nxt is not None and ts(nxt) - ts(now) < 180:
            return
        if not self.cfg.safety["enabled"]:
            if now_ts >= self.safety.retry_at and not self.safety.remove(self.api, ids, now, self.note):
                self.safety.retry_at = now_ts + 1800  # don't retry (and back up) every few seconds
            return
        entries, slots = self.safety.plan(self.cfg, now, getattr(self.api, "clock_offset_min", 0))
        h = self.safety.plan_hash(entries, slots)
        if self.safety.due(ids, h, now.date(), now_ts):
            was = self._safety_ready()
            self.safety.sync(self.api, self.cfg, ids, now, self.note)
            if self._safety_ready() != was:
                with self.lock:
                    self._invalidate()  # switch between Off and Timer mode

    def _read_devices(self) -> list[dict]:
        """Ask every controller for its state (this also sends it today's time)."""
        out = []
        for d in self.devices:
            det = self.api.get_device(d["deviceId"], self.cfg.loc.now())
            if self.safety:
                msg = self.safety.check_live(d["deviceId"], det)
                if msg:
                    self.note(f"{det.get('name', d.get('name'))}: {msg}", logging.WARNING)
                    with self.lock:   # leave Timer mode now; don't wait for the next sync
                        self._invalidate()
            self.saved[d["deviceId"]] = {str(e.get("name", "")).strip().lower(): e for e in det.get("effects", [])}
            out.append({"name": det.get("name", d.get("name")), "id": d["deviceId"],
                        "online": det.get("connectivity") == 1, "switch_raw": det.get("switchState"),
                        "effect_raw": det.get("currentEffect"),
                        "switch": {0: "off", 1: "on", 2: "timer"}.get(det.get("switchState"), "?"),
                        "firmware": det.get("fwVersionName")})
        return out

    def _maintenance(self, t):
        """Every few minutes (and at least daily, for the clock): read the
        controllers back. If one isn't in the state we set (power blip, someone
        used the Trimlight app), restore it: the switch (on, off, Timer) and,
        while this app runs the lights, the pattern showing. Two readings in a
        row must disagree before acting, so a lagging cloud report can't cause
        flapping."""
        now = time.time()
        today = self.cfg.loc.now().date()
        self._safety_step(now)
        if not self.devices or (now - self.last_verify < VERIFY_EVERY and self.last_clock_sync == today):
            return
        self.last_verify = now
        try:
            snap = self._read_devices()
        except TrimlightError as e:
            log.debug("controller check failed: %s", e)
            self.read_error = str(e)
            return
        self.read_error = None
        self.last_clock_sync = today
        restored = None
        with self.lock:
            self.status_cache = {"at": now, "data": snap}
            if t.key != self.applied_key:
                return
            want = 2 if t.delegated else 1 if t.on else (2 if t.key == "off|timer" else 0)
            wrong = [d for d in snap if d["online"] and d["switch_raw"] != want]
            self.mismatches = self.mismatches + 1 if wrong else 0
            if self.mismatches >= 2:
                self.mismatches = 0
                self.pattern_mismatches = 0
                self._invalidate()
                restored = ", ".join(str(d["name"]) for d in wrong)
            elif not wrong:
                restored = self._check_pattern(t, snap)
        self._save_reported()
        if restored:
            self.note(f"{restored} was changed outside this app (power blip or the Trimlight app). Restoring it.",
                      logging.WARNING)

    def _tonight(self, now: datetime, fmt) -> list[dict]:
        """Home's "Tonight" timeline (3.15): what the schedule does in the
        next 24 hours (sunset, on, a switch to another rule, off), with
        minutes from now worked out here, so a phone's own clock can't skew
        the countdown."""
        sch, loc = self.cfg.schedule, self.cfg.loc
        horizon = ts(now) + 24 * 3600
        seen, plans = set(), []
        for dd in (now.date() - timedelta(days=1), now.date(), now.date() + timedelta(days=1)):
            for p in sch.day_plans(dd):
                k = (ts(p.start), ts(p.end))
                if k not in seen and ts(p.end) > ts(now) and ts(p.start) < horizon:
                    seen.add(k)
                    plans.append(p)
        plans.sort(key=lambda p: ts(p.start))
        ev = []
        for dd in (now.date(), now.date() + timedelta(days=1)):
            ss = loc.sun(dd).get("sunset")
            if ss and ts(now) < ts(ss) < horizon:
                ev.append((ts(ss), "sunset", ss, "Sunset"))
                break
        for i, p in enumerate(plans):
            prev_end = ts(plans[i - 1].end) if i else None
            what = f"{p.rule.name}: {p.effect_label()}" if p.effect_label() != p.rule.name else p.rule.name
            if ts(p.start) > ts(now):
                ev.append((ts(p.start), "switch" if prev_end == ts(p.start) else "on", p.start, what))
            if not (i + 1 < len(plans) and ts(plans[i + 1].start) == ts(p.end)) and ts(p.end) < horizon:
                ev.append((ts(p.end), "off", p.end, p.rule.name))
        ev.sort(key=lambda e: e[0])
        return [{"kind": k, "at": fmt(at), "day": at.strftime("%a") if at.date() != now.date() else None,
                 "in_min": max(0, round((t0 - ts(now)) / 60)), "text": text} for t0, k, at, text in ev[:6]]

    def _load_reported(self) -> dict:
        if not self.reported_path:
            return {}
        try:
            with open(self.reported_path, encoding="utf-8") as f:
                raw = json.load(f)
            return {str(k): [str(x) for x in v][:3] for k, v in raw.items()
                    if isinstance(v, list)} if isinstance(raw, dict) else {}
        except (OSError, ValueError, AttributeError, TypeError):
            return {}

    @staticmethod
    def _learnable(sent, current) -> bool:
        """Only a report that's clearly the same pattern, described a little
        differently, may be learned (3.15.1). Never another saved pattern
        (a different id), another kind (built-in vs custom colors) or another
        animation: those are real changes, made in the Trimlight app, and
        learning one would stop them ever being undone."""
        if not (isinstance(sent, dict) and isinstance(current, dict)):
            return False
        cid, sid = current.get("id"), sent.get("id")
        if cid is not None and cid >= 0 and cid != sid:
            return False                                   # a different saved pattern runs
        for k in ("category", "mode"):
            if k in sent and k in current and sent[k] != current[k]:
                return False
        return True

    def _learn_reported(self, sent, current):
        """Remember that the controller reports `sent` back as `current`."""
        if not self._learnable(sent, current):
            return False
        s, c = effect_fp(sent), effect_fp(current)
        if not (s and c):
            return False
        seen = self.reported.setdefault(s, [])
        if c not in seen:
            seen.insert(0, c)
            del seen[3:]
        while len(self.reported) > 300:                    # oldest first (dicts keep insertion order)
            self.reported.pop(next(iter(self.reported)))
        self._reported_dirty = True                        # saved after the lock is released
        return True

    def _save_reported(self):
        """Write the learned reports (outside self.lock: a slow disk mustn't
        hold up the status page)."""
        if not (self.reported_path and getattr(self, "_reported_dirty", False)):
            return
        with self.lock:
            body = json.dumps(self.reported)
            self._reported_dirty = False
        try:
            tmp = self.reported_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(body)
            os.replace(tmp, self.reported_path)
        except OSError as e:
            log.debug("couldn't save reported patterns: %s", e)

    def _matches(self, current, sent):
        ok = effect_matches(current, sent)
        if ok is False and effect_fp(current) in self.reported.get(effect_fp(sent) or "", ()):
            return True                                     # how this controller reports this pattern
        return ok

    def _check_pattern(self, t, snap) -> str | None:
        """The switch is right; is the pattern? (Someone chose another one in
        the Trimlight app, or a power cut dropped an unsaved preview.) Returns
        the names to report when it's being restored. Lock held.

        A controller that reports a pattern differently from how it was sent
        would otherwise be "restored" every few minutes all night. So after a
        restore, if the reading still never matches what was just sent, the
        pattern isn't checked again for this target (the switch still is)."""
        if not t.on or t.delegated or t.key in self.pattern_unverified:
            self.pattern_mismatches = 0
            return None
        verdicts = [(d, self._matches(d.get("effect_raw"), self.sent_effect.get(d["id"])))
                    for d in snap if d["online"]]
        wrong = [d for d, ok in verdicts if ok is False]
        if any(ok for _, ok in verdicts) and not wrong:
            self.pattern_restored = None          # confirmed: a later change is a real one
        self.pattern_mismatches = self.pattern_mismatches + 1 if wrong else 0
        if self.pattern_mismatches < 2:
            return None
        self.pattern_mismatches = 0
        if self.pattern_restored == t.key:
            # Just restored, and it still reads differently: that's how the
            # controller reports this pattern. Learn it (kept across restarts)
            # and go on checking against it, so a real change is still caught.
            if all(self._learn_reported(self.sent_effect.get(d["id"]), d.get("effect_raw")) for d in wrong):
                self.pattern_restored = "learned|" + t.key
                self.note("Learned how the controller reports this pattern back; it won't be resent for that "
                          "again, also after a restart.", logging.INFO)
                return None
        if self.pattern_restored in (t.key, "learned|" + t.key):
            if len(self.pattern_unverified) > 500:   # one entry per night or pattern; keep it small
                self.pattern_unverified.clear()
            self.pattern_unverified.add(t.key)
            self.pattern_restored = None
            self.note("The controller doesn't report this pattern back exactly as it was sent, so only its "
                      "on/off state is checked until the next change.", logging.INFO)
            return None
        self.pattern_restored = t.key
        self._invalidate()
        return ", ".join(f"{d['name']}'s pattern" for d in wrong)

    def _kick(self):
        self.next_try = 0.0
        self.fail_count = 0

    def manual(self, on: bool, effect_key: str | None = None, obj=None, expires_min: int | None = None):
        """obj: an unsaved Effect to try out (pattern designer, built-in
        browser, bulb finder). expires_min: previews end by themselves, so a
        forgotten bulb-finder highlight can't replace the lights all night."""
        with self.lock:
            if on and obj is None and effect_key not in self.cfg.effects:
                raise ValueError(f"Unknown pattern '{effect_key}'")
            self._end_music("a pattern was chosen")
            if on and obj is None:
                self.last_on = effect_key
            key = effect_key if obj is None else f"_try:{obj.label}:{hash(json.dumps(obj.payload, sort_keys=True))}"
            self.override = {"on": on, "effect": key, "obj": obj, "since": self.cfg.loc.now(),
                             "expires": time.time() + expires_min * 60 if expires_min else None}
            self.adjust = {}
            self._kick()
        self.tick(maintenance=False)

    def default_on_effect(self) -> str:
        """The pattern the On button uses: tonight's scheduled one (the window
        now, or the next one within a week), else the last pattern turned on
        by hand, else Warm white, else the first pattern."""
        effects = self.cfg.effects
        if not effects:
            raise ValueError("There are no patterns yet. Add one on the Patterns tab.")
        now = self.cfg.loc.now()
        sch = self.cfg.schedule
        w = sch.active_window(now)
        if w is None:
            for k in range(8):
                ahead = [p for p in sch.day_plans(now.date() + timedelta(days=k)) if ts(p.end) > ts(now)]
                if ahead:
                    w = ahead[0].window
                    break
        if w is not None:
            at = now if ts(now) >= ts(w.start) else w.start
            eff, _ = w.rule.pick(w.start, at)
            key = next((k for k, v in effects.items() if v is eff), None)
            if key:
                return key
        if self.last_on in effects:
            return self.last_on
        return "warm_white" if "warm_white" in effects else next(iter(effects))

    def resume(self, force: bool = False):
        """Back to the schedule. A show night is part of the schedule: it isn't
        ended, and one skipped tonight (a pattern was chosen, or the show was
        stopped) comes back. A show from the Music button isn't, so it ends.
        force (the Schedule tab's "Run the schedule"): also end a security
        flash, and send the scheduled lights to the controller again in full,
        even if this app thinks they're already showing. That undoes changes
        made in the Trimlight Edge app, which this app can't see."""
        with self.lock:
            changed = False
            if force and self.flash:
                self.flash = None
                self.note("Security flash stopped.")
            if self.music:
                self.music = None
                self.note("Music show stopped (back to the schedule).")
                changed = True
            msched = self.cfg.music.get("schedule")
            w = msched.active_window(self.cfg.loc.now()) if msched is not None else None
            if w is not None and self.music_skipped == w.key:
                self.music_skipped = None
                self.note(f"Back to tonight's music show [{w.rule.name}].")
                changed = True
            if changed:
                self._invalidate()
            if force:
                self.note("Running the schedule: the scheduled lights were sent to the controller again.")
            elif self.override or self.adjust:
                self.note("Back on the schedule.")
            self.override = None
            self.adjust = {}
            if force:
                self._invalidate()
            self._kick()
        self.tick(maintenance=False)

    def set_levels(self, brightness=None, speed=None):
        with self.lock:
            t = self._target()
            if not t.on:
                raise ValueError("The lights are off, so there's nothing to adjust.")
            if t.reason == "flash":
                raise ValueError("Brightness and speed can't be changed during a security flash.")
            if t.reason == "music":
                raise ValueError("During a music show, brightness is set in the Trimlight app's music mode.")
            for k, v in (("brightness", brightness), ("speed", speed)):
                if v is not None:
                    v = int(v)
                    if not 0 <= v <= 255:
                        raise ValueError(f"{k} must be 0-255")
                    self.adjust[k] = v
            self._kick()
        self.tick(maintenance=False)

    # ------------------------------------------------------------ music
    def _end_music(self, why: str) -> bool:
        """Stop a running show (the button's, or tonight's show night). Lock held."""
        now = self.cfg.loc.now()
        ended = False
        if self.music:
            self.music = None
            ended = True
        msched = self.cfg.music.get("schedule")
        w = msched.active_window(now) if msched is not None else None
        if w is not None and w.key != self.music_skipped:
            self.music_skipped = w.key           # this one show night only
            ended = True
        if ended:
            self.note(f"Music show stopped ({why}); back on the schedule.")
        return ended

    def _music_status(self, t, now, fmt) -> dict:
        msched = self.cfg.music.get("schedule")
        nxt = None
        if msched is not None:
            for k in range(0, 35):
                for p in msched.day_plans(now.date() + timedelta(days=k)):
                    if ts(p.start) > ts(now) and p.window.key != self.music_skipped:
                        nxt = p
                        break
                if nxt:
                    break
        return {"active": t.reason == "music", "source": t.source if t.reason == "music" else None,
                "scheduled": t.reason == "music" and not t.key.startswith("music|button|"),
                "until": fmt(t.until) if t.reason == "music" and t.until else None,
                "minutes": self.cfg.music["minutes"], "shows": len(self.cfg.music["shows"]),
                "next": {"name": nxt.window.rule.name, "start": fmt(nxt.start), "end": fmt(nxt.end),
                         "day": nxt.start.strftime("%a %b %d").replace(" 0", " ")} if nxt else None}

    def start_music(self, minutes: int | None = None):
        """Step aside so the controller's music mode can run: until stopped,
        or for `minutes`. 0 or None with until_stopped means no end time."""
        with self.lock:
            if self.flash:
                raise ValueError("A security flash is running. Stop it first.")
            now = self.cfg.loc.now()
            until = None
            if minutes:
                minutes = max(5, min(6 * 60, int(minutes)))
                until = add_real(now, timedelta(minutes=minutes))
            self.music = {"since": now, "until": until}
            self.override, self.adjust = None, {}
            self._kick()
            self.note("Music show started " + (f"for {minutes} min." if until else "(until stopped)."))
        self.tick(maintenance=False)

    def stop_music(self):
        with self.lock:
            self._end_music("stopped")
            self._invalidate()                   # send the scheduled pattern in full
        self.tick(maintenance=False)

    def start_flash(self, minutes: int | None = None):
        if not self.cfg.security["effect"]:
            raise ValueError("No security flash is set up. Choose a pattern for it on the Schedule screen.")
        minutes = max(1, min(240, int(minutes or self.cfg.security["minutes"])))
        with self.lock:
            until = add_real(self.cfg.loc.now(), timedelta(minutes=minutes))
            extended = bool(self.flash)
            self.flash = {"until": until}
            self._kick()
            self.note(f"Security flash {'extended' if extended else 'started'} for {minutes} min.")
        self.tick(maintenance=False)

    def stop_flash(self):
        with self.lock:
            if self.flash:
                self.flash = None
                self.note("Security flash stopped.")
            self._kick()
        self.tick(maintenance=False)

    def reload(self, cfg, api=None):
        """Swap in new settings (and credentials) without restarting."""
        with self.lock:
            old = self.cfg
            self.cfg = cfg
            self.cfg_gen += 1
            if api is not None:
                self.api = api
                self.devices, self.saved = [], {}
            if cfg.devices != old.devices:
                self.devices = []
            if (cfg.loc.lat, cfg.loc.lon, cfg.weather) != (old.loc.lat, old.loc.lon, old.weather) or not cfg.weather["enabled"]:
                w = cfg.weather
                self.weather = (WeatherService(cfg.loc.lat, cfg.loc.lon, w["use"], w["check_minutes"], w["contact"])
                                if w["enabled"] else None)
            self._invalidate()        # re-apply whatever the new settings say
            self.pattern_unverified.clear()   # and check the patterns again
            self.status_cache["at"] = 0.0
        self.tick(maintenance=False)

    # ------------------------------------------------------------ loop
    def run_forever(self):
        self.note("Scheduler started.")
        wt = None
        while not self.stop_event.is_set():
            if wt is None or not wt.is_alive():   # (re)start it, e.g. after a cancelled port move
                wt = threading.Thread(target=self._weather_loop, daemon=True, name="weather")
                wt.start()
            try:
                self.tick()
            except Exception:  # never let the loop die
                log.exception("Unexpected error in scheduler loop")
            try:
                self.runtime.add(self.lights_on())
            except Exception:
                log.exception("Runtime count failed")
            self.stop_event.wait(self.cfg.interval)
        self.runtime.save()

    def lights_on(self) -> bool:
        """On as far as this app knows: the scheduled or chosen state was sent
        and it's an on state, or a music show runs."""
        with self.lock:
            t = self._target(commit=False)
            return bool(t.hands_off or (t.on and self.applied_key == t.key))

    # ------------------------------------------------------------ status
    def device_status(self, max_age=None):
        """Last controller readings from the background check (no network here)."""
        return [{k: v for k, v in d.items() if k not in ("switch_raw", "effect_raw")} for d in self.status_cache["data"]]

    def _weather_loop(self):
        while not self.stop_event.is_set():
            w = self.weather
            if w:
                try:
                    w.refresh()
                except Exception:
                    log.exception("weather check failed")
            self.stop_event.wait(30)

    def status(self) -> dict:
        loc, sch = self.cfg.loc, self.cfg.schedule
        devices = self.device_status()
        now = loc.now()
        fmt = lambda dt: dt.strftime("%-I:%M %p") if dt else None
        try:
            fmt(now)
        except ValueError:  # Windows strftime has no %-I
            fmt = lambda dt: dt.strftime("%I:%M %p").lstrip("0") if dt else None
        midnight = now.replace(hour=0, minute=0, second=0)

        def mins(dt):
            return round((dt - midnight).total_seconds() / 60) if dt else None

        sun = loc.sun(now.date())
        with self.lock:
            t = self._target(commit=False)   # a status read changes nothing
            override = t.reason == "manual"
            adjusted = t.adjusted
            synced = t.key == self.applied_key
            err = self.last_error
            wmatch = t.weather_match
        w = sch.active_window(now)
        days = []
        for i in range(8):
            d = now.date() + timedelta(days=i)
            s = loc.sun(d)
            plans = sch.day_plans(d)
            wins = [{"on": fmt(p.start), "off": fmt(p.end), "rule": p.rule.name, "effect": p.effect_label()} for p in plans]
            first = wins[0] if wins else {}
            days.append({"date": d.isoformat(), "dow": d.strftime("%a"), "label": d.strftime("%b %d").replace(" 0", " "),
                         "sunrise": fmt(s["sunrise"]), "sunset": fmt(s["sunset"]),
                         "abbr": s["noon"].tzname() if s["noon"] else "", "windows": wins,
                         **{k: first.get(k) for k in ("on", "off", "rule", "effect")}})
        # Day bar: sample what the schedule has on every 5 minutes today
        # (memoized per minute and per settings, since it's ~300 lookups).
        memo_key = (now.date(), now.hour, now.minute, self.cfg_gen)  # id() can be reused after GC
        strip, seg = [], None
        cached_key, cached = self._strip_cache
        rng = [] if cached_key == memo_key else range(0, 1441, 5)
        if cached_key == memo_key:
            strip = cached
        for m in rng:
            aw = sch.active_window(midnight + timedelta(minutes=m)) if m < 1440 else None
            name = aw.rule.name if aw else None
            if seg and seg["rule"] != name:
                seg["end"] = m
                strip.append(seg)
                seg = None
            if name and not seg:
                seg = {"start": m, "end": m, "rule": name}
        self._strip_cache = (memo_key, strip)
        nxt = sch.next_change(now)
        tonight = self._tonight(now, fmt)
        base = self.base_levels(t.effect)
        levels = {**base, **t.levels} if t.on else {}
        rot = None
        if t.on and t.reason in ("schedule", "weather"):
            rule = next((r for r in (self.cfg.weather_rules if t.reason == "weather" else sch.rules)
                         if r.name == t.source), None)
            if rule and len(rule.effects) > 1:
                rot = {"labels": [e.label for e in rule.effects], "minutes": rule.rotate_minutes,
                       "nightly": bool(getattr(rule, "nightly", False)),
                       "each": list(rule.rotate_each) if getattr(rule, "rotate_each", None) else None}
        wx = None
        if self.weather:
            cur = self.weather.current()
            wx = {"summary": cur["summary"], "fresh": cur["fresh"], "error": cur.get("error"),
                  "match": wmatch, "active": t.reason == "weather"}
        return {
            "now": now.isoformat(), "now_label": fmt(now), "now_min": mins(now), "tz": now.tzname(),
            "target": {"on": t.on, "effect": t.effect.label if t.effect else None,
                       "effect_key": t.effect.key if t.effect else None,
                       "reason": t.reason, "source": t.source, "applied": synced, "delegated": t.delegated,
                       "until": fmt(t.until)},
            "levels": {"brightness": levels.get("brightness"), "speed": levels.get("speed"), "adjusted": adjusted},
            "rotation": rot, "weather": wx,
            "flash": {"available": bool(self.cfg.security["effect"]), "minutes": self.cfg.security["minutes"],
                      "active": t.reason == "flash", "until": fmt(t.until) if t.reason == "flash" else None},
            "override": override,
            "music": self._music_status(t, now, fmt),
            "window": {"rule": w.rule.name, "start": fmt(w.start), "end": fmt(w.end)} if w else None,
            "next_change": fmt(nxt), "next_change_day": nxt.strftime("%a") if nxt and nxt.date() != now.date() else None,
            "sun": {k: fmt(v) for k, v in sun.items()},
            "sun_min": {k: mins(v) for k, v in sun.items()},
            "strip": strip, "days": days, "error": err, "tonight": tonight,
            "effects": [{"key": e.key, "label": e.label, "swatches": e.swatches()} for e in self.cfg.effects.values()],
            "devices": devices, "events": list(self.events)[:40],
        }
