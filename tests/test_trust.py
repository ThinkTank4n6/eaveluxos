# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""HTTPS trust for Trimlight's cloud. On a Mac the app's own OpenSSL can't find
the system's certificate authorities, which failed setup with
CERTIFICATE_VERIFY_FAILED ("unable to get local issuer certificate")."""
import datetime
import http.server
import json
import os
import shutil
import ssl
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from eaveluxos import trust

try:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
    HAVE_CRYPTO = True
except ImportError:
    HAVE_CRYPTO = False


def make_ca_and_server(d: Path):
    """A private certificate authority and a server certificate it signed."""
    now = datetime.datetime.now(datetime.timezone.utc)
    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "EaveLuxOS Test Root")])
    ca = (x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name).public_key(ca_key.public_key())
          .serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(days=1))
          .not_valid_after(now + datetime.timedelta(days=30))
          .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
          .add_extension(x509.KeyUsage(digital_signature=True, key_cert_sign=True, crl_sign=True, content_commitment=False,
                                       key_encipherment=False, data_encipherment=False, key_agreement=False,
                                       encipher_only=False, decipher_only=False), critical=True)
          .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
          .sign(ca_key, hashes.SHA256()))
    key = ec.generate_private_key(ec.SECP256R1())
    import ipaddress
    cert = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "127.0.0.1")]))
            .issuer_name(ca_name).public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1)).not_valid_after(now + datetime.timedelta(days=30))
            .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
            .add_extension(x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .sign(ca_key, hashes.SHA256()))
    pem = serialization.Encoding.PEM
    (d / "ca.pem").write_bytes(ca.public_bytes(pem))
    (d / "srv.pem").write_bytes(cert.public_bytes(pem))
    (d / "srv.key").write_bytes(key.private_bytes(pem, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    return d / "ca.pem", d / "srv.pem", d / "srv.key"


class _Cloud(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _reply(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        if n:
            self.rfile.read(n)
        body = {"code": 0, "desc": "ok", "payload": {"data": [{"deviceId": "D1", "name": "House"}]}}
        if self.server.refuse_keys:
            body = {"code": 10002, "desc": "auth failed"}
        b = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)
    do_GET = do_POST = _reply


@unittest.skipUnless(HAVE_CRYPTO, "cryptography not installed")
class MacTrustTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = Path(tempfile.mkdtemp())
        cls.ca, cert, key = make_ca_and_server(cls.dir)
        cls.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Cloud)
        cls.srv.refuse_keys = False
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(cert, key)
        cls.srv.socket = ctx.wrap_socket(cls.srv.socket, server_side=True)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.url = f"https://127.0.0.1:{cls.srv.server_address[1]}/trimlight"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        shutil.rmtree(cls.dir, ignore_errors=True)

    def setUp(self):
        trust.client_context.cache_clear()
        self.srv.refuse_keys = False
        # Like the Mac app: OpenSSL's own system list is empty.
        self.env = mock.patch.dict(os.environ, {"SSL_CERT_FILE": str(self.dir / "none.pem"),
                                                "SSL_CERT_DIR": str(self.dir / "none")})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        trust.client_context.cache_clear()

    def devices(self):
        from eaveluxos.api import TrimlightAPI
        return TrimlightAPI("id", "secret", base_url=self.url).list_devices()

    def test_without_a_usable_list_it_fails_and_says_why(self):
        from eaveluxos.api import TrimlightError
        with mock.patch.object(trust, "_extra_bundles", return_value=[]):
            with self.assertRaises(TrimlightError) as cm:
                self.devices()
        self.assertEqual(cm.exception.kind, "network")
        self.assertIn("isn't a problem with your keys", str(cm.exception))
        self.assertIn("CERTIFICATE_VERIFY_FAILED", str(cm.exception))

    def test_bundled_list_fixes_it(self):
        with mock.patch.object(trust, "_extra_bundles", return_value=[str(self.ca)]):
            self.assertEqual(self.devices(), [{"deviceId": "D1", "name": "House"}])

    def test_a_damaged_extra_list_does_not_break_the_others(self):
        bad = self.dir / "bad.pem"
        bad.write_text("not a certificate")
        with mock.patch.object(trust, "_extra_bundles", return_value=[str(bad), str(self.ca)]):
            self.assertEqual(len(self.devices()), 1)

    def test_setup_blames_the_connection_not_the_keys(self):
        from eaveluxos.server import App, make_server
        import eaveluxos.api
        import urllib.request
        d = Path(tempfile.mkdtemp())
        app = App(d, start=False)
        srv = make_server(app, "127.0.0.1", 0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()

        def setup(cid="id", sec="secret"):
            r = urllib.request.Request(f"http://127.0.0.1:{srv.server_address[1]}/api/credentials",
                                       data=json.dumps({"client_id": cid, "client_secret": sec}).encode(),
                                       headers={"Content-Type": "application/json", "X-Requested-With": "eaveluxos"})
            try:
                with urllib.request.urlopen(r, timeout=30) as x:
                    return x.status, json.loads(x.read())
            except urllib.error.HTTPError as e:
                return e.code, json.loads(e.read())
        try:
            with mock.patch.object(eaveluxos.api, "BASE_URL", self.url):
                with mock.patch.object(trust, "_extra_bundles", return_value=[]):
                    st, r = setup()
                self.assertEqual(st, 502)
                self.assertTrue(r["error"].startswith("Couldn't check these with Trimlight."), r)
                self.assertNotIn("didn't accept", r["error"])
                trust.client_context.cache_clear()
                self.srv.refuse_keys = True
                with mock.patch.object(trust, "_extra_bundles", return_value=[str(self.ca)]):
                    st, r = setup()
                self.assertEqual(st, 400)
                self.assertIn("Trimlight didn't accept these", r["error"])
        finally:
            srv.shutdown()
            srv.server_close()
            app.store.close()
            shutil.rmtree(d, ignore_errors=True)


class TrustContextTests(unittest.TestCase):
    def setUp(self):
        trust.client_context.cache_clear()

    def tearDown(self):
        trust.client_context.cache_clear()

    def test_checks_stay_on(self):
        ctx = trust.client_context()
        self.assertEqual(ctx.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(ctx.check_hostname)

    def test_mac_also_uses_the_list_macos_ships(self):
        with mock.patch.object(trust.platform, "system", return_value="Darwin"), \
                mock.patch.object(trust.os.path, "exists", side_effect=lambda p: p == trust.MAC_SYSTEM_BUNDLE):
            self.assertIn(trust.MAC_SYSTEM_BUNDLE, trust._extra_bundles())
        with mock.patch.object(trust.platform, "system", return_value="Windows"):
            self.assertNotIn(trust.MAC_SYSTEM_BUNDLE, trust._extra_bundles())

    def test_certifi_used_when_installed(self):
        try:
            import certifi
        except ImportError:
            self.skipTest("certifi not installed")
        self.assertIn(certifi.where(), trust._extra_bundles())


if __name__ == "__main__":
    unittest.main()
