# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Web server for the EaveLuxOS GUI (standard library only).

Security model
- Requests from this computer itself are trusted, unless they carry reverse
  proxy headers (then they came from another machine through a proxy/tunnel).
- Other devices (phones, laptops) sign in with the app password and get a
  session token (sent in the X-Session header; 30 days after last use).
  Security changes from them need the password again (SENSITIVE).
- Before a password exists, another device can only finish setup with the
  6-digit code shown in the app's window/log.
- Every state-changing request must carry X-Requested-With (blocks CSRF).
- The Trimlight secret is never sent to the browser.
- Webhooks use their own token and nothing else.
"""
import base64
import copy
import hashlib
import hmac
import ipaddress
import json
import logging
import mimetypes
import os
import platform
import re
import socket
import sys
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from zoneinfo import available_timezones

from . import autostart, catalog
from .api import TrimlightAPI, TrimlightError
from .controller import Controller
from .safety import SafetyNet
from .schedule import ConfigError, Effect, SetupNeeded, add_real, build_config, color_gamma, tz_info
from .store import Conflict, Store, check_password, hash_password, needs_rehash

_DUMMY_HASH = hash_password("timing-equalizer-not-a-password")

log = logging.getLogger("eaveluxos.web")
STATIC = Path(__file__).parent / "static"
# The manual and license, readable without signing in (the footer links to
# the license on every screen, including the sign-in page).
DOCS = {"/docs/MANUAL.md": ("MANUAL.md", "text/markdown; charset=utf-8"),
        "/docs/LICENSE.txt": ("LICENSE", "text/plain; charset=utf-8")}


def doc_path(name: str) -> Path | None:
    """Find a document next to the app: the source folder, the folder of a
    bundled executable, or inside the bundle (PyInstaller)."""
    places = [Path(__file__).resolve().parent.parent, Path(sys.executable).resolve().parent]
    if getattr(sys, "_MEIPASS", None):
        places.insert(0, Path(sys._MEIPASS))
    for d in places:
        f = d / name
        if f.is_file():
            return f
    return None
from .version import VERSION  # noqa: E402  (kept importable from here)
COOKIE = "tls_session"
MAX_BODY = 2_000_000
# Headers a reverse proxy or tunnel adds. A request carrying any of them came
# from another machine even though the TCP connection is from 127.0.0.1.
PROXY_HEADERS = ("X-Forwarded-For", "X-Forwarded-Host", "X-Forwarded-Proto", "Forwarded", "X-Real-IP", "Via",
                 "CF-Connecting-IP", "True-Client-IP", "Tailscale-User-Login", "X-Original-Forwarded-For")
LOCAL_SUFFIXES = ("", ".local", ".lan", ".home", ".home.arpa", ".localdomain", ".internal")
COMMON_TZ = ["America/New_York", "America/Chicago", "America/Denver", "America/Phoenix", "America/Los_Angeles",
             "America/Anchorage", "Pacific/Honolulu", "America/Halifax", "America/St_Johns", "America/Toronto",
             "America/Vancouver", "Europe/London", "Europe/Dublin", "Australia/Sydney", "Pacific/Auckland"]


class _Reauth:
    """Session hash -> password confirmed until. Used from every request
    thread, so all access is under one lock."""
    def __init__(self):
        self._d: dict[str, float] = {}
        self._lock = threading.Lock()

    def valid(self, key: str, now: float) -> bool:
        with self._lock:
            for k in [k for k, t in self._d.items() if t <= now]:
                del self._d[k]
            return self._d.get(key, 0) > now

    def grant(self, key: str, until: float):
        with self._lock:
            self._d[key] = until

    def pop(self, key: str):
        with self._lock:
            self._d.pop(key, None)

    def clear(self):
        with self._lock:
            self._d.clear()


class ApiError(Exception):
    def __init__(self, msg, code=400, **extra):
        super().__init__(msg)
        self.code = code
        self.extra = extra


# Changes that affect security or access. From another device these need the
# app password again (once per 5 minutes per sign-in), so a borrowed or lost
# phone that's still signed in can't take over the account, webhooks or port.
SENSITIVE = {"/api/credentials", "/api/webhook", "/api/port", "/api/autostart", "/api/local_login",
             "/api/users", "/api/users/delete", "/api/session_policy"}
REAUTH_SECONDS = 300

# Roles (3.4). Administrators can do everything. Editors design patterns,
# schedules and the house map and control the lights, but can't change the
# household's location, controllers, weather or safety-net settings, accounts,
# or anything on the admin list. Viewers can look but not change anything.
EDITOR_POSTS = {"/api/action", "/api/settings", "/api/photo", "/api/photo/delete", "/api/device/save_effect", "/api/import"}
ADMIN_GETS = {"/api/users", "/api/safety/backup"}
HOUSEHOLD_KEYS = ("location", "safety", "weather", "setup_done", "color")
ROLE_NAMES = {"admin": "Administrator", "editor": "Editor", "viewer": "Viewer"}
# A browser on the app computer itself (when it doesn't require a password).
LOCAL_USER = {"id": None, "username": "this computer", "role": "admin", "disabled": False, "local": True}
_UNSET = object()


def _canon(v) -> str:
    return json.dumps(v, sort_keys=True, separators=(",", ":"))


def probe_app(port: int) -> bool:
    """Is this app answering on the port (HTTPS or HTTP)?"""
    import ssl
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE  # just "is it us?" on this computer
    for scheme in ("https", "http"):
        try:
            with urllib.request.urlopen(f"{scheme}://127.0.0.1:{port}/api/session", timeout=2,
                                        context=ctx if scheme == "https" else None) as r:
                if "version" in json.loads(r.read()):
                    return True
        except Exception:
            pass
    return False


IN_CONTAINER = os.environ.get("EAVELUXOS_CONTAINER") == "1"


def env_allowed_hosts() -> list[str]:
    """Extra host names from EAVELUXOS_ALLOWED_HOSTS (comma-separated), for
    containers, where there's no settings file to edit by hand."""
    return [h.strip().lower() for h in os.environ.get("EAVELUXOS_ALLOWED_HOSTS", "").split(",") if h.strip()]


def lan_addresses() -> list[str]:
    if IN_CONTAINER:
        return []   # the container's own address isn't the one phones use
    ips = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))  # no packet is sent
        ips.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    return sorted(ip for ip in ips if not ip.startswith("127."))


class App:
    def __init__(self, base: Path, start: bool = True):
        self.base = base
        self.started = start
        self.store = Store(base)
        self.safety = SafetyNet(self.store.dir)
        self.lock = threading.RLock()
        self.ctrl: Controller | None = None
        self.cfg = None
        self.problem = None          # why the scheduler isn't running yet
        self.problem_is_setup = True
        self.thread = None
        self.fails: dict[str, list] = {}
        self.fails_lock = threading.Lock()
        self.reauth = _Reauth()              # session hash -> password confirmed until
        self.rebuild()

    # ------------------------------------------------------------ lifecycle
    def client(self) -> TrimlightAPI:
        s = self.store.secrets
        if not (s.get("client_id") and s.get("client_secret")):
            raise ApiError("Enter your Trimlight Client ID and Client Secret first (Settings).", 409)
        api = TrimlightAPI(s["client_id"], s["client_secret"])
        api.clock_offset_min = self.clock_offset()
        return api

    def clock_offset(self) -> int:
        try:
            return max(-1440 * 366, min(1440 * 366, int(self.store.settings.get("controller", {}).get("clock_offset_min", 0))))
        except (TypeError, ValueError):
            return 0

    def now(self):
        return self.cfg.loc.now() if self.cfg else datetime.now().astimezone().replace(microsecond=0)

    def rebuild(self, creds_changed=False):
        with self.lock:
            try:
                cfg = build_config(self.store.settings, self.store.secrets)
            except SetupNeeded as e:
                self.problem, self.problem_is_setup = str(e), True
                return False
            except (ConfigError, ValueError, TypeError) as e:
                self.problem, self.problem_is_setup = str(e), False
                return False
            self.problem = None
            api = TrimlightAPI(cfg.client_id, cfg.client_secret)
            api.clock_offset_min = self.clock_offset()
            self.cfg = cfg
            if self.ctrl is None:
                self.ctrl = Controller(cfg, api, safety=self.safety)
                if self.started:
                    self._start_thread()
            else:
                self.ctrl.api.clock_offset_min = api.clock_offset_min
                self.ctrl.reload(cfg, api if creds_changed else None)
            return True

    def _start_thread(self):
        if self.thread is None and self.ctrl is not None:
            self.thread = threading.Thread(target=self.ctrl.run_forever, daemon=True, name="scheduler")
            self.thread.start()

    def start(self):
        """Start scheduling (call once the web port is held, so a second copy
        of the app can never run a second scheduler)."""
        with self.lock:
            self.started = True
            self._start_thread()

    def gamma(self) -> float | None:
        """Gamma correction in effect (None = off); bad values count as off
        here because save_settings refuses them."""
        try:
            return color_gamma(self.store.settings)
        except ConfigError:
            return None

    def setup_state(self) -> dict:
        s, loc = self.store.secrets, self.store.settings.get("location", {})
        return {"credentials": bool(s.get("client_id") and s.get("client_secret")),
                "location": not (float(loc.get("latitude", 0) or 0) == 0 and float(loc.get("longitude", 0) or 0) == 0),
                "password": self.store.has_users(),
                "wizard_done": bool(self.store.settings.get("setup_done")),
                "running": self.ctrl is not None and self.problem is None,
                "warnings": list(self.store.warnings),
                "problem": self.problem}

    # ------------------------------------------------------------ settings
    def validate(self, data: dict):
        """Check everything that's filled in. A missing location or missing
        patterns is allowed (setup isn't finished), but it must not hide errors
        elsewhere, so validate with a stand-in location in that case."""
        self._validate_map(data.get("map"))
        try:
            color_gamma(data)
        except ConfigError as e:
            raise ApiError(str(e))
        probe = copy.deepcopy(data)
        loc = probe.setdefault("location", {})
        try:
            unset = float(loc.get("latitude", 0) or 0) == 0 and float(loc.get("longitude", 0) or 0) == 0
        except (TypeError, ValueError):
            raise ApiError("Latitude and longitude must be numbers.")
        if unset:
            loc["latitude"], loc["longitude"] = 40.0, -75.0
        if not probe.get("effects"):
            if probe.get("rules") or probe.get("weather_rules"):
                raise ApiError("Rules need at least one pattern.")
            return
        try:
            build_config(probe, self.store.secrets, need_secrets=False)
        except (ConfigError, ValueError, TypeError, KeyError, AttributeError) as e:
            raise ApiError(str(e) if not isinstance(e, (KeyError, AttributeError)) else "Settings are malformed.")

    @staticmethod
    def _validate_map(m):
        if m is None:
            return
        if not isinstance(m, dict):
            raise ApiError("Map data is malformed.")
        tb = m.get("total_bulbs")
        if tb is not None and not (isinstance(tb, int) and 1 <= tb <= 10000):
            raise ApiError("Total bulbs must be 1-10000.")
        for side in m.get("sides", []) or []:
            if not (isinstance(side, dict) and re.fullmatch(r"[a-z0-9_-]{1,40}", str(side.get("id", "")))
                    and 1 <= len(str(side.get("name", ""))) <= 30):
                raise ApiError("A house side has an invalid id or name.")
        for lm in m.get("landmarks", []) or []:
            if not (isinstance(lm, dict) and isinstance(lm.get("bulb"), int) and 1 <= lm["bulb"] <= 10000
                    and 1 <= len(str(lm.get("name", "")).strip()) <= 60):
                raise ApiError("Each landmark needs a name (up to 60 characters) and a bulb number.")
            for k in ("x", "y"):
                if lm.get(k) is not None and not (isinstance(lm[k], (int, float)) and 0 <= lm[k] <= 1):
                    raise ApiError("A landmark pin is outside the photo.")
        rl = m.get("rooflines")
        if rl is not None:
            if not isinstance(rl, dict) or len(rl) > 50:
                raise ApiError("Roofline data is malformed.")
            for side, lines in rl.items():
                if not re.fullmatch(r"[a-z0-9_-]{1,40}", str(side)) or not isinstance(lines, list) or len(lines) > 40:
                    raise ApiError("Use at most 40 roofline sections per side.")
                ids = set()
                for ln in lines:
                    pts = ln.get("points") if isinstance(ln, dict) else None
                    if not (isinstance(ln, dict) and re.fullmatch(r"[A-Za-z0-9_-]{1,40}", str(ln.get("id", "")))
                            and ln["id"] not in ids and ln.get("kind") in ("edge", "ridge")
                            and isinstance(pts, list) and 2 <= len(pts) <= 100):
                        raise ApiError("A roofline section is malformed (2-100 points, edge or ridge).")
                    ids.add(ln["id"])
                    for pt in pts:
                        if not (isinstance(pt, list) and len(pt) == 2 and all(
                                isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v <= 100 for v in pt)):
                            raise ApiError("Roofline points must stay within the photo.")
                    wire = ln.get("wire", [])
                    if not (isinstance(wire, list) and len(set(wire)) == len(wire) and all(
                            isinstance(i, int) and not isinstance(i, bool) and 0 <= i < len(pts) - 1 for i in wire)):
                        raise ApiError("A roofline section has invalid wire-only segments.")
                    extra = set(ln) - {"id", "kind", "points", "wire"}
                    if extra:
                        raise ApiError("A roofline section has unknown fields.")
        names = set()
        for z in m.get("zones", []) or []:
            if not (isinstance(z, dict) and isinstance(z.get("start"), int) and isinstance(z.get("end"), int)
                    and 1 <= z["start"] <= z["end"] <= 10000 and 1 <= len(str(z.get("name", "")).strip()) <= 60):
                raise ApiError("Each zone needs a name and a first and last bulb (first not after last).")
            if z["name"].strip().lower() in names:
                raise ApiError(f"Two zones are named \u201c{z['name']}\u201d.")
            names.add(z["name"].strip().lower())

    def photo_path(self, side: str) -> Path:
        if not re.fullmatch(r"[a-z0-9_-]{1,40}", side or ""):
            raise ApiError("Invalid photo name.")
        return self.store.dir / "photos" / f"{side}.jpg"

    def rule_check(self) -> dict:
        """Find rules that never get a night in the next year because another
        rule always wins, so the user isn't left wondering why."""
        if not self.cfg:
            return {}
        memo_key = (self.store.rev, self.cfg.loc.now().date())
        if getattr(self, "_rc_memo", (None,))[0] == memo_key:
            return self._rc_memo[1]
        from collections import Counter
        from datetime import timedelta
        sch, today = self.cfg.schedule, self.cfg.loc.now().date()
        out = {}
        days = [today + timedelta(days=i) for i in range(366)]
        running = {d: {p.rule.name for p in sch.day_plans(d)} for d in days}
        for r in sch.rules:
            applies, wins, beaten = 0, 0, Counter()
            for d in days:
                w = sch._window(r, d)
                if not w:
                    continue
                applies += 1
                if r.name in running[d]:   # runs for at least part of its window
                    wins += 1
                else:                      # covered the whole time: by whom?
                    other = sch.active_window(add_real(w.start, (w.end.astimezone(timezone.utc) - w.start.astimezone(timezone.utc)) / 2))
                    if other:
                        beaten[other.rule.name] += 1
            info = {"applies": applies, "wins": wins, "blocked_by": None, "hint": ""}
            if applies and not wins and beaten:
                top = beaten.most_common(1)[0][0]
                other = next(x for x in sch.rules if x.name == top)
                info["blocked_by"] = top
                info["hint"] = ("Give this rule a higher priority than %d." % other.priority if other.priority >= r.priority
                                else "")
                if other.priority == r.priority:
                    info["hint"] = f"Both have priority {r.priority} and that one is listed first. Raise this rule's priority (for example to {r.priority + 10})."
            out[r.name] = info
        self._rc_memo = (memo_key, out)
        return out

    def change_port(self, value) -> dict:
        """Save a new web port and hand over to a copy of the app on it."""
        try:
            new = int(value)
        except (TypeError, ValueError):
            raise ApiError("Enter a port number.")
        if not 1024 <= new <= 65535:
            raise ApiError("Choose a port from 1024 to 65535.")
        if IN_CONTAINER:
            raise ApiError("In a container, change the published port (HOST_PORT in .env) instead.", 409)
        svc = self.store.settings.get("service", {})
        old = int(svc.get("web_port", 8787))
        if new == old:
            raise ApiError(f"The app already uses port {new}.")
        probe = socket.socket()
        try:
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            probe.bind((svc.get("web_host", "0.0.0.0"), new))
        except OSError:
            raise ApiError(f"Port {new} is already used by another program. Pick a different one.", 409)
        finally:
            probe.close()
        n = copy.deepcopy(self.store.settings)
        n["service"] = {**svc, "web_port": new}
        self.store.save_settings(n)
        threading.Thread(target=self._restart_on, args=(old, new), daemon=True).start()
        return {"ok": True, "port": new}

    def _restart_on(self, old: int, new: int):
        import os
        import subprocess
        time.sleep(0.6)  # let the reply reach the browser
        # Only our own service entries set this (see autostart.py). INVOCATION_ID
        # isn't usable: desktop terminals started by systemd carry it too.
        supervised = "1" in (os.environ.get("EAVELUXOS_SUPERVISED"), os.environ.get("LUMAOS_SUPERVISED"),
                             os.environ.get("TRIMLIGHT_SUPERVISED"))  # service files from earlier names

        def put_port_back():
            n = copy.deepcopy(self.store.settings)
            n["service"] = {**n.get("service", {}), "web_port": old}
            self.store.save_settings(n)

        # Never two schedulers at once: the new copy may only start once this
        # one's scheduler has really stopped. A safety-net sync can take a
        # while (a dozen cloud calls), so wait for it rather than give up.
        if self.ctrl:
            self.ctrl.stop_event.set()
            if self.thread:
                self.thread.join(timeout=120)
                if self.thread.is_alive():
                    log.error("Couldn't move to port %s: the scheduler didn't stop; staying on %s.", new, old)
                    put_port_back()
                    self.ctrl.stop_event.clear()   # the same thread carries on; no second one
                    return
        if supervised:
            log.info("Restarting on port %s (the system service restarts the app).", new)
            os._exit(0)
        kw = {"cwd": str(self.base), "stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
        if os.name == "nt":
            kw["creationflags"] = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        else:
            kw["start_new_session"] = True
        proc = None
        try:
            from . import autostart
            proc = subprocess.Popen(autostart.launch_command(self.base), **kw)
            deadline = time.time() + 60          # a Pi or a one-file bundle can be slow to start
            while time.time() < deadline:
                time.sleep(0.5)
                if probe_app(new):
                    log.info("Now running on port %s. This copy (port %s) is closing.", new, old)
                    os._exit(0)
                if proc.poll() is not None:
                    raise RuntimeError(f"the new copy exited (code {proc.returncode})")
            raise RuntimeError("the new copy didn't answer")
        except Exception as e:  # put everything back the way it was
            # Stop the new copy first, so it can't go on scheduling next to us.
            if proc is not None and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
            if probe_app(new):   # it came up after all (or survived): let it take over
                log.info("The copy on port %s answered late; this copy (port %s) is closing.", new, old)
                os._exit(0)
            log.error("Couldn't move to port %s (%s); staying on %s.", new, e, old)
            put_port_back()
            if self.ctrl:
                self.ctrl.stop_event.clear()
                self.thread = None
                self._start_thread()

    def safety_status(self) -> dict:
        sf = self.store.settings.get("safety", {}) or {}
        out = {"enabled": bool(sf.get("enabled")), "days": int(sf.get("days", 7) or 7), "devices": self.safety.summary(),
               "plan": []}
        if self.cfg:
            entries, _ = self.safety.plan(self.cfg, self.cfg.loc.now(), self.clock_offset())
            out["plan"] = [{"date": f"{e['month']:02d}-{e['day']:02d}", "on": "%02d:%02d" % tuple(e["start"]),
                            "off": "%02d:%02d" % tuple(e["end"]), "pattern": e["label"], "rule": e["rule"]} for e in entries]
        return out

    def save_settings(self, data: dict, expect_rev=None):
        if not isinstance(data, dict):
            raise ApiError("Settings must be an object.")
        self.validate(data)
        try:
            rev = self.store.save_settings(data, expect_rev)
        except Conflict:
            raise ApiError("These settings were changed on another device. Reloaded the latest; please make your change again.", 409)
        self.rebuild()
        return rev

    # ------------------------------------------------------------ devices
    def devices(self) -> list[dict]:
        api = self.client()
        chosen = set(self.store.settings.get("service", {}).get("devices", []))
        out = []
        try:
            listing = api.list_devices()
        except TrimlightError as e:
            raise ApiError(str(e), 502)
        # Ask every controller at once: one at a time, a slow cloud (15 s per
        # call) made this screen take minutes with several controllers.
        from concurrent.futures import ThreadPoolExecutor
        now = self.now()

        def detail(dev_id):
            try:
                return api.get_device(dev_id, now)
            except TrimlightError as e:
                return e
        with ThreadPoolExecutor(max_workers=max(1, min(4, len(listing)))) as pool:
            details = list(pool.map(detail, [d.get("deviceId") for d in listing]))
        for d, det in zip(listing, details):
            item = {"id": d.get("deviceId"), "name": d.get("name"), "online": d.get("connectivity") == 1,
                    "selected": not chosen or d.get("deviceId") in chosen}
            try:
                if isinstance(det, TrimlightError):
                    raise det
                item.update({"name": det.get("name", item["name"]), "ports": det.get("ports", []),
                             "ic": det.get("ic"), "colorOrder": det.get("colorOrder"),
                             "firmware": det.get("fwVersionName"), "switch": det.get("switchState"),
                             "effects": [{"id": e.get("id"), "name": e.get("name"), "category": e.get("category"),
                                          "mode": e.get("mode"), "speed": e.get("speed"),
                                          "brightness": e.get("brightness"), "pixelLen": e.get("pixelLen"),
                                          "reverse": e.get("reverse"), "pixels": e.get("pixels")}
                                         for e in det.get("effects", [])],
                             "daily": det.get("daily", []), "calendar": det.get("calendar", [])})
            except TrimlightError as e:
                item["error"] = str(e)
            out.append(item)
        return out

    def target_devices(self, ids=None) -> list[str]:
        if ids:
            return list(ids)
        chosen = self.store.settings.get("service", {}).get("devices", [])
        if chosen:
            return chosen
        try:
            return [d["deviceId"] for d in self.client().list_devices()]
        except TrimlightError as e:
            raise ApiError(str(e), 502)

    def update_device(self, body: dict):
        dev = body.get("deviceId")
        if not dev:
            raise ApiError("Choose a controller.")
        payload = {}
        if "name" in body:
            name = str(body["name"]).strip()
            if not 1 <= len(name) <= 30:
                raise ApiError("Controller name must be 1-30 characters.")
            payload["name"] = name
        if "ic" in body:
            if body["ic"] not in (0, 1):
                raise ApiError("Unknown LED chip type.")
            payload["ic"] = body["ic"]
        if "colorOrder" in body:
            if body["colorOrder"] not in range(6):
                raise ApiError("Unknown color order.")
            payload["colorOrder"] = body["colorOrder"]
        if "ports" in body:
            ports = []
            for p in body["ports"]:
                pid, st, en = int(p["id"]), int(p["start"]), int(p["end"])
                if pid not in range(4):
                    raise ApiError("Port must be 1-4.")
                off = st == 0 and en == 0
                if not off and not (1 <= st <= en <= 2048):
                    raise ApiError(f"Port {pid + 1}: bulbs must be within 1-2048 and the start can't be after the end.")
                ports.append({"id": pid, "start": st, "end": en})
            payload["ports"] = ports
        if not payload:
            raise ApiError("Nothing to change.")
        try:
            self.client().update_device(dev, payload)
        except TrimlightError as e:
            raise ApiError(str(e), 502)
        if self.ctrl:
            with self.ctrl.lock:
                self.ctrl.devices = []
                self.ctrl.last_verify = 0.0
        return {"ok": True}

    def set_clock(self, body: dict):
        """Send the time to the controllers. With a chosen date/time, remember
        the difference from real time and keep using it, because every request
        to the controller carries the time and would otherwise undo it."""
        real = self.now()
        if body.get("reset"):
            offset = 0
        elif body.get("datetime"):
            try:
                naive = datetime.fromisoformat(body["datetime"])
            except (TypeError, ValueError):
                raise ApiError("Use a date and time like 2026-12-24T18:30.")
            chosen = naive.replace(tzinfo=real.tzinfo) if naive.tzinfo is None else naive
            offset = round((chosen - real).total_seconds() / 60)
            if abs(offset) > 1440 * 366:
                raise ApiError("Pick a time within a year of today.")
        else:
            offset = self.clock_offset()
        if offset != self.clock_offset():
            n = copy.deepcopy(self.store.settings)
            n.setdefault("controller", {})["clock_offset_min"] = offset
            self.store.save_settings(n)
            self.rebuild()
        api = self.client()
        sent = []
        for dev in self.target_devices(body.get("deviceIds")):
            try:
                api.set_clock(dev, real)
                sent.append(dev)
            except TrimlightError as e:
                raise ApiError(str(e), 502)
        from datetime import timedelta
        shown = real + timedelta(minutes=offset)
        return {"ok": True, "sent": sent, "offset_min": offset, "label": shown.strftime("%a %b %d, %I:%M %p")}

    def save_to_controller(self, body: dict):
        name = str(body.get("name", "")).strip()
        if not 1 <= len(name) <= 30:
            raise ApiError("Pattern name must be 1-30 characters.")
        eff = Effect.from_config("_save", body.get("effect") or {}, self.gamma())
        if eff.kind == "saved":
            raise ApiError("That pattern is already on the controller.")
        payload = {"id": -1, "name": name, **eff.payload}
        api = self.client()
        out = []
        for dev in self.target_devices(body.get("deviceIds")):
            try:
                r = api.save_effect(dev, payload) or {}
                out.append({"device": dev, "id": r.get("id")})
            except TrimlightError as e:
                raise ApiError(str(e), 502)
        if self.ctrl:
            self.ctrl.saved = {}
        return {"ok": True, "saved": out}

    # ------------------------------------------------------------ misc
    def upcoming(self, days: int):
        if not self.cfg:
            return []
        sch, loc = self.cfg.schedule, self.cfg.loc
        out = []
        start = loc.now().date()
        from datetime import timedelta
        prev = None
        for i in range(days):
            d = start + timedelta(days=i)
            s = loc.sun(d)
            plans = sch.day_plans(d)
            wins = [{"on": p.start.isoformat(), "off": p.end.isoformat(), "on_label": p.start.strftime("%H:%M"),
                     "off_label": p.end.strftime("%H:%M"), "rule": p.rule.name, "effect": p.effect_label()} for p in plans]
            abbr = s["noon"].tzname() if s["noon"] else ""
            first = wins[0] if wins else {}
            out.append({"date": d.isoformat(), "sunrise": s["sunrise"] and s["sunrise"].strftime("%H:%M"),
                        "sunset": s["sunset"] and s["sunset"].strftime("%H:%M"), "abbr": abbr,
                        "dst_change": bool(prev and prev != abbr), "windows": wins,
                        **{k: first.get(k) for k in ("on", "off", "on_label", "off_label", "rule", "effect")}})
            prev = abbr
        return out

    def geocode(self, q: str):
        q = q.strip()
        if not 2 <= len(q) <= 80:
            raise ApiError("Type a town or city name.")
        url = "https://geocoding-api.open-meteo.com/v1/search?" + urllib.parse.urlencode(
            {"name": q, "count": 8, "language": "en", "format": "json"})
        try:
            req = urllib.request.Request(url, headers={"User-Agent": f"EaveLuxOS/{VERSION}"})
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read())
        except Exception:
            raise ApiError("Couldn't reach the place search service. Enter latitude and longitude instead.", 502)
        return [{"name": x.get("name"), "region": x.get("admin1"), "country": x.get("country"),
                 "lat": round(x["latitude"], 4), "lon": round(x["longitude"], 4), "timezone": x.get("timezone")}
                for x in data.get("results", []) or []]

    def import_settings(self, body: dict):
        incoming = body.get("settings")
        if not isinstance(incoming, dict):
            raise ApiError("That file isn't a EaveLuxOS export.")
        for k in ("setup_done", "_rev", "controller"):
            incoming.pop(k, None)
        cur = copy.deepcopy(self.store.settings)
        if body.get("mode") == "replace":
            keep = {k: cur.get(k) for k in ("location", "service", "setup_done", "controller") if k in cur}
            # Exports leave out the house map and safety-net settings, so a
            # file without them must not erase this home's copies.
            for k in ("map", "safety"):
                if k not in incoming and k in cur:
                    keep[k] = cur[k]
            new = {**incoming, **keep}
        else:  # merge: add patterns and rules that don't exist yet
            new = cur
            effs = new.setdefault("effects", {})
            added = 0
            renamed = {}   # incoming key -> key used here (same key, different pattern)
            for k, v in (incoming.get("effects") or {}).items():
                if k not in effs:
                    effs[k] = v
                    added += 1
                elif _canon(effs[k]) != _canon(v):
                    # Same key but a different pattern: add it under a new key,
                    # so imported rules keep the pattern they were made with.
                    i = 2
                    while f"{k}_{i}" in effs:
                        i += 1
                    nk = f"{k}_{i}"
                    effs[nk] = {**v, "label": f"{v.get('label', k)} ({i})"} if isinstance(v, dict) else v
                    renamed[k] = nk
                    added += 1

            def rekey(r):
                if not (renamed and isinstance(r, dict)):
                    return r
                e = r.get("effect")
                e = [renamed.get(x, x) for x in e] if isinstance(e, list) else renamed.get(e, e)
                return {**r, "effect": e}
            for key in ("rules", "weather_rules"):
                names = {r.get("name") for r in new.get(key, []) if isinstance(r, dict)}
                for r in incoming.get(key) or []:
                    if not isinstance(r, dict):
                        raise ApiError("That file isn't a EaveLuxOS export.")
                    if r.get("name") not in names:
                        new.setdefault(key, []).append(rekey(r))
                        added += 1
            if not added:
                raise ApiError("Everything in that file is already here (matched by name).")
        self.save_settings(new)
        return {"ok": True}


def host_allowed(header: str, extra: list) -> bool:
    """Block DNS-rebinding: a hostile web page can point its own domain at
    127.0.0.1 and talk to this app from the user's browser. Browsers always
    send that domain in Host, so only accept IP addresses, localhost, this
    computer's own name, and names the user listed in service.allowed_hosts."""
    h = (header or "").strip().lower()
    if not h:
        return True  # non-browser clients (curl, Home Assistant) may omit it
    if h.startswith("["):
        name = h[1:h.find("]")] if "]" in h else h
    else:
        name = h.rsplit(":", 1)[0] if h.count(":") == 1 else h
    try:
        ipaddress.ip_address(name)
        return True
    except ValueError:
        pass
    me = socket.gethostname().lower().split(".")[0]
    if name == "localhost" or name in {x.lower() for x in extra}:
        return True
    return any(name == me + suf for suf in LOCAL_SUFFIXES)


def make_server(app: App, host: str, port: int):
    def is_local_addr(addr: str) -> bool:
        return addr in ("127.0.0.1", "::1", "::ffff:127.0.0.1")

    class Handler(BaseHTTPRequestHandler):
        server_version = f"EaveLuxOS/{VERSION}"
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):
            log.debug("%s %s", self.address_string(), fmt % args)

        # -------------------------------------------------------- helpers
        def _token(self):
            # Sessions travel in a header, not a cookie: browsers send cookies
            # to every port on the same host, so another web app on this
            # computer would receive them. The token lives in the browser's
            # per-origin storage (port included) and is added by app.js.
            return self.headers.get("X-Session") or None

        def _local(self) -> bool:
            """Is this request from a browser on this computer? A reverse proxy
            or tunnel (Caddy, nginx, Tailscale Serve, cloudflared) on this
            computer also connects from 127.0.0.1, but on behalf of someone
            else, so a request carrying proxy headers is never local."""
            if not is_local_addr(self.client_address[0]):
                return False
            if any(self.headers.get(h) is not None for h in PROXY_HEADERS):
                # One handler serves every request on a keep-alive connection.
                # A proxy reuses its upstream connection for many outside
                # clients, so once a connection has carried a proxied request,
                # nothing else on it counts as this computer.
                self._via_proxy = True
            return not self._via_proxy

        _via_proxy = False

        _u = _UNSET

        def _user(self) -> dict | None:
            """Who is asking: this computer (trusted unless "require the
            password on this computer too" is on), a signed-in account, a
            setup session, or None. Looked up once per request."""
            if self._u is _UNSET:
                if self._local() and not app.store.local_login_required():
                    self._u = dict(LOCAL_USER)
                else:
                    self._u = app.store.session_user(self._token())
            return self._u

        def _authed(self) -> bool:
            return self._user() is not None

        def _is_admin(self) -> bool:
            u = self._user()
            return bool(u and u["role"] == "admin")

        def _authorize_post(self, path, b):
            """Role check for a change (server-side; the app only hides buttons)."""
            u = self._user()
            if u["role"] == "admin" or path == "/api/password":
                return
            if u["role"] == "viewer":
                raise ApiError("This account can only view. Ask an Administrator for Editor access.", 403)
            if path not in EDITOR_POSTS:
                raise ApiError("Only an Administrator can do that.", 403)
            if path == "/api/settings":
                cur = app.store.settings
                for k in HOUSEHOLD_KEYS:
                    if _canon(b.get(k)) != _canon(cur.get(k)):
                        raise ApiError("Only an Administrator can change location, weather, safety-net, color-correction or setup settings.", 403)
                devs = (b.get("service") or {}).get("devices", cur.get("service", {}).get("devices", []))
                if _canon(devs) != _canon(cur.get("service", {}).get("devices", [])):
                    raise ApiError("Only an Administrator can choose controllers.", 403)
            if path == "/api/import" and b.get("mode") == "replace":
                raise ApiError("Only an Administrator can replace everything. Use \u201cAdd to mine\u201d instead.", 403)

        def _send(self, code, body: bytes, ctype: str, extra=None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy",
                             "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
                             "script-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; "
                             "form-action 'self'; frame-ancestors 'none'")
            self.send_header("Cross-Origin-Opener-Policy", "same-origin")
            self.send_header("Cross-Origin-Resource-Policy", "same-origin")
            self.send_header("Permissions-Policy", "geolocation=(self), camera=(), microphone=(), payment=(), usb=()")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            try:
                self.end_headers()
            except (BrokenPipeError, ConnectionResetError):
                self.close_connection = True
                return
            if self.command != "HEAD":
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    self.close_connection = True  # client went away; nothing to do

        def _json(self, code, obj, extra=None):
            self._send(code, json.dumps(obj, default=str).encode(), "application/json", extra)

        def _read_raw(self) -> bytes:
            """Read the whole body exactly once per request. Bad lengths close
            the connection so leftover bytes can't be read as another request.
            (One handler object serves every request on a keep-alive
            connection, so the cache is cleared in do_GET/do_POST.)"""
            if self._raw is not None:
                return self._raw
            if self.headers.get("Transfer-Encoding"):
                self.close_connection = True
                raise ApiError("Chunked requests aren't supported.", 411)
            cl = self.headers.get("Content-Length", "0") or "0"
            if not cl.isdigit():
                self.close_connection = True
                raise ApiError("Bad Content-Length.", 400)
            n = int(cl)
            if n > MAX_BODY:
                self.close_connection = True
                raise ApiError("Request is too large.", 413)
            self._raw = self.rfile.read(n) if n else b""
            return self._raw

        def _body(self) -> dict:
            raw = self._read_raw()
            if not raw.strip():
                return {}
            try:
                data = json.loads(raw)
            except ValueError:
                raise ApiError("Request body isn't valid JSON.")
            if not isinstance(data, dict):
                raise ApiError("Request body must be a JSON object.")
            return data

        def _static(self, path):
            name = "index.html" if path in ("/", "") else path.lstrip("/")
            f = (STATIC / name).resolve()
            if STATIC.resolve() not in f.parents or not f.is_file():
                return self._json(404, {"error": "not found"})
            ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
            if f.suffix == ".webmanifest":
                ctype = "application/manifest+json"
            if ctype.startswith("text/") or ctype.endswith(("javascript", "json")):
                ctype += "; charset=utf-8"
            self._send(200, f.read_bytes(), ctype)

        def _client_key(self) -> str:
            """Who to count failed sign-ins against. Through a proxy on this
            computer, every client arrives from 127.0.0.1, so use the address
            the proxy reports (the last X-Forwarded-For hop is the one the
            proxy added itself; earlier ones are the client's to invent).
            IPv6 clients are counted per /64, since one home or phone gets a
            whole /64 and can pick a new address for every try."""
            peer = self.client_address[0]
            ip = peer
            if is_local_addr(peer):
                xff = self.headers.get("X-Forwarded-For")
                for v in ((xff.split(",")[-1] if xff else None), self.headers.get("X-Real-IP"),
                          self.headers.get("CF-Connecting-IP"), self.headers.get("True-Client-IP")):
                    if v and v.strip():
                        ip = v.strip()
                        break
            try:
                a = ipaddress.ip_address(ip.removeprefix("::ffff:") if ip.startswith("::ffff:") and "." in ip else ip)
            except ValueError:
                return "proxy:" + ip[:64]
            if a.version == 6:
                return str(ipaddress.ip_network(f"{a}/64", strict=False))
            return str(a)

        def _too_many(self, ip) -> bool:
            now = time.time()
            with app.fails_lock:
                for k in [k for k, v in app.fails.items() if not v or now - v[-1] > 600]:
                    app.fails.pop(k, None)
                hist = [t for t in app.fails.get(ip, []) if now - t < 600]
                app.fails[ip] = hist
                return len(hist) >= 10

        def _failed(self, ip):
            with app.fails_lock:
                app.fails.setdefault(ip, []).append(time.time())
            time.sleep(1)

        def _confirm_password(self, path, b):
            """Ask a signed-in phone for the app password again before a
            security change (see SENSITIVE). Not needed on this computer, or
            before an app password exists (setup with the setup code)."""
            given = b.pop("confirm_password", None)
            u = self._user()
            if path not in SENSITIVE or u.get("local") or u.get("setup"):
                return
            ph = app.store.password_hash_of(u["id"])
            tok = self._token()
            if not ph or not tok:
                return
            key = hashlib.sha256(tok.encode()).hexdigest()
            now = time.time()
            if app.reauth.valid(key, now):
                return
            ip = self._client_key()
            if self._too_many(ip):
                raise ApiError("Too many tries. Wait 10 minutes.", 429)
            if given is None:
                raise ApiError("Enter the app password to make this change.", 403, reauth=True)
            if not check_password(str(given), ph):
                self._failed(ip)
                raise ApiError("That password isn't right.", 403, reauth=True)
            app.reauth.grant(key, now + REAUTH_SECONDS)

        # -------------------------------------------------------- GET
        def do_HEAD(self):
            self.do_GET()

        def _host_ok(self) -> bool:
            extra = (app.store.settings.get("service", {}).get("allowed_hosts", []) or []) + env_allowed_hosts()
            if host_allowed(self.headers.get("Host", ""), extra):
                return True
            log.warning("Refused request for unknown host %r from %s", self.headers.get("Host"), self.client_address[0])
            self.close_connection = True
            self._send(421, b"Unknown host name. If it's yours, run on the app computer: python3 main.py allow-host NAME",
                       "text/plain; charset=utf-8")
            return False

        _raw = None

        def do_GET(self):
            self._raw = None
            self._u = _UNSET
            if not self._host_ok():
                return
            try:
                # Always consume a body, even on GET/HEAD: bytes left on a
                # keep-alive connection would be read as the next request
                # (request smuggling through a reverse proxy).
                self._read_raw()
            except ApiError as e:
                self.close_connection = True
                return self._json(e.code, {"error": str(e)})
            url = urllib.parse.urlparse(self.path)
            path, q = url.path, {k: v[0] for k, v in urllib.parse.parse_qs(url.query).items()}
            if path in DOCS:
                name, ctype = DOCS[path]
                f = doc_path(name)
                if not f:
                    return self._json(404, {"error": f"{name} isn't included in this copy of the app."})
                return self._send(200, f.read_bytes(), ctype)
            if not path.startswith("/api/"):
                return self._static(path)
            try:
                if path == "/api/session":
                    st = app.setup_state()
                    authed = self._authed()
                    out = {"authed": authed, "local": self._local(), "password_set": st["password"],
                           "setup_open": not st["password"] and not st["wizard_done"], "version": VERSION}
                    if authed:
                        u = self._user()
                        out["setup"] = st
                        out["user"] = {"username": u["username"], "role": u["role"], "local": bool(u.get("local")),
                                       "setup": bool(u.get("setup"))}
                    return self._json(200, out)
                if not self._authed():
                    return self._json(401, {"error": "Sign in first."})
                if path in ADMIN_GETS and not self._is_admin():
                    return self._json(403, {"error": "Only an Administrator can see that."})
                if path.startswith("/api/photo/"):
                    f = app.photo_path(path.rsplit("/", 1)[-1])
                    if not f.is_file():
                        return self._json(404, {"error": "No photo yet."})
                    return self._send(200, f.read_bytes(), "image/jpeg")
                r = self._get(path, q)
                return self._json(200, r)
            except ApiError as e:
                return self._json(e.code, {"error": str(e)})
            except ValueError:
                return self._json(400, {"error": "A value in the address isn't valid."})
            except Exception:
                log.exception("GET %s failed", path)
                return self._json(500, {"error": "Something went wrong. Details are in the log."})

        def _get(self, path, q):
            if path == "/api/status":
                if app.ctrl is None:
                    return {"setup_only": True, "setup": app.setup_state()}
                st = app.ctrl.status()
                st["setup"] = app.setup_state()
                return st
            if path == "/api/catalog":
                return catalog.catalog()
            if path == "/api/settings":
                return app.store.settings
            if path == "/api/devices":
                return app.devices()
            if path == "/api/upcoming":
                return app.upcoming(max(1, min(400, int(q.get("days", 14)))))
            if path == "/api/timezones":
                rest = sorted(z for z in available_timezones() if "/" in z and not z.startswith(("Etc/", "SystemV/")))
                return {"common": COMMON_TZ, "all": rest}
            if path == "/api/tzinfo":
                try:
                    return tz_info(q.get("name", "America/New_York"))
                except Exception:
                    raise ApiError("Unknown time zone.")
            if path == "/api/geocode":
                return app.geocode(q.get("q", ""))
            if path == "/api/account":
                s, u = app.store.secrets, self._user()
                out = {"password_set": app.store.has_users(), "addresses": lan_addresses(),
                       "scheme": getattr(app, "scheme", "http"),
                       "port": app.store.settings.get("service", {}).get("web_port", 8787),
                       "version": VERSION, "user": {"username": u["username"], "role": u["role"],
                                                    "local": bool(u.get("local")), "setup": bool(u.get("setup"))}}
                if u["role"] != "admin":
                    return out   # no credentials, webhook token or folders for Editors and Viewers
                from .store import SESSION_IDLE_CHOICES, SESSION_MAX_DAYS
                out.update({"client_id": s.get("client_id", ""),
                            "secret_hint": ("••••" + s["client_secret"][-4:]) if s.get("client_secret") else "",
                            "webhook_token": s.get("webhook_token"), "local_login": app.store.local_login_required(),
                            "autostart": autostart.status(app.base), "python": platform.python_version(),
                            "data_dir": str(app.store.dir), "session_idle_hours": app.store.session_idle_hours(),
                            "session_idle_choices": list(SESSION_IDLE_CHOICES), "session_max_days": SESSION_MAX_DAYS})
                return out
            if path == "/api/users":
                return app.store.users()
            if path == "/api/safety":
                return app.safety_status()
            if path == "/api/history":
                return app.store.history(max(1, min(100, int(q.get("limit", 30)))))
            if path == "/api/photos":
                d = app.store.dir / "photos"
                return sorted(f.stem for f in d.glob("*.jpg")) if d.is_dir() else []
            if path == "/api/rulecheck":
                return app.rule_check()
            if path == "/api/safety/backup":
                name = q.get("file", "")
                if not re.fullmatch(r"[A-Za-z0-9_-]+-(\d{8}-\d{6}-\d{6}|original)\.json", name):
                    raise ApiError("Unknown backup.", 404)
                f = app.safety.backup_dir / name
                if not f.is_file():
                    raise ApiError("That backup no longer exists.", 404)
                return json.loads(f.read_text(encoding="utf-8"))
            if path == "/api/export":
                data = copy.deepcopy(app.store.settings)
                for k in ("location", "service", "setup_done", "_rev", "controller", "map", "safety"):
                    data.pop(k, None)
                return {"format": "eaveluxos", "version": VERSION,
                        "exported": datetime.now().isoformat(timespec="seconds"), "settings": data}
            raise ApiError("not found", 404)

        # -------------------------------------------------------- POST/PUT
        def do_PUT(self):
            self.do_POST()

        def do_POST(self):
            self._raw = None
            self._u = _UNSET
            if not self._host_ok():
                return
            url = urllib.parse.urlparse(self.path)
            path = url.path
            ip = self._client_key()
            try:
                self._read_raw()  # always consume the body, even for early refusals
                if path.startswith("/api/hook/"):
                    return self._hook(url)
                if self.headers.get("X-Requested-With") != "eaveluxos":
                    return self._json(403, {"error": "Missing request header."})
                if path == "/api/login":
                    return self._login(ip)
                if path == "/api/logout":
                    tok = self._token()
                    if tok:
                        app.store.end_session(tok)
                        app.reauth.pop(hashlib.sha256(tok.encode()).hexdigest())
                    return self._json(200, {"ok": True})
                if not self._authed():
                    return self._json(401, {"error": "Sign in first."})
                b = self._body()
                self._authorize_post(path, b)
                self._confirm_password(path, b)
                return self._json(200, self._post(path, b))
            except ApiError as e:
                return self._json(e.code, {"error": str(e), **e.extra})
            except TrimlightError as e:
                return self._json(502, {"error": str(e)})
            except ValueError as e:
                return self._json(400, {"error": str(e)})
            except Exception:
                log.exception("POST %s failed", path)
                return self._json(500, {"error": "Something went wrong. Details are in the log."})

        def _login(self, ip):
            if self._too_many(ip):
                return self._json(429, {"error": "Too many tries. Wait 10 minutes."})
            b = self._body()
            label = str(b.get("device", self.headers.get("User-Agent", "device")))[:80]
            accounts = app.store.has_users()
            uid = None
            if accounts:
                pw = str(b.get("password", ""))
                found = app.store.user_by_name(str(b.get("username") or "admin"))
                # Unknown names cost the same time as wrong passwords.
                ok = check_password(pw, found[1] if found else _DUMMY_HASH) and bool(found) and not found[0]["disabled"]
                if ok:
                    uid = found[0]["id"]
                    if needs_rehash(found[1]):   # upgrade an older (PBKDF2) hash to scrypt
                        app.store.set_password_hash(uid, hash_password(pw))
            elif app.store.settings.get("setup_done"):
                return self._json(403, {"error": "Create an account on the main computer (Settings \u203a Accounts) to use other devices."})
            else:
                ok = hmac.compare_digest(str(b.get("code", "")).encode(), app.store.setup_code.encode())
            if not ok:
                self._failed(ip)
                return self._json(403, {"error": "That user name or password isn't right." if accounts else "That setup code isn't right."})
            tok = app.store.new_session(label, uid)
            # Also clear the cookie older versions set, so it stops being sent to other ports.
            return self._json(200, {"ok": True, "token": tok},
                              {"Set-Cookie": f"{COOKIE}=; Max-Age=0; Path=/; HttpOnly; SameSite=Strict"})

        def _post(self, path, b):
            ctrl = app.ctrl
            if path == "/api/action":
                if ctrl is None:
                    raise ApiError("Finish setup first.", 409)
                a = b.get("action")
                if a == "try":
                    eff = Effect.from_config("_try", b.get("effect") or {}, app.gamma())
                    eff.label = str((b.get("effect") or {}).get("label") or "Preview")[:40]
                    try:
                        minutes = max(1, min(120, int(b.get("minutes", 15))))
                    except (TypeError, ValueError):
                        minutes = 15
                    ctrl.manual(True, obj=eff, expires_min=minutes)
                elif a == "on":
                    # No pattern named (the On button): tonight's scheduled one.
                    ctrl.manual(True, b.get("effect") or ctrl.default_on_effect())
                elif a == "off":
                    ctrl.manual(False)
                elif a == "resume":
                    ctrl.resume()
                elif a == "levels":
                    ctrl.set_levels(b.get("brightness"), b.get("speed"))
                elif a == "flash":
                    ctrl.start_flash(b.get("minutes"))
                elif a == "stop_flash":
                    ctrl.stop_flash()
                elif a == "music":
                    # minutes: a number, 0 for "until I stop it", or left out
                    # for the length set on the Music screen.
                    m = b.get("minutes", ctrl.cfg.music["minutes"])
                    try:
                        m = int(m or 0)
                    except (TypeError, ValueError):
                        raise ApiError("Show length must be a whole number of minutes.") from None
                    ctrl.start_music(m or None)
                elif a == "stop_music":
                    ctrl.stop_music()
                else:
                    raise ApiError("Unknown action.")
                return ctrl.status()
            if path == "/api/settings":
                if "_rev" not in b:
                    raise ApiError("Missing settings revision; reload the page.", 409)
                # Network/security settings aren't editable through the settings
                # document (a signed-in phone could otherwise add allowed hosts or
                # rebind the server). Only the controller list is taken from it;
                # the port has its own endpoint, allowed_hosts is file-only.
                cur = app.store.settings
                cur_svc = cur.get("service", {})
                devs = (b.get("service") or {}).get("devices", cur_svc.get("devices", []))
                if not (isinstance(devs, list) and all(isinstance(x, str) and len(x) <= 64 for x in devs)):
                    raise ApiError("Controller list is malformed.")
                b["service"] = {**cur_svc, "devices": devs}
                if "controller" in cur:
                    b["controller"] = cur["controller"]
                else:
                    b.pop("controller", None)
                rev = app.save_settings(b, b.get("_rev"))
                return {"ok": True, "_rev": rev, "setup": app.setup_state()}
            if path == "/api/credentials":
                cid, sec = str(b.get("client_id", "")).strip(), str(b.get("client_secret", "")).strip()
                if not cid:
                    raise ApiError("Enter the Client ID.")
                if not sec:
                    sec = app.store.secrets.get("client_secret", "")
                    if not sec:
                        raise ApiError("Enter the Client Secret.")
                try:
                    devices = TrimlightAPI(cid, sec).list_devices()
                except TrimlightError as e:
                    raise ApiError(f"Trimlight didn't accept these: {e}", 400)
                app.store.save_secrets(client_id=cid, client_secret=sec)
                app.rebuild(creds_changed=True)
                return {"ok": True, "devices": [{"id": d.get("deviceId"), "name": d.get("name"),
                                                 "online": d.get("connectivity") == 1} for d in devices]}
            if path == "/api/device/update":
                return app.update_device(b)
            if path == "/api/device/clock":
                return app.set_clock(b)
            if path == "/api/device/save_effect":
                return app.save_to_controller(b)
            if path == "/api/password":
                return self._change_password(b)
            if path == "/api/users":
                return self._save_user(b)
            if path == "/api/users/delete":
                me = self._user()
                if b.get("id") and b.get("id") == me.get("id"):
                    raise ApiError("You can't delete the account you're signed in with. Ask another Administrator.")
                app.store.delete_user(str(b.get("id", "")))
                return {"ok": True}
            if path == "/api/session_policy":
                app.store.set_session_idle_hours(int(b.get("idle_hours", 0)))
                return {"ok": True, "idle_hours": app.store.session_idle_hours()}
            if path == "/api/history/restore":
                old = app.store.history_version(int(b.get("rev", 0)))
                if old is None:
                    raise ApiError("That version isn't in the history any more.", 404)
                cur = app.store.settings
                # restore patterns, schedule, map etc.; keep how this computer is set up
                for k in ("service", "controller", "setup_done"):
                    if k in cur:
                        old[k] = cur[k]
                    else:
                        old.pop(k, None)
                rev = app.save_settings(old, cur.get("_rev"))
                return {"ok": True, "_rev": rev}
            if path == "/api/warnings/dismiss":
                app.store.warnings.clear()
                return {"ok": True}
            if path == "/api/local_login":
                on = bool(b.get("enabled"))
                if on and not app.store.has_users():
                    raise ApiError("Create an Administrator account first.")
                app.store.save_secrets(local_login=True if on else None)
                return {"ok": True, "local_login": on}
            if path == "/api/sessions/end_all":
                app.store.end_all_sessions()
                app.reauth.clear()
                return {"ok": True}
            if path == "/api/webhook":
                import secrets as pysecrets
                token = pysecrets.token_urlsafe(24) if b.get("enable") else None
                app.store.save_secrets(webhook_token=token)
                app.rebuild()
                return {"ok": True, "webhook_token": token}
            if path == "/api/autostart":
                try:
                    return autostart.set_enabled(app.base, bool(b.get("enabled")))
                except (OSError, RuntimeError) as e:
                    raise ApiError(str(e))
            if path == "/api/import":
                return app.import_settings(b)
            if path == "/api/photo":
                f = app.photo_path(str(b.get("side", "")))
                data = str(b.get("data", ""))
                if data.startswith("data:"):
                    data = data.split(",", 1)[-1]
                try:
                    raw = base64.b64decode(data, validate=True)
                except (ValueError, TypeError):
                    raise ApiError("That photo couldn't be read.")
                if not raw.startswith(b"\xff\xd8") or len(raw) > 1_500_000:
                    raise ApiError("Use a JPEG photo (the app shrinks it before upload).")
                f.parent.mkdir(exist_ok=True)
                f.write_bytes(raw)
                return {"ok": True}
            if path == "/api/photo/delete":
                f = app.photo_path(str(b.get("side", "")))
                f.unlink(missing_ok=True)
                return {"ok": True}
            if path == "/api/safety/sync":
                if not app.ctrl:
                    raise ApiError("Finish setup first.", 409)
                with app.safety.lock:
                    app.safety.retry_at = 0
                    for d in app.safety.state["devices"].values():
                        d["hash"] = None
                app.ctrl.tick()
                return app.safety_status()
            if path == "/api/safety/daily_off":
                api = app.client()
                import contextlib
                # Same lock as the scheduler's own cloud writes (and its safety
                # sync), so the two never write to a controller at once.
                with (app.ctrl.apply_lock if app.ctrl else contextlib.nullcontext()):
                    n = sum(app.safety.disable_app_daily_timers(api, dev, app.now()) for dev in app.target_devices())
                return {"ok": True, "turned_off": n}
            if path == "/api/port":
                return app.change_port(b.get("port"))
            if path == "/api/quit":
                if not self._local():
                    raise ApiError("Quit the app from the computer it runs on.", 403)
                if IN_CONTAINER:
                    raise ApiError("The app runs in a container here, which starts it again by itself. "
                                   "Stop it with: docker compose stop", 400)
                from . import autostart
                at_login = autostart.status(app.base)["enabled"]

                def quit_now():
                    import os
                    # Run as a login service, a plain exit is restarted at once;
                    # ask the service manager to stop it instead.
                    autostart.stop_service()
                    os._exit(0)
                threading.Timer(0.5, quit_now).start()
                return {"ok": True, "starts_at_login": at_login}
            raise ApiError("not found", 404)

        def _first_account_token(self, uid):
            """A setup session (setup code) that creates the first account is
            switched over to that account, since setup sessions end then."""
            if self._user().get("setup"):
                old = self._token()
                tok = app.store.new_session(str(self.headers.get("User-Agent", "device"))[:80], uid)
                if old:
                    app.store.end_session(old)
                return tok
            return None

        def _change_password(self, b):
            new = str(b.get("new", ""))
            u = self._user()
            if u.get("local") or u.get("setup"):
                # This computer (or setup): set the password of an account by
                # name ("admin" unless given). With no accounts yet, this creates
                # the first Administrator.
                name = str(b.get("username") or "admin")
                found = app.store.user_by_name(name)
                if found:
                    f = found[0]
                    app.store.save_user(f["id"], f["username"], f["role"], f["disabled"], password=new)
                    app.reauth.clear()
                    return {"ok": True}
                if app.store.has_users():
                    raise ApiError(f"There's no account named \u201c{name}\u201d.", 404)
                created = app.store.save_user(None, name, "admin", password=new)
                tok = self._first_account_token(created["id"])
                return {"ok": True, **({"token": tok} if tok else {})}
            ip = self._client_key()
            if self._too_many(ip):
                raise ApiError("Too many tries. Wait 10 minutes.", 429)
            if not check_password(str(b.get("current", "")), app.store.password_hash_of(u["id"]) or _DUMMY_HASH):
                self._failed(ip)
                raise ApiError("Your current password isn't right.", 403)
            # A new password signs this account out everywhere except here.
            app.store.save_user(u["id"], u["username"], u["role"], u["disabled"], password=new, keep_token=self._token())
            app.reauth.clear()
            return {"ok": True}

        def _save_user(self, b):
            me = self._user()
            uid = b.get("id") or None
            pw = b.get("password") or None
            saved = app.store.save_user(uid, str(b.get("username", "")), str(b.get("role", "")), bool(b.get("disabled")),
                                        password=None if pw is None else str(pw),
                                        keep_token=self._token() if uid and uid == me.get("id") else None)
            tok = None if uid else self._first_account_token(saved["id"]) if len(app.store.users()) == 1 else None
            return {"ok": True, "user": saved, **({"token": tok} if tok else {})}

        def _hook(self, url):
            token = app.store.secrets.get("webhook_token")
            if not token or app.ctrl is None:
                return self._json(404, {"error": "Webhooks are off."})
            q = {k: v[0] for k, v in urllib.parse.parse_qs(url.query).items()}
            if "token" in q:
                # A token in the address ends up in browser history and in proxy
                # and Home Assistant logs, so it isn't accepted there.
                log.warning("Refused webhook from %s: token was in the URL", self.client_address[0])
                return self._json(400, {"error": "Send the token in the X-Token header, or as \"token\" in a JSON body, not in the URL."})
            data = self._body()
            given = str(self.headers.get("X-Token") or data.pop("token", "") or "")
            if not hmac.compare_digest(given.encode(), token.encode()):
                log.warning("Rejected webhook from %s (bad token)", self.client_address[0])
                return self._json(403, {"error": "bad token"})
            body = {**q, **data, "action": url.path.rsplit("/", 1)[-1]}
            if body["action"] not in ("flash", "stop_flash", "on", "off", "resume", "levels", "music", "stop_music"):
                return self._json(400, {"error": "unknown action"})
            self._post("/api/action", body)
            app.ctrl.note(f"Webhook '{body['action']}' from {self.client_address[0]}")
            t = app.ctrl.status()["target"]
            return self._json(200, {"ok": True, "on": t["on"], "effect": t["effect"], "reason": t["reason"]})

    srv = _Server((host, port), Handler)
    cert, key = app.store.dir / "tls" / "cert.pem", app.store.dir / "tls" / "key.pem"
    app.scheme = "http"
    if cert.is_file() and key.is_file():
        # Optional HTTPS with the owner's own certificate (for example from
        # mkcert). The handshake runs in each request's thread, so a client
        # that connects and stalls can't block everyone else.
        import ssl
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        try:
            ctx.load_cert_chain(cert, key)
        except (ssl.SSLError, OSError) as e:
            srv.server_close()
            raise OSError(f"The HTTPS certificate in {cert.parent} couldn't be loaded ({e}). Fix or remove it.") from None
        srv.socket = ctx.wrap_socket(srv.socket, server_side=True, do_handshake_on_connect=False)
        app.scheme = "https"
    return srv


class _Server(ThreadingHTTPServer):
    """On Windows, SO_REUSEADDR lets two programs bind the same port at once
    (both then get garbled traffic), so claim the port exclusively there."""
    allow_reuse_address = os.name != "nt"
    daemon_threads = True

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

    def handle_error(self, request, client_address):
        import ssl
        exc = sys.exc_info()[1]
        if isinstance(exc, (ssl.SSLError, ConnectionError, TimeoutError)):
            return  # a browser refusing a certificate, or a dropped connection
        super().handle_error(request, client_address)

    def finish_request(self, request, client_address):
        request.settimeout(30)  # covers the TLS handshake as well as slow clients
        super().finish_request(request, client_address)
