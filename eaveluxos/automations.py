# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Automations (4.11): WHEN something happens, IF conditions hold, THEN do
something to the lights.

  When  a team scores; a game starts or ends (win, loss or either); a severe
        weather alert starts; a webhook event is called by its name; a time
        of day or sunrise/sunset with an offset; the schedule turns the lights
        on or off.
  If    (all of them) it's dark (sunset to sunrise); between two times;
        before or after a time; on some days of the week; between two dates;
        the lights are on or off; a rule or a pattern is showing; the team is
        home or away, winning or losing (game events only).
  Then  (in order) flash a pattern, a color or a zone for some seconds and
        go back to what was showing; show a pattern for some minutes or until
        the schedule changes; turn off for some minutes; play a team's
        celebration sound. Each on all controllers or one.

Every action goes through the controller's own flash and manual paths, so
the same safety rules apply as for buttons in the app (no cloud pattern
writes, the same limits). When several automations fire together, the higher
priority runs first, and a lower one that wants the same controllers is
skipped; while one is flashing, a lower-priority one doesn't cut in. Each has
a cooldown, and by default none interrupts a choice made by hand."""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from datetime import date, datetime, timedelta

from .schedule import ConfigError, TimeExpr, ts

log = logging.getLogger("eaveluxos.automations")

MAX_AUTOS, MAX_CONDS, MAX_ACTS = 50, 8, 4
EVENTS = ("score", "game_start", "game_end", "weather", "webhook", "time", "lights")
CONDS = ("dark", "between", "before", "after", "days", "dates", "lights", "rule", "pattern",
         "home", "away", "winning", "losing")
ACTIONS = ("flash", "show", "off", "sound")
GAME_EVENTS = ("score", "game_start", "game_end")
TIME_WINDOW = 120            # seconds after a time event that it may still fire (the engine looks every 15)
DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def _time(v, where):
    if not isinstance(v, str) or not 1 <= len(v) <= 30:
        raise ConfigError(f"{where}: choose a time.")
    return TimeExpr.parse(v)


def _int(v, lo, hi, where, what):
    if isinstance(v, bool) or not isinstance(v, int) or not lo <= v <= hi:
        raise ConfigError(f"{where}: {what} is {lo} to {hi}.")
    return v


def _mmdd(v, where):
    try:
        m, d = (int(x) for x in str(v).split("-"))
        date(2024, m, d)
    except (ValueError, TypeError):
        raise ConfigError(f"{where}: dates are month-day, for example 12-01.") from None
    return (m, d)


def parse(raw, effects: dict, teams: set, devices_ok=lambda d: True) -> list[dict]:
    """Check and tidy the "automations" setting. teams: the Game-day team keys
    (league-team) that game events may name."""
    if raw is None:
        return []
    if not isinstance(raw, list) or len(raw) > MAX_AUTOS:
        raise ConfigError(f"Up to {MAX_AUTOS} automations.")
    out, ids = [], set()
    for n, a in enumerate(raw, 1):
        if not isinstance(a, dict):
            raise ConfigError(f"Automation {n} isn't readable.")
        name = str(a.get("name") or "").strip()
        where = f"Automation “{name or n}”"
        if not 1 <= len(name) <= 60:
            raise ConfigError(f"Automation {n}: give it a name (up to 60 characters).")
        aid = str(a.get("id") or "")
        if not 1 <= len(aid) <= 40 or aid in ids:
            raise ConfigError(f"{where}: its id is missing or used twice.")
        ids.add(aid)
        w = a.get("when")
        if not isinstance(w, dict) or w.get("type") not in EVENTS:
            raise ConfigError(f"{where}: choose what starts it (When).")
        when = {"type": w["type"]}
        if w["type"] in GAME_EVENTS:
            team = w.get("team", "any")
            if team != "any" and team not in teams:
                raise ConfigError(f"{where}: the team isn't under Schedule › Game-day lights any more.")
            when["team"] = team
            if w["type"] == "game_end":
                if w.get("result", "any") not in ("any", "win", "loss"):
                    raise ConfigError(f"{where}: a game's end is a win, a loss or either.")
                when["result"] = w.get("result", "any")
        elif w["type"] == "weather":
            when["event"] = str(w.get("event") or "").strip()[:60]          # empty: any warning
        elif w["type"] == "webhook":
            nm = str(w.get("name") or "").strip().lower()
            if not 1 <= len(nm) <= 40 or not all(ch.isalnum() or ch in "-_ " for ch in nm):
                raise ConfigError(f"{where}: a webhook event name is 1 to 40 letters, numbers, spaces, - or _.")
            when["name"] = nm
        elif w["type"] == "time":
            when["at"] = w.get("at")
            when["_at"] = _time(w.get("at"), where)
        elif w["type"] == "lights":
            when["on"] = bool(w.get("on", True))
        conds = a.get("if") or []
        if not isinstance(conds, list) or len(conds) > MAX_CONDS:
            raise ConfigError(f"{where}: up to {MAX_CONDS} conditions.")
        cs = []
        for c in conds:
            if not isinstance(c, dict) or c.get("type") not in CONDS:
                raise ConfigError(f"{where}: a condition isn't readable.")
            t, cc = c["type"], {"type": c["type"]}
            if t in ("between", "dark"):
                cc["from"], cc["to"] = c.get("from", "sunset" if t == "dark" else None), c.get("to", "sunrise" if t == "dark" else None)
                cc["_from"], cc["_to"] = _time(cc["from"], where), _time(cc["to"], where)
            elif t in ("before", "after"):
                cc["at"] = c.get("at")
                cc["_at"] = _time(c.get("at"), where)
            elif t == "days":
                ds = c.get("days")
                if not isinstance(ds, list) or not ds or not all(isinstance(x, int) and not isinstance(x, bool) and 0 <= x <= 6 for x in ds):
                    raise ConfigError(f"{where}: choose at least one day.")
                cc["days"] = sorted(set(ds))
            elif t == "dates":
                cc["from"], cc["to"] = c.get("from"), c.get("to")
                cc["_from"], cc["_to"] = _mmdd(c.get("from"), where), _mmdd(c.get("to"), where)
            elif t == "lights":
                cc["on"] = bool(c.get("on", True))
            elif t == "rule":
                cc["name"] = str(c.get("name") or "").strip()[:80]
                if not cc["name"]:
                    raise ConfigError(f"{where}: choose the rule.")
            elif t == "pattern":
                if c.get("effect") not in effects:
                    raise ConfigError(f"{where}: the pattern in a condition is gone.")
                cc["effect"] = c["effect"]
            elif t in ("home", "away", "winning", "losing") and when["type"] not in GAME_EVENTS:
                raise ConfigError(f"{where}: home, away, winning and losing are only for game events.")
            cs.append(cc)
        acts = a.get("then")
        if not isinstance(acts, list) or not 1 <= len(acts) <= MAX_ACTS:
            raise ConfigError(f"{where}: give it 1 to {MAX_ACTS} things to do (Then).")
        av = []
        for x in acts:
            if not isinstance(x, dict) or x.get("type") not in ACTIONS:
                raise ConfigError(f"{where}: an action isn't readable.")
            t, xx = x["type"], {"type": x["type"]}
            dev = x.get("device")
            if dev is not None:
                if not isinstance(dev, str) or not 1 <= len(dev) <= 80 or not devices_ok(dev):
                    raise ConfigError(f"{where}: an action names a controller this app doesn't know.")
                xx["device"] = dev
            if t == "flash":
                if x.get("effect"):
                    if x["effect"] not in effects:
                        raise ConfigError(f"{where}: the pattern to flash is gone.")
                    xx["effect"] = x["effect"]
                elif x.get("color"):
                    col = str(x["color"])
                    if len(col) != 7 or col[0] != "#" or not all(ch in "0123456789abcdefABCDEF" for ch in col[1:]):
                        raise ConfigError(f"{where}: a color is like #FF6600.")
                    xx["color"] = col.upper()
                else:
                    raise ConfigError(f"{where}: choose a pattern or a color to flash.")
                if x.get("zone"):
                    xx["zone"] = str(x["zone"])[:60]
                xx["seconds"] = _int(x.get("seconds", 20), 5, 600, where, "a flash")
            elif t == "show":
                if x.get("effect") not in effects:
                    raise ConfigError(f"{where}: choose the pattern to show.")
                xx["effect"] = x["effect"]
                if x.get("minutes") is not None:
                    xx["minutes"] = _int(x["minutes"], 1, 720, where, "showing it")
            elif t == "off":
                xx["minutes"] = _int(x.get("minutes", 30), 1, 720, where, "turning off")
            elif t == "sound":
                team = x.get("team")
                if team not in teams:
                    raise ConfigError(f"{where}: choose the team whose sound plays.")
                xx["team"] = team
            av.append(xx)
        out.append({"id": aid, "name": name, "enabled": a.get("enabled", True) is not False,
                    "priority": _int(a.get("priority", 100), 0, 1000, where, "priority"),
                    "cooldown": _int(a.get("cooldown", 30), 0, 86400, where, "the cooldown (seconds)"),
                    "beats_manual": bool(a.get("beats_manual", False)), "when": when, "if": cs, "then": av})
    return out


def watch_teams(gd, autos: list[dict]) -> dict:
    """Teams the scoreboard must watch for automations even when their score
    celebrations are off: key -> the team settings, flagged automation_only."""
    from .gameday import GameDayError, check_team, team_key
    from .schedule import CELEBRATE_POINTS
    wanted = {a["when"].get("team") for a in autos if a["enabled"] and a["when"]["type"] in GAME_EVENTS}
    if not wanted or not isinstance(gd, dict):
        return {}
    out = {}
    for t in gd.get("teams") or []:
        if not isinstance(t, dict):
            continue
        try:
            c = check_team(t)
        except GameDayError:
            continue
        key = team_key(c["league"], c["team"])
        if "any" in wanted or key in wanted:
            mp = t.get("min_points", CELEBRATE_POINTS[c["league"]])
            out[key] = {**c, "effect": None, "seconds": 0, "min_points": mp if isinstance(mp, int) and not isinstance(mp, bool) else 1,
                        "only_when_on": False, "sound": None, "automation_only": True}
    return out


def describe(a: dict, names=lambda kind, v: v) -> str:
    """One line, for the list and the log: When … if … then …"""
    w = a["when"]
    team = lambda k: "a team" if k == "any" else names("team", k)
    when = {"score": lambda: f"{team(w['team'])} scores",
            "game_start": lambda: f"{team(w['team'])}'s game starts",
            "game_end": lambda: f"{team(w['team'])}'s game ends" + ({"win": " in a win", "loss": " in a loss"}.get(w.get("result"), "")),
            "weather": lambda: f"a {w['event']} starts" if w.get("event") else "a weather warning starts",
            "webhook": lambda: f"the webhook event “{w['name']}” comes",
            "time": lambda: f"it's {w['at']}",
            "lights": lambda: "the schedule turns the lights " + ("on" if w["on"] else "off")}[w["type"]]()
    cs = []
    for c in a["if"]:
        t = c["type"]
        cs.append({"dark": lambda: "it's dark" if (c["from"], c["to"]) == ("sunset", "sunrise") else f"between {c['from']} and {c['to']}",
                   "between": lambda: f"between {c['from']} and {c['to']}",
                   "before": lambda: f"before {c['at']}", "after": lambda: f"after {c['at']}",
                   "days": lambda: "on " + ", ".join(DAYS[d] for d in c["days"]),
                   "dates": lambda: f"from {c['from']} to {c['to']}",
                   "lights": lambda: "the lights are " + ("on" if c["on"] else "off"),
                   "rule": lambda: f"{c['name']} is running",
                   "pattern": lambda: f"{names('effect', c['effect'])} is showing",
                   "home": lambda: "they're at home", "away": lambda: "they're away",
                   "winning": lambda: "they're winning", "losing": lambda: "they're losing"}[t]())
    acts = []
    for x in a["then"]:
        on = f" on {names('device', x['device'])}" if x.get("device") else ""
        what = names("effect", x["effect"]) if x.get("effect") else x.get("color", "")
        acts.append({"flash": lambda: f"flash {what}{' in ' + x['zone'] if x.get('zone') else ''} for {x['seconds']} s{on}",
                     "show": lambda: f"show {what}{on} " + (f"for {x['minutes']} min" if x.get("minutes") else "until the schedule changes"),
                     "off": lambda: f"turn off{on} for {x['minutes']} min",
                     "sound": lambda: f"play {names('team', x['team'])}'s sound"}[x["type"]]())
    return f"When {when}" + (f", if {' and '.join(cs)}" if cs else "") + f", then {', then '.join(acts)}."


def _by_hand(o) -> bool:
    """A choice made by hand: not a preview that ends by itself, and not an
    automation's own (Review #4). A flash on one controller keeps the choice
    it covers, so that counts too."""
    if not o:
        return False
    if not o.get("expires") and not o.get("auto"):
        return True
    return _by_hand(o.get("restore"))


class Engine:
    """Runs automations. app gives: ctrl (the scheduler), cfg, run_flash,
    run_show, run_off, run_sound (server.py), all of which may raise."""

    def __init__(self, app, now=time.time):
        self.app = app
        self.now = now
        self.lock = threading.RLock()
        self.last_run: dict = {}           # id -> when it last ran (epoch)
        self.time_fired: dict = {}         # id -> the day its time event last fired
        self.busy = None                   # {"until", "priority", "devices", "name"} while a flash runs
        self.prev_lights = None            # the schedule's on/off at the last look
        self.prev_alerts = None            # weather warnings showing at the last look
        self.history: deque = deque(maxlen=40)
        self.thread = None
        self.stop = threading.Event()

    # --- what's true now ---------------------------------------------------
    def _ctx(self, ev: dict | None):
        c = self.app.ctrl
        cfg = c.cfg
        now = cfg.loc.now()
        t = c._target(commit=False)
        return {"now": now, "loc": cfg.loc, "target": t, "ev": ev or {}}

    @staticmethod
    def _between(now, a: TimeExpr, b: TimeExpr, loc) -> bool:
        """now within a..b, which may run past midnight (sunset to sunrise)."""
        d = now.date()
        for start_day in (d - timedelta(days=1), d):
            s = a.resolve(start_day, loc)
            if s is None:
                continue
            e = b.resolve(start_day, loc)
            if e is None:
                continue
            if ts(e) <= ts(s):
                e = b.resolve(start_day + timedelta(days=1), loc)
                if e is None:
                    continue
            if ts(s) <= ts(now) < ts(e):
                return True
        return False

    def _cond(self, c: dict, x: dict) -> tuple[bool, str]:
        now, loc, t, ev = x["now"], x["loc"], x["target"], x["ev"]
        k = c["type"]
        if k in ("dark", "between"):
            return self._between(now, c["_from"], c["_to"], loc), ""
        if k in ("before", "after"):
            at = c["_at"].resolve(now.date(), loc)
            if at is None:
                return False, "the sun doesn't rise or set here today"
            return (ts(now) < ts(at)) if k == "before" else (ts(now) >= ts(at)), ""
        if k == "days":
            return now.weekday() in c["days"], ""
        if k == "dates":
            md, a, b = (now.month, now.day), c["_from"], c["_to"]
            return (a <= md <= b) if a <= b else (md >= a or md <= b), ""
        if k == "lights":
            return bool(t.on) == c["on"], ""
        if k == "rule":
            names = {t.source} | {p.get("rule") for p in (t.parts or {}).values()}
            return c["name"] in names, ""
        if k == "pattern":
            keys = {getattr(t.effect, "key", None)} | {getattr(p, "key", None) for p in ((t.effect.parts or {}).values() if t.effect is not None and t.effect.kind == "split" else ())}
            return c["effect"] in keys, ""
        g, abbr = ev.get("game"), ev.get("abbr")
        if not g or not abbr:
            return False, "only for game events"
        if k in ("home", "away"):
            home = g.get("home")
            if home is None:
                return False, "the scoreboard didn't say who's at home"
            return (home == abbr) == (k == "home"), ""
        us = g["teams"].get(abbr)
        them = [s for a, s in g["teams"].items() if a != abbr]
        if us is None or not them:
            return False, "no score yet"
        return (us > them[0]) if k == "winning" else (us < them[0]), ""

    def check(self, a: dict, ev: dict | None = None) -> list[tuple[str, bool]]:
        """Each condition of a, and whether it holds now (the editor's Check it now)."""
        x = self._ctx(ev)
        out = []
        for c in a["if"]:
            ok, why = self._cond(c, x)
            out.append((describe({**a, "if": [c]}).split(", if ", 1)[-1].split(", then ", 1)[0] + (f" ({why})" if why else ""), ok))
        return out

    # --- events --------------------------------------------------------------
    def _matches(self, a, ev) -> bool:
        w = a["when"]
        if not a["enabled"] or w["type"] != ev["type"]:
            return False
        if w["type"] in GAME_EVENTS:
            if w["team"] not in ("any", ev.get("team")):
                return False
            if w["type"] == "game_end" and w.get("result", "any") != "any" and w["result"] != ev.get("result"):
                return False
        if w["type"] == "weather" and w.get("event") and w["event"].lower() not in str(ev.get("event", "")).lower():
            return False
        if w["type"] == "webhook" and w["name"] != ev.get("name"):
            return False
        if w["type"] == "lights" and w["on"] != ev.get("on"):
            return False
        if w["type"] == "time" and w is not ev.get("when"):
            return False
        return True

    def _devices(self, a) -> set:
        devs = set()
        for x in a["then"]:
            if x["type"] != "sound":
                devs.add(x.get("device") or "*")
        return devs

    def event(self, ev: dict) -> list[str]:
        """Something happened; run the automations it starts. Returns what
        was done or skipped, one line each (also in Activity)."""
        c = self.app.ctrl
        if c is None:
            return []
        autos = [a for a in (c.cfg.automations or []) if self._matches(a, ev)]
        if not autos:
            return []
        autos.sort(key=lambda a: -a["priority"])
        done, used = [], set()
        with self.lock:
            x = self._ctx(ev)
            for a in autos:
                why = self._why_not(a, x, used)
                if why:
                    done.append(self._note(a, f"skipped: {why}"))
                    continue
                devs = self._devices(a)
                used |= devs
                done.append(self._run(a, ev, devs))
        return done

    def _why_not(self, a, x, used) -> str | None:
        for cnd in a["if"]:
            ok, why = self._cond(cnd, x)
            if not ok:
                return why or "not " + describe({**a, "if": [cnd]}).split(", if ", 1)[-1].split(", then ", 1)[0]
        if a["cooldown"] and self.now() - self.last_run.get(a["id"], -1e12) < a["cooldown"]:
            return "it ran less than its cooldown ago"
        devs = self._devices(a)
        t = x["target"]
        if devs and t.reason == "alert":
            # Review #1 (4.11): a weather warning stays on top. Showing a
            # pattern goes through the same path as a choice made by hand,
            # which would have dismissed the warning.
            return f"the {t.source or 'weather'} alert is showing"
        if devs and t.hands_off and not a["beats_manual"]:
            return "a music show is on"
        if used and ("*" in used or "*" in devs or used & devs):
            return "a higher-priority automation already took these lights"
        b = self.busy
        if b and self.now() < b["until"] and b["priority"] > a["priority"] and (
                "*" in b["devices"] or "*" in devs or b["devices"] & devs):
            return f"the higher-priority “{b['name']}” is still running"
        if not a["beats_manual"] and devs:
            c = self.app.ctrl
            manual = _by_hand(c.override)
            mine = {d for d, o in c.dev_override.items() if _by_hand(o)}
            if manual or ("*" in devs and mine) or (devs & mine):
                return "the lights were set by hand (turn on Beats a manual choice to allow it)"
        return None

    def _run(self, a, ev, devs, test=False) -> str:
        if not test:                        # Review #5: Try it now doesn't start the cooldown
            self.last_run[a["id"]] = self.now()
        flash = max((x["seconds"] for x in a["then"] if x["type"] == "flash"), default=0)
        if flash:
            self.busy = {"until": self.now() + flash, "priority": a["priority"], "devices": devs, "name": a["name"]}
        problems = []
        for x in a["then"]:
            try:
                getattr(self.app, "auto_" + x["type"])(x, a, ev)
            except Exception as e:          # one action failing doesn't stop the others
                log.warning("Automation %s: %s failed: %s", a["name"], x["type"], e)
                problems.append(f"{x['type']}: {e}")
        return self._note(a, ("tried" if test else "ran") + (f" ({'; '.join(problems)})" if problems else ""))

    def _note(self, a, what) -> str:
        line = f"Automation “{a['name']}” {what}."
        self.history.appendleft({"at": self.now(), "id": a["id"], "text": line})
        try:                                 # 4.17: in the audit log too
            self.app.store.audit(f"automation: {a['name']}", "Automation " + what.split(" (")[0], what, role="automation",
                                 ok="(" not in what)
        except Exception:
            pass
        c = self.app.ctrl
        if c is not None:
            c.note(line)
        return line

    def try_now(self, a: dict) -> str:
        """The editor's Try it now: the actions, whatever the conditions."""
        with self.lock:
            return self._run(a, {"type": a["when"]["type"], "test": True}, self._devices(a), test=True)

    # --- what the engine looks for by itself -------------------------------------
    def tick(self):
        c = self.app.ctrl
        if c is None:
            return
        cfg = c.cfg
        now = cfg.loc.now()
        for a in cfg.automations or []:
            w = a["when"]
            if not a["enabled"] or w["type"] != "time" or self.time_fired.get(a["id"]) == now.date():
                continue
            at = w["_at"].resolve(now.date(), cfg.loc)
            if at is not None and 0 <= ts(now) - ts(at) < TIME_WINDOW:
                self.time_fired[a["id"]] = now.date()
                self.event({"type": "time", "when": w})
        t = c._target(commit=False)
        if t.reason in ("schedule", "weather"):        # the schedule's own on and off, not a flash or a choice by hand
            on = bool(t.on)
            if self.prev_lights is not None and on != self.prev_lights:
                self.event({"type": "lights", "on": on})
            self.prev_lights = on
        try:
            alerts = {a["event"] for a in c.wx_alerts.active()} if getattr(c, "wx_alerts", None) else set()
        except Exception:
            alerts = set()
        if self.prev_alerts is not None:
            for e in sorted(alerts - self.prev_alerts):
                self.event({"type": "weather", "event": e})
        self.prev_alerts = alerts

    def _loop(self):
        while not self.stop.wait(15):
            try:
                self.tick()
            except Exception:
                log.exception("Automation check failed")

    def start(self):
        if self.thread is None:
            self.thread = threading.Thread(target=self._loop, daemon=True, name="automations")
            self.thread.start()
