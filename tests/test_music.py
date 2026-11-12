# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Music shows: while one runs, this app sends nothing to the controller, so
the Trimlight app's music mode isn't interrupted or "restored" away."""
import copy
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from eaveluxos.controller import Controller
from eaveluxos.schedule import ConfigError, Location, build_config, build_music
from eaveluxos.store import DEFAULT_SETTINGS

NY = ZoneInfo("America/New_York")


class CountingAPI:
    def __init__(self):
        self.switch, self.calls = 0, []
        self.clock_offset_min = 0

    def list_devices(self):
        return [{"deviceId": "D1", "name": "House"}]

    def get_device(self, d, now):
        self.calls.append(("get",))
        return {"name": "House", "connectivity": 1, "switchState": self.switch, "effects": []}

    def set_switch(self, d, v):
        self.switch = v
        self.calls.append(("switch", v))

    def preview_effect(self, d, p):
        self.calls.append(("preview", p.get("mode")))


def settings(shows=None, minutes=60):
    s = copy.deepcopy(DEFAULT_SETTINGS)
    s["location"].update(latitude=39.95, longitude=-75.17)
    s["rules"] = [{"name": "Night", "on": "17:00", "off": "23:00", "effect": "warm_white"}]
    s["music"] = {"minutes": minutes, "shows": shows or []}
    return s


class MusicConfigTests(unittest.TestCase):
    def loc(self):
        return build_config(settings(), {}, need_secrets=False).loc

    def test_defaults(self):
        m = build_music({}, self.loc())
        self.assertEqual((m["minutes"], m["schedule"], m["shows"]), (60, None, []))

    def test_show_nights_parse_like_rules(self):
        m = build_music({"music": {"shows": [{"name": "TSO", "on": "sunset + 30", "off": "21:00",
                                              "days": ["fri", "sat"], "dates": "12-01..12-31"}]}}, self.loc())
        self.assertEqual(m["shows"], [{"name": "TSO"}])
        self.assertIsNotNone(m["schedule"])

    def test_bad_values_are_refused(self):
        for bad in ({"minutes": 2}, {"minutes": 9999}, {"minutes": "x"},
                    {"shows": [{"name": "A", "on": "19:00", "off": "21:00"}, {"name": "A", "on": "19:00", "off": "21:00"}]},
                    {"shows": [{"name": "A", "on": "nope", "off": "21:00"}]},
                    {"shows": [{"name": "A", "on": "19:00"}]},
                    {"shows": "x"}):
            with self.subTest(bad=bad), self.assertRaises(ConfigError):
                build_music({"music": bad}, self.loc())


class MusicControllerTests(unittest.TestCase):
    def setUp(self):
        self.clock = [datetime(2026, 12, 4, 18, 0, tzinfo=NY)]   # a Friday, lights on
        self._orig_now = Location.now
        Location.now = lambda loc: self.clock[0]
        self.api = CountingAPI()

    def tearDown(self):
        Location.now = self._orig_now

    def make(self, shows=None):
        self.cfg = build_config(settings(shows), {"client_id": "x", "client_secret": "y"})
        self.c = Controller(self.cfg, self.api)
        return self.c

    def at(self, h, m=0, day=4):
        self.clock[0] = datetime(2026, 12, day, h, m, tzinfo=NY)
        self.c.next_try = 0
        self.c.last_verify = 0          # a read-back would be due
        self.c.tick()
        return self.c._target(commit=False)

    def test_button_show_sends_nothing_until_it_ends(self):
        c = self.make()
        self.at(18, 0)
        self.assertEqual(self.api.switch, 1)
        self.api.calls.clear()
        c.start_music(30)
        for minute in (5, 10, 20, 29):
            self.assertEqual(self.at(18, minute).reason, "music")
        self.assertEqual(self.api.calls, [])                 # no commands, no read-backs
        st = c.status()["music"]
        self.assertTrue(st["active"])
        self.assertFalse(st["scheduled"])
        t = self.at(18, 31)                                   # 30 minutes later: schedule again
        self.assertEqual(t.reason, "schedule")
        self.assertIn(("switch", 1), self.api.calls)          # sent in full, not assumed on
        self.assertTrue(any(x[0] == "preview" for x in self.api.calls))

    def test_until_stopped_and_stop(self):
        c = self.make()
        self.at(18, 0)
        c.start_music(None)
        self.assertIsNone(c.status()["music"]["until"])
        self.assertEqual(self.at(22, 0).reason, "music")
        self.api.calls.clear()
        c.stop_music()
        self.assertEqual(c._target(commit=False).reason, "schedule")
        self.assertIn(("switch", 1), self.api.calls)

    def test_choosing_a_pattern_ends_the_show(self):
        c = self.make()
        self.at(18, 0)
        c.start_music(None)
        c.manual(True, "warm_white")
        self.assertEqual(c._target(commit=False).reason, "manual")

    def test_resume_ends_the_show(self):
        c = self.make()
        self.at(18, 0)
        c.start_music(None)
        c.resume()
        self.assertEqual(c._target(commit=False).reason, "schedule")

    def test_security_flash_still_wins(self):
        c = self.make()
        c.cfg.security["effect"] = "warm_white"
        self.at(18, 0)
        c.start_music(None)
        c.start_flash(5)
        self.assertEqual(c._target(commit=False).reason, "flash")
        self.assertEqual(self.at(18, 6).reason, "music")      # the show carries on after it

    def test_show_night_runs_and_can_be_stopped_for_tonight_only(self):
        c = self.make([{"name": "TSO Friday", "on": "19:00", "off": "21:00", "days": ["fri"]}])
        self.assertEqual(self.at(18, 30).reason, "schedule")
        nxt = c.status()["music"]["next"]
        self.assertEqual(nxt["name"], "TSO Friday")
        self.api.calls.clear()
        t = self.at(19, 1)
        self.assertEqual((t.reason, t.source), ("music", "TSO Friday"))
        self.assertTrue(c.status()["music"]["scheduled"])
        self.assertEqual(self.api.calls, [])
        c.stop_music()
        self.assertEqual(self.at(19, 30).reason, "schedule")
        self.assertEqual(self.at(19, 1, day=11).reason, "music")   # next Friday runs again

    def test_status_read_does_not_end_a_show(self):
        c = self.make()
        self.at(18, 0)
        c.start_music(10)
        self.clock[0] = datetime(2026, 12, 4, 18, 30, tzinfo=NY)
        c.status()
        self.assertIsNotNone(c.music)                         # only the scheduler ends it
        self.c.tick()
        self.assertIsNone(c.music)

    def test_lights_off_when_show_ends_outside_schedule(self):
        c = self.make()
        self.at(22, 50)
        c.start_music(15)
        self.api.calls.clear()
        self.assertFalse(self.at(23, 6).on)
        self.assertIn(("switch", 0), self.api.calls)

    def test_flash_refused_to_start_show_while_flashing(self):
        c = self.make()
        c.cfg.security["effect"] = "warm_white"
        self.at(18, 0)
        c.start_flash(5)
        with self.assertRaises(ValueError):
            c.start_music(30)


if __name__ == "__main__":
    unittest.main()


class MusicApiTests(unittest.TestCase):
    """Through the web API: the button, the webhook, and who may use them."""
    @classmethod
    def setUpClass(cls):
        import os
        import shutil  # noqa: F401
        import tempfile
        import threading
        from pathlib import Path
        from tests import fake_trimlight as F
        import eaveluxos.api
        cls.F = F
        cls.cloud = F.start()
        # Other test modules point the shared client at their own fake cloud;
        # put theirs back afterwards.
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
        cls.app.store.save_secrets(client_id=F.CID, client_secret=F.SECRET, webhook_token="w" * 24)
        cls.app.rebuild()
        cls.srv = make_server(cls.app, "127.0.0.1", 0)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        import shutil
        cls.srv.shutdown()
        cls.srv.server_close()
        if cls.app.ctrl:
            cls.app.ctrl.stop_event.set()
        cls.app.store.close()
        shutil.rmtree(cls.dir, ignore_errors=True)
        import os
        import eaveluxos.api
        env, base = cls._saved
        if env is None:
            os.environ.pop("TRIMLIGHT_API_BASE", None)
        else:
            os.environ["TRIMLIGHT_API_BASE"] = env
        eaveluxos.api.BASE_URL = base

    def call(self, path, body=None, hdr=None):
        import json
        import urllib.error
        import urllib.request
        h = {"Content-Type": "application/json", "X-Requested-With": "eaveluxos", **(hdr or {})}
        r = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}",
                                   data=None if body is None else json.dumps(body).encode(), headers=h)
        try:
            with urllib.request.urlopen(r, timeout=20) as x:
                return x.status, json.loads(x.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def tearDown(self):
        self.call("/api/action", {"action": "stop_music"})

    def test_start_and_stop_from_the_app(self):
        st, r = self.call("/api/action", {"action": "music", "minutes": 45})
        self.assertEqual(st, 200, r)
        self.assertTrue(r["music"]["active"])
        self.assertTrue(r["music"]["until"])
        st, r = self.call("/api/action", {"action": "music", "minutes": 0})       # until stopped
        self.assertIsNone(r["music"]["until"])
        st, r = self.call("/api/action", {"action": "stop_music"})
        self.assertFalse(r["music"]["active"])

    def test_bad_length_is_refused(self):
        st, r = self.call("/api/action", {"action": "music", "minutes": "lots"})
        self.assertEqual(st, 400)

    def test_webhook_starts_a_show_with_the_usual_length(self):
        st, r = self.call("/api/hook/music", {}, {"X-Token": "w" * 24})
        self.assertEqual((st, r.get("reason")), (200, "music"), r)
        self.assertTrue(self.app.ctrl.status()["music"]["until"])
        st, r = self.call("/api/hook/stop_music", {}, {"X-Token": "w" * 24})
        self.assertEqual(r.get("reason"), "schedule")

    def test_viewer_cannot_start_a_show(self):
        self.call("/api/users", {"username": "owner", "role": "admin", "password": "password-xxxx"})
        self.call("/api/users", {"username": "guest", "role": "viewer", "password": "password-xxxx"})
        proxy = {"X-Forwarded-For": "203.0.113.66"}
        st, r = self.call("/api/login", {"username": "guest", "password": "password-xxxx"}, proxy)
        self.assertEqual(st, 200, r)
        st, r = self.call("/api/action", {"action": "music"}, {**proxy, "X-Session": r["token"]})
        self.assertEqual(st, 403)

    def test_show_nights_save_and_validate(self):
        st, cur = self.call("/api/settings")
        cur["music"] = {"minutes": 90, "shows": [{"name": "TSO", "on": "sunset + 30", "off": "21:30",
                                                  "days": ["fri", "sat"], "dates": "12-01..12-31"}]}
        st, r = self.call("/api/settings", cur)
        self.assertEqual(st, 200, r)
        st, cur = self.call("/api/settings")
        cur["music"]["minutes"] = 1
        st, r = self.call("/api/settings", cur)
        self.assertEqual(st, 400)
