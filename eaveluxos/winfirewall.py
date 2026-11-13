# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Why can't a phone open the app? On Windows it's usually the firewall:

- the network is set to Public, where Windows blocks incoming connections;
- someone pressed Cancel on the "Windows Defender Firewall has blocked some
  features of this app" prompt, which adds a rule that BLOCKS the app (a block
  rule wins over any allow rule);
- or there's simply no rule letting phones in.

check() reads these (no special rights needed). allow() fixes the last two
after one Windows permission (UAC) prompt on this computer: it switches off
block rules for this program and adds an allow rule for the app's port on
Private and Domain networks. It never changes a network from Public to
Private; the person decides that (see the manual).

Everything goes through PowerShell with the script passed as -EncodedCommand,
so paths with spaces or quotes can't break it, and the output read is enum
names (Public, Block, Inbound), which Windows doesn't translate."""
import base64
import os
import subprocess
import sys

RULE_PREFIX = "EaveLuxOS (port"
NO_WINDOW = 0x08000000   # CREATE_NO_WINDOW: no console flashes up from the windowed app


def rule_name(port: int) -> str:
    return f"{RULE_PREFIX} {int(port)})"


def program_path() -> str:
    """The program Windows sees listening: the app's .exe, or python(w).exe."""
    return sys.executable


def _ps_quote(s: str) -> str:
    return "'" + str(s).replace("'", "''") + "'"


def _encoded(script: str) -> str:
    return base64.b64encode(script.encode("utf-16-le")).decode("ascii")


def _powershell(script: str, run=subprocess.run, timeout: int = 40):
    return run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                "-EncodedCommand", _encoded(script)],
               capture_output=True, text=True, timeout=timeout, **({"creationflags": NO_WINDOW} if os.name == "nt" else {}))


def check_script(port: int, program: str) -> str:
    return f"""$ErrorActionPreference = 'SilentlyContinue'
'CATEGORY=' + ((Get-NetConnectionProfile | ForEach-Object {{ [string]$_.NetworkCategory }}) -join ',')
$blocked = Get-NetFirewallApplicationFilter -Program {_ps_quote(program)} | Get-NetFirewallRule |
  Where-Object {{ [string]$_.Direction -eq 'Inbound' -and [string]$_.Action -eq 'Block' -and [string]$_.Enabled -eq 'True' }}
'BLOCKED=' + (($blocked | ForEach-Object {{ $_.DisplayName }}) -join '|')
$allow = Get-NetFirewallRule -DisplayName {_ps_quote(rule_name(port))} |
  Where-Object {{ [string]$_.Enabled -eq 'True' -and [string]$_.Action -eq 'Allow' }}
'ALLOWED=' + [bool]$allow
"""


def allow_script(port: int, program: str) -> str:
    return f"""$ErrorActionPreference = 'Stop'
Get-NetFirewallApplicationFilter -Program {_ps_quote(program)} -ErrorAction SilentlyContinue | Get-NetFirewallRule |
  Where-Object {{ [string]$_.Direction -eq 'Inbound' -and [string]$_.Action -eq 'Block' }} | Disable-NetFirewallRule
Get-NetFirewallRule -DisplayName {_ps_quote(RULE_PREFIX + '*')} -ErrorAction SilentlyContinue | Remove-NetFirewallRule
New-NetFirewallRule -DisplayName {_ps_quote(rule_name(port))} -Direction Inbound -Action Allow -Protocol TCP `
  -LocalPort {int(port)} -Profile Private,Domain | Out-Null
"""


def parse_check(out: str) -> dict:
    vals = {}
    for line in (out or "").splitlines():
        k, sep, v = line.strip().partition("=")
        if sep and k in ("CATEGORY", "BLOCKED", "ALLOWED"):
            vals[k] = v.strip()
    cats = [c for c in vals.get("CATEGORY", "").split(",") if c]
    return {
        "networks": cats,                                    # Public / Private / DomainAuthenticated
        "public": "Public" in cats,
        "blocked_rules": [b for b in vals.get("BLOCKED", "").split("|") if b],
        "allowed": vals.get("ALLOWED", "").lower() == "true",
    }


def check(port: int, run=subprocess.run) -> dict:
    """What's in the way of phones on this computer, or {"error": ...}."""
    try:
        r = _powershell(check_script(port, program_path()), run=run)
    except (OSError, subprocess.SubprocessError) as e:
        return {"error": f"Couldn't check Windows Firewall ({e.__class__.__name__})."}
    if r.returncode != 0 and "CATEGORY=" not in (r.stdout or ""):
        return {"error": "Couldn't check Windows Firewall: " + ((r.stderr or "").strip().splitlines() or ["no details"])[-1]}
    return {**parse_check(r.stdout), "program": program_path(), "from_source": not getattr(sys, "frozen", False)}


def allow(port: int, run=subprocess.run) -> dict:
    """One Windows permission prompt on this computer; then check() again."""
    inner = _encoded(allow_script(port, program_path()))
    outer = ("try { $p = Start-Process -FilePath powershell -Verb RunAs -Wait -PassThru -WindowStyle Hidden "
             f"-ArgumentList '-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-EncodedCommand','{inner}'; "
             "exit $p.ExitCode } catch { 'DECLINED'; exit 1223 }")
    try:
        r = _powershell(outer, run=run, timeout=180)
    except (OSError, subprocess.SubprocessError) as e:
        return {"ok": False, "error": f"Couldn't change Windows Firewall ({e.__class__.__name__})."}
    if r.returncode == 1223 or "DECLINED" in (r.stdout or ""):
        return {"ok": False, "error": "Windows asked for permission and it wasn't given, so nothing changed."}
    if r.returncode != 0:
        return {"ok": False, "error": f"Windows Firewall wasn't changed (code {r.returncode})."}
    return {"ok": True, **check(port, run=run)}
