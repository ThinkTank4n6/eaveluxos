"""4.21 review #1, standalone: the winning goal's own celebration flash made the win lights
skip, though a flash goes back to whatever is chosen under it. Run with --fixed for the fix."""
import sys
FIXED = "--fixed" in sys.argv
def win_lights(showing, flash_kind):                      # celebrate_win's check, as written first
    if showing in ("alert", "music"):
        return "skipped: a weather warning or a music show"
    if showing == "flash" and (not FIXED or flash_kind == "security"):
        return "skipped: something more important is showing"
    return "win lights chosen (they show when the flash ends)"
# a hockey game: an empty-net goal with 20 seconds left, the final horn while its flash still runs
events = [("score", "flash for 30 s"), ("game over: win", None)]
showing, flash_kind = "schedule", None
for what, _ in events:
    if what == "score":
        showing, flash_kind = "flash", "score"
    else:
        result = win_lights(showing, flash_kind)
print(f"BUG: {result}" if result.startswith("skipped") else f"OK: {result}")
sys.exit(1 if result.startswith("skipped") else 0)
