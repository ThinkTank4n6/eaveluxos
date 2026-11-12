#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""EaveLuxOS: true sunrise/sunset and DST-correct control of
Trimlight Edge lights, with a full point-and-click control app.

Most people never need these; double-click the launcher instead.

  python3 main.py run [--open]     start the app (--open also opens the browser)
  python3 main.py check            validate saved settings
  python3 main.py schedule [days]  print upcoming on/off times
  python3 main.py flash [minutes]  security flash via the running app
  python3 main.py port NUMBER      use a different web port (restart the app after)
  python3 main.py users            list accounts and their roles
  python3 main.py reset-password NAME   forgot it? set a new password for account NAME (signs it out everywhere)
  python3 main.py allow-host NAME  accept requests addressed to NAME (add --remove to undo)
  python3 main.py backup FILE      copy the whole database (settings, patterns, history) to FILE
  python3 main.py make-cert        make a self-signed HTTPS certificate (add --force to replace one)
  python3 main.py hwtest           guided test of your real controller (quit the app first)
"""
import json
import logging
import os
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from datetime import timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path

if sys.version_info < (3, 11):
    sys.exit("Python 3.11 or newer is required. Get it from https://www.python.org/downloads/")

# Bundled executable (PyInstaller): keep data next to the executable, not in
# the temporary folder the bundle unpacks to (that's wiped on every exit).
FROZEN = getattr(sys, "frozen", False)
HERE = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parent


def data_dir() -> Path:
    from eaveluxos.store import resolve_data_dir
    return resolve_data_dir(HERE)


def fatal(msg: str) -> int:
    """Report a startup failure where the user will see it. On Windows the
    launcher runs without a console, so a message box is the only visible way."""
    logging.getLogger("eaveluxos").error(msg)
    if sys.stdout:
        print(msg, file=sys.stderr)
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, msg, "EaveLuxOS", 0x10)
        except Exception:
            pass
    return 1


def setup_logging():
    try:
        log_dir = data_dir()
    except OSError:
        log_dir = None
    handlers = [RotatingFileHandler(log_dir / "eaveluxos.log", maxBytes=1_000_000, backupCount=3)] if log_dir else []
    if sys.stdout and sys.stdout.isatty() or "pythonw" not in sys.executable.lower():
        handlers.append(logging.StreamHandler())
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", handlers=handlers)


def already_running(port: int) -> bool:
    from eaveluxos.server import probe_app
    return probe_app(port)


def configured_port() -> tuple[str, int]:
    from eaveluxos.store import has_install, previous_data_dir, read_service_settings
    try:
        d = data_dir()
        if not has_install(d):          # first start on Windows: the earlier copy's port
            d = previous_data_dir(HERE, exclude=d) or d
        svc = read_service_settings(d)
        return str(svc.get("web_host", "0.0.0.0")), int(svc.get("web_port", 8787))
    except (OSError, ValueError, TypeError):
        return "0.0.0.0", 8787


def cmd_run(open_browser: bool):
    # Check for a running copy BEFORE starting anything: a second scheduler
    # would send its own commands to the lights.
    host, port = configured_port()
    url = f"http://localhost:{port}/"
    if already_running(port):
        print(f"EaveLuxOS is already running. Opening {url}")
        if open_browser:
            webbrowser.open(url)
        return 0
    from eaveluxos.server import App, make_server
    app = App(HERE, start=False)
    log = logging.getLogger("eaveluxos")
    server, tried = None, []
    # If another program (not this app) already uses the port, move to the next
    # free one and remember it, instead of failing silently in the background.
    for candidate in range(port, min(port + 20, 65536)):
        if candidate != port and already_running(candidate):
            print(f"EaveLuxOS is already running on port {candidate}.")
            if open_browser:
                webbrowser.open(f"http://localhost:{candidate}/")
            return 0
        try:
            server = make_server(app, host, candidate)
            break
        except OSError:
            tried.append(candidate)
    if server is None:
        return fatal(f"EaveLuxOS couldn't start: ports {port}-{port + 19} are all in use by other programs. "
                     "Choose another with: python3 main.py port NUMBER")
    if server.server_address[1] != port:
        port = server.server_address[1]
        url = f"http://localhost:{port}/"
        log.warning("Port %s is used by another program, so EaveLuxOS moved to port %s "
                    "(saved for next time; change it under Settings).", tried[0], port)
        settings = dict(app.store.settings)
        settings["service"] = {**settings.get("service", {}), "web_port": port}
        app.store.save_settings(settings)
    url = f"{getattr(app, 'scheme', 'http')}://localhost:{port}/"
    app.start()  # the port is ours now, so this is the only scheduler
    try:
        from eaveluxos import autostart
        if autostart.migrate_legacy(HERE):
            logging.getLogger("eaveluxos").info("Start-at-login entry updated to the EaveLuxOS name.")
        elif autostart.repoint(HERE):
            logging.getLogger("eaveluxos").info("Start automatically now starts this copy (%s).", HERE)
    except Exception:
        pass
    threading.Thread(target=server.serve_forever, daemon=True, name="web").start()
    log.info("EaveLuxOS is running. Open %s on this computer.", url)
    from eaveluxos.server import lan_addresses
    for ip in lan_addresses():
        log.info("On your phone (same Wi-Fi): %s://%s:%s/", app.scheme, ip, port)
    if not app.store.has_users():
        log.info("Setup code for finishing setup from a phone: %s", app.store.setup_code)
    if app.problem:
        log.info("Waiting for setup: %s", app.problem)
    if open_browser:
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        if app.ctrl:
            app.ctrl.stop_event.set()
        server.shutdown()
    return 0


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "run"
    if FROZEN and len(argv) == 1:
        argv = [argv[0], "run", "--open"]   # double-clicked: start and open the browser
    if cmd in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    setup_logging()
    if cmd == "run":
        try:
            return cmd_run("--open" in argv)
        except Exception as e:  # anything at startup: tell the user, don't vanish silently
            logging.getLogger("eaveluxos").exception("Startup failed")
            return fatal(f"EaveLuxOS couldn't start: {e}\n\nDetails are in eaveluxos.log in the data folder.")

    from eaveluxos.schedule import ConfigError, build_config
    from eaveluxos.store import Store
    store = Store(HERE)
    if cmd == "check":
        try:
            cfg = build_config(store.settings, store.secrets)
        except ConfigError as e:
            print(f"Not ready: {e}")
            return 2
        print(f"Settings OK: {len(cfg.effects)} patterns, {len(cfg.schedule.rules)} rules, "
              f"time zone {cfg.loc.tz_name} (daylight saving: {cfg.loc.dst_mode}).")
        return 0
    if cmd == "schedule":
        try:
            cfg = build_config(store.settings, store.secrets, need_secrets=False)
        except ConfigError as e:
            print(f"Not ready: {e}")
            return 2
        days = int(argv[2]) if len(argv) > 2 else 14
        start, prev = cfg.loc.now().date(), None
        for i in range(days):
            d = start + timedelta(days=i)
            s = cfg.loc.sun(d)
            abbr = s["noon"].tzname() if s["noon"] else ""
            w = cfg.schedule.day_plan(d)
            lights = f"{w.start:%I:%M %p} to {w.end:%I:%M %p %a} [{w.rule.name}]" if w else "off"
            mark = f"  <-- {abbr} begins" if prev and abbr != prev else ""
            prev = abbr
            sunset = f"{s['sunset']:%I:%M %p}" if s["sunset"] else "-"
            print(f"{d:%a %b %d}  sunset {sunset}  lights {lights}{mark}")
        return 0
    if cmd == "hwtest":
        _, port = configured_port()
        if already_running(port):
            print("Quit the app first (Settings > Quit the app), so it doesn't change the lights during the test.", file=sys.stderr)
            return 2
        from eaveluxos import hwtest
        return hwtest.run(store, store.dir)
    if cmd == "allow-host":
        if len(argv) < 3:
            print("Usage: python3 main.py allow-host NAME [--remove]", file=sys.stderr)
            return 2
        import re
        name = argv[2].strip().lower()
        if not re.fullmatch(r"[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)*", name):
            print("That isn't a valid host name.", file=sys.stderr)
            return 2
        n = dict(store.settings)
        svc = dict(n.get("service", {}))
        hosts = [h for h in svc.get("allowed_hosts", []) if h != name]
        if "--remove" not in argv:
            hosts.append(name)
        svc["allowed_hosts"] = hosts
        n["service"] = svc
        store.save_settings(n)
        print("Allowed host names: " + (", ".join(hosts) or "none") + ". Restart the app to apply.")
        return 0
    if cmd == "backup":
        if len(argv) < 3:
            print("Usage: python3 main.py backup FILE", file=sys.stderr)
            return 2
        import sqlite3
        dest = Path(argv[2]).expanduser()
        with store.lock:
            out = sqlite3.connect(dest)
            store.con.backup(out)
            out.close()
        try:
            os.chmod(dest, 0o600)
        except OSError:
            pass
        print(f"Database copied to {dest}. It contains your Trimlight credentials; keep it private.")
        if store.box.active and not os.environ.get("EAVELUXOS_SECRET_KEY"):
            print(f"The credentials in it are encrypted with {store.dir / 'secret.key'}. Back that file up too,")
            print("but store it somewhere separate from the database copy.")
        return 0
    if cmd == "make-cert":
        from eaveluxos.server import lan_addresses
        from eaveluxos.tlscert import make_cert
        try:
            path = make_cert(store.dir / "tls", store.settings.get("service", {}).get("allowed_hosts", []) or [],
                             lan_addresses(), force="--force" in argv)
        except RuntimeError as e:
            print(e, file=sys.stderr)
            return 2
        print(f"Certificate saved in {path.parent}. Restart the app; it then uses https:// addresses.")
        print("Each browser warns once that the certificate is self-signed; accept it on your own devices.")
        return 0
    if cmd == "users":
        rows = store.users()
        if not rows:
            print("No accounts yet. Open the app on this computer and create one under Settings > Accounts.")
        for u in rows:
            print(f"{u['username']:<24} {u['role']:<7} {'disabled' if u['disabled'] else ''}")
        return 0
    if cmd == "reset-password":
        # Recovery from the app computer: a new password for an account, which
        # is also re-enabled (and made an Administrator with --admin).
        args = [a for a in argv[2:] if not a.startswith("--")]
        if not args:
            print("Usage: python3 main.py reset-password NAME [--admin] [--stdin]", file=sys.stderr)
            print("Accounts: " + (", ".join(u["username"] for u in store.users()) or "none"), file=sys.stderr)
            return 2
        found = store.user_by_name(args[0])
        if "--stdin" in argv:
            pw = sys.stdin.readline().rstrip("\n")
        else:
            import getpass
            pw = getpass.getpass(f"New password for {args[0]}: ")
            if getpass.getpass("Type it again: ") != pw:
                print("The passwords don't match.", file=sys.stderr)
                return 2
        try:
            if found:
                u = found[0]
                store.save_user(u["id"], u["username"], "admin" if "--admin" in argv else u["role"], False, password=pw)
            else:
                store.save_user(None, args[0], "admin", password=pw)
        except ValueError as e:
            print(e, file=sys.stderr)
            return 2
        store.end_all_sessions() if not found else None
        print(f"Password for {args[0].lower()} is set{' (new Administrator account)' if not found else ''}, "
              "and that account is signed out everywhere.")
        return 0
    if cmd == "port":
        try:
            new = int(argv[2])
        except (IndexError, ValueError):
            print("Usage: python3 main.py port NUMBER   (1024-65535)", file=sys.stderr)
            return 2
        if not 1024 <= new <= 65535:
            print("Choose a port from 1024 to 65535.", file=sys.stderr)
            return 2
        old = int(store.settings.get("service", {}).get("web_port", 8787))
        n = dict(store.settings)
        n["service"] = {**n.get("service", {}), "web_port": new}
        store.save_settings(n)
        print(f"Saved: the app will use port {new} (was {old}).")
        if already_running(old):
            print("It's running now on the old port. Quit it (Settings > Quit the app) and start it again,")
            print("or use Settings > App address > Restart on new port.")
        return 0
    if cmd == "flash":
        token = store.secrets.get("webhook_token")
        port = int(store.settings.get("service", {}).get("web_port", 8787))
        if not token:
            print("Turn on webhooks in the app's Settings screen first.", file=sys.stderr)
            return 2
        mins = int(argv[2]) if len(argv) > 2 else None
        import ssl
        ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
        scheme = "https" if (data_dir() / "tls" / "cert.pem").is_file() else "http"
        req = urllib.request.Request(f"{scheme}://127.0.0.1:{port}/api/hook/flash", method="POST",
                                     data=json.dumps({"minutes": mins} if mins else {}).encode(),
                                     headers={"Content-Type": "application/json", "X-Token": token})
        try:
            with urllib.request.urlopen(req, timeout=30, context=ctx if scheme == "https" else None) as r:
                print(json.loads(r.read()))
            return 0
        except (urllib.error.URLError, OSError):
            print("The app isn't running.", file=sys.stderr)
            return 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
