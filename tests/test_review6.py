# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Regression tests for the 3.12.1 review fixes."""
import copy
import http.server
import io
import json
import os
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

from eaveluxos import community, server, winfirewall
from eaveluxos.server import App, make_server
from tests import fake_trimlight as F

ROOT = Path(__file__).resolve().parent.parent
TOKEN = "t" * 32


class Quiet(http.server.BaseHTTPRequestHandler):
    hits: list = []

    def log_message(self, *a):
        pass

    def do_GET(self):
        Quiet.hits.append(self.path)
        if self.path.startswith("/redirect/"):
            self.send_response(302)
            self.send_header("Location", f"http://127.0.0.1:{self.server.server_address[1]}/elsewhere/index.json")
            self.end_headers()
            return
        b = b'{"patterns": []}'
        self.send_response(200)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import eaveluxos.api
        cls.cloud = F.start()
        cls._saved = (os.environ.get("TRIMLIGHT_API_BASE"), eaveluxos.api.BASE_URL)
        os.environ["TRIMLIGHT_API_BASE"] = f"http://127.0.0.1:{cls.cloud.server_address[1]}/trimlight"
        eaveluxos.api.BASE_URL = os.environ["TRIMLIGHT_API_BASE"]
        cls.web = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Quiet)
        threading.Thread(target=cls.web.serve_forever, daemon=True).start()
        cls.dir = Path(tempfile.mkdtemp())
        cls.app = App(cls.dir, start=False)
        s = copy.deepcopy(cls.app.store.settings)
        s["location"].update(latitude=39.95, longitude=-75.16)
        s["setup_done"] = True
        cls.app.store.save_settings(s)
        cls.app.store.save_secrets(client_id=F.CID, client_secret=F.SECRET, webhook_token=TOKEN)
        cls.app.store.save_user(None, "owner", "admin", password="password-xxxx")
        cls.app.store.save_user(None, "ed", "editor", password="password-xxxx")
        cls.app.store.save_user(None, "vi", "viewer", password="password-xxxx")
        cls.app.rebuild()
        cls.srv = make_server(cls.app, "127.0.0.1", 0)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        import eaveluxos.api
        for s in (cls.srv, cls.web):
            s.shutdown()
            s.server_close()
        cls.app.store.close()
        shutil.rmtree(cls.dir, ignore_errors=True)
        env, base = cls._saved
        if env is None:
            os.environ.pop("TRIMLIGHT_API_BASE", None)
        else:
            os.environ["TRIMLIGHT_API_BASE"] = env
        eaveluxos.api.BASE_URL = base

    def call(self, path, body=None, hdr=None, raw=None, ctype="application/json"):
        data = raw if raw is not None else (None if body is None else json.dumps(body).encode())
        r = urllib.request.Request(f"http://127.0.0.1:{self.srv.server_address[1]}{path}", data=data,
                                   headers={"Content-Type": ctype, "X-Requested-With": "eaveluxos", **(hdr or {})})
        try:
            with urllib.request.urlopen(r, timeout=30) as x:
                return x.status, json.loads(x.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")
        except (ConnectionError, urllib.error.URLError) as e:
            return 0, {"error": str(e)}

    def signed_in(self, user):
        h = {"X-Forwarded-For": "203.0.113.20"}
        st, r = self.call("/api/login", {"username": user, "password": "password-xxxx"}, h)
        self.assertEqual(st, 200, r)
        return {**h, "X-Session": r["token"]}

    def set_library(self, url):
        s = copy.deepcopy(self.app.store.settings)
        s["community"] = {"url": url}
        self.app.store.save_settings(s)


class LibraryAddressTests(Base):
    def test_import_never_changes_it(self):
        Quiet.hits.clear()
        evil = {"effects": {"candy": {"label": "Candy", "colors": ["#FF0000"], "counts": [3]}},
                "community": {"url": f"http://127.0.0.1:{self.web.server_address[1]}/admin?x="}}
        for mode in ("replace", "merge"):
            f = copy.deepcopy(evil)
            f["effects"] = {f"candy_{mode}": {"label": f"Candy {mode}", "colors": ["#FF0000"], "counts": [3]}}
            st, r = self.call("/api/import", {"mode": mode, "settings": f})
            self.assertEqual(st, 200, r)
            self.assertNotIn("community", self.app.store.settings)
        self.call("/api/community")
        self.assertEqual(Quiet.hits, [])

    def test_editor_cannot_change_it(self):
        h = self.signed_in("ed")
        st, cur = self.call("/api/settings", hdr=h)
        cur["community"] = {"url": "https://attacker.example/"}
        st, r = self.call("/api/settings", cur, hdr=h)
        self.assertEqual(st, 403, r)

    def test_not_exported(self):
        self.set_library("https://example.org/lib/")
        try:
            st, r = self.call("/api/export")
            self.assertNotIn("community", r["settings"])
        finally:
            s = copy.deepcopy(self.app.store.settings)
            s.pop("community", None)
            self.app.store.save_settings(s)

    def test_https_only_and_no_query(self):
        for bad in ("http://192.168.1.1/", "ftp://example.org/", "https://example.org/x?cmd=1", "https://u:p@example.org/", "https:///x"):
            with self.subTest(bad=bad), self.assertRaises(community.CommunityError):
                community.base_url({"community": {"url": bad}})
        self.assertEqual(community.base_url({"community": {"url": "http://127.0.0.1:9/"}}), "http://127.0.0.1:9/")

    def test_redirects_are_not_followed(self):
        Quiet.hits.clear()
        lib = community.Library()
        with self.assertRaises(community.CommunityError) as cm:
            lib.index({"community": {"url": f"http://127.0.0.1:{self.web.server_address[1]}/redirect/"}})
        self.assertIn("somewhere else", str(cm.exception))
        self.assertEqual(Quiet.hits, ["/redirect/index.json"])         # never fetched /elsewhere


class PhotoMemoryTests(Base):
    def setUp(self):
        try:
            from PIL import Image  # noqa: F401
        except ImportError:
            self.skipTest("Pillow not installed")

    def test_huge_png_refused_before_decoding(self):
        from PIL import Image
        b = io.BytesIO()
        Image.new("L", (8000, 6000), 0).save(b, "PNG")                 # 48 MP in a few KB
        with mock.patch.object(Image.Image, "load", side_effect=AssertionError("decoded")):
            with self.assertRaises(server.PhotoUnreadable) as cm:
                server.shrink_photo(b.getvalue())
        self.assertEqual(cm.exception.code, 413)

    def test_big_jpeg_still_fine(self):
        from PIL import Image
        b = io.BytesIO()
        Image.new("RGB", (8000, 6000), (30, 30, 30)).save(b, "JPEG", quality=60)
        self.assertGreater(len(server.shrink_photo(b.getvalue())), 1000)

    def test_viewer_cannot_send_a_big_body(self):
        h = self.signed_in("vi")
        st, r = self.call("/api/photo/upload?side=front", hdr=h, raw=b"\xff\xd8" + bytes(3_000_000), ctype="image/jpeg")
        self.assertIn(st, (413, 0))                                    # refused by size, not read in full


class HomeAssistantTests(Base):
    def hook(self, a, body):
        r = urllib.request.Request(f"http://127.0.0.1:{self.srv.server_address[1]}/api/hook/{a}", data=json.dumps(body).encode(),
                                   headers={"Content-Type": "application/json", "X-Token": TOKEN})
        try:
            with urllib.request.urlopen(r, timeout=30) as x:
                return x.status, json.loads(x.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def test_brightness_on_an_off_light_turns_it_on(self):
        self.hook("off", {})
        self.assertEqual(self.hook("levels", {"brightness": 128})[0], 400)          # unchanged without "on"
        st, r = self.hook("levels", {"brightness": "128", "on": True})
        self.assertEqual((st, r["on"], r["brightness"]), (200, True, 128), r)
        self.hook("resume", {})

    def load_yaml(self):
        try:
            import yaml
        except ImportError:
            self.skipTest("PyYAML not installed")

        class L(yaml.SafeLoader):
            pass
        L.add_constructor("!secret", lambda loader, node: "S")
        return yaml.load((ROOT / "tools/home-assistant/eaveluxos.yaml").read_text(encoding="utf-8"), Loader=L)

    def test_package_sends_on_with_brightness(self):
        body = self.load_yaml()["light"][0]["lights"]["house_lights"]["set_level"][0]["data"]["body"]
        self.assertIs(body.get("on"), True)            # the key is the text "on" (unquoted, YAML would read True)

    def test_effect_only_when_it_is_in_the_list(self):
        try:
            import jinja2
        except ImportError:
            self.skipTest("Jinja2 not installed")
        tpl = self.load_yaml()["light"][0]["lights"]["house_lights"]["effect_template"]
        pats = [{"key": "christmas", "label": "Christmas"}]

        def render(on, effect):
            st = {"on": on, "effect": effect, "patterns": pats}
            return jinja2.Environment().from_string(tpl).render(state_attr=lambda e, a: st.get(a)).strip()
        self.assertEqual(render(True, "Christmas"), "Christmas")
        self.assertEqual(render(False, "Christmas"), "")
        self.assertEqual(render(True, None), "")        # music show
        self.assertEqual(render(True, "Something else"), "")


class SmallerFixesTests(unittest.TestCase):
    def test_addresses_kept_for_a_minute(self):
        server._lan_cache = (0.0, [])
        with mock.patch.object(server, "_lan_addresses", return_value=["10.0.0.5"]) as look:
            server.lan_addresses()
            server.lan_addresses()
        self.assertEqual(look.call_count, 1)
        server._lan_cache = (0.0, [])

    def test_firewall_check_says_when_running_from_python(self):
        import subprocess

        def run(cmd, **kw):
            return subprocess.CompletedProcess(cmd, 0, "CATEGORY=Private\nBLOCKED=python.exe\nALLOWED=False\n", "")
        with mock.patch.object(winfirewall.sys, "frozen", False, create=True):
            r = winfirewall.check(8787, run=run)
        self.assertTrue(r["from_source"])
        self.assertIn("from_source", (ROOT / "eaveluxos/static/app.js").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
