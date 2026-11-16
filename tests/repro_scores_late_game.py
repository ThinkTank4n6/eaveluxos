# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Review #1 (4.3.2, ESPN): a game starting after midnight counts for the
evening before (4.3.2), but on that evening the score watcher only asked
ESPN's board for that day, which doesn't list the game, so the panel said
"Not on ESPN's scoreboard today" all evening. ESPN is mocked here.
Run: python3 tests/repro_scores_late_game.py"""
import json, sys
from datetime import date, datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from eaveluxos.scores import ScoreWatch

game = {"id": "1", "date": "2026-12-06T06:30Z", "status": {"type": {"state": "pre", "shortDetail": "1:30 AM"}},
        "competitions": [{"competitors": [{"team": {"abbreviation": "PHI"}, "score": "0"},
                                          {"team": {"abbreviation": "LA"}, "score": "0"}]}]}
board = lambda *evs: json.dumps({"events": list(evs)}).encode()
w = ScoreWatch(lambda *a: None, fetch=lambda url: board(game) if "dates=20261206" in url else board(),
               now=lambda: datetime(2026, 12, 6, 2, 0, tzinfo=timezone.utc).timestamp())   # 9 PM Dec 5 in Philadelphia
team = {"nhl-phi": {"league": "nhl", "team": "phi", "name": "Flyers", "min_points": 1}}
w.check(team, {"nhl-phi": {date(2026, 12, 5)}}, date(2026, 12, 5), hour=21)
st = w.summary()["nhl-phi"]["state"]
print("OK: tonight's late game is found" if st == "pre" else f"BUG: the panel says the team is {st} on ESPN's board")
