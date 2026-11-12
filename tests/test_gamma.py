# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""3.8 gamma-corrected colors."""
import json
import shutil
import subprocess
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from eaveluxos.schedule import ConfigError, Effect, color_gamma, gamma_correct
from eaveluxos.server import App, make_server

H = {"Content-Type": "application/json", "X-Requested-With": "eaveluxos"}
PROXY = {**H, "X-Forwarded-For": "203.0.113.66"}
STATIC = Path(__file__).resolve().parent.parent / "eaveluxos" / "static"


class Math(unittest.TestCase):
    def test_formula(self):
        self.assertEqual(gamma_correct(0xFFFFFF, 2.2), 0xFFFFFF)
        self.assertEqual(gamma_correct(0x000000, 2.2), 0x000000)
        self.assertEqual(gamma_correct(0x808080, 2.2), 0x383838)       # 255*(128/255)^2.2 = 56
        self.assertEqual(gamma_correct(0xFF8000, 2.2), 0xFF3800)

    def test_off_or_one_changes_nothing(self):
        for g in (None, 0, 1, 1.0):
            self.assertEqual(gamma_correct(0x123456, g), 0x123456)

    def test_dim_channels_stay_on(self):
        # 255*(5/255)^2.2 rounds to 0; it stays 1 so the hue doesn't change
        self.assertEqual(gamma_correct(0x050505, 2.2), 0x010101)
        self.assertEqual(gamma_correct(0x050000, 3.5) & 0x00FFFF, 0)    # channels that were off stay off

    def test_settings(self):
        self.assertIsNone(color_gamma({}))
        self.assertIsNone(color_gamma({"color": {"enabled": False, "gamma": 9}}))
        self.assertEqual(color_gamma({"color": {"enabled": True}}), 2.2)
        self.assertEqual(color_gamma({"color": {"enabled": True, "gamma": "2.8"}}), 2.8)
        for bad in ({"color": "yes"}, {"color": {"enabled": True, "gamma": 0.5}}, {"color": {"enabled": True, "gamma": 4}},
                    {"color": {"enabled": True, "gamma": "x"}}, {"color": {"enabled": True, "gamma": float("nan")}}):
            with self.assertRaises(ConfigError, msg=bad):
                color_gamma(bad)


class Patterns(unittest.TestCase):
    PAT = {"label": "Warm", "colors": ["#FF8000", "off", "#808080"], "counts": [2, 1, 3]}

    def test_custom_colors_are_corrected_and_swatches_are_not(self):
        e = Effect.from_config("w", self.PAT, 2.2)
        self.assertEqual([p["color"] for p in e.payload["pixels"]], [0xFF3800, 0, 0x383838])
        self.assertTrue(e.payload["pixels"][1]["disable"])
        self.assertEqual(e.swatches(), ["#FF8000", "off", "#808080"])

    def test_exact_colors_skip_correction(self):
        e = Effect.from_config("w", {**self.PAT, "exact_colors": True}, 2.2)
        self.assertEqual([p["color"] for p in e.payload["pixels"]], [0xFF8000, 0, 0x808080])

    def test_builtin_untouched(self):
        a = Effect.from_config("b", {"builtin": 5}, 2.2).payload
        self.assertEqual(a, Effect.from_config("b", {"builtin": 5}).payload)

    def test_browser_matches_server(self):
        """app.js converter shows the same numbers the server sends."""
        js = (STATIC / "app.js").read_text(encoding="utf-8")
        start = js.index("function gammaHex")
        fn = js[start:js.index("\n}\n", start) + 3]
        cases = [(f"#{c:06X}", g) for c in (0xFF8000, 0x808080, 0x050505, 0x00FF7F, 0x1A2B3C) for g in (1.0, 1.8, 2.2, 2.8, 3.5)]
        try:
            out = subprocess.run(["node", "-e", fn + f"console.log(JSON.stringify({json.dumps(cases)}.map(([h,g])=>gammaHex(h,g))))"],
                                 capture_output=True, text=True, encoding="utf-8", timeout=30)
        except FileNotFoundError:
            self.skipTest("node isn't installed")
        got = json.loads(out.stdout)
        self.assertEqual(got, [f"#{gamma_correct(int(h[1:], 16), g):06X}" for h, g in cases])


class Server(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.app = App(self.dir, start=False)
        self.srv = make_server(self.app, "127.0.0.1", 0)
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.app.store.close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def call(self, path, body=None, hdr=H):
        r = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}",
                                   data=None if body is None else json.dumps(body).encode(), headers=hdr)
        try:
            with urllib.request.urlopen(r, timeout=10) as x:
                return x.status, json.loads(x.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def test_save_checks_gamma_and_app_uses_it(self):
        s = self.call("/api/settings")[1]
        s["color"] = {"enabled": True, "gamma": 5}
        st, r = self.call("/api/settings", s)
        self.assertEqual(st, 400, r)
        self.assertIn("Gamma", r.get("error", ""))
        self.assertIsNone(self.app.gamma())
        s["color"] = {"enabled": True, "gamma": 2.4}
        st, r = self.call("/api/settings", s)
        self.assertEqual(st, 200, r)
        self.assertEqual(self.app.gamma(), 2.4)

    def test_editor_cannot_change_color_correction(self):
        for name, role in (("owner", "admin"), ("helper", "editor")):
            self.assertEqual(self.call("/api/users", {"username": name, "role": role, "password": "password-xxxx"})[0], 200)
        tok = self.call("/api/login", {"username": "helper", "password": "password-xxxx"}, PROXY)[1]["token"]
        e = {**PROXY, "X-Session": tok}
        s = self.call("/api/settings", hdr=e)[1]
        s["color"] = {"enabled": True, "gamma": 2.2}
        self.assertEqual(self.call("/api/settings", s, e)[0], 403)


if __name__ == "__main__":
    unittest.main()
