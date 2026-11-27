# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""4.22.2: Start EaveLuxOS from the page on the app computer (the desktop
icon the browser made, a bookmark, or after Quit): eaveluxos://start."""
import importlib.util
import plistlib
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from eaveluxos import launchlink
from tests.test_local43 import ServerBase

HERE = Path(__file__).resolve().parent


class FakeWinreg:
    HKEY_CURRENT_USER, REG_SZ = "HKCU", 1

    def __init__(self):
        self.keys = {}
        self.writes = 0

    class _K:
        def __init__(self, reg, path):
            self.reg, self.path = reg, path

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def OpenKey(self, root, path):
        if path not in self.keys:
            raise OSError("no key")
        return self._K(self, path)

    def CreateKey(self, root, path):
        self.keys.setdefault(path, {})
        return self._K(self, path)

    def QueryValueEx(self, k, name):
        if name not in self.keys[k.path]:
            raise OSError("no value")
        return self.keys[k.path][name], self.REG_SZ

    def SetValueEx(self, k, name, _, kind, value):
        self.writes += 1
        self.keys[k.path][name] = value


class Register(unittest.TestCase):
    def test_command_never_opens_another_tab(self):
        with mock.patch.object(sys, "frozen", True, create=True), mock.patch.object(sys, "executable", r"C:\Apps\EaveLuxOS\EaveLuxOS.exe"):
            self.assertEqual(launchlink.command(Path(r"C:\Apps\EaveLuxOS")), [r"C:\Apps\EaveLuxOS\EaveLuxOS.exe", "run"])

    def test_1_windows_for_this_user_only(self):
        reg = FakeWinreg()
        with mock.patch.object(sys, "frozen", True, create=True), mock.patch.object(sys, "executable", r"C:\Apps\EaveLuxOS\EaveLuxOS.exe"):
            self.assertTrue(launchlink.register(Path(r"C:\Apps\EaveLuxOS"), "Windows", winreg=reg))
            cmd = reg.keys[r"Software\Classes\eaveluxos\shell\open\command"][""]
            self.assertEqual(cmd, r'"C:\Apps\EaveLuxOS\EaveLuxOS.exe" "run"')
            self.assertNotIn("%1", cmd, "nothing from the link reaches the program")
            self.assertEqual(reg.keys[r"Software\Classes\eaveluxos"]["URL Protocol"], "")
            n = reg.writes
            launchlink.register(Path(r"C:\Apps\EaveLuxOS"), "Windows", winreg=reg)
            self.assertEqual(reg.writes, n, "nothing written when it's already right")
        with mock.patch.object(sys, "frozen", True, create=True), mock.patch.object(sys, "executable", r"D:\New\EaveLuxOS.exe"):
            launchlink.register(Path(r"D:\New"), "Windows", winreg=reg)
        self.assertIn(r"D:\New\EaveLuxOS.exe", reg.keys[r"Software\Classes\eaveluxos\shell\open\command"][""],
                      "a copy moved elsewhere takes the link over")

    def test_linux(self):
        home = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, home, True)
        calls = []
        with mock.patch.object(sys, "frozen", True, create=True), mock.patch.object(sys, "executable", "/opt/my $app/eaveluxos"), \
                mock.patch.dict("os.environ", {"XDG_DATA_HOME": ""}), mock.patch("shutil.which", return_value="/usr/bin/xdg-mime"):
            self.assertTrue(launchlink.register(Path("/opt/x"), "Linux", home=home, run=lambda a, **k: calls.append(a)))
        text = (home / ".local/share/applications/eaveluxos-start.desktop").read_text()
        self.assertIn('Exec="/opt/my \\$app/eaveluxos" "run"', text)
        self.assertIn("MimeType=x-scheme-handler/eaveluxos;", text)
        self.assertNotIn("%u", text)
        self.assertEqual(calls[-1], ["xdg-mime", "default", "eaveluxos-start.desktop", "x-scheme-handler/eaveluxos"])

    def test_mac_app_carries_the_link(self):
        spec = importlib.util.spec_from_file_location("build", HERE.parent / "packaging" / "build.py")
        b = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(b)
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        app = tmp / "EaveLuxOS.app"
        (app / "Contents").mkdir(parents=True)
        (app / "Contents" / "Info.plist").write_bytes(plistlib.dumps({"CFBundleName": "x"}))
        with mock.patch("shutil.which", return_value=None):
            b.finish_mac_app(app, "9.9.9")
        info = plistlib.loads((app / "Contents" / "Info.plist").read_bytes())
        self.assertEqual(info["CFBundleURLTypes"][0]["CFBundleURLSchemes"], ["eaveluxos"])
        self.assertTrue(launchlink.supported("Darwin", True))
        self.assertFalse(launchlink.supported("Darwin", False), "run from source on a Mac: no app to carry it")


class Review(unittest.TestCase):
    def test_1_the_standalone_repro(self):
        script = str(HERE / "repro_min_icon_cant_start.py")
        self.assertIn("BUG:", subprocess.run([sys.executable, script], capture_output=True, text=True, timeout=60).stdout)
        self.assertIn("OK:", subprocess.run([sys.executable, script, "--fixed"], capture_output=True, text=True, timeout=60).stdout)

    def test_main_sets_it_up_at_each_start(self):
        main = (HERE.parent / "main.py").read_text(encoding="utf-8")
        self.assertIn("launchlink.register(HERE)", main)


try:
    from playwright.sync_api import sync_playwright
except ImportError:            # pragma: no cover
    sync_playwright = None


@unittest.skipIf(sync_playwright is None, "Playwright isn't installed")
class Browser(ServerBase):
    def serve(self, port=0):
        from eaveluxos.server import make_server
        srv = make_server(self.app, "127.0.0.1", port)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        return srv

    def test_start_button_and_reload_once_it_answers(self):
        self.app.start_link, self.app.program = True, r"C:\Apps\EaveLuxOS\EaveLuxOS.exe"
        srv = self.serve()
        port = srv.server_address[1]
        try:
            pw = sync_playwright().start()
            br = pw.chromium.launch()
        except Exception as e:
            srv.shutdown(); srv.server_close()
            self.skipTest(f"Chromium can't start: {e}")
        self.addCleanup(pw.stop)
        self.addCleanup(br.close)
        ctx = br.new_context(service_workers="block")
        pg = ctx.new_page()
        pg.goto(f"http://localhost:{port}/#home")
        pg.wait_for_selector("#quick [data-q=off]", timeout=20000)
        self.assertIn("EaveLuxOS.exe", pg.evaluate("localStorage.getItem('elx.start')"))
        srv.shutdown(); srv.server_close()
        # The program stopped: the page itself still loads (the installed
        # app keeps it), but the app's questions go unanswered.
        pg2 = ctx.new_page()
        pg2.route("**/*", lambda r: r.continue_() if not r.request.url.endswith("/api/session") else r.abort())
        srv2 = self.serve(port)
        self.addCleanup(srv2.server_close)
        self.addCleanup(srv2.shutdown)
        pg2.goto(f"http://localhost:{port}/#home")
        pg2.wait_for_selector("a[data-startlink]", timeout=20000)
        self.assertEqual(pg2.get_attribute("a[data-startlink]", "href"), "eaveluxos://start")
        self.assertIn(r"C:\Apps\EaveLuxOS\EaveLuxOS.exe", pg2.inner_text("#main"))
        pg2.unroute("**/*")                         # the program answers again
        # 4.27: wait_for_selector survives the page reloading itself; polling
        # with query_selector failed when the reload landed mid-call
        try:
            pg2.wait_for_selector("#quick [data-q=off]", state="attached", timeout=20000)
        except Exception:
            self.fail("the page didn't open the app by itself")


if __name__ == "__main__":
    unittest.main()
