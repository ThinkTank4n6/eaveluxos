# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Regression tests for the open-issues sweep (2.4.0)."""
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from eaveluxos.store import Store


class Storage(unittest.TestCase):
    """SQLite storage (3.0): migration, damage recovery, cross-process safety, history."""
    def setUp(self):
        self.base = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def _add(self, st, key):
        s = dict(st.settings)
        s["effects"] = {**s["effects"], key: {"label": key, "colors": ["#FF0000"], "counts": [1]}}
        return st.save_settings(s, st.rev)

    def test_migrates_a_json_install_and_keeps_the_old_files(self):
        import os
        d = self.base / "data"
        d.mkdir()
        (d / "settings.json").write_text(json.dumps({"effects": {"mine": {"colors": ["#FF0000"], "counts": [1]}},
                                                     "rules": [{"name": "N", "on": "sunset", "off": "23:00", "effect": "mine"}], "_rev": 7}), encoding="utf-8")
        (d / "secrets.json").write_text(json.dumps({"client_id": "abc", "client_secret": "s3"}), encoding="utf-8")
        st = Store(self.base)
        self.assertIn("mine", st.settings["effects"])
        self.assertEqual(st.settings["rules"][0]["name"], "N")
        self.assertEqual(st.rev, 7)
        self.assertEqual(st.secrets["client_secret"], "s3")
        names = sorted(f.name for f in d.iterdir())
        self.assertTrue(any(n.startswith("settings.migrated-") for n in names))
        self.assertTrue(any(n.startswith("secrets.migrated-") for n in names))
        if os.name != "nt":   # Windows uses ACLs, not mode bits (see store._restrict_windows)
            self.assertEqual(oct(os.stat(d / "eaveluxos.db").st_mode & 0o777), "0o600")

    def test_damaged_legacy_file_is_kept_and_last_good_used(self):
        d = self.base / "data"
        d.mkdir()
        (d / "settings.last-good.json").write_text(json.dumps({"effects": {"good": {"colors": ["#00FF00"], "counts": [1]}}}), encoding="utf-8")
        (d / "settings.json").write_text('{"effects": {"x": 1}, oops}', encoding="utf-8")
        st = Store(self.base)
        self.assertIn("good", st.settings["effects"])
        self.assertTrue(st.warnings and "line" in st.warnings[0])
        self.assertEqual(len(list(d.glob("settings.damaged-*.json"))), 1)

    def test_damaged_database_recovers_from_last_good_copy(self):
        st = Store(self.base)
        self._add(st, "keepme")
        st.close()
        db = self.base / "data" / "eaveluxos.db"
        for extra in ("-wal", "-shm"):
            Path(str(db) + extra).unlink(missing_ok=True)
        db.write_bytes(b"this is not a database" * 100)
        st2 = Store(self.base)
        self.assertIn("keepme", st2.settings["effects"])
        self.assertTrue(st2.warnings and "restored" in st2.warnings[0])
        self.assertTrue(list((self.base / "data").glob("eaveluxos.damaged-*.db")))

    def test_two_processes_cannot_overwrite_each_other(self):
        from eaveluxos.store import Conflict
        a, b = Store(self.base), Store(self.base)
        start = b.rev
        self._add(a, "from_a")
        self.assertIn("from_a", b.settings["effects"])      # b sees a's save
        stale = dict(b.settings)
        with self.assertRaises(Conflict):
            b.save_settings(stale, start)                  # b's editor started before a saved

    def test_history_records_every_save(self):
        st = Store(self.base)
        r1 = self._add(st, "one")
        r2 = self._add(st, "two")
        revs = [h["rev"] for h in st.history()]
        self.assertEqual(revs[:2], [r2, r1])
        self.assertNotIn("two", st.history_version(r1)["effects"])

    def test_sessions_and_secrets(self):
        st = Store(self.base)
        tok = st.new_session("phone")
        self.assertTrue(Store(self.base).valid_session(tok))  # works across processes
        st.end_all_sessions()
        self.assertFalse(st.valid_session(tok))
        st.save_secrets(client_id="x", local_login=True)
        st.save_secrets(local_login=None)
        self.assertEqual(Store(self.base).secrets, {"client_id": "x"})


class Delegation(unittest.TestCase):
    """#2: armed nights run on the controller's own timer, so the lights still
    go off if the app dies while they're on."""
    def setUp(self):
        import copy
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from eaveluxos.controller import Controller
        from eaveluxos.safety import SafetyNet
        from eaveluxos.schedule import Location, build_config
        from eaveluxos.store import DEFAULT_SETTINGS
        self.NY = ZoneInfo("America/New_York")
        s = copy.deepcopy(DEFAULT_SETTINGS)
        s["location"].update(latitude=40.6, longitude=-75.4)
        s["rules"] = [{"name": "Night", "on": "17:00", "off": "19:00", "effect": "warm_white"},
                      {"name": "Eve", "dates": "12-31", "on": "20:00", "off": "00:30", "effect": "christmas"}]
        s["safety"] = {"enabled": True, "days": 3}
        self.cfg = build_config(s, {"client_id": "x", "client_secret": "y"})
        self.dir = Path(tempfile.mkdtemp())
        self.net = SafetyNet(self.dir)
        self.calls = []
        test = self

        class Api:
            clock_offset_min = 0
            def list_devices(s): return [{"deviceId": "D"}]
            def get_device(s, *a): return {"connectivity": 1, "switchState": 2, "effects": [], "calendar": [], "daily": []}
            def set_switch(s, d, v): test.calls.append(("switch", v))
            def preview_effect(s, d, p): test.calls.append(("preview",))
        self.clock = [datetime(2026, 11, 20, 16, 0, tzinfo=self.NY)]
        self._orig = Location.now
        Location.now = lambda loc: self.clock[0]
        self.c = Controller(self.cfg, Api(), safety=self.net)
        self.c._ensure_devices()
        self.c.last_verify = 1e18  # keep the read-back out of these tests
        today = self.clock[0].date().isoformat()
        self.net.state["devices"]["D"] = {"ok": True, "covers_until": "2027-12-31", "hash": "x", "synced_on": today,
            "entries": [{"date": "11-20", "on": "17:00", "off": "19:00", "pattern": "Warm white"},
                        {"date": "12-31", "on": "20:00", "off": "23:59", "pattern": "Christmas"}],
            "effects": {}, "calendar": []}
        self.net.due = lambda *a: False

    def tearDown(self):
        from eaveluxos.schedule import Location
        Location.now = self._orig
        shutil.rmtree(self.dir, ignore_errors=True)

    def at(self, *t):
        from datetime import datetime
        self.clock[0] = datetime(*t, tzinfo=self.NY)
        self.calls.clear()
        self.c.next_try = 0
        self.c.tick()
        return self.c._target()

    def test_plain_night_is_handed_to_the_controller(self):
        self.assertEqual(self.at(2026, 11, 20, 16, 0).key, "off|timer")
        t = self.at(2026, 11, 20, 17, 0)
        self.assertTrue(t.delegated)
        self.assertEqual(self.calls, [("switch", 2)])          # no Manual, no preview
        self.assertTrue(self.at(2026, 11, 20, 18, 30).delegated)
        self.assertEqual(self.calls, [])                         # nothing to resend

    def test_after_a_manual_change_the_app_keeps_control_that_night(self):
        self.at(2026, 11, 20, 16, 0)
        self.at(2026, 11, 20, 17, 0)
        self.c.manual(True, "christmas")
        self.c.resume()
        t = self.at(2026, 11, 20, 18, 0)
        self.assertFalse(t.delegated)
        self.assertIn(("preview",), self.calls + [("preview",)])

    def test_window_past_midnight_is_taken_back_before_the_copy_ends(self):
        self.assertEqual(self.at(2026, 12, 31, 19, 30).key, "off|timer")
        self.assertTrue(self.at(2026, 12, 31, 20, 1).delegated)
        t = self.at(2026, 12, 31, 23, 58)
        self.assertFalse(t.delegated)
        self.assertIn(("switch", 1), self.calls)                # app takes over for the tail


class DataFolder(unittest.TestCase):
    """#3: a read-only app folder falls back to the per-user data folder."""
    def test_fallback_when_app_folder_is_read_only(self):
        import os
        from unittest import mock
        from eaveluxos import store
        base = Path(tempfile.mkdtemp())
        home = Path(tempfile.mkdtemp())
        real = store._writable
        try:
            with mock.patch.object(store, "_writable", side_effect=lambda d: False if d == base / "data" else real(d)), \
                 mock.patch.dict(os.environ, {"XDG_DATA_HOME": str(home), "LOCALAPPDATA": str(home)}):
                d = store.resolve_data_dir(base)
                self.assertTrue(str(d).startswith(str(home)) or "Application Support" in str(d))
                with mock.patch.object(store, "_writable", return_value=False):
                    with self.assertRaises(OSError):
                        store.resolve_data_dir(base)
        finally:
            shutil.rmtree(base, ignore_errors=True)
            shutil.rmtree(home, ignore_errors=True)


class WindowsPrivacy(unittest.TestCase):
    """#4: on Windows, private files get an ACL for this user and SYSTEM only."""
    def test_icacls_command(self):
        import os
        from unittest import mock
        from eaveluxos import store
        with mock.patch.dict(os.environ, {"USERNAME": "chris", "USERDOMAIN": "MINIPC"}), \
             mock.patch("subprocess.run") as run:
            run.return_value.returncode = 0
            self.assertTrue(store._restrict_windows(Path("C:/x/secrets.json")))
            args = run.call_args[0][0]
            self.assertEqual(args[:4], ["icacls", str(Path("C:/x/secrets.json")), "/inheritance:r", "/grant:r"])
            self.assertIn("MINIPC\\chris:(F)", args)
            self.assertIn("*S-1-5-18:(F)", args)

    def test_private_write_uses_it_on_windows(self):
        from unittest import mock
        from eaveluxos import store
        d = Path(tempfile.mkdtemp())
        try:
            with mock.patch.object(store.os, "name", "nt"), mock.patch.object(store, "_restrict_windows", return_value=True) as r:
                store._atomic_write(d / "secrets.json", {"a": 1}, private=True)
                self.assertTrue(r.called)
        finally:
            shutil.rmtree(d, ignore_errors=True)


class SlotLimit(unittest.TestCase):
    """#6: if the cloud only accepts 60 bulbs per color slot, long runs are split."""
    def test_split_and_remember(self):
        from tests import fake_trimlight as F
        from eaveluxos.api import TrimlightAPI, split_runs
        from eaveluxos.safety import _same_effect
        srv = F.start()
        api = TrimlightAPI(F.CID, F.SECRET, base_url=f"http://127.0.0.1:{srv.server_address[1]}/trimlight")
        payload = {"category": 1, "mode": 0, "speed": 100, "brightness": 200,
                   "pixels": [{"index": 0, "count": 90, "color": 0xFF0000, "disable": False},
                              {"index": 1, "count": 10, "color": 0xFFFFFF, "disable": False}]}
        F.STATE["max_count"] = 60
        try:
            F.STATE["log"].clear()
            api.preview_effect("TL-EDGE-01", payload)
            sent = [b for p, b in F.STATE["log"] if p == "/device/effect/preview"][-1]["payload"]["pixels"]
            self.assertEqual([x["count"] for x in sent], [60, 30, 10])
            self.assertEqual(TrimlightAPI.slot_limit, 60)
            self.assertTrue(_same_effect({**payload, "pixels": sent}, payload))
            self.assertIsNone(split_runs({"pixels": [{"index": i, "count": 90, "color": i} for i in range(30)]}, 60))
        finally:
            F.STATE["max_count"] = None
            TrimlightAPI.slot_limit = 90


class SyncTiming(unittest.TestCase):
    """#7: no safety-net sync in the 3 minutes before a scheduled change."""
    def test_defers_near_a_change(self):
        import copy
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from eaveluxos.controller import Controller
        from eaveluxos.schedule import Location, build_config
        from eaveluxos.store import DEFAULT_SETTINGS
        NY = ZoneInfo("America/New_York")
        s = copy.deepcopy(DEFAULT_SETTINGS)
        s["location"].update(latitude=40.6, longitude=-75.4)
        s["rules"] = [{"name": "Night", "on": "17:00", "off": "22:00", "effect": "warm_white"}]
        s["safety"] = {"enabled": True, "days": 3}
        cfg = build_config(s, {"client_id": "x", "client_secret": "y"})
        synced = []

        class Net:
            retry_at = 0
            def ready(self, *a): return False
            def plan(self, *a): return [], {}
            def plan_hash(self, *a): return "h"
            def due(self, *a): return True
            def sync(self, *a, **k): synced.append(1)

        class Api:
            clock_offset_min = 0
        clock = [datetime(2026, 11, 20, 16, 58, tzinfo=NY)]
        orig = Location.now
        Location.now = lambda loc: clock[0]
        try:
            c = Controller(cfg, Api(), safety=Net())
            c.devices = [{"deviceId": "D"}]
            c._safety_step(0)
            self.assertEqual(synced, [])
            clock[0] = datetime(2026, 11, 20, 17, 1, tzinfo=NY)
            c._safety_step(0)
            self.assertEqual(synced, [1])
        finally:
            Location.now = orig


class Https(unittest.TestCase):
    """#9: optional HTTPS with the owner's certificate."""
    def test_https_serves_and_a_stalled_client_blocks_no_one(self):
        import socket, ssl, subprocess, threading, time, urllib.request
        from eaveluxos.server import App, make_server, probe_app
        d = Path(tempfile.mkdtemp())
        try:
            (d / "data" / "tls").mkdir(parents=True)
            try:   # the app's own make-cert (no openssl needed, so this runs on Windows too)
                from eaveluxos.tlscert import make_cert
                make_cert(d / "data" / "tls")
            except RuntimeError:
                self.skipTest("the cryptography package isn't installed")
            app = App(d)
            srv = make_server(app, "127.0.0.1", 0)
            port = srv.server_address[1]
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            self.assertEqual(app.scheme, "https")
            staller = socket.create_connection(("127.0.0.1", port))      # connects, never handshakes
            plain = socket.create_connection(("127.0.0.1", port))
            plain.sendall(b"GET / HTTP/1.1\r\nHost: x\r\n\r\n")           # plain HTTP to the HTTPS port
            ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
            t0 = time.time()
            with urllib.request.urlopen(f"https://127.0.0.1:{port}/api/session", context=ctx, timeout=5) as x:
                self.assertIn("version", json.loads(x.read()))
                self.assertIn("frame-ancestors 'none'", x.headers["Content-Security-Policy"])
            self.assertLess(time.time() - t0, 3)
            self.assertTrue(probe_app(port))
            staller.close(); plain.close(); srv.shutdown(); srv.server_close()
        finally:
            shutil.rmtree(d, ignore_errors=True)


class DayBarCache(unittest.TestCase):
    """#10: the day bar is recomputed after every settings reload."""
    def test_reload_invalidates(self):
        import copy
        from eaveluxos.controller import Controller
        from eaveluxos.schedule import build_config
        from eaveluxos.store import DEFAULT_SETTINGS
        s = copy.deepcopy(DEFAULT_SETTINGS)
        s["location"].update(latitude=40.6, longitude=-75.4)

        class Api:
            clock_offset_min = 0
            def list_devices(s): return []
        c = Controller(build_config(s, {"client_id": "x", "client_secret": "y"}), Api())
        g = c.cfg_gen
        c.tick = lambda **kw: None
        c.reload(build_config(s, {"client_id": "x", "client_secret": "y"}))
        self.assertEqual(c.cfg_gen, g + 1)


class HardwareTestScript(unittest.TestCase):
    """The guided hardware test runs end to end and always cleans up."""
    def _run(self, max_count=None, answers="y"):
        import copy
        from datetime import datetime
        from tests import fake_trimlight as F
        from eaveluxos import api as api_mod, hwtest
        srv = F.start()
        base = f"http://127.0.0.1:{srv.server_address[1]}/trimlight"
        d = Path(tempfile.mkdtemp())
        before = copy.deepcopy(F.STATE["dev"])
        F.STATE["max_count"] = max_count
        old_base = api_mod.BASE_URL
        api_mod.BASE_URL = base
        try:
            st = Store(d)
            st.save_secrets(client_id=F.CID, client_secret=F.SECRET)
            out = []
            code = hwtest.run(st, st.dir, ask=lambda q: answers, say=out.append, sleep=lambda s: None,
                              now=lambda: datetime(2026, 11, 20, 12, 0).astimezone())
            report = next(st.dir.glob("hardware-test-*.txt")).read_text(encoding="utf-8")
            after = F.STATE["dev"]
            return code, report, before, after
        finally:
            F.STATE["max_count"] = None
            api_mod.BASE_URL = old_base
            shutil.rmtree(d, ignore_errors=True)

    def test_full_run_passes_and_restores_everything(self):
        code, report, before, after = self._run()
        self.assertEqual(code, 0, report)
        for line in ("[PASS] 90 bulbs per color slot", "[PASS] Save pattern to library", "[PASS] Port off as 0/0",
                     "[PASS] Controller timer turns lights on", "[PASS] Timer entry reads back as written"):
            self.assertIn(line, report)
        self.assertEqual(after["ports"], before["ports"])
        self.assertEqual(after["calendar"], before["calendar"])
        self.assertEqual([e["id"] for e in after["effects"]], [e["id"] for e in before["effects"]])

    def test_reports_a_60_bulb_cloud(self):
        code, report, *_ = self._run(max_count=60)
        self.assertIn("[NO  ] 90 bulbs per color slot", report)


class RenameCarryOver(unittest.TestCase):
    """3.1: installs from before the rename to EaveLuxOS carry over by themselves."""
    def test_old_database_name_is_picked_up(self):
        base = Path(tempfile.mkdtemp())
        try:
            st = Store(base)
            s = dict(st.settings)
            s["effects"] = {**s["effects"], "keep": {"colors": ["#FF0000"], "counts": [1]}}
            st.save_settings(s)
            st.close()
            d = base / "data"
            for suffix in ("", "-wal", "-shm"):
                f = Path(str(d / "eaveluxos.db") + suffix)
                if f.exists():
                    f.rename(Path(str(d / "trimlight.db") + suffix))
            from eaveluxos.store import read_service_settings
            self.assertIn("web_port", read_service_settings(d))      # startup can still read the port
            st2 = Store(base)
            self.assertIn("keep", st2.settings["effects"])
            self.assertTrue((d / "eaveluxos.db").exists())
            self.assertFalse((d / "trimlight.db").exists())
        finally:
            shutil.rmtree(base, ignore_errors=True)

    def test_old_start_at_login_entry_is_replaced(self):
        import os
        from unittest import mock
        from eaveluxos import autostart
        home = Path(tempfile.mkdtemp())
        try:
            with mock.patch.object(Path, "home", return_value=home), mock.patch("platform.system", return_value="Linux"), \
                 mock.patch("subprocess.run") as run:
                run.return_value.returncode = 0
                old = home / ".config/systemd/user/trimlight-scheduler.service"
                old.parent.mkdir(parents=True)
                old.write_text("[Service]\nEnvironment=TRIMLIGHT_SUPERVISED=1\n", encoding="utf-8")
                self.assertTrue(autostart.status(Path("/app"))["enabled"])
                self.assertTrue(autostart.migrate_legacy(Path("/app")))
                self.assertFalse(old.exists())
                new = home / ".config/systemd/user/eaveluxos.service"
                self.assertIn("EAVELUXOS_SUPERVISED=1", new.read_text(encoding="utf-8"))
                self.assertFalse(autostart.migrate_legacy(Path("/app")))   # nothing left to do
        finally:
            shutil.rmtree(home, ignore_errors=True)


class SecondRenameCarryOver(unittest.TestCase):
    """3.2: LumaOS installs (as well as Trimlight Scheduler ones) carry over."""
    def test_lumaos_database_and_autostart(self):
        from unittest import mock
        from eaveluxos import autostart
        base = Path(tempfile.mkdtemp())
        home = Path(tempfile.mkdtemp())
        try:
            st = Store(base)
            s = dict(st.settings)
            s["effects"] = {**s["effects"], "from_luma": {"colors": ["#8270C3"], "counts": [2]}}
            st.save_settings(s)
            st.close()
            d = base / "data"
            for suffix in ("", "-wal", "-shm"):
                f = Path(str(d / "eaveluxos.db") + suffix)
                if f.exists():
                    f.rename(Path(str(d / "lumaos.db") + suffix))
            self.assertIn("from_luma", Store(base).settings["effects"])
            self.assertTrue((d / "eaveluxos.db").exists() and not (d / "lumaos.db").exists())
            with mock.patch.object(Path, "home", return_value=home), mock.patch("platform.system", return_value="Linux"), \
                 mock.patch("subprocess.run") as run:
                run.return_value.returncode = 0
                old = home / ".config/systemd/user/lumaos.service"
                old.parent.mkdir(parents=True)
                old.write_text("[Service]\\n", encoding="utf-8")
                self.assertTrue(autostart.migrate_legacy(Path("/app")))
                self.assertFalse(old.exists())
                self.assertTrue((home / ".config/systemd/user/eaveluxos.service").exists())
        finally:
            shutil.rmtree(base, ignore_errors=True)
            shutil.rmtree(home, ignore_errors=True)


class Executable(unittest.TestCase):
    """Bundled-executable mode (PyInstaller)."""
    def test_frozen_paths_and_launch_command(self):
        import subprocess, sys
        root = Path(__file__).resolve().parent.parent
        code = ("import sys; sys.frozen = True; sys.executable = '/opt/EaveLuxOS/EaveLuxOS'; "
                f"sys.path.insert(0, {str(root)!r}); import main; "
                "from eaveluxos import autostart; "
                "print(main.HERE); print(autostart.launch_command(main.HERE))")
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=root).stdout.split("\n")
        # (On Windows, /opt/EaveLuxOS resolves to C:\\opt\\EaveLuxOS.)
        self.assertEqual(out[0], str(Path("/opt/EaveLuxOS/EaveLuxOS").resolve().parent))   # data lives next to the executable
        self.assertEqual(out[1], "['/opt/EaveLuxOS/EaveLuxOS', 'run']")  # autostart and port moves run the exe

    def test_gitignore_keeps_private_data_out(self):
        import shutil as sh, subprocess
        if not sh.which("git"):
            self.skipTest("git not installed")
        root = Path(__file__).resolve().parent.parent
        d = Path(tempfile.mkdtemp())
        try:
            sh.copy(root / ".gitignore", d / ".gitignore")
            (d / "data" / "photos").mkdir(parents=True)
            for f in ("data/eaveluxos.db", "data/eaveluxos.db-wal", "data/photos/front.jpg", "data/settings.last-good.json"):
                (d / f).write_text("private", encoding="utf-8")
            (d / "main.py").write_text("print(1)", encoding="utf-8")
            subprocess.run(["git", "init", "-q"], cwd=d, check=True)
            subprocess.run(["git", "add", "-A"], cwd=d, check=True)
            staged = subprocess.run(["git", "diff", "--cached", "--name-only"], cwd=d, capture_output=True, text=True, encoding="utf-8", errors="replace").stdout.split()
            self.assertEqual(sorted(staged), [".gitignore", "main.py"])
        finally:
            sh.rmtree(d, ignore_errors=True)


class MacAppBundle(unittest.TestCase):
    def test_data_never_goes_inside_an_app_bundle(self):
        import os
        from unittest import mock
        from eaveluxos.store import resolve_data_dir
        apps = Path(tempfile.mkdtemp())
        home = Path(tempfile.mkdtemp())
        try:
            macos = apps / "EaveLuxOS.app" / "Contents" / "MacOS"
            macos.mkdir(parents=True)
            with mock.patch("platform.system", return_value="Darwin"), mock.patch.object(Path, "home", return_value=home):
                d = resolve_data_dir(macos)
            self.assertEqual(d, home / "Library" / "Application Support" / "EaveLuxOS")
            self.assertFalse((macos / "data").exists())
        finally:
            shutil.rmtree(apps, ignore_errors=True)
            shutil.rmtree(home, ignore_errors=True)


class Packaging(unittest.TestCase):
    """packaging/build.py: the steps after PyInstaller, testable without it."""
    def _build(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("build", Path(__file__).resolve().parent.parent / "packaging" / "build.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_linux_packages(self):
        import shutil as sh, subprocess, tarfile
        b = self._build()
        tmp = Path(tempfile.mkdtemp())
        b.DIST = tmp / "dist"
        try:
            exe = tmp / "eaveluxos"
            exe.write_text("#!/bin/sh\necho ok\n", encoding="utf-8")
            exe.chmod(0o755)
            outs = b.package_linux(exe, "9.9.9", "aarch64")
            tar = next(o for o in outs if o.suffix == ".gz")
            with tarfile.open(tar) as t:
                self.assertTrue(t.getmember("EaveLuxOS/eaveluxos").mode & 0o111)     # still executable
            if sh.which("dpkg-deb"):
                deb = next(o for o in outs if o.suffix == ".deb")
                self.assertEqual(deb.name, "eaveluxos_9.9.9_arm64.deb")                # Raspberry Pi OS 64-bit
                info = subprocess.run(["dpkg-deb", "-f", str(deb), "Architecture", "Version"], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
                self.assertIn("arm64", info)
                files = subprocess.run(["dpkg-deb", "-c", str(deb)], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
                for f in ("./opt/eaveluxos/eaveluxos", "./usr/bin/eaveluxos", "eaveluxos.desktop", "apps/eaveluxos.png"):
                    self.assertIn(f, files)
        finally:
            sh.rmtree(tmp, ignore_errors=True)

    def test_mac_app_runs_without_a_dock_icon(self):
        import plistlib
        b = self._build()
        tmp = Path(tempfile.mkdtemp())
        try:
            app = tmp / "EaveLuxOS.app"
            (app / "Contents").mkdir(parents=True)
            (app / "Contents" / "Info.plist").write_bytes(plistlib.dumps({"CFBundleName": "x"}))
            b.finish_mac_app(app, "9.9.9")
            info = plistlib.loads((app / "Contents" / "Info.plist").read_bytes())
            self.assertTrue(info["LSUIElement"])
            self.assertEqual(info["CFBundleShortVersionString"], "9.9.9")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
