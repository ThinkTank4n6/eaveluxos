# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""4.18.2: Set up this phone (the root certificate for phones, over plain
http too), arrive/leave settling, who's home on Home, birthdays with
several patterns, and automations in groups."""
import copy
import datetime as dt
import json
import shutil
import socket
import ssl
import tempfile
import threading
import time
import unittest
import unittest.mock
import urllib.error
import urllib.request
from pathlib import Path

from eaveluxos.presence import Presence, settle_minutes
from eaveluxos.schedule import ConfigError
from tests.test_local43 import ServerBase

ROOT = Path(__file__).resolve().parent.parent
TOKEN = "t" * 32

try:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
except ImportError:            # pragma: no cover
    x509 = None


def make_ca(tls: Path, other_root=False):
    """An mkcert-like root and a certificate for 127.0.0.1 signed by it
    (or by another root, other_root). Returns the root's PEM."""
    def name(cn):
        return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    now = dt.datetime.now(dt.timezone.utc)

    def root(cn):
        k = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        c = (x509.CertificateBuilder().subject_name(name(cn)).issuer_name(name(cn)).public_key(k.public_key())
             .serial_number(x509.random_serial_number()).not_valid_before(now - dt.timedelta(days=1))
             .not_valid_after(now + dt.timedelta(days=30)).add_extension(x509.BasicConstraints(ca=True, path_length=None), True)
             .add_extension(x509.SubjectKeyIdentifier.from_public_key(k.public_key()), False)
             .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False, key_encipherment=False, data_encipherment=False,
                                          key_agreement=False, key_cert_sign=True, crl_sign=True, encipher_only=False, decipher_only=False), True)
             .sign(k, hashes.SHA256()))
        return k, c
    rk, rc = root("mkcert test root")
    sk, sc = root("another root") if other_root else (rk, rc)
    lk = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    import ipaddress
    leaf = (x509.CertificateBuilder().subject_name(name("127.0.0.1")).issuer_name(sc.subject).public_key(lk.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - dt.timedelta(days=1))
            .not_valid_after(now + dt.timedelta(days=30))
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(sk.public_key()), False)
            .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1")), x509.DNSName("localhost")]), False)
            .sign(sk, hashes.SHA256()))
    tls.mkdir(parents=True, exist_ok=True)
    (tls / "cert.pem").write_bytes(leaf.public_bytes(serialization.Encoding.PEM))
    (tls / "key.pem").write_bytes(lk.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
                                                   serialization.NoEncryption()))
    pem = rc.public_bytes(serialization.Encoding.PEM)
    (tls / "rootCA.pem").write_bytes(pem)
    return pem


class Settling(unittest.TestCase):
    def test_a_quick_change_back_is_only_noted(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        clock = [1000.0]
        p, ppl = Presence(d, now=lambda: clock[0]), ["Chris"]
        self.assertFalse(p.set(ppl, "Chris", "home", 120)["settling"], "the first report counts")
        clock[0] += 30
        r = p.set(ppl, "Chris", "away", 120)
        self.assertTrue(r["changed"] and r["settling"])
        self.assertEqual(p.home(ppl), set(), "but who's home stays right")
        clock[0] += 30
        self.assertTrue(p.set(ppl, "Chris", "home", 120)["settling"], "still bouncing")
        clock[0] += 200
        self.assertFalse(p.set(ppl, "Chris", "away", 120)["settling"], "settled: counts again")
        self.assertFalse(p.set(ppl, "Chris", "home", 0)["settling"], "0: never ignored")

    def test_the_setting(self):
        self.assertEqual(settle_minutes(None), 2)
        self.assertEqual(settle_minutes({"settle_minutes": 0}), 0)
        for bad in (-1, 31, "2", True):
            with self.assertRaises(ConfigError):
                settle_minutes({"settle_minutes": bad})


class Server(ServerBase):
    def settings(self, **kw):
        s = copy.deepcopy(self.app.store.settings)
        s.update(kw)
        self.app.save_settings(s)

    def test_a_bouncing_phone_starts_no_automations(self):
        self.settings(presence={"people": ["Chris"], "settle_minutes": 2},
                      automations=[{"id": "w", "name": "Welcome", "when": {"type": "arrive", "person": "any"}, "if": [],
                                    "then": [{"type": "flash", "color": "#00FF00", "seconds": 10}], "cooldown": 0}])
        self.assertTrue(self.app.presence_set("Chris", "home", "webhook")["automations"])
        self.app.presence_set("Chris", "away", "webhook")
        r = self.app.presence_set("Chris", "home", "webhook")
        self.assertTrue(r["settling"])
        self.assertEqual(r["automations"], [])
        self.assertTrue(any("again within 2 min" in e["msg"] for e in list(self.app.ctrl.events)))
        self.app.presence_set("Chris", "away", "set by hand")
        r = self.app.presence_set("Chris", "home", "set by hand")
        self.assertFalse(r["settling"], "marking by hand is never ignored")
        self.assertTrue(r["automations"])

    @unittest.skipIf(x509 is None, "cryptography isn't installed")
    def test_the_root_certificate_is_found_and_checked(self):
        tls = self.app.store.dir / "tls"
        pem = make_ca(tls)
        ca = self.app.phone_ca()
        self.assertEqual(ca["pem"], pem)
        self.assertEqual(len(ca["sha256"]), 64)
        info = self.app.phone_info(8787)
        self.assertTrue(info["ca"])
        self.assertEqual(info["ca_sha256"].count(":"), 31)
        (tls / "rootCA.pem").write_bytes(pem + b"-----BEGIN PRIVATE KEY-----\nAAAA\n-----END PRIVATE KEY-----\n")
        self.assertIsNone(self.app.phone_ca(), "never a file with a key in it")
        shutil.rmtree(tls)
        make_ca(tls, other_root=True)
        with unittest.mock.patch.dict("os.environ", {"CAROOT": str(self.app.store.dir / "nowhere"), "LOCALAPPDATA": str(self.app.store.dir / "x"),
                                                     "XDG_DATA_HOME": str(self.app.store.dir / "y")}), \
                unittest.mock.patch.object(Path, "home", return_value=self.app.store.dir / "z"):
            self.assertIsNone(self.app.phone_ca(), "a root that didn't sign this app's certificate is no use to a phone")


@unittest.skipIf(x509 is None, "cryptography isn't installed")
class OverPlainHttp(unittest.TestCase):
    """With HTTPS on, /trust and /ca.crt answer over plain http (a phone
    needs them before it trusts the certificate); everything else is still
    sent on to https://."""

    def setUp(self):
        from eaveluxos.server import App, make_server
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.app = App(self.dir, start=False)
        self.pem = make_ca(self.app.store.dir / "tls")
        self.addCleanup(self.app.store.close)
        self.srv = make_server(self.app, "127.0.0.1", 0)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)
        self.port = self.srv.server_address[1]

    def plain(self, path):
        s = socket.create_connection(("127.0.0.1", self.port), timeout=10)
        s.sendall(f"GET {path} HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\n\r\n".encode())
        out = b""
        while True:
            c = s.recv(65536)
            if not c:
                break
            out += c
        s.close()
        head, _, body = out.partition(b"\r\n\r\n")
        return head.decode("latin-1"), body

    def test_paths(self):
        head, body = self.plain("/ca.crt")
        self.assertIn("200 OK", head.split("\r\n")[0])
        self.assertIn("application/x-x509-ca-cert", head)
        self.assertEqual(body, self.pem)
        head, body = self.plain("/trust")
        self.assertIn("200 OK", head.split("\r\n")[0])
        self.assertIn(b'href="/ca.crt"', body)
        self.assertIn(f"https://127.0.0.1:{self.port}/#phone".encode(), body)
        self.assertNotIn(b"<script", body)
        head, _ = self.plain("/api/settings")
        self.assertIn("307", head.split("\r\n")[0], "anything else still goes to https://")
        head, _ = self.plain("/")
        self.assertIn("307", head.split("\r\n")[0])

    def test_over_https_too(self):
        ctx = ssl.create_default_context(cafile=str(self.app.store.dir / "tls" / "rootCA.pem"))
        with urllib.request.urlopen(f"https://127.0.0.1:{self.port}/ca.crt", context=ctx, timeout=10) as r:
            self.assertEqual(r.read(), self.pem)


class Review(unittest.TestCase):
    def test_1_a_download_is_never_kept_as_the_apps_page(self):
        from tests import reprorun
        reprorun.run(self, "repro_sw_keeps_download.py", 60)

    def test_2_home_asks_who_is_home_at_most_every_20_seconds(self):
        js = (ROOT / "eaveluxos" / "static" / "triggers.js").read_text(encoding="utf-8")
        self.assertIn("Date.now() - S.presenceSeen.at < 20000", js)


class Sources(unittest.TestCase):
    def test_the_service_worker_never_keeps_a_download_as_the_page(self):
        sw = (ROOT / "eaveluxos" / "static" / "sw.js").read_text(encoding="utf-8")
        self.assertIn("url.pathname === '/ca.crt'", sw)
        self.assertIn("startsWith('text/html')", sw)

    def test_phone_has_its_tab(self):
        self.assertIn("phone: 'setup'", (ROOT / "eaveluxos" / "static" / "nav.js").read_text(encoding="utf-8"))


try:
    from playwright.sync_api import sync_playwright
except ImportError:            # pragma: no cover
    sync_playwright = None


@unittest.skipIf(sync_playwright is None, "Playwright isn't installed")
class Browser(ServerBase):
    SHOTS = None

    def test_screens(self):
        from eaveluxos.server import make_server
        self.app.store.save_secrets(webhook_token=TOKEN)
        s = copy.deepcopy(self.app.store.settings)
        effs = list(s["effects"])
        today = dt.date.today()
        s["presence"] = {"people": ["Chris", "Ann"]}
        s["dates"] = {"list": [{"name": "Chris", "date": today.strftime("%m-%d"), "effects": [effs[0]]}]}
        s["automations"] = [{"id": f"a{i}", "name": f"Doorbell {i}", "when": {"type": "webhook", "name": f"door{i}"}, "if": [],
                             "then": [{"type": "flash", "color": "#0000FF", "seconds": 10}]} for i in range(6)] + [
            {"id": "w", "name": "Welcome", "when": {"type": "arrive", "person": "any"}, "if": [],
             "then": [{"type": "flash", "color": "#00FF00", "seconds": 10}]}]
        self.app.save_settings(s)
        self.app.presence_set("Chris", "home")
        srv = make_server(self.app, "127.0.0.1", 0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        base = f"http://localhost:{srv.server_address[1]}/"
        try:
            pw = sync_playwright().start()
            br = pw.chromium.launch()
        except Exception as e:
            self.skipTest(f"Chromium can't start: {e}")
        self.addCleanup(pw.stop)
        self.addCleanup(br.close)
        errors = []

        def until(cond, what):
            for _ in range(200):
                if cond():
                    return
                time.sleep(0.05)
            self.fail(f"never: {what}")

        def unfold(pg, key):
            pg.wait_for_selector(f'[data-fold="{key}"]')
            if "closed" in (pg.get_attribute(f'[data-fold="{key}"]', "class") or ""):
                pg.click(f'[data-fold="{key}"] .foldbar')
        pg = br.new_page(viewport={"width": 1300, "height": 900})
        pg.on("pageerror", lambda e: errors.append(str(e)))
        # Home: who's home
        pg.goto(base + "#home")
        pg.wait_for_selector("#homewho:not([hidden])")
        txt = pg.inner_text("#homewho")
        self.assertIn("Chris", txt)
        self.assertIn("not known yet: Ann", txt)
        # Automations in groups
        pg.goto(base + "#alerts")
        unfold(pg, "autos")
        pg.wait_for_selector("h3.autogroup")
        groups = pg.eval_on_selector_all("h3.autogroup", "els => els.map(e => e.textContent)")
        self.assertTrue(groups[0].startswith("People"), groups)
        self.assertTrue(any(g.startswith("Cameras") for g in groups), groups)
        # Birthdays: tonight's badge, several patterns
        pg.goto(base + "#schedule")
        unfold(pg, "dates")
        pg.wait_for_selector("#datebox .badge.hi")
        self.assertIn("Today", pg.inner_text("#datebox"))
        pg.click('[data-dtedit="0"]')
        pg.wait_for_selector("#dlg #dtadd")
        pg.select_option("#dlg #dtadd", effs[1])
        pg.wait_for_selector("#dlg #dtrot")
        pg.fill("#dlg #dtrot", "20")
        pg.click('#dlg [data-dtup="1"]')
        pg.locator("#dlg .primary").last.click()
        until(lambda: self.app.store.settings["dates"]["list"][0]["effects"] == [effs[1], effs[0]], "two patterns, in the new order")
        self.assertEqual(self.app.store.settings["dates"]["list"][0]["rotate"], 20)
        # Set up a phone, on the computer: the code to scan
        pg.goto(base + "#phone")
        pg.wait_for_selector(".qrbox svg")
        if self.SHOTS:
            pg.screenshot(path=f"{self.SHOTS}/phone-computer.png", full_page=True)
        # ... and on a phone: the three steps
        ph = br.new_context(**pw.devices["iPhone 13"]).new_page()
        ph.on("pageerror", lambda e: errors.append(str(e)))
        ph.goto(f"http://127.0.0.1:{srv.server_address[1]}/#phone")
        if ph.query_selector("#user") or ph.query_selector('input[type="password"]'):
            self.skipTest("this test's phone would have to sign in")
        ph.wait_for_selector("#phme")
        body = ph.inner_text("#main")
        for want in ("Trust the app’s certificate", "Put EaveLuxOS on the home screen", "Who’s home"):
            self.assertIn(want, body)
        self.assertEqual(ph.evaluate("document.documentElement.scrollWidth"), ph.viewport_size["width"], "fits the phone")
        ph.select_option("#phme", "Ann")
        ph.click('[data-phset="home"]')
        until(lambda: "Ann" in self.app.presence.home(["Chris", "Ann"]), "Ann marked home from her phone")
        if self.SHOTS:
            ph.screenshot(path=f"{self.SHOTS}/phone-iphone.png", full_page=True)
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
