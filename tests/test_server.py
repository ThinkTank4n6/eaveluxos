# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""The web app end to end against a fake Trimlight cloud: security checks,
setup flow, edit conflicts, and controller clock handling."""
import json
import os
import shutil
import socket
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

from tests import fake_trimlight as F

_cloud = F.start()
os.environ["TRIMLIGHT_API_BASE"] = f"http://127.0.0.1:{_cloud.server_address[1]}/trimlight"

import eaveluxos.api  # noqa: E402
eaveluxos.api.BASE_URL = os.environ["TRIMLIGHT_API_BASE"]
from eaveluxos.server import App, host_allowed, make_server  # noqa: E402

H = {"Content-Type": "application/json", "X-Requested-With": "eaveluxos"}


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = Path(tempfile.mkdtemp())
        cls.app = App(cls.dir)
        cls.srv = make_server(cls.app, "127.0.0.1", 0)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.app.start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        if cls.app.ctrl:
            cls.app.ctrl.stop_event.set()
        shutil.rmtree(cls.dir, ignore_errors=True)

    def call(self, path, body=None, headers=H):
        r = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}",
                                   data=None if body is None else json.dumps(body).encode(), headers=headers)
        try:
            with urllib.request.urlopen(r, timeout=10) as x:
                return x.status, json.loads(x.read())
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                return e.code, json.loads(raw)
            except ValueError:
                return e.code, raw

    def settings(self):
        return self.call("/api/settings")[1]

    def test_1_setup_flow_and_secret_never_returned(self):
        st, r = self.call("/api/credentials", {"client_id": F.CID, "client_secret": "wrong"})
        self.assertEqual(st, 400)
        st, r = self.call("/api/credentials", {"client_id": F.CID, "client_secret": F.SECRET})
        self.assertEqual(st, 200)
        self.assertEqual(r["devices"][0]["id"], "TL-EDGE-01")
        s = self.settings()
        s["location"].update(latitude=39.9, longitude=-75.4)
        self.assertEqual(self.call("/api/settings", s)[0], 200)
        acct = json.dumps(self.call("/api/account")[1])
        self.assertNotIn(F.SECRET, acct)
        if os.name != "nt":   # Windows uses ACLs, not mode bits (see store._restrict_windows)
            self.assertEqual(oct(os.stat(self.dir / "data" / "eaveluxos.db").st_mode & 0o777), "0o600")

    def test_2_csrf_header_required(self):
        self.assertEqual(self.call("/api/action", {"action": "off"}, {"Content-Type": "application/json"})[0], 403)

    def test_3_dns_rebinding_blocked(self):
        self.assertEqual(self.call("/api/account", headers={**H, "Host": "evil.example:1"})[0], 421)
        self.assertTrue(host_allowed("192.168.1.20:8787", []))
        self.assertTrue(host_allowed("[::1]:8787", []))
        self.assertTrue(host_allowed("localhost:8787", []))
        self.assertTrue(host_allowed("lights.example.net", ["lights.example.net"]))
        self.assertFalse(host_allowed("evil.example", []))

    def test_4_bad_content_length(self):
        for cl in (b"-1", b"abc", b"99999999"):
            s = socket.create_connection(("127.0.0.1", self.port), timeout=3)
            s.sendall(b"POST /api/action HTTP/1.1\r\nHost: 127.0.0.1\r\nX-Requested-With: eaveluxos\r\nContent-Length: " + cl + b"\r\n\r\n")
            self.assertRegex(s.recv(64), rb"HTTP/1\.[01] (400|413)")
            s.close()

    def test_4b_keep_alive_requests_get_their_own_bodies(self):
        import http.client
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        replies = []
        for secret in ("wrong-one", F.SECRET):
            c.request("POST", "/api/credentials", json.dumps({"client_id": F.CID, "client_secret": secret}), H)
            r = c.getresponse()
            replies.append(r.status)
            r.read()
        c.close()
        self.assertEqual(replies, [400, 200])

    def test_5_stale_save_is_refused(self):
        a, b = self.settings(), self.settings()
        a["effects"]["phone_a"] = {"label": "A", "colors": ["#FF0000"], "counts": [1]}
        b["effects"]["phone_b"] = {"label": "B", "colors": ["#00FF00"], "counts": [1]}
        self.assertEqual(self.call("/api/settings", a)[0], 200)
        self.assertEqual(self.call("/api/settings", b)[0], 409)
        self.assertIn("phone_a", self.settings()["effects"])

    def test_6_invalid_rule_rejected_even_before_location(self):
        s = self.settings()
        s["location"].update(latitude=0, longitude=0)
        s["rules"].append({"name": "Broken", "on": "whenever", "off": "23:00", "effect": "warm_white"})
        self.assertEqual(self.call("/api/settings", s)[0], 400)

    def test_7_controller_time_offset_sticks(self):
        F.STATE["log"].clear()
        st, r = self.call("/api/device/clock", {"datetime": "2026-12-24T18:30"})
        self.assertEqual(st, 200)
        self.app.ctrl.last_verify = 0
        self.app.ctrl.tick()
        dates = [b["currentDate"] for p, b in F.STATE["log"] if p == "/device/get"]
        self.assertTrue(dates)
        self.assertTrue(all((d["month"], d["day"]) == (12, 24) for d in dates), dates)
        self.call("/api/device/clock", {"reset": True})
        self.assertEqual(self.app.clock_offset(), 0)

    def test_8_setup_code_closes_after_setup(self):
        s = self.settings()
        s["setup_done"] = True
        self.call("/api/settings", s)
        st, _ = self.call("/api/login", {"code": self.app.store.setup_code})
        self.assertEqual(st, 403)

    def test_91_photo_must_be_jpeg_and_named_safely(self):
        import base64
        jpg = base64.b64encode(b"\xff\xd8\xff\xe0" + b"0" * 100).decode()
        self.assertEqual(self.call("/api/photo", {"side": "front", "data": jpg})[0], 200)
        self.assertEqual(self.call("/api/photo", {"side": "front", "data": base64.b64encode(b"<svg/>").decode()})[0], 400)
        self.assertEqual(self.call("/api/photo", {"side": "../secrets", "data": jpg})[0], 400)
        self.assertEqual(self.call("/api/photos")[1], ["front"])

    def test_92_map_validation(self):
        s = self.settings()
        s["map"] = {"zones": [{"name": "Garage", "start": 90, "end": 40}]}
        self.assertEqual(self.call("/api/settings", s)[0], 400)
        s["map"] = {"zones": [{"name": "Garage", "start": 40, "end": 90}], "landmarks": [{"name": "Peak", "bulb": 120, "x": 0.4, "y": 0.3}]}
        self.assertEqual(self.call("/api/settings", s)[0], 200)
        self.assertNotIn("map", self.call("/api/export")[1]["settings"])  # house layout never exported

    def test_93_rule_that_never_wins_is_reported(self):
        s = self.settings()
        s["rules"] = [{"name": "Season", "dates": "12-01..12-31", "on": "sunset", "off": "23:00", "effect": "christmas"},
                      {"name": "Hidden", "dates": "12-05..12-10", "on": "sunset", "off": "23:00", "effect": "warm_white"}]
        self.assertEqual(self.call("/api/settings", s)[0], 200)
        rc = self.call("/api/rulecheck")[1]
        self.assertEqual(rc["Hidden"]["blocked_by"], "Season")
        self.assertIsNone(rc["Season"]["blocked_by"])

    def test_94_history_restore(self):
        s = self.settings()
        s["effects"]["temp_pattern"] = {"label": "Temp", "colors": ["#123456"], "counts": [1]}
        self.assertEqual(self.call("/api/settings", s)[0], 200)
        hist = self.call("/api/history")[1]
        before = hist[1]["rev"]
        self.assertEqual(self.call("/api/history/restore", {"rev": before})[0], 200)
        self.assertNotIn("temp_pattern", self.settings()["effects"])
        self.assertEqual(self.call("/api/history/restore", {"rev": 999999})[0], 404)

    def test_9_webhook_token(self):
        self.call("/api/webhook", {"enable": True})
        tok = self.app.store.secrets["webhook_token"]
        self.assertEqual(self.call("/api/hook/flash", {}, {"Content-Type": "application/json", "X-Token": "x" * 32})[0], 403)
        self.assertEqual(self.call("/api/hook/off", {}, {"Content-Type": "application/json", "X-Token": tok})[0], 200)
        self.assertEqual(self.call(f"/api/hook/off?token={tok}", {}, {"Content-Type": "application/json"})[0], 400)
        self.assertEqual(self.call("/api/hook/off", {"token": tok}, {"Content-Type": "application/json"})[0], 200)
        self.assertEqual(self.call("/api/hook/levels", {"token": tok, "brightness": 300}, {"Content-Type": "application/json"})[0], 400)
        self.assertEqual(self.call("/api/hook/try", {"token": tok}, {"Content-Type": "application/json"})[0], 400)


if __name__ == "__main__":
    unittest.main()


class LocalLogin(unittest.TestCase):
    """#8: optional password on the app computer itself."""
    def test_local_login_toggle_and_reset(self):
        import subprocess, sys
        d = Path(tempfile.mkdtemp())
        app = App(d)
        srv = make_server(app, "127.0.0.1", 0)
        port = srv.server_address[1]
        threading.Thread(target=srv.serve_forever, daemon=True).start()

        def call(path, body=None, hdr=H):
            r = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=None if body is None else json.dumps(body).encode(), headers=hdr)
            try:
                with urllib.request.urlopen(r, timeout=10) as x:
                    return x.status, json.loads(x.read())
            except urllib.error.HTTPError as e:
                return e.code, None
        try:
            self.assertEqual(call("/api/local_login", {"enabled": True})[0], 400)   # needs a password first
            call("/api/password", {"new": "porchlights1"})
            self.assertEqual(call("/api/local_login", {"enabled": True})[0], 200)
            self.assertEqual(call("/api/settings")[0], 401)
            tok = call("/api/login", {"password": "porchlights1"})[1]["token"]
            self.assertEqual(call("/api/settings", hdr={**H, "X-Session": tok})[0], 200)
            shutil.copy(Path(__file__).resolve().parent.parent / "main.py", d / "main.py")
            shutil.copytree(Path(__file__).resolve().parent.parent / "eaveluxos", d / "eaveluxos")
            srv.shutdown(); srv.server_close(); app.store.close()   # 3.4: reset a named account
            out = subprocess.run([sys.executable, str(d / "main.py"), "reset-password", "admin", "--stdin"], input="fresh-password1\n",
                                 capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=d)
            self.assertIn("is set", out.stdout)
            from eaveluxos.store import Store, check_password
            st = Store(d)
            self.assertTrue(check_password("fresh-password1", st.user_by_name("admin")[1]))
            self.assertFalse(st.valid_session(tok))                       # signed out everywhere
            st.close()
            srv = make_server(App(d, start=False), "127.0.0.1", 0)        # for the finally block
            threading.Thread(target=srv.serve_forever, daemon=True).start()
        finally:
            srv.shutdown()
            shutil.rmtree(d, ignore_errors=True)
