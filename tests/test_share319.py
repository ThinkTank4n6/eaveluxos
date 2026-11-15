# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""3.19: share codes and QR codes."""
import base64
import json
import shutil
import subprocess
import unittest
import zlib
from pathlib import Path

from eaveluxos import sharecode as SC
from eaveluxos.store import DEFAULT_SETTINGS

HERE = Path(__file__).resolve().parent


def raw_code(doc, raw=None) -> str:
    c = zlib.compressobj(9, zlib.DEFLATED, -15)
    body = raw if raw is not None else json.dumps(doc).encode()
    return "ELX1:" + base64.urlsafe_b64encode(c.compress(body) + c.flush()).decode().rstrip("=")


class ShareCodes(unittest.TestCase):
    effects = DEFAULT_SETTINGS["effects"]

    def test_round_trip_and_found_inside_a_message(self):
        r = SC.encode_keys(self.effects, ["christmas", "snowfall"], 10)
        self.assertTrue(r["code"].startswith("ELX1:"))
        self.assertEqual(r["labels"], ["Christmas", "Snowfall"])
        got = SC.decode(f"Try my lights!\n{r['code'][:40]}\n{r['code'][40:]}  :)")
        self.assertEqual([p["label"] for p in got["patterns"]], ["Christmas", "Snowfall"])
        self.assertEqual(got["patterns"][0]["colors"], self.effects["christmas"]["colors"])
        self.assertEqual(got["rotate"], 10)
        one = SC.decode(SC.encode_keys(self.effects, ["christmas"], 10)["code"])
        self.assertIsNone(one["rotate"], "one pattern isn't a playlist")

    def test_only_shareable_patterns(self):
        effs = {**self.effects, "mine": {"label": "On the controller", "saved": "9-11"},
                "sp": {"label": "Split", "split": {"A": "christmas"}},
                "sc": {"label": "Scene", "colors": ["#FF0000"], "counts": [1], "scene": {"groups": []}}}
        for k in ("mine", "sp", "sc", "nope"):
            with self.assertRaises(SC.ShareError, msg=k):
                SC.encode_keys(effs, [k])
        with self.assertRaises(SC.ShareError):
            SC.encode_keys(self.effects, ["christmas"] * 9)
        for bad in (None, [], "christmas", [1]):
            with self.assertRaises(SC.ShareError):
                SC.encode_keys(self.effects, bad)
        with self.assertRaises(SC.ShareError):
            SC.encode_keys(self.effects, ["christmas", "snowfall"], 0)

    def test_a_code_from_someone_else_is_only_data(self):
        doc = {"v": 1, "p": [{"label": "Nice", "colors": ["#FF0000"], "counts": [2], "saved": "x", "rules": [1],
                              "client_secret": "s", "scene": {"x": 1}}], "location": {"latitude": 1}}
        got = SC.decode(raw_code(doc))
        self.assertEqual(set(got["patterns"][0]), {"label", "colors", "counts"}, "unknown fields are dropped")
        for bad in ({"v": 1, "p": [{"label": "Saved only", "saved": "9-11"}]},
                    {"v": 1, "p": [{"label": "Bad", "colors": ["red!"]}]},
                    {"v": 1, "p": [{"label": "Too many", "colors": ["#FF0000"] * 31}]},
                    {"v": 2, "p": []}, {"v": 1, "p": []}, [1, 2],
                    {"v": 1, "p": [{"colors": ["#FF0000"]}] * 9}):
            with self.assertRaises(SC.ShareError, msg=bad):
                SC.decode(raw_code(bad))

    def test_damaged_huge_and_bomb_codes(self):
        for bad in (None, 5, "hello", "ELX1:", "ELX1:!!!!", "ELX1:AAAA", "ELX1:" + "A" * (SC.MAX_CODE + 10)):
            with self.assertRaises(SC.ShareError, msg=str(bad)[:20]):
                SC.decode(bad)
        bomb = raw_code(None, raw=b'{"v":1,"p":[{"label":"' + b"a" * 4_000_000 + b'"}]}')
        self.assertLess(len(bomb), SC.MAX_CODE, "small when compressed")
        with self.assertRaises(SC.ShareError) as cm:
            SC.decode(bomb)
        self.assertIn("too much", str(cm.exception))
        good = SC.encode_keys(self.effects, ["christmas"])["code"]
        with self.assertRaises(SC.ShareError):
            SC.decode(good[:-6])                           # cut short when copied


@unittest.skipUnless(shutil.which("node"), "Node.js isn't installed")
class QrCodes(unittest.TestCase):
    def make(self, texts):
        r = subprocess.run(["node", str(HERE / "qr_check.js"), json.dumps(texts)], capture_output=True, text=True,
                           encoding="utf-8", timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_codes_decode_with_a_real_scanner(self):
        code = SC.encode_keys(DEFAULT_SETTINGS["effects"], ["christmas", "snowfall", "warm_white"], 10)["code"]
        import random
        rnd = random.Random(319)              # share codes are compressed: random-looking text
        alpha = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
        texts = [["HELLO", "M"], [code, "M"]] + [["ELX1:" + "".join(rnd.choice(alpha) for _ in range(n)), e]
                                                 for n, e in ((400, "M"), (900, "L"), (1700, "L"))]
        out = self.make(texts)
        self.assertEqual([o["v"] for o in out][0], 1)
        try:
            import cv2
            import numpy as np
        except ImportError:
            self.skipTest("OpenCV isn't installed (decoding checked where it is)")
        det = cv2.QRCodeDetector()
        for o in out:
            m = np.array([[int(c) for c in row] for row in o["m"]], dtype=np.uint8)
            img = (np.pad(1 - m, 4, constant_values=1) * 255).astype(np.uint8)
            img = cv2.resize(img, None, fx=8, fy=8, interpolation=cv2.INTER_NEAREST)
            got = det.detectAndDecode(img)[0]
            if got != o["t"] and hasattr(cv2, "QRCodeDetectorAruco"):     # OpenCV's stronger reader, for big codes
                got = cv2.QRCodeDetectorAruco().detectAndDecode(img)[0]
            self.assertEqual(got, o["t"], f"version {o['v']}")

    def test_page_scripts(self):
        html = (HERE.parent / "eaveluxos" / "static" / "index.html").read_text(encoding="utf-8")
        self.assertLess(html.index("qr.js"), html.index("app.js"))
        js = (HERE.parent / "eaveluxos" / "static" / "app.js").read_text(encoding="utf-8")
        for s in ("data-share=", "data-shareopen", "BarcodeDetector", "api('share/open'", "holidayPanel($('#holbox'))"):
            self.assertIn(s, js)


class ReleaseContents(unittest.TestCase):
    def test_no_stray_folders_in_the_project(self):
        """3.19: a test screenshot folder (ui3182) slipped into 3.18.2."""
        known = {".git", ".github", "__pycache__", "eaveluxos", "packaging", "tests", "tools", "data", "build", "dist"}
        extra = {p.name for p in HERE.parent.iterdir() if p.is_dir()} - known
        self.assertEqual(extra, set(), "folders that don't belong in the project")


if __name__ == "__main__":
    unittest.main()
