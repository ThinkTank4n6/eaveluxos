# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Phone alerts through ntfy (https://ntfy.sh, free, no account) (3.15).

Once a minute this looks at a few conditions and sends a push message when a
problem has lasted a while, then one "back to normal" when it clears:

  failed      the lights can't be reached to turn on or off (10 minutes)
  offline     a controller reports offline (15 minutes)
  unreadable  Trimlight can't read its copy of a controller, code 12006 (15 min)
  update      a new EaveLuxOS version is out (once per version)

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
    "offline": (900, "Controller offline", "{detail} has been offline for 15 minutes, so the schedule can't run it.",
                "{detail} is back online."),
    "unreadable": (900, "Controller can't be read", "Trimlight's cloud can't read its copy of {detail}. The lights "
                   "keep running, but nothing can be changed from EaveLuxOS. See the manual, Troubleshooting.",
                   "Trimlight can read {detail} again."),
    "update": (0, "New version", "EaveLuxOS {detail} is available. Open the app to see what's new.", None),
}


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
    def __init__(self, data_dir: Path, probe=None, send=None, now=time.time):
        self.path = Path(data_dir) / "alerts.json"
        self.probe = probe or (lambda: {})
        self.send_raw = send or _post
        self.now = now
        self.lock = threading.Lock()
        self.cfg = self._load()
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
        return {"enabled": raw.get("enabled") is True and bool(topic), "server": server,
                "topic": topic or "eaveluxos-" + secrets.token_hex(8),
                "events": {k: ev.get(k) is not False for k in KINDS}, "sent_update": str(raw.get("sent_update") or "")}

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
                "subscribe": f"{c['server']}/{c['topic']}"}

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
        self.send("test", "Alerts from EaveLuxOS reach this phone.", tags="white_check_mark")

    def step(self):
        """One check: compare the conditions with what was already sent."""
        with self.lock:
            on, events = self.cfg["enabled"], dict(self.cfg["events"])
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
            return True
        except AlertError as e:
            log.warning("Couldn't send an alert: %s", e)
            return False

    def _loop(self):
        while not self.stop.wait(EVERY):
            self.step()

    def start(self):
        if self.thread is None:
            self.thread = threading.Thread(target=self._loop, daemon=True, name="alerts")
            self.thread.start()
