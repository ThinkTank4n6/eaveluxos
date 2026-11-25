"""4.25 review #1: an owner asked for the team colors only while the game is
on. Game-day lights ran from sunset to 11 PM on every game date: a 7:05 PM
first pitch on Aug 1 lit the house from 8:14 PM sunset... and an 8:20 PM
kick-off from 4:40 PM. Standalone; prints BUG, or OK with --fixed."""
import sys

FIXED = "--fixed" in sys.argv
SUNSET, OFF = 16 * 60 + 40, 23 * 60                  # Dec 6: 4:40 PM, 11:00 PM
kickoff, longest, before, after = 20 * 60 + 20, 240, 15, 15


def window():
    if FIXED:                                        # 4.25: game time
        return kickoff - before, kickoff + longest + after
    return SUNSET, OFF                               # game-day lights: all evening


on, off = window()
hm = lambda m: f"{m // 60 % 24}:{m % 60:02d}"
early = kickoff - on
print(f"OK: {hm(on)} to {hm(off)} (ends sooner at the final)" if early <= before
      else f"BUG: team colors from {hm(on)}, {early} minutes before kick-off")
