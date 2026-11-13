# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""A phone can't open the app: the address list, and the Windows Firewall
check and fix (Settings › Phones and other computers)."""
import base64
import json
import shutil
import socket
import subprocess
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

from eaveluxos import server, winfirewall
from eaveluxos.server import App, make_server


def decoded(cmd):
    """The PowerShell script inside an -EncodedCommand argument list."""
    return base64.b64decode(cmd[cmd.index("-EncodedCommand") + 1]).decode("utf-16-le")


class FirewallScriptTests(unittest.TestCase):
    def test_check_reads_enum_names_only(self):
        s = winfirewall.check_script(8787, r"C:\Program Files\EaveLuxOS\EaveLuxOS.exe")
        self.assertIn("Get-NetConnectionProfile", s)
        self.assertIn(r"-Program 'C:\Program Files\EaveLuxOS\EaveLuxOS.exe'", s)
        self.assertIn("'EaveLuxOS (port 8787)'", s)

    def test_a_quote_in_the_path_cant_break_out(self):
        s = winfirewall.allow_script(8787, r"C:\Users\O'Brien\EaveLuxOS.exe")
        self.assertIn(r"'C:\Users\O''Brien\EaveLuxOS.exe'", s)

    def test_allow_only_private_and_domain_networks(self):
        s = winfirewall.allow_script(9001, "x.exe")
        self.assertIn("-LocalPort 9001 -Profile Private,Domain", s)
        self.assertIn("Disable-NetFirewallRule", s)      # block rules for this program are switched off,
        self.assertNotIn("Remove-NetFirewallApplicationFilter", s)   # not deleted
        self.assertIn("'EaveLuxOS (port*'", s)           # an old rule for a previous port is replaced
        self.assertNotIn("Set-NetConnectionProfile", s)  # never turns a Public network Private

    def test_parse(self):
        r = winfirewall.parse_check("CATEGORY=Public,Private\r\nBLOCKED=EaveLuxOS.exe|EaveLuxOS.exe\r\nALLOWED=False\r\n")
        self.assertEqual(r, {"networks": ["Public", "Private"], "public": True,
                             "blocked_rules": ["EaveLuxOS.exe", "EaveLuxOS.exe"], "allowed": False})
        r = winfirewall.parse_check("CATEGORY=Private\nBLOCKED=\nALLOWED=True\n")
        self.assertEqual((r["public"], r["blocked_rules"], r["allowed"]), (False, [], True))


class FirewallRunTests(unittest.TestCase):
    def run_with(self, *results):
        calls, results = [], list(results)

        def run(cmd, **kw):
            calls.append(cmd)
            rc, out = results.pop(0)
            return subprocess.CompletedProcess(cmd, rc, out, "")
        return calls, run

    def test_check(self):
        calls, run = self.run_with((0, "CATEGORY=Private\nBLOCKED=\nALLOWED=True\n"))
        r = winfirewall.check(8787, run=run)
        self.assertTrue(r["allowed"])
        self.assertIn("Get-NetFirewallRule", decoded(calls[0]))

    def test_allow_asks_windows_then_checks_again(self):
        calls, run = self.run_with((0, ""), (0, "CATEGORY=Private\nBLOCKED=\nALLOWED=True\n"))
        r = winfirewall.allow(8787, run=run)
        self.assertEqual((r["ok"], r["allowed"]), (True, True))
        outer = decoded(calls[0])
        self.assertIn("-Verb RunAs", outer)                # one permission prompt
        inner_b64 = outer.split("'-EncodedCommand','")[1].split("'")[0]
        self.assertIn("New-NetFirewallRule", base64.b64decode(inner_b64).decode("utf-16-le"))

    def test_permission_declined(self):
        calls, run = self.run_with((1223, "DECLINED\n"))
        r = winfirewall.allow(8787, run=run)
        self.assertFalse(r["ok"])
        self.assertIn("wasn't given", r["error"])

    def test_powershell_missing(self):
        def run(cmd, **kw):
            raise FileNotFoundError("powershell")
        self.assertIn("error", winfirewall.check(8787, run=run))
        self.assertFalse(winfirewall.allow(8787, run=run)["ok"])


class AddressTests(unittest.TestCase):
    def test_home_network_address_first_and_loopback_left_out(self):
        class Sock:
            def __init__(self, *a):
                self.ip = None

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def connect(self, addr):
                self.ip = {"8.8.8.8": "10.168.168.155"}.get(addr[0], "172.27.80.1")

            def getsockname(self):
                return (self.ip, 0)
        server._lan_cache = (0.0, [])                          # no answer kept from an earlier test
        self.addCleanup(setattr, server, "_lan_cache", (0.0, []))   # nor these fake ones for later tests
        with mock.patch.object(server.socket, "socket", Sock), \
                mock.patch.object(server.socket, "getaddrinfo", return_value=[
                    (socket.AF_INET, 0, 0, "", ("127.0.0.1", 0)), (socket.AF_INET, 0, 0, "", ("169.254.3.4", 0)),
                    (socket.AF_INET, 0, 0, "", ("192.168.56.1", 0))]):
            self.assertEqual(server.lan_addresses(), ["10.168.168.155", "172.27.80.1", "192.168.56.1"])


class EndpointTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.app = App(self.dir, start=False)
        self.app.store.save_user(None, "owner", "admin", password="password-xxxx")
        self.srv = make_server(self.app, "127.0.0.1", 0)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.app.store.close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def call(self, path, body=None, hdr=None):
        r = urllib.request.Request(f"http://127.0.0.1:{self.srv.server_address[1]}{path}",
                                   data=None if body is None else json.dumps(body).encode(),
                                   headers={"Content-Type": "application/json", "X-Requested-With": "eaveluxos", **(hdr or {})})
        try:
            with urllib.request.urlopen(r, timeout=20) as x:
                return x.status, json.loads(x.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def phone(self):
        h = {"X-Forwarded-For": "203.0.113.7"}
        st, r = self.call("/api/login", {"username": "owner", "password": "password-xxxx"}, h)
        self.assertEqual(st, 200, r)
        return {**h, "X-Session": r["token"]}

    def test_check_on_windows(self):
        res = {"networks": ["Public"], "public": True, "blocked_rules": [], "allowed": False}
        with mock.patch.object(server.platform, "system", return_value="Windows"), \
                mock.patch.object(winfirewall, "check", return_value=res) as chk:
            st, r = self.call("/api/lan_check")
        self.assertEqual(st, 200, r)
        self.assertEqual(r["windows"], res)
        self.assertEqual(chk.call_args[0][0], self.srv.server_address[1])

    def test_check_elsewhere_has_no_windows_part(self):
        with mock.patch.object(server.platform, "system", return_value="Linux"):
            st, r = self.call("/api/lan_check")
        self.assertEqual(st, 200)
        self.assertNotIn("windows", r)

    def test_only_on_the_app_computer(self):
        h = self.phone()
        with mock.patch.object(winfirewall, "allow") as allow:
            self.assertEqual(self.call("/api/lan_check", hdr=h)[0], 403)
            self.assertEqual(self.call("/api/lan_allow", {}, hdr=h)[0], 403)
        allow.assert_not_called()

    def test_allow_reports_a_refusal(self):
        with mock.patch.object(server.platform, "system", return_value="Windows"), \
                mock.patch.object(winfirewall, "allow", return_value={"ok": False, "error": "Windows asked for permission and it wasn't given, so nothing changed."}):
            st, r = self.call("/api/lan_allow", {})
        self.assertEqual(st, 400)
        self.assertIn("wasn't given", r["error"])

    def test_allow_is_windows_only(self):
        with mock.patch.object(server.platform, "system", return_value="Darwin"), mock.patch.object(winfirewall, "allow") as allow:
            st, r = self.call("/api/lan_allow", {})
        self.assertEqual(st, 400)
        allow.assert_not_called()


if __name__ == "__main__":
    unittest.main()
