"""Standalone (no app, no network): the "changed outside this app" check after
a home-network send, Chris's log Nov 27 (lights on 4:48 PM, "changed outside"
4:54 PM; every send sent again about 6 minutes 40 seconds later).
The cloud reports the pattern sent over the home network its own way: an id
of -1, and all 30 of the controller's slots, the empty ones with a count of 0.
Run: python3 tests/repro_min_lan_resend.py [--fixed]"""
import sys

FIXED = "--fixed" in sys.argv
SENT = {"category": 1, "mode": 1, "speed": 60, "brightness": 220,
        "pixels": [{"index": 0, "count": 4, "color": 0xFF0000}, {"index": 1, "count": 4, "color": 0x008900},
                   {"index": 2, "count": 4, "color": 0xFFFFFF}]}
REPORT = {"id": -1, **SENT, "pixels": SENT["pixels"] + [{"index": i, "count": 0, "color": 0, "disable": True}
                                                         for i in range(3, 30)]}


def runs(px):
    out = []
    for p in sorted(px, key=lambda p: p["index"]):
        if FIXED and not p.get("count"):
            continue                              # the fix: an empty slot shows nothing
        k = (p.get("color"), bool(p.get("disable")))
        if out and out[-1][0] == k:
            out[-1][1] += p.get("count", 0)
        else:
            out.append([k, p.get("count", 0)])
    return out


def same(a, b):
    return all(a.get(k) == b.get(k) for k in ("category", "mode", "speed", "brightness")) and runs(a["pixels"]) == runs(b["pixels"])


seen, moving, alarms = None, None, []
for report in ["old", "old", "new", "new", "new"]:        # stale, then the cloud catches up
    cur = {"id": 19, "category": 1} if report == "old" else REPORT
    caught_up = same(cur, SENT)
    if seen is None or seen == report or caught_up:
        seen, moving = report, None
    elif moving == report:
        alarms.append(report)
        seen, moving = report, None
    else:
        moving = report
if alarms:
    print("BUG: 'Trimlight was changed outside this app': the cloud's report of the pattern just sent "
          "wasn't recognized, so it was sent again")
else:
    print("OK: the cloud catching up with a home-network send isn't a change from outside")
sys.exit(1 if alarms else 0)
