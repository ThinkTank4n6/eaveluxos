# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""4.22.2: a "Start EaveLuxOS" link (eaveluxos://start) for this computer.

Reported on Windows: after Quit, the EaveLuxOS icon on the desktop (the
browser's installed app, "Open in app") only showed "Can't reach EaveLuxOS",
because it is a window onto the program, not the program. A browser page
can't start a program, but it can open a link the computer knows. So each
time the program starts, it tells this computer (for this user only, no
administrator rights) that eaveluxos:// links start it:

  Windows  HKEY_CURRENT_USER\\Software\\Classes\\eaveluxos
  Linux    ~/.local/share/applications/eaveluxos-start.desktop (+ xdg-mime)
  Mac      the app's Info.plist (CFBundleURLTypes, set when the .app is built)

The link never passes anything to the program: whatever follows
"eaveluxos:" is ignored (no %1 or %u), so a web page can at most start
EaveLuxOS, which the browser asks about first. Pages on this computer show a
Start EaveLuxOS button when the program isn't running."""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

SCHEME = "eaveluxos"
LINK = SCHEME + "://start"


def command(app_dir: Path) -> list[str]:
    """What the link starts: the program, without opening another browser tab
    (the page that was waiting reloads itself)."""
    from .autostart import launch_command
    return [c for c in launch_command(app_dir) if c != "--open"]


def supported(system: str | None = None, frozen: bool | None = None) -> bool:
    system = system or platform.system()
    frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    return system in ("Windows", "Linux") or (system == "Darwin" and frozen)


def _win_quote(args) -> str:
    return " ".join(f'"{a}"' for a in args)


def _desktop_quote(a: str) -> str:
    """One Exec argument in a .desktop file (quoted, with ", `, $ and \\
    escaped; % doubled, so nothing is a field code)."""
    for ch in ('\\', '"', '`', '$'):
        a = a.replace(ch, '\\' + ch)
    return '"' + a.replace("%", "%%") + '"'


def register(app_dir: Path, system: str | None = None, winreg=None, home: Path | None = None, run=subprocess.run) -> bool:
    """Make eaveluxos:// start this copy. Writes only when something differs.
    Returns True when the link works on this computer (as far as can be told)."""
    system = system or platform.system()
    cmd = command(app_dir)
    if system == "Windows":
        if winreg is None:
            import winreg                                     # noqa: F811 (Windows only)
        want = _win_quote(cmd)
        base = "Software\\Classes\\" + SCHEME
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, base + r"\shell\open\command") as k:
                if winreg.QueryValueEx(k, "")[0] == want:
                    return True
        except OSError:
            pass
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base) as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, "URL:EaveLuxOS")
            winreg.SetValueEx(k, "URL Protocol", 0, winreg.REG_SZ, "")
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base + r"\DefaultIcon") as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, f'"{cmd[0]}",0')
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base + r"\shell\open\command") as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, want)
        return True
    if system == "Linux":
        home = home or Path.home()
        apps = Path(os.environ.get("XDG_DATA_HOME") or home / ".local/share") / "applications"
        f = apps / "eaveluxos-start.desktop"
        text = ("[Desktop Entry]\nType=Application\nName=Start EaveLuxOS\nNoDisplay=true\n"
                f"Exec={' '.join(_desktop_quote(c) for c in cmd)}\n"
                f"MimeType=x-scheme-handler/{SCHEME};\n")
        try:
            if not f.exists() or f.read_text(encoding="utf-8") != text:
                apps.mkdir(parents=True, exist_ok=True)
                f.write_text(text, encoding="utf-8")
        except OSError:
            return False
        if shutil.which("xdg-mime"):
            try:
                run(["xdg-mime", "default", f.name, f"x-scheme-handler/{SCHEME}"], capture_output=True, timeout=10)
            except (OSError, subprocess.SubprocessError):
                return False
            return True
        return False
    return supported(system)          # Mac: the .app carries it (packaging/build.py)
