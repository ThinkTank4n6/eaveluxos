"""4.26 review #1: since 4.23 a pattern can use the newer Trimlight
animations (17-22, like Juggle), but the community library's check still
allowed 0-16, so sharing one failed its pull request. Standalone; prints
BUG, or OK with --fixed."""
import sys

FIXED = "--fixed" in sys.argv
LIBRARY_MAX = 22 if FIXED else 16               # tools/community-library/build_index.py
APP_MAX = 22                                    # eaveluxos/schedule.py since 4.23


def library_check(pattern):
    m = pattern.get("custom_mode", 0)
    return [] if 0 <= m <= LIBRARY_MAX else [f"'custom_mode' must be a whole number 0-{LIBRARY_MAX}"]


juggle = {"label": "Bouncing candy", "colors": ["#FF0000", "#FFFFFF"], "counts": [3, 3], "custom_mode": 22}
assert 0 <= juggle["custom_mode"] <= APP_MAX     # the app saves it fine
errs = library_check(juggle)
print("OK: the library accepts it" if not errs else f"BUG: the library refuses it: {errs[0]}")
