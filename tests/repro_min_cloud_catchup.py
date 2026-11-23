"""Standalone (no app, no network): the 4.16.6 "changed outside" check, Nov 22 4:48 PM.
Run: python3 tests/repro_min_cloud_catchup.py [--fixed]"""
import sys
FIXED, SENT = "--fixed" in sys.argv, (1, 19)          # lights on (1), pattern 19, sent over the home network
seen, moving, alarms = None, None, []
# what the cloud reported at each 5-minute read-back: stale until it catches up
for report in [(0, 14), (0, 14), (1, 19), (1, 19), (1, 19)]:
    caught_up = FIXED and report == SENT              # the fix: matching what was sent is never "outside"
    if seen is None or seen == report or caught_up:
        seen, moving = report, None                   # the new baseline
    elif moving == report:                            # the same new report twice: act on it
        alarms.append(report)
        seen, moving = report, None
    else:
        moving = report                               # look again in a minute
if alarms:
    print(f"BUG: 'Trimlight was changed outside this app' for {alarms[0]}, which is what this app sent")
else:
    print("OK: the cloud catching up with a home-network send isn't a change from outside")
sys.exit(1 if alarms else 0)
