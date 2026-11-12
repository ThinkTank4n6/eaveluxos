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
import json
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .api import TrimlightAPI, TrimlightError
from .weather import WeatherService

log = logging.getLogger("eaveluxos")
VERIFY_EVERY = 300  # seconds between read-backs of the controllers


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


class Controller:
    def __init__(self, cfg, api: TrimlightAPI, weather: WeatherService | None = None, safety=None):
        self.cfg = cfg
        self.api = api
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.devices: list[dict] = []
        self.saved: dict[str, dict] = {}      # deviceId -> {name lower: effect dict}
        self.override = None                  # {"on": bool, "effect": key, "since": dt}
        self.adjust: dict = {}                # slider levels {"brightness": n, "speed": n}
        self.flash = None                     # {"until": dt}
        self.sched_key = None
        self.applied_key = None
        self.fail_count = 0
        self.next_try = 0.0
        self.last_error = None
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
            raise TrimlightError(f"No saved effect {what} on this controller. "
                                 f"Run 'python3 main.py effects' to see what's saved.")
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
        for lib in self.saved.values():
            for e in lib.values():
                if (effect.saved_id is not None and e.get("id") == effect.saved_id) or \
                        str(e.get("name", "")).strip().lower() == (effect.saved_name or "").strip().lower():
                    return {"brightness": e.get("brightness"), "speed": e.get("speed")}
        return {}

    # ------------------------------------------------------------ actions
    def _apply(self, on: bool, effect, levels: dict | None = None, timer_off: bool = False, delegated: bool = False):
        """timer_off: when off, use Timer mode (safety net) instead of Off.
        delegated: lights on, run by the controller's own timer (Timer mode)."""
        self._ensure_devices()
        levels = levels or {}
        if delegated:
            for d in self.devices:
                self.api.set_switch(d["deviceId"], 2)
            self.known_on = False
            self.status_cache["at"] = 0.0
            return
        for d in self.devices:
            dev = d["deviceId"]
            if not on:
                self.api.set_switch(dev, 2 if timer_off else 0)
                continue
            # (switch-on is skipped when we already turned it on; effect calls follow)
            if not self.known_on:
                self.api.set_switch(dev, 1)
            if effect.kind == "saved" and not levels:
                self.api.run_saved_effect(dev, int(self._saved_effect(dev, effect).get("id")))
            else:
                payload = (self._payload_from_saved(self._saved_effect(dev, effect))
                           if effect.kind == "saved" else dict(effect.payload))
                payload.update(levels)
                self.api.preview_effect(dev, payload)
        self.known_on = on
        self.status_cache["at"] = 0.0

    def _safety_ready(self) -> bool:
        """Leave the controller in Timer mode between windows only when every
        controller holds a verified copy of the coming nights."""
        if not (self.safety and self.cfg.safety["enabled"] and self.devices):
            return False
        today = self.cfg.loc.now().date()
        return all(self.safety.ready(d["deviceId"], today) for d in self.devices)

    def _weather_pick(self, window):
        """Highest-priority matching weather rule that outranks the window's rule."""
        self.weather_match = None
        if not (self.weather and self.cfg.weather_rules):
            return None
        cur = self.weather.current()
        if not cur["fresh"]:
            return None
        for wr in sorted(self.cfg.weather_rules, key=lambda r: (-r.priority, r.order)):
            if wr.matches(cur["tags"], cur["temp_f"]):
                self.weather_match = wr.name
                return wr if window and wr.priority > window.rule.priority else None
        return None

    def _target(self) -> Target:
        now = self.cfg.loc.now()
        w = self.cfg.schedule.active_window(now)
        sched_key = w.key if w else "off"
        if sched_key != self.sched_key:
            # The first check after startup isn't a scheduled *change*; don't
            # throw away something the user set in the app's first seconds.
            if self.sched_key is not None:
                if self.override or self.adjust:
                    self.note("Scheduled change reached, so manual settings ended.")
                self.override = None
                self.adjust = {}
            self.sched_key = sched_key

        # 1. security flash
        if self.flash:
            if now < self.flash["until"]:
                eff = self.cfg.effects[self.cfg.security["effect"]]
                return Target(f"flash|{self.flash['until'].isoformat()}", True, eff, {}, "flash", "Security flash",
                              self.flash["until"])
            self.flash = None
            self.note("Security flash ended.")

        lv = json.dumps(self.adjust, sort_keys=True)
        # 2. manual
        if self.override and self.override.get("expires") and time.time() > self.override["expires"]:
            self.override = None
            self.adjust = {}
            self.note("Preview ended; back on the schedule.")
        if self.override:
            o = self.override
            eff = (o.get("obj") or self.cfg.effects.get(o.get("effect"))) if o["on"] else None
            if o["on"] and eff is None:  # pattern was deleted
                self.override = None
                return self._target()
            return Target(f"manual|{o['on']}|{o.get('effect')}|{o['since'].isoformat()}|{lv}",
                          o["on"], eff, dict(self.adjust) if o["on"] else {}, "manual")
        if not w:
            self._weather_pick(None)
            return Target("off|timer" if self._safety_ready() else "off", False)
        # 3. weather / 4. schedule, with rotation
        wr = self._weather_pick(w)
        rule = wr or w.rule
        if wr is None:
            eff, step = w.rule.pick(w.start, now)
        elif len(rule.effects) > 1 and rule.rotate_minutes:
            elapsed = max(0, int((now - w.start).total_seconds() // 60))
            step = elapsed // rule.rotate_minutes
            eff = rule.effects[step % len(rule.effects)]
        else:
            step, eff = 0, rule.effects[0]
        # A weather rule keeps the scheduled rule's levels (e.g. late-night dim)
        # unless it sets its own.
        levels = {**w.rule.levels, **(wr.levels if wr else {}), **self.adjust}
        reason = "weather" if wr else "schedule"
        # Hand plain scheduled nights to the controller's own timer (safety
        # net), so the lights still go OFF if this app dies mid-evening. Only
        # when entering the window from armed-off (or already handed over):
        # switching to Timer mode part-way through a night is avoided because
        # it isn't confirmed that the controller re-lights immediately.
        if not wr and not self.adjust:
            entry_end = self._delegation_end(w, eff, now)
            prev = self.applied_key or ""
            if entry_end and now < entry_end - timedelta(minutes=2) and (prev == "off|timer" or prev.startswith(w.key + "|timer")):
                return Target(f"{w.key}|timer|{step}", True, eff, levels, "schedule", rule.name, w.end, delegated=True)
        key = f"{w.key}|{reason}|{rule.name}|{step}|{json.dumps(levels, sort_keys=True)}"
        return Target(key, True, eff, levels, reason, rule.name, w.end)

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

    def tick(self):
        """One scheduling pass. Network calls happen under apply_lock only, so
        status reads (which need just self.lock) never wait on the cloud."""
        with self.apply_lock:
            with self.lock:
                t = self._target()
                due = t.key != self.applied_key and time.time() >= self.next_try
            if due:
                try:
                    self._apply(t.on, t.effect, t.levels, timer_off=t.key == "off|timer", delegated=t.delegated)
                    with self.lock:
                        self.applied_key = t.key
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
        if nxt is not None and nxt - now < timedelta(minutes=3):
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
                    self.applied_key = None  # switch between Off and Timer mode
                    self._kick()

    def _read_devices(self) -> list[dict]:
        """Ask every controller for its state (this also sends it today's time)."""
        out = []
        for d in self.devices:
            det = self.api.get_device(d["deviceId"], self.cfg.loc.now())
            self.saved[d["deviceId"]] = {str(e.get("name", "")).strip().lower(): e for e in det.get("effects", [])}
            out.append({"name": det.get("name", d.get("name")), "id": d["deviceId"],
                        "online": det.get("connectivity") == 1, "switch_raw": det.get("switchState"),
                        "switch": {0: "off", 1: "on", 2: "timer"}.get(det.get("switchState"), "?"),
                        "firmware": det.get("fwVersionName")})
        return out

    def _maintenance(self, t):
        """Every few minutes (and at least daily, for the clock): read the
        controllers back. If one isn't in the state we set (power blip, someone
        used the Trimlight app), restore it. Two readings in a row must disagree
        before acting, so a lagging cloud report can't cause flapping."""
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
            return
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
                self.applied_key = None
                self.known_on = False
                self._kick()
                restored = ", ".join(str(d["name"]) for d in wrong)
        if restored:
            self.note(f"{restored} was changed outside this app (power blip or the Trimlight app). Restoring it.",
                      logging.WARNING)

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
            key = effect_key if obj is None else f"_try:{obj.label}:{hash(json.dumps(obj.payload, sort_keys=True))}"
            self.override = {"on": on, "effect": key, "obj": obj, "since": self.cfg.loc.now(),
                             "expires": time.time() + expires_min * 60 if expires_min else None}
            self.adjust = {}
            self._kick()
        self.tick()

    def resume(self):
        with self.lock:
            if self.override or self.adjust:
                self.note("Back on the schedule.")
            self.override = None
            self.adjust = {}
            self._kick()
        self.tick()

    def set_levels(self, brightness=None, speed=None):
        with self.lock:
            t = self._target()
            if not t.on:
                raise ValueError("The lights are off, so there's nothing to adjust.")
            if t.reason == "flash":
                raise ValueError("Brightness and speed can't be changed during a security flash.")
            for k, v in (("brightness", brightness), ("speed", speed)):
                if v is not None:
                    v = int(v)
                    if not 0 <= v <= 255:
                        raise ValueError(f"{k} must be 0-255")
                    self.adjust[k] = v
            self._kick()
        self.tick()

    def start_flash(self, minutes: int | None = None):
        if not self.cfg.security["effect"]:
            raise ValueError("No security flash is set up. Add a [security] section to config.toml.")
        minutes = max(1, min(240, int(minutes or self.cfg.security["minutes"])))
        with self.lock:
            until = self.cfg.loc.now() + timedelta(minutes=minutes)
            extended = bool(self.flash)
            self.flash = {"until": until}
            self._kick()
            self.note(f"Security flash {'extended' if extended else 'started'} for {minutes} min.")
        self.tick()

    def stop_flash(self):
        with self.lock:
            if self.flash:
                self.flash = None
                self.note("Security flash stopped.")
            self._kick()
        self.tick()

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
            self.applied_key = None   # re-apply whatever the new settings say
            self.status_cache["at"] = 0.0
            self._kick()
        self.tick()

    # ------------------------------------------------------------ loop
    def run_forever(self):
        self.note("Scheduler started.")
        threading.Thread(target=self._weather_loop, daemon=True, name="weather").start()
        while not self.stop_event.is_set():
            try:
                self.tick()
            except Exception:  # never let the loop die
                log.exception("Unexpected error in scheduler loop")
            self.stop_event.wait(self.cfg.interval)

    # ------------------------------------------------------------ status
    def device_status(self, max_age=None):
        """Last controller readings from the background check (no network here)."""
        return [{k: v for k, v in d.items() if k != "switch_raw"} for d in self.status_cache["data"]]

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
            t = self._target()
            override = bool(self.override)
            adjusted = bool(self.adjust)
            synced = t.key == self.applied_key
            err = self.last_error
            wmatch = self.weather_match
        w = sch.active_window(now)
        days = []
        for i in range(8):
            d = now.date() + timedelta(days=i)
            s = loc.sun(d)
            p = sch.day_plan(d)
            days.append({"date": d.isoformat(), "dow": d.strftime("%a"), "label": d.strftime("%b %d").replace(" 0", " "),
                         "sunrise": fmt(s["sunrise"]), "sunset": fmt(s["sunset"]),
                         "abbr": s["noon"].tzname() if s["noon"] else "",
                         "on": fmt(p.start) if p else None, "off": fmt(p.end) if p else None,
                         "rule": p.rule.name if p else None,
                         "effect": (p.rule.pick(p.start, p.start)[0].label if p.rule.nightly else p.rule.effect_label) if p else None})
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
        base = self.base_levels(t.effect)
        levels = {**base, **t.levels} if t.on else {}
        rot = None
        if t.on and t.reason in ("schedule", "weather"):
            rule = next((r for r in (self.cfg.weather_rules if t.reason == "weather" else sch.rules)
                         if r.name == t.source), None)
            if rule and len(rule.effects) > 1:
                rot = {"labels": [e.label for e in rule.effects], "minutes": rule.rotate_minutes,
                       "nightly": bool(getattr(rule, "nightly", False))}
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
            "window": {"rule": w.rule.name, "start": fmt(w.start), "end": fmt(w.end)} if w else None,
            "next_change": fmt(nxt), "next_change_day": nxt.strftime("%a") if nxt and nxt.date() != now.date() else None,
            "sun": {k: fmt(v) for k, v in sun.items()},
            "sun_min": {k: mins(v) for k, v in sun.items()},
            "strip": strip, "days": days, "error": err,
            "effects": [{"key": e.key, "label": e.label, "swatches": e.swatches()} for e in self.cfg.effects.values()],
            "devices": devices, "events": list(self.events)[:40],
        }
