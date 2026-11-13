# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Settings › Start automatically and house photos, through the web API, plus a
guard against the import mistake that broke Start automatically in 3.10.0."""
import ast
import base64
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

from eaveluxos import autostart
from eaveluxos.server import App, make_server

ROOT = Path(__file__).resolve().parent.parent


class ApiCase(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.app = App(self.dir, start=False)
        self.srv = make_server(self.app, "127.0.0.1", 0)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.app.store.close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def call(self, path, body=None, raw=False):
        r = urllib.request.Request(f"http://127.0.0.1:{self.srv.server_address[1]}{path}",
                                   data=None if body is None else json.dumps(body).encode(),
                                   headers={"Content-Type": "application/json", "X-Requested-With": "eaveluxos"})
        try:
            with urllib.request.urlopen(r, timeout=20) as x:
                data = x.read()
                return x.status, (data if raw else json.loads(data))
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")


class StartAutomaticallyTests(ApiCase):
    def test_turn_on_and_off_on_windows(self):
        startup = self.dir / "appdata"
        with mock.patch.object(autostart.platform, "system", return_value="Windows"), \
                mock.patch.dict(os.environ, {"APPDATA": str(startup)}):
            vbs = startup / "Microsoft/Windows/Start Menu/Programs/Startup/EaveLuxOS.vbs"
            st, r = self.call("/api/autostart", {"enabled": True})
            self.assertEqual((st, r.get("enabled")), (200, True), r)
            self.assertTrue(vbs.exists())
            self.assertIn("run", vbs.read_text(encoding="locale"))
            st, r = self.call("/api/autostart", {"enabled": False})
            self.assertEqual((st, r.get("enabled")), (200, False), r)
            self.assertFalse(vbs.exists())

    def test_a_write_problem_is_reported_not_hidden(self):
        with mock.patch.object(autostart, "set_enabled", side_effect=PermissionError("Access is denied")):
            st, r = self.call("/api/autostart", {"enabled": True})
        self.assertEqual(st, 400)
        self.assertIn("Access is denied", r["error"])


class NoShadowedImportsTest(unittest.TestCase):
    """An import inside a function makes that name local to the whole
    function: in 3.10.0, `from . import autostart` inside one branch of the
    request handler hid the module's autostart from every other branch."""
    def test_functions_do_not_re_import_module_level_names(self):
        bad = []
        for f in sorted((ROOT / "eaveluxos").glob("*.py")) + [ROOT / "main.py"]:
            tree = ast.parse(f.read_text(encoding="utf-8"))
            top = {(a.asname or a.name).split(".")[0] for n in tree.body
                   if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names}
            for fn in ast.walk(tree):
                if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    for n in ast.walk(fn):
                        if isinstance(n, (ast.Import, ast.ImportFrom)):
                            bad += [f"{f.name}:{n.lineno} {fn.name}() re-imports {a.asname or a.name}"
                                    for a in n.names if (a.asname or a.name).split(".")[0] in top]
        self.assertEqual(bad, [])


class PhotoTests(ApiCase):
    def jpeg(self, color=(200, 120, 40)):
        try:
            from PIL import Image
        except ImportError:   # a minimal valid JPEG header is enough for the server
            return b"\xff\xd8\xff\xe0" + bytes(500) + b"\xff\xd9"
        b = io.BytesIO()
        Image.new("RGB", (64, 48), color).save(b, "JPEG")
        return b.getvalue()

    def test_saved_photo_comes_back_byte_for_byte(self):
        raw = self.jpeg()
        st, r = self.call("/api/photo", {"side": "front", "data": "data:image/jpeg;base64," + base64.b64encode(raw).decode()})
        self.assertEqual(st, 200, r)
        st, got = self.call("/api/photo/front", raw=True)
        self.assertEqual((st, got), (200, raw))
        leftovers = [p.name for p in (self.app.store.dir / "photos").iterdir() if p.name != "front.jpg"]
        self.assertEqual(leftovers, [])                       # no temporary files left behind

    def test_replacing_a_photo(self):
        for color in ((10, 10, 10), (250, 250, 250)):
            raw = self.jpeg(color)
            self.call("/api/photo", {"side": "front", "data": base64.b64encode(raw).decode()})
        self.assertEqual(self.call("/api/photo/front", raw=True)[1], raw)

    def test_not_a_jpeg_is_refused(self):
        st, r = self.call("/api/photo", {"side": "front", "data": base64.b64encode(b"\x89PNG\r\n\x1a\n" + bytes(100)).decode()})
        self.assertEqual(st, 400)
        self.assertEqual(self.call("/api/photo/front")[0], 404)


class AppShrinksPhotoTests(ApiCase):
    """3.11.3: the original photo goes to the app computer, which shrinks it
    with Pillow; the browser's graphics never touch the pixels."""
    def setUp(self):
        super().setUp()
        try:
            from PIL import Image  # noqa: F401
        except ImportError:
            self.skipTest("Pillow not installed")

    def upload(self, raw, side="front", hdr=None):
        r = urllib.request.Request(f"http://127.0.0.1:{self.srv.server_address[1]}/api/photo/upload?side={side}", data=raw,
                                   headers={"Content-Type": "image/jpeg", "X-Requested-With": "eaveluxos", **(hdr or {})})
        try:
            with urllib.request.urlopen(r, timeout=30) as x:
                return x.status, json.loads(x.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")
        except (ConnectionError, urllib.error.URLError) as e:   # refused before the body was read
            return 0, {"error": str(e)}

    def saved(self, side="front"):
        from PIL import Image
        st, raw = self.call(f"/api/photo/{side}", raw=True)
        self.assertEqual(st, 200)
        return Image.open(io.BytesIO(raw))

    def test_phone_photo_is_turned_upright_and_shrunk(self):
        from PIL import Image
        im = Image.new("RGB", (4000, 3000), (30, 30, 80))
        im.paste((250, 200, 0), (0, 0, 400, 3000))            # a yellow stripe down the left edge
        ex = Image.Exif()
        ex[0x0112] = 6                                          # "rotate 90° clockwise to view"
        b = io.BytesIO()
        im.save(b, "JPEG", quality=90, exif=ex.tobytes())
        st, r = self.upload(b.getvalue())
        self.assertEqual(st, 200, r)
        out = self.saved()
        self.assertEqual(out.format, "JPEG")
        self.assertEqual(out.size, (1200, 1600))               # portrait now, longest side 1600
        top = out.convert("RGB").getpixel((600, 20))
        self.assertGreater(top[0], 200)                         # the stripe is along the top: turned upright

    def test_transparent_png_gets_a_white_background(self):
        from PIL import Image
        b = io.BytesIO()
        Image.new("RGBA", (300, 200), (0, 0, 0, 0)).save(b, "PNG")
        st, r = self.upload(b.getvalue())
        self.assertEqual(st, 200, r)
        self.assertGreater(min(self.saved().convert("RGB").getpixel((150, 100))), 240)

    def test_small_photo_is_not_enlarged(self):
        from PIL import Image
        b = io.BytesIO()
        Image.new("RGB", (800, 600), (10, 120, 10)).save(b, "JPEG")
        self.upload(b.getvalue())
        self.assertEqual(self.saved().size, (800, 600))

    def test_unreadable_file_asks_the_browser_to_do_it(self):
        st, r = self.upload(b"\x00\x00ftypheic" + bytes(5000))     # what an iPhone HEIC looks like to Pillow
        self.assertEqual(st, 415, r)
        self.assertEqual(self.call("/api/photo/front")[0], 404)

    def test_without_pillow_the_browser_does_it(self):
        import builtins
        real = builtins.__import__

        def no_pil(name, *a, **k):
            if name == "PIL" or name.startswith("PIL."):
                raise ImportError("No module named 'PIL'")
            return real(name, *a, **k)
        with mock.patch("builtins.__import__", side_effect=no_pil):
            st, r = self.upload(b"\xff\xd8" + bytes(100))
        self.assertEqual(st, 501, r)

    def test_big_original_allowed_when_signed_in_only(self):
        from PIL import Image
        import random
        rnd = random.Random(1)
        im = Image.frombytes("RGB", (1800, 1400), bytes(rnd.getrandbits(8) for _ in range(1800 * 1400 * 3)))
        b = io.BytesIO()
        im.save(b, "JPEG", quality=98)
        raw = b.getvalue()
        self.assertGreater(len(raw), 2_000_000)                 # bigger than the normal request limit
        st, r = self.upload(raw)                                # this computer: signed in
        self.assertEqual(st, 200, r)
        st, r = self.upload(raw, side="back", hdr={"X-Forwarded-For": "203.0.113.5"})   # a phone, not signed in
        self.assertIn(st, (413, 0))
        self.assertEqual(self.call("/api/photo/back")[0], 404)


if __name__ == "__main__":
    unittest.main()
