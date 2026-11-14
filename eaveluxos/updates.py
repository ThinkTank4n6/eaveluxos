# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Tell the owner when a newer EaveLuxOS has been published (3.14).

Once a day the app computer asks GitHub for the project's latest release
(https://api.github.com/repos/ThinkTank4n6/eaveluxos/releases/latest), over
the same verified HTTPS as Trimlight's cloud. Nothing about this household is
sent; GitHub sees an ordinary request with this app's version in the
User-Agent. It only reads: nothing is downloaded or installed by itself.

Everything fetched is data. Only a version number, a date, release notes
(as plain text, capped) and links that point into this project on GitHub are
kept. A redirect is refused. Administrators can turn the check off; the
choice and the last answer are kept in data/updates.json.
"""
import json
import logging
import os
import platform
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from .trust import CERT_HELP, client_context, is_cert_failure
from .version import VERSION

log = logging.getLogger("eaveluxos.updates")
REPO = "ThinkTank4n6/eaveluxos"
API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
PAGE_PREFIX = f"https://github.com/{REPO}/"
RELEASES_URL = f"https://github.com/{REPO}/releases/latest"
EVERY = 24 * 3600          # a normal check
RETRY = 6 * 3600           # after a failed one
FIRST_DELAY = 60           # after starting: let the lights come up first
MAX_BYTES = 512_000
NOTES_MAX = 4000
TAG_RE = re.compile(r"v?(\d{1,4})\.(\d{1,4})\.(\d{1,4})")


class UpdateError(Exception):
    pass


def parse_version(s) -> tuple | None:
    m = TAG_RE.fullmatch(str(s or "").strip())
    return tuple(int(x) for x in m.groups()) if m else None


def _ours(url) -> str | None:
    """A link kept only if it points into this project on GitHub."""
    url = str(url or "")
    return url if url.startswith(PAGE_PREFIX) and not any(c in url for c in '"<> \n\r\t') else None


def asset_for_this_computer(names) -> str | None:
    """Which download fits the computer this copy runs on. None when it runs
    from source (then the release page is the link)."""
    if not getattr(sys, "frozen", False):
        return None
    sysname, machine = platform.system(), platform.machine().lower()
    want = []
    if sysname == "Windows":
        want = [lambda n: n == "EaveLuxOS-Windows.zip"]
    elif sysname == "Darwin":
        want = [lambda n: n.endswith(".dmg")]
    elif sysname == "Linux":
        arm = machine in ("aarch64", "arm64")
        want = [lambda n: n.endswith("_arm64.deb" if arm else "_amd64.deb"),
                lambda n: n == ("EaveLuxOS-Linux-aarch64.tar.gz" if arm else "EaveLuxOS-Linux-x86_64.tar.gz")]
    for test in want:
        for n in names:
            if test(n):
                return n
    return None


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _default_fetch(url: str) -> bytes:
    opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=client_context()), _NoRedirect)
    req = urllib.request.Request(url, headers={"User-Agent": f"EaveLuxOS/{VERSION}",
                                               "Accept": "application/vnd.github+json"})
    try:
        with opener.open(req, timeout=15) as r:
            raw = r.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as e:
        e.close()
        if e.code == 404:
            raise UpdateError("No release has been published yet.") from None
        if e.code in (403, 429):
            raise UpdateError("GitHub asked to wait before checking again.") from None
        if 300 <= e.code < 400:
            raise UpdateError("GitHub sent the check somewhere else (the project may have moved or been renamed), "
                              "and this app doesn't follow redirects. See the project page for news.") from None
        raise UpdateError(f"GitHub answered {e.code}.") from None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        if is_cert_failure(e):
            raise UpdateError(CERT_HELP.format(who="GitHub")) from None
        raise UpdateError(f"Couldn't reach GitHub: {getattr(e, 'reason', e)}") from None
    if len(raw) > MAX_BYTES:
        raise UpdateError("GitHub's answer was too large.")
    return raw


def read_release(raw: bytes) -> dict:
    """Keep only what's needed from GitHub's answer, and only safe values."""
    try:
        r = json.loads(raw)
    except ValueError:
        raise UpdateError("GitHub's answer wasn't readable.") from None
    if not isinstance(r, dict):
        raise UpdateError("GitHub's answer wasn't readable.")
    v = parse_version(r.get("tag_name"))
    if v is None:
        raise UpdateError("The latest release has no version number.")
    if r.get("draft") or r.get("prerelease"):
        raise UpdateError("The latest release is a test version.")
    assets = {}
    for a in r.get("assets") or []:
        if isinstance(a, dict) and isinstance(a.get("name"), str):
            u = _ours(a.get("browser_download_url"))
            if u and len(assets) < 30:
                assets[a["name"][:120]] = u
    notes = r.get("body") if isinstance(r.get("body"), str) else ""
    pub = r.get("published_at") if isinstance(r.get("published_at"), str) else ""
    return {"version": ".".join(map(str, v)), "url": _ours(r.get("html_url")) or RELEASES_URL,
            "published": pub[:25], "notes": notes[:NOTES_MAX], "assets": assets}


class UpdateChecker:
    def __init__(self, data_dir: Path, fetch=None, now=time.time):
        self.path = Path(data_dir) / "updates.json"
        self.fetch = fetch or _default_fetch
        self.now = now
        self.lock = threading.Lock()
        self.state = self._load()
        self.next_at = self.now() + FIRST_DELAY
        self.thread = None
        self.stop = threading.Event()

    def _load(self) -> dict:
        """The saved state, with anything damaged or unexpected dropped, so a
        bad file can never break the Updates panel or the bar."""
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raw = None
        raw = raw if isinstance(raw, dict) else {}
        st = {"enabled": raw.get("enabled") if isinstance(raw.get("enabled"), bool) else True}
        lt = raw.get("latest")
        if isinstance(lt, dict) and parse_version(lt.get("version")):
            assets = lt.get("assets") if isinstance(lt.get("assets"), dict) else {}
            st["latest"] = {"version": ".".join(map(str, parse_version(lt["version"]))),
                            "url": _ours(lt.get("url")) or RELEASES_URL,
                            "published": str(lt.get("published") or "")[:25],
                            "notes": str(lt.get("notes") or "")[:NOTES_MAX],
                            "assets": {str(k)[:120]: _ours(v) for k, v in list(assets.items())[:30] if _ours(v)}}
        if isinstance(raw.get("checked"), (int, float)) and not isinstance(raw.get("checked"), bool):
            st["checked"] = raw["checked"]
        if isinstance(raw.get("error"), str):
            st["error"] = raw["error"][:300]
        return st

    def _save(self):
        try:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.state, indent=2), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError as e:
            log.warning("Couldn't save the update check: %s", e)

    # ------------------------------------------------------------- checking
    def check(self) -> dict:
        """Ask GitHub now. Returns the summary either way."""
        at = self.now()
        try:
            rel = read_release(self.fetch(API_URL))
            with self.lock:
                was = (self.state.get("latest") or {}).get("version")
                self.state.update(latest=rel, error=None, checked=at)
                self._save()
            self.next_at = at + EVERY
            if self.newer(rel["version"]) and rel["version"] != was:
                log.info("EaveLuxOS %s is available (this is %s): %s", rel["version"], VERSION, rel["url"])
        except UpdateError as e:
            with self.lock:
                self.state.update(error=str(e), checked=at)
                self._save()
            self.next_at = at + RETRY
            log.info("Update check: %s", e)
        return self.summary()

    @staticmethod
    def newer(version) -> bool:
        v, cur = parse_version(version), parse_version(VERSION)
        return bool(v and cur and v > cur)

    def set_enabled(self, on: bool) -> dict:
        with self.lock:
            self.state["enabled"] = bool(on)
            self._save()
        if on:
            self.next_at = min(self.next_at, self.now() + 5)
        return self.summary()

    def summary(self) -> dict:
        with self.lock:
            st = dict(self.state)
        latest = st.get("latest") or {}
        newer = st.get("enabled", True) and self.newer(latest.get("version"))
        name = asset_for_this_computer(list((latest.get("assets") or {}).keys())) if newer else None
        checked = st.get("checked")
        return {"enabled": bool(st.get("enabled", True)), "current": VERSION,
                "latest": latest.get("version"), "newer": bool(newer),
                "url": latest.get("url") or RELEASES_URL,
                "download": (latest.get("assets") or {}).get(name) if name else None, "download_name": name,
                "published": latest.get("published"), "notes": latest.get("notes") if newer else "",
                "error": st.get("error"), "from_source": not getattr(sys, "frozen", False),
                "checked_label": datetime.fromtimestamp(checked).strftime("%b %d, %I:%M %p").replace(" 0", " ") if checked else None}

    # ------------------------------------------------------------- background
    def _loop(self):
        while not self.stop.wait(30):
            if self.state.get("enabled", True) and self.now() >= self.next_at:
                try:
                    self.check()
                except Exception:          # never let this stop: it's only a notice
                    log.exception("Update check failed")
                    self.next_at = self.now() + RETRY

    def start(self):
        if self.thread is None:
            self.thread = threading.Thread(target=self._loop, daemon=True, name="updates")
            self.thread.start()
