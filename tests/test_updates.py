# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""'A new version is out' (3.14): the daily GitHub release check."""
import json
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

from eaveluxos import updates
from eaveluxos.updates import UpdateChecker, UpdateError, read_release
from eaveluxos.version import VERSION

REPO = "https://github.com/ThinkTank4n6/eaveluxos/"


def bump(v=VERSION, by=1):
    a, b, c = map(int, v.split("."))
    return f"{a}.{b}.{c + by}"


def release(tag, **extra):
    r = {"tag_name": f"v{tag}", "html_url": f"{REPO}releases/tag/v{tag}", "published_at": "2026-11-14T01:00:00Z",
         "body": "- Fixed things", "draft": False, "prerelease": False,
         "assets": [{"name": "EaveLuxOS-Windows.zip", "browser_download_url": f"{REPO}releases/download/v{tag}/EaveLuxOS-Windows.zip"},
                    {"name": "EaveLuxOS-macOS.dmg", "browser_download_url": f"{REPO}releases/download/v{tag}/EaveLuxOS-macOS.dmg"},
                    {"name": f"eaveluxos_{tag}_arm64.deb", "browser_download_url": f"{REPO}releases/download/v{tag}/eaveluxos_{tag}_arm64.deb"},
                    {"name": f"eaveluxos_{tag}_amd64.deb", "browser_download_url": f"{REPO}releases/download/v{tag}/eaveluxos_{tag}_amd64.deb"}]}
    r.update(extra)
    return json.dumps(r).encode()


class Checker(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.answer = release(bump())
        self.fetched = []
        self.u = UpdateChecker(self.dir, fetch=self.fake)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def fake(self, url):
        self.fetched.append(url)
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer

    def test_newer_version_is_reported(self):
        s = self.u.check()
        self.assertEqual(self.fetched, [updates.API_URL])
        self.assertTrue(s["newer"])
        self.assertEqual((s["latest"], s["current"]), (bump(), VERSION))
        self.assertTrue(s["url"].startswith(REPO))
        self.assertIn("Fixed things", s["notes"])

    def test_same_or_older_is_not(self):
        for v in (VERSION, "1.0.0"):
            self.answer = release(v)
            self.assertFalse(self.u.check()["newer"], v)

    def test_versions_compare_as_numbers(self):
        self.assertTrue(UpdateChecker.newer("99.0.0"))
        with mock.patch.object(updates, "VERSION", "3.9.0"):
            self.assertTrue(UpdateChecker.newer("3.10.0"))     # not "3.10" < "3.9" as text

    def test_remembered_across_restarts(self):
        self.u.check()
        again = UpdateChecker(self.dir, fetch=lambda url: (_ for _ in ()).throw(AssertionError("no fetch")))
        self.assertTrue(again.summary()["newer"])

    def test_turned_off_hides_it(self):
        self.u.check()
        s = self.u.set_enabled(False)
        self.assertFalse(s["enabled"])
        self.assertFalse(s["newer"])
        self.assertTrue(UpdateChecker(self.dir).summary()["enabled"] is False)

    def test_links_outside_the_project_are_dropped(self):
        self.answer = release(bump(), html_url="https://evil.example/x",
                              assets=[{"name": "EaveLuxOS-Windows.zip", "browser_download_url": "https://evil.example/a.zip"}])
        r = read_release(self.answer)
        self.assertEqual(r["url"], updates.RELEASES_URL)
        self.assertEqual(r["assets"], {})

    def test_bad_answers_are_errors_not_crashes(self):
        for bad in (b"not json", b"[]", json.dumps({"tag_name": "latest"}).encode(),
                    release(bump(), prerelease=True)):
            self.answer = bad
            s = self.u.check()
            self.assertTrue(s["error"], bad)
            self.assertFalse(s["newer"])
        self.answer = UpdateError("Couldn't reach GitHub: offline")
        self.assertIn("offline", self.u.check()["error"])

    def test_notes_are_capped(self):
        self.answer = release(bump(), body="x" * 50_000)
        self.assertEqual(len(self.u.check()["notes"]), updates.NOTES_MAX)

    def test_download_for_this_computer(self):
        names = ["EaveLuxOS-Windows.zip", "EaveLuxOS-macOS.dmg", "eaveluxos_9_arm64.deb", "eaveluxos_9_amd64.deb"]
        self.assertIsNone(updates.asset_for_this_computer(names))            # from source: the release page
        with mock.patch.object(updates.sys, "frozen", True, create=True):
            for system, machine, want in (("Windows", "AMD64", "EaveLuxOS-Windows.zip"), ("Darwin", "arm64", "EaveLuxOS-macOS.dmg"),
                                          ("Linux", "aarch64", "eaveluxos_9_arm64.deb"), ("Linux", "x86_64", "eaveluxos_9_amd64.deb")):
                with mock.patch.object(updates.platform, "system", return_value=system), \
                        mock.patch.object(updates.platform, "machine", return_value=machine):
                    self.assertEqual(updates.asset_for_this_computer(names), want)

    def test_redirects_are_refused(self):
        h = updates._NoRedirect()
        self.assertIsNone(h.redirect_request(None, None, 302, "Found", {}, "http://192.168.1.1/"))


class Endpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from eaveluxos.server import App, make_server
        cls.dir = Path(tempfile.mkdtemp())
        cls.app = App(cls.dir, start=False)
        cls.app.updates.fetch = lambda url: release(bump())
        cls.srv = make_server(cls.app, "127.0.0.1", 0)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.app.store.close()
        shutil.rmtree(cls.dir, ignore_errors=True)

    def call(self, path, body=None):
        r = urllib.request.Request(f"http://127.0.0.1:{self.srv.server_address[1]}{path}",
                                   data=json.dumps(body).encode() if body is not None else None,
                                   headers={"Content-Type": "application/json", "X-Requested-With": "eaveluxos"},
                                   method="POST" if body is not None else "GET")
        try:
            with urllib.request.urlopen(r, timeout=20) as x:
                return x.status, json.loads(x.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def test_check_and_settings(self):
        st, r = self.call("/api/update")
        self.assertEqual(st, 200)
        self.assertFalse(r["newer"])                           # not checked yet
        st, r = self.call("/api/update/check", {})
        self.assertEqual((st, r["newer"], r["latest"]), (200, True, bump()))
        st, r = self.call("/api/update/settings", {"enabled": "yes"})
        self.assertEqual(st, 400)
        st, r = self.call("/api/update/settings", {"enabled": False})
        self.assertEqual((st, r["enabled"], r["newer"]), (200, False, False))
        self.call("/api/update/settings", {"enabled": True})

    def test_screens_have_the_bar_and_panel(self):
        root = Path(__file__).resolve().parent.parent / "eaveluxos" / "static"
        self.assertIn('id="updbar"', (root / "index.html").read_text(encoding="utf-8"))
        js = (root / "app.js").read_text(encoding="utf-8")
        for s in ("async function updateBar", 'id="updbox"', "data-updnow", "update/settings"):
            self.assertIn(s, js)


if __name__ == "__main__":
    unittest.main()
