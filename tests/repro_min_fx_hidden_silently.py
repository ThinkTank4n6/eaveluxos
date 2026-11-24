"""4.22.6 review #1: on a controller whose effects list wasn't readable,
Local mode quietly left the Effect choice out; the owner saw only Delete
and had no way to tell why or to report it. Standalone; prints BUG, or OK
with --fixed."""
import sys

FIXED = "--fixed" in sys.argv
tail = bytes.fromhex("02ff00003c03000000") + bytes(8)     # no clock: the controller's time not set


def read(d):
    mo = d[-6]
    if not 1 <= mo <= 12:
        return None, ("no clock at the end" if FIXED else None)
    return [], None


def row(name, d):
    fx, why = read(d)
    effect = "Effect: [None v]" if fx is not None else ""
    note = f"  (Lightning and Snowflake unavailable: {why}; Copy details)" if why else ""
    return f"{name} {effect} [Delete]{note}"


r = row("Christmas Day #14", tail)
print(("OK: " if "unavailable" in r else "BUG: no Effect and no reason: ") + r)
