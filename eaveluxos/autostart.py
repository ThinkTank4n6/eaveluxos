# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""'Start automatically' switch, without admin rights:
  Windows  a hidden launcher in the user's Startup folder
  macOS    a LaunchAgent in ~/Library/LaunchAgents
  Linux    a systemd user service (starts at login; see note about boot)
"""
import os
import platform
from xml.sax.saxutils import escape
import subprocess
import sys
from pathlib import Path

NAME = "eaveluxos"


def launch_command(app_dir: Path) -> list[str]:
    """How to start the app: the bundled executable, or Python + main.py."""
    if getattr(sys, "frozen", False):
        return [sys.executable, "run"]
    return [_python_gui(), str(app_dir / "main.py"), "run"]


def _python_gui():
    exe = Path(sys.executable)
    if platform.system() == "Windows":
        w = exe.with_name("pythonw.exe")
        return str(w if w.exists() else exe)
    return str(exe)


def _paths(app_dir: Path):
    system = platform.system()
    if system == "Windows":
        startup = Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs/Startup"
        return system, startup / "EaveLuxOS.vbs"
    if system == "Darwin":
        return system, Path.home() / "Library/LaunchAgents/com.eaveluxos.plist"
    return system, Path.home() / ".config/systemd/user" / f"{NAME}.service"


def _legacy_paths():
    """Start-at-login entries made under earlier names (LumaOS, Trimlight Scheduler)."""
    system = platform.system()
    if system == "Windows":
        startup = Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs/Startup"
        return [startup / "LumaOS.vbs", startup / "Trimlight Scheduler.vbs"]
    if system == "Darwin":
        agents = Path.home() / "Library/LaunchAgents"
        return [agents / "com.lumaos.plist", agents / "com.trimlight-scheduler.plist"]
    units = Path.home() / ".config/systemd/user"
    return [units / "lumaos.service", units / "trimlight-scheduler.service"]


def _remove_legacy():
    for old in _legacy_paths():
        if old.exists():
            if old.suffix == ".service":
                subprocess.run(["systemctl", "--user", "disable", old.name], capture_output=True)
            old.unlink(missing_ok=True)


def migrate_legacy(app_dir: Path) -> bool:
    """If the old name's start-at-login entry exists, replace it with EaveLuxOS's."""
    if not any(p.exists() for p in _legacy_paths()):
        return False
    try:
        set_enabled(app_dir, True)
    except (OSError, RuntimeError):
        return False
    return True


def repoint(app_dir: Path) -> bool:
    """Windows: if "Start automatically" is on but starts another copy of the
    app (an older version's folder), make it start this one. Returns True if
    it changed anything."""
    system, path = _paths(app_dir)
    if system != "Windows" or not path.exists():
        return False
    target = str(Path(launch_command(app_dir)[-2 if not getattr(sys, "frozen", False) else 0]))
    try:
        if target in path.read_text(encoding="locale", errors="replace"):
            return False
        set_enabled(app_dir, True)
    except (OSError, RuntimeError):
        return False
    return True


def status(app_dir: Path) -> dict:
    system, path = _paths(app_dir)
    note = None
    if system == "Linux":
        note = ("Starts when you log in. To start at power-on without logging in, run once: "
                "loginctl enable-linger $USER")
    return {"supported": system in ("Windows", "Darwin", "Linux"),
            "enabled": path.exists() or any(p.exists() for p in _legacy_paths()), "system": system,
            "note": note}


def set_enabled(app_dir: Path, enabled: bool) -> dict:
    system, path = _paths(app_dir)
    cmd = launch_command(app_dir)
    _remove_legacy()
    if not enabled:
        if system == "Linux" and path.exists():
            subprocess.run(["systemctl", "--user", "disable", f"{NAME}.service"], capture_output=True)
        path.unlink(missing_ok=True)
        return status(app_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    if system == "Windows":
        quoted = " ".join(f'""{c}""' if " " in c or "\\" in c else c for c in cmd)
        path.write_text(f'CreateObject("Wscript.Shell").Run "{quoted}", 0, False\r\n')
    elif system == "Darwin":
        path.write_text(encoding="utf-8", data=f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.eaveluxos</string>
  <key>ProgramArguments</key><array>{"".join(f"<string>{escape(c)}</string>" for c in cmd)}</array>
  <key>EnvironmentVariables</key><dict><key>EAVELUXOS_SUPERVISED</key><string>1</string></dict>
  <key>WorkingDirectory</key><string>{escape(str(app_dir))}</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
</dict></plist>
""")
    else:
        path.write_text(encoding="utf-8", data=f"""[Unit]
Description=EaveLuxOS
After=network-online.target

[Service]
WorkingDirectory={app_dir}
Environment=EAVELUXOS_SUPERVISED=1
ExecStart={" ".join(f'"{c}"' if c != "run" else c for c in cmd)}
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
""")
        r = subprocess.run(["systemctl", "--user", "enable", f"{NAME}.service"], capture_output=True, text=True)
        if r.returncode != 0:
            path.unlink(missing_ok=True)
            raise RuntimeError("Couldn't register with systemd: " + (r.stderr.strip() or "unknown error"))
    return status(app_dir)
