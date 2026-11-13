# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Patterns › Community: the app's library client, the server endpoints, and
the starter kit in tools/community-library (served here as the library)."""
import copy
import functools
import http.server
import importlib.util
import io
import json
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from eaveluxos import community
from eaveluxos.schedule import build_config
from eaveluxos.server import App, make_server
from eaveluxos.store import DEFAULT_SETTINGS

ROOT = Path(__file__).resolve().parent.parent
KIT = ROOT / "tools" / "community-library"
spec = importlib.util.spec_from_file_location("build_index", KIT / "build_index.py")
BI = importlib.util.module_from_spec(spec)
spec.loader.exec_module(BI)


class Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def opener_for(files: dict, calls=None):
    def opener(req):
        if calls is not None:
            calls.append(req.full_url)
        name = req.full_url.split("/lib/", 1)[1]
        if name not in files:
            raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, None)
        v = files[name]
        return Resp(v if isinstance(v, bytes) else json.dumps(v).encode())
    return opener


SET = {"community": {"url": "https://example.test/lib/"}}
GOOD = {"name": "Candy cane", "pattern": {"colors": ["#ff0000", "#FFFFFF"], "counts": [4, 4], "custom_mode": 1}}


class LibraryClientTests(unittest.TestCase):
    def test_index_keeps_good_entries_only(self):
        idx = {"version": 1, "patterns": [
            {"id": "candy-cane", "name": "Candy cane", "colors": ["#FF0000", "red", "#ffffff"], "tags": ["Christmas"]},
            {"id": "Bad ID!", "name": "x"}, {"id": "candy-cane", "name": "duplicate"}, "nonsense",
            {"id": "long", "name": "N" * 500, "description": "d\n\n" * 200}]}
        lib = community.Library(opener=opener_for({"index.json": idx}))
        got = lib.index(SET)["patterns"]
        self.assertEqual([p["id"] for p in got], ["candy-cane", "long"])
        self.assertEqual(got[0]["colors"], ["#FF0000", "#FFFFFF"])
        self.assertEqual(got[0]["tags"], ["christmas"])
        self.assertEqual(len(got[1]["name"]), 60)
        self.assertLessEqual(len(got[1]["description"]), 200)

    def test_pattern_is_checked_and_trimmed(self):
        evil = {"name": "x", "pattern": {**GOOD["pattern"], "saved_id": 3, "onclick": "alert(1)", "rules": [1]}}
        lib = community.Library(opener=opener_for({"patterns/candy-cane.json": GOOD, "patterns/evil.json": evil}))
        p = lib.pattern(SET, "candy-cane")
        self.assertEqual(p, {"label": "Candy cane", "colors": ["#FF0000", "#FFFFFF"], "counts": [4, 4], "custom_mode": 1})
        self.assertEqual(set(lib.pattern(SET, "evil")), {"label", "colors", "counts", "custom_mode"})

    def test_refused(self):
        files = {"patterns/saved.json": {"name": "x", "pattern": {"saved": "My pattern"}},
                 "patterns/badcolor.json": {"name": "x", "pattern": {"colors": ["#GG0000"]}},
                 "patterns/toolong.json": {"name": "x", "pattern": {"colors": ["#FF0000"], "counts": [500]}},
                 "patterns/notjson.json": b"<html>", "patterns/huge.json": b" " * (community.PATTERN_MAX + 10)}
        lib = community.Library(opener=opener_for(files))
        for pid in ("saved", "badcolor", "toolong", "notjson", "huge", "missing", "../etc", "UPPER"):
            with self.subTest(pid=pid), self.assertRaises(community.CommunityError):
                lib.pattern(SET, pid)

    def test_not_created_yet_says_so(self):
        lib = community.Library(opener=opener_for({}))
        with self.assertRaises(community.CommunityError) as cm:
            lib.index(SET)
        self.assertIn("isn't available yet", str(cm.exception))

    def test_only_web_addresses(self):
        with self.assertRaises(community.CommunityError):
            community.base_url({"community": {"url": "file:///etc/"}})
        self.assertEqual(community.base_url({}), community.DEFAULT_URL)
        self.assertTrue(community.DEFAULT_URL.startswith("https://"))

    def test_cached_for_a_while_then_refreshed(self):
        calls, now = [], [1000.0]
        lib = community.Library(opener=opener_for({"index.json": {"patterns": []}}, calls), clock=lambda: now[0])
        lib.index(SET)
        lib.index(SET)
        self.assertEqual(len(calls), 1)
        lib.index(SET, refresh=True)
        now[0] += community.CACHE_SECONDS + 1
        lib.index(SET)
        self.assertEqual(len(calls), 3)


class StarterKitTests(unittest.TestCase):
    def test_samples_pass_both_checks(self):
        index, problems = BI.build(KIT)
        self.assertEqual(problems, {})
        self.assertEqual(len(index["patterns"]), 4)
        s = copy.deepcopy(DEFAULT_SETTINGS)
        s["location"].update(latitude=39.95, longitude=-75.16)
        for f in sorted((KIT / "patterns").glob("*.json")):
            p = community.clean_pattern(f.stem, json.loads(f.read_text(encoding="utf-8")))
            s["effects"] = {**DEFAULT_SETTINGS["effects"], "x": p}
            build_config(s, {}, need_secrets=False)

    def test_committed_index_is_up_to_date(self):
        index, _ = BI.build(KIT)
        self.assertEqual(json.loads((KIT / "index.json").read_text(encoding="utf-8")), index)

    def test_builder_rejects_bad_submissions(self):
        d = Path(tempfile.mkdtemp())
        try:
            (d / "patterns").mkdir()
            bad = {"Bad_Name": GOOD, "saved": {"name": "x", "pattern": {"saved": "Mine"}},
                   "counts": {"name": "x", "pattern": {"colors": ["#FF0000", "#00FF00"], "counts": [3]}},
                   "both": {"name": "x", "pattern": {"colors": ["#FF0000"], "builtin": 3}},
                   "noname": {"pattern": GOOD["pattern"]}, "extra": {**GOOD, "script": "x"},
                   "speed": {"name": "x", "pattern": {"builtin": 3, "speed": 999}}}
            for k, v in bad.items():
                (d / "patterns" / f"{k}.json").write_text(json.dumps(v))
            (d / "patterns" / "good.json").write_text(json.dumps(GOOD))
            index, problems = BI.build(d)
            self.assertEqual([p["id"] for p in index["patterns"]], ["good"])
            self.assertEqual(set(problems), {f"{k}.json" for k in bad})
        finally:
            shutil.rmtree(d, ignore_errors=True)


class EndpointTests(unittest.TestCase):
    """The app reading the starter kit from a real (local) web server."""
    @classmethod
    def setUpClass(cls):
        class Quiet(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *a):
                pass
        handler = functools.partial(Quiet, directory=str(KIT))
        cls.lib = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=cls.lib.serve_forever, daemon=True).start()
        cls.dir = Path(tempfile.mkdtemp())
        cls.app = App(cls.dir, start=False)
        s = copy.deepcopy(cls.app.store.settings)
        s["community"] = {"url": f"http://127.0.0.1:{cls.lib.server_address[1]}/"}
        cls.app.store.save_settings(s)
        cls.srv = make_server(cls.app, "127.0.0.1", 0)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        for s in (cls.srv, cls.lib):
            s.shutdown()
            s.server_close()
        cls.app.store.close()
        shutil.rmtree(cls.dir, ignore_errors=True)

    def get(self, path):
        r = urllib.request.Request(f"http://127.0.0.1:{self.srv.server_address[1]}{path}", headers={"X-Requested-With": "eaveluxos"})
        try:
            with urllib.request.urlopen(r, timeout=20) as x:
                return x.status, json.loads(x.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def test_list_then_one_pattern(self):
        st, r = self.get("/api/community")
        self.assertEqual(st, 200, r)
        self.assertEqual([p["id"] for p in r["patterns"]],
                         ["candy-cane", "fourth-of-july-sparkle", "halloween-glow", "warm-architectural"])
        st, r = self.get("/api/community/pattern?id=candy-cane")
        self.assertEqual((st, r["pattern"]["colors"]), (200, ["#FF0000", "#FFFFFF"]))

    def test_missing_pattern(self):
        st, r = self.get("/api/community/pattern?id=no-such-pattern")
        self.assertEqual(st, 502)
        self.assertIn("removed from the community library", r["error"])


if __name__ == "__main__":
    unittest.main()
