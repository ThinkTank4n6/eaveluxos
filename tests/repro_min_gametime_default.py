"""4.28 repro: Chris's teams were saved before 4.25 with no "during", so
turning on Use game-time lights lit the Eagles colors all evening instead
of from 15 minutes before the game to 15 after.
Prints BUG, or OK with --fixed (when such a team gets game time)."""
import sys
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.test_gameday import SECRETS, settings
from eaveluxos.schedule import build_config

d = date(2026, 12, 14)
gd = {"enabled": True, "teams": [{"league": "nfl", "team": "phi", "name": "Eagles", "effect": "eagles"}]}
c = build_config(settings(gameday=gd), SECRETS, gamedates={"nfl-phi": {d}}, gamestarts={"nfl-phi": {d: "20:15"}})
names = [r.name for r in c.schedule.rules if "Eagles" in r.name]
ok = names == ["Eagles game time (8:00 PM)"]
if "--fixed" in sys.argv:
    print("OK: game time, from 8:00 PM" if ok else f"BUG: still {names}")
else:
    print(f"BUG: all evening ({names})" if not ok else "OK: (already fixed)")
