# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""3.3 security fixes: proxied requests aren't "this computer", scrypt
passwords, AES-GCM secrets at rest, short sliding sessions, password
re-entry for security changes from phones, and make-cert."""
import hashlib
import json
import os
import shutil
import sqlite3
import ssl
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from eaveluxos import secretbox, store as store_mod
from eaveluxos.server import App, make_server
from eaveluxos.store import Store, check_password, hash_password, needs_rehash

H = {"Content-Type": "application/json", "X-Requested-With": "eaveluxos"}
PROXY = {**H, "X-Forwarded-For": "203.0.113.66"}   # what Caddy/nginx/Tailscale Serve add


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
            with urllib.request.urlopen(r, timeout=10) as x:
                return x.status, json.loads(x.read())
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                return e.code, json.loads(raw)
            except ValueError:
                return e.code, raw

    # ------------------------------------------------------------- issue 1
    def test_proxied_request_is_not_trusted_as_local(self):
        self.assertEqual(self.call("/api/settings")[0], 200)                        # owner's own browser
        for hdr in ({"X-Forwarded-For": "203.0.113.66"}, {"Forwarded": "for=203.0.113.66"},
                    {"X-Real-IP": "203.0.113.66"}, {"CF-Connecting-IP": "203.0.113.66"}, {"Via": "1.1 caddy"}):
            self.assertEqual(self.call("/api/settings", hdr={**H, **hdr})[0], 401, hdr)
            self.assertEqual(self.call("/api/action", {"action": "off"}, {**H, **hdr})[0], 401, hdr)
        st, r = self.call("/api/session", hdr=PROXY)
        self.assertFalse(r["authed"])
        self.assertFalse(r["local"])
        # quitting and removing the password stay local-only
        self.call("/api/password", {"new": "porchlights1"})
        tok = self.call("/api/login", {"password": "porchlights1"}, PROXY)[1]["token"]
        self.assertEqual(self.call("/api/quit", {}, {**PROXY, "X-Session": tok})[0], 403)

    # ------------------------------------------------------------- issue 5
    def test_security_changes_from_phone_need_password_again(self):
        self.call("/api/password", {"new": "porchlights1"})
        tok = self.call("/api/login", {"password": "porchlights1"}, PROXY)[1]["token"]
        phone = {**PROXY, "X-Session": tok}
        st, r = self.call("/api/webhook", {"enable": True}, phone)
        self.assertEqual((st, r.get("reauth")), (403, True))
        st, r = self.call("/api/webhook", {"enable": True, "confirm_password": "wrong-one"}, phone)
        self.assertEqual((st, r.get("reauth")), (403, True))
        st, r = self.call("/api/webhook", {"enable": True, "confirm_password": "porchlights1"}, phone)
        self.assertEqual(st, 200)
        self.assertTrue(r["webhook_token"])
        self.assertEqual(self.call("/api/local_login", {"enabled": False}, phone)[0], 200)   # confirmed for 5 minutes
        self.assertEqual(self.call("/api/action", {"action": "x"}, phone)[0], 409)          # ordinary use: no prompt
        self.assertEqual(self.call("/api/webhook", {"enable": False})[0], 200)               # this computer: no prompt
        self.call("/api/logout", {}, phone)
        self.assertEqual(self.call("/api/webhook", {"enable": True}, phone)[0], 401)

    def test_wrong_current_password_is_rate_limited(self):
        self.call("/api/password", {"new": "porchlights1"})
        tok = self.call("/api/login", {"password": "porchlights1"}, PROXY)[1]["token"]
        phone = {**PROXY, "X-Session": tok}
        self.app.fails["127.0.0.1"] = [time.time()] * 10
        self.assertEqual(self.call("/api/password", {"current": "x", "new": "another-pass1"}, phone)[0], 429)

    def test_password_change_signs_out_other_devices(self):
        self.call("/api/password", {"new": "porchlights1"})
        lost = self.call("/api/login", {"password": "porchlights1"}, PROXY)[1]["token"]
        mine = self.call("/api/login", {"password": "porchlights1"}, PROXY)[1]["token"]
        st, _ = self.call("/api/password", {"current": "porchlights1", "new": "brand-new-pass"}, {**PROXY, "X-Session": mine})
        self.assertEqual(st, 200)
        self.assertEqual(self.call("/api/settings", hdr={**PROXY, "X-Session": lost})[0], 401)
        self.assertEqual(self.call("/api/settings", hdr={**PROXY, "X-Session": mine})[0], 200)
        self.call("/api/password", {"new": "changed-locally"})          # from this computer: everyone out
        self.assertEqual(self.call("/api/settings", hdr={**PROXY, "X-Session": mine})[0], 401)

    # ------------------------------------------------------------- scrypt upgrade at sign-in
    def test_old_pbkdf2_password_upgraded_to_scrypt_at_sign_in(self):
        # a pre-3.3 shared password becomes the "admin" account at the next start (3.4)
        old = store_mod._legacy_pbkdf2("porchlights1", b"0123456789abcdef")
        self.app.store.save_secrets(password_hash=old)
        self.srv.shutdown(); self.srv.server_close(); self.app.store.close()
        self.app = App(self.dir, start=False)
        self.srv = make_server(self.app, "127.0.0.1", 0)
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.assertNotIn("password_hash", self.app.store.secrets)
        self.assertEqual(self.call("/api/login", {"password": "porchlights1"}, PROXY)[0], 200)   # user name defaults to admin
        new = self.app.store.user_by_name("admin")[1]
        self.assertTrue(new.startswith("scrypt$"))
        self.assertTrue(check_password("porchlights1", new))


class Passwords(unittest.TestCase):
    def test_scrypt(self):
        h = hash_password("porchlights1")
        self.assertTrue(h.startswith(f"scrypt${2 ** 15}$8$1$"))
        self.assertTrue(check_password("porchlights1", h))
        self.assertFalse(check_password("porchlights2", h))
        self.assertNotEqual(h, hash_password("porchlights1"))       # salted
        self.assertFalse(needs_rehash(h))

    def test_legacy_pbkdf2_still_accepted_and_flagged(self):
        old = store_mod._legacy_pbkdf2("porchlights1", b"0123456789abcdef")
        self.assertTrue(check_password("porchlights1", old))
        self.assertFalse(check_password("nope", old))
        self.assertTrue(needs_rehash(old))

    def test_malformed_and_hostile_parameters(self):
        for bad in ("", "scrypt$1$1$1$00$00", f"scrypt${2 ** 30}$8$1$00$00", "md5$x", None):
            self.assertFalse(check_password("x", bad))


@unittest.skipUnless(secretbox.available(), "needs the cryptography package")
class SecretsAtRest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def raw(self, st):
        return dict(st.con.execute("SELECT key, value FROM secrets"))

    def test_values_encrypted_and_readable(self):
        st = Store(self.dir)
        st.save_secrets(client_id="cid-1", client_secret="s3cr3t-value-1234", webhook_token="tok")
        raw = self.raw(st)
        self.assertTrue(all(v.startswith("enc1:") for v in raw.values()))
        self.assertNotIn(b"s3cr3t-value-1234", (st.dir / "eaveluxos.db").read_bytes())
        self.assertEqual(st.secrets["client_secret"], "s3cr3t-value-1234")
        if os.name != "nt":   # Windows uses ACLs, not mode bits (see store._restrict_windows)
            self.assertEqual(oct((st.dir / "secret.key").stat().st_mode & 0o777), "0o600")
        st.close()
        st2 = Store(self.dir)                                  # reopens with the same key
        self.assertEqual(st2.secrets["client_id"], "cid-1")
        st2.close()

    def test_plain_values_from_older_versions_are_encrypted_at_start(self):
        st = Store(self.dir)
        st.con.execute("INSERT OR REPLACE INTO secrets VALUES('client_secret', ?)", (json.dumps("old-plain"),))
        st.close()
        st = Store(self.dir)
        self.assertTrue(self.raw(st)["client_secret"].startswith("enc1:"))
        self.assertEqual(st.secrets["client_secret"], "old-plain")
        st.close()

    def test_value_cannot_be_moved_between_rows_or_tampered(self):
        st = Store(self.dir)
        st.save_secrets(client_secret="abc", webhook_token="tok")
        raw = self.raw(st)
        st.con.execute("UPDATE secrets SET value=? WHERE key='webhook_token'", (raw["client_secret"],))
        st.save_secrets(local_login=True)      # refresh cache
        self.assertNotIn("webhook_token", st.secrets)
        self.assertEqual(st.secrets["client_secret"], "abc")
        st.close()

    def test_lost_key_warns_instead_of_crashing(self):
        st = Store(self.dir)
        st.save_secrets(client_secret="abc")
        st.close()
        (self.dir / "data" / "secret.key").unlink()
        st = Store(self.dir)
        self.assertNotIn("client_secret", st.secrets)
        self.assertTrue(any("secret.key" in w for w in st.warnings))
        st.close()

    def test_key_from_environment(self):
        import os
        os.environ[secretbox.KEY_ENV] = "11" * 32
        try:
            st = Store(self.dir)
            st.save_secrets(client_secret="abc")
            self.assertFalse((st.dir / "secret.key").exists())
            self.assertEqual(st.secrets["client_secret"], "abc")
            st.close()
        finally:
            del os.environ[secretbox.KEY_ENV]


class Sessions(unittest.TestCase):
    def test_short_sliding_sessions_with_absolute_cap(self):
        d = Path(tempfile.mkdtemp())
        try:
            st = Store(d)
            admin = st.save_user(None, "owner", "admin", password="porchlights1")
            tok = st.new_session("phone", admin["id"])
            h = hashlib.sha256(tok.encode()).hexdigest()
            row = lambda: st.con.execute("SELECT expires, created FROM sessions WHERE hash=?", (h,)).fetchone()
            self.assertAlmostEqual(row()[0] - time.time(), 8 * 3600, delta=60)         # 8 hours idle by default
            st.con.execute("UPDATE sessions SET expires=? WHERE hash=?", (time.time() + 180 * 86400, h))  # pre-3.4
            self.assertTrue(st.valid_session(tok))
            self.assertLess(row()[0] - time.time(), 8 * 3600 + 60)                       # cut down
            st.con.execute("UPDATE sessions SET expires=? WHERE hash=?", (time.time() + 600, h))  # used again
            self.assertTrue(st.valid_session(tok))
            self.assertGreater(row()[0] - time.time(), 7 * 3600)                         # slid forward
            st.con.execute("UPDATE sessions SET created=? WHERE hash=?", (time.time() - 7 * 86400 - 1, h))
            self.assertFalse(st.valid_session(tok))                                      # 7-day cap
            st.set_session_idle_hours(24)
            tok = st.new_session("phone", admin["id"])
            h = hashlib.sha256(tok.encode()).hexdigest()
            self.assertAlmostEqual(row()[0] - time.time(), 24 * 3600, delta=60)
            with self.assertRaises(ValueError):
                st.set_session_idle_hours(5000)
            st.con.execute("UPDATE sessions SET expires=? WHERE hash=?", (time.time() - 1, h))
            self.assertFalse(st.valid_session(tok))
            st.close()
        finally:
            shutil.rmtree(d, ignore_errors=True)


@unittest.skipUnless(secretbox.available(), "needs the cryptography package")
class MakeCert(unittest.TestCase):
    def test_cert_loads_and_names_this_computer(self):
        from cryptography import x509
        from eaveluxos.tlscert import make_cert
        d = Path(tempfile.mkdtemp())
        try:
            cert = make_cert(d, ["lights.example.lan"], ["192.168.1.20"])
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.load_cert_chain(cert, d / "key.pem")
            san = x509.load_pem_x509_certificate(cert.read_bytes()).extensions.get_extension_for_class(
                x509.SubjectAlternativeName).value
            self.assertIn("lights.example.lan", san.get_values_for_type(x509.DNSName))
            if os.name != "nt":   # Windows uses ACLs, not mode bits (see store._restrict_windows)
                self.assertEqual(oct((d / "key.pem").stat().st_mode & 0o777), "0o600")
            with self.assertRaises(RuntimeError):
                make_cert(d)                                    # won't overwrite without --force
        finally:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
