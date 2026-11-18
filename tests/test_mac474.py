# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""4.7.4: what GitHub's first Mac test run found (4.7.3)."""
import socket
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from eaveluxos import server, tlscert


class MacFixes(unittest.TestCase):
    def setUp(self):
        # Each test starts with no lookup running and nothing found.
        server._name_thread, server._name_ips = None, []
        self.addCleanup(setattr, server, "_name_ips", [])
        self.addCleanup(setattr, server, "_name_thread", None)

    def test_one_lookup_at_a_time_and_a_late_answer_counts(self):
        """Review #1 (4.7.4): tests/repro_name_lookup.py."""
        import subprocess
        import sys
        root = Path(__file__).resolve().parent.parent
        r = subprocess.run([sys.executable, str(root / "tests" / "repro_name_lookup.py")], capture_output=True,
                           text=True, encoding="utf-8", timeout=60, cwd=root)
        self.assertTrue(r.stdout.startswith("OK"), r.stdout + r.stderr)

    def test_a_slow_own_name_lookup_holds_nothing_up(self):
        """Setup, sign-in and Phones and tablets waited for this computer's
        own name to be looked up; on the test Mac that took over 10 s."""
        def slow(*a, **k):
            time.sleep(4)
            return [(socket.AF_INET, 0, 0, "", ("192.168.1.50", 0))]
        with mock.patch.object(server.socket, "getaddrinfo", slow):
            t0 = time.monotonic()
            server._lan_addresses()
            self.assertLess(time.monotonic() - t0, 2.5)

    def test_a_quick_lookup_still_counts(self):
        with mock.patch.object(server.socket, "getaddrinfo", lambda *a, **k: [(socket.AF_INET, 0, 0, "", ("192.168.77.9", 0))]), \
                mock.patch.object(server.socket.socket, "connect", side_effect=OSError):
            self.assertEqual(server._lan_addresses(), ["192.168.77.9"])

    def test_a_long_computer_name_still_gets_a_certificate(self):
        try:
            import cryptography  # noqa: F401
        except ImportError:
            self.skipTest("cryptography isn't installed")
        from cryptography import x509
        long_name = "sat12-bq456-3f1d0c2a-9b7e-4c1d-8a55-2f0e6b1c7d90-runner.local"
        with tempfile.TemporaryDirectory() as d, mock.patch.object(tlscert.socket, "gethostname", return_value=long_name):
            tlscert.make_cert(Path(d))
            cert = x509.load_pem_x509_certificate((Path(d) / "cert.pem").read_bytes())
        names = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName)
        self.assertIn(long_name.split(".")[0], names, "the full name is still one the certificate answers to")


if __name__ == "__main__":
    unittest.main()
