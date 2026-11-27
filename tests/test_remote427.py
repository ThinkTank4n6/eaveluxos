# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""4.27: Away from home with Tailscale."""
import json
import subprocess
import unittest
from unittest import mock

from eaveluxos import remote
from eaveluxos.server import host_allowed

STATUS = json.dumps({"BackendState": "Running", "CertDomains": ["minipc.tail1234.ts.net"],
                     "Self": {"DNSName": "minipc.tail1234.ts.net.", "TailscaleIPs": ["100.101.102.103", "fd7a:115c:a1e0::1"]}})
SERVE = json.dumps({"TCP": {"443": {"HTTPS": True}},
                    "Web": {"minipc.tail1234.ts.net:443": {"Handlers": {"/": {"Proxy": "https+insecure://127.0.0.1:8787"}}}}})


def fake_run(status=STATUS, serve=SERVE, fail=False):
    calls = []

    def run(args, **kw):
        calls.append(args[1:])
        if fail:
            raise subprocess.TimeoutExpired(args, 6)
        out = status if args[1] == "status" else serve
        return subprocess.CompletedProcess(args, 0, out, "")
    return run, calls


class Parse(unittest.TestCase):
    def test_status(self):
        st = remote.parse_status(STATUS)
        self.assertTrue(st["running"])
        self.assertEqual(st["ip"], "100.101.102.103")
        self.assertEqual(st["name"], "minipc.tail1234.ts.net")

    def test_stopped_and_garbage(self):
        self.assertFalse(remote.parse_status(json.dumps({"BackendState": "Stopped", "Self": {}}))["running"])
        self.assertFalse(remote.parse_status("not json")["running"])
        self.assertFalse(remote.parse_status("[1]")["running"])
        bad = remote.parse_status(json.dumps({"BackendState": "Running", "Self": {"DNSName": "evil name<script>", "TailscaleIPs": ["8.8.8.8"]}}))
        self.assertEqual(bad["name"], "")
        self.assertIsNone(bad["ip"])                    # only 100.64.0.0/10 is Tailscale's

    def test_serve_points_here(self):
        self.assertTrue(remote.points_here(remote.serve_targets(SERVE), 8787))
        self.assertFalse(remote.points_here(remote.serve_targets(SERVE), 9000))
        for t in ("http://127.0.0.1:8787", "localhost:8787", "8787", "https+insecure://localhost:8787/"):
            self.assertTrue(remote.points_here([t], 8787), t)
        self.assertFalse(remote.points_here(["http://10.0.0.5:8787"], 8787))
        self.assertEqual(remote.serve_targets("{bad"), [])

    def test_command(self):
        with mock.patch("shutil.which", return_value="/usr/bin/tailscale"):
            self.assertEqual(remote.serve_command(8787, True, "Linux"), "tailscale serve --bg https+insecure://127.0.0.1:8787")
            self.assertEqual(remote.serve_command(8788, False, "Windows"), "tailscale serve --bg http://127.0.0.1:8788")


class Look(unittest.TestCase):
    def setUp(self):
        remote._cache = (0.0, {})

    def test_all_set(self):
        run, calls = fake_run()
        with mock.patch.object(remote, "find_cli", return_value="tailscale"):
            r = remote.look(8787, run=run, fresh=True)
        self.assertTrue(r["installed"] and r["running"] and r["serve"])
        self.assertEqual(remote.known_name(), "minipc.tail1234.ts.net")
        with mock.patch.object(remote, "find_cli", return_value="tailscale"):
            remote.look(8787, run=run)                  # kept for 30 seconds
        self.assertEqual(len(calls), 2)

    def test_not_installed(self):
        with mock.patch.object(remote, "find_cli", return_value=None):
            r = remote.look(8787, fresh=True)
        self.assertFalse(r["installed"])
        self.assertEqual(remote.known_name(), "")

    def test_not_answering(self):
        run, _ = fake_run(fail=True)
        with mock.patch.object(remote, "find_cli", return_value="tailscale"):
            r = remote.look(8787, run=run, fresh=True)
        self.assertFalse(r["running"])
        self.assertIn("didn't answer", r["error"])

    def test_signed_out(self):
        run, calls = fake_run(status=json.dumps({"BackendState": "NeedsLogin", "Self": {}}))
        with mock.patch.object(remote, "find_cli", return_value="tailscale"):
            r = remote.look(8787, run=run, fresh=True)
        self.assertFalse(r["running"])
        self.assertIn("sign in", r["error"])
        self.assertEqual(len(calls), 1)                 # serve isn't asked about


class HostName(unittest.TestCase):
    def test_tailscale_name_allowed_only_when_it_is_this_computer(self):
        self.assertFalse(host_allowed("minipc.tail1234.ts.net", []))
        self.assertTrue(host_allowed("minipc.tail1234.ts.net", ["minipc.tail1234.ts.net"]))
        self.assertFalse(host_allowed("evil.ts.net", ["", "minipc.tail1234.ts.net"]))

    def test_admin_only(self):
        import eaveluxos.server as srv
        self.assertIn("/api/remote", srv.ADMIN_GETS)


if __name__ == "__main__":
    unittest.main()


try:
    from playwright.sync_api import sync_playwright
except ImportError:                       # pragma: no cover
    sync_playwright = None
from tests.test_local43 import ServerBase  # noqa: E402


@unittest.skipUnless(sync_playwright, "playwright not installed")
class Browser(ServerBase):
    def _page(self, width=390):
        import threading
        from eaveluxos.server import make_server
        srv = make_server(self.app, "127.0.0.1", 0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        try:
            pw = sync_playwright().start()
            br = pw.chromium.launch()
        except Exception as e:
            self.skipTest(f"Chromium can't start: {e}")
        self.addCleanup(pw.stop)
        self.addCleanup(br.close)
        pg = br.new_page(viewport={"width": width, "height": 900})
        self.errs = []
        pg.on("pageerror", lambda e: self.errs.append(str(e)))
        return pg, srv.server_address[1]

    def test_tailscale_steps_and_address(self):
        remote._cache = (0.0, {})
        orig = remote.look
        box = {}
        with mock.patch.object(remote, "find_cli", return_value="tailscale"), \
                mock.patch.object(remote, "look", side_effect=lambda port, run_=None, system=None, fresh=False:
                                  orig(port, run=fake_run(serve=SERVE.replace("8787", str(port)))[0], fresh=True)):
            pg, port = self._page()
            pg.goto(f"http://localhost:{port}/#access")
            pg.wait_for_selector("#tsbox .qr svg", timeout=20000)
            text = pg.inner_text("#tsbox")
            self.assertIn("Connected as minipc.tail1234.ts.net", text)
            self.assertIn("https://minipc.tail1234.ts.net", text)
            self.assertLessEqual(pg.evaluate("document.documentElement.scrollWidth"), 390)
            self.assertEqual(self.errs, [])

    def test_not_installed_shows_the_command(self):
        remote._cache = (0.0, {})
        with mock.patch.object(remote, "find_cli", return_value=None):
            pg, port = self._page()
            pg.goto(f"http://localhost:{port}/#access")
            pg.wait_for_selector("#tscmd", timeout=20000)
            self.assertIn("serve --bg http://127.0.0.1:", pg.inner_text("#tscmd"))
            self.assertIn("tailscale.com/download", pg.inner_text("#tsbox"))
            self.assertEqual(self.errs, [])

    def test_alert_history_listed(self):
        self.app.alerts.send_raw = lambda *a: None
        self.app.alerts.test()
        pg, port = self._page()
        pg.goto(f"http://localhost:{port}/#alerts")
        pg.click("[data-fold=phone] .foldbar", timeout=20000)
        pg.wait_for_selector("#alhist", state="attached", timeout=20000)
        pg.click("#alhist summary")
        self.assertIn(": test", pg.inner_text("#alhist"))
        self.assertIn("EaveLuxOS was off", pg.inner_text("[data-alev='down'] >> xpath=.."))
        self.assertEqual(self.errs, [])
