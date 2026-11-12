# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""3.4 accounts: Administrator / Editor / Viewer roles, at least one active
Administrator, sign-outs when passwords or accounts change."""
import json
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from eaveluxos.server import App, make_server

H = {"Content-Type": "application/json", "X-Requested-With": "eaveluxos"}
PROXY = {**H, "X-Forwarded-For": "203.0.113.66"}   # another device


class Roles(unittest.TestCase):
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
            with urllib.request.urlopen(r, timeout=10) as x:
                return x.status, json.loads(x.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def add(self, name, role, pw="password-" + "x" * 4):
        st, r = self.call("/api/users", {"username": name, "role": role, "password": pw})   # from this computer
        self.assertEqual(st, 200, r)
        return r["user"]

    def login(self, name, pw="password-xxxx"):
        st, r = self.call("/api/login", {"username": name, "password": pw}, PROXY)
        self.assertEqual(st, 200, r)
        return {**PROXY, "X-Session": r["token"]}

    def test_viewer_can_look_but_not_change(self):
        self.add("owner", "admin")
        self.add("guest", "viewer")
        v = self.login("guest")
        self.assertEqual(self.call("/api/settings", hdr=v)[0], 200)
        self.assertEqual(self.call("/api/session", hdr=v)[1]["user"], {"username": "guest", "role": "viewer", "local": False, "setup": False})
        acct = self.call("/api/account", hdr=v)[1]
        self.assertNotIn("webhook_token", acct)
        self.assertNotIn("client_id", acct)
        self.assertEqual(self.call("/api/users", hdr=v)[0], 403)
        for path, body in (("/api/action", {"action": "off"}), ("/api/settings", self.call("/api/settings")[1]),
                           ("/api/photo/delete", {"side": "front"}), ("/api/webhook", {"enable": True})):
            st, r = self.call(path, body, v)
            self.assertEqual(st, 403, path)
            self.assertIn("only view", r["error"])

    def test_editor_designs_but_cannot_change_household_or_accounts(self):
        self.add("owner", "admin")
        self.add("helper", "editor")
        e = self.login("helper")
        s = self.call("/api/settings", hdr=e)[1]
        s["effects"]["new_one"] = {"label": "New one", "colors": ["#FF0000"], "counts": [1], "custom_mode": 0}
        st, r = self.call("/api/settings", s, e)
        self.assertEqual(st, 200, r)
        s = self.call("/api/settings", hdr=e)[1]
        s["location"]["latitude"] = 12.5
        self.assertEqual(self.call("/api/settings", s, e)[0], 403)
        s = self.call("/api/settings", hdr=e)[1]
        s["service"]["devices"] = ["someone-elses"]
        self.assertEqual(self.call("/api/settings", s, e)[0], 403)
        for path, body in (("/api/credentials", {"client_id": "x"}), ("/api/users", {"username": "x", "role": "admin", "password": "12345678"}),
                           ("/api/history/restore", {"rev": 1}), ("/api/import", {"settings": {}, "mode": "replace"}),
                           ("/api/local_login", {"enabled": True}), ("/api/sessions/end_all", {})):
            self.assertEqual(self.call(path, body, e)[0], 403, path)
        self.assertEqual(self.call("/api/safety/backup?file=x-original.json", hdr=e)[0], 403)

    def test_at_least_one_active_admin_remains(self):
        owner = self.add("owner", "admin")
        for change in ({"role": "editor"}, {"disabled": True}):
            st, r = self.call("/api/users", {"id": owner["id"], "username": "owner", "role": "admin", **change})
            self.assertEqual(st, 400)
            self.assertIn("Administrator must remain", r["error"])
        self.assertEqual(self.call("/api/users/delete", {"id": owner["id"]})[0], 400)
        second = self.add("partner", "admin")
        self.assertEqual(self.call("/api/users", {"id": owner["id"], "username": "owner", "role": "viewer"})[0], 200)
        self.assertEqual(self.call("/api/users/delete", {"id": second["id"]})[0], 400)    # now the only admin
        st, r = self.call("/api/users", {"username": "first", "role": "editor", "password": "password-xxxx"})
        self.assertEqual(st, 200)

    def test_account_changes_sign_the_account_out(self):
        self.add("owner", "admin")
        helper = self.add("helper", "editor")
        e = self.login("helper")
        self.assertEqual(self.call("/api/users", {"id": helper["id"], "username": "helper", "role": "viewer"})[0], 200)
        self.assertEqual(self.call("/api/settings", hdr=e)[0], 401)          # role change: signed out
        e = self.login("helper")
        self.assertEqual(self.call("/api/users", {"id": helper["id"], "username": "helper", "role": "viewer", "disabled": True})[0], 200)
        self.assertEqual(self.call("/api/settings", hdr=e)[0], 401)
        self.assertEqual(self.call("/api/login", {"username": "helper", "password": "password-xxxx"}, PROXY)[0], 403)
        self.assertEqual(self.call("/api/users", {"id": helper["id"], "username": "helper", "role": "viewer"})[0], 200)
        a, b = self.login("helper"), self.login("helper")
        st, r = self.call("/api/password", {"current": "password-xxxx", "new": "another-pass-1"}, a)
        self.assertEqual(st, 200, r)
        self.assertEqual(self.call("/api/settings", hdr=a)[0], 200)           # this device stays
        self.assertEqual(self.call("/api/settings", hdr=b)[0], 401)           # the other is signed out
        self.assertEqual(self.call("/api/password", {"current": "wrong", "new": "another-pass-2"}, a)[0], 403)

    def test_remote_admin_needs_password_again_for_accounts(self):
        self.add("owner", "admin")
        a = self.login("owner")
        st, r = self.call("/api/users", {"username": "kid", "role": "viewer", "password": "password-xxxx"}, a)
        self.assertEqual((st, r.get("reauth")), (403, True))
        st, r = self.call("/api/users", {"username": "kid", "role": "viewer", "password": "password-xxxx",
                                          "confirm_password": "password-xxxx"}, a)
        self.assertEqual(st, 200, r)
        me = self.app.store.user_by_name("owner")[0]
        self.assertEqual(self.call("/api/users/delete", {"id": me["id"]}, a)[0], 400)   # not your own account

    def test_unknown_or_wrong_sign_in_looks_the_same(self):
        self.add("owner", "admin")
        bad_user = self.call("/api/login", {"username": "nobody", "password": "password-xxxx"}, PROXY)
        bad_pw = self.call("/api/login", {"username": "owner", "password": "nope-nope"}, PROXY)
        self.assertEqual(bad_user, bad_pw)

    def test_setup_code_session_creates_first_admin_and_is_switched_over(self):
        st, r = self.call("/api/login", {"code": self.app.store.setup_code}, PROXY)
        setup = {**PROXY, "X-Session": r["token"]}
        self.assertEqual(self.call("/api/session", hdr=setup)[1]["user"]["role"], "admin")
        st, r = self.call("/api/password", {"username": "owner", "new": "password-xxxx"}, setup)
        self.assertEqual(st, 200, r)
        self.assertEqual(self.call("/api/settings", hdr=setup)[0], 401)       # setup session ended
        owner = {**PROXY, "X-Session": r["token"]}
        self.assertEqual(self.call("/api/session", hdr=owner)[1]["user"]["username"], "owner")
        self.assertEqual(self.call("/api/login", {"code": self.app.store.setup_code}, PROXY)[0], 403)

    def test_session_policy_admin_only(self):
        self.add("owner", "admin")
        self.add("helper", "editor")
        self.assertEqual(self.call("/api/session_policy", {"idle_hours": 24})[1]["idle_hours"], 24)
        self.assertEqual(self.call("/api/session_policy", {"idle_hours": 99})[0], 400)
        self.assertEqual(self.call("/api/session_policy", {"idle_hours": 1}, self.login("helper"))[0], 403)


if __name__ == "__main__":
    unittest.main()
