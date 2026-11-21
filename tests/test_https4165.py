# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""4.16.5: with HTTPS on, http:// addresses are sent on to https://, and
the app opens its https:// address."""
import shutil
import socket
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent


class Redirect(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from eaveluxos.tlscert import make_cert
        except ImportError:
            raise unittest.SkipTest("no cryptography")
        from eaveluxos.server import App, make_server
        cls.d = Path(tempfile.mkdtemp())
        (cls.d / "data" / "tls").mkdir(parents=True)
        try:
            make_cert(cls.d / "data" / "tls")
        except RuntimeError:
            raise unittest.SkipTest("no cryptography")
        cls.app = App(cls.d)
        cls.srv = make_server(cls.app, "127.0.0.1", 0)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown(); cls.srv.server_close(); cls.app.store.close()
        shutil.rmtree(cls.d, ignore_errors=True)

    def ask(self, raw: bytes) -> str:
        s = socket.create_connection(("127.0.0.1", self.port), timeout=10)
        s.sendall(raw)
        got = b""
        try:
            while chunk := s.recv(4096):
                got += chunk
        except OSError:
            pass
        s.close()
        return got.decode("latin-1")

    def location(self, raw: bytes) -> str:
        r = self.ask(raw)
        self.assertTrue(r.startswith("HTTP/1.1 307"), r[:80])
        return next(l.split(": ", 1)[1] for l in r.split("\r\n") if l.lower().startswith("location:"))

    def test_the_address_and_path_carry_over(self):
        p = self.port
        self.assertEqual(self.location(b"GET /#app HTTP/1.1\r\nHost: localhost:%d\r\n\r\n" % p), f"https://localhost:{p}/#app")
        self.assertEqual(self.location(b"GET /api/session?x=1 HTTP/1.1\r\nHost: 10.168.168.155:%d\r\n\r\n" % p),
                         f"https://10.168.168.155:{p}/api/session?x=1")
        self.assertEqual(self.location(b"GET / HTTP/1.1\r\nHost: [::1]:%d\r\n\r\n" % p), f"https://[::1]:{p}/")

    def test_odd_requests_go_to_localhost(self):
        p = self.port
        self.assertEqual(self.location(b"GET / HTTP/1.1\r\nHost: evil.com/x\r\n\r\n"), f"https://localhost:{p}/")
        self.assertEqual(self.location(b"GET //evil.com/ HTTP/1.1\r\nHost: localhost\r\n\r\n"), f"https://localhost:{p}/")
        self.assertEqual(self.location(b"GET / HTTP/1.1\r\n\r\n"), f"https://localhost:{p}/")
        self.assertNotIn("\r\nX:", self.ask(b"GET /a%0d%0aX:1 HTTP/1.1\r\nHost: localhost\r\n\r\n"))

    def test_https_still_works(self):
        import json
        import ssl
        import urllib.request
        ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(f"https://127.0.0.1:{self.port}/api/session", context=ctx, timeout=5) as r:
            self.assertIn("version", json.loads(r.read()))
        from eaveluxos.server import probe_app
        self.assertTrue(probe_app(self.port))


class OpensHttps(unittest.TestCase):
    def test_local_url_follows_the_certificate(self):
        sys.path.insert(0, str(ROOT))
        self.addCleanup(sys.path.remove, str(ROOT))
        import main
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d, True)
        with mock.patch.object(main, "data_dir", return_value=d):
            self.assertEqual(main.local_url(8787), "http://localhost:8787/")
            (d / "tls").mkdir()
            (d / "tls" / "cert.pem").write_text("x")
            self.assertEqual(main.local_url(8787), "http://localhost:8787/", "a certificate without its key isn't used")
            (d / "tls" / "key.pem").write_text("x")
            self.assertEqual(main.local_url(8787), "https://localhost:8787/")
        self.assertNotIn('"http://localhost', (ROOT / "main.py").read_text(encoding="utf-8"))


class Review(unittest.TestCase):
    def test_1_http_goes_on_to_https(self):
        from tests import reprorun
        reprorun.run(self, "repro_http_to_https.py", 60)


if __name__ == "__main__":
    unittest.main()
