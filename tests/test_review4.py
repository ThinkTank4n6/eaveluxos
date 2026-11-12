# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Regression tests for the 3.8.1 review fixes."""
import json
import os
import shutil
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path

from tests import fake_trimlight as F

_cloud = F.start()
os.environ["TRIMLIGHT_API_BASE"] = f"http://127.0.0.1:{_cloud.server_address[1]}/trimlight"
import eaveluxos.api  # noqa: E402
eaveluxos.api.BASE_URL = os.environ["TRIMLIGHT_API_BASE"]
from eaveluxos.server import App, make_server  # noqa: E402


def raw_exchange(port, data: bytes, wait=1.0) -> bytes:
    s = socket.create_connection(("127.0.0.1", port))
    s.sendall(data)
    time.sleep(wait)
    s.settimeout(1)
    out = b""
    try:
        while True:
            chunk = s.recv(65536)
            if not chunk:
                break
            out += chunk
    except OSError:
        pass
    s.close()
    return out


class DesyncTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = Path(tempfile.mkdtemp())
        cls.app = App(cls.dir)
        cls.app.store.save_user(None, "owner", "admin", password="correct horse battery")
        cls.srv = make_server(cls.app, "127.0.0.1", 0)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.app.store.close()
        shutil.rmtree(cls.dir, ignore_errors=True)

    def _inner(self, name):
        body = json.dumps({"username": name, "role": "admin", "password": "pwned-pwned"}).encode()
        return (b"POST /api/users HTTP/1.1\r\nHost: 127.0.0.1\r\nX-Requested-With: eaveluxos\r\n"
                b"Content-Type: application/json\r\nContent-Length: %d\r\n\r\n" % len(body) + body)

    def names(self):
        return {u["username"] for u in self.app.store.users()}

    def test_get_body_is_not_parsed_as_a_second_request(self):
        inner = self._inner("smuggled")
        outer = (b"GET /api/session HTTP/1.1\r\nHost: 127.0.0.1\r\nX-Forwarded-For: 203.0.113.9\r\n"
                 b"Content-Length: %d\r\n\r\n" % len(inner) + inner)
        raw_exchange(self.port, outer)
        self.assertNotIn("smuggled", self.names())

    def test_chunked_get_is_refused_and_closed(self):
        out = raw_exchange(self.port, b"GET /api/session HTTP/1.1\r\nHost: 127.0.0.1\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n\r\n")
        self.assertIn(b" 411 ", out.split(b"\r\n", 1)[0] + b" ")

    def test_proxied_connection_never_becomes_local(self):
        first = b"GET /api/session HTTP/1.1\r\nHost: 127.0.0.1\r\nX-Forwarded-For: 203.0.113.9\r\n\r\n"
        raw_exchange(self.port, first + self._inner("second-on-conn"))
        self.assertNotIn("second-on-conn", self.names())


def _cfg(rules):
    import copy
    from eaveluxos.schedule import build_config
    from eaveluxos.store import DEFAULT_SETTINGS
    s = copy.deepcopy(DEFAULT_SETTINGS)
    s["location"].update(latitude=39.95, longitude=-75.16, timezone="America/New_York")
    s["rules"] = rules
    return build_config(s, {}, need_secrets=False)


def _switches(cfg, t0, t1):
    from datetime import timedelta
    out, prev, t = [], None, t0
    while t < t1:
        on = cfg.schedule.active_window(t.astimezone(cfg.loc.tz)) is not None
        if on != prev:
            out.append(on)
            prev = on
        t += timedelta(minutes=5)
    return out


class DstTests(unittest.TestCase):
    def test_fall_back_night_lights_only_once(self):
        from datetime import datetime, timezone
        cfg = _cfg([{"name": "Late", "on": "sunset", "off": "01:30", "effect": "warm_white"}])
        sw = _switches(cfg, datetime(2026, 11, 1, 4, 50, tzinfo=timezone.utc), datetime(2026, 11, 1, 7, 30, tzinfo=timezone.utc))
        self.assertEqual(sw, [True, False])

    def test_window_inside_repeated_hour_runs_once(self):
        from datetime import date, datetime, timezone
        cfg = _cfg([{"name": "b", "on": "01:15", "off": "01:45", "effect": "warm_white"}])
        sw = _switches(cfg, datetime(2026, 11, 1, 4, 0, tzinfo=timezone.utc), datetime(2026, 11, 1, 8, 0, tzinfo=timezone.utc))
        self.assertEqual(sw, [False, True, False])
        self.assertEqual(len(cfg.schedule.day_plans(date(2026, 11, 1))), 1)

    def test_flash_lasts_real_minutes_across_fall_back(self):
        from datetime import datetime, timedelta, timezone
        from zoneinfo import ZoneInfo
        from eaveluxos.schedule import add_real, ts
        start = datetime(2026, 11, 1, 5, 58, tzinfo=timezone.utc).astimezone(ZoneInfo("America/New_York"))
        self.assertEqual(ts(add_real(start, timedelta(minutes=5))) - ts(start), 300)


class WeatherLockTests(unittest.TestCase):
    def test_current_does_not_wait_for_a_slow_fetch(self):
        from eaveluxos.weather import WeatherService
        gate = threading.Event()

        def slow(url):
            gate.wait(5)
            raise RuntimeError("NWS unreachable: timed out")
        w = WeatherService(39.95, -75.16, "either", 15, fetch=slow)
        threading.Thread(target=w.refresh, daemon=True).start()
        time.sleep(0.2)
        t0 = time.time()
        w.current()
        self.assertLess(time.time() - t0, 0.5)
        gate.set()

    def test_readings_still_update(self):
        from eaveluxos.weather import WeatherService
        data = {"/points/": {"properties": {"forecastHourly": "H", "observationStations": "S"}},
                "S": {"features": [{"properties": {"stationIdentifier": "KPHL"}}]},
                "/observations/latest": {"properties": {"textDescription": "Light Snow", "temperature": {"value": -2},
                                                        "timestamp": "2099-01-01T00:00:00+00:00"}},
                "H": {"properties": {"periods": [{"shortForecast": "Snow", "temperature": 28, "temperatureUnit": "F"}]}}}

        def fetch(url):
            return next(v for k, v in data.items() if k in url or url == k)
        w = WeatherService(39.95, -75.16, "either", 15, fetch=fetch)
        w.refresh(force=True)
        cur = w.current()
        self.assertTrue(cur["fresh"])
        self.assertIn("snow", cur["tags"])


class PortHandoffTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.app = App(self.dir, start=False)
        n = dict(self.app.store.settings)
        n["service"] = {**n["service"], "web_port": 9999}
        self.app.store.save_settings(n)

    def tearDown(self):
        self.app.store.close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def _fake_ctrl(self):
        class C:
            stop_event = threading.Event()
        return C()

    def test_scheduler_that_wont_stop_cancels_the_move(self):
        from unittest import mock
        self.app.ctrl = self._fake_ctrl()
        stuck = mock.Mock(**{"is_alive.return_value": True})
        self.app.thread = stuck
        with mock.patch("eaveluxos.server.time.sleep"), mock.patch("subprocess.Popen") as popen:
            self.app._restart_on(8787, 9999)
        popen.assert_not_called()
        self.assertIs(self.app.thread, stuck)             # no second scheduler thread
        self.assertFalse(self.app.ctrl.stop_event.is_set())
        self.assertEqual(self.app.store.settings["service"]["web_port"], 8787)

    def test_failed_new_copy_is_stopped_before_rollback(self):
        from unittest import mock
        self.app.ctrl = self._fake_ctrl()
        self.app.thread = mock.Mock(**{"is_alive.return_value": False})
        child = mock.Mock(returncode=None)
        child.poll.return_value = None
        starts = []
        with mock.patch("eaveluxos.server.time.sleep"), mock.patch("subprocess.Popen", return_value=child), \
                mock.patch("eaveluxos.server.probe_app", return_value=False), \
                mock.patch("eaveluxos.server.time.time", side_effect=[0, 0, 100, 100, 100]), \
                mock.patch.object(App, "_start_thread", lambda a: starts.append(1)):
            self.app._restart_on(8787, 9999)
        child.terminate.assert_called_once()
        self.assertEqual(starts, [1])
        self.assertEqual(self.app.store.settings["service"]["web_port"], 8787)


class StartupRaceTests(unittest.TestCase):
    def test_busy_port_held_by_a_starting_copy_is_not_skipped(self):
        from unittest import mock
        import main
        answers = iter([False, False, True])   # first check, then the copy finishes starting
        binds = []

        def fake_make_server(app, host, port):
            binds.append(port)
            raise OSError("in use")
        with mock.patch.object(main, "configured_port", return_value=("127.0.0.1", 8787)), \
                mock.patch.object(main, "already_running", side_effect=lambda p: next(answers)), \
                mock.patch.object(main.time, "sleep"), \
                mock.patch("eaveluxos.server.App"), mock.patch("eaveluxos.server.make_server", fake_make_server):
            self.assertEqual(main.cmd_run(False), 0)
        self.assertEqual(binds, [8787])          # never tried 8788: no second scheduler


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.app = App(self.dir, start=False)
        n = dict(self.app.store.settings)
        n["location"] = {**n["location"], "latitude": 39.95, "longitude": -75.16}
        n["map"] = {"total_bulbs": 300, "zones": [{"name": "Garage", "start": 1, "end": 40}]}
        n["safety"] = {"enabled": True, "days": 5}
        self.app.store.save_settings(n)

    def tearDown(self):
        self.app.store.close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def export(self):
        import copy
        d = copy.deepcopy(self.app.store.settings)
        for k in ("location", "service", "setup_done", "_rev", "controller", "map", "safety"):
            d.pop(k, None)
        return d

    def test_replace_keeps_house_map_and_safety(self):
        self.app.import_settings({"mode": "replace", "settings": self.export()})
        s = self.app.store.settings
        self.assertEqual(s["map"]["zones"][0]["name"], "Garage")
        self.assertTrue(s["safety"]["enabled"])

    def test_merge_keeps_imported_rule_on_its_own_pattern(self):
        inc = {"effects": {"christmas": {"label": "Their Xmas", "colors": ["#0000FF"], "counts": [5]}},
               "rules": [{"name": "Theirs", "on": "sunset", "off": "23:00", "effect": "christmas"}]}
        self.app.import_settings({"mode": "merge", "settings": inc})
        s = self.app.store.settings
        rule = next(r for r in s["rules"] if r["name"] == "Theirs")
        self.assertNotEqual(rule["effect"], "christmas")
        self.assertEqual(s["effects"][rule["effect"]]["colors"], ["#0000FF"])
        self.assertEqual(s["effects"]["christmas"]["label"], "Christmas")   # the local one is untouched


class DatabaseOpenTests(unittest.TestCase):
    def test_io_error_does_not_reset_the_database(self):
        import sqlite3
        from unittest import mock
        from eaveluxos.store import Store
        d = Path(tempfile.mkdtemp())
        try:
            s = Store(d)
            s.save_user(None, "owner", "admin", password="correct horse battery")
            s.close()
            err = sqlite3.OperationalError("disk I/O error")
            err.sqlite_errorcode = 10      # SQLITE_IOERR
            with mock.patch.object(Store, "_connect", side_effect=err):
                with self.assertRaises(sqlite3.OperationalError):
                    Store(d)
            self.assertFalse(list((d / "data").glob("*.damaged-*")))
            s = Store(d)
            self.assertEqual([u["username"] for u in s.users()], ["owner"])
            s.close()
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_not_a_database_is_still_recovered(self):
        from eaveluxos.store import Store
        d = Path(tempfile.mkdtemp())
        try:
            Store(d).close()
            for f in (d / "data").glob("eaveluxos.db*"):
                f.unlink()
            (d / "data" / "eaveluxos.db").write_bytes(b"garbage" * 200)
            s = Store(d)
            self.assertTrue(any("couldn't be read" in w for w in s.warnings))
            s.close()
        finally:
            shutil.rmtree(d, ignore_errors=True)


class SafetyLiveCheckTests(unittest.TestCase):
    def test_copy_changed_in_trimlight_app_stops_delegation(self):
        import copy
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from eaveluxos.api import TrimlightAPI
        from eaveluxos.safety import SafetyNet
        from eaveluxos.schedule import build_config
        from eaveluxos.store import DEFAULT_SETTINGS
        d = Path(tempfile.mkdtemp())
        saved = copy.deepcopy(F.STATE["dev"])
        try:
            F.STATE["corrupt_calendar"] = False
            F.STATE["dev"]["calendar"] = []
            s = copy.deepcopy(DEFAULT_SETTINGS)
            s["location"].update(latitude=39.95, longitude=-75.17)
            s["rules"] = [{"name": "Night", "on": "sunset", "off": "22:00", "effect": "warm_white"}]
            s["safety"] = {"enabled": True, "days": 3}
            cfg = build_config(s, {"client_id": F.CID, "client_secret": F.SECRET})
            api = TrimlightAPI(F.CID, F.SECRET, base_url=os.environ["TRIMLIGHT_API_BASE"])
            net = SafetyNet(d)
            now = datetime(2026, 12, 5, 12, 0, tzinfo=ZoneInfo("America/New_York"))
            self.assertTrue(net.sync(api, cfg, ["TL-EDGE-01"], now))
            self.assertTrue(net.ready("TL-EDGE-01", now.date()))
            det = api.get_device("TL-EDGE-01", now)
            self.assertIsNone(net.check_live("TL-EDGE-01", det))          # untouched: still trusted
            F.STATE["dev"]["calendar"] = F.STATE["dev"]["calendar"][1:]   # someone deleted a timer
            msg = net.check_live("TL-EDGE-01", api.get_device("TL-EDGE-01", now))
            self.assertTrue(msg)
            self.assertFalse(net.ready("TL-EDGE-01", now.date()))
            self.assertTrue(net.due(["TL-EDGE-01"], "x", now.date(), 0))
        finally:
            F.STATE["dev"] = saved
            shutil.rmtree(d, ignore_errors=True)


class SafetyPartialWriteTests(unittest.TestCase):
    def test_failure_midway_leaves_no_mixed_copy(self):
        import copy
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from eaveluxos.api import TrimlightAPI, TrimlightError
        from eaveluxos.safety import SafetyNet
        from eaveluxos.schedule import build_config
        from eaveluxos.store import DEFAULT_SETTINGS
        d = Path(tempfile.mkdtemp())
        saved = copy.deepcopy(F.STATE["dev"])
        try:
            F.STATE["corrupt_calendar"] = False
            user_entry = {"id": 0, "effectId": 3, "startDate": {"month": 12, "day": 1}, "endDate": {"month": 12, "day": 31},
                          "startTime": {"hours": 17, "minutes": 0}, "endTime": {"hours": 23, "minutes": 0}}
            F.STATE["dev"]["calendar"] = [copy.deepcopy(user_entry)]
            s = copy.deepcopy(DEFAULT_SETTINGS)
            s["location"].update(latitude=39.95, longitude=-75.17)
            s["rules"] = [{"name": "Night", "on": "sunset", "off": "22:00", "effect": "warm_white"}]
            s["safety"] = {"enabled": True, "days": 4}
            cfg = build_config(s, {"client_id": F.CID, "client_secret": F.SECRET})

            class Flaky(TrimlightAPI):
                n = 0

                def calendar_save(self, dev, payload):
                    Flaky.n += 1
                    if Flaky.n == 3:
                        raise TrimlightError("Network error calling /device/calendar/save: timed out")
                    return super().calendar_save(dev, payload)
            api = Flaky(F.CID, F.SECRET, base_url=os.environ["TRIMLIGHT_API_BASE"])
            net = SafetyNet(d)
            now = datetime(2026, 12, 5, 12, 0, tzinfo=ZoneInfo("America/New_York"))
            self.assertFalse(net.sync(api, cfg, ["TL-EDGE-01"], now))
            self.assertEqual(F.STATE["dev"]["calendar"], [user_entry])   # only the owner's own entry is left
            self.assertEqual(net.state["devices"]["TL-EDGE-01"]["calendar"], [])
        finally:
            F.STATE["dev"] = saved
            shutil.rmtree(d, ignore_errors=True)


class StoreRobustnessTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_recovery_copy_failure_does_not_fail_the_save(self):
        from unittest import mock
        from eaveluxos import store as store_mod
        s = store_mod.Store(self.dir)
        n = dict(s.settings)
        n["security"] = {"effect": "security_white", "minutes": 7}
        with mock.patch.object(store_mod, "_atomic_write", side_effect=OSError(28, "No space left on device")):
            rev = s.save_settings(n)
        self.assertEqual(s.settings["_rev"], rev)
        self.assertEqual(s.settings["security"]["minutes"], 7)
        s.close()

    def test_lost_key_keeps_local_sign_in_required(self):
        from eaveluxos import secretbox
        from eaveluxos.store import Store
        if not secretbox.available():
            self.skipTest("cryptography not installed")
        s = Store(self.dir)
        s.save_user(None, "owner", "admin", password="correct horse battery")
        s.save_secrets(local_login=True)
        self.assertTrue(s.local_login_required())
        s.close()
        (self.dir / "data" / "secret.key").unlink()        # key lost; a new one gets made
        s = Store(self.dir)
        self.assertIsNone(s.secrets.get("local_login"))
        self.assertTrue(s.local_login_required())
        s.close()


class PureStatusTests(unittest.TestCase):
    def test_status_read_does_not_end_a_flash_or_preview(self):
        import copy
        from datetime import timedelta
        from eaveluxos.api import TrimlightAPI
        from eaveluxos.controller import Controller
        from eaveluxos.schedule import build_config
        from eaveluxos.store import DEFAULT_SETTINGS
        st = copy.deepcopy(DEFAULT_SETTINGS)
        st["location"].update(latitude=39.95, longitude=-75.17)
        cfg = build_config(st, {"client_id": "x", "client_secret": "y"})
        c = Controller(cfg, TrimlightAPI("x", "y"))
        c.flash = {"until": cfg.loc.now() - timedelta(minutes=1)}
        c.override = {"on": False, "effect": None, "obj": None, "since": cfg.loc.now(), "expires": time.time() - 1}
        c.adjust = {"brightness": 40}
        before = len(c.events)
        for _ in range(3):
            out = c.status()
            self.assertFalse(out["flash"]["active"])
            self.assertFalse(out["override"])
        self.assertIsNotNone(c.flash)
        self.assertIsNotNone(c.override)
        self.assertEqual(len(c.events), before)
        with c.lock:
            c._target(commit=True)
        self.assertIsNone(c.flash)
        self.assertIsNone(c.override)
        self.assertEqual(c.adjust, {})


class WeatherWordsTests(unittest.TestCase):
    def test_snow_showers_are_not_rain(self):
        from eaveluxos.weather import classify
        self.assertEqual(classify("Snow Showers"), {"snow"})
        self.assertEqual(classify("Light Snow Shower"), {"snow"})
        self.assertEqual(classify("Rain and Snow Showers"), {"rain", "snow"})
        self.assertEqual(classify("Rain Showers"), {"rain"})
        self.assertIn("rain", classify("Freezing Rain"))


class RateLimitKeyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = Path(tempfile.mkdtemp())
        cls.app = App(cls.dir)
        cls.app.store.save_user(None, "owner", "admin", password="correct horse battery")
        cls.srv = make_server(cls.app, "127.0.0.1", 0)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.app.store.close()
        shutil.rmtree(cls.dir, ignore_errors=True)

    def login(self, xff, pw):
        import urllib.request
        r = urllib.request.Request(f"http://127.0.0.1:{self.port}/api/login",
                                   data=json.dumps({"username": "owner", "password": pw}).encode(),
                                   headers={"Content-Type": "application/json", "X-Requested-With": "eaveluxos",
                                            "X-Forwarded-For": xff})
        try:
            with urllib.request.urlopen(r, timeout=10) as x:
                return x.status
        except urllib.error.HTTPError as e:
            return e.code

    def test_one_bad_client_behind_proxy_does_not_lock_out_others(self):
        self.app.fails["198.51.100.7"] = [time.time()] * 10
        self.assertEqual(self.login("198.51.100.7", "x"), 429)
        self.assertEqual(self.login("203.0.113.5", "correct horse battery"), 200)

    def test_spoofed_first_hop_is_ignored(self):
        self.app.fails["198.51.100.8"] = [time.time()] * 10
        self.assertEqual(self.login("1.2.3.4, 198.51.100.8", "x"), 429)

    def test_ipv6_counted_per_64(self):
        self.app.fails["2001:db8:1:2::/64"] = [time.time()] * 10
        self.assertEqual(self.login("2001:db8:1:2::abcd", "x"), 429)


if __name__ == "__main__":
    unittest.main()
