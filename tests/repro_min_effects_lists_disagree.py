"""4.22.4 review #1: after deleting a pattern with Lightning, the controller's
two effects lists disagreed (03 01 14 | 01 01 15): the first still named #20.
4.22 required them to agree, so the Effect choice vanished. Standalone; prints
BUG, or OK with --fixed."""
import sys

FIXED = "--fixed" in sys.argv
tail = bytes.fromhex("030114010115")         # 03 | 1: [20] | 1 pair: (Snowflake, 21)


def readable(d):
    n = d[1]
    light = list(d[2:2 + n])
    m = d[2 + n]
    pairs = [(d[3 + n + 2 * i], d[4 + n + 2 * i]) for i in range(m)]
    if not FIXED and light != [x for k, x in pairs if k == 0]:
        return None                          # 4.22.0-4.22.3: must agree
    return pairs


pairs = readable(tail)
print(f"OK: Effect choice shown; pairs {pairs}" if pairs is not None else "BUG: Effect choice hidden on this controller")
