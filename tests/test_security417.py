# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""4.17 local-first and security: API tokens, the audit log, encrypted
backups, handing over to the controller's own timers, and running over the
home network without the internet."""
import base64
import copy
import json
import os
import shutil
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from eaveluxos import lanlink as L
from eaveluxos import vault
from eaveluxos.server import App, make_server
from tests.test_local43 import ServerBase

H = {"Content-Type": "application/json", "X-Requested-With": "eaveluxos"}
PROXY = {**H, "X-Forwarded-For": "203.0.113.66"}      # someone on another device, through a proxy


class Live(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.app = App(self.dir, start=False)
        self.srv = make_server(self.app, "127.0.0.1", 0)
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.app.store.close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def call(self, path, body=None, hdr=H):
        r = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}",
                                   data=None if body is None else json.dumps(body).encode(), headers=hdr)
        try:
            with urllib.request.urlopen(r, timeout=20) as x:
                raw = x.read()
                try:
                    return x.status, json.loads(raw)
                except ValueError:
                    return x.status, raw
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                return e.code, json.loads(raw)
            except ValueError:
                return e.code, raw

    def token(self, role="editor", days=None, name="Home Assistant"):
        st, r = self.call("/api/tokens", {"name": name, "role": role, "days": days})
        self.assertEqual(st, 200, r)
        return r["token"]


class Tokens(Live):
    def test_a_token_works_like_its_role(self):
        tok = self.token("viewer")
        bearer = {"Content-Type": "application/json", "Authorization": f"Bearer {tok}", "X-Forwarded-For": "203.0.113.9"}
        self.assertEqual(self.call("/api/settings", hdr=bearer)[0], 200)
        st, r = self.call("/api/settings", {"rules": []}, bearer)        # no X-Requested-With needed with a token
        self.assertEqual(st, 403, r)
        self.assertIn("only view", r["error"])

    def test_never_accounts_tokens_or_updates(self):
        tok = self.token("admin")
        bearer = {"Content-Type": "application/json", "Authorization": f"Bearer {tok}"}
        for path, body in (("/api/users", {"username": "x", "password": "longenough1", "role": "admin"}),
                           ("/api/tokens", {"name": "y", "role": "admin"}), ("/api/quit", {}),
                           ("/api/update/install", {}), ("/api/backup/encrypted", {"passphrase": "x" * 12}),
                           ("/api/credentials", {"client_id": "a", "client_secret": "b"})):
            st, r = self.call(path, body, bearer)
            self.assertEqual(st, 403, (path, r))
        rows = self.app.store.audit_rows()
        self.assertTrue(any(not x["ok"] and x["who"] == "token: Home Assistant" for x in rows), rows[:3])

    def test_revoked_expired_and_wrong_tokens_dont_work(self):
        tok = self.token("editor")
        bearer = {"Authorization": f"Bearer {tok}", "X-Forwarded-For": "203.0.113.9"}
        self.assertEqual(self.call("/api/status", hdr=bearer)[0], 200)
        tid = self.app.store.tokens()[0]["id"]
        self.assertEqual(self.call("/api/tokens/revoke", {"id": tid})[0], 200)
        self.assertEqual(self.call("/api/status", hdr=bearer)[0], 401)
        self.assertEqual(self.call("/api/status", hdr={"Authorization": "Bearer elx_nope", "X-Forwarded-For": "1.2.3.4"})[0], 401)
        old = self.token("editor", days=1, name="old")
        self.app.store.con.execute("UPDATE tokens SET expires=? WHERE name='old'", (time.time() - 5,))
        self.assertEqual(self.call("/api/status", hdr={"Authorization": f"Bearer {old}", "X-Forwarded-For": "1.2.3.4"})[0], 401)
        self.assertTrue(self.app.store.tokens()[0]["expired"])

    def test_only_the_hash_is_kept_and_last_use_is_noted(self):
        tok = self.token("editor")
        raw = self.app.store.con.execute("SELECT * FROM tokens").fetchall()
        self.assertNotIn(tok, json.dumps(raw))
        self.call("/api/status", hdr={"Authorization": f"Bearer {tok}", "X-Forwarded-For": "203.0.113.9"})
        t = self.app.store.tokens()[0]
        self.assertIsNotNone(t["last_used"])
        self.assertEqual(t["hint"], tok[-4:])

    def test_bad_requests(self):
        for body in ({"name": "", "role": "editor"}, {"name": "x", "role": "god"}, {"name": "x", "role": "editor", "days": 0},
                     {"name": "x" * 61, "role": "viewer"}):
            self.assertEqual(self.call("/api/tokens", body)[0], 400, body)

    def test_from_a_phone_making_a_token_asks_for_the_password_again(self):
        self.call("/api/password", {"new": "porchlights1"})
        s = self.call("/api/login", {"password": "porchlights1"}, PROXY)[1]["token"]
        st, r = self.call("/api/tokens", {"name": "x", "role": "viewer"}, {**PROXY, "X-Session": s})
        self.assertEqual(st, 403)
        self.assertTrue(r.get("reauth"))


class Audit(Live):
    def test_changes_are_logged_without_secrets(self):
        s = self.call("/api/settings")[1]
        s["rules"] = s.get("rules", [])[:1]
        s["security"] = {**s.get("security", {}), "minutes": 7}
        self.assertEqual(self.call("/api/settings", s)[0], 200)
        self.call("/api/password", {"new": "porchlights1"})
        rows = self.app.store.audit_rows()
        what = [r["what"] for r in rows]
        self.assertIn("Changed settings", what)
        self.assertIn("Changed a password", what)
        ch = next(r for r in rows if r["what"] == "Changed settings")
        self.assertIn("security", ch["detail"])
        self.assertEqual(ch["who"], "this computer")
        self.assertNotIn("porchlights1", json.dumps(rows))

    def test_looking_isnt_logged(self):
        n = len(self.app.store.audit_rows())
        for p in ("/api/settings", "/api/status", "/api/catalog"):
            self.call(p)
        self.call("/api/rulecheck", {})
        self.assertEqual(len(self.app.store.audit_rows()), n)

    def test_admins_only_and_csv(self):
        self.app.store.audit("chris", "Changed settings", "Changed: rules, \"quoted\"")
        st, r = self.call("/api/audit?q=rules")
        self.assertEqual(st, 200)
        self.assertEqual(len(r["rows"]), 1)
        st, raw = self.call("/api/audit?format=csv")
        self.assertEqual(st, 200)
        self.assertIn(b'""quoted""', raw)
        tok = self.token("editor")
        self.assertEqual(self.call("/api/audit", hdr={"Authorization": f"Bearer {tok}"})[0], 403)

    def test_search_is_literal(self):
        self.app.store.audit("a", "100% off", "")
        self.app.store.audit("a", "something", "")
        self.assertEqual([r["what"] for r in self.app.store.audit_rows(q="%")], ["100% off"])

    def test_kept_to_a_year(self):
        from eaveluxos import store as S
        old = time.time() - (S.AUDIT_KEEP_DAYS + 5) * 86400
        for i in range(199):
            self.app.store.audit("x", f"old {i}", at=old)
        self.app.store.audit("x", "new")           # the 200th row: tidy-up time
        self.assertEqual([r["what"] for r in self.app.store.audit_rows()], ["new"])


class Vault(unittest.TestCase):
    def setUp(self):
        if not vault.available():
            self.skipTest("no cryptography")

    def test_round_trip_wrong_passphrase_and_tampering(self):
        b = vault.seal({"a": 1}, "correct horse")
        self.assertEqual(vault.open_(b, "correct horse"), {"a": 1})
        with self.assertRaises(vault.VaultError):
            vault.open_(b, "wrong horse!")
        t = dict(b)
        raw = bytearray(base64.b64decode(t["data"]))
        raw[3] ^= 1
        t["data"] = base64.b64encode(bytes(raw)).decode()
        with self.assertRaises(vault.VaultError):
            vault.open_(t, "correct horse")
        t = json.loads(json.dumps(b))
        t["kdf"]["n"] = 2 ** 14                # the header is checked too
        with self.assertRaises(vault.VaultError):
            vault.open_(t, "correct horse")
        with self.assertRaises(vault.VaultError):
            vault.seal({}, "short")
        with self.assertRaises(vault.VaultError):
            vault.open_({"format": "nope"}, "x")


class Backup(Live):
    def setUp(self):
        super().setUp()
        if not vault.available():
            self.skipTest("no cryptography")

    def test_back_up_and_put_back_on_another_computer(self):
        self.app.store.save_secrets(client_id="cid-1", client_secret="sec-1")
        self.call("/api/users", {"username": "chris", "password": "porchlights1", "role": "admin"})
        s = self.call("/api/settings")[1]
        s["security"] = {**s.get("security", {}), "minutes": 9}
        self.call("/api/settings", s)
        (self.app.store.dir / "photos").mkdir(exist_ok=True)
        (self.app.store.dir / "photos" / "front.jpg").write_bytes(b"\xff\xd8photo")
        st, blob = self.call("/api/backup/encrypted", {"passphrase": "a long passphrase", "photos": True})
        self.assertEqual(st, 200, blob)
        text = json.dumps(blob)
        for secret in ("cid-1", "sec-1", "porchlights1", "chris"):
            self.assertNotIn(secret, text)
        # Another computer
        other = Live("run"); other.setUp(); self.addCleanup(other.tearDown)
        port_before = other.app.store.settings.get("service")
        st, r = other.call("/api/backup/restore", {"backup": blob, "passphrase": "wrong passphrase"})
        self.assertEqual(st, 400)
        st, r = other.call("/api/backup/restore", {"backup": blob, "passphrase": "a long passphrase"})
        self.assertEqual(st, 200, r)
        self.assertEqual((r["accounts"], r["photos"]), (1, 1))
        self.assertEqual(other.app.store.settings["security"]["minutes"], 9)
        self.assertEqual(other.app.store.secrets.get("client_secret"), "sec-1")
        self.assertEqual([u["username"] for u in other.app.store.users()], ["chris"])
        self.assertEqual(other.app.store.settings.get("service"), port_before, "where this app runs stays")
        self.assertEqual((other.app.store.dir / "photos" / "front.jpg").read_bytes(), b"\xff\xd8photo")

    def test_odd_photo_names_are_skipped(self):
        body = {"settings": copy.deepcopy(self.app.store.settings), "secrets": {}, "users": [],
                "photos": {"../../evil.jpg": base64.b64encode(b"x").decode(), "ok.jpg": base64.b64encode(b"y").decode()}}
        body["settings"].pop("_rev", None)
        st, r = self.call("/api/backup/restore", {"backup": vault.seal(body, "a long passphrase"), "passphrase": "a long passphrase"})
        self.assertEqual((st, r.get("photos")), (200, 1), r)
        self.assertFalse((self.dir / "evil.jpg").exists())

    def test_a_backup_without_an_administrator_is_refused(self):
        body = {"settings": {}, "users": [{"id": "1", "username": "v", "password_hash": "x", "role": "viewer"}]}
        st, r = self.call("/api/backup/restore", {"backup": vault.seal(body, "a long passphrase"), "passphrase": "a long passphrase"})
        self.assertEqual(st, 400)


class HandOver(ServerBase):
    def test_on_quit_the_controllers_own_timers_take_over_when_asked(self):
        self.app.local_commands(True)
        c = self.app.ctrl
        c.devices = [{"deviceId": "TL-EDGE-01", "name": "Trimlight"}]
        self.assertEqual(self.app.hand_over(), [], "off unless asked")
        self.app.timer_on_quit(True)
        self.app.ctrl.devices = [{"deviceId": "TL-EDGE-01", "name": "Trimlight"}]
        self.assertEqual(self.app.hand_over(), ["Trimlight"])
        got = [b for _, _, b in self.ctl.frames(L.CMD_REQUEST) if b[0] == L.SUB_POWER]
        self.assertEqual(got[-1], L.request(L.SUB_POWER, bytes([L.POWER_TIMER])), "Timer mode (2)")

    def test_the_setting_is_checked(self):
        from eaveluxos.server import ApiError
        with self.assertRaises(ApiError):
            self.app.timer_on_quit("yes")
        s = copy.deepcopy(self.app.store.settings)
        s["lan"] = {**s["lan"], "timer_on_quit": "yes"}
        with self.assertRaises(Exception):
            self.app.save_settings(s)


class NoInternet(ServerBase):
    def test_the_lights_still_run_over_the_home_network(self):
        self.app.local_commands(True)
        c = self.app.ctrl
        c.devices, c.next_try = [], 0
        c.tick()                                         # online: the controllers are noted
        c.api.base_url = "http://127.0.0.1:9"            # then the internet goes
        c.devices = []
        n = len(self.ctl.frames(L.CMD_REQUEST))
        c.manual(True, "christmas")
        c.next_try = 0
        c.tick()
        self.assertGreater(len(self.ctl.frames(L.CMD_REQUEST)), n, "sent over the home network")
        self.assertTrue(any("can't be reached" in e["msg"] for e in list(c.events)))
        self.assertTrue(c.status()["cloud_down"])

    def test_without_a_list_from_before_it_says_so(self):
        self.app.local_commands(True)
        c = self.app.ctrl
        c.api.base_url = "http://127.0.0.1:9"
        c.devices, c.next_try = [], 0
        c.tick()
        self.assertFalse(c.devices)
        self.assertTrue(any("Couldn't reach the lights" in e["msg"] for e in list(c.events)))


class ReviewFixes(Live):
    def test_1_a_token_doesnt_read_the_accounts_secrets(self):
        from tests import reprorun
        reprorun.run(self, "repro_token_reads_secrets.py", 60)

    def test_2_sliders_and_previews_dont_fill_the_log(self):
        n = len(self.app.store.audit_rows())
        for _ in range(5):
            self.call("/api/action", {"action": "levels", "brightness": 120})
        self.assertEqual(len(self.app.store.audit_rows()), n)

    def test_3_a_big_backup_can_be_put_back_by_an_administrator_only(self):
        from eaveluxos import server as S
        self.assertGreater(S.RESTORE_MAX, 60 * 1024 * 1024 * 4 // 3)    # 60 MB of photos, as base64
        big = b'{"backup": "' + b"x" * (S.MAX_BODY + 10) + b'"}'
        r = urllib.request.Request(f"http://127.0.0.1:{self.port}/api/backup/restore", data=big, headers=H)
        try:
            urllib.request.urlopen(r, timeout=20)
            code = 200
        except urllib.error.HTTPError as e:
            code = e.code
        self.assertEqual(code, 400, "read (and refused as not a backup), not 413")
        tok = self.token("admin")
        r = urllib.request.Request(f"http://127.0.0.1:{self.port}/api/backup/restore", data=big,
                                   headers={"Content-Type": "application/json", "Authorization": f"Bearer {tok}"})
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(r, timeout=20)
        self.assertEqual(cm.exception.code, 413)


if __name__ == "__main__":
    unittest.main()
