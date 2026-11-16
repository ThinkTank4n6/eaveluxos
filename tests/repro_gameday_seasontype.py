# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Review #1 (4.3.1, game-day lights): the regular season was asked for with
no season type, so ESPN answered with whatever it calls current. In the
preseason that is the preseason: the season opener isn't known until ESPN
flips over (often the day before), and preseason games light up instead.
ESPN is mocked here. Run: python3 tests/repro_gameday_seasontype.py"""
import json, sys, tempfile
from pathlib import Path
from datetime import timezone
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from eaveluxos.gameday import GameDays

ev = lambda *ds: json.dumps({"events": [{"date": d + "T23:00Z"} for d in ds]}).encode()
ESPN = {"": ev("2026-09-27", "2026-10-01"),               # its "current" type in September: preseason
        "?seasontype=2": ev("2026-10-08", "2026-10-11"),  # the regular season, opener Oct 8
        "?seasontype=3": ev()}                            # no playoff games yet
g = GameDays(Path(tempfile.mkdtemp()), fetch=lambda url: ESPN[url[url.find("?"):] if "?" in url else ""])
g.refresh([{"league": "nhl", "team": "phi", "name": "Flyers"}], timezone.utc)
dates = g.cache["nhl-phi"]["dates"]
print("OK: opener known" if "2026-10-08" in dates and "2026-09-27" not in dates
      else f"BUG: lights on {dates}, opener Oct 8 missing")
