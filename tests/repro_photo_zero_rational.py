# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""4.4.5: a user's house photo wouldn't upload ("Something went wrong").
Their camera wrote a resolution of 0/0 into the photo's EXIF; Pillow's
exif_transpose rewrites the EXIF and divides by zero. The picture is fine.
Run: python3 tests/repro_photo_zero_rational.py"""
import io, sys; from pathlib import Path; sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from PIL import Image, TiffImagePlugin
from eaveluxos.server import shrink_photo, PhotoUnreadable
# The Windows release has Pillow 11.0.0, where turning a 0/0 value into a number divides by zero
# (Pillow 12 fixed it); act like 11.0 whatever is installed here.
TiffImagePlugin.IFDRational.__float__ = lambda r: r.numerator / r.denominator
TiffImagePlugin._limit_rational = lambda val, max_val: (                  # 11.0's version calls float()
    TiffImagePlugin.IFDRational(float(val)).limit_rational(max_val))
im = Image.new("RGB", (40, 20), (200, 30, 30))
ex = Image.Exif(); ex[0x0112] = 6; ex[0x011A] = 72.0; ex[0x011B] = 72.0; ex[0x0128] = 2   # turned, 72 dpi
b = io.BytesIO(); im.save(b, "JPEG", exif=ex.tobytes()); raw = b.getvalue()
i = raw.find(b"\x00\x00\x00\x48\x00\x00\x00\x01")                    # XResolution 72/1 ...
raw = raw[:i] + bytes(8) + raw[i + 8:]                                # ... becomes 0/0
try:
    out = Image.open(io.BytesIO(shrink_photo(raw)))
    print("OK: saved", out.size, "(turned upright)" if out.size == (20, 40) else "(NOT turned upright)")
except (ZeroDivisionError, PhotoUnreadable) as e:
    print(f"BUG: {e.__class__.__name__}: {e}")
