# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""The community pattern library (Patterns › Community).

Patterns live in a public GitHub repository: an index.json listing them and
one small file per pattern (see tools/community-library). New patterns arrive
as pull requests that the owner reviews, so only reviewed patterns appear.

This app computer fetches them only when someone opens the list, over the
same verified HTTPS as Trimlight's cloud. Everything fetched is data, never
code: sizes are capped, only known fields are kept, and each pattern passes
the same check as one saved by hand before it can be tried or added. Only
self-contained patterns are accepted (colors, or a built-in effect); never a
"saved" pattern, which would point at someone else's controller.
"""
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from .schedule import ConfigError, Effect
from .trust import CERT_HELP, client_context, is_cert_failure
from .version import VERSION

DEFAULT_URL = "https://raw.githubusercontent.com/ThinkTank4n6/eaveluxos-patterns/main/"
INDEX_MAX = 1_000_000
PATTERN_MAX = 100_000
CACHE_SECONDS = 15 * 60
ID_RE = re.compile(r"[a-z0-9][a-z0-9-]{0,59}")
HEX_RE = re.compile(r"#[0-9A-Fa-f]{6}")
PATTERN_KEYS = ("label", "colors", "counts", "custom_mode", "speed", "brightness", "exact_colors",
                "builtin", "pixel_len", "reverse")


class CommunityError(Exception):
    pass


class NotFound(CommunityError):
    pass


LOOPBACK = ("127.0.0.1", "localhost", "::1")


def base_url(settings: dict) -> str:
    """The library's address (settings: community.url, Administrators only),
    ending with /. HTTPS only; plain http just for this computer (testing)."""
    url = str(((settings or {}).get("community") or {}).get("url") or DEFAULT_URL).strip()
    u = urllib.parse.urlparse(url)
    if not (u.scheme == "https" or (u.scheme == "http" and u.hostname in LOOPBACK)) or not u.hostname:
        raise CommunityError("The community library address must start with https://")
    if u.query or u.fragment or u.username or u.password:
        raise CommunityError("The community library address can't contain ?, # or a user name.")
    return url if url.endswith("/") else url + "/"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect becomes an error, never a request somewhere else."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_opener = None


def _default_open(req):
    global _opener
    if _opener is None:
        _opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=client_context()), _NoRedirect)
    return _opener.open(req, timeout=15)


def _fetch_json(url: str, limit: int, opener=None):
    req = urllib.request.Request(url, headers={"User-Agent": f"EaveLuxOS/{VERSION}", "Accept": "application/json"})
    try:
        resp = (opener or _default_open)(req)
        with resp as r:
            raw = r.read(limit + 1)
    except urllib.error.HTTPError as e:
        e.close()                       # the refused response's connection
        if e.code == 404:
            raise NotFound("The community library isn't available yet (nothing was found at its address).") from None
        if 300 <= e.code < 400:
            raise CommunityError("The community library tried to send the app somewhere else, so it was ignored.") from None
        raise CommunityError(f"The community library answered with an error ({e.code}).") from None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        if is_cert_failure(e):
            raise CommunityError(CERT_HELP.format(who="the community library")) from None
        raise CommunityError(f"Couldn't reach the community library ({getattr(e, 'reason', e)}).") from None
    if len(raw) > limit:
        raise CommunityError("The community library sent more data than expected, so it was ignored.")
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise CommunityError("The community library sent something that isn't a pattern list.") from None


def _text(v, n: int) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip()[:n]


def clean_index(data) -> list[dict]:
    """The usable entries of index.json; anything malformed is skipped."""
    if not isinstance(data, dict) or not isinstance(data.get("patterns"), list):
        raise CommunityError("The community library's list is damaged.")
    out, seen = [], set()
    for e in data["patterns"][:2000]:
        if not isinstance(e, dict):
            continue
        pid = str(e.get("id", ""))
        if not ID_RE.fullmatch(pid) or pid in seen:
            continue
        colors = [c.upper() for c in (e.get("colors") or []) if isinstance(c, str) and HEX_RE.fullmatch(c)][:8]
        tags = [_text(t, 24).lower() for t in (e.get("tags") or []) if isinstance(t, str)][:8]
        out.append({"id": pid, "name": _text(e.get("name") or pid, 60), "author": _text(e.get("author"), 40),
                    "description": _text(e.get("description"), 200), "colors": colors, "tags": [t for t in tags if t]})
        seen.add(pid)
    return out


def clean_pattern(pid: str, data) -> dict:
    """A pattern file → a pattern definition this app accepts."""
    if not isinstance(data, dict) or not isinstance(data.get("pattern"), dict):
        raise CommunityError("That community pattern's file is damaged.")
    p = {k: v for k, v in data["pattern"].items() if k in PATTERN_KEYS}
    if "colors" not in p and "builtin" not in p:
        raise CommunityError("That community pattern has no colors or built-in effect.")
    p["label"] = _text(p.get("label") or data.get("name") or pid, 60)
    try:
        Effect.from_config("community", p)      # the same check as a pattern saved by hand
    except (ConfigError, ValueError, TypeError, KeyError) as e:
        raise CommunityError(f"That community pattern isn't valid ({e}).") from None
    if "colors" in p:
        p["colors"] = [str(c).upper() for c in p["colors"]]
    return p


class Library:
    def __init__(self, opener=None, clock=time.time):
        self.opener, self.clock = opener, clock
        self.lock = threading.Lock()
        self._cache: dict[str, tuple[float, list]] = {}

    def index(self, settings: dict, refresh: bool = False) -> dict:
        base = base_url(settings)
        with self.lock:
            hit = self._cache.get(base)
        if hit and not refresh and self.clock() - hit[0] < CACHE_SECONDS:
            return {"url": base, "patterns": hit[1], "fetched": hit[0]}
        items = clean_index(_fetch_json(base + "index.json", INDEX_MAX, self.opener))
        now = self.clock()
        with self.lock:
            self._cache[base] = (now, items)
        return {"url": base, "patterns": items, "fetched": now}

    def pattern(self, settings: dict, pid: str) -> dict:
        if not ID_RE.fullmatch(pid or ""):
            raise CommunityError("No such community pattern.")
        base = base_url(settings)
        try:
            data = _fetch_json(f"{base}patterns/{pid}.json", PATTERN_MAX, self.opener)
        except NotFound:
            raise CommunityError("That pattern has been removed from the community library. Tap Refresh for the current list.") from None
        return clean_pattern(pid, data)
