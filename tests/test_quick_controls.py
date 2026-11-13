# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""The header's On, Off and Quit buttons."""
import copy
import json
import os
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

from eaveluxos import autostart
from eaveluxos.controller import Controller
from eaveluxos.schedule import Location, build_config
from eaveluxos.store import DEFAULT_SETTINGS
from tests.test_music import CountingAPI

NY = ZoneInfo("America/New_York")


class DefaultOnPatternTests(unittest.TestCase):
    def setUp(self):
        self.clock = [datetime(2026, 12, 4, 18, 0, tzinfo=NY)]
        self._orig = Location.now
        Location.now = lambda loc: self.clock[0]

    def tearDown(self):
        Location.now = self._orig

    def make(self, rules):
        s = copy.deepcopy(DEFAULT_SETTINGS)
        s["location"].update(latitude=39.95, longitude=-75.17)
        s["rules"] = rules
        return Controller(build_config(s, {"client_id": "x", "client_secret": "y"}), CountingAPI())

    def test_uses_the_pattern_scheduled_now(self):
        c = self.make([{"name": "Xmas", "on": "17:00", "off": "23:00", "effect": "christmas"}])
        self.assertEqual(c.default_on_effect(), "christmas")

    def test_before_tonights_window_uses_tonights_pattern(self):
        self.clock[0] = datetime(2026, 12, 4, 9, 0, tzinfo=NY)
        c = self.make([{"name": "Xmas", "on": "17:00", "off": "23:00", "effect": "christmas"}])
        self.assertEqual(c.default_on_effect(), "christmas")

    def test_rotation_uses_the_current_step(self):
        c = self.make([{"name": "Mix", "on": "17:00", "off": "23:00", "effect": ["christmas", "snowfall"],
                        "rotate_minutes": 30}])
        self.clock[0] = datetime(2026, 12, 4, 17, 40, tzinfo=NY)
        self.assertEqual(c.default_on_effect(), "snowfall")

    def test_no_schedule_falls_back_to_last_used_then_warm_white(self):
        c = self.make([])
        self.assertEqual(c.default_on_effect(), "warm_white")
        c.manual(True, "halloween")
        self.assertEqual(c.default_on_effect(), "halloween")

    def test_on_then_off_are_manual_until_the_next_change(self):
        c = self.make([{"name": "Xmas", "on": "17:00", "off": "23:00", "effect": "christmas"}])
        c.manual(False)
        t = c._target(commit=False)
        self.assertEqual((t.on, t.reason), (False, "manual"))
        c.manual(True, c.default_on_effect())
        self.assertEqual(c._target(commit=False).effect.label, "Christmas")


class StopServiceTests(unittest.TestCase):
    def run_as(self, system, supervised=True, results=(0,)):
        calls, codes = [], list(results)

        def run(cmd, **kw):
            calls.append(cmd)
            return mock.Mock(returncode=codes.pop(0) if codes else 0)
        env = {"EAVELUXOS_SUPERVISED": "1"} if supervised else {}
        with mock.patch.dict(os.environ, env, clear=False), \
                mock.patch.object(autostart.platform, "system", return_value=system), \
                mock.patch.object(autostart.os, "getuid", create=True, return_value=501):
            if not supervised:
                for k in ("EAVELUXOS_SUPERVISED", "LUMAOS_SUPERVISED", "TRIMLIGHT_SUPERVISED"):
                    os.environ.pop(k, None)
            ok = autostart.stop_service(run=run)
        return ok, calls

    def test_not_a_service_does_nothing(self):
        self.assertEqual(self.run_as("Linux", supervised=False), (False, []))

    def test_linux_stops_the_user_unit_without_waiting(self):
        ok, calls = self.run_as("Linux")
        self.assertTrue(ok)
        self.assertEqual(calls, [["systemctl", "--user", "--no-block", "stop", "eaveluxos.service"]])

    def test_macos_boots_out_the_launch_agent(self):
        ok, calls = self.run_as("Darwin")
        self.assertEqual(calls, [["launchctl", "bootout", "gui/501/com.eaveluxos"]])
        ok, calls = self.run_as("Darwin", results=(5, 0))           # older macOS
        self.assertEqual(calls[-1], ["launchctl", "remove", "com.eaveluxos"])
        self.assertTrue(ok)

    def test_windows_has_no_service_to_stop(self):
        self.assertEqual(self.run_as("Windows"), (False, []))


class QuickApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests import fake_trimlight as F
        import eaveluxos.api
        cls.cloud = F.start()
        cls._saved = (os.environ.get("TRIMLIGHT_API_BASE"), eaveluxos.api.BASE_URL)
        os.environ["TRIMLIGHT_API_BASE"] = f"http://127.0.0.1:{cls.cloud.server_address[1]}/trimlight"
        eaveluxos.api.BASE_URL = os.environ["TRIMLIGHT_API_BASE"]
        from eaveluxos.server import App, make_server
        cls.dir = Path(tempfile.mkdtemp())
        cls.app = App(cls.dir)
        s = copy.deepcopy(cls.app.store.settings)
        s["location"].update(latitude=39.95, longitude=-75.16)
        s["setup_done"] = True
        cls.app.store.save_settings(s)
        cls.app.store.save_secrets(client_id=F.CID, client_secret=F.SECRET)
        cls.app.rebuild()
        cls.srv = make_server(cls.app, "127.0.0.1", 0)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        import eaveluxos.api
        cls.srv.shutdown()
        cls.srv.server_close()
        if cls.app.ctrl:
            cls.app.ctrl.stop_event.set()
        cls.app.store.close()
        shutil.rmtree(cls.dir, ignore_errors=True)
        env, base = cls._saved
        if env is None:
            os.environ.pop("TRIMLIGHT_API_BASE", None)
        else:
            os.environ["TRIMLIGHT_API_BASE"] = env
        eaveluxos.api.BASE_URL = base

    def call(self, path, body=None, hdr=None):
        h = {"Content-Type": "application/json", "X-Requested-With": "eaveluxos", **(hdr or {})}
        r = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}",
                                   data=None if body is None else json.dumps(body).encode(), headers=h)
        try:
            with urllib.request.urlopen(r, timeout=20) as x:
                return x.status, json.loads(x.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def test_on_without_a_pattern_and_off(self):
        st, r = self.call("/api/action", {"action": "off"})
        self.assertEqual((st, r["target"]["on"]), (200, False))
        st, r = self.call("/api/action", {"action": "on"})
        self.assertEqual(st, 200, r)
        self.assertTrue(r["target"]["on"])
        self.assertEqual(r["target"]["reason"], "manual")
        self.call("/api/action", {"action": "resume"})

    def test_quit_from_another_device_is_refused(self):
        phone = {"X-Forwarded-For": "203.0.113.9"}
        with mock.patch("eaveluxos.server.threading.Timer") as timer:
            st, _ = self.call("/api/quit", {}, phone)
            self.assertEqual(st, 401)                                    # not signed in
            self.call("/api/users", {"username": "owner", "role": "admin", "password": "password-xxxx"})
            st, r = self.call("/api/login", {"username": "owner", "password": "password-xxxx"}, phone)
            self.assertEqual(st, 200, r)
            st, r = self.call("/api/quit", {}, {**phone, "X-Session": r["token"]})
        self.assertEqual(st, 403)                                        # an Administrator, but on a phone
        self.assertIn("computer it runs on", r["error"])
        timer.assert_not_called()

    def test_quit_in_a_container_explains_how_to_stop_it(self):
        with mock.patch("eaveluxos.server.IN_CONTAINER", True), mock.patch("eaveluxos.server.threading.Timer") as timer:
            st, r = self.call("/api/quit", {})
        self.assertEqual(st, 400)
        self.assertIn("docker compose stop", r["error"])
        timer.assert_not_called()

    def test_quit_stops_the_service_then_exits(self):
        with mock.patch("eaveluxos.server.threading.Timer") as timer:
            st, r = self.call("/api/quit", {})
        self.assertEqual(st, 200)
        self.assertIn("starts_at_login", r)
        quit_now = timer.call_args[0][1]
        order = []
        with mock.patch.object(autostart, "stop_service", side_effect=lambda: order.append("stop")), \
                mock.patch("os._exit", side_effect=lambda code: order.append(("exit", code))):
            quit_now()
        self.assertEqual(order, ["stop", ("exit", 0)])


if __name__ == "__main__":
    unittest.main()
