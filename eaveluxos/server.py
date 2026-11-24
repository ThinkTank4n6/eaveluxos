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
import csv
import io
import ipaddress
import json
import logging
import mimetypes
import os
import platform
import re
import secrets
import socket
import sys
import threading
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from zoneinfo import available_timezones

from . import alerts, automations, autostart, catalog, community, gameday, holidays, keepawake, lanlink, localmode, presence, restore, scores, sharecode, sound, updates, winfirewall
from .api import TrimlightAPI, TrimlightError, port_base
from .controller import Controller
from . import safety
from .safety import SafetyNet
from .schedule import CELEBRATE_POINTS, ConfigError, Effect, SetupNeeded, add_real, build_config, color_gamma, tz_info, ts
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
RESTORE_MAX = 100 * 1024 * 1024        # 4.17: an encrypted backup with photos (at most 60 MB of them)
PHOTO_UPLOAD_MAX = 30_000_000   # an original phone photo, sent as is (/api/photo/upload)
PHOTO_SIDE = 1600
# Formats decoded at full size (PNG, WebP, ...): a tiny file can describe a
# huge image, and 12000 x 12000 already took about 860 MB. JPEGs are decoded at
# a fraction of their size (draft), so only the overall cap applies to them.
PHOTO_MAX_PIXELS_FULL_DECODE = 40_000_000


class PhotoUnreadable(Exception):
    """The app computer can't read this photo (code 415), or has no image
    library (501); the browser then shrinks it itself instead."""
    def __init__(self, msg: str, code: int):
        super().__init__(msg)
        self.code = code


def shrink_photo(raw: bytes, max_side: int = PHOTO_SIDE) -> bytes:
    """An uploaded photo, turned upright (EXIF), fitted inside max_side and
    saved as JPEG, on this computer's processor. Browsers did this on the
    graphics card, and some graphics drivers return garbage (solid green,
    stripes)."""
    try:
        from PIL import Image
    except ImportError:
        raise PhotoUnreadable("This computer has no image library (Pillow).", 501) from None
    Image.MAX_IMAGE_PIXELS = 250_000_000      # 200-megapixel phone photos; the file size is capped too
    try:
        with Image.open(io.BytesIO(raw)) as im:     # reads only the header so far
            if im.format in ("JPEG", "MPO"):           # MPO: the JPEG variant some phones save
                im.draft("RGB", (max_side, max_side))
            elif im.size[0] * im.size[1] > PHOTO_MAX_PIXELS_FULL_DECODE:
                raise PhotoUnreadable(f"That image is too large ({im.size[0]} x {im.size[1]}). "
                                      "Save it as a JPEG, or smaller, and upload it again.", 413)   # decode at a fraction of full size: fast, little memory
            im = _upright(im)
            if im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info):
                rgba = im.convert("RGBA")
                flat = Image.new("RGB", rgba.size, (255, 255, 255))
                flat.paste(rgba, mask=rgba.split()[3])
                im = flat
            else:
                im = im.convert("RGB")
            im.thumbnail((max_side, max_side), Image.LANCZOS)
            out = io.BytesIO()
            im.save(out, "JPEG", quality=85, optimize=True)
            return out.getvalue()
    except PhotoUnreadable:
        raise
    except Exception as e:
        # Anything else in a photo the image library can't handle (4.4.5:
        # ZeroDivisionError from a camera's 0/0 EXIF value) means the
        # browser shrinks it instead, rather than "Something went wrong".
        log.warning("This computer couldn't read a house photo (%s: %s); the browser shrinks it instead.",
                    e.__class__.__name__, e)
        raise PhotoUnreadable(f"This computer couldn't read that photo ({e.__class__.__name__}).", 415) from None


# EXIF orientation -> how to turn the picture upright
_TURNS = {2: "FLIP_LEFT_RIGHT", 3: "ROTATE_180", 4: "FLIP_TOP_BOTTOM", 5: "TRANSPOSE",
          6: "ROTATE_270", 7: "TRANSVERSE", 8: "ROTATE_90"}


def _upright(im):
    """Turn a photo upright from its EXIF orientation (4.4.5). Pillow's
    exif_transpose also rewrites the rest of the EXIF, and a camera's damaged
    value there (a resolution of 0/0) crashed it on a user's photo; the app
    saves the photo without EXIF anyway, so only the turn is needed."""
    from PIL import Image
    try:
        o = im.getexif().get(0x0112)
    except Exception:            # unreadable EXIF: leave the picture as it is
        return im
    turn = _TURNS.get(o)
    if turn is None:
        return im
    return im.transpose(getattr(Image.Transpose, turn))
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
SENSITIVE = {"/api/credentials", "/api/webhook", "/api/port", "/api/autostart", "/api/awake", "/api/local_login",
             "/api/users", "/api/users/delete", "/api/session_policy",
             "/api/ai/settings",      # a paid key: swapping or removing it needs the password (3.18.2)
             "/api/update/install", "/api/update/rollback", "/api/update/auto",   # 4.15: replacing the program
             "/api/tokens", "/api/tokens/revoke", "/api/backup/encrypted", "/api/backup/restore"}   # 4.17
REAUTH_SECONDS = 300

# Roles (3.4). Administrators can do everything. Editors design patterns,
# schedules and the house map and control the lights, but can't change the
# household's location, controllers, weather or safety-net settings, accounts,
# or anything on the admin list. Viewers can look but not change anything.
EDITOR_POSTS = {"/api/action", "/api/settings", "/api/photo", "/api/photo/upload", "/api/photo/delete", "/api/device/save_effect", "/api/import",
                "/api/sound/upload", "/api/sound/delete", "/api/sound/test",     # 4.9: celebration sounds
                "/api/automation/try", "/api/automation/check",                  # 4.11: automations
                "/api/presence",                                                 # 4.18: who's home, set by hand
                "/api/fade/try",                                                 # 4.19: try a fade
                "/api/sync",                                                     # 4.21: controllers together
                "/api/share/show", "/api/share/automation", "/api/share/install",  # 4.21: sharing more
                "/api/studio/compose", "/api/studio/describe", "/api/studio/play", "/api/studio/stop",
                "/api/studio/save",                                              # 4.20: Studio
                "/api/textpattern", "/api/mood", "/api/holidays/refresh", "/api/share", "/api/share/open",
                "/api/musiclink",    # 4.1: a music show from this computer (address, finding and tests: Administrators)
                "/api/musiczones",   # 4.13: zones that follow the music
                "/api/health/check"} # 4.15: check the controllers now
# Viewers may make a share code: it only reads patterns (3.19.1).
VIEWER_POSTS = {"/api/share"}
MOOD_LEVELS = ("calm", "lively", "party")
MOOD_MINUTES = 3     # a mood pattern ends by itself this long after the last word from the listening page
AI_PER_MINUTE, AI_PER_DAY = 6, 100   # AI pattern ideas cost money on the owner's key (3.18.2)
ADMIN_GETS = {"/api/users", "/api/safety/backup", "/api/backups", "/api/backups/patterns", "/api/alerts", "/api/local",
              "/api/audit", "/api/tokens"}                       # 4.17
# Household settings only an Administrator may change. "community" is the
# address the app computer fetches the pattern library from: anyone who could
# set it could make this computer request any address on the home network.
HOUSEHOLD_KEYS = ("location", "safety", "weather", "setup_done", "color", "community", "ai", "lan")   # ai: the AI model, which spends the owner's money (3.18.2)
# This home's own, never in an export and never taken from someone's file:
# away mode reveals when nobody's home, and usage is this home's equipment and
# electric rate (3.15.1).
PRIVATE_KEYS = ("away", "usage", "ai", "lan", "paused", "dates", "presence")   # 4.18: birthdays and who lives here stay home   # ai (3.18.2): which paid model to call is this home's choice
ROLE_NAMES = {"admin": "Administrator", "editor": "Editor", "viewer": "Viewer"}
# A browser on the app computer itself (when it doesn't require a password).
LOCAL_USER = {"id": None, "username": "this computer", "role": "admin", "disabled": False, "local": True}

# 4.17: the audit log. Not logged: what only looks or streams (many times a second).
AUDIT_SKIP = {"/api/mood", "/api/musiclink", "/api/musiczones", "/api/rulecheck", "/api/automation/check", "/api/geocode",
              "/api/textpattern", "/api/share/open", "/api/lan_check", "/api/local/identify", "/api/health/check",
              "/api/update/check", "/api/sound/test", "/api/sound/clip", "/api/warnings/dismiss", "/api/local",
              "/api/conflicts", "/api/upcoming", "/api/house/tonight", "/api/catalog", "/api/status", "/api/session",
              "/api/devices", "/api/history", "/api/photos", "/api/backups", "/api/backups/patterns", "/api/export",
              "/api/runtime", "/api/timezones", "/api/tzinfo", "/api/health", "/api/triggers", "/api/hook/status",
              "/api/audit", "/api/studio/compose", "/api/studio/describe"}
# Sent many times while a slider moves or a pattern is edited: not each one
AUDIT_QUIET_ACTIONS = {"levels", "end_preview", "try"}
AUDIT_NAMES = {"/api/settings": "Changed settings", "/api/import": "Imported settings", "/api/history/restore": "Restored an earlier version",
               "/api/users": "Added or changed an account", "/api/users/delete": "Deleted an account", "/api/password": "Changed a password",
               "/api/credentials": "Changed the Trimlight account details", "/api/webhook": "Changed the webhook link",
               "/api/quit": "Quit EaveLuxOS", "/api/update/install": "Installed an update", "/api/update/rollback": "Went back a version",
               "/api/tokens": "Created an API token", "/api/tokens/revoke": "Revoked an API token",
               "/api/backup/encrypted": "Downloaded an encrypted backup", "/api/backup/restore": "Restored an encrypted backup",
               "/api/local/delete": "Deleted patterns on a controller", "/api/local/effect": "Set a pattern's effect on a controller", "/api/backups/restore": "Put patterns back on a controller",
               "/api/local/ports": "Changed a controller's ports", "/api/sessions/end_all": "Signed out everywhere",
               "/api/presence": "Marked someone home or away", "/api/weather/looks": "Added the weather looks",
               "/api/studio/play": "Played a Studio show", "/api/studio/save": "Saved a Studio show",
               "/api/sync": "Started the controllers together", "/api/share/install": "Added from a share code"}
# 4.17: never with an API token, whatever its role: accounts, tokens and the app itself
TOKEN_NEVER = {"/api/users", "/api/users/delete", "/api/password", "/api/tokens", "/api/tokens/revoke", "/api/quit",
               "/api/update/install", "/api/update/rollback", "/api/backup/encrypted", "/api/backup/restore",
               "/api/sessions/end_all", "/api/session_policy", "/api/import", "/api/history/restore"}
_AUDIT_KEYS = ("action", "effect", "on", "device", "name", "username", "role", "id", "mode", "file", "team", "side",
               "address", "key", "ids", "minutes", "seconds", "version", "person", "state")


_SENT = object()      # a GET answered by itself (a file download)


def _audit_detail(path, b, before) -> str:
    """A short, safe summary of a change: never a password, secret or token."""
    if path == "/api/settings" and isinstance(before, dict) and isinstance(b, dict):
        keys = sorted(k for k in set(b) | set(before) if not k.startswith("_") and _canon(b.get(k)) != _canon(before.get(k)))
        return ("Changed: " + ", ".join(keys)) if keys else "No change"
    if not isinstance(b, dict):
        return ""
    parts = []
    for k in _AUDIT_KEYS:
        v = b.get(k)
        if v is None or v == "":
            continue
        if isinstance(v, (list, dict)):
            v = json.dumps(v, default=str)
        parts.append(f"{k}: {str(v)[:80]}")
    return ", ".join(parts)[:400]
_UNSET = object()


def _trust_page(ca, secure_url: str) -> str:
    """4.18.2: the one page sent over plain http when HTTPS is on: how a
    phone trusts this app's certificate. No script, no sign-in, nothing
    private: the root certificate is public."""
    import html as _h
    u = _h.escape(secure_url, quote=True)
    if not ca:
        steps = ("<p>The app computer has no mkcert root certificate to give phones. On the app computer, run "
                 "<code>mkcert -CAROOT</code> and copy <b>rootCA.pem</b> (never rootCA-key.pem) into EaveLuxOS's "
                 "<code>tls</code> folder, then reload this page.</p>")
    else:
        fp = ca.get("sha256", "")
        fp = ":".join(fp[i:i + 2] for i in range(0, len(fp), 2))
        steps = f"""<p><a class="b" href="/ca.crt">1. Download the certificate</a></p>
<p class="s">Fingerprint (SHA-256), the same as on the app computer's Set up a phone page:<br><code>{_h.escape(fp)}</code></p>
<h2>iPhone or iPad</h2><ol><li>Tap <b>Allow</b>: it says <b>Profile Downloaded</b>.</li>
<li>Open the <b>Settings</b> app: <b>General</b>, <b>VPN &amp; Device Management</b>, the <b>mkcert</b> profile, <b>Install</b>.</li>
<li>Then <b>General</b>, <b>About</b>, <b>Certificate Trust Settings</b>: turn on <b>mkcert</b>.</li></ol>
<h2>Android phone or tablet</h2><ol><li>Open the <b>Settings</b> app and search for <b>CA certificate</b>.</li>
<li>Tap it, <b>Install anyway</b>, and choose <b>EaveLuxOS-root.crt</b> from Downloads.</li></ol>"""
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>EaveLuxOS: trust this app</title><style>body{{font:16px/1.5 system-ui,sans-serif;margin:0 auto;max-width:34em;padding:16px;color:#1d2433;background:#f6f7fb}}
code{{word-break:break-all;font-size:.85em}}.b{{display:block;text-align:center;padding:12px;border-radius:10px;background:#a65c06;color:#fff;font-weight:600;text-decoration:none}}
.s{{color:#5b6478;font-size:.9em}}h2{{font-size:1.05em;margin-top:1.4em}}</style></head><body>
<h1 style="font-size:1.3em">Set up this phone for EaveLuxOS</h1>
<p>This app uses a secure (https) address with its own certificate. Trust it once on this phone, then open the app.</p>
{steps}
<p><a class="b" href="{u}">2. Open EaveLuxOS (secure)</a></p>
<p class="s">Then sign in and follow the rest of <b>Set up this phone</b>: the home-screen icon and, if you like, who's home.</p>
</body></html>"""


def ssl_pem_to_der(pem: bytes) -> bytes:
    import ssl
    try:
        return ssl.PEM_cert_to_DER_cert(pem.decode("ascii", "replace"))
    except (ValueError, UnicodeError):
        return b""


def _signed_by(cert_path, ca_pem: bytes) -> bool:
    """Is this app's HTTPS certificate issued by this root? (Another mkcert
    root on the computer would be no use to a phone.) Without the
    cryptography package it can't tell, and says yes."""
    try:
        from cryptography import x509
    except ImportError:              # pragma: no cover
        return True
    try:
        ca = x509.load_pem_x509_certificate(ca_pem)
        leaf = x509.load_pem_x509_certificate(Path(cert_path).read_bytes())
        if leaf.issuer != ca.subject:
            return False
        from cryptography.hazmat.primitives.asymmetric import ec, padding
        pub = ca.public_key()
        args = (ec.ECDSA(leaf.signature_hash_algorithm),) if isinstance(pub, ec.EllipticCurvePublicKey) \
            else (padding.PKCS1v15(), leaf.signature_hash_algorithm)
        pub.verify(leaf.signature, leaf.tbs_certificate_bytes, *args)
        return True
    except Exception:
        return False


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


_lan_cache: tuple[float, list] = (0.0, [])
NAME_WAIT = 1.0     # seconds to wait for this computer's own name to be looked up (4.7.4)
_name_ips: list = []           # what the last finished lookup found
_name_thread = None
_name_lock = threading.Lock()


def _look_up_own_name():
    global _name_ips
    try:
        found = [info[4][0] for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)]
    except (OSError, UnicodeError):
        found = []
    _name_ips = found


def lan_addresses() -> list[str]:
    """This computer's home-network addresses, the likeliest first: the one its
    internet traffic leaves from. A VPN or virtual adapter (Hyper-V, WSL,
    VirtualBox) can own another private address, so others follow, up to 4.
    Kept for a minute: looking up this computer's own name can take seconds
    when the name server is slow, and Settings asks on every visit."""
    global _lan_cache
    if IN_CONTAINER:
        return []   # the container's own address isn't the one phones use
    if time.time() - _lan_cache[0] < 60:
        return list(_lan_cache[1])
    out = _lan_addresses()
    _lan_cache = (time.time(), out)
    return list(out)


def _lan_addresses() -> list[str]:
    found: list[str] = []

    def add(ip):
        if ip and not ip.startswith(("127.", "169.254.", "0.")) and ip not in found:
            found.append(ip)
    # Which address would traffic to these leave from? (No packet is sent.)
    for target in ("8.8.8.8", "10.255.255.255", "192.168.255.255", "172.31.255.255"):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect((target, 1))
                add(s.getsockname()[0])
        except OSError:
            pass
    # 4.7.4: looking up this computer's own name waits on the network. On a
    # Mac whose name the network doesn't know it can take half a minute, and
    # Setup, sign-in and Phones and tablets waited with it (GitHub's first Mac
    # test run timed out on them). It's asked in the background, a second at
    # most is waited, one lookup runs at a time, and an answer that comes
    # late is used next time (review #1).
    global _name_thread
    with _name_lock:
        if _name_thread is None or not _name_thread.is_alive():
            _name_thread = threading.Thread(target=_look_up_own_name, daemon=True, name="own-name")
            _name_thread.start()
        t = _name_thread
    t.join(NAME_WAIT)
    for ip in list(_name_ips):
        add(ip)
    private = [ip for ip in found if ipaddress.ip_address(ip).is_private]
    return (private or found)[:4]


class App:
    def __init__(self, base: Path, start: bool = True):
        self.base = base
        self.started = start
        self.store = Store(base)
        self.safety = SafetyNet(self.store.dir)
        lanlink.DUMP_DIR = self.store.dir      # unreadable messages from the controller are kept (4.3.10)
        self.updates = updates.UpdateChecker(self.store.dir)   # "a new version is out"
        self.awake = keepawake.KeepAwake(self.store.dir)        # no sleeping while the schedule runs (4.4.4)
        self.player = sound.Player()                            # celebration sounds (4.9)
        self.alerts = alerts.Alerts(self.store.dir, probe=self.alert_probe)   # phone alerts (ntfy)
        self.gameday = gameday.GameDays(self.store.dir, on_change=self.rebuild)  # game-day lights
        self.country = holidays.CountryHolidays(self.store.dir, on_change=self.rebuild)  # public holidays (3.19)
        self._country_checked = {}                                               # code -> last "Check now" (3.19.1)
        self.scores = scores.ScoreWatch(self.on_score, on_game=self.on_game)     # score celebrations (3.16), automations (4.11)
        self.autos = automations.Engine(self)                                   # When / If / Then (4.11)
        self.presence = presence.Presence(self.store.dir)                       # who's home (4.18)
        self._presence_lock = threading.Lock()
        self.ai_fetch = None                                                     # tests replace the AI call (3.18)
        self.ai_calls = []                                                       # times of AI calls, for the limits (3.18.2)
        self.mood_state = None                                                   # mood follow: {"level", "key", "at"}
        self.lanshow = lanlink.Streamer(on_end=self._musiclink_ended)          # music from this computer (4.1)
        from . import health as _health
        from . import api as _api
        self.health = _health.Health(self.store.dir)            # 4.15: how each controller has been answering
        _api.RECORDER = self.health.record
        self.zoneshows = {}           # 4.13: a controller id -> its musicsync.ZoneStreamer while zones follow the music
        self.lan_seen = {}                  # address -> {"ok", "at", "checking", "gen"}: answering there? (4.1.2; 4.5: each address)
        self._acct = []                     # the account's controllers, from the last listing here (4.5)
        self._acct_tried = -1e9             # when they were last asked for
        self._acct_lock = threading.Lock()
        self._ports_set = {}                # device -> {port: (start, end)} last set over the home network (4.5.1)
        self.lan_lock = threading.Lock()     # guards lan_seen (4.1.4)
        self._resync_at = None               # the last Resync with Trimlight's cloud (4.4.1)
        self.local_busy = threading.Lock()   # one local-mode job at a time (4.3.1)
        self.lan_io = threading.Lock()       # one connection to the controller at a time (4.3.6)
        self._local_seen = (0.0, None, None)  # the last read (time, state, address), shared by panels opened together
        self._port_base = {}         # controller id -> 0 or 1 (how it numbers its ports)
        self._port_write_base = {}   # controller id -> 0 or 1 when the cloud takes other numbers than it shows (4.0.3)
        self._bulbs = None           # last bulb count read from the controller (zones without a House map total)
        self.lock = threading.RLock()
        self.ctrl: Controller | None = None
        self.cfg = None
        self.problem = None          # why the scheduler isn't running yet
        self.problem_is_setup = True
        self.thread = None
        self.fails: dict[str, list] = {}
        self.fails_lock = threading.Lock()
        self.reauth = _Reauth()              # session hash -> password confirmed until
        self.community = community.Library()  # Patterns › Community (fetched on demand)
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
                cfg = build_config(self.store.settings, self.store.secrets, gamedates=self.gameday.dates(),
                                   country_dates=self.country_dates())
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
                self.ctrl = Controller(cfg, api, safety=self.safety, data_dir=self.store.dir)
                self.ctrl.lan = localmode.Commands(        # 4.4: on/off and saved patterns over the home network
                    enabled=lambda: bool((self.store.settings.get("lan") or {}).get("commands")),
                    host=self._lan_address, io=self.lan_io,      # 4.5: each controller at its own address
                    blocked=lambda: self.lanshow.running() or self.local_busy.locked(), now=self.controller_now)
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
        self.awake.apply()
        # Background services that reach the internet. EAVELUXOS_BACKGROUND=0
        # turns them all off (the tests do); EAVELUXOS_UPDATE_CHECK=0 only the
        # GitHub version check (3.15.1: they used to share that one switch).
        if os.environ.get("EAVELUXOS_BACKGROUND") != "0":
            if os.environ.get("EAVELUXOS_UPDATE_CHECK") != "0":
                self.updates.start()

                def auto_updates():                # 4.15: install by themselves, when chosen
                    while not self.updates.stop.wait(600):
                        self.auto_update_step()
                threading.Thread(target=auto_updates, daemon=True, name="auto-update").start()
            self.alerts.start()
            self.gameday.start(self.game_teams, lambda: self.cfg.loc.tz if self.cfg else timezone.utc)
            self.country.start(self.country_code)
            self.scores.start(lambda: {**self.cfg.watch, **self.cfg.celebrate} if self.cfg else {}, self.gameday.dates,
                              lambda: self.cfg.loc.now() if self.cfg else datetime.now())
            self.autos.start()

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
        self._validate_scenes(data.get("effects"))
        self._validate_music_zones(data.get("music_zones"))
        q = data.get("quick")
        if q is not None:     # 4.14: Quick's buttons
            if not isinstance(q, list) or len(q) > 12:
                raise ApiError("Quick holds up to 12 buttons.")
            for x in q:
                ok = isinstance(x, dict) and (
                    (x.get("type") in ("on", "off", "resume", "flash") and set(x) == {"type"})
                    or (x.get("type") == "pattern" and set(x) == {"type", "key"} and isinstance(x["key"], str) and 1 <= len(x["key"]) <= 80)
                    or (x.get("type") == "auto" and set(x) == {"type", "id"} and isinstance(x["id"], str) and 1 <= len(x["id"]) <= 40))
                if not ok:
                    raise ApiError("A Quick button is malformed.")
        for f in ("unused_ports", "ports_set"):
            up = (data.get("service") or {}).get(f)
            if up is not None and not (isinstance(up, dict) and all(
                    isinstance(v, list) and len(v) <= 4 and all(isinstance(i, int) and not isinstance(i, bool) and 0 <= i <= 3 for i in v)
                    for v in up.values())):
                raise ApiError("The list of ports that aren't connected is malformed.")
        md = data.get("mood")
        if md is not None:
            effs = data.get("effects") or {}
            if not isinstance(md, dict) or set(md) - set(MOOD_LEVELS) or any(
                    v is not None and v not in effs for v in md.values()):
                raise ApiError("Mood follow: choose one of your patterns for calm, lively and party music.")
        ai = data.get("ai")
        lan = data.get("lan")
        if lan is not None:
            devs = lan.get("devices", {}) if isinstance(lan, dict) else None
            if not (isinstance(lan, dict) and set(lan) <= {"address", "commands", "devices", "timer_on_quit"}
                    and isinstance(lan.get("address", ""), str) and isinstance(lan.get("commands", False), bool)
                    and isinstance(lan.get("timer_on_quit", False), bool)
                    and isinstance(devs, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in devs.items())):
                raise ApiError("The controller's local address is malformed.")
            for a in [lan.get("address")] + list(devs.values()):
                if a:
                    try:
                        lanlink.check_address(a)
                    except lanlink.LinkError as e:
                        raise ApiError(str(e)) from None
            if len(set(devs.values())) != len(devs):
                raise ApiError("Two controllers can't have the same home-network address.")
        if ai is not None and not (isinstance(ai, dict) and set(ai) <= {"model"} and (
                ai.get("model") is None or (isinstance(ai["model"], str) and re.fullmatch(r"[a-z0-9][a-z0-9.\-]{2,63}", ai["model"])))):
            raise ApiError("AI pattern ideas: a model name looks like claude-haiku-5-5.")
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
    def _validate_scenes(effects):
        """A scene's groups (3.17) are kept so it can be edited on the House
        map; a malformed one (from an imported file, say) would break that
        screen, so it's refused here (3.17.1)."""
        if not isinstance(effects, dict):
            return
        for k, e in effects.items():
            sc = e.get("scene") if isinstance(e, dict) else None
            if sc is None:
                continue
            groups = sc.get("groups") if isinstance(sc, dict) else None
            ok = isinstance(groups, list) and 1 <= len(groups) <= 14 and set(sc) == {"groups"}
            total = 0
            for g in groups if ok else []:
                b = g.get("bulbs") if isinstance(g, dict) else None
                ok = (isinstance(g, dict) and set(g) <= {"color", "level", "bulbs"}
                      and isinstance(g.get("color"), str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", g["color"]) is not None
                      and isinstance(g.get("level", 100), int) and not isinstance(g.get("level", 100), bool)
                      and 1 <= g.get("level", 100) <= 100
                      and isinstance(b, list) and all(isinstance(n, int) and not isinstance(n, bool) and 1 <= n <= 10000 for n in b))
                if not ok:
                    break
                total += len(b)
            if not ok or total > 10000:
                raise ApiError(f"The scene \u201c{e.get('label', k)}\u201d is malformed. Rebuild it on the House tab.")

    @staticmethod
    def _validate_music_zones(mz):
        """4.13: which zone follows what in a music show from this computer."""
        if mz is None:
            return
        hexc = re.compile(r"#[0-9A-Fa-f]{6}")
        if not isinstance(mz, dict) or set(mz) - {"maps", "base", "tested"}:
            raise ApiError("The music zones settings are malformed.")
        maps = mz.get("maps", [])
        if not isinstance(maps, list) or len(maps) > 60:
            raise ApiError("Up to 60 zones can follow the music.")
        for m in maps:
            if not (isinstance(m, dict) and isinstance(m.get("zone"), str) and 1 <= len(m["zone"]) <= 60
                    and m.get("follows") in ("bass", "mid", "treble", "beat", "off") and m.get("shows") in ("glow", "meter")
                    and isinstance(m.get("color"), str) and hexc.fullmatch(m["color"])
                    and (m.get("device") is None or (isinstance(m["device"], str) and 1 <= len(m["device"]) <= 80))
                    and not set(m) - {"zone", "device", "follows", "shows", "color"}):
                raise ApiError("A zone's music choice is malformed.")
        if mz.get("base") is not None and not (isinstance(mz["base"], str) and hexc.fullmatch(mz["base"])):
            raise ApiError("The color for the rest is like #000000.")
        t = mz.get("tested", {})
        if not isinstance(t, dict) or len(t) > 20 or not all(isinstance(k, str) and isinstance(v, dict) for k, v in t.items()):
            raise ApiError("The speed test results are malformed.")

    @staticmethod
    def _validate_map(m):
        if m is None:
            return

        def device_ok(x):
            # 4.10: a side, landmark or zone can be one controller's
            d = x.get("device") if isinstance(x, dict) else None
            return d is None or (isinstance(d, str) and 1 <= len(d) <= 80)
        if not isinstance(m, dict):
            raise ApiError("Map data is malformed.")
        tb = m.get("total_bulbs")
        if tb is not None and not (isinstance(tb, int) and 1 <= tb <= 10000):
            raise ApiError("Total bulbs must be 1-10000.")
        sides = m.get("sides", []) or []
        if not isinstance(sides, list) or len(sides) > 80:
            raise ApiError("Use at most 80 elevations and versions.")
        sid = re.compile(r"[a-z0-9_-]{1,40}")
        seen = set()
        for side in sides:
            if not (isinstance(side, dict) and sid.fullmatch(str(side.get("id", "")))
                    and 1 <= len(str(side.get("name", ""))) <= 30) or side["id"] in seen:
                raise ApiError("A house side has an invalid id or name.")
            seen.add(side["id"])
            if not device_ok(side):
                raise ApiError("A house side names an invalid controller.")
            # 4.12: elevations: a kind; versions of one (day and night photos,
            # before and after) are sides of their own that name the one
            # they're a version of ("of"); "use" is the version the whole-house
            # view and flat diagram show; "vname" names the first version.
            if side.get("kind") is not None and side["kind"] not in ("front", "side", "rear", "other"):
                raise ApiError("An elevation is front, side, rear or other.")
            for k in ("of", "use"):
                if side.get(k) is not None and not sid.fullmatch(str(side[k])):
                    raise ApiError("A version of an elevation is malformed.")
            if side.get("vname") is not None and not 1 <= len(str(side["vname"])) <= 30:
                raise ApiError("A version name is 1 to 30 characters.")
            if set(side) - {"id", "name", "device", "kind", "of", "use", "vname"}:
                raise ApiError("A house side has unknown fields.")
        by_id = {x["id"]: x for x in sides}
        for side in sides:
            if side.get("of") is not None and (side["of"] == side["id"] or side["of"] not in by_id or by_id[side["of"]].get("of")):
                raise ApiError("A version must belong to an elevation, not to another version.")
            if side.get("use") is not None and side["use"] != side["id"] and by_id.get(side["use"], {}).get("of") != side["id"]:
                raise ApiError("An elevation shows one of its own versions.")
        for lm in m.get("landmarks", []) or []:
            if not (isinstance(lm, dict) and isinstance(lm.get("bulb"), int) and 1 <= lm["bulb"] <= 10000
                    and 1 <= len(str(lm.get("name", "")).strip()) <= 60):
                raise ApiError("Each landmark needs a name (up to 60 characters) and a bulb number.")
            if not device_ok(lm):
                raise ApiError("A landmark names an invalid controller.")
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
                    bl = ln.get("bulbs")
                    if bl is not None and not (isinstance(bl, dict) and set(bl) == {"from", "to"} and all(
                            isinstance(bl[k], int) and not isinstance(bl[k], bool) and 1 <= bl[k] <= 10000 for k in ("from", "to"))):
                        raise ApiError("A roofline section's bulbs need a first and last bulb number (1-10000).")
                    pins = ln.get("pins", [])
                    # 4.12: bulbs dragged to where they sit: [bulb, x%, y%], one each
                    if not (isinstance(pins, list) and len(pins) <= 200 and all(
                            isinstance(p, list) and len(p) == 3 and isinstance(p[0], int) and not isinstance(p[0], bool)
                            and 1 <= p[0] <= 10000 and all(isinstance(v, (int, float)) and not isinstance(v, bool)
                                                           and 0 <= v <= 100 for v in p[1:]) for p in pins)
                            and len({p[0] for p in pins}) == len(pins)):
                        raise ApiError("A roofline section's pinned bulbs are malformed.")
                    extra = set(ln) - {"id", "kind", "points", "wire", "bulbs", "pins"}
                    if extra:
                        raise ApiError("A roofline section has unknown fields.")
        names = set()
        for z in m.get("zones", []) or []:
            if not (isinstance(z, dict) and isinstance(z.get("start"), int) and isinstance(z.get("end"), int)
                    and 1 <= z["start"] <= z["end"] <= 10000 and 1 <= len(str(z.get("name", "")).strip()) <= 60):
                raise ApiError("Each zone needs a name and a first and last bulb (first not after last).")
            if not device_ok(z):
                raise ApiError("A zone names an invalid controller.")
            if not isinstance(z.get("reverse", False), bool):     # 4.12: runs from its last bulb to its first
                raise ApiError("A zone's direction is malformed.")
            # 4.10: the same name may be used once for each controller
            k = (z["name"].strip().lower(), z.get("device"))
            if k in names:
                raise ApiError(f"Two zones are named \u201c{z['name']}\u201d.")
            names.add(k)

    def save_photo(self, f: Path, jpeg: bytes):
        f.parent.mkdir(exist_ok=True)
        tmp = f.with_name(f".{f.name}.{os.urandom(4).hex()}.tmp")
        tmp.write_bytes(jpeg)
        os.replace(tmp, f)       # never a half-written photo for a reader

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
        kw = {"cwd": str(self.base), "stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
              "env": autostart.child_env()}     # 4.16.3: its own unpacked files, not this copy's
        if os.name == "nt":
            kw["creationflags"] = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        else:
            kw["start_new_session"] = True
        proc = None
        try:
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
               "plan": [], "halted": self.safety.halted, "held": self.safety.held(), "paused": safety.PAUSED}
        if self.cfg:
            entries, _ = self.safety.plan(self.cfg, self.cfg.loc.now(), self.clock_offset())
            out["plan"] = [{"date": f"{e['month']:02d}-{e['day']:02d}", "on": "%02d:%02d" % tuple(e["start"]),
                            "off": "%02d:%02d" % tuple(e["end"]), "pattern": e["label"], "rule": e["rule"]} for e in entries]
        return out

    def save_settings(self, data: dict, expect_rev=None):
        if not isinstance(data, dict):
            raise ApiError("Settings must be an object.")
        if isinstance(data.get("music_zones"), dict):
            # 4.13: speed test results come only from the test, never from a page
            data["music_zones"]["tested"] = copy.deepcopy((self.store.settings.get("music_zones") or {}).get("tested") or {})
        self.validate(data)
        teams_before = self._team_keys()
        try:
            rev = self.store.save_settings(data, expect_rev)
        except Conflict:
            raise ApiError("These settings were changed on another device. Reloaded the latest; please make your change again.", 409)
        self.rebuild()
        if self._team_keys() - teams_before:
            self.gameday.next_at = 0      # a team was added: fetch its game dates soon (not on every save)
        return rev

    def _team_keys(self) -> set:
        return {gameday.team_key(t["league"], t["team"]) for t in self.game_teams()}

    def game_teams(self) -> list[dict]:
        """Teams whose schedules are checked: every team while game-night
        colors are on, and teams with celebrations while those are on (4.3.5:
        two switches; celebrations need the game days too)."""
        gd = self.store.settings.get("gameday") or {}
        if not isinstance(gd, dict):
            return []
        lights, party = bool(gd.get("enabled")), gameday.celebrations_on(gd)
        wins = any(isinstance(t, dict) and t.get("win_effect") for t in gd.get("teams") or [])   # 4.21
        if not (lights or party or wins):
            return []
        out = []
        for t in gd.get("teams") or []:
            if not lights and not (isinstance(t, dict) and (t.get("celebrate") or t.get("win_effect"))):
                continue
            try:
                out.append(gameday.check_team(t))
            except gameday.GameDayError:
                pass
        return out

    def gameday_refresh_soon(self) -> dict:
        """Check schedules now, in the background: ESPN can take up to 20 s per
        team, too long to hold a web request (3.15.1). One at a time."""
        if getattr(self, "_gd_thread", None) and self._gd_thread.is_alive():
            return {**self.gameday_status(), "checking": True}

        def run():
            try:
                if self.gameday.refresh(self.game_teams(), self.cfg.loc.tz if self.cfg else timezone.utc):
                    self.rebuild()
            except Exception:
                log.exception("Game-day check failed")
        self._gd_thread = threading.Thread(target=run, daemon=True, name="gameday-now")
        self._gd_thread.start()
        return {**self.gameday_status(), "checking": True}

    # ------------------------------------------------------------ holidays (3.19)
    def country_code(self) -> str | None:
        hc = self.store.settings.get("holidays") or {}
        cc = hc.get("country") if hc.get("enabled") else None
        return cc.get("code") if isinstance(cc, dict) and isinstance(cc.get("code"), str) else None

    def country_dates(self) -> dict:
        code = self.country_code()
        return {code: self.country.dates(code)} if code else {}

    def holidays_status(self) -> dict:
        today = self.cfg.loc.now().date() if self.cfg else date.today()
        hc = self.store.settings.get("holidays") or {}
        picked = {e.get("key"): e for e in hc.get("list", []) if isinstance(e, dict)}
        code = (hc.get("country") or {}).get("code") if isinstance(hc.get("country"), dict) else None
        return {"holidays": holidays.summary(today, picked), "groups": holidays.GROUPS,
                "country": self.country.state(code) if code else None, "table_last": holidays.TABLE_LAST,
                "today": self.ctrl.holiday_today() if self.ctrl else None}

    REFRESH_GAP = 60     # seconds between "Check now" fetches (3.19.1)

    def coming_up(self) -> dict:
        """The next picked holiday and the next game day, for the one-line
        summaries of folded panels (4.0.1). Worked out on this computer."""
        today = self.cfg.loc.now().date() if self.cfg else date.today()
        out = {"holiday": None, "game": None}
        hc = self.store.settings.get("holidays") or {}
        if hc.get("enabled"):
            picked = {e.get("key"): e for e in hc.get("list", []) if isinstance(e, dict)}
            best = None
            for h in holidays.summary(today, picked, years=1):
                if h["key"] in picked and h["next"]:
                    first = h["starts"][0] if h.get("starts") else h["next"][0]
                    if best is None or first < best["date"]:
                        best = {"name": h["name"], "date": first}
            out["holiday"] = best
        gd = self.store.settings.get("gameday") or {}
        if gd.get("enabled") or gameday.celebrations_on(gd):
            for t in self.gameday.summary(self.game_teams(), today):
                if t["next"] and (out["game"] is None or t["next"][0] < out["game"]["date"]):
                    out["game"] = {"name": t["name"], "date": t["next"][0]}
        return out

    def holidays_refresh(self, code) -> dict:
        """Fetch the chosen country's public holidays now (Schedule ›
        Holidays). Only the country in settings (3.19.1: another one used to
        replace its dates), and at most once a minute."""
        if not isinstance(code, str) or not re.fullmatch(r"[A-Z]{2}", code):
            raise ApiError("Choose a country (a 2-letter code like CA).")
        if code != self.country_code():
            raise ApiError("Choose that country under Holidays first (and turn holiday lights on).", 409)
        now = time.time()
        if now - self._country_checked.get(code, 0) < self.REFRESH_GAP:
            return {**self.country.state(code), "recent": True}
        self._country_checked[code] = now
        if self.country.refresh(code):
            self.rebuild()
        st = self.country.state(code)
        if st["error"]:
            raise ApiError(st["error"], 502)
        return st

    def gameday_status(self) -> dict:
        today = self.cfg.loc.now().date() if self.cfg else date.today()
        live = self.scores.summary()
        teams = self.gameday.summary(self.game_teams(), today)
        for t in teams:
            t["live"] = live.get(t["key"])
        return {"presets": gameday.PRESETS, "leagues": {k: v[1] for k, v in gameday.LEAGUES.items()},
                "teams": teams, "points": dict(CELEBRATE_POINTS)}

    def mood(self, level, tab=None) -> dict:
        """Mood follow (3.18): the listening page (on the app computer, whose
        microphone a browser allows) reports calm / lively / party every 10
        seconds, or quiet / stop. The matching pattern is set like a pattern
        chosen by hand that ends by itself MOOD_MINUTES after the last report,
        so a closed page or a sleeping computer hands the lights back.

        3.18.2: it ranks below what the user and the house decided (see
        Controller.mood_set): a weather alert stays on top, and a pattern
        chosen by hand wins until it ends. One page listens at a time (tab:
        the page's own id), so two open pages can't flip the lights between
        them; quiet or stop ends only mood follow's own pattern."""
        c = self.ctrl
        if c is None:
            raise ApiError("Finish setup first.", 409)
        if tab is not None and (not isinstance(tab, str) or not 1 <= len(tab) <= 40):
            raise ApiError("Unknown listening page.")
        st = self.mood_state
        if st and st.get("tab") != tab and time.time() - st["at"] < MOOD_MINUTES * 60:
            if level in ("quiet", "stop"):
                return {"active": False}            # not this page's to end
            raise ApiError("Mood follow is already listening on another page. Stop it there (or close that page "
                           f"and wait {MOOD_MINUTES} minutes) first.", 409)
        if level in ("quiet", "stop"):
            self.mood_state = None
            if st and c.mood_end():
                c.note("Mood follow: " + ("the music stopped" if level == "quiet" else "stopped") + "; back on the schedule.")
            return {"active": False}
        if level not in MOOD_LEVELS:
            raise ApiError("Unknown mood.")
        key = (self.store.settings.get("mood") or {}).get(level)
        if not key or key not in c.cfg.effects:
            raise ApiError(f"Choose a pattern for {level} music on the Music tab first.")
        try:
            got = c.mood_set(key, MOOD_MINUTES)
        except ValueError as e:
            raise ApiError(str(e)) from None
        self.mood_state = {"level": level, "key": key, "at": time.time(), "tab": tab}
        if got == "manual":
            return {"active": True, "level": level, "waiting": True,
                    "pattern": "waiting: a pattern chosen by hand is on; mood follow takes over when it ends"}
        if got == "set":
            c.note(f"Mood follow: {level} music, {c.cfg.effects[key].label}")
        return {"active": True, "level": level, "pattern": c.cfg.effects[key].label}

    # ------------------------------------------------------------ music from this computer (4.1)
    def _lan_address(self, dev: str | None = None) -> str:
        """A controller's address on the home network (4.5: one per
        controller, Setup › Local mode). Without dev:
        the address music from this computer uses (the one saved under Music,
        or the only controller's). An address saved before 4.5 counts for a
        controller only when the account has just that one, so with two
        controllers it is never taken for the wrong one."""
        lan = self.store.settings.get("lan") or {}
        m = {k: v for k, v in (lan.get("devices") or {}).items() if v}
        legacy = str(lan.get("address") or "")
        if dev is None:
            return legacy or (next(iter(m.values())) if len(m) == 1 else "")
        if dev in m:
            return m[dev]
        if legacy and legacy not in m.values():
            acct = self._account(fetch=True)
            if len(acct) == 1 and acct[0]["id"] == dev:
                return legacy
        return ""

    def _account(self, fetch: bool = False) -> list[dict]:
        """Every controller on the Trimlight account ([{"id", "name"}]), as
        last listed; fetch: list them now if none are known yet (empty when
        the cloud can't be reached either)."""
        known = lambda: (self.ctrl.account if self.ctrl else None) or self._acct
        if fetch and not known():
            # One listing at a time: panels opened together wait for it rather
            # than each finding none (4.5).
            with self._acct_lock:
                if not known() and time.monotonic() - self._acct_tried > 60:   # a slow or down cloud isn't asked on every look
                    self._acct_tried = time.monotonic()
                    try:
                        self._acct = list(self.client().list_devices())
                    except Exception as e:
                        log.info("Couldn't list the controllers on this account: %s", e)
        # (the controller list fills both together, so the ones run here alone
        # stand in only before that, as in tests)
        found = (self.ctrl.account if self.ctrl else None) or self._acct or (self.ctrl.devices if self.ctrl else None)
        return [{"id": d.get("deviceId"), "name": d.get("name") or d.get("deviceId")} for d in found or []]

    def _lan_unassigned(self) -> str:
        """An address saved before 4.5 that isn't known to be any controller's
        (two or more controllers): Local mode asks which one it is."""
        lan = self.store.settings.get("lan") or {}
        legacy = str(lan.get("address") or "")
        if not legacy or legacy in (lan.get("devices") or {}).values():
            return ""
        return "" if len(self._account()) <= 1 else legacy

    def _name_of(self, dev: str) -> str:
        return next((d["name"] for d in self._account() if d["id"] == dev), None) or \
            next((d.get("name") for d in (self.ctrl.devices if self.ctrl else []) if d.get("deviceId") == dev), None) or dev

    def _our_show(self, sid: str | None = None) -> bool:
        """A show from this computer is in charge (sid: that very show)."""
        c = self.ctrl
        by = str((c.music or {}).get("by") or "") if c else ""
        return by == f"lan:{sid}" if sid else by.startswith("lan:")

    # ------------------------------------------------------------ local mode (4.3)
    def local(self, *, write: bool = True, dev: str | None = None):
        """A controller over the home network: (Local, device id). Patterns
        are saved, put back and deleted only this way since 4.3. 4.5: each
        controller at its own address; dev chooses one (needed when the
        account has more than one)."""
        if write and self.lanshow.running():
            raise ApiError("A music show from this computer is using the connection. Stop it first.", 409)
        if not self._account(fetch=True):
            # Review #7 (4.3.1): the cloud is down and no controller is known
            # yet; local mode needs to know which one it's talking to.
            raise ApiError("Couldn't list the controllers on this account. Check the internet connection and "
                           "try again.", 502)
        if dev is None:
            acct = [d["id"] for d in self._account()]
            if len(acct) != 1:
                raise ApiError("Choose a controller first: this account has more than one.", 409)
            dev = acct[0]
        elif not isinstance(dev, str) or not dev:
            raise ApiError("Choose a controller.")
        addr = self._lan_address(dev)
        if not addr:
            whose = (self._name_of(dev) + "\u2019s") if len(self._account()) > 1 else "the controller\u2019s"
            raise ApiError(f"Patterns are saved over your home network since 4.3, so this app needs {whose} address "
                           "there first: Setup \u203a Local mode.", 409)
        if write:
            self.safety.hold()        # no backup-timer writes next to these
        return localmode.Local(addr, now=self.controller_now, backup=lambda det: self.safety._backup(dev, det),
                               lock=self.ctrl.apply_lock if self.ctrl else None, busy=self.local_busy,
                               io=self.lan_io, blocked=self.lanshow.running), dev

    def controller_now(self):
        """The time the controller should hold: reading it over the home
        network sets its clock, so the Setup offset goes along, as with every
        cloud request (review #3, 4.3.1; music from this computer since 4.1)."""
        from datetime import timedelta
        return self.now() + timedelta(minutes=self.clock_offset())

    def _after_local_write(self, dev: str):
        self._local_seen = (0.0, None, None)
        """The controller changed without the cloud: forget what was read
        through it, and ask the controller to send Trimlight's cloud a fresh
        copy (a read for the cloud, not a write to the controller)."""
        if self.ctrl:
            with self.ctrl.lock:
                self.ctrl.saved = {}

        def nudge():
            try:
                self.client().resync(dev, self.now())
            except Exception as e:      # best effort, and never a traceback (the app may be closing, 4.3.4)
                log.info("Couldn't ask the controller to update Trimlight's cloud: %s", e)
        threading.Thread(target=nudge, daemon=True).start()

    def local_state(self, fresh: bool = False, dev: str | None = None) -> dict:
        loc, dev, st = self._local_read(fresh, dev)
        if st.get("effects") is None and st.get("effects_tail"):
            # 4.22.6: once per controller while running, so it's in the log to send
            seen = self.__dict__.setdefault("_fx_logged", set())
            if dev not in seen:
                seen.add(dev)
                log.info("Lightning and Snowflake: this controller's effects list couldn't be read (%s). "
                         "Details to send to the EaveLuxOS project: %s", st.get("effects_why"), st["effects_tail"])
        names = {p["id"]: p["name"] for p in st["patterns"]}
        daily = [{**t, "pattern": names.get(t["effectId"]), "repeat": lanlink.REPEAT.get(t["repetition"])}
                 for t in st.get("daily") or []] or None          # 4.6: read only
        return {"address": loc.host, "device": dev, "ports": st["ports"], "daily": daily,
                "unreadable": st.get("unreadable", 0),        # 4.9.1: slots that aren't patterns, left out
                "patterns": [{"id": p["id"], "name": p["name"], "mode": p["mode"], "speed": p["speed"],
                              "brightness": p["brightness"],
                              "colors": [[c, col] for c, col, on in p["slots"] if c and on],
                              # 4.7.1: in the cloud's layout, for Patterns › In the Trimlight app
                              "effect": localmode.cloud_effect(p),
                              # 4.22: Lightning / Snowflake (None: the list wasn't readable)
                              "extra": (None if st.get("effects") is None else
                                        next((lanlink.EFFECT_KINDS[k] for k, n in st["effects"] if n == p["id"]), ""))}
                             for p in st["patterns"]],
                "effects_readable": st.get("effects") is not None,
                "effects_why": st.get("effects_why"), "effects_tail": st.get("effects_tail"),       # 4.22.6
                # 4.22.4: numbers whose deleted pattern's effect the controller still lists
                "effects_leftover": sorted(localmode.leftover_effects(st)) if st.get("effects") is not None else []}

    def _local_read(self, fresh: bool = False, dev: str | None = None):
        """(Local, device, what the controller holds), read now or a read from
        the last 5 seconds of the same controller."""
        if self.lanshow.running():
            raise ApiError("A music show from this computer is using the connection to the controller. "
                           "Stop it to read the controller.", 409)
        loc, dev = self.local(write=False, dev=dev)
        t, st, key = self._local_seen
        if fresh or st is None or time.time() - t > 5 or key != loc.host:   # two panels opened together share one read (4.3.6)
            try:
                st = loc.read()
            except localmode.LocalError as e:
                raise ApiError(str(e), 502) from None
            self._local_seen = (time.time(), st, loc.host)    # review #3: only for this address
        return loc, dev, st

    def resync_cloud(self) -> dict:
        """Resync with Trimlight's cloud (4.4): ask each controller to send
        the cloud a fresh copy of its data, then read it back. What the
        Trimlight app's sync did, without the Trimlight app. Reads only; it
        changes nothing on the controller."""
        with self.lan_lock:
            if self._resync_at is not None and time.monotonic() - self._resync_at < 30:
                raise ApiError("Resync was just asked for; give the controller a minute.", 429)
            self._resync_at = time.monotonic()
        api = self.client()
        out = []
        for dev in self.target_devices():
            now = self.now()
            try:                        # one controller's trouble doesn't skip the others (4.4.1)
                api.resync(dev, now)
                api.get_device(dev, now, resync=False)
                out.append({"device": dev, "ok": True})
            except TrimlightError as e:
                out.append({"device": dev, "ok": False, "error": str(e)})
        good = all(r["ok"] for r in out)
        log.info("Resync with Trimlight's cloud: %s", "it reads the controller again" if good else
                 "; ".join(r.get("error", "") for r in out if not r["ok"]))
        if self.ctrl:
            self.ctrl.refresh_devices()
        return {"ok": good, "devices": out}

    def local_backup(self, dev: str | None = None) -> dict:
        """Save what the controller holds now as a backup (Local mode › Back
        up now, 4.3.6), listed under Pattern backups and downloadable."""
        loc, dev, st = self._local_read(fresh=True, dev=dev)     # review #2 (4.3.6): this very read, not a shared one
        name = self.safety._backup(dev, localmode.as_backup(st))
        log.info("Backed up the controller over the home network: %s (%d patterns)", name, len(st["patterns"]))
        return {"file": name, "patterns": len(st["patterns"])}

    def local_ports(self, ports, dev: str | None = None) -> dict:
        loc, dev = self.local(dev=dev)
        try:
            changed = loc.ports(ports)
        except localmode.LocalError as e:
            raise ApiError(str(e), 502) from None
        log.info("Ports set over the home network: %s", "; ".join(changed))
        self._after_local_write(dev)
        if self.ctrl:
            self.ctrl.refresh_devices()
        return {"ok": True, "changed": changed}

    def local_effect(self, pid, effect, dev: str | None = None) -> dict:
        """4.22: Lightning, Snowflake or none on a pattern saved on the controller."""
        if isinstance(pid, bool) or not isinstance(pid, int):
            raise ApiError("Choose a pattern.")
        kind = None if effect in (None, "", "none") else effect
        if kind is not None and kind not in lanlink.EFFECT_CODES:
            raise ApiError("The effect is Lightning, Snowflake or none.")
        loc, dev = self.local(dev=dev)
        try:
            new = loc.set_effect(pid, kind)
        except localmode.LocalError as e:
            raise ApiError(str(e), 502) from None
        log.info("Pattern %s's effect over the home network: %s.", pid, kind or "none")
        self._after_local_write(dev)
        return {"ok": True, "effects": [{"pattern": n, "effect": lanlink.EFFECT_KINDS[k]} for k, n in new]}

    def local_delete(self, pid, name, dev: str | None = None) -> dict:
        if isinstance(pid, bool) or not isinstance(pid, int) or not isinstance(name, str) or not name.strip():
            raise ApiError("Choose a pattern to delete.")
        loc, dev = self.local(dev=dev)
        try:
            loc.delete(pid, name)
        except localmode.LocalError as e:
            raise ApiError(str(e), 502) from None
        log.info("Deleted pattern %s (%r) over the home network.", pid, name)
        self._after_local_write(dev)
        return {"ok": True}

    def musiclink_status(self) -> dict:
        return {"address": self._lan_address(), **self.lanshow.status(),
                "show": bool(self.ctrl and self.ctrl.music), "patterns": list(lanlink.PATTERNS),
                "names": list(lanlink.PATTERN_NAMES), "single": list(lanlink.SINGLE_COLOR),
                "sensitivity": list(lanlink.SENSITIVITY)}

    LAN_CHECK_EVERY = 300          # seconds between "is the controller answering at its address?" checks

    def lan_home(self) -> dict:
        """For Home (4.1.2; 4.5: each controller): its address on the home
        network (Trimlight's cloud doesn't report it) and whether it answered
        there lately, as {"devices": {id: {"address", "ok"}}, "unassigned":
        an address saved before 4.5 that isn't known to be any controller's}.
        Each address is checked in the background at most every 5 minutes by
        opening and closing a connection (nothing is sent)."""
        out = {}
        for d in self._account(fetch=True):
            addr = self._lan_address(d["id"])
            if addr:
                out[d["id"]] = {"address": addr, "ok": self._answers(addr), "name": d["name"]}
        return {"devices": out, "unassigned": self._lan_unassigned() or None}

    def _answers(self, addr: str):
        """True/False/None (not known yet) for one address; starts a check
        when the last is over 5 minutes old."""
        if self.lanshow.running() and addr == self._lan_address():
            return True
        with self.lan_lock:
            seen = self.lan_seen.setdefault(addr, {"ok": None, "at": 0.0, "checking": False, "gen": 0})
            # 4.1.4: one probe at a time, and a probe's answer only counts if
            # nothing newer (Test connection) came in meanwhile.
            start = not seen["checking"] and time.time() - seen["at"] >= self.LAN_CHECK_EVERY
            if start:
                seen["checking"] = True
            gen, ok_now = seen["gen"], seen["ok"]
        if start:
            def check():
                # 4.4: waits its turn for the connection like everything else
                # (a probe next to a show may have dropped it, Nov 16, 5:45 PM).
                if not self.lan_io.acquire(blocking=False):
                    # Busy: keep what was known and check again on the next
                    # look; a connection stuck waiting on a controller that's
                    # gone isn't proof it answers (4.4.1).
                    with self.lan_lock:
                        seen["checking"] = False
                    return
                try:
                    with socket.create_connection((addr, lanlink.TCP_PORT), timeout=1.5):
                        ok = True
                except OSError:
                    ok = False
                finally:
                    self.lan_io.release()
                with self.lan_lock:
                    if seen["gen"] == gen:
                        seen.update(ok=ok, at=time.time())
                    seen["checking"] = False
            threading.Thread(target=check, daemon=True, name="lan-check").start()
        return ok_now

    def _lan_result(self, addr, ok):
        """Test connection's answer, newer than any probe still running."""
        with self.lan_lock:
            seen = self.lan_seen.setdefault(addr, {"ok": None, "at": 0.0, "checking": False, "gen": 0})
            seen.update(ok=ok, at=time.time(), gen=seen["gen"] + 1)

    def lan_recheck(self):
        with self.lan_lock:
            for seen in self.lan_seen.values():
                seen.update(at=0.0, ok=None, gen=seen["gen"] + 1)

    def local_address(self, dev, addr, force: bool = False) -> dict:
        """Administrators (4.5): one controller's address on the home network.
        With two or more controllers, the controller found there is read
        first and its ports compared with what Trimlight's cloud says this
        one has, so an address is never given to the wrong controller without
        a warning (force: saved anyway after that warning)."""
        acct = self._account()
        if not isinstance(dev, str) or (acct and dev not in [d["id"] for d in acct]):
            raise ApiError("Choose one of the controllers on this account.")
        if addr is None or (isinstance(addr, str) and not addr.strip()):
            addr = ""
        else:
            try:
                addr = lanlink.check_address(addr)
            except lanlink.LinkError as e:
                raise ApiError(str(e)) from None
        s = copy.deepcopy(self.store.settings)
        lan = dict(s.get("lan") or {})
        m = dict(lan.get("devices") or {})
        other = next((k for k, v in m.items() if v == addr and k != dev), None) if addr else None
        if other:
            raise ApiError(f"{addr} is already {self._name_of(other)}\u2019s address.", 409)
        if addr and len(acct) > 1 and not force:
            warn = self._ports_differ(dev, addr)
            if warn:
                return {"ok": False, "confirm": warn}
        if addr:
            m[dev] = addr
        else:
            m.pop(dev, None)
        lan["devices"] = m
        if lan.get("address") and len(acct) <= 1 and lan["address"] != addr and dev in m:
            lan.pop("address")          # the old single address, now this controller's own
        s["lan"] = lan
        self.store.save_settings(s)
        self.lan_recheck()
        log.info("%s's home-network address: %s", self._name_of(dev), addr or "none")
        return {"ok": True, "lan": self.lan_home()}

    def _ports_differ(self, dev, addr) -> str:
        """A warning when the controller at addr doesn't have dev's ports (as
        Trimlight's cloud knows them); "" when they match or can't be told."""
        try:
            got = self.local_identify(addr)
        except ApiError as e:
            return (f"Couldn't read a controller at {addr} to check it's {self._name_of(dev)} ({e}). "
                    "Save it anyway?")
        why = self._not_this_one(dev, addr, got["ports"])
        return f"{why} Save it as {self._name_of(dev)}\u2019s address anyway?" if why else ""

    def _not_this_one(self, dev, addr, lan_ports) -> str:
        """Why the controller at addr (with these ports, read over the home
        network) may not be dev: its ports differ from what Trimlight's cloud
        says dev has, and from what this app last set there. "" when they
        match; a note when the cloud can't be read to tell (4.5.1)."""
        here = {i: (p["start"], p["end"]) for i, p in enumerate(lan_ports)}
        if self._ports_set.get(dev) == here:
            return ""
        try:
            det = self.client().get_device(dev, self.now())
        except Exception as e:
            return (f"Couldn't check that the controller at {addr} is {self._name_of(dev)}: Trimlight\u2019s cloud "
                    f"didn't say which ports {self._name_of(dev)} has ({e}).")
        base = port_base(det.get("ports"))
        cloud = {p.get("id", 0) - base: (p.get("start"), p.get("end")) for p in det.get("ports") or []}
        if not [i for i, se in cloud.items() if se != (0, 0) and i in here and here[i] != se]:
            return ""
        fmt = lambda d: ", ".join(f"port {i + 1}: {a}-{b}" for i, (a, b) in sorted(d.items()) if (a, b) != (0, 0))
        return (f"The controller at {addr} has {fmt(here)}, but {self._name_of(dev)} has {fmt(cloud)} in "
                f"Trimlight\u2019s cloud. It may be another controller.")

    def local_discover(self, scan: bool = False) -> dict:
        """Administrators (4.15): find the controllers on the home network
        and say which is which. The finding broadcast first; with scan (or
        when nothing answers it), a knock on the controllers' port at each
        address of this computer's own network. Each controller found is read
        (its ports), and matched to the account's controllers by the ports
        Trimlight's cloud has for them."""
        found, how = [], {}
        try:
            for a in lanlink.find():
                found.append(a)
                how[a] = "answered"
        except OSError:
            pass
        if scan or not found:
            for own in lan_addresses()[:2]:
                for a in lanlink.scan(own):
                    if a not in found:
                        found.append(a)
                        how[a] = "port open"
        acct = self._account(fetch=True)
        cloud = {}
        for d in acct:
            try:
                det = self.client().get_device(d["id"], self.now(), resync=False)
                base = port_base(det.get("ports"))
                cloud[d["id"]] = {p.get("id", 0) - base: (p.get("start"), p.get("end")) for p in det.get("ports") or []
                                  if (p.get("start"), p.get("end")) != (0, 0)}
            except Exception:
                cloud[d["id"]] = None
        lan = self.store.settings.get("lan") or {}
        saved = {v: k for k, v in (lan.get("devices") or {}).items() if v}
        # 4.16.4: one controller, its address saved the original way (one
        # address for all): that's saved too, not offered again as "Use for"
        if len(acct) == 1 and lan.get("address") and lan["address"] not in saved and acct[0]["id"] not in saved.values():
            saved[lan["address"]] = acct[0]["id"]
        out = []
        for a in found[:16]:
            row = {"address": a, "how": how[a], "saved_for": saved.get(a), "match": None}
            try:
                got = self.local_identify(a)
                row.update(ports=got["ports"], patterns=got["patterns"], count=got["count"])
                here = {i: (p["start"], p["end"]) for i, p in enumerate(got["ports"])}
                fits = [dev for dev, c in cloud.items() if c and all(here.get(i) == se for i, se in c.items())]
                if len(fits) == 1:
                    row["match"] = fits[0]
                elif len(fits) > 1:
                    row["note"] = "Its ports match more than one of your controllers; use Which is this? to tell."
            except ApiError as e:
                row["error"] = str(e)
            out.append(row)
        return {"found": out, "devices": acct, "scanned": bool(scan or how and "port open" in how.values())}

    def local_identify(self, addr) -> dict:
        """Administrators (4.5): what the controller at an address holds (its
        ports and first pattern names), to tell two controllers apart."""
        try:
            addr = lanlink.check_address(addr)
        except lanlink.LinkError as e:
            raise ApiError(str(e)) from None
        if self.lanshow.running():
            raise ApiError("A music show from this computer is using the connection. Stop it first.", 409)
        loc = localmode.Local(addr, now=self.controller_now, backup=lambda det: None,
                              lock=None, busy=self.local_busy, io=self.lan_io, blocked=self.lanshow.running)
        try:
            st = loc.read()
        except localmode.LocalError as e:
            raise ApiError(str(e), 502) from None
        return {"address": addr, "ports": st["ports"],
                "patterns": [p["name"] for p in st["patterns"]][:6], "count": len(st["patterns"])}

    def musiclink_address(self, addr) -> dict:
        """Administrators: the controller's address on the home network."""
        if addr is None or (isinstance(addr, str) and not addr.strip()):
            addr = ""
        else:
            try:
                addr = lanlink.check_address(addr)
            except lanlink.LinkError as e:
                raise ApiError(str(e)) from None
        s = copy.deepcopy(self.store.settings)
        self.lan_recheck()
        lan = dict(s.get("lan") or {})              # keeps the commands setting (4.4) and each controller's (4.5)
        if addr:
            lan["address"] = addr
        else:
            lan.pop("address", None)
        if lan:
            s["lan"] = lan
        else:
            s.pop("lan", None)
        self.store.save_settings(s)
        return self.musiclink_status()

    def local_commands(self, on) -> dict:
        """Administrators: send on/off and saved patterns over the home network (4.4)."""
        if not isinstance(on, bool):
            raise ApiError("on must be true or false.")
        if on and not any(self._lan_address(d["id"]) for d in self._account(fetch=True)):
            # 4.5.1: an address saved before 4.5 that isn't any controller's yet
            # (two or more controllers) doesn't count: nothing would go there.
            raise ApiError("Enter the controller's address on your home network first"
                           + (", or choose which controller the saved one is" if self._lan_unassigned() else "")
                           + ": Setup \u203a Local mode.", 409)
        s = copy.deepcopy(self.store.settings)
        if s.get("lan") or on:
            s["lan"] = {**(s.get("lan") or {}), "commands": on}
            self.store.save_settings(s)
        log.info("Everyday commands %s.", "go over the home network when they can" if on else "go through Trimlight's cloud")
        return {"ok": True, "commands": on}

    BACKUP_SECRETS = ("client_id", "client_secret", "webhook_token", "password_hash", "local_login", "ai_key",
                      "session_idle_hours")

    def encrypted_backup(self, passphrase, photos: bool = False) -> dict:
        """Administrators (4.17): settings, secrets and accounts (and the house
        photos if asked), sealed with a passphrase (vault.py)."""
        from . import vault
        sec = {k: v for k, v in self.store.secrets.items()}
        body = {"app": "EaveLuxOS", "version": VERSION, "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "settings": copy.deepcopy(self.store.settings), "secrets": sec, "users": self.store.export_users(), "photos": {}}
        body["settings"].pop("_rev", None)
        if photos:
            d = self.store.dir / "photos"
            total = 0
            for f in sorted(d.glob("*.jpg")) if d.is_dir() else []:
                raw = f.read_bytes()
                total += len(raw)
                if total > 60 * 1024 * 1024:
                    raise ApiError("The house photos are too big for one backup. Make it without photos.")
                body["photos"][f.name] = base64.b64encode(raw).decode()
        try:
            out = vault.seal(body, passphrase)
        except vault.VaultError as e:
            raise ApiError(str(e)) from None
        log.info("Encrypted backup made (%d setting sections, %d accounts, %d photos).",
                 len(body["settings"]), len(body["users"]), len(body["photos"]))
        return out

    def restore_encrypted(self, blob, passphrase, accounts: bool = True) -> dict:
        """Administrators (4.17): put an encrypted backup back. Everything is
        replaced except where this app runs (its port and address)."""
        from . import vault
        try:
            body = vault.open_(blob, passphrase)
        except vault.VaultError as e:
            raise ApiError(str(e)) from None
        if not (isinstance(body, dict) and isinstance(body.get("settings"), dict)):
            raise ApiError("That backup has no settings in it.")
        cur = self.store.settings
        new = copy.deepcopy(body["settings"])
        for k in ("service", "_rev"):            # where this computer runs the app stays as it is
            if k in cur:
                new[k] = copy.deepcopy(cur[k])
            else:
                new.pop(k, None)
        self.save_settings(new)                   # checked like any other save
        sec = body.get("secrets") or {}
        if isinstance(sec, dict):
            self.store.save_secrets(**{k: v for k, v in sec.items() if k in self.BACKUP_SECRETS})
        n_users = 0
        if accounts and isinstance(body.get("users"), list) and body["users"]:
            try:
                self.store.replace_users(body["users"])
            except ValueError as e:
                raise ApiError(str(e)) from None
            n_users = len(body["users"])
        n_photos = 0
        ph = body.get("photos") or {}
        if isinstance(ph, dict) and ph:
            d = self.store.dir / "photos"
            d.mkdir(exist_ok=True)
            for name, b64 in ph.items():
                if not (isinstance(name, str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,80}\.jpg", name) and isinstance(b64, str)):
                    continue
                (d / name).write_bytes(base64.b64decode(b64))
                n_photos += 1
        self.rebuild(creds_changed=True)
        log.info("Encrypted backup from %s put back (%d accounts, %d photos).", body.get("created"), n_users, n_photos)
        return {"ok": True, "created": body.get("created"), "version": body.get("version"), "accounts": n_users,
                "photos": n_photos, "signed_out": bool(n_users)}

    def timer_on_quit(self, on) -> dict:
        """Administrators (4.17): when EaveLuxOS is quit, hand each controller
        to its own daily timers (Timer mode) over the home network."""
        if not isinstance(on, bool):
            raise ApiError("on must be true or false.")
        s = copy.deepcopy(self.store.settings)
        s["lan"] = {**(s.get("lan") or {}), "timer_on_quit": on}
        self.store.save_settings(s)
        return {"ok": True, "timer_on_quit": on}

    def hand_over(self) -> list:
        """4.17: on Quit (and a clean stop), when asked: each controller set
        over the home network goes to its own Timer mode, so its own two daily
        timers run the lights while EaveLuxOS is stopped. Returns the names."""
        lan = self.store.settings.get("lan") or {}
        c = self.ctrl
        if not lan.get("timer_on_quit") or c is None or c.lan is None:
            return []
        done = []
        for d in list(c.devices or []):
            try:
                if c.lan.timer_mode(d.get("deviceId")):
                    done.append(d.get("name") or d.get("deviceId"))
            except Exception:                    # never keep the app from stopping
                log.exception("Couldn't hand the lights to the controller's timers")
        if done:
            log.info("Handed the lights to the controller's own timers: %s.", ", ".join(map(str, done)))
        return done

    def musiclink_test(self, addr=None, read=False) -> dict:
        """Administrators: connect, greet and ping; with read, also set the
        controller's clock and list what it holds (the Trimlight app does
        both each time it opens)."""
        try:
            addr = lanlink.check_address(addr or self._lan_address())
        except lanlink.LinkError as e:
            raise ApiError(str(e)) from None
        if self.lanshow.running():
            raise ApiError("A music show from this computer is running. Stop it first.", 409)
        if self.local_busy.locked():
            raise ApiError("A change to the controller over the home network is running. Try again when it's done.", 409)
        self.safety.hold()      # no backup-timer writes next to local-link use (4.2.1)
        if not self.lan_io.acquire(timeout=20):
            raise ApiError("The connection to the controller is busy. Try again in a moment.", 409)
        try:
            with lanlink.Link(addr) as link:
                ms = link.ping()
                out = {"ok": True, "address": addr, "ms": round(ms)}
                if read:
                    dump = link.read_all(self.controller_now())
                    out.update(bytes=len(dump), names=lanlink.names_in(dump))
        except lanlink.LinkError as e:
            self._lan_result(addr, False)
            raise ApiError(str(e), 502) from None
        finally:
            self.lan_io.release()
        self._lan_result(addr, True)
        log.info("Local link to %s works (%s ms)%s", addr, out["ms"], " and read the controller" if read else "")
        return out

    def musiclink_find(self) -> dict:
        try:
            return {"found": lanlink.find()}
        except OSError as e:
            raise ApiError(f"Couldn't look for controllers: {e}", 502) from None

    def musiclink(self, b: dict) -> dict:
        """Editors: start, feed, adjust or stop a music show from this
        computer. The listening page sends 16 sound levels about 9 times a
        second; this app passes them to the controller over the home network
        and steps aside like any music show while it runs."""
        op, tab = b.get("op"), b.get("tab")
        if not isinstance(tab, str) or not 1 <= len(tab) <= 40:
            raise ApiError("Unknown listening page.")

        def num(k, lo, hi):
            v = b.get(k)
            if isinstance(v, bool) or not isinstance(v, int) or not lo <= v <= hi:
                raise ApiError(f"{k.capitalize()} must be a whole number from {lo} to {hi}.")
            return v
        if op == "levels":
            try:
                return {"running": self.lanshow.feed(b.get("levels"), tab)}
            except ValueError as e:
                raise ApiError(str(e)) from None
        if op == "set":
            try:
                ok = self.lanshow.adjust(tab, pattern=num("pattern", *lanlink.PATTERNS) if "pattern" in b else None,
                                           sensitivity=num("sensitivity", *lanlink.SENSITIVITY) if "sensitivity" in b else None,
                                           color=b["color"] if "color" in b else None)
            except ValueError as e:
                raise ApiError(str(e)) from None
            return {"running": ok}
        if op == "stop":
            self.lanshow.stop(tab, "stopped")
            # 4.1.4: hand the lights back here, not only when the stream has
            # wound down (which waits at most 3 s), so Stop answers after the
            # schedule is back.
            if self.ctrl is not None and self._our_show():
                self.ctrl.stop_music()
            return {"running": False}
        if op != "start":
            raise ApiError("Unknown music step.")
        c = self.ctrl
        if c is None:
            raise ApiError("Finish setup first.", 409)
        addr = self._lan_address()
        if not addr:
            raise ApiError("Enter the controller's address on your home network first (Music › Music from this computer).", 409)
        if self.local_busy.locked():
            raise ApiError("A change to the controller over the home network is running. Start the show when it's done.", 409)
        if any(z.running() for z in self.zoneshows.values()):     # 4.13
            raise ApiError("Zones are following the music. Stop that first.", 409)
        pattern, sens = num("pattern", *lanlink.PATTERNS), num("sensitivity", *lanlink.SENSITIVITY)
        try:
            color = lanlink.check_color(b.get("color", "#FF0000"))      # for the "Single Color" patterns (4.2)
        except ValueError as e:
            raise ApiError(str(e)) from None
        minutes = b.get("minutes", 0)
        if isinstance(minutes, bool) or not isinstance(minutes, int) or not 0 <= minutes <= 360:
            raise ApiError("Minutes must be from 0 (until stopped) to 360.")
        # Review #1 (4.3.6): start only when no read or change holds the
        # connection (the controller answers one at a time), and before the
        # app steps aside for the show.
        if not self.lan_io.acquire(timeout=20):
            raise ApiError("The connection to the controller is busy. Try again in a moment.", 409)
        try:
            fresh = not self.lanshow.running()
            if fresh:
                # 4.1.4: the page's button is off during another show; the server
                # says no too, or stopping this one would also end a show night.
                other = c.other_show_on(by="lan:")
                if other:
                    raise ApiError(f"{other} is on. Stop it first (Music \u203a Music show).", 409)
                sid = secrets.token_hex(4)
                try:
                    c.start_music(minutes or None, by=f"lan:{sid}")
                except ValueError as e:
                    raise ApiError(str(e), 409) from None
            else:
                sid = None
            try:
                self.lanshow.start(addr, pattern, sens, tab, wanted=(lambda: self._our_show(sid)) if sid else self._our_show,
                                   clock=self.controller_now, sid=sid, color=color)
            except (lanlink.LinkError, ValueError) as e:
                if fresh and self._our_show(sid):
                    c.stop_music()
                raise ApiError(str(e), 502 if isinstance(e, lanlink.LinkError) else 400) from None
            if fresh:
                c.note(f"Music from this computer: started ({lanlink.PATTERN_NAMES[pattern]}, sensitivity {sens}).")
        finally:
            self.lan_io.release()
        return self.musiclink_status()

    # --- 4.13: music sync 2.0, zones that follow the music (musicsync.py) -------------

    def musiczones_status(self) -> dict:
        c = self.ctrl
        mz = self.store.settings.get("music_zones") or {}
        devs = {}
        for d in (c.devices if c else []):
            dev = d["deviceId"]
            zs = self.zoneshows.get(dev)
            devs[dev] = {"name": d.get("name") or dev, "address": bool(self._lan_address(dev)),
                         "tested": (mz.get("tested") or {}).get(dev), "show": zs.status() if zs else {"running": False}}
        return {"devices": devs, "running": any(z.running() for z in self.zoneshows.values()),
                "link": self.lanshow.running()}

    def _zone_busy(self) -> str | None:
        if self.lanshow.running():
            return "A music show from this computer (the controller's music patterns) is on. Stop it first."
        if any(z.running() for z in self.zoneshows.values()):
            return "Zones are following the music already. Stop that first."
        c = self.ctrl
        other = c.other_show_on() if c else None
        return f"{other} is on. Stop it first (Music \u203a Music show)." if other else None

    def musiczones(self, b: dict) -> dict:
        """Editors: zones that follow the music. op "test" (a controller's
        speed test), "start", "frame" (the page's latest frame for each
        controller) and "stop"."""
        from . import musicsync
        op, c = b.get("op"), self.ctrl
        if c is None:
            raise ApiError("Finish setup first.", 409)
        known = {d["deviceId"]: d for d in c.devices}
        if op == "frame":
            tab, frames = b.get("tab"), b.get("frames")
            if not isinstance(frames, dict) or len(frames) > 20:
                raise ApiError("A frame for each controller.")
            out = {}
            for dev, f in frames.items():
                zs = self.zoneshows.get(dev)
                try:
                    out[dev] = bool(zs and zs.feed((f or {}).get("colors"), (f or {}).get("counts"), tab))
                except ValueError as e:
                    raise ApiError(str(e)) from None
            st = self.musiczones_status()
            return {"running": any(out.values()), "devices": {d: v["show"] for d, v in st["devices"].items()}}
        if op == "stop":
            tab = b.get("tab")
            if not isinstance(tab, str) or not 1 <= len(tab) <= 40:      # Review #3: one page's show, never any
                raise ApiError("Unknown listening page.")
            for zs in list(self.zoneshows.values()):
                zs.stop(tab, "stopped")
            if self._our_show():
                c.stop_music()
            return self.musiczones_status()
        if op == "test":
            dev = b.get("device")
            if dev not in known:
                raise ApiError("Choose one of your controllers.")
            addr = self._lan_address(dev)
            if not addr:
                raise ApiError("Enter this controller's address on your home network first (Setup \u203a Local mode).", 409)
            busy = self._zone_busy()
            if busy:
                raise ApiError(busy, 409)
            if not self.lan_io.acquire(timeout=20):
                raise ApiError("The connection to the controller is busy. Try again in a moment.", 409)
            sid = "t" + secrets.token_hex(4)
            try:
                try:
                    c.start_music(5, by=f"lan:{sid}")      # step aside while the frames go out
                except ValueError as e:
                    raise ApiError(str(e), 409) from None
                try:
                    r = musicsync.speed_test(addr, clock=self.controller_now)
                except lanlink.LinkError as e:
                    raise ApiError(f"The speed test couldn't finish: {e}", 502) from None
            finally:
                if self._our_show(sid):
                    c.stop_music()                     # the schedule's pattern again
                self.lan_io.release()
            r["at"] = c.cfg.loc.now().isoformat(timespec="minutes")
            s = copy.deepcopy(self.store.settings)
            mz = s.setdefault("music_zones", {})
            mz.setdefault("tested", {})[dev] = r
            self.validate(s)
            self.store.save_settings(s)
            c.note(f"Music zones: {known[dev].get('name') or dev} took {r['fps']} frames a second in its speed test.")
            return {**r, **self.musiczones_status()}
        if op != "start":
            raise ApiError("Unknown music step.")
        tab, devs, minutes = b.get("tab"), b.get("devices"), b.get("minutes", 0)
        if not isinstance(tab, str) or not 1 <= len(tab) <= 40:
            raise ApiError("Unknown listening page.")
        if not (isinstance(devs, list) and 1 <= len(devs) <= len(known) and all(d in known for d in devs)) or len(set(devs)) != len(devs):
            raise ApiError("Choose the controllers whose zones follow the music.")
        if isinstance(minutes, bool) or not isinstance(minutes, int) or not 0 <= minutes <= 360:
            raise ApiError("Minutes must be from 0 (until stopped) to 360.")
        tested = (self.store.settings.get("music_zones") or {}).get("tested") or {}
        for d in devs:
            if not self._lan_address(d):
                raise ApiError(f"Enter {known[d].get('name') or d}'s address on your home network first (Setup \u203a Local mode).", 409)
            if not (tested.get(d) or {}).get("fps"):
                raise ApiError(f"Run {known[d].get('name') or d}'s speed test first. It shows how many frames a second it can take.", 409)
        busy = self._zone_busy()
        if busy:
            raise ApiError(busy, 409)
        if not self.lan_io.acquire(timeout=20):
            raise ApiError("The connection to the controller is busy. Try again in a moment.", 409)
        sid = "z" + secrets.token_hex(4)
        started = []
        try:
            try:
                c.start_music(minutes or None, by=f"lan:{sid}")
            except ValueError as e:
                raise ApiError(str(e), 409) from None
            try:
                for d in devs:
                    zs = self.zoneshows.get(d) or musicsync.ZoneStreamer(on_end=lambda why, s_, dv=d: self._zones_ended(dv, why, s_))
                    self.zoneshows[d] = zs
                    zs.start(self._lan_address(d), tab, tested[d]["fps"], sid, wanted=lambda: self._our_show(sid),
                             clock=self.controller_now)
                    started.append(zs)
            except (lanlink.LinkError, ValueError) as e:
                for zs in started:
                    zs.stop(tab, "stopped")
                if self._our_show(sid):
                    c.stop_music()
                raise ApiError(str(e), 502 if isinstance(e, lanlink.LinkError) else 400) from None
        finally:
            self.lan_io.release()
        c.note("Music zones: started on " + ", ".join(known[d].get("name") or d for d in devs) + ".")
        return self.musiczones_status()

    def _zones_ended(self, dev: str, why: str, sid: str | None):
        c = self.ctrl
        if c is None:
            return
        zs = self.zoneshows.get(dev)
        text = {"stopped": "stopped", "idle": "the listening page stopped sending", "app": "the music show ended",
                "lost": f"the connection was lost ({zs.last_error if zs else ''})"}.get(why, why)
        name = next((d.get("name") for d in c.devices if d["deviceId"] == dev), dev)
        c.note(f"Music zones on {name}: {text}.")
        if why in ("idle", "lost"):            # one controller gone: end the whole show, the others too
            for other in list(self.zoneshows.values()):
                if other is not zs:
                    other.stop(None, "stopped")
        if why != "app" and self._our_show(sid) and not any(z.running() for z in self.zoneshows.values() if z is not zs):
            c.stop_music()

    def _musiclink_ended(self, why: str, sid: str | None = None):
        c = self.ctrl
        if c is None:
            return
        text = {"stopped": "stopped", "idle": "the listening page stopped sending sound",
                "lost": "the connection to the controller was lost", "app": "the music show ended"}.get(why, why)
        c.note(f"Music from this computer: {text}.")
        if why != "app" and self._our_show(sid):       # only this show: never a newer one
            c.stop_music()

    def ai_pattern(self, prompt) -> dict:
        """An AI pattern idea (3.18), limited to AI_PER_MINUTE a minute and
        AI_PER_DAY a day: every call costs money on the owner's key, and
        editors can ask (3.18.2)."""
        from . import textpattern
        now = time.time()
        with self.lock:
            calls = [t for t in self.ai_calls if now - t < 86400]
            if sum(1 for t in calls if now - t < 60) >= AI_PER_MINUTE:
                raise ApiError("That's a lot of AI ideas in a minute. Wait a moment, or use Try another (free).", 429)
            if len(calls) >= AI_PER_DAY:
                raise ApiError(f"The daily limit of {AI_PER_DAY} AI ideas is reached. Try again tomorrow, or use Try another (free).", 429)
            calls.append(now)
            self.ai_calls = calls
        model = (self.store.settings.get("ai") or {}).get("model") or textpattern.AI_MODEL
        return textpattern.ai_generate(prompt, self.store.secrets.get("ai_key"), fetch=self.ai_fetch, model=model)

    # --- 4.11: automations (automations.py) -------------------------------------

    def on_score(self, team: dict, points: int, game: dict):
        """A watched team scored: its celebration (when on), then automations."""
        if not team.get("automation_only"):
            self.celebrate(team, points, game)
        self._auto_event({"type": "score", "team": team["key"], "abbr": team["team"], "game": game, "points": points})

    def _auto_event(self, ev: dict) -> list:
        """Review #6: an automation that fails never stops the scoreboard."""
        try:
            return self.autos.event(ev)
        except Exception:
            log.exception("Automations for %s failed", ev.get("type"))
            return []

    def on_game(self, team: dict, kind: str, game: dict):
        us = game["teams"].get(team["team"])
        them = [v for k, v in game["teams"].items() if k != team["team"]]
        result = None
        if kind == "end" and us is not None and them:
            result = "win" if us > them[0] else "loss" if us < them[0] else "tie"
        if result == "win" and team.get("win_effect"):
            self.celebrate_win(team)
        self._auto_event({"type": "game_start" if kind == "start" else "game_end", "team": team["key"],
                          "abbr": team["team"], "game": game, "result": result})

    def celebrate_win(self, team: dict):
        """4.21: the team won: its win pattern for its minutes, then back to
        the schedule (only while the lights are on, if celebrations are set so)."""
        c = self.ctrl
        if c is None:
            return
        name = team.get("name") or team.get("team", "").upper()
        try:
            t = c._target(commit=False)
            if team.get("only_when_on", True) and not t.on:
                c.note(f"{name} won! No win lights: the lights are off.")
                return
            # Review #1 (4.21): a score celebration (often the winning goal's
            # own) or an automation's flash goes back to what's chosen under
            # it, so the win lights wait for it; only a weather warning, a
            # music show, a pause or the security flash keep them off
            fk = (c.flash or {}).get("kind") if t.reason == "flash" else None
            if t.reason in ("alert", "music") or t.hands_off or (t.reason == "flash" and fk not in ("score", "automation")):
                c.note(f"{name} won! No win lights: something more important is showing.")
                return
            c.manual(True, team["win_effect"], expires_min=int(team.get("win_minutes", 30)))
            c.note(f"{name} won! Win lights for {team.get('win_minutes', 30)} minutes.")
        except Exception as e:                 # the scoreboard goes on
            log.warning("Win lights for %s failed: %s", name, e)

    def _auto_zones(self, dev):
        zs = (self.ctrl.cfg.zones or []) if self.ctrl else []
        return [z for z in zs if not dev or not z.get("device") or z["device"] == dev] if dev else zs

    def auto_flash(self, x: dict, a: dict, ev: dict):
        from .triggers import flash_effect
        c = self.ctrl
        cfg, dev = c.cfg, x.get("device")
        eff = flash_effect(cfg.effects, cfg.gamma, effect=x.get("effect"), color=x.get("color"), zone=x.get("zone"),
                           zones=self._auto_zones(dev), total=self.address_space() if x.get("zone") else None)
        if dev:
            c.flash_one(dev, eff, x["seconds"])      # Review #3: then back to what it showed
        elif not c.start_flash(seconds=x["seconds"], effect=eff, label=a["name"], kind="automation"):
            raise RuntimeError("something more important is showing")

    def auto_show(self, x: dict, a: dict, ev: dict):
        c = self.ctrl
        if x.get("device"):
            c.manual_one(x["device"], True, x["effect"], expires_min=x.get("minutes"))
        else:
            c.manual(True, x["effect"], expires_min=x.get("minutes"))
        c.mark_automation(x.get("device"))

    def auto_off(self, x: dict, a: dict, ev: dict):
        c = self.ctrl
        if x.get("device"):
            c.manual_one(x["device"], False, expires_min=x["minutes"])
        else:
            c.manual(False, expires_min=x["minutes"])
        c.mark_automation(x.get("device"))

    def auto_sound(self, x: dict, a: dict, ev: dict):
        snd = self._team_sound(x["team"])
        if not snd:
            raise ValueError("that team has no sound (Schedule \u203a Game-day lights)")
        if not self._play_sound(x["team"], snd):
            raise RuntimeError("the sound couldn't be played")

    def _automation(self, aid: str) -> dict:
        if not self.ctrl:
            raise ApiError("Set up first.", 409)
        a = next((x for x in self.ctrl.cfg.automations if x["id"] == aid), None)
        if a is None:
            raise ApiError("Save the automation first.", 404)
        return a

    def automation_try(self, aid: str) -> dict:
        return {"result": self.autos.try_now(self._automation(aid))}

    def automation_check(self, aid: str) -> dict:
        a = self._automation(aid)
        rows = self.autos.check(a)
        return {"conditions": [{"text": t, "ok": ok} for t, ok in rows],
                "game_only": any(c["type"] in ("home", "away", "winning", "losing") for c in a["if"])}

    # --- sharing shows and automations (4.21) -------------------------------------
    def share_more(self, what: str, b: dict) -> dict:
        from . import marketplace
        try:
            if what == "show":
                return sharecode.encode_show(b.get("show"))
            if what == "automation":
                a = next((x for x in self.store.settings.get("automations") or [] if x.get("id") == b.get("id")), None)
                if a is None:
                    raise sharecode.ShareError("Save the automation first.")
                return sharecode.encode_automation(a, self.store.settings.get("effects") or {})
            got = sharecode.decode(b.get("code"))
            if got["kind"] == "automation":
                new, name = marketplace.install(got["automation"], got["patterns"], self.store.settings)
                self.save_settings(new)
                return {"kind": "automation", "name": name, "patterns": len(got["patterns"])}
            return got                              # a show opens in Studio; patterns as before
        except (sharecode.ShareError, marketplace.TemplateError) as e:
            raise ApiError(str(e)) from None

    # --- energy (4.21) ------------------------------------------------------------
    def patterns_fx(self) -> dict:
        """4.22.5: which patterns carry Lightning or Snowflake, for badges on
        Patterns › My patterns and In the Trimlight app.
        by_id: the controller's saved patterns (number -> effect).
        mine: this app's patterns (key -> effect) that would be shown by that
        saved pattern's number, so the effect plays (the same choice as
        Controller._apply: saved by name or number; else an exact copy, the
        same name first). Reads nothing new: the last read of the controller
        over the home network (at most 5 seconds old, else read once).
        Empty when there's no home-network address or the list isn't readable."""
        out = {"by_id": {}, "mine": {}, "known": False,
               "plays": bool(self.ctrl and self.ctrl.lan is not None)}
        try:
            _, _, st = self._local_read(False)
        except ApiError:
            return out
        if st.get("effects") is None:
            return out
        kinds = {n: lanlink.EFFECT_KINDS[k] for k, n in st["effects"]}
        have = {p["id"]: p for p in st["patterns"]}
        out["known"] = True
        out["by_id"] = {str(n): k for n, k in kinds.items() if n in have}
        if not self.ctrl:
            return out
        by_name = {p["name"].strip().lower(): p["id"] for p in st["patterns"]}
        looks = {}
        for p in st["patterns"]:
            looks.setdefault(localmode.look_key(p), []).append(p)
        for key, e in (self.ctrl.cfg.effects or {}).items():
            pid = None
            if e.kind == "saved":
                pid = e.saved_id if e.saved_id in have else by_name.get((e.saved_name or "").strip().lower())
            elif e.kind not in ("split", "builtin") and isinstance(e.payload, dict):
                lk = localmode.look_of(dict(e.payload))
                if lk is not None:
                    pid = localmode.pick_same_look(looks.get(lk) or [], e.label, st["effects"])
            if pid and kinds.get(pid):
                out["mine"][key] = kinds[pid]
        return out

    def energy_estimate(self) -> dict:
        from . import energy
        if not self.ctrl:
            raise ApiError("Set up first.", 409)
        us = self.store.settings.get("usage") or {}
        cfg = self.ctrl.cfg
        bulbs = int(us.get("bulbs") or cfg.total_bulbs or 0)
        per = float(us.get("watts_per_bulb") or energy.WATTS_PER_BULB)
        rate = us.get("rate")
        today = cfg.loc.now().date()
        st = self.ctrl.status()
        t = self.ctrl._target(commit=False)
        now_w = energy.pattern_watts(t.effect, bulbs, per, (t.levels or {}).get("brightness")) if t.on and bulbs else 0.0
        top = sorted(((energy.pattern_watts(e, bulbs, per), e.label) for e in cfg.effects.values() if e.kind != "split"),
                     reverse=True)[:5] if bulbs else []
        return {"bulbs": bulbs, "watts_per_bulb": per, "rate": rate, "now_watts": round(now_w, 1), "on": bool(st["target"]["on"]),
                "month": energy.month_estimate(cfg.schedule, today, 30, bulbs, per, rate) if bulbs else None,
                "hungriest": [{"label": lbl, "watts": round(w, 1)} for w, lbl in top]}

    # --- Studio (4.20) ------------------------------------------------------------
    def studio(self, what: str, b: dict) -> dict:
        from . import studio
        try:
            if what == "compose":
                return studio.compose(b.get("spec"))
            if what == "describe":
                return studio.from_words(b.get("text"))
            if not self.ctrl:
                raise ApiError("Set up first.", 409)
            if what == "stop":
                self.ctrl.stop_show()
                self.ctrl.resume()
                return {"ok": True}
            show = studio.check_show(b.get("show"))
            if what == "play":
                hold = b.get("hold", 5)
                if isinstance(hold, bool) or not isinstance(hold, (int, float)) or not 2 <= hold <= 60:
                    raise ValueError("Each keyframe plays 2 to 60 seconds here.")
                return self.ctrl.play_show([k["pattern"] for k in show["keyframes"]], float(hold), show["fade"])
            # save: the looks become patterns, and (if asked) a rule plays them in turn
            s = copy.deepcopy(self.store.settings)
            add, keys = studio.save_plan(show, s.get("effects") or {})
            s.setdefault("effects", {}).update(add)
            out = {"patterns": keys, "rule": None, "fade": None}
            if b.get("schedule"):
                names = {r.get("name") for r in s.get("rules") or []}
                name, n = f"Studio: {show['name']}"[:60], 2
                while name in names:
                    name, n = f"Studio: {show['name']} ({n})"[:60], n + 1
                rule = {"name": name, "on": str(b.get("on") or "sunset"), "off": str(b.get("off") or "23:00"),
                        "effect": keys if len(keys) > 1 else keys[0]}
                if len(keys) > 1:
                    rule["rotate_each"] = [k["minutes"] for k in show["keyframes"]]
                s.setdefault("rules", []).append(rule)
                out["rule"] = name
                if show["fade"] and not (s.get("transitions") or {}).get("fade_seconds"):
                    s["transitions"] = {**(s.get("transitions") or {}), "fade_seconds": show["fade"]}
                    out["fade"] = show["fade"]
            self.save_settings(s)
            return out
        except ValueError as e:
            raise ApiError(str(e)) from None

    # --- weather looks (4.19) -----------------------------------------------------
    def weather_looks(self, temperature: bool = True) -> dict:
        from . import weatherlook
        new, added = weatherlook.add_looks(self.store.settings, temperature)
        if added:
            self.save_settings(new)
        return {"added": added}

    # --- set up this phone (4.18.2) ---------------------------------------------
    def phone_ca(self) -> dict | None:
        """mkcert's root certificate, when it's the one that signed this app's
        HTTPS certificate: {"pem", "sha256", "where"}. Looked for in the tls
        folder (rootCA.pem copied there), $CAROOT, and mkcert's own folder.
        Only ever the public certificate: never rootCA-key.pem."""
        tls = self.store.dir / "tls"
        cands = [tls / "rootCA.pem"]
        if os.environ.get("CAROOT"):
            cands.append(Path(os.environ["CAROOT"]) / "rootCA.pem")
        home = Path.home()
        if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
            cands.append(Path(os.environ["LOCALAPPDATA"]) / "mkcert" / "rootCA.pem")
        cands += [home / "Library" / "Application Support" / "mkcert" / "rootCA.pem",
                  Path(os.environ.get("XDG_DATA_HOME") or home / ".local" / "share") / "mkcert" / "rootCA.pem"]
        cert = tls / "cert.pem"
        for f in cands:
            try:
                if not f.is_file() or f.stat().st_size > 16384:
                    continue
                pem = f.read_bytes()
            except OSError:
                continue
            if not pem.lstrip().startswith(b"-----BEGIN CERTIFICATE-----") or b"PRIVATE KEY" in pem:
                continue
            if not _signed_by(cert, pem):
                continue
            der = ssl_pem_to_der(pem)
            return {"pem": pem, "sha256": hashlib.sha256(der).hexdigest().upper() if der else "", "where": str(f)}
        return None

    def phone_info(self, port: int | None = None) -> dict:
        ca = self.phone_ca()
        https = getattr(self, "scheme", "http") == "https"
        port = port or int((self.store.settings.get("service") or {}).get("web_port", 8787))
        addrs = [a for a in lan_addresses() if ":" not in a]
        people = presence.check_people(self.store.settings.get("presence")) if self.store.settings.get("presence") else []
        fp = ca["sha256"] if ca else ""
        return {"https": https, "ca": bool(ca), "ca_sha256": ":".join(fp[i:i + 2] for i in range(0, len(fp), 2)),
                "addresses": addrs, "port": port, "people": people}

    # --- who's home (4.18) ----------------------------------------------------
    def presence_status(self) -> dict:
        people = self.ctrl.cfg.people if self.ctrl else presence.check_people(self.store.settings.get("presence"))
        self.presence.prune(people)          # Review #11: someone taken off the list is forgotten now
        return {"people": self.presence.summary(people), "home": sorted(self.presence.home(people))}

    def presence_set(self, person, state, via: str = "") -> dict:
        """Someone arrived or left (a phone's webhook, or by hand on the
        Who's home panel): remember it and start the automations it starts."""
        if not self.ctrl:
            raise ApiError("Finish setup first.", 409)
        people = self.ctrl.cfg.people
        state = {"arrived": "home", "arrive": "home", "left": "away", "leave": "away"}.get(str(state).lower(), str(state).lower())
        if state not in presence.STATES:
            raise ApiError('The state is "home" or "away".')
        who = self.presence.find(people, person)
        if who is None:
            raise ApiError("Add that person under Alerts › Who's home first." if people else
                           "Add the people who live here under Alerts › Who's home first.", 404)
        # Review #5 (4.18.1): one change and its automations at a time, so two
        # quick reports (arrive, then leave) can't run their automations in
        # the wrong order
        with self._presence_lock:
            settle = presence.settle_minutes(self.store.settings.get("presence")) * 60 if via == "webhook" else 0
            r = self.presence.set(people, who, state, settle)
            done = []
            if r["settling"]:
                # 4.18.2: a phone at the edge of the Wi-Fi going home, away, home
                self.ctrl.note(f"{who} {'arrived home' if state == 'home' else 'left'} again within "
                               f"{settle // 60:.0f} min: noted, no automations.")
            elif r["changed"]:
                self.ctrl.note(f"{who} {'arrived home' if state == 'home' else 'left'}{' (' + via + ')' if via else ''}.")
                ev = {"type": "arrive" if state == "home" else "leave", "person": who, "first": r["first"], "last": r["last"]}
                done = self._auto_event(ev)
        return {"ok": True, "person": who, "state": state, "changed": r["changed"], "settling": r["settling"],
                "home": r["home"], "automations": done}

    def health_status(self) -> dict:
        """4.15: each controller: what the cloud says (online, firmware), how
        its requests went (today and 14 days), and the home-network check."""
        listed = (self.ctrl.account if self.ctrl else None) or self._acct or (self.ctrl.devices if self.ctrl else None) or []
        if not listed:
            self._account(fetch=True)
            listed = (self.ctrl.account if self.ctrl else None) or self._acct or []
        run = {d["deviceId"] for d in (self.ctrl.devices if self.ctrl else [])}
        out = []
        for d in listed:
            dev = d.get("deviceId")
            if not dev:
                continue
            con = d.get("connectivity")
            out.append({"id": dev, "name": d.get("name") or dev, "run": dev in run,
                        "online": None if con is None else con == 1, "firmware": d.get("fwVersionName"),
                        "address": self._lan_address(dev) or None, **self.health.summary(dev)})
        return {"devices": out, "now": time.time()}

    def health_check(self, dev: str | None = None) -> dict:
        """List the controllers again (online, firmware), read each one's
        detail (timed like any request), and greet each over the home
        network (its round trip)."""
        if self.ctrl is None:
            raise ApiError("Finish setup first.", 409)
        try:
            listed = list(self.client().list_devices())
            self._acct = listed
            if self.ctrl:
                self.ctrl.account = listed
        except Exception as e:
            raise ApiError(f"Trimlight's cloud didn't answer: {e}", 502) from None
        for d in listed:
            did = d.get("deviceId")
            if not did or (dev and did != dev):
                continue
            try:
                self.client().get_device(did, self.controller_now(), resync=False)
            except Exception:
                pass                                  # counted by the recorder
            addr = self._lan_address(did)
            if addr and not (self.lanshow.running() or any(z.running() for z in self.zoneshows.values()) or self.local_busy.locked()):
                if self.lan_io.acquire(timeout=5):
                    try:
                        with lanlink.Link(addr) as link:
                            self.health.record_lan(did, link.ping())
                    except lanlink.LinkError as e:
                        self.health.record_lan(did, None, str(e))
                    finally:
                        self.lan_io.release()
        return self.health_status()

    # --- 4.15: install a new version, and go back if it doesn't start ----------------
    def _updater(self):
        from . import selfupdate
        if getattr(self, "_upd", None) is None:
            self._upd = selfupdate.Updater(self.store.dir, stop=self._update_stop, spawn=self._update_spawn,
                                           answers=self._update_answers, quit=lambda: os._exit(0))
            self._upd.cleanup()
        return self._upd

    def _update_stop(self):
        """This copy steps aside: the scheduler stops (it may be sending),
        then the web server lets go of the port."""
        if self.ctrl:
            self.ctrl.stop_event.set()
            if self.thread:
                self.thread.join(timeout=120)
        h = getattr(self, "httpd", None)
        if h is not None:
            h.shutdown()
            h.server_close()

    def _update_spawn(self):
        import subprocess
        kw = {"cwd": str(self.base), "stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
              "env": autostart.child_env()}     # 4.16.3: its own unpacked files, not this copy's
        if os.name == "nt":
            kw["creationflags"] = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        else:
            kw["start_new_session"] = True
        return subprocess.Popen(autostart.launch_command(self.base), **kw)

    def _update_answers(self):
        import ssl
        port = (self.store.settings.get("service") or {}).get("web_port") or 8787
        ctx = ssl.create_default_context()
        ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
        for scheme in ("https", "http"):
            base = f"{scheme}://127.0.0.1:{port}"
            c = ctx if scheme == "https" else None
            try:
                with urllib.request.urlopen(base + "/api/session", timeout=2, context=c) as r:
                    v = json.loads(r.read()).get("version")
            except Exception:
                continue
            # 4.16.3: answering isn't enough; its page and script must load too
            # (a copy that lost its unpacked files answered, with no page)
            try:
                for path in ("/", "/app.js"):
                    with urllib.request.urlopen(base + path, timeout=3, context=c) as r:
                        if r.status != 200 or len(r.read(4096)) < 100:
                            return None
            except Exception:
                return None
            return v
        return None

    def update_summary(self) -> dict:
        u = self.updates.summary()
        up = self._updater()
        st = up.state()
        return {**u, "install": {"ok": up.plan["ok"], "why": up.plan["why"], "can_roll_back": up.can_roll_back(),
                                 "busy": up.busy, "last": {k: st.get(k) for k in ("stage", "frm", "to", "why", "at")} if st else None,
                                 "previous": st.get("frm") if up.can_roll_back() else None}}

    def _quiet_for_update(self) -> str | None:
        c = self.ctrl
        if self.lanshow.running() or any(z.running() for z in self.zoneshows.values()):
            return "A music show from this computer is running."
        if c is not None:
            with c.lock:
                if c.music or c.flash:
                    return "A music show or a flash is running."
        if self.local_busy.locked():
            return "A change over the home network is running."
        return None

    def update_install(self, auto: bool = False) -> dict:
        from . import selfupdate
        up = self._updater()
        u = self.updates.summary()
        if not u["newer"] or not u["download_name"]:
            raise ApiError("There's no newer version for this computer to install.", 409)
        if not up.plan["ok"]:
            raise ApiError(up.plan["why"], 409)
        why = self._quiet_for_update()
        if why:
            raise ApiError(why + " Install when it's done.", 409)
        if up.busy:
            raise ApiError("An update is already being installed.", 409)
        up.busy = True
        try:
            new = up.prepare({"version": u["latest"], "assets": u["assets"]}, u["download_name"])
        except selfupdate.UpdateError as e:
            up.busy = False
            raise ApiError(str(e), 502) from None
        except Exception as e:             # Review #3: never left "already being installed"
            up.busy = False
            log.exception("Preparing the update failed")
            raise ApiError(f"The update couldn't be prepared: {e}", 500) from None
        if self.ctrl:
            self.ctrl.note(f"Installing EaveLuxOS {u['latest']}{' (by itself)' if auto else ''}; the lights pause for a moment.")
        threading.Thread(target=self._run_update, args=(lambda: up.install(new, VERSION, u["latest"]),), daemon=True,
                         name="update").start()
        return {"ok": True, "installing": u["latest"]}

    def update_rollback(self) -> dict:
        up = self._updater()
        if not up.can_roll_back():
            raise ApiError("There's no previous version kept here to go back to.", 409)
        why = self._quiet_for_update()
        if why:
            raise ApiError(why + " Try again when it's done.", 409)
        up.busy = True
        if self.ctrl:
            self.ctrl.note("Going back to the previous EaveLuxOS version; the lights pause for a moment.")
        threading.Thread(target=self._run_update, args=(lambda: up.roll_back(VERSION),), daemon=True, name="update").start()
        return {"ok": True}

    def _run_update(self, job):
        time.sleep(0.8)          # let the answer reach the browser first
        try:
            job()
        except Exception:
            log.exception("The update couldn't be installed")
            self._updater().busy = False

    def auto_update_step(self):
        """Every ten minutes: with Install by themselves on, a newer version
        is installed while the lights are off and nothing else is running.
        A version that had to be rolled back isn't tried again by itself."""
        try:
            if not self.updates.summary().get("auto"):
                return
            u = self.updates.summary()
            if not u["newer"]:
                return
            st = self._updater().state()
            if st.get("stage") == "rolled_back" and st.get("to") == u["latest"]:
                return
            if self.ctrl is None or self.ctrl.lights_on() or self._quiet_for_update():
                return
            self.update_install(auto=True)
        except ApiError as e:
            log.info("Automatic update not now: %s", e)
        except Exception:
            log.exception("Automatic update check failed")

    def conflicts(self, day: str | None = None) -> dict:
        """4.15: who wins a night (noon to noon), for each controller."""
        from datetime import date as _date, timedelta
        from . import conflicts
        c = self.ctrl
        if c is None:
            raise ApiError("Finish setup first.", 409)
        now = c.cfg.loc.now()
        if day:
            try:
                d = _date.fromisoformat(str(day)[:10])
            except ValueError:
                raise ApiError("A date is like 2026-12-24.") from None
        else:
            d = now.date() - timedelta(days=1) if now.hour < 12 else now.date()
        names = {x["deviceId"]: x.get("name") or x["deviceId"] for x in c.devices}
        r = conflicts.night(c.cfg, list(names), d, names)
        r["names"] = names
        return r

    def house_tonight(self) -> dict:
        """4.12: what each controller's schedule shows from noon today to noon
        tomorrow (from noon yesterday before noon), for the whole-house
        timeline: spans of {start, end, effect (key), label, rule}. Only the
        schedule (rules and holidays): weather, scores, alerts and choices by
        hand can't be known ahead."""
        from datetime import timedelta
        c = self.ctrl
        if c is None:
            raise ApiError("Finish setup first.", 409)
        cfg = c.cfg
        now = cfg.loc.now()
        start = now.replace(hour=12, minute=0, second=0, microsecond=0)
        if now < start:
            start -= timedelta(days=1)
        end = start + timedelta(days=1)
        devs = [d["deviceId"] for d in c.devices] or [None]
        step = 300
        out = {}
        for dev in devs:
            sch = cfg.schedule.for_controller(dev)
            spans = []
            for d in (start.date() - timedelta(days=1), start.date(), end.date()):
                for p in sch.day_plans(d):
                    a, b = max(ts(p.start), ts(start)), min(ts(p.end), ts(end))
                    if a >= b:
                        continue
                    u = a
                    while u < b:              # in real seconds, so a night the clocks change is counted right
                        eff = p.window.rule.pick(p.window.start, datetime.fromtimestamp(u, now.tzinfo))[0]
                        nxt = min(b, u + step)
                        last = spans[-1] if spans else None
                        if last and last["effect"] == eff.key and last["rule"] == p.rule.name and last["_end"] == u:
                            last["_end"] = nxt
                        else:
                            spans.append({"_start": u, "_end": nxt, "effect": eff.key, "label": eff.label, "rule": p.rule.name})
                        u = nxt
            spans.sort(key=lambda x: x["_start"])
            for x in spans:
                x["start"] = datetime.fromtimestamp(x.pop("_start"), now.tzinfo).isoformat()
                x["end"] = datetime.fromtimestamp(x.pop("_end"), now.tzinfo).isoformat()
            out[dev or "all"] = spans
        return {"start": start.isoformat(), "end": end.isoformat(), "now": now.isoformat(), "devices": out}

    def automation_history(self) -> list:
        tz = self.cfg.loc.tz if self.cfg else None
        return [{"at": datetime.fromtimestamp(h["at"], tz).strftime("%b %d, %I:%M %p").replace(" 0", " "), "id": h["id"],
                 "text": h["text"]} for h in list(self.autos.history)]

    def celebrate(self, team: dict, points: int, game: dict) -> bool:
        """A watched team scored (scores.py): flash its colors, moving fast,
        for a few seconds; then everything returns to what was on."""
        c = self.ctrl
        cfg = c.cfg if c else None     # the scheduler's own settings, never a mix of old and new
        if not (c and cfg) or team["key"] not in cfg.celebrate:
            return False
        eff = cfg.effects.get(team["effect"])
        if eff is None:
            return False
        if eff.kind == "custom":
            eff = Effect(eff.key, eff.label, "custom", payload={**eff.payload, "mode": 1, "speed": 230, "brightness": 255},
                         colors=list(eff.colors))
        started = c.start_flash(seconds=team["seconds"], effect=eff, label=f"{team['name']} scored!", kind="score",
                                only_if_on=team.get("only_when_on", True))
        if started and (team.get("sound") or {}).get("on"):
            self._play_sound(team["key"], team["sound"])          # 4.9: the goal horn
        if not started:
            c.note(f"{team['name']} scored ({points} points); no celebration because the lights are off.")
        return started

    # --- 4.9: celebration sounds (sound.py) -------------------------------------

    def _sound_file(self, team: str) -> Path:
        if not re.fullmatch(r"[a-z]{2,8}-[a-z0-9]{1,6}", team or ""):
            raise ApiError("That isn't a team.")
        return self.store.dir / "sounds" / f"{team}.sound"

    def _team_sound(self, team: str) -> dict | None:
        gd = self.store.settings.get("gameday") or {}
        for t in gd.get("teams") or []:
            if isinstance(t, dict) and f"{t.get('league')}-{t.get('team')}" == team:
                return t.get("sound") if isinstance(t.get("sound"), dict) else None
        raise ApiError("Add the team under Schedule › Game-day lights first.", 404)

    def sound_upload(self, team: str, data: bytes, name: str) -> dict:
        """Keep a sound file for a team. The settings say which part plays;
        the page saves those once this returns."""
        f = self._sound_file(team)
        self._team_sound(team)
        try:
            kind, secs = sound.check_upload(data)
        except sound.SoundError as e:
            raise ApiError(str(e), 415 if "MP3 or WAV" in str(e) else 400) from None
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, f)
        return {"kind": kind, "length": secs, "name": re.sub(r"[\x00-\x1f]", "", name)[:120]}

    def sound_delete(self, team: str) -> dict:
        f = self._sound_file(team)
        f.unlink(missing_ok=True)
        for old in f.parent.glob(f"{team}-*.*") if f.parent.is_dir() else ():
            if old.suffix in (".mp3", ".wav"):
                try:
                    old.unlink()
                except OSError:
                    pass
        return {"ok": True}

    def sound_clip(self, team: str) -> tuple[bytes, str]:
        f, snd = self._sound_file(team), self._team_sound(team)
        if not snd or not f.is_file():
            raise ApiError("No sound for that team yet.", 404)
        try:
            return sound.cut(f.read_bytes(), snd.get("kind", "mp3"), float(snd.get("start", 0)),
                             float(snd.get("seconds", 20))), snd.get("kind", "mp3")
        except (sound.SoundError, TypeError, ValueError) as e:
            raise ApiError(str(e) or "That sound can't be cut.", 400) from None

    def _play_sound(self, team: str, snd: dict) -> bool:
        """Never raises: the lights celebrate whatever happens to the sound.
        Review #1 (4.9): the clip is named for what it holds and written
        only when it's new, because on Windows the player keeps the file
        open while it plays (a second goal couldn't rewrite it)."""
        try:
            data, kind = self.sound_clip(team)
            clip = self._sound_file(team).with_name(f"{team}-{hashlib.sha256(data).hexdigest()[:12]}.{kind}")
            if not clip.is_file():
                tmp = clip.with_suffix(".tmp")
                tmp.write_bytes(data)
                os.replace(tmp, clip)
                for old in clip.parent.glob(f"{team}-*.*"):
                    if old != clip and old.suffix in (".mp3", ".wav"):
                        try:
                            old.unlink()
                        except OSError:
                            pass         # still playing; it goes next time
            return self.player.play(clip, kind, float(snd.get("seconds", 20)))
        except (ApiError, OSError, ValueError) as e:
            log.warning("Celebration sound for %s didn't play: %s", team, e)
            return False

    def sound_test(self, team: str) -> dict:
        snd = self._team_sound(team)
        if not snd:
            raise ApiError("Choose a sound file first.")
        if not self.player.supported(snd.get("kind", "mp3")):
            raise ApiError("This computer has no sound player the app can use.", 409)
        return {"played": self._play_sound(team, snd)}

    def alert_probe(self) -> dict:
        """What phone alerts look at, once a minute (alerts.py)."""
        out = {}
        c = self.ctrl
        if c:
            out["failed"] = (c.fail_count >= 2, (c.last_error or "")[:200])
            snap = (c.status_cache or {}).get("data") or []
            off = [str(d.get("name") or "A controller") for d in snap if isinstance(d, dict) and d.get("online") is False]
            out["offline"] = (bool(off), ", ".join(off))
            out["unreadable"] = ("12006" in (c.read_error or ""), "your controller")
        u = self.updates.summary()
        out["update"] = (bool(u["newer"]), u["latest"] or "")
        return out

    def restore_patterns(self, name, ids) -> dict:
        """Put patterns from a controller backup back on that controller,
        over the home network (4.3; never through the cloud)."""
        if not isinstance(ids, list) or not ids:
            raise ApiError("Choose at least one pattern to put back.")
        try:
            det = restore.read_backup(self.safety.backup_dir, name)
        except restore.RestoreError as e:
            raise ApiError(str(e), 404)
        m = restore.NAME_RE.fullmatch(str(name))
        acct = [d["id"] for d in self._account()]
        if acct and m.group(1) not in acct:
            raise ApiError("That backup is of a controller that isn't on this Trimlight account now.", 409)
        loc, dev = self.local(dev=m.group(1))        # 4.5: back onto the controller it came from
        try:
            r = loc.restore(det, ids)
        except localmode.LocalError as e:
            raise ApiError(str(e), 502)
        if r["restored"]:
            log.info("Put back from backup %s over the home network: %s", name, ", ".join(r["restored"]))
            self._after_local_write(dev)
        return r

    # ------------------------------------------------------------ devices
    def devices(self) -> list[dict]:
        api = self.client()
        chosen = set(self.store.settings.get("service", {}).get("devices", []))
        out = []
        try:
            listing = api.list_devices()
        except TrimlightError as e:
            raise ApiError(str(e), 502)
        self._acct = list(listing)           # 4.5: which controllers there are, for their home-network addresses
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
                base = port_base(det.get("ports"))
                if base and self._port_base.get(item["id"]) != base:
                    log.info("%s numbers its ports 1-4; shown and saved that way.", item["name"] or item["id"])
                self._port_base[item["id"]] = base
                item.update({"name": det.get("name", item["name"]),
                             "ports": [{**p, "id": p.get("id", 0) - base,
                                        "unused": p.get("id", 0) - base in self.unused_ports(item["id"]),
                                        "set_here": p.get("id", 0) - base in self.unused_ports(item["id"], "ports_set")}
                                       for p in det.get("ports", []) or []],
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
        ends = [p.get("end", 0) for it in out if it.get("selected") for p in it.get("ports") or []
                if isinstance(p.get("end"), int) and not p.get("unused")]
        if ends and max(ends) > 0:
            self._bulbs = max(ends)
        return out

    def unused_ports(self, dev, field="unused_ports") -> set:
        """Ports marked not connected on the Lights tab (app numbers 0-3), or
        (field "ports_set") ports given bulbs on the Lights tab (3.18.2)."""
        u = (self.store.settings.get("service") or {}).get(field) or {}
        return {i for i in u.get(dev, []) if isinstance(i, int)}

    def set_unused_ports(self, dev, ids, touched=None, given=None):
        """Remember which of a controller's ports aren't connected. touched:
        the ports this change was about (default all); a port it doesn't
        mention keeps what was remembered, so a client sending only some
        ports can't quietly count the others again (3.18.2). given: ports
        given bulbs here (other than the controller's never-set-up 1-600);
        they're remembered (ports_set), so the Lights tab doesn't take a real
        run for a port that was never set up."""
        s = copy.deepcopy(self.store.settings)
        svc = s.setdefault("service", {})
        old = copy.deepcopy(svc)
        u = dict(svc.get("unused_ports") or {})
        if touched is None:
            touched = set(range(4))
        ids = sorted(set(ids) | {i for i in u.get(dev, []) if i not in touched})
        if ids:
            u[dev] = ids
        else:
            u.pop(dev, None)
        svc["unused_ports"] = u
        ps = dict(svc.get("ports_set") or {})
        have = sorted((set(ps.get(dev, [])) | set(given if given is not None else touched)) - set(ids))
        if have:
            ps[dev] = have
        else:
            ps.pop(dev, None)
        svc["ports_set"] = ps
        for k in ("unused_ports", "ports_set"):
            if not svc[k] and k not in old:
                del svc[k]
        if svc == old:
            return
        self.store.save_settings(s)
        self._bulbs = None                 # count again without them

    def address_space(self) -> int | None:
        """Bulbs in the pattern address space, as the House map counts them:
        its own total when set there, else the controller's last port end."""
        if self.cfg and self.cfg.total_bulbs:
            return self.cfg.total_bulbs
        if self._bulbs is None and self.cfg:
            try:
                self.devices()
            except ApiError:
                return None
        return self._bulbs

    def flash_from(self, b: dict) -> dict:
        """Start a flash from an app or webhook request: {"effect" | "color",
        "zone", "seconds" | "minutes", "label"}. Nothing named = the security
        flash."""
        from .triggers import flash_effect
        ctrl, cfg = self.ctrl, self.cfg
        eff = None
        if b.get("effect") or b.get("color") or b.get("zone"):
            try:
                eff = flash_effect(cfg.effects, cfg.gamma, effect=b.get("effect"), color=b.get("color"),
                                   zone=b.get("zone"), zones=cfg.zones,
                                   total=self.address_space() if b.get("zone") else None)
            except ValueError as e:
                raise ApiError(str(e)) from None
        secs = mins = None
        try:
            if b.get("seconds") not in (None, ""):
                secs = int(b["seconds"])
            elif b.get("minutes") not in (None, ""):
                mins = int(b["minutes"])
        except (TypeError, ValueError):
            raise ApiError("Seconds and minutes must be whole numbers.") from None
        if eff is not None and secs is None and mins is None:
            secs = 30                      # alerts default to 30 seconds
        label = str(b.get("label") or "").strip()[:60] or None
        # What wins when two happen at once (controller.FLASH_RANK): the
        # security flash and urgent alerts (alarm, or "urgent": true) beat a
        # weather warning and other alerts; a package can't end an alarm.
        urgent = b.get("urgent") is True or str(b.get("urgent")).lower() == "true" or \
            str(b.get("effect") or "").strip().lower() in ("alarm", "security")
        kind = "security" if eff is None else "urgent" if urgent else "alert"
        started = ctrl.start_flash(mins, seconds=secs, effect=eff, label=label, kind=kind)
        return {**ctrl.status(), "flash_started": started}

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
            if len({p["id"] for p in ports}) != len(ports):
                raise ApiError("Each port can be given only once.")          # review #5 (4.3.1)
            if ports and all(p["start"] == 0 and p["end"] == 0 for p in ports):
                raise ApiError("At least one port needs bulbs. Turning every port off would leave the lights dark.")
            if self._lan_address(dev) and sorted(p["id"] for p in ports) == [0, 1, 2, 3]:   # review #5 (4.3.1): each port once
                # 4.3: over the home network, where a port can really be off.
                return self._ports_local(dev, ports, {k: v for k, v in payload.items()})
            off_ids = sorted(p["id"] for p in ports if p["start"] == 0 and p["end"] == 0)
            base = self._port_base.get(dev)
            current = None
            if base is None or off_ids:
                # How this controller numbers its ports, and (for a port marked
                # not connected) what it holds now.
                try:
                    current = self.client().get_device(dev, self.now()).get("ports") or []
                except TrimlightError as e:
                    raise ApiError(f"Couldn't read the controller's ports first, so nothing was changed: {e}", 502)
                base = port_base(current)
                self._port_base[dev] = base
            # Trimlight has no "off" for a port: start 0 is refused (code 12000,
            # "Invalid parameter [port -> start]"). A port marked not connected
            # keeps what the controller already holds (left out if that isn't
            # valid either), and this app remembers to leave it out of the bulb
            # count (3.18.1).
            local = []                   # ports 0-3 as the screen numbers them
            for p in ports:
                if p["id"] in off_ids:
                    was = next((q for q in current or [] if q.get("id") == p["id"] + base), None)
                    if not (was and isinstance(was.get("start"), int) and was["start"] >= 1
                            and isinstance(was.get("end"), int) and was["end"] >= was["start"]):
                        continue
                    local.append({"id": p["id"], "start": was["start"], "end": was["end"]})
                else:
                    local.append(dict(p))
            if local:
                payload["ports"] = local
            unused = off_ids
        if not payload and "ports" not in body:
            raise ApiError("Nothing to change.")
        note = None
        if payload:
            note = self._send_device_update(dev, payload, base if "ports" in payload else None)
        if "ports" in body:
            self.set_unused_ports(dev, unused, touched={p["id"] for p in ports},
                                  given={p["id"] for p in ports if (p["start"], p["end"]) not in ((0, 0), (1, 600))})
        if self.ctrl:
            # List the controllers again and send them the lights in full
            # (switch-on included), not just forget the list.
            self.ctrl.refresh_devices()
        return {"ok": True, **({"note": note} if note else {})}

    def _ports_local(self, dev: str, ports: list, other: dict) -> dict:
        """The Lights tab's port layout, sent over the home network (4.3). A
        port marked not connected is switched off and keeps its numbers."""
        loc, ldev = self.local(dev=dev)
        try:
            cur = loc.read()["ports"]
        except localmode.LocalError as e:
            raise ApiError(f"{e} Nothing was changed.", 502) from None
        if len(self._account()) > 1:
            # 4.5.1: with several controllers, make sure this is the one: if the
            # router gave two of them each other's addresses, these ports would
            # land on the wrong controller.
            why = self._not_this_one(dev, loc.host, cur)
            if why:
                raise ApiError(f"{why} Nothing was changed. If its address changed, update it in Setup \u203a "
                               "Local mode (Find controllers).", 409)
        want = []
        for p in sorted(ports, key=lambda p: p["id"]):
            off = p["start"] == 0 and p["end"] == 0
            c = cur[p["id"]]
            st_, en = (c["start"], c["end"]) if off else (p["start"], p["end"])
            if not 1 <= st_ <= en:
                st_, en = 1, max(1, en)
            want.append({"start": st_, "end": en, "on": not off})
        try:
            changed = loc.ports(want)
        except localmode.LocalError as e:
            raise ApiError(str(e), 502) from None
        self._ports_set[dev] = {i: (w["start"], w["end"]) for i, w in enumerate(want)}   # what it holds now
        log.info("Ports set over the home network: %s", "; ".join(changed))
        self._after_local_write(dev)
        note = None
        if other:       # the name, chip type and color order still go through the cloud
            note = self._send_device_update(dev, other, None)
        self.set_unused_ports(dev, [p["id"] for p in ports if p["start"] == 0 and p["end"] == 0],
                              touched={p["id"] for p in ports},
                              given={p["id"] for p in ports if (p["start"], p["end"]) not in ((0, 0), (1, 600))})
        if self.ctrl:
            self.ctrl.refresh_devices()
        return {"ok": True, "local": True, **({"note": note} if note else {})}

    def _send_device_update(self, dev: str, payload: dict, base: int | None):
        """Send a device update; ports go in the controller's own numbers.

        4.0.3: Trimlight Edge firmware 1.17.77 reports its ports as 1-4, but
        the cloud refused a save in those numbers with code 12000 "Invalid
        parameter [port -> id]". A refused request changes nothing, so when
        the cloud names the port id, the save is tried once more with the
        other numbering (0-3 instead of 1-4, or the other way round). What
        worked is remembered for this controller, and the controller is read
        back to check the ports landed where they were meant to."""
        api = self.client()
        if base is None:
            try:
                api.update_device(dev, payload)
            except TrimlightError as e:
                raise ApiError(str(e), 502)
            return None
        local = payload["ports"]

        def with_ids(wb):
            return {**payload, "ports": [{**p, "id": p["id"] + wb} for p in local]}

        wb = self._port_write_base.get(dev, base)
        try:
            api.update_device(dev, with_ids(wb))
            self._port_write_base[dev] = wb
            return None
        except TrimlightError as e:
            if not (e.refused and "port -> id" in str(e).lower()):
                raise ApiError(str(e), 502)
            first = e
        other = 1 - wb
        try:
            api.update_device(dev, with_ids(other))
        except TrimlightError as e:
            if e.refused and "port -> id" in str(e).lower():
                raise ApiError(f"Trimlight refused the port numbers both ways (1-4 and 0-3): {first}. "
                               "Nothing was changed. Set the ports in the Trimlight app for now, and "
                               "please report this with the app's log.", 502)
            raise ApiError(str(e), 502)
        self._port_write_base[dev] = other
        log.warning("Trimlight refused ports numbered %s (%s); they were saved numbered %s, and will be from now on.",
                    "1-4" if wb else "0-3", first, "1-4" if other else "0-3")
        # Check where they landed (reads can lag a little behind a save).
        try:
            back = api.get_device(dev, self.now()).get("ports") or []
        except TrimlightError:
            return None
        rb = port_base(back)
        wrong = [p["id"] + 1 for p in local
                 if not any(q.get("id") == p["id"] + rb and q.get("start") == p["start"] and q.get("end") == p["end"]
                            for q in back)]
        if wrong:
            log.warning("After saving ports %s, the controller reads back %s.", local, back)
            return (f"Saved, but the controller doesn't show port {', '.join(map(str, wrong))} as set yet. "
                    "Wait a minute and open Setup › Lights & controller again; if a port is still off by one, "
                    "fix it in the Trimlight app and send the developer the app's log.")
        return None

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
        """Also save a pattern in the controller's own library (the Trimlight
        app's list), over the home network (4.3; never through the cloud)."""
        name = str(body.get("name", "")).strip()
        if not 1 <= len(name) <= 30:
            raise ApiError("Pattern name must be 1-30 characters.")
        eff = Effect.from_config("_save", body.get("effect") or {}, self.gamma())
        if eff.kind == "saved":
            raise ApiError("That pattern is already on the controller.")
        if eff.kind == "split":
            raise ApiError("A pattern split across controllers can't be saved in the Trimlight app; save each part instead.")
        if eff.payload.get("category") != 1:
            raise ApiError("Only patterns of your own colors can be saved on the controller; a built-in effect is "
                           "already there.")
        want = body.get("devices")
        if want is None:
            # 4.5: every controller this app runs that has an address (one,
            # before 4.5); a controller without one is named, not skipped quietly.
            want = [d.get("deviceId") for d in (self.ctrl.devices if self.ctrl else [])] or None
        if want is not None and (not isinstance(want, list) or not want or not all(isinstance(x, str) for x in want)):
            raise ApiError("Choose which controllers to save it on.")
        saved, missing = [], []
        for dev in (want or [None]):
            if dev is not None and not self._lan_address(dev):
                missing.append(self._name_of(dev))
                continue
            loc, dev = self.local(dev=dev)
            try:
                pid = loc.save({"name": name, **eff.payload})
            except localmode.LocalError as e:
                if saved:
                    raise ApiError(f"Saved on {', '.join(self._name_of(x['device']) for x in saved)}, but not on "
                                   f"{self._name_of(dev)}: {e}", 502)
                raise ApiError(str(e), 502)
            log.info("Saved %r on %s over the home network as pattern %s.", name, self._name_of(dev), pid)
            self._after_local_write(dev)
            saved.append({"device": dev, "id": pid})
        if not saved:
            raise ApiError(f"{' and '.join(missing)} {'has' if len(missing) == 1 else 'have'} no home-network address "
                           "yet, so nothing was saved on the controller: Setup \u203a Lights & controller \u203a "
                           "Local mode.", 409)
        return {"ok": True, "saved": saved, "missing": missing}

    # ------------------------------------------------------------ misc
    def upcoming(self, days: int, month: str | None = None, device: str | None = None):
        """What runs each night from today (or, with month="YYYY-MM", that
        whole month: the Schedule tab's month view, 3.15). device (4.8): as
        that controller runs it. Without one, when some rules run only some
        controllers, each controller's nights together, each time naming
        the controllers it's for."""
        if not self.cfg:
            return []
        sch, loc = self.cfg.schedule, self.cfg.loc
        if device:
            sch = sch.for_controller(str(device)[:80])
        devs = [(d["deviceId"], str(d.get("name") or d["deviceId"])) for d in (self.ctrl.devices if self.ctrl else [])]

        def plans_of(d):
            if device or not sch.per_controller or not devs:
                return [(p, None) for p in sch.day_plans(d)]
            got = {}
            for dev, name in devs:
                for p in sch.for_controller(dev).day_plans(d):
                    k = (p.rule.name, p.start.isoformat(), p.end.isoformat())
                    got.setdefault(k, (p, []))[1].append(name)
            out = sorted(got.values(), key=lambda x: x[0].start.isoformat())
            return [(p, None if len(names) == len(devs) else names) for p, names in out]
        out = []
        start = loc.now().date()
        from datetime import timedelta
        if month is not None:
            import calendar
            m = re.fullmatch(r"(\d{4})-(\d{2})", str(month))
            if not m or not 1 <= int(m.group(2)) <= 12:
                raise ApiError("Month must look like 2026-12.")
            y, mo = int(m.group(1)), int(m.group(2))
            if not start.year - 1 <= y <= start.year + 2:
                raise ApiError("Pick a month from last year to two years ahead.")
            start, days = date(y, mo, 1), calendar.monthrange(y, mo)[1]
        prev = None
        for i in range(days):
            d = start + timedelta(days=i)
            s = loc.sun(d)
            wins = [{"on": p.start.isoformat(), "off": p.end.isoformat(), "on_label": p.start.strftime("%H:%M"),
                     "off_label": p.end.strftime("%H:%M"), "rule": p.rule.name, "effect": p.effect_label(),
                     **({"controllers": names} if names else {})} for p, names in plans_of(d)]
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
            from .trust import CERT_HELP, client_context, is_cert_failure
            with urllib.request.urlopen(req, timeout=10, context=client_context()) as r:
                data = json.loads(r.read())
        except Exception as e:
            if is_cert_failure(e):
                raise ApiError(CERT_HELP.format(who="the place search service") +
                               " Or enter latitude and longitude instead.", 502)
            raise ApiError("Couldn't reach the place search service. Enter latitude and longitude instead.", 502)
        return [{"name": x.get("name"), "region": x.get("admin1"), "country": x.get("country"),
                 "lat": round(x["latitude"], 4), "lon": round(x["longitude"], 4), "timezone": x.get("timezone")}
                for x in data.get("results", []) or []]

    def import_settings(self, body: dict):
        incoming = body.get("settings")
        if not isinstance(incoming, dict):
            raise ApiError("That file isn't a EaveLuxOS export.")
        # Never taken from a file: this home's own setup, and where the
        # community library is fetched from (a shared file could otherwise
        # make this computer request any address on the home network).
        for k in ("setup_done", "_rev", "controller", "service", "community", *PRIVATE_KEYS):
            incoming.pop(k, None)
        cur = copy.deepcopy(self.store.settings)
        if body.get("mode") == "replace":
            # This home's own settings, never taken from a file (a shared file
            # could otherwise repoint the community library, for example).
            keep = {k: cur.get(k) for k in ("location", "service", "setup_done", "controller", "community", *PRIVATE_KEYS) if k in cur}
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
            if renamed:   # a split pattern (3.17) names other patterns: follow their new keys
                for v in effs.values():
                    if isinstance(v, dict) and isinstance(v.get("split"), dict):
                        v["split"] = {d: renamed.get(x, x) for d, x in v["split"].items()}
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
                if self._bearer() is not None:
                    # 4.17: an integration's API token (Authorization: Bearer elx_...)
                    self._u = app.store.token_user(self._bearer(), self.client_address[0])
                elif self._local() and not app.store.local_login_required():
                    self._u = dict(LOCAL_USER)
                else:
                    self._u = app.store.session_user(self._token())
            return self._u

        def _bearer(self) -> str | None:
            a = self.headers.get("Authorization") or ""
            return a[7:].strip() if a[:7].lower() == "bearer " else None

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
                if path in VIEWER_POSTS:
                    return
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
                             "default-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; style-src 'self' 'unsafe-inline'; "
                             "script-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; "
                             "form-action 'self'; frame-ancestors 'none'")
            self.send_header("Cross-Origin-Opener-Policy", "same-origin")
            self.send_header("Cross-Origin-Resource-Policy", "same-origin")
            self.send_header("Permissions-Policy", "geolocation=(self), camera=(), microphone=(self), payment=(), usb=()")
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
            limit = MAX_BODY
            up = urllib.parse.urlparse(self.path).path
            if up in ("/api/photo/upload", "/api/sound/upload"):
                u = self._user()
                if u and u.get("role") in ("admin", "editor"):
                    # only people who may save photos (and sounds, 4.9) send a big body
                    limit = PHOTO_UPLOAD_MAX if up == "/api/photo/upload" else sound.UPLOAD_MAX
            elif up == "/api/backup/restore":
                u = self._user()
                if u and u.get("role") == "admin" and not u.get("token"):
                    limit = RESTORE_MAX              # 4.17: an encrypted backup with the house photos
            if n > limit:
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
            body = f.read_bytes()
            if name == "sw.js":
                # 4.14: the phone keeps one set of the app's files per version
                body = body.replace(b"__VERSION__", VERSION.encode())
            self._send(200, body, ctype)

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
            if urllib.parse.urlparse(self.path).path == "/api/hook/status":
                try:
                    self._read_raw()
                    return self._hook(urllib.parse.urlparse(self.path))
                except ApiError as e:
                    self.close_connection = True
                    return self._json(e.code, {"error": str(e)})
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
            if path == "/trust":
                self.send_response(302)
                self.send_header("Location", "/#phone")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if path == "/ca.crt":
                # 4.18.2: the mkcert root certificate (public, never its key),
                # so a phone can trust this app's HTTPS: Set up this phone
                ca = app.phone_ca()
                if not ca:
                    return self._json(404, {"error": "No mkcert root certificate was found on the app computer."})
                return self._send(200, ca["pem"], "application/x-x509-ca-cert",
                                  {"Content-Disposition": 'attachment; filename="EaveLuxOS-root.crt"'})
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
                        if self._local():           # 4.22.2: for the page on this computer, if it can't reach the program later
                            out["start"] = {"link": bool(getattr(app, "start_link", False)),
                                            "program": getattr(app, "program", None)}
                    return self._json(200, out)
                if not self._authed():
                    return self._json(401, {"error": "Sign in first."})
                if path in ADMIN_GETS and not self._is_admin():
                    return self._json(403, {"error": "Only an Administrator can see that."})
                if path == "/api/health":                 # 4.15: controller health
                    return self._json(200, app.health_status())
                if path == "/api/conflicts":              # 4.15: who wins a night
                    return self._json(200, app.conflicts(q.get("date")))
                if path == "/api/house/tonight":          # 4.12: the whole-house timeline
                    return self._json(200, app.house_tonight())
                if path == "/api/studio/state":           # 4.20: a Studio show playing
                    return self._json(200, {"playing": (app.ctrl.show_state if app.ctrl else None)})
                if path == "/api/phone":                  # 4.18.2: Set up this phone
                    return self._json(200, app.phone_info(self.server.server_address[1]))
                if path == "/api/presence":               # 4.18: who's home
                    # Review #4 (4.18.1): when nobody's home is as private as
                    # away mode: not for Viewer accounts or Viewer tokens
                    if (self._user() or {}).get("role") == "viewer":
                        return self._json(403, {"error": "Viewers can't see who's home."})
                    return self._json(200, app.presence_status())
                if path == "/api/automations/history":    # 4.11: what automations did lately
                    return self._json(200, app.automation_history())
                if path == "/api/sound/clip":      # 4.9: to listen in the browser
                    data, kind = app.sound_clip(q.get("team", ""))
                    return self._send(200, data, "audio/mpeg" if kind == "mp3" else "audio/wav")
                if path.startswith("/api/photo/"):
                    f = app.photo_path(path.rsplit("/", 1)[-1])
                    if not f.is_file():
                        return self._json(404, {"error": "No photo yet."})
                    return self._send(200, f.read_bytes(), "image/jpeg")
                r = self._get(path, q)
                if r is _SENT:                          # 4.17: answered already (a download)
                    return None
                return self._json(200, r)
            except ApiError as e:
                return self._json(e.code, {"error": str(e)})
            except ValueError:
                return self._json(400, {"error": "A value in the address isn't valid."})
            except Exception:
                log.exception("GET %s failed", path)
                return self._json(500, {"error": "Something went wrong. Details are in the log."})

        def _get(self, path, q):
            if path == "/api/update":
                return app.update_summary()
            if path == "/api/community":
                try:
                    return app.community.index(app.store.settings, refresh=q.get("refresh") == "1")
                except community.CommunityError as e:
                    raise ApiError(str(e), 502) from None
            if path == "/api/community/item":         # 4.21: a shared show or automation
                try:
                    return app.community.item(app.store.settings, q.get("id", ""), q.get("kind", ""))
                except community.CommunityError as e:
                    raise ApiError(str(e), 502) from None
            if path == "/api/community/pattern":
                try:
                    return {"pattern": app.community.pattern(app.store.settings, q.get("id", ""))}
                except community.CommunityError as e:
                    raise ApiError(str(e), 502) from None
            if path == "/api/musiclink":
                return app.musiclink_status()
            if path == "/api/musiczones":
                return app.musiczones_status()
            if path == "/api/lan_check":
                # Why can't a phone open the app? Only from this computer: it
                # reads this computer's firewall.
                if not self._local():
                    raise ApiError("Check this from the computer the app runs on.", 403)
                port = self.server.server_address[1]
                out = {"system": platform.system(), "port": port, "addresses": lan_addresses(),
                       "scheme": getattr(app, "scheme", "http")}
                if out["system"] == "Windows":
                    out["windows"] = winfirewall.check(port)
                return out
            if path == "/api/status":
                if app.ctrl is None:
                    return {"setup_only": True, "setup": app.setup_state()}
                st = app.ctrl.status()
                st["setup"] = app.setup_state()
                st["slot_limit"] = TrimlightAPI.slot_limit     # bulbs per color slot this controller takes (90 or 60)
                st["coming"] = app.coming_up()                  # next holiday and game, for the panel summaries (4.0.1)
                st["lan"] = app.lan_home()                      # each controller's home-network address, for Home (4.1.2; 4.5)
                # 4.7.1: every controller on the account, and which ones this app
                # runs (Home shows those as active and the others greyed out)
                st["account"] = app._account()
                st["controlled"] = [d.get("deviceId") for d in list(app.ctrl.devices)] or \
                    (list(app.ctrl.cfg.devices) if app.ctrl.cfg.devices else [d["id"] for d in st["account"]])
                return st
            if path == "/api/catalog":
                return catalog.catalog()
            if path == "/api/settings":
                return app.store.settings
            if path == "/api/devices":
                return app.devices()
            if path == "/api/upcoming":
                return app.upcoming(max(1, min(400, int(q.get("days", 14)))), q.get("month"), q.get("device"))
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
                if u["role"] != "admin" or u.get("token"):
                    return out   # no credentials, webhook token or folders for Editors, Viewers and API tokens (4.17)
                from .store import SESSION_IDLE_CHOICES, SESSION_MAX_DAYS
                out.update({"client_id": s.get("client_id", ""),
                            "secret_hint": ("••••" + s["client_secret"][-4:]) if s.get("client_secret") else "",
                            "webhook_token": s.get("webhook_token"), "local_login": app.store.local_login_required(),
                            "autostart": autostart.status(app.base), "awake": app.awake.status(),
                            "python": platform.python_version(),
                            "data_dir": str(app.store.dir), "session_idle_hours": app.store.session_idle_hours(),
                            "session_idle_choices": list(SESSION_IDLE_CHOICES), "session_max_days": SESSION_MAX_DAYS})
                return out
            if path == "/api/users":
                return app.store.users()
            if path == "/api/audit":                  # Administrators (4.17)
                rows = app.store.audit_rows(int(q.get("limit", 200) or 200), int(q.get("before", 0) or 0) or None,
                                            q.get("who") or None, q.get("q") or None)
                if q.get("format") == "csv":
                    buf = io.StringIO()
                    w = csv.writer(buf)
                    w.writerow(["when", "who", "role", "from", "what", "detail", "ok"])
                    for r in rows:
                        w.writerow([datetime.fromtimestamp(r["at"]).isoformat(timespec="seconds"), r["who"], r["role"] or "",
                                    r["via"] or "", r["what"], r["detail"] or "", "yes" if r["ok"] else "refused"])
                    self._send(200, buf.getvalue().encode("utf-8-sig"), "text/csv; charset=utf-8",
                               {"Content-Disposition": 'attachment; filename="eaveluxos-audit.csv"'})
                    return _SENT
                return {"rows": rows}
            if path == "/api/tokens":                 # Administrators (4.17)
                return app.store.tokens()
            if path == "/api/safety":
                return app.safety_status()
            if path == "/api/history":
                return app.store.history(max(1, min(100, int(q.get("limit", 30)))))
            if path == "/api/photos":
                d = app.store.dir / "photos"
                return sorted(f.stem for f in d.glob("*.jpg")) if d.is_dir() else []
            if path == "/api/rulecheck":
                return app.rule_check()
            if path == "/api/patterns/fx":            # 4.22.5: Lightning / Snowflake badges
                return app.patterns_fx()
            if path == "/api/energy":                 # 4.21: estimates from the patterns
                return app.energy_estimate()
            if path == "/api/runtime":                # hours on per month (3.15)
                return {"months": app.ctrl.runtime.summary(12) if app.ctrl else []}
            if path == "/api/alerts":
                return app.alerts.settings()
            if path == "/api/ai":
                from .textpattern import AI_MODEL
                return {"configured": bool(app.store.secrets.get("ai_key")),
                        "model": (app.store.settings.get("ai") or {}).get("model") or AI_MODEL, "default_model": AI_MODEL}
            if path == "/api/triggers":
                from .triggers import ALERT_GROUPS, preset_list
                return {"presets": preset_list(), "zones": app.cfg.zones if app.cfg else [],
                        "alert_groups": [{"key": k, "label": v[0], "events": v[1]} for k, v in ALERT_GROUPS.items()],
                        "alert": app.ctrl.status().get("alert") if app.ctrl else None,
                        "bulbs": app.cfg.total_bulbs if app.cfg and app.cfg.total_bulbs else app._bulbs}
            if path == "/api/gameday":
                return app.gameday_status()
            if path == "/api/holidays":             # the holiday calendar (3.19)
                return app.holidays_status()
            if path == "/api/backups":                 # controller backups to restore patterns from (3.15)
                return restore.list_backups(app.safety.backup_dir)
            if path == "/api/local":                    # Administrators: the controller over the home network (4.3)
                return app.local_state(q.get("fresh") == "1", q.get("device") or None)
            if path == "/api/backups/patterns":
                try:
                    det = restore.read_backup(app.safety.backup_dir, q.get("file", ""))
                except restore.RestoreError as e:
                    raise ApiError(str(e), 404)
                return {"file": q.get("file"), "patterns": restore.patterns_in(det)}
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
                for k in ("location", "service", "setup_done", "_rev", "controller", "map", "safety", "community", *PRIVATE_KEYS):
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
                if self.headers.get("X-Requested-With") != "eaveluxos" and self._bearer() is None:
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
                if path == "/api/photo/upload":   # the photo's own bytes, not JSON
                    b = {"side": urllib.parse.parse_qs(url.query).get("side", [""])[0]}
                elif path == "/api/sound/upload":   # 4.9: the sound file's own bytes
                    qs = urllib.parse.parse_qs(url.query)
                    b = {"team": qs.get("team", [""])[0], "name": qs.get("name", [""])[0]}
                else:
                    b = self._body()
                self._authorize_post(path, b)
                if self._user().get("token") and (path in SENSITIVE or path in TOKEN_NEVER):
                    raise ApiError("An API token can't do that. Sign in as an Administrator.", 403)
                self._confirm_password(path, b)
                before = app.store.settings if path == "/api/settings" else None
                out = self._post(path, b)
                self._audit(path, b, before)
                return self._json(200, out)
            except ApiError as e:
                if e.code == 403 and self._u not in (_UNSET, None):
                    self._audit(path, {}, None, ok=False, why=str(e))
                return self._json(e.code, {"error": str(e), **e.extra})
            except PhotoUnreadable as e:
                return self._json(e.code, {"error": str(e)})
            except TrimlightError as e:
                return self._json(502, {"error": str(e)})
            except ValueError as e:
                return self._json(400, {"error": str(e)})
            except Exception:
                log.exception("POST %s failed", path)
                return self._json(500, {"error": "Something went wrong. Details are in the log."})

        def _audit(self, path, b, before, ok=True, why=""):
            """4.17: who changed what, in the audit log (Setup › Accounts & access)."""
            if path in AUDIT_SKIP or (path == "/api/action" and b.get("action") in AUDIT_QUIET_ACTIONS):
                return
            try:
                u = self._user() or {}
                who = u.get("username") or "?"
                via = self.client_address[0] + (" (proxy)" if self._via_proxy else "")
                what = AUDIT_NAMES.get(path) or path.replace("/api/", "").replace("/", " › ")
                if path == "/api/action":
                    what = "Lights: " + str(b.get("action") or "")
                detail = why or _audit_detail(path, b, before)
                app.store.audit(who, what, detail, role=u.get("role"), via=via, ok=ok)
            except Exception:
                log.debug("audit failed", exc_info=True)

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
            if path == "/api/gameday/refresh":      # Administrators (not on the editor list)
                return app.gameday_refresh_soon()
            if path == "/api/holidays/refresh":     # Editors: a country's public holidays, now (3.19)
                return app.holidays_refresh(b.get("code"))
            if path == "/api/share":                # Editors: a share code for patterns (3.19)
                try:
                    return sharecode.encode_keys(app.store.settings.get("effects") or {}, b.get("keys"),
                                                 b.get("rotate"))
                except sharecode.ShareError as e:
                    raise ApiError(str(e)) from None
            if path in ("/api/share/show", "/api/share/automation", "/api/share/install"):   # 4.21
                return app.share_more(path.rsplit("/", 1)[-1], b)
            if path == "/api/share/open":           # Editors: what a share code holds, checked (3.19)
                try:
                    return sharecode.decode(b.get("code"))
                except sharecode.ShareError as e:
                    raise ApiError(str(e)) from None
            if path == "/api/alerts/settings":      # Administrators (not on the editor list)
                try:
                    return app.alerts.update(b)
                except alerts.AlertError as e:
                    raise ApiError(str(e))
            if path == "/api/alerts/test":
                try:
                    app.alerts.test()
                except alerts.AlertError as e:
                    raise ApiError(str(e), 502)
                return {"ok": True}
            if path == "/api/backups/restore":      # Administrators (not on the editor list)
                return app.restore_patterns(b.get("file"), b.get("ids"))
            if path == "/api/local/ports":          # Administrators (4.3)
                return app.local_ports(b.get("ports"), b.get("device"))
            if path == "/api/local/commands":       # Administrators (4.4)
                return app.local_commands(b.get("on"))
            if path == "/api/local/timer_on_quit":  # Administrators (4.17)
                return app.timer_on_quit(b.get("on"))
            if path == "/api/resync":               # Administrators (4.4)
                return app.resync_cloud()
            if path == "/api/local/backup":         # Administrators (4.3.6)
                return app.local_backup(b.get("device"))
            if path == "/api/local/effect":         # Administrators (4.22): Lightning / Snowflake
                return app.local_effect(b.get("id"), b.get("effect"), b.get("device"))
            if path == "/api/local/delete":         # Administrators (4.3)
                return app.local_delete(b.get("id"), b.get("name"), b.get("device"))
            if path == "/api/local/address":        # Administrators (4.5): one controller's address
                return app.local_address(b.get("device"), b.get("address"), bool(b.get("force")))
            if path == "/api/local/identify":       # Administrators (4.5): what's at an address
                return app.local_identify(b.get("address"))
            if path == "/api/textpattern":         # Editors: describe a pattern in words (3.18)
                from . import textpattern
                try:
                    v = int(b.get("variant") or 0)
                except (TypeError, ValueError):
                    v = 0
                try:
                    if b.get("ai"):
                        return app.ai_pattern(b.get("prompt"))
                    return textpattern.generate(b.get("prompt"), max(0, min(50, v)))
                except ValueError as e:
                    raise ApiError(str(e)) from None
            if path == "/api/musiclink":           # Editors: music from this computer (4.1)
                return app.musiclink(b)
            if path == "/api/local/discover":      # Administrators: find and match controllers (4.15)
                return app.local_discover(bool(b.get("scan")))
            if path == "/api/health/check":        # Editors: check the controllers now (4.15)
                return app.health_check(b.get("device"))
            if path == "/api/musiczones":          # Editors: zones that follow the music (4.13)
                return app.musiczones(b)
            if path == "/api/musiclink/address":   # Administrators
                return app.musiclink_address(b.get("address"))
            if path == "/api/musiclink/test":      # Administrators
                return app.musiclink_test(b.get("address"), bool(b.get("read")))
            if path == "/api/musiclink/find":      # Administrators
                return app.musiclink_find()
            if path == "/api/mood":                # Editors: mood follow, from the listening page (3.18)
                return app.mood(b.get("level"), b.get("tab"))
            if path == "/api/ai/settings":         # Administrators: the owner's own Anthropic API key
                key = b.get("key")
                if key is not None and (not isinstance(key, str) or len(key) > 300 or (key and not key.strip().startswith("sk-"))):
                    raise ApiError("That doesn't look like an Anthropic API key (they start with sk-).")
                model = b.get("model")
                if model is not None and (not isinstance(model, str) or (model and not re.fullmatch(r"[a-z0-9][a-z0-9.\-]{2,63}", model))):
                    raise ApiError("A model name looks like claude-haiku-5-5.")
                if "key" in b:
                    app.store.save_secrets(ai_key=key.strip() if key else None)
                if model is not None:
                    s = copy.deepcopy(app.store.settings)
                    if model:
                        s["ai"] = {**(s.get("ai") or {}), "model": model}
                    else:
                        s.pop("ai", None)
                    app.store.save_settings(s)
                return {"configured": bool(app.store.secrets.get("ai_key"))}
            if path == "/api/update/check":        # Administrators (not on the editor list)
                app.updates.check()
                return app.update_summary()
            if path == "/api/update/install":      # Administrators: install the new version (4.15)
                return app.update_install()
            if path == "/api/update/rollback":     # Administrators: go back to the previous version (4.15)
                return app.update_rollback()
            if path == "/api/update/auto":         # Administrators: install new versions by themselves (4.15)
                if not isinstance(b.get("auto"), bool):
                    raise ApiError("Say whether to install new versions by themselves (true or false).")
                app.updates.set_auto(b["auto"])
                return app.update_summary()
            if path == "/api/update/settings":
                if not isinstance(b.get("enabled"), bool):
                    raise ApiError("Say whether to check for new versions (true or false).")
                return app.updates.set_enabled(b["enabled"])
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
                    if b.get("device"):
                        # 4.10: the House tab's finder and scenes on one controller;
                        # the others keep showing what they were.
                        try:
                            # 4.16: remembers the choice it covers, for end_preview
                            ctrl.flash_one(str(b["device"]), eff, minutes * 60)
                        except ValueError as e:
                            raise ApiError(str(e)) from None
                    else:
                        ctrl.manual(True, obj=eff, expires_min=minutes)
                elif a == "on":
                    # No pattern named (the On button): tonight's scheduled one.
                    ctrl.manual(True, b.get("effect") or ctrl.default_on_effect())
                elif a == "off":
                    ctrl.manual(False)
                elif a == "one":
                    # 4.8: Home's controller cards: On, Off, a pattern or back to
                    # the schedule for one controller only.
                    dev, state = str(b.get("device") or ""), b.get("state")
                    if state not in ("on", "off", "schedule"):
                        raise ApiError("Choose on, off or schedule.")
                    try:
                        if state == "on":
                            ctrl.manual_one(dev, True, b.get("effect") or ctrl.default_on_effect(dev))
                        else:
                            ctrl.manual_one(dev, False if state == "off" else None)
                    except ValueError as e:
                        raise ApiError(str(e)) from None
                elif a == "end_preview":
                    # 4.16: calibration done, a finder closed: back to what showed before
                    ctrl.end_preview(str(b["device"]) if b.get("device") else None)
                elif a == "resume":
                    # force: the Schedule tab's "Run the schedule" (resend in full).
                    ctrl.resume(force=b.get("force") is True or str(b.get("force")).lower() == "true")
                elif a == "levels":
                    # "on": true (Home Assistant's brightness slider on an off
                    # light): turn on with tonight's pattern first.
                    if b.get("on") is True or str(b.get("on")).lower() == "true":
                        with ctrl.lock:
                            off = not ctrl._target(commit=False).on
                        if off:
                            ctrl.manual(True, ctrl.default_on_effect())
                    ctrl.set_levels(b.get("brightness"), b.get("speed"))
                elif a == "flash":
                    return app.flash_from(b)
                elif a == "dismiss_alert":
                    ctrl.dismiss_alert()
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
                    # Only blame the keys when Trimlight actually answered.
                    if getattr(e, "kind", "api") == "network":
                        raise ApiError(f"Couldn't check these with Trimlight. {e}", 502)
                    if getattr(e, "code", None) == 10002:
                        # 4.3.9: say what to check, not just the code.
                        raise ApiError("Trimlight didn't accept this Client ID and Client Secret (code 10002). Copy both "
                                       "again from Trimlight's API credentials page, exactly as shown, and check that this "
                                       "computer's date and time are right (Trimlight checks them too).", 400)
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
            if path == "/api/tokens":                 # Administrators (4.17): a token for an integration
                name = str(b.get("name") or "").strip()
                role = b.get("role")
                days = b.get("days")
                if not name or len(name) > 60:
                    raise ApiError("Name the token (who uses it, like Home Assistant), up to 60 characters.")
                if role not in ("viewer", "editor", "admin"):
                    raise ApiError("Choose what the token can do: viewer, editor or admin.")
                if days is not None and (isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= 3650):
                    raise ApiError("A token lasts 1 to 3650 days, or until revoked.")
                if len(app.store.tokens()) >= 50:
                    raise ApiError("50 tokens is the most. Revoke one you no longer use.")
                return app.store.new_token(name, role, days)
            if path == "/api/backup/encrypted":       # Administrators (4.17)
                return app.encrypted_backup(b.get("passphrase"), bool(b.get("photos")))
            if path == "/api/backup/restore":
                return app.restore_encrypted(b.get("backup"), b.get("passphrase"), b.get("accounts", True) is not False)
            if path == "/api/tokens/revoke":
                if not app.store.revoke_token(str(b.get("id", ""))):
                    raise ApiError("No such token.", 404)
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
            if path == "/api/lan_allow":
                if not self._local():
                    raise ApiError("Do this on the computer the app runs on: Windows asks for permission there.", 403)
                if platform.system() != "Windows":
                    raise ApiError("This button is for Windows. See the manual for other systems.")
                r = winfirewall.allow(self.server.server_address[1])
                if not r.get("ok"):
                    raise ApiError(r.get("error") or "Windows Firewall wasn't changed.")
                return r
            if path == "/api/awake":
                try:
                    return app.awake.set_enabled(bool(b.get("enabled")))
                except OSError as e:
                    raise ApiError(f"Couldn't save that: {e}")
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
                app.save_photo(f, raw)
                return {"ok": True}
            if path == "/api/photo/upload":
                f = app.photo_path(str(b.get("side", "")))
                raw = self._read_raw()
                if not raw:
                    raise ApiError("No photo was sent.")
                app.save_photo(f, shrink_photo(raw))
                return {"ok": True}
            if path == "/api/automation/try":
                return app.automation_try(str(b.get("id", "")))
            if path in ("/api/studio/compose", "/api/studio/describe", "/api/studio/play", "/api/studio/stop",
                        "/api/studio/save"):          # 4.20: Studio
                return app.studio(path.rsplit("/", 1)[-1], b)
            if path == "/api/sync":                   # 4.21: controllers started together
                if not app.ctrl:
                    raise ApiError("Set up first.", 409)
                try:
                    return app.ctrl.sync_now()
                except ValueError as e:
                    raise ApiError(str(e)) from None
            if path == "/api/fade/try":               # 4.19
                if not app.ctrl:
                    raise ApiError("Set up first.", 409)
                try:
                    return app.ctrl.try_fade(str(b.get("effect", "")), min(8, max(1, int(b.get("seconds") or 3))))
                except ValueError as e:
                    raise ApiError(str(e)) from None
            if path == "/api/weather/looks":          # 4.19: Administrators (weather is a household setting)
                return app.weather_looks(b.get("temperature", True) is not False)
            if path == "/api/presence":
                return app.presence_set(b.get("person"), b.get("state"), "set by hand")
            if path == "/api/automation/check":
                return app.automation_check(str(b.get("id", "")))
            if path == "/api/sound/upload":
                return app.sound_upload(str(b.get("team", "")), self._read_raw(), str(b.get("name", "")))
            if path == "/api/sound/delete":
                return app.sound_delete(str(b.get("team", "")))
            if path == "/api/sound/test":
                return app.sound_test(str(b.get("team", "")))
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
                # (autostart is imported for the whole module: importing it in
                # here made it a local name in all of _post, which broke
                # Settings > Start automatically.)
                at_login = autostart.status(app.base)["enabled"]
                # 4.16.5: say so in the log (a quiet log otherwise looked like a crash)
                log.info("Quit from this computer's page: the schedule stops until EaveLuxOS starts again%s.",
                         " (it starts by itself at the next sign-in)" if at_login else "")

                def quit_now():
                    # 4.17: the controller's own timers take over, when asked
                    app.hand_over()
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
            if body["action"] == "status":          # read only: what the lights are doing
                return self._json(200, self._hook_state())
            if self.command != "POST":
                return self._json(405, {"error": "Only status can be read with GET; other actions need POST."})
            if body["action"] == "event":
                # 4.11: a named event for automations, e.g. POST /api/hook/event {"name": "doorbell"}
                name = str(body.get("name") or "").strip().lower()[:40]
                if not name:
                    return self._json(400, {"error": "Name the event: {\"name\": \"doorbell\"}."})
                if app.ctrl is None:            # Review #6: before setup, not a crash
                    return self._json(409, {"error": "Finish setup first."})
                done = app._auto_event({"type": "webhook", "name": name})
                app.ctrl.note(f"Webhook event '{name}' from {self.client_address[0]}")
                app.store.audit("webhook", f"Webhook event: {name}", "; ".join(done or [])[:400], role="webhook",
                                via=self.client_address[0])
                return self._json(200, {**self._hook_state(), "automations": done})
            if body["action"] == "presence":
                # 4.18: a phone says someone arrived or left:
                # POST /api/hook/presence {"person": "Chris", "state": "home"}
                try:
                    r = app.presence_set(body.get("person"), body.get("state"), "webhook")
                except ApiError as e:
                    return self._json(e.code, {"error": str(e)})
                app.store.audit("webhook", f"Webhook: {r['person']} {'arrived' if r['state'] == 'home' else 'left'}",
                                "; ".join(r["automations"] or [])[:400], role="webhook", via=self.client_address[0])
                return self._json(200, {**self._hook_state(), **{k: r[k] for k in ("person", "state", "changed", "settling", "home", "automations")}})
            if body["action"] not in ("flash", "stop_flash", "on", "off", "resume", "levels", "music", "stop_music",
                                      "dismiss_alert"):
                return self._json(400, {"error": "unknown action"})
            r = self._post("/api/action", body)
            app.ctrl.note(f"Webhook '{body['action']}' from {self.client_address[0]}")
            app.store.audit("webhook", f"Webhook: {body['action']}", _audit_detail("/api/action", body, None), role="webhook",
                            via=self.client_address[0])
            out = self._hook_state()
            if isinstance(r, dict) and "flash_started" in r:
                out["flash_started"] = r["flash_started"]   # false: something more important is showing
            return self._json(200, out)

        def _hook_state(self) -> dict:
            """What webhooks reply: for Home Assistant's sensor, light and
            pattern list. Keeps the fields earlier versions sent."""
            st = app.ctrl.status()
            t, lv = st["target"], st.get("levels") or {}
            effects = app.ctrl.cfg.effects
            return {"ok": True, "on": bool(t["on"]), "effect": t["effect"], "effect_key": t.get("effect_key"),
                    "reason": t["reason"], "source": t.get("source"), "until": t.get("until"),
                    "brightness": lv.get("brightness"), "speed": lv.get("speed"),
                    "flash": bool((st.get("flash") or {}).get("active")), "music": bool((st.get("music") or {}).get("active")),
                    "patterns": sorted(({"key": k, "label": e.label} for k, e in effects.items()), key=lambda p: p["label"].lower())}

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
        # 4.16.5: each connection is looked at before the handshake: a plain
        # http:// request (an old bookmark, a typed address) is sent on to
        # https:// instead of "didn't send any data"
        srv.tls_ctx = ctx
        srv.ca_provider = app.phone_ca         # 4.18.2: the root certificate for phones, over plain http too
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

    tls_ctx = None             # set by make_server when HTTPS is on
    ca_provider = None         # 4.18.2: () -> the mkcert root certificate, or None

    def finish_request(self, request, client_address):
        request.settimeout(30)  # covers the TLS handshake as well as slow clients
        if self.tls_ctx is None:
            return super().finish_request(request, client_address)
        try:
            first = request.recv(1, socket.MSG_PEEK)
        except OSError:
            return
        if not first:
            return
        if first[0] != 0x16:                 # not a TLS handshake: plain HTTP
            return _to_https(request, self.server_address[1], self.ca_provider)
        tls = self.tls_ctx.wrap_socket(request, server_side=True)   # the handshake, in this request's thread
        try:
            super().finish_request(tls, client_address)
        finally:
            try:
                tls.close()
            except OSError:
                pass


_HOST_OK = re.compile(r"^(\[[0-9A-Fa-f:.]+\]|[A-Za-z0-9.-]{1,253})(:\d{1,5})?$")


def _to_https(sock, port: int, ca_provider=None):
    """4.16.5: answer a plain http:// request on the HTTPS port with a
    temporary redirect to the same address on https:// (temporary, so
    turning HTTPS off later doesn't leave browsers stuck on it).
    4.18.2: except /trust and /ca.crt, which a phone needs before it trusts
    the certificate (Set up this phone): the public root certificate and a
    page that says what to do with it. Nothing else is ever sent unencrypted."""
    data = b""
    try:
        sock.settimeout(5)
        while b"\r\n\r\n" not in data and len(data) < 8192:
            chunk = sock.recv(2048)
            if not chunk:
                break
            data += chunk
    except OSError:
        pass
    head = data.split(b"\r\n\r\n", 1)[0].decode("latin-1", "replace").split("\r\n")
    parts = head[0].split(" ") if head and head[0] else []
    path = parts[1] if len(parts) >= 3 and parts[1].startswith("/") and not parts[1].startswith("//") else "/"
    if any(c in path for c in "\r\n\\") or len(path) > 2048:
        path = "/"
    host = "localhost"
    for line in head[1:]:
        k, _, v = line.partition(":")
        if k.strip().lower() == "host" and _HOST_OK.match(v.strip()):
            host = v.strip()
            break
    name = host.rsplit(":", 1)[0] if not host.endswith("]") and host.count(":") == 1 else host
    if host.startswith("[") and "]:" in host:
        name = host.rsplit(":", 1)[0]
    where = f"https://{name}:{port}{path}"
    bare = path.split("?", 1)[0]
    if bare in ("/trust", "/ca.crt") and ca_provider is not None:
        try:
            ca = ca_provider()
        except Exception:
            ca = None
        if bare == "/ca.crt" and ca:
            out, ctype, extra = ca["pem"], b"application/x-x509-ca-cert", b'Content-Disposition: attachment; filename="EaveLuxOS-root.crt"\r\n'
        else:
            out, ctype, extra = _trust_page(ca, f"https://{name}:{port}/#phone").encode(), b"text/html; charset=utf-8", b""
        try:
            sock.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: " + ctype + b"\r\nContent-Length: " + str(len(out)).encode()
                         + b"\r\nCache-Control: no-store\r\nX-Content-Type-Options: nosniff\r\n"
                         + b"Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'\r\n"
                         + extra + b"Connection: close\r\n\r\n" + out)
        except OSError:
            pass
        return
    body = b"This address uses https://. Opening " + where.encode() + b"\n"
    try:
        sock.sendall(b"HTTP/1.1 307 Temporary Redirect\r\nLocation: " + where.encode()
                     + b"\r\nContent-Type: text/plain; charset=utf-8\r\nContent-Length: " + str(len(body)).encode()
                     + b"\r\nConnection: close\r\n\r\n" + body)
    except OSError:
        pass
