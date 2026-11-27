# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Phone alerts through ntfy (https://ntfy.sh, free, no account) (3.15).

Once a minute this looks at a few conditions and sends a push message when a
problem has lasted a while, then one "back to normal" when it clears:

  failed      the lights can't be reached to turn on or off (10 minutes)
  offline     a controller reports offline (10 minutes; 15 before 4.27)
  unreadable  Trimlight can't read its copy of a controller, code 12006 (15 min)
  update      a new EaveLuxOS version is out (once per version)
  down        4.27: EaveLuxOS itself was off for 5 minutes or more without
              being quit (a power cut, the computer shut down or crashed),
              sent once when it runs again. While it's off it can't send
              anything, so this is the only way to hear about it.

4.27: the last 20 messages (sent or not, and why) are kept, so "I never get
alerts" can be told apart from "nothing happened" and "my phone doesn't show
them".

At most one message per problem every 6 hours. The settings live in
data/alerts.json, not in the settings document, because the topic name works
like a password (anyone who knows it can read the messages) and settings get
exported and shared. Messages say what happened, never where you live.
"""
import ipaddress
import json
import logging
import os
import re
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .trust import client_context

log = logging.getLogger("eaveluxos.alerts")
DEFAULT_SERVER = "https://ntfy.sh"
TOPIC_RE = re.compile(r"[A-Za-z0-9_-]{12,64}")
REPEAT = 6 * 3600
EVERY = 60
KINDS = {
    "failed": (600, "Lights didn't change", "EaveLuxOS can't reach the lights to turn them on or off. {detail}",
               "The lights are answering again."),
    "offline": (600, "Controller offline", "{detail} has been offline for 10 minutes, so the schedule can't run it.",
                "{detail} is back online."),
    "unreadable": (900, "Controller can't be read", "Trimlight's cloud can't read its copy of {detail}. The lights "
                   "keep running, but nothing can be changed from EaveLuxOS. See the manual, Troubleshooting.",
                   "Trimlight can read {detail} again."),
    "update": (0, "New version", "EaveLuxOS {detail} is available. Open the app to see what's new.", None),
    "down": (0, "the app was off", "{detail}", None),
}
DOWN_AFTER = 300        # 4.27: off this long (seconds) without a Quit counts
HISTORY = 20


class AlertError(Exception):
    pass


def check_server(url: str) -> str:
    """https://host[:port] (any host), or http:// only for this computer or a
    private address (a home ntfy server). No path, query or login."""
    u = urllib.parse.urlsplit(str(url or "").strip().rstrip("/"))
    if u.path not in ("",) or u.query or u.fragment or u.username or u.password or not u.hostname:
        raise AlertError("The ntfy server must look like https://ntfy.sh (no path).")
    if u.scheme == "https":
        return f"https://{u.netloc}"
    if u.scheme == "http":
        host = u.hostname
        try:
            ip = ipaddress.ip_address(host)
            ok = ip.is_private or ip.is_loopback
        except ValueError:
            ok = host == "localhost"
        if ok:
            return f"http://{u.netloc}"
    raise AlertError("Use https:// (plain http:// only for a server on your home network).")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _post(url: str, title: str, message: str, tags: str, priority: str):
    opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=client_context()), _NoRedirect)
    req = urllib.request.Request(url, data=message.encode("utf-8"), method="POST",
                                 headers={"Title": title.encode("utf-8").decode("latin-1", "replace"),
                                          "Tags": tags, "Priority": priority, "User-Agent": "EaveLuxOS"})
    try:
        with opener.open(req, timeout=10) as r:
            r.read(2000)
    except urllib.error.HTTPError as e:
        e.close()
        raise AlertError(f"The ntfy server answered {e.code}.") from None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise AlertError(f"Couldn't reach the ntfy server: {getattr(e, 'reason', e)}") from None


class Alerts:
    def __init__(self, data_dir: Path, probe=None, send=None, now=time.time, clock=None, note=None):
        self.path = Path(data_dir) / "alerts.json"
        self.alive_path = Path(data_dir) / "alive.json"
        self.probe = probe or (lambda: {})
        self.send_raw = send or _post
        self.now = now
        self.clock = clock or (lambda ts: time.strftime("%I:%M %p", time.localtime(ts)).lstrip("0"))
        self.note = note or (lambda text: log.warning("%s", text))
        self.lock = threading.Lock()
        self.cfg = self._load()
        self._quit = False
        self._alive_lock = threading.Lock()
        self.last_alive = self._read_alive()     # before this run writes its own
        self.started = None
        self.state = {}                 # kind -> {"since", "sent", "detail"}
        self.thread = None
        self.stop = threading.Event()

    # ------------------------------------------------------------- settings
    def _load(self) -> dict:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raw = {}
        raw = raw if isinstance(raw, dict) else {}
        try:
            server = check_server(raw.get("server") or DEFAULT_SERVER)
        except AlertError:
            server = DEFAULT_SERVER
        topic = raw.get("topic") if isinstance(raw.get("topic"), str) and TOPIC_RE.fullmatch(raw.get("topic")) else None
        ev = raw.get("events") if isinstance(raw.get("events"), dict) else {}
        hist = [h for h in (raw.get("history") if isinstance(raw.get("history"), list) else [])
                if isinstance(h, dict) and isinstance(h.get("at"), (int, float)) and isinstance(h.get("title"), str)]
        return {"enabled": raw.get("enabled") is True and bool(topic), "server": server,
                "topic": topic or "eaveluxos-" + secrets.token_hex(8),
                "events": {k: ev.get(k) is not False for k in KINDS}, "sent_update": str(raw.get("sent_update") or ""),
                "history": [{"at": float(h["at"]), "title": h["title"][:80], "ok": h.get("ok") is True,
                             "error": str(h.get("error") or "")[:200]} for h in hist][-HISTORY:]}

    # ------------------------------------------------------------- was it off?
    def _read_alive(self):
        try:
            raw = json.loads(self.alive_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(raw, dict) or not isinstance(raw.get("at"), (int, float)) or isinstance(raw.get("at"), bool):
            return None
        return {"at": float(raw["at"]), "quit": raw.get("quit") is True}

    def _write_alive(self, quit=False):
        # Review #1: under one lock, so a minute's "still running" can't land
        # after Quit's "quit" and make the next start look like a power cut
        with self._alive_lock:
            if self._quit and not quit:
                return                        # Quit pressed: keep saying so until the program exits
            try:
                tmp = self.alive_path.with_suffix(".tmp")
                tmp.write_text(json.dumps({"at": self.now(), "quit": quit}), encoding="utf-8")
                os.replace(tmp, self.alive_path)
            except OSError as e:
                log.debug("couldn't note that the app is running: %s", e)

    def quitting(self):
        """Quit on purpose (the Quit button): the next start isn't reported."""
        with self._alive_lock:
            self._quit = True
        self._write_alive(quit=True)

    def _was_down(self):
        """(off since, back at) when the last run ended without a Quit at
        least DOWN_AFTER before this one started, else None."""
        prev, start = self.last_alive, self.started
        if not prev or start is None or prev["quit"] or start - prev["at"] < DOWN_AFTER:
            return None
        return prev["at"], start

    def down_text(self, since, back):
        mins = round((back - since) / 60)
        took = f"{mins} minutes" if mins < 120 else f"{mins / 60:.1f} hours"
        return (f"EaveLuxOS was off from about {self.clock(since)} to {self.clock(back)} ({took}) without being quit: "
                "the computer lost power, was shut down or restarted. It's running again and has set the lights. "
                "While it was off, nothing could change them.")

    def _save(self):
        try:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.cfg, indent=2), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError as e:
            log.warning("Couldn't save the alert settings: %s", e)

    def settings(self) -> dict:
        with self.lock:
            c = dict(self.cfg)
        return {"enabled": c["enabled"], "server": c["server"], "topic": c["topic"], "events": dict(c["events"]),
                "subscribe": f"{c['server']}/{c['topic']}", "history": list(reversed(c["history"]))}

    def update(self, body: dict) -> dict:
        if not isinstance(body, dict):
            raise AlertError("Send the alert settings as an object.")
        with self.lock:
            c = dict(self.cfg)
            if "server" in body:
                c["server"] = check_server(body["server"] or DEFAULT_SERVER)
            if "topic" in body:
                t = str(body["topic"] or "").strip()
                if not TOPIC_RE.fullmatch(t):
                    raise AlertError("The topic must be 12-64 letters, numbers, - or _. Make it hard to guess: "
                                     "anyone who knows it can read your alerts.")
                c["topic"] = t
            if isinstance(body.get("events"), dict):
                c["events"] = {k: (body["events"].get(k, c["events"][k]) is not False) for k in KINDS}
            if "enabled" in body:
                if not isinstance(body["enabled"], bool):
                    raise AlertError("Say whether alerts are on (true or false).")
                c["enabled"] = body["enabled"]
            self.cfg = c
            self._save()
        return self.settings()

    # ------------------------------------------------------------- sending
    def _url(self):
        return f"{self.cfg['server']}/{self.cfg['topic']}"

    def send(self, title: str, message: str, tags="bulb", priority="default"):
        self.send_raw(self._url(), "EaveLuxOS: " + title, message, tags, priority)

    def test(self):
        try:
            self.send("test", "Alerts from EaveLuxOS reach this phone.", tags="white_check_mark")
        except AlertError as e:
            self._record("test", False, str(e))
            raise
        self._record("test", True)

    def _record(self, title, ok, error=""):
        with self.lock:
            h = self.cfg["history"] + [{"at": self.now(), "title": title, "ok": ok, "error": error[:200]}]
            self.cfg = {**self.cfg, "history": h[-HISTORY:]}
            self._save()

    def step(self):
        """One check: compare the conditions with what was already sent."""
        self._write_alive()
        with self.lock:
            on, events = self.cfg["enabled"], dict(self.cfg["events"])
        down = self._was_down()
        if down:
            self.last_alive = None           # reported once (or not at all, when off)
            text = self.down_text(*down)
            self.note(text)
            if on and events.get("down"):
                self._try(KINDS["down"][1], text, "electric_plug", "high")
        if not on:
            self.state.clear()
            return
        try:
            cond = self.probe() or {}
        except Exception:                   # a probe can't stop alerts
            log.exception("alert check failed")
            return
        t = self.now()
        for kind, (wait, title, text, back) in KINDS.items():
            active, detail = (cond.get(kind) or (False, ""))[:2]
            st = self.state.get(kind)
            if kind == "down":
                continue
            if kind == "update":
                if active and events["update"] and detail and detail != self.cfg.get("sent_update"):
                    if self._try(title, text.format(detail=detail), "tada"):
                        with self.lock:
                            self.cfg["sent_update"] = detail
                            self._save()
                continue
            if active:
                if not st:
                    st = self.state[kind] = {"since": t, "sent": None, "detail": detail}
                st["detail"] = detail or st["detail"]
                if (events.get(kind) and t - st["since"] >= wait
                        and (st["sent"] is None or t - st["sent"] >= REPEAT)):
                    if self._try(title, text.format(detail=st["detail"] or "the controller"), "warning", "high"):
                        st["sent"] = t
            elif st:
                if st["sent"] is not None and back and events.get(kind):
                    self._try("back to normal", back.format(detail=st["detail"] or "The controller"), "white_check_mark")
                self.state.pop(kind, None)

    def _try(self, title, message, tags, priority="default") -> bool:
        try:
            self.send(title, message, tags, priority)
            log.info("Alert sent: %s", title)
            self._record(title, True)
            return True
        except AlertError as e:
            log.warning("Couldn't send an alert: %s", e)
            self._record(title, False, str(e))
            return False

    def _loop(self):
        while not self.stop.wait(EVERY):
            self.step()

    def start(self):
        if self.started is None:
            self.started = self.now()
            self._write_alive()            # the earlier run's last sign of life was read in __init__
        if self.thread is None:
            self.thread = threading.Thread(target=self._loop, daemon=True, name="alerts")
            self.thread.start()
