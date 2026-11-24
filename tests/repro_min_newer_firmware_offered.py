"""4.23.1 review #1: a Mac owner's controller (newer firmware, 4.17.79) sends
0F before its effects lists where Chris's sends 03; the reader required 03,
so Lightning and Snowflake were hidden on it. Standalone; prints BUG, or OK
with --fixed."""
import sys

FIXED = "--fixed" in sys.argv
tail = bytes.fromhex("01ff00003c0f0000001a0b1807191602")   # the end of his backup, Nov 24 7:25 AM


def readable(d):
    offered, n, m, zero = d[-11], d[-10], d[-9], d[-8]
    if (n, m, zero) != (0, 0, 0):
        return None
    if FIXED:
        return [] if offered & 0x03 == 0x03 else None      # Lightning and Snowflake among those offered
    return [] if offered == 0x03 else None                  # 4.22-4.23.0: exactly 03


r = readable(tail)
print("OK: Effect choice shown (none set yet)" if r is not None else "BUG: Effect choice hidden on the newer firmware")
