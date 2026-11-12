# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Regression tests for the third code review (2.3.2)."""
import copy
import json
import shutil
import tempfile
import threading
import time
import unittest
import urllib.request
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from tests import fake_trimlight as F
from eaveluxos.api import TrimlightAPI, TrimlightError
from eaveluxos.controller import Controller
from eaveluxos.safety import SafetyNet
from eaveluxos.schedule import Effect, Location, build_config
from eaveluxos.server import App, lan_addresses, make_server
from eaveluxos.store import DEFAULT_SETTINGS

NY = ZoneInfo("America/New_York")
_cloud = F.start()
BASE = f"http://127.0.0.1:{_cloud.server_address[1]}/trimlight"
H = {"Content-Type": "application/json", "X-Requested-With": "eaveluxos"}


def cfg(**extra):
    s = copy.deepcopy(DEFAULT_SETTINGS)
    s["location"].update(latitude=40.6, longitude=-75.4)
    s.update(extra)
    return build_config(s, {"client_id": F.CID, "client_secret": F.SECRET})


class Engine(unittest.TestCase):
    def test_nightly_order_with_day_filter(self):
        r = cfg(rules=[{"name": "W", "dates": "12-01..12-31", "days": ["fri", "sat"], "on": "sunset", "off": "23:00",
                        "effect": ["christmas", "warm_white", "snowfall"], "rotate": "nightly"}]).schedule.rules[0]
        seq = [r.effects[r.night_index(date(2026, 12, n))].key for n in range(1, 32) if r.applies_on(date(2026, 12, n))]
        self.assertEqual(seq[:6], ["christmas", "warm_white", "snowfall"] * 2)

    def test_preview_expires(self):
        c0 = cfg(rules=[{"name": "N", "on": "17:00", "off": "23:00", "effect": "warm_white"}])
        clock = [datetime(2026, 11, 20, 18, 0, tzinfo=NY)]
        orig = Location.now
        Location.now = lambda loc: clock[0]
        try:
            class Api:
                clock_offset_min = 0
                def list_devices(s): return [{"deviceId": "D"}]
                def get_device(s, *a): return {"connectivity": 1, "switchState": 1, "effects": []}
                def set_switch(s, *a): pass
                def preview_effect(s, *a): pass
            c = Controller(c0, Api())
            c.manual(True, obj=Effect.from_config("_t", {"colors": ["#FF0000"], "counts": [1]}), expires_min=10)
            self.assertEqual(c._target().reason, "manual")
            c.override["expires"] = time.time() - 1
            self.assertEqual(c._target().reason, "schedule")
            c.manual(False)                       # a manual change from Home never expires
            self.assertIsNone(c.override["expires"])
        finally:
            Location.now = orig


class SafetyOwnership(unittest.TestCase):
    def test_interrupted_sync_keeps_ownership_and_original_backup(self):
        d = Path(tempfile.mkdtemp())
        try:
            F.STATE["dev"]["calendar"] = []
            F.STATE["dev"]["effects"] = [e for e in F.STATE["dev"]["effects"] if not str(e.get("name", "")).startswith("Auto")]
            net, api = SafetyNet(d), TrimlightAPI(F.CID, F.SECRET, base_url=BASE)
            c0 = cfg(safety={"enabled": True, "days": 7})
            real, n = api.calendar_save, [0]

            def flaky(dev, p):
                n[0] += 1
                if n[0] == 4:
                    raise TrimlightError("timed out")
                return real(dev, p)
            api.calendar_save = flaky
            now = datetime(2026, 12, 10, 12, tzinfo=NY)
            self.assertFalse(net.sync(api, c0, ["TL-EDGE-01"], now))
            on_ctrl = {c["id"] for c in F.STATE["dev"]["calendar"]}
            self.assertTrue(on_ctrl <= set(net.state["devices"]["TL-EDGE-01"]["calendar"]))
            api.calendar_save = real
            self.assertTrue(net.sync(api, c0, ["TL-EDGE-01"], now))
            self.assertEqual(sorted(c["id"] for c in F.STATE["dev"]["calendar"]), net.state["devices"]["TL-EDGE-01"]["calendar"])
            for _ in range(22):
                net._backup("TL-EDGE-01", {"x": 1})
            names = [f.name for f in (d / "controller-backups").glob("*.json")]
            self.assertIn("TL-EDGE-01-original.json", names)
            self.assertEqual(len(names), 21)
        finally:
            shutil.rmtree(d, ignore_errors=True)


@unittest.skipUnless(lan_addresses(), "needs a LAN address to act as a phone")
class Browser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = Path(tempfile.mkdtemp())
        cls.app = App(cls.dir)
        cls.srv = make_server(cls.app, "0.0.0.0", 0)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.ip = lan_addresses()[0]
        cls.call("127.0.0.1", "/api/password", {"new": "porchlights1"})

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        shutil.rmtree(cls.dir, ignore_errors=True)

    @classmethod
    def call(cls, host, path, body=None, headers=H):
        r = urllib.request.Request(f"http://{host}:{cls.port}{path}", data=None if body is None else json.dumps(body).encode(), headers=headers)
        try:
            with urllib.request.urlopen(r, timeout=10) as x:
                return x.status, json.loads(x.read()), x.headers
        except urllib.error.HTTPError as e:
            return e.code, None, e.headers

    def test_phone_session_is_a_header_not_a_cookie(self):
        st, body, hdr = self.call(self.ip, "/api/login", {"password": "porchlights1"})
        self.assertEqual(st, 200)
        self.assertNotIn("tls_session=" + body["token"], hdr.get("Set-Cookie", ""))
        self.assertEqual(self.call(self.ip, "/api/settings")[0], 401)
        self.assertEqual(self.call(self.ip, "/api/settings", headers={**H, "Cookie": "tls_session=" + body["token"]})[0], 401)
        st, s, _ = self.call(self.ip, "/api/settings", headers={**H, "X-Session": body["token"]})
        self.assertEqual(st, 200)
        s["service"]["allowed_hosts"] = ["attacker.example"]
        s["service"]["web_port"] = 1
        self.assertEqual(self.call(self.ip, "/api/settings", s, headers={**H, "X-Session": body["token"]})[0], 200)
        self.assertNotIn("allowed_hosts", self.app.store.settings["service"])
        self.assertNotEqual(self.app.store.settings["service"].get("web_port"), 1)

    def test_security_headers(self):
        _, _, h = self.call("127.0.0.1", "/api/session")
        csp = h["Content-Security-Policy"]
        for part in ("script-src 'self'", "object-src 'none'", "base-uri 'none'", "frame-ancestors 'none'", "form-action 'self'"):
            self.assertIn(part, csp)
        self.assertEqual(h["X-Frame-Options"], "DENY")
        self.assertEqual(h["Cross-Origin-Resource-Policy"], "same-origin")
        self.assertEqual(h["X-Content-Type-Options"], "nosniff")


if __name__ == "__main__":
    unittest.main()
