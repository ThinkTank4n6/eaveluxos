# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""4.4.5: a user's house photo wouldn't upload. Their camera wrote a 0/0
resolution into the EXIF, and Pillow 11.0 (the Windows release) divided by
zero rewriting it while turning the photo upright: "Something went wrong"."""
import io
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image, ImageOps, TiffImagePlugin

from eaveluxos import server
from eaveluxos.server import PhotoUnreadable, shrink_photo

ROOT = Path(__file__).resolve().parent.parent


def photo(orientation, size=(30, 20), fmt="JPEG", zero_resolution=False):
    im = Image.new("RGB", size)
    for x in range(size[0]):
        for y in range(size[1]):
            im.putpixel((x, y), (x * 8 % 256, y * 12 % 256, 0))
    ex = Image.Exif()
    ex[0x0112] = orientation
    ex[0x011A] = 72.0
    ex[0x011B] = 72.0
    ex[0x0128] = 2
    b = io.BytesIO()
    im.save(b, fmt, exif=ex.tobytes(), **({"quality": 100} if fmt == "JPEG" else {}))
    raw = b.getvalue()
    if zero_resolution:
        i = raw.find(b"\x00\x00\x00\x48\x00\x00\x00\x01")     # XResolution 72/1 -> 0/0
        assert i > 0
        raw = raw[:i] + bytes(8) + raw[i + 8:]
    return raw


class Upright(unittest.TestCase):
    def test_every_orientation_as_pillow_turns_it(self):
        for o in range(1, 9):
            raw = photo(o, fmt="PNG")
            want = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("RGB")
            got = Image.open(io.BytesIO(shrink_photo(raw))).convert("RGB")
            self.assertEqual(got.size, want.size, o)
            diff = max(abs(a - b) for p, q in zip(got.tobytes(), want.tobytes()) for a, b in [(p, q)])
            self.assertLess(diff, 40, o)

    def test_a_zero_resolution_like_pillow_11(self):
        raw = photo(6, zero_resolution=True)
        with mock.patch.object(TiffImagePlugin.IFDRational, "__float__", lambda r: r.numerator / r.denominator), \
             mock.patch.object(TiffImagePlugin, "_limit_rational",
                               lambda val, mx: TiffImagePlugin.IFDRational(float(val)).limit_rational(mx)):
            got = Image.open(io.BytesIO(shrink_photo(raw)))
        self.assertEqual(got.size, (20, 30), "saved and turned upright")

    def test_anything_else_unexpected_lets_the_browser_do_it(self):
        with mock.patch.object(server, "_upright", side_effect=ZeroDivisionError("x")), \
             self.assertLogs("eaveluxos.web", "WARNING"), self.assertRaises(PhotoUnreadable) as cm:
            shrink_photo(photo(1))
        self.assertEqual(cm.exception.code, 415)

    def test_too_large_still_says_so(self):
        with mock.patch.object(server, "PHOTO_MAX_PIXELS_FULL_DECODE", 100), self.assertRaises(PhotoUnreadable) as cm:
            shrink_photo(photo(1, fmt="PNG"))
        self.assertEqual(cm.exception.code, 413)

    def test_the_browser_also_takes_over_after_a_server_error(self):
        js = (ROOT / "eaveluxos" / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn("if (r.status < 500 && r.status !== 415) throw", js)


if __name__ == "__main__":
    unittest.main()
