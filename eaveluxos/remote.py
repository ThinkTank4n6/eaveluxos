# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""4.27: use EaveLuxOS away from home with Tailscale (Setup › Accounts &
access › Away from home).

Tailscale (free for personal use) joins this computer and your phone into a
private network of their own, encrypted end to end, with no port opened on the
router. The recommended way uses **Tailscale Serve**: Tailscale gives this
computer an https://NAME.TAILNET.ts.net address with a real certificate, so
phones need no certificate installed, and passes requests on to the app here.

This module only looks: whether Tailscale is installed and connected, this
computer's Tailscale name and address, and whether Serve already points at the
app. It never changes Tailscale's settings; the page shows the one command to
run. Requests through Serve come from 127.0.0.1 with X-Forwarded-For, so the
app treats them as from away (never as this computer), as with any proxy.
"""
from __future__ import annotations

import ipaddress
import json
import os
import platform
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

CACHE = 30          # seconds a look at Tailscale is kept
TIMEOUT = 6
NAME_RE = re.compile(r"[a-z0-9-]{1,63}(\.[a-z0-9-]{1,63}){1,6}")
TAILNET = ipaddress.ip_network("100.64.0.0/10")

_cache: tuple[float, dict] = (0.0, {})
_lock = threading.Lock()


def find_cli(system: str | None = None) -> str | None:
    """The tailscale command: on the PATH, or where the installers put it."""
    system = system or platform.system()
    found = shutil.which("tailscale")
    if found:
        return found
    cands = []
    if system == "Windows":
        for env in ("ProgramFiles", "ProgramFiles(x86)"):
            if os.environ.get(env):
                cands.append(Path(os.environ[env]) / "Tailscale" / "tailscale.exe")
    elif system == "Darwin":
        cands.append(Path("/Applications/Tailscale.app/Contents/MacOS/Tailscale"))
    for c in cands:
        if c.is_file():
            return str(c)
    return None


def _run(cli, args, run):
    kw = {"capture_output": True, "text": True, "timeout": TIMEOUT}
    if os.name == "nt":
        kw["creationflags"] = 0x08000000          # CREATE_NO_WINDOW: no console flashes up
    return run([cli, *args], **kw)


def parse_status(text: str) -> dict:
    """`tailscale status --json` -> running, address, name."""
    try:
        st = json.loads(text)
    except ValueError:
        return {"running": False, "error": "Tailscale's answer couldn't be read."}
    if not isinstance(st, dict):
        return {"running": False, "error": "Tailscale's answer couldn't be read."}
    me = st.get("Self") if isinstance(st.get("Self"), dict) else {}
    ips = [str(i) for i in (me.get("TailscaleIPs") or []) if isinstance(i, str)]
    v4 = next((i for i in ips if _in_tailnet(i)), None)
    name = str(me.get("DNSName") or "").rstrip(".").lower()
    if not NAME_RE.fullmatch(name):
        name = ""
    state = str(st.get("BackendState") or "")
    return {"running": state == "Running", "state": state, "ip": v4, "name": name,
            "https_names": [str(n).rstrip(".").lower() for n in (st.get("CertDomains") or []) if isinstance(n, str)]}


def _in_tailnet(ip: str) -> bool:
    try:
        return ipaddress.ip_address(ip) in TAILNET
    except ValueError:
        return False


def serve_targets(text: str) -> list[str]:
    """Where `tailscale serve status --json` sends requests (proxy targets)."""
    try:
        st = json.loads(text)
    except ValueError:
        return []
    out = []

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k == "Proxy" and isinstance(v, str):
                    out.append(v)
                else:
                    walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(st)
    return out


def points_here(targets, port: int) -> bool:
    for t in targets:
        m = re.match(r"^(?:https?(?:\+insecure)?://)?(localhost|127\.0\.0\.1|\[::1\])?:?(\d+)(/.*)?$", t.strip())
        if m and int(m.group(2)) == int(port):
            return True
    return False


def look(port: int, run=subprocess.run, system: str | None = None, fresh=False) -> dict:
    """What the Away from home panel shows. Kept for CACHE seconds."""
    global _cache
    with _lock:
        if not fresh and time.time() - _cache[0] < CACHE and _cache[1].get("port") == port:
            return dict(_cache[1])
    cli = find_cli(system)
    out = {"port": port, "installed": bool(cli), "running": False, "ip": None, "name": "", "serve": False}
    if cli:
        try:
            r = _run(cli, ["status", "--json"], run)
            out.update(parse_status(r.stdout or ""))
            if not out.get("running") and not out.get("error"):
                out["error"] = "Tailscale is installed but not connected. Open Tailscale and sign in."
        except (OSError, subprocess.SubprocessError) as e:
            out["error"] = f"Tailscale didn't answer ({e.__class__.__name__})."
        if out.get("running"):
            try:
                r = _run(cli, ["serve", "status", "--json"], run)
                out["serve"] = points_here(serve_targets(r.stdout or ""), port)
            except (OSError, subprocess.SubprocessError):
                pass
    with _lock:
        _cache = (time.time(), out)
    return dict(out)


def known_name() -> str:
    """This computer's Tailscale name from the last look, for the Host check."""
    with _lock:
        return _cache[1].get("name") or ""


def serve_command(port: int, https: bool, system: str | None = None) -> str:
    system = system or platform.system()
    cli = "tailscale"
    if system == "Darwin" and not shutil.which("tailscale"):
        cli = "/Applications/Tailscale.app/Contents/MacOS/Tailscale"
    # Tailscale's documentation: only 127.0.0.1 (not "localhost") is supported for http proxies
    target = f"https+insecure://127.0.0.1:{int(port)}" if https else f"http://127.0.0.1:{int(port)}"
    return f"{cli} serve --bg {target}"
