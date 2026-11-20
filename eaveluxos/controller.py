# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""The always-on part: decides what the lights should be doing right now and
makes it so. It drives the controller directly in manual mode, so the
controller's own clock and timers never matter.

What wins, highest first:
  1. Flash                 (security flash, a webhook alert or a score
                            celebration; timed, then everything below resumes)
  1b. Severe weather alert (NWS warning; only while the lights are on unless
                            it's set to turn them on; never during a music show)
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
import itertools
import json
import logging
import os
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from .api import TrimlightAPI, TrimlightError
from .runtime import Runtime
from .safety import _same_effect
from .schedule import Effect, add_real, ts
from .triggers import FLASH_MAX_S, FLASH_MIN_S, PRESETS, AlertWatch
from .weather import WeatherService

log = logging.getLogger("eaveluxos")
VERIFY_EVERY = 300  # seconds between read-backs of the controllers
OFFLINE_VERIFY_EVERY = 60    # 4.15: while one is offline
# Which event wins when two happen at once (3.16.1). A severe weather warning
# sits at 2: above webhook alerts and score celebrations, below the security
# flash (and alerts marked urgent, like an alarm).
FLASH_RANK = {"security": 3, "urgent": 3, "alert": 1, "automation": 1, "score": 0}
ALERT_RANK = 2
MAX_HELD = 8


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
    curve: tuple | None = None   # night curve now (3.18): (kelvin or None, level %)
    parts: dict | None = None    # 4.8: each controller's own: deviceId -> {"on", "effect", "rule", "manual", "until"}
    part_keys: dict | None = None  # 4.8: deviceId -> what that controller shows, as a key (unchanged: not sent again)


class Controller:
    def __init__(self, cfg, api: TrimlightAPI, weather: WeatherService | None = None, safety=None, data_dir=None):
        self.cfg = cfg
        self.api = api
        self.lan = None                       # localmode.Commands when the server sets it (4.4)
        self.lan_state: dict = {}             # deviceId -> 0/1 last sent over the home network (4.5.1)
        self.lan_sent: dict = {}              # deviceId -> {"switch", "pattern"}: which last went over the home network
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.wake = threading.Event()         # wakes the loop early (stop, a flash starting)
        self.devices: list[dict] = []
        self.account: list[dict] = []          # every controller on the account, run here or not (4.5)
        self.saved: dict[str, dict] = {}      # deviceId -> {name lower: effect dict}
        self.override = None                  # {"on": bool, "effect": key, "since": dt}
        # 4.8: a manual choice for one controller: deviceId -> {"on", "effect",
        # "obj", "since", "wkey"}; it ends when that controller's schedule changes.
        self.dev_override: dict = {}
        self._dov_seq = itertools.count(1)
        self.adjust: dict = {}                # slider levels {"brightness": n, "speed": n}
        self.flash = None                     # the flash showing: {"until", "eff", "label", "kind", "rank", "since"}
        self.flash_held: list = []            # longer flashes a shorter one interrupted; they resume after it
        self.dismissed_path = os.path.join(str(data_dir), "alert-dismissed.json") if data_dir else None
        # The day the holiday was announced, kept across restarts (3.19.1).
        self.noted_path = os.path.join(str(data_dir), "holiday-noted.txt") if data_dir else None
        self.alert_dismissed: dict = self._load_dismissed()   # warning name (lower) -> when dismissed (epoch)
        self.music = None                     # music show from the button: {"until": dt | None, "since": dt}
        self.holiday_noted = None             # the day the morning holiday note was written (3.19)
        self.music_skipped = None             # key of a show night stopped early (don't restart it)
        self.last_on = None                   # last pattern turned on by hand (for the On button)
        self.sched_key = None
        self.applied_key = None
        self.applied_parts: dict = {}         # 4.8: deviceId -> part key last sent, while applied_key holds
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
        self.wx_alerts = self._make_alerts(cfg)
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
        self.offline: set = set()             # 4.15: controllers the cloud said were offline at the last read-back
        # 4.15: what the lights were doing, kept across app restarts (smart recovery)
        self.state_path = os.path.join(str(data_dir), "lights-state.json") if data_dir else None
        self._state_text = None
        self.recovered = None                 # what a restart brought back, for Activity and Home
        self._restore_state()

    # --- 4.15: smart recovery after the app restarts or the computer loses power ----
    RESTORE_WITHIN = 24 * 3600    # older saved state is ignored
    TRUST_SENT = 1800             # what was sent counts as showing for this long (checked at once)

    @staticmethod
    def _ser(o):
        """A choice made by hand, as JSON; None for a preview of an unsaved
        pattern (its pattern isn't saved anywhere to bring back)."""
        if not o or o.get("obj") is not None:
            return None
        since = o.get("since")
        return {k: v for k, v in {**o, "since": since.isoformat() if hasattr(since, "isoformat") else since,
                                  "restore": None}.items() if k not in ("obj", "restore", "n")}

    def _save_state(self):
        if not self.state_path:
            return
        with self.lock:
            m = self.music
            fl = self.flash
            data = {
                "sched_key": self.sched_key,
                "override": self._ser(self.override),
                "dev_override": {d: x for d, o in self.dev_override.items() if (x := self._ser(o))},
                "adjust": self.adjust or {},
                # a show from a button, a webhook or a show night; not one from this computer's page (it's gone)
                "music": {"until": m["until"].isoformat() if m.get("until") else None, "by": m.get("by")}
                if m and not str(m.get("by") or "").startswith("lan:") else None,
                "flash": {"until": fl["until"].isoformat(), "label": fl.get("label"), "kind": fl.get("kind"), "rank": fl.get("rank")}
                if fl and fl.get("eff") is None else None,             # the security flash (its pattern is in the settings)
                "applied_key": self.applied_key, "applied_parts": self.applied_parts, "known_on": self.known_on,
                "sent_effect": self.sent_effect, "last_on": self.last_on,
            }
        try:
            text = json.dumps(data, sort_keys=True, default=str)
        except (TypeError, ValueError):
            return
        if text == self._state_text:
            return
        self._state_text = text
        try:
            tmp = self.state_path + f".{os.getpid()}.tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(json.dumps({**json.loads(text), "saved_at": time.time()}))
            os.replace(tmp, self.state_path)
        except OSError as e:
            log.debug("Couldn't save the lights' state: %s", e)

    def _restore_state(self):
        if not self.state_path or not os.path.isfile(self.state_path):
            return
        try:
            with open(self.state_path, encoding="utf-8") as f:
                d = json.load(f)
            age = time.time() - float(d.get("saved_at") or 0)
        except (OSError, ValueError, TypeError):
            return
        if not 0 <= age <= self.RESTORE_WITHIN:
            return
        now, brought = time.time(), []

        def back(o):
            if not isinstance(o, dict) or (o.get("expires") and o["expires"] < now):
                return None
            o = dict(o)
            try:
                o["since"] = datetime.fromisoformat(o["since"]) if o.get("since") else self.cfg.loc.now()
            except (TypeError, ValueError):
                o["since"] = self.cfg.loc.now()
            if o.get("on") and o.get("effect") and o["effect"] not in self.cfg.effects:
                return None                        # its pattern was deleted meanwhile
            o["obj"] = None
            return o
        try:
            self.sched_key = d.get("sched_key")        # so a scheduled change while the app was off still ends a choice by hand
            ov = back(d.get("override"))
            if ov:
                self.override = ov
                brought.append("your choice for every controller" if ov["on"] else "Off, chosen by hand")
            for dev, o in (d.get("dev_override") or {}).items():
                o = back(o)
                if o:
                    o["n"] = next(self._dov_seq)
                    self.dev_override[dev] = o
            if self.dev_override:
                brought.append("each controller's own choice")
            if isinstance(d.get("adjust"), dict):
                self.adjust = d["adjust"]
            m = d.get("music")
            if isinstance(m, dict):
                until = datetime.fromisoformat(m["until"]) if m.get("until") else None
                if until is None or ts(until) > now:
                    self.music = {"since": self.cfg.loc.now(), "until": until, "by": m.get("by")}
                    brought.append("the music show")
            fl = d.get("flash")
            if isinstance(fl, dict) and fl.get("until") and self.cfg.security["effect"]:
                until = datetime.fromisoformat(fl["until"])
                if ts(until) > now:
                    self.flash = {"until": until, "eff": None, "label": fl.get("label"), "kind": fl.get("kind") or "security",
                                  "rank": fl.get("rank", 3), "since": now}
                    brought.append(fl.get("label") or "the security flash")
            self.last_on = d.get("last_on") if d.get("last_on") in self.cfg.effects else None
            if age <= self.TRUST_SENT and d.get("applied_key"):
                # What was sent a moment ago is most likely still showing: don't
                # send it again (no restart of its motion, no extra commands),
                # but check at once, and act on the first difference found.
                self.applied_key = d["applied_key"]
                self.applied_parts = d.get("applied_parts") or {}
                self.known_on = bool(d.get("known_on"))
                self.sent_effect = d.get("sent_effect") or {}
                self.mismatches = 1
                self.pattern_mismatches = 1
                self.last_verify = 0.0
        except (TypeError, ValueError, KeyError) as e:
            log.info("Couldn't bring back the lights' state from before the restart: %s", e)
            return
        self.recovered = brought
        if brought:
            self.note("After the restart, brought back: " + ", ".join(brought) + ".")

    @staticmethod
    def _make_alerts(cfg, old=None):
        """The NWS warning checker; keeps what `old` already knows when the
        location is the same, so changing a setting doesn't drop an alert
        that's showing until the next check (3.16.1)."""
        a = cfg.weather_alerts
        if not a["enabled"]:
            return None
        w = AlertWatch(cfg.loc.lat, cfg.loc.lon, a["groups"], cfg.weather.get("contact", ""))
        if old is not None:
            w.adopt(old)
        return w

    def _load_dismissed(self) -> dict:
        if not self.dismissed_path:
            return {}
        try:
            with open(self.dismissed_path, encoding="utf-8") as f:
                raw = json.load(f)
        except (OSError, ValueError):
            return {}
        cut = time.time() - 7 * 86400          # a warning lasts days at most
        return {str(k): float(v) for k, v in (raw.items() if isinstance(raw, dict) else [])
                if isinstance(v, (int, float)) and v > cut}

    def _save_dismissed(self):
        if not self.dismissed_path:
            return
        try:
            tmp = self.dismissed_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.alert_dismissed, f)
            os.replace(tmp, self.dismissed_path)
        except OSError as e:
            log.warning("Couldn't save dismissed weather alerts: %s", e)

    def _alert_effect(self):
        key = self.cfg.weather_alerts["effect"]
        if key in self.cfg.effects:
            return self.cfg.effects[key]
        eff = Effect.from_config("_alert", PRESETS.get(key) or PRESETS["severe"], self.cfg.gamma)
        eff.label = (PRESETS.get(key) or PRESETS["severe"])["label"]
        return eff

    def active_alert(self, now=None):
        """The weather warning to show now, if any. A dismissed warning stays
        dismissed by name while the Weather Service keeps updating it (each
        update has a new id); once it's gone, a new one shows again."""
        if not (self.wx_alerts and self.cfg.weather_alerts["enabled"]):
            return None
        now = now or self.cfg.loc.now()
        live = [a for a in self.wx_alerts.active(now) if a["event"].lower() not in self.alert_dismissed]
        order = list(self.cfg.weather_alerts["groups"])
        live.sort(key=lambda a: order.index(a["group"]) if a["group"] in order else 99)
        return live[0] if live else None

    def _invalidate(self):
        """Send the target again on the next pass, in full. Lock held."""
        self.applied_key = None
        self.applied_parts = {}
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
        self.account = list(found)
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
        if effect.kind == "split":
            first = next((p for p in list(effect.parts.values()) + [effect.rest] if p is not None), None)
            return self.base_levels(first)
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
    def _switch(self, dev: str, state: int):
        """On (1) and off (0) over the home network when that's set up and
        works (4.4), else through Trimlight's cloud. Timer mode (2) always
        goes through the cloud."""
        if state in (0, 1) and self.lan is not None and self.lan.power(dev, state == 1):
            self._sent(dev, "switch", True)
            self.lan_state[dev] = state
            return
        self._sent(dev, "switch", False)
        self.api.set_switch(dev, state)

    def _show_saved(self, dev: str, pid: int):
        if self.lan is not None and self.lan.show(dev, pid):
            self._sent(dev, "pattern", True)
            return
        self._sent(dev, "pattern", False)
        self.api.run_saved_effect(dev, pid)

    def _sent(self, dev: str, what: str, local: bool):
        """Note which way the on/off ("switch") and the pattern last went
        (4.4.1). Each is checked where it was sent: the cloud doesn't hear
        about a change made over the home network, so after a local "on" and
        a pattern through the cloud, the cloud still says off."""
        got = self.lan_sent.setdefault(dev, set())
        (got.add if local else got.discard)(what)
        if not got:
            self.lan_sent.pop(dev, None)

    def _apply(self, on: bool, effect, levels: dict | None = None, timer_off: bool = False, delegated: bool = False,
               skip=frozenset()):
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
        some_off = False
        for d in self.devices:
            dev = d["deviceId"]
            if dev in skip:
                # 4.8: this controller already shows its part (only another
                # controller's rule changed); sending it again would only
                # restart its motion and add commands.
                some_off = some_off or not on or (effect is not None and effect.for_device(dev) is None)
                continue
            self.sent_effect.pop(dev, None)
            part = effect.for_device(dev) if on and effect is not None else effect
            if not on or (effect is not None and effect.kind == "split" and part is None):
                # A split pattern can leave a controller off (3.17).
                self._switch(dev, 2 if timer_off else 0)
                some_off = True
                continue
            effect_d = part
            # A split pattern's parts keep their own speed, and a brightness
            # set by a rule or the slider scales each part by the same ratio,
            # so upstairs stays dimmer than the garage (3.17.1).
            lv = levels if effect.kind != "split" else {k: v for k, v in levels.items() if k == "brightness"}
            if effect.part_levels is not None:
                lv = dict(effect.part_levels.get(dev) or {})    # 4.8: this controller's own rule's levels
            # (switch-on is skipped when we already turned it on; effect calls follow)
            if not self.known_on or (effect.kind == "split"):
                self._switch(dev, 1)
            if effect_d.kind == "saved" and not lv:
                saved = self._saved_effect(dev, effect_d)
                self._show_saved(dev, int(saved.get("id")))
                self.sent_effect[dev] = {**self._payload_from_saved(saved), "id": int(saved.get("id"))}
            else:
                payload = (self._payload_from_saved(self._saved_effect(dev, effect_d))
                           if effect_d.kind == "saved" else dict(effect_d.payload))
                if effect.kind == "split" and lv and effect.part_levels is None:
                    base = self.base_levels(effect).get("brightness") or 255
                    payload["brightness"] = max(1, min(255, round(payload.get("brightness", 255) * lv["brightness"] / max(1, base))))
                else:
                    payload.update(lv)
                # 4.4.2: the same as a pattern saved on the controller? Show
                # that one over the home network, by its number.
                pid = self.lan.show_like(dev, payload) if self.lan is not None and effect.kind != "split" else None
                if pid:
                    self._sent(dev, "pattern", True)
                    self.sent_effect[dev] = {**payload, "id": pid}
                    continue
                # 4.6: otherwise shown live over the home network, as the
                # Trimlight app previews; the cloud only when that can't be done.
                if self.lan is not None and effect.kind != "split" and self.lan.preview(dev, payload):
                    self._sent(dev, "pattern", True)
                    self.sent_effect[dev] = payload
                    continue
                self.api.preview_effect(dev, payload)
                self._sent(dev, "pattern", False)       # this one went through the cloud
                self.sent_effect[dev] = payload
        self.status_cache["at"] = 0.0
        return on and not some_off          # "all switched on": else the next pattern switches each one on

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
        sch = self.cfg.schedule
        override, adjust, flash, held, notes = self.override, self.adjust, self.flash, self.flash_held, []
        devs = [d["deviceId"] for d in self.devices]
        # Review #2 (4.8): a choice for a controller this app no longer runs is
        # kept for when it does, but doesn't count now; it made every night
        # "each controller on its own" (no handing nights to the controllers'
        # timers) until the app restarted.
        dov = {dev: o for dev, o in self.dev_override.items() if dev in devs}
        kept = {dev: o for dev, o in self.dev_override.items() if dev not in devs}
        ws = None
        if devs and (sch.per_controller or dov or len(devs) > 1):
            # 4.8: each controller follows its own rules (and its own manual
            # choice). When they all agree, it's one window, as before.
            ws = {dev: sch.for_controller(dev).active_window(now) for dev in devs}
            wkeys = {dev: (x.key if x else "off") for dev, x in ws.items()}
            for dev in list(dov):
                if dev not in wkeys:
                    continue                      # not run right now; kept for when it is
                if dov[dev].get("expires") and time.time() > dov[dev]["expires"]:
                    r = dov[dev].get("restore")
                    if r and r.get("wkey") == wkeys[dev] and not (r.get("expires") and time.time() > r["expires"]):
                        # 4.11: an automation's flash on one controller ends;
                        # back to the choice it covered (Review #3).
                        notes.append(f"Flash ended on {self._dev_name(dev)}; back to what it showed.")
                        dov[dev] = {**r, "n": next(self._dov_seq)}
                    else:
                        notes.append(f"Preview ended on {self._dev_name(dev)}; back on the schedule.")
                        dov.pop(dev)
                elif dov[dev].get("wkey") != wkeys[dev]:
                    notes.append(f"Scheduled change reached for {self._dev_name(dev)}, so its manual setting ended.")
                    dov.pop(dev)
            if len(set(wkeys.values())) == 1:
                w = ws[devs[0]]
                sched_key = wkeys[devs[0]]
            else:
                w = None
                sched_key = "multi|" + "|".join(f"{dev}={k}" for dev, k in sorted(wkeys.items()))
        else:
            # Before the controllers are known (the first pass after starting),
            # only rules for all of them count: a rule for one controller must
            # never reach the others, even once.
            w = (sch.for_controller("\0") if sch.per_controller else sch).active_window(now)
            sched_key = w.key if w else "off"
        if sched_key != self.sched_key:
            # The first check after startup isn't a scheduled *change*; don't
            # throw away something the user set in the app's first seconds.
            if self.sched_key is not None:
                if override or adjust:
                    notes.append("Scheduled change reached, so manual settings ended.")
                override, adjust = None, {}

        alert_on = False

        def done(t: Target) -> Target:
            if alert_on:
                # A severe weather alert replaces whatever is on (or turns the
                # lights on, if set to), but never interrupts a music show.
                alert = self.active_alert(now)
                if alert and not t.hands_off and (t.on or self.cfg.weather_alerts["turn_on"]):
                    t = Target(f"alert|{alert['id']}", True, self._alert_effect(), {}, "alert", alert["event"],
                               alert["ends"].astimezone(now.tzinfo) if alert["ends"] else None,
                               weather_match=t.weather_match)
            t.adjusted = bool(adjust) and t.reason not in ("flash", "alert") and t.on
            if ws is not None and t.part_keys is None and t.reason in ("schedule", "weather") \
                    and not t.delegated and t.key != "off|timer":
                # 4.8: one window for all: each controller's part is the same,
                # under the same key a controller's own window would have, so
                # moving to (or from) different rules sends only what changed.
                t.part_keys = {dev: t.key for dev in ws}
            if commit:
                self.sched_key = sched_key
                self.override, self.adjust, self.flash, self.flash_held = override, adjust, flash, held
                self.dev_override = {**kept, **dov}
                self.weather_match = t.weather_match
                for n in notes:
                    self.note(n)
            return t

        # 1. flash (security flash, webhook alert, score celebration). When
        # one ends, a longer one it interrupted carries on.
        while flash:
            # The security pattern can be cleared or replaced in settings while a
            # flash runs; with none left, end the flash instead of failing
            # every pass (and every status read) until it would have ended.
            eff = flash.get("eff") or self.cfg.effects.get(self.cfg.security["effect"] or "")
            label = flash.get("label") or "Security flash"
            if eff is not None and ts(now) < ts(flash["until"]):
                return done(Target(f"flash|{flash['until'].isoformat()}|{label}", True, eff, {}, "flash", label,
                                   flash["until"]))
            notes.append(f"{label} ended." if eff is not None
                         else f"{label} ended: no flash pattern is set up any more.")
            live = [f for f in held if ts(now) < ts(f["until"])]
            flash = max(live, key=lambda f: (f.get("rank", 3), f.get("since", 0))) if live else None
            held = [f for f in live if f is not flash]
            if flash:
                notes.append(f"Back to {flash.get('label') or 'Security flash'}.")
        # 1b. severe weather alert: applied by done() over whatever comes
        # below (music show excepted).
        alert_on = True

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
            r = override.get("restore")
            if r and not (r.get("expires") and time.time() > r["expires"]):
                notes.append("Preview ended; back to what showed before.")      # 4.16
                override = r
            else:
                notes.append("Mood follow ended (no word from the listening page); back on the schedule."
                             if override.get("mood") else "Preview ended; back on the schedule.")
                override, adjust = None, {}
        if override:
            o = override
            eff = (o.get("obj") or self.cfg.effects.get(o.get("effect"))) if o["on"] else None
            if o["on"] and eff is None:  # pattern was deleted
                override = None
            else:
                lv = json.dumps(adjust, sort_keys=True)
                return done(Target(f"manual|{o['on']}|{o.get('effect')}|{o['since'].isoformat()}|{lv}",
                                   o["on"], eff, dict(adjust) if o["on"] else {}, "manual"))
        if ws is not None and (dov or len({(x.key if x else "off") for x in ws.values()}) > 1):
            return done(self._each_own(ws, dov, now, adjust))
        if not w:
            _, match = self._weather_pick(None)
            return done(Target("off|timer" if self._safety_ready() else "off", False, weather_match=match))
        # 4. weather / 5. schedule, with rotation
        wr, match, rule, eff, step, levels, reason, cv = self._scheduled(w, now, adjust)
        # Hand plain scheduled nights to the controller's own timer (safety
        # net), so the lights still go OFF if this app dies mid-evening. Only
        # when entering the window from armed-off (or already handed over):
        # switching to Timer mode part-way through a night is avoided because
        # it isn't confirmed that the controller re-lights immediately.
        if not wr and not adjust and not w.rule.curve:      # a curve needs the app to change it
            entry_end = self._delegation_end(w, eff, now)
            prev = self.applied_key or ""
            if entry_end and ts(now) < ts(entry_end) - 120 and (prev == "off|timer" or prev.startswith(w.key + "|timer")):
                return done(Target(f"{w.key}|timer|{step}", True, eff, levels, "schedule", rule.name, w.end,
                                   delegated=True, weather_match=match))
        key = f"{w.key}|{reason}|{rule.name}|{step}|{json.dumps(levels, sort_keys=True)}" + (f"|k{cv[0]}" if cv else "")
        return done(Target(key, True, eff, levels, reason, rule.name, w.end, weather_match=match, curve=cv))

    def _scheduled(self, w, now, adjust):
        """What window w shows now: (weather rule or None, best weather
        match, the rule in charge, pattern, rotation step, levels, reason,
        night curve now). Shared by one window for all controllers and by
        each controller's own (4.8)."""
        wr, match = self._weather_pick(w)
        rule = wr or w.rule
        eff, step = rule.pick(w.start, now)   # the weather rule's own rotation, or the schedule's
        # A weather rule keeps the scheduled rule's levels (e.g. late-night dim)
        # unless it sets its own.
        levels = {**w.rule.levels, **(wr.levels if wr else {}), **adjust}
        reason = "weather" if wr else "schedule"
        cv = None
        if w.rule.curve:
            # Night curve (3.18): whites and brightness change through the
            # night in 10-minute steps; a brightness set by hand still wins.
            # Each step sends the pattern again, which restarts its motion,
            # so a moving pattern steps every 30 minutes, not every 10. A
            # weather pattern keeps its own whites (snow white stays snow
            # white) and follows only the curve's brightness (3.18.2).
            from .circadian import STEP_MIN, STEP_MOVING, curve_at, curve_levels, moves, with_white
            k, lvl = curve_at(w.rule.curve, w, now, self.cfg.loc, STEP_MOVING if moves(eff) else STEP_MIN)
            if wr:
                k = None
            eff = with_white(eff, k, self.cfg.gamma)
            if "brightness" not in adjust:
                levels = curve_levels(self.base_levels(eff).get("brightness"), levels, lvl)
            cv = (k, lvl)
        return wr, match, rule, eff, step, levels, reason, cv

    def _dev_name(self, dev: str) -> str:
        return next((str(d.get("name") or dev) for d in self.devices + self.account if d.get("deviceId") == dev), dev)

    def _each_own(self, ws: dict, dov: dict, now, adjust) -> Target:
        """4.8: the controllers follow different rules (or one has its own
        manual choice). Each one's pattern, with its own rule's brightness
        and speed, is put together as a split pattern and sent the way Split
        by controller is: one controller can be off while another is on.
        The controller's own timer isn't handed the night (each controller's
        night is different), so the app runs it, as for a night curve."""
        parts, levels_of, info, keys, reasons, ends, match = {}, {}, {}, [], set(), [], None
        for dev, wd in sorted(ws.items()):
            o = dov.get(dev)
            if o is not None:
                eff = (o.get("obj") or self.cfg.effects.get(o.get("effect"))) if o["on"] else None
                eff, _ = self._own_part(eff, dev, {})
                parts[dev], levels_of[dev] = eff, {}
                info[dev] = {"on": eff is not None, "effect": eff.label if eff else None, "rule": None,
                             "manual": True, "until": wd.end if wd else None}
                keys.append(f"{dev}=manual|{o['on']}|{o.get('effect')}|{o['since'].isoformat()}|{o.get('n', 0)}")
                reasons.add("manual")
                if wd:
                    ends.append(wd.end)
                continue
            if wd is None:
                parts[dev], levels_of[dev] = None, {}
                info[dev] = {"on": False, "effect": None, "rule": None, "manual": False, "until": None}
                keys.append(f"{dev}=off")
                continue
            wr, m, rule, eff, step, lv, reason, cv = self._scheduled(wd, now, adjust)
            match = match or m
            eff, lv = self._own_part(eff, dev, lv)
            parts[dev], levels_of[dev] = eff, lv
            info[dev] = {"on": eff is not None, "effect": eff.label if eff else None, "rule": rule.name,
                         "manual": False, "until": wd.end}
            keys.append(f"{dev}={wd.key}|{reason}|{rule.name}|{step}|{json.dumps(lv, sort_keys=True)}"
                        + (f"|k{cv[0]}" if cv else ""))
            reasons.add(reason)
            ends.append(wd.end)
        if match is None:
            _, match = self._weather_pick(None)
        pkeys = dict(k.split("=", 1) for k in keys)
        if all(p is None for p in parts.values()):
            return Target("multi|" + "|".join(keys), False, weather_match=match, parts=info, part_keys=pkeys)
        label = " \u00b7 ".join(f"{self._dev_name(dev)}: {p.label if p else 'off'}" for dev, p in parts.items())
        eff = Effect("each", label, "split", parts=parts, rest=None, part_levels=levels_of)
        eff.payload = {"parts": {dev: (p.kind, p.payload, p.saved_name, p.saved_id, levels_of[dev]) if p else None
                                 for dev, p in parts.items()}}
        reason = "manual" if "manual" in reasons else "weather" if "weather" in reasons else "schedule"
        rules = sorted({i["rule"] for i in info.values() if i["rule"]})
        return Target("multi|" + "|".join(keys), True, eff, {}, reason, " \u00b7 ".join(rules) or None,
                      min(ends, key=ts) if ends else None, weather_match=match, parts=info, part_keys=pkeys)

    def _own_part(self, eff, dev: str, lv: dict):
        """A split pattern chosen for one controller (by its rule or by
        hand) is that controller's part of it, and a brightness the rule sets
        scales the part as Split by controller does (3.17.1); its speed stays
        the part's own. Returns (pattern or None for off, levels)."""
        if eff is None or eff.kind != "split":
            return eff, lv
        part = eff.for_device(dev)
        out = {}
        if part is not None and "brightness" in lv:
            base = self.base_levels(eff).get("brightness") or 255
            own = self.base_levels(part).get("brightness") or 255
            out["brightness"] = max(1, min(255, round(own * lv["brightness"] / max(1, base))))
        return part, out

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
            if not self.devices and time.time() >= self.next_try:
                # 4.8: each controller's own rules need to know them first. Not
                # while waiting out a failure (review #1): that asked the cloud
                # every pass instead of backing off.
                try:
                    self._ensure_devices()
                except TrimlightError:
                    pass                         # sending below fails the same way and backs off
            with self.lock:
                t = self._target()
                due = t.key != self.applied_key and time.time() >= self.next_try
                gen = self.apply_gen
                skip = frozenset(dev for dev, k in (t.part_keys or {}).items()
                                 if self.applied_key is not None and self.applied_parts.get(dev) == k)
            if t.hands_off and self.safety:
                self.safety.hold()           # and none for 15 minutes after it (4.2.1)
            if due and t.hands_off:
                # A music show: send nothing, so the controller's music mode
                # isn't interrupted. What it shows afterward is unknown, so the
                # next pattern is sent in full.
                with self.lock:
                    if self.apply_gen == gen:
                        self.applied_key = t.key
                        self.applied_parts = {}
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
                                              delegated=t.delegated, skip=skip)
                    with self.lock:
                        if self.apply_gen == gen:
                            self.applied_key = t.key
                            self.applied_parts = dict(t.part_keys or {})
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
                            else f"on ({t.effect.label}{lv})" if t.on else ("off (backup timer armed)" if t.key == "off|timer" else "off"))
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
                self._holiday_morning()

    HOLIDAY_MORNING = 6      # o'clock: the holiday's playlist is announced (3.19)

    def holiday_today(self, now=None) -> dict | None:
        """Today's holiday whose lights run tonight (the schedule's own pick,
        so a game day or a higher rule tonight wins): name, playlist, from."""
        now = now or self.cfg.loc.now()
        for p in self.cfg.schedule.day_plans(now.date()):
            if getattr(p.rule, "holiday", None):
                on = p.start.strftime("%I:%M %p").lstrip("0")
                return {"name": p.rule.holiday, "playlist": p.effect_label(), "on": on,
                        "patterns": [e.label for e in p.rule.effects]}
        return None

    def _holiday_morning(self):
        """On a holiday's morning, load its playlist for tonight: say so in
        the log and on Home (the schedule already has it; 3.19)."""
        now = self.cfg.loc.now()
        if self.holiday_noted is None and self.noted_path:
            try:
                with open(self.noted_path, encoding="utf-8") as f:
                    self.holiday_noted = date.fromisoformat(f.read().strip())
            except (OSError, ValueError):
                self.holiday_noted = date.min
        if now.hour < self.HOLIDAY_MORNING or self.holiday_noted == now.date():
            return
        self.holiday_noted = now.date()
        if self.noted_path:
            try:
                with open(self.noted_path, "w", encoding="utf-8") as f:
                    f.write(now.date().isoformat())
            except OSError as e:
                log.warning("Couldn't save the holiday note day: %s", e)
        h = self.holiday_today(now)
        if h:
            self.note(f"Today is {h['name']}: tonight's lights are {h['playlist']}, from {h['on']}.")

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
            self.safety.clear_halt()      # off and on again clears a halt (4.2.1)
        # Never write next to a music show (the button's, a show night or the
        # local link: tick() holds it while one runs) or local-link use.
        if self.safety.held():
            return
        if not self.cfg.safety["enabled"]:
            if now_ts >= self.safety.retry_at and not self.safety.remove(self.api, ids, now, self.note):
                self.safety.retry_at = now_ts + 1800  # don't retry (and back up) every few seconds
            return
        off = getattr(self.api, "clock_offset_min", 0)
        if self.cfg.schedule.per_controller:      # 4.8: each controller's own nights
            h = {dev: self.safety.plan_hash(*self.safety.plan(self.cfg, now, off, dev)) for dev in ids}
        else:
            h = self.safety.plan_hash(*self.safety.plan(self.cfg, now, off))
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
        # 4.15: while a controller is offline (a power cut), look every minute
        every = OFFLINE_VERIFY_EVERY if self.offline else VERIFY_EVERY
        if not self.devices or (now - self.last_verify < every and self.last_clock_sync == today):
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
        # 4.4: a controller set over the home network is checked there too;
        # Trimlight's cloud may not have caught up with it yet.
        # 4.5.1: only when the cloud disagrees with what was sent. Reading
        # every 5 minutes, all night, meant hundreds of full reads (each also
        # sets the controller's clock); on Nov 17 the controller stopped
        # answering reads at 2:56 AM after hours of them.
        for d in snap:
            if ("switch" in self.lan_sent.get(d["id"], ()) and self.lan is not None
                    and d["switch_raw"] != self.lan_state.get(d["id"])):
                sw = self.lan.switch(d["id"])
                if sw in (0, 1):
                    d["switch_raw"], d["switch"] = sw, ("off", "on")[sw]     # Home shows it too (4.4.1)
        restored = None
        # Review #1 (4.15): a controller back online after a power cut is set
        # again at once, whatever it shows (it may have come back off, or in
        # the controller's own default), instead of waiting for two read-backs.
        back = [d["name"] for d in snap if d["online"] and d["id"] in self.offline]
        self.offline = {d["id"] for d in snap if not d["online"]}
        if back:
            with self.lock:
                self.mismatches = self.pattern_mismatches = 0
                self._invalidate()
            self.note(f"{', '.join(map(str, back))} is back online (after a power cut?). Setting its lights again.",
                      logging.WARNING)
        with self.lock:
            self.status_cache = {"at": now, "data": snap}
            if t.key != self.applied_key:
                return
            want = 2 if t.delegated else 1 if t.on else (2 if t.key == "off|timer" else 0)

            def want_for(d):            # a split pattern can leave a controller off (3.17)
                if want == 1 and t.effect is not None and t.effect.kind == "split" and t.effect.for_device(d["id"]) is None:
                    return 0
                return want
            wrong = [d for d in snap if d["online"] and d["switch_raw"] != want_for(d)]
            self.mismatches = self.mismatches + 1 if wrong else 0
            if self.mismatches >= 2:
                self.mismatches = 0
                self.pattern_mismatches = 0
                self._invalidate()
                restored = ", ".join(str(d["name"]) for d in wrong)
            elif not wrong and not any("pattern" in self.lan_sent.get(d["id"], ()) for d in snap):
                restored = self._check_pattern(t, snap)   # (the cloud's view of the pattern lags local commands)
        self._save_reported()
        if restored:
            self.note(f"{restored} was changed outside this app (power blip or the Trimlight app). Restoring it.",
                      logging.WARNING)

    def _plans_all(self, d) -> list:
        """[(plan, controller names or None for all)] for windows starting on
        date d. With rules for some controllers only (4.8), each controller's
        own nights together, a window shared by all of them listed once."""
        sch = self.cfg.schedule
        devs = [(x["deviceId"], str(x.get("name") or x["deviceId"])) for x in list(self.devices)]
        if not sch.per_controller or not devs:
            return [(p, None) for p in sch.day_plans(d)]
        got = {}
        for dev, name in devs:
            for p in sch.for_controller(dev).day_plans(d):
                got.setdefault((p.rule.name, ts(p.start), ts(p.end)), (p, []))[1].append(name)
        out = sorted(got.values(), key=lambda x: (ts(x[0].start), ts(x[0].end)))
        return [(p, None if len(names) == len(devs) else names) for p, names in out]

    def _tonight(self, now: datetime, fmt) -> list[dict]:
        """Home's "Tonight" timeline (3.15): what the schedule does in the
        next 24 hours (sunset, on, a switch to another rule, off), with
        minutes from now worked out here, so a phone's own clock can't skew
        the countdown."""
        sch, loc = self.cfg.schedule, self.cfg.loc
        horizon = ts(now) + 24 * 3600
        seen, plans, whose = set(), [], {}
        for dd in (now.date() - timedelta(days=1), now.date(), now.date() + timedelta(days=1)):
            for p, names in self._plans_all(dd):
                k = (ts(p.start), ts(p.end), p.rule.name)
                if k not in seen and ts(p.end) > ts(now) and ts(p.start) < horizon:
                    seen.add(k)
                    plans.append(p)
                    whose[id(p)] = f" ({', '.join(names)})" if names else ""
        plans.sort(key=lambda p: ts(p.start))
        ev = []
        for dd in (now.date(), now.date() + timedelta(days=1)):
            ss = loc.sun(dd).get("sunset")
            if ss and ts(now) < ts(ss) < horizon:
                ev.append((ts(ss), "sunset", ss, "Sunset"))
                break
        for i, p in enumerate(plans):
            prev_end = ts(plans[i - 1].end) if i else None
            what = (f"{p.rule.name}: {p.effect_label()}" if p.effect_label() != p.rule.name else p.rule.name) + whose[id(p)]
            if ts(p.start) > ts(now):
                ev.append((ts(p.start), "switch" if prev_end == ts(p.start) else "on", p.start, what))
            if not (i + 1 < len(plans) and ts(plans[i + 1].start) == ts(p.end)) and ts(p.end) < horizon:
                ev.append((ts(p.end), "off", p.end, p.rule.name + whose[id(p)]))
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
                    for d in snap if d["online"] and d["id"] in self.sent_effect]
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

    def manual(self, on: bool, effect_key: str | None = None, obj=None, expires_min: int | None = None,
               device: str | None = None):
        """obj: an unsaved Effect to try out (pattern designer, built-in
        browser, bulb finder). expires_min: previews end by themselves, so a
        forgotten bulb-finder highlight can't replace the lights all night.
        device (4.8): for that one controller only (Home's controller cards);
        without it, for all of them, and any one controller's choice ends."""
        if device is not None:
            return self.manual_one(device, on, effect_key)
        with self.lock:
            if on and obj is None and effect_key not in self.cfg.effects:
                raise ValueError(f"Unknown pattern '{effect_key}'")
            if not expires_min:
                # Review #3 (4.8): a preview (Try, the bulb finder) ends by
                # itself and leaves each controller's own choice as it was.
                self.dev_override = {}
            self._end_music("a pattern was chosen")
            # Choosing On, Off or a pattern by hand during a weather alert
            # means "not now": dismiss it, so the choice actually shows (3.16.1).
            if self._target(commit=False).reason == "alert":
                a = self.active_alert()
                if a:
                    self.alert_dismissed[a["event"].lower()] = time.time()
                    self._save_dismissed()
                    self.note(f"Weather alert dismissed by a manual change: {a['event']}")
            if on and obj is None:
                self.last_on = effect_key
            key = effect_key if obj is None else f"_try:{obj.label}:{hash(json.dumps(obj.payload, sort_keys=True))}"
            prev = self.override
            if prev and prev.get("obj") is not None and prev.get("expires"):
                prev = prev.get("restore")              # 4.16: what the first preview covered
            self.override = {"on": on, "effect": key, "obj": obj, "since": self.cfg.loc.now(),
                             "expires": time.time() + expires_min * 60 if expires_min else None,
                             **({"restore": prev} if obj is not None and expires_min and prev else {})}
            self.adjust = {}
            self._kick()
        self.tick(maintenance=False)

    def manual_one(self, dev: str, on: bool | None, effect_key: str | None = None, obj=None,
                   expires_min: int | None = None):
        """4.8: On, Off or a pattern for one controller; on=None puts it back
        on the schedule. It lasts until that controller's schedule changes
        (its rule starts or ends), as a choice for all of them does. A choice
        for all of them made earlier ends: that controller leaves it, and the
        others go back to the schedule, so the top of Home says what's on."""
        with self.lock:
            if dev not in [d["deviceId"] for d in self.devices]:
                raise ValueError("This app doesn't run that controller. Turn it on under Setup \u203a Lights & "
                                 "controller \u203a Controlled by this app.")
            if on and obj is None and effect_key not in self.cfg.effects:
                raise ValueError(f"Unknown pattern '{effect_key}'")
            self._end_music("a pattern was chosen")
            if self._target(commit=False).reason == "alert":
                a = self.active_alert()
                if a:
                    self.alert_dismissed[a["event"].lower()] = time.time()
                    self._save_dismissed()
                    self.note(f"Weather alert dismissed by a manual change: {a['event']}")
            if self.override:
                # Review #1 (4.10): a choice for all of them becomes each other
                # controller's own (an Off by hand stays off), rather than ending
                # for all; it ends for each when that one's schedule changes.
                o, now = self.override, self.cfg.loc.now()
                for other in [d["deviceId"] for d in self.devices]:
                    if other == dev or other in self.dev_override:
                        continue
                    ow = self.cfg.schedule.for_controller(other).active_window(now)
                    self.dev_override[other] = {"on": bool(o["on"]), "effect": o.get("effect") if o["on"] else None,
                                                "obj": o.get("obj") if o["on"] else None, "since": now,
                                                "wkey": ow.key if ow else "off", "expires": o.get("expires"),
                                                "n": next(self._dov_seq)}
                self.override, self.adjust = None, {}
            name = self._dev_name(dev)
            if on is None:
                if self.dev_override.pop(dev, None) is not None:
                    self.note(f"{name}: back on the schedule.")
            else:
                w = self.cfg.schedule.for_controller(dev).active_window(self.cfg.loc.now())
                self.dev_override[dev] = {"on": bool(on), "effect": effect_key if on and obj is None else None,
                                          "obj": obj if on else None,
                                          "since": self.cfg.loc.now(), "wkey": w.key if w else "off",
                                          # 4.10: a preview (the House tab's finder) ends by itself
                                          "expires": time.time() + expires_min * 60 if expires_min else None,
                                          # each choice its own key, so the finder moving is sent
                                          "n": next(self._dov_seq)}
                if on and obj is None:
                    self.last_on = effect_key
            self._kick()
        self.tick(maintenance=False)

    def flash_one(self, dev: str, obj, seconds: int):
        """4.11: an automation's flash on one controller. Like the finder's
        preview, it ends by itself; then that controller goes back to the
        choice it covered (its own, or one made for all of them), or to the
        schedule if there was none or the schedule has changed since."""
        with self.lock:
            prev = self.dev_override.get(dev)
            if prev is None and self.override:
                o, now = self.override, self.cfg.loc.now()
                w = self.cfg.schedule.for_controller(dev).active_window(now)
                prev = {"on": bool(o["on"]), "effect": o.get("effect") if o["on"] else None,
                        "obj": o.get("obj") if o["on"] else None, "since": now,
                        "wkey": w.key if w else "off", "expires": o.get("expires"), "auto": o.get("auto")}
            if prev and prev.get("obj") is not None and prev.get("expires"):
                # 4.16: a preview after a preview (the finder moving, calibration
                # frames) covers what the first one covered, not the first one
                prev = prev.get("restore")
            prev = dict(prev) if prev else None
        self.manual_one(dev, True, obj=obj, expires_min=seconds / 60)     # sends; not under the lock
        with self.lock:
            e = self.dev_override.get(dev)
            if e is not None and prev is not None and e.get("obj") is obj:
                e["restore"] = prev

    def end_preview(self, dev: str | None = None):
        """4.16: end a preview now (calibration done, the finder closed): back
        to the choice it covered, or to the schedule if there was none."""
        with self.lock:
            if dev:
                e = self.dev_override.get(dev)
                if e is None or e.get("obj") is None:
                    return
                r = e.get("restore")
                if r:
                    self.dev_override[dev] = {**r, "n": next(self._dov_seq)}
                else:
                    self.dev_override.pop(dev, None)
            else:
                o = self.override
                if o is None or o.get("obj") is None:
                    return
                self.override = o.get("restore")
            self._kick()
        self.note(f"Preview ended{' on ' + self._dev_name(dev) if dev else ''}; back to what showed before.")
        self.tick(maintenance=False)

    def mark_automation(self, dev: str | None):
        """4.11: the choice just made was an automation's, not one made by
        hand, so a later automation may replace it (Review #4)."""
        with self.lock:
            o = self.dev_override.get(dev) if dev else self.override
            if o is not None:
                o["auto"] = True

    def mood_set(self, effect_key: str, expires_min: int) -> str:
        """Mood follow's pattern (3.18.2). It shows like a pattern chosen by
        hand that ends by itself, but it ranks below everything the user or
        the house decided: it never dismisses a weather alert (the alert
        stays on top), never ends a music show, and never replaces a pattern
        chosen by hand (it waits until that one ends). Returns "set",
        "same" (the pattern already on; its end pushed back) or "manual"
        (a pattern chosen by hand is on; nothing changed)."""
        with self.lock:
            if effect_key not in self.cfg.effects:
                raise ValueError(f"Unknown pattern '{effect_key}'")
            o = self.override
            if o and not o.get("mood") and not (o.get("expires") and time.time() > o["expires"]):
                return "manual"
            if o and o.get("mood") and o.get("effect") == effect_key:
                o["expires"] = time.time() + expires_min * 60
                return "same"
            self.override = {"on": True, "effect": effect_key, "obj": None, "since": self.cfg.loc.now(),
                             "expires": time.time() + expires_min * 60, "mood": True}
            self.adjust = {}
            self._kick()
        self.tick(maintenance=False)
        return "set"

    def mood_end(self) -> bool:
        """Mood follow stopped: end its pattern, and only its pattern. A
        pattern chosen by hand since then stays (3.18.2)."""
        with self.lock:
            if not (self.override and self.override.get("mood")):
                return False
            self.override, self.adjust = None, {}
            self._kick()
        self.tick(maintenance=False)
        return True

    def touch_override(self, effect_key: str, expires_min: int) -> bool:
        """Push back when a pattern set for a while ends, without sending it
        again (mood follow keeps its pattern while the music's mood holds)."""
        with self.lock:
            o = self.override
            if not (o and o["on"] and o.get("effect") == effect_key and o.get("expires")):
                return False
            o["expires"] = time.time() + expires_min * 60
            return True

    def default_on_effect(self, dev: str | None = None) -> str:
        """The pattern the On button uses: tonight's scheduled one (the window
        now, or the next one within a week), else the last pattern turned on
        by hand, else Warm white, else the first pattern."""
        effects = self.cfg.effects
        if not effects:
            raise ValueError("There are no patterns yet. Add one on the Patterns tab.")
        now = self.cfg.loc.now()
        sch = self.cfg.schedule.for_controller(dev)     # 4.8: that controller's own, when asked for one
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
                self.note(f"{self.flash.get('label') or 'Security flash'} stopped.")
                self.flash, self.flash_held = None, []
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
            elif self.override or self.adjust or self.dev_override:
                self.note("Back on the schedule.")
            self.override = None
            self.adjust = {}
            self.dev_override = {}
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

    def other_show_on(self, by: str | None = None) -> str | None:
        """The name of a music show running now that wasn't started by `by` (a prefix)
        (a show from the button, a webhook or a show night), or None (4.1.4)."""
        with self.lock:
            now = self.cfg.loc.now()
            m = self.music
            if m and not (m.get("until") and ts(now) >= ts(m["until"])):
                return None if by is not None and str(m.get("by") or "").startswith(by) else "A music show"
            msched = self.cfg.music.get("schedule")
            w = msched.active_window(now) if msched is not None else None
            if w is not None and w.key != self.music_skipped:
                return f"Show night \u201c{w.rule.name}\u201d"
            return None

    def start_music(self, minutes: int | None = None, by: str | None = None):
        """Step aside so the controller's music mode can run: until stopped,
        or for `minutes`. 0 or None with until_stopped means no end time."""
        with self.lock:
            if self.flash:
                raise ValueError(f"{self.flash.get('label') or 'A security flash'} is running. Stop it first.")
            now = self.cfg.loc.now()
            until = None
            if minutes:
                minutes = max(5, min(6 * 60, int(minutes)))
                until = add_real(now, timedelta(minutes=minutes))
            self.music = {"since": now, "until": until, "by": by}   # by: "lan" for music from this computer (4.1)
            self.override, self.adjust = None, {}
            self._kick()
            self.note("Music show started " + (f"for {minutes} min." if until else "(until stopped)."))
        self.tick(maintenance=False)

    def stop_music(self):
        with self.lock:
            self._end_music("stopped")
            self._invalidate()                   # send the scheduled pattern in full
        self.tick(maintenance=False)

    def start_flash(self, minutes: int | None = None, seconds: int | None = None, effect=None,
                    label: str | None = None, kind: str = "security", only_if_on: bool = False) -> bool:
        """Flash a pattern for a while, then everything returns to normal.
        effect: an Effect (a webhook's pattern, color or zone; a score
        celebration), or None for the security flash pattern. only_if_on:
        skip it when the lights are off (score celebrations in daylight) or a
        music show runs. Returns whether it started."""
        if effect is None and not self.cfg.security["effect"]:
            raise ValueError("No security flash is set up. Choose a pattern for it on the Schedule screen.")
        if seconds is not None:
            secs = max(FLASH_MIN_S, min(FLASH_MAX_S, int(seconds)))
        else:
            secs = 60 * max(1, min(240, int(minutes or self.cfg.security["minutes"])))
        label = (label or ("Security flash" if effect is None else f"Flash: {effect.label}"))[:80]
        rank = FLASH_RANK.get(kind, 1)
        with self.lock:
            t = self._target(commit=False)
            cur = self.flash if t.reason == "flash" else None

            def skip(why):
                self.note(f"{label} skipped: {why}.")
                return False
            if t.hands_off:
                # Any pattern sent now knocks the controller out of music mode,
                # which this app can't switch back on (3.16.1). Only something
                # urgent ends the show; the rest wait it out.
                if rank < FLASH_RANK["security"]:
                    return skip("a music show is on")
                self._end_music(label.lower())
            elif only_if_on and not t.on:
                return skip("the lights are off")
            if t.reason == "alert" and rank < ALERT_RANK:
                return skip(f"the {t.source} alert is showing")
            if cur is not None and cur.get("rank", 3) > rank:
                return skip(f"{cur.get('label') or 'Security flash'} is on")
            until = add_real(self.cfg.loc.now(), timedelta(seconds=secs))
            extended = cur is not None and (cur.get("label") or "Security flash") == label
            held = [f for f in self.flash_held if (f.get("label") or "Security flash") != label]
            if cur is not None and not extended and ts(cur["until"]) > ts(until):
                held.append(cur)            # resumes when this shorter one ends
            self.flash_held = held[-MAX_HELD:]
            self.flash = {"until": until, "eff": effect, "label": label, "kind": kind, "rank": rank, "since": time.time()}
            self._kick()
            took = f"{secs // 60} min" if secs % 60 == 0 else f"{secs} s"
            self.note(f"{label} {'extended' if extended else 'started'} for {took}.")
        self.wake.set()
        self.tick(maintenance=False)
        return True

    def stop_flash(self):
        with self.lock:
            if self.flash:
                self.note(f"{self.flash.get('label') or 'Security flash'} stopped.")
            self.flash, self.flash_held = None, []
            self._kick()
        self.tick(maintenance=False)

    def dismiss_alert(self) -> bool:
        """Put the lights back for the weather alert showing now (it stays
        dismissed; a new alert shows again)."""
        with self.lock:
            a = self.active_alert()
            if not a:
                return False
            self.alert_dismissed[a["event"].lower()] = time.time()
            self._save_dismissed()
            self._kick()
            self.note(f"Weather alert dismissed: {a['event']}")
        self.tick(maintenance=False)
        return True

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
            wa, wb = cfg.weather_alerts, old.weather_alerts
            if (cfg.loc.lat, cfg.loc.lon, wa["enabled"], wa["groups"], cfg.weather.get("contact")) != \
                    (old.loc.lat, old.loc.lon, wb["enabled"], wb["groups"], old.weather.get("contact")):
                self.wx_alerts = self._make_alerts(cfg, self.wx_alerts)
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
            try:
                self._save_state()            # 4.15: for the next start (smart recovery)
            except Exception:
                log.exception("Saving the lights' state failed")
            # Wake when a flash ends (a 15-second celebration shouldn't last
            # a whole check interval), or when something new starts.
            wait = self.cfg.interval
            with self.lock:
                f = self.flash
                if f:
                    left = (f["until"] - self.cfg.loc.now()).total_seconds()
                    wait = max(0.5, min(wait, left + 0.3))
            end = time.monotonic() + wait
            while not (self.stop_event.is_set() or self.wake.is_set()):
                left = end - time.monotonic()
                if left <= 0:
                    break
                self.stop_event.wait(min(0.5, left))
            self.wake.clear()
        self.runtime.save()
        self._save_state()

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

    def _prune_dismissed(self, wa):
        """Forget a dismissed warning once the Weather Service no longer lists
        it, so the next one of its kind shows. Only after a good check."""
        if not self.alert_dismissed or not wa.fresh():
            return
        names = {a["event"].lower() for a in wa.active(self.cfg.loc.now())}
        with self.lock:
            gone = [k for k in self.alert_dismissed if k not in names]
            for k in gone:
                del self.alert_dismissed[k]
            if gone:
                self._save_dismissed()

    def _alert_status(self, now, fmt, t):
        if not self.wx_alerts:
            return None
        a = self.active_alert(now)
        st = self.wx_alerts.state()
        return {"event": a["event"] if a else None, "headline": a["headline"] if a else None,
                "until": (lambda e: fmt(e) + ("" if e.date() == now.date() else e.strftime(" %a %b %d").replace(" 0", " ")))(
                    a["ends"].astimezone(now.tzinfo)) if a and a["ends"] else None,
                "showing": t.reason == "alert", "error": st["error"], "checked": bool(st["checked"])}

    def _weather_loop(self):
        while not self.stop_event.is_set():
            w, wa = self.weather, self.wx_alerts
            if w:
                try:
                    w.refresh()
                except Exception:
                    log.exception("weather check failed")
            if wa:
                try:
                    wa.refresh()
                    self._prune_dismissed(wa)
                except Exception:
                    log.exception("weather alert check failed")
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
            wins = [{"on": fmt(p.start), "off": fmt(p.end), "rule": p.rule.name, "effect": p.effect_label(),
                     **({"controllers": names} if names else {})} for p, names in self._plans_all(d)]
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
            at = midnight + timedelta(minutes=m)
            aw = None
            if m < 1440:
                # 4.8: with rules for some controllers, the first controller that's on
                aw = sch.active_window(at) if not sch.per_controller or not self.devices else next(
                    (x for d in list(self.devices) if (x := sch.for_controller(d["deviceId"]).active_window(at))), None)
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
                       "until": fmt(t.until),
                       "curve": {"kelvin": t.curve[0], "level": t.curve[1]} if t.curve else None,
                       # 4.8: what each controller shows, when they differ
                       "parts": {dev: {**p, "until": fmt(p["until"])} for dev, p in t.parts.items()} if t.parts else None},
            "levels": {"brightness": levels.get("brightness"), "speed": levels.get("speed"), "adjusted": adjusted},
            "rotation": rot, "weather": wx,
            "flash": {"available": bool(self.cfg.security["effect"]), "minutes": self.cfg.security["minutes"],
                      "active": t.reason == "flash", "until": fmt(t.until) if t.reason == "flash" else None,
                      "label": t.source if t.reason == "flash" else None},
            "alert": self._alert_status(now, fmt, t),
            "holiday": self.holiday_today(now),
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
