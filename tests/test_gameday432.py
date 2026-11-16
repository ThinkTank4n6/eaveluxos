# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""4.3.2: game-day lights review fixes (tests/repro_gameday_seasontype.py is #1)."""
import json
import tempfile
import threading
import time
import unittest
from datetime import timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from eaveluxos import gameday
from eaveluxos.gameday import GameDays, parse_dates

NY = ZoneInfo("America/New_York")
FLYERS = [{"league": "nhl", "team": "phi", "name": "Flyers"}]


def ev(date, status="STATUS_SCHEDULED", time_valid=None):
    c = {"date": date, "status": {"type": {"name": status}}}
    if time_valid is not None:
        c["timeValid"] = time_valid
    return {"date": date, "competitions": [c]}


def answer(*events):
    return json.dumps({"events": list(events)}).encode()


class Dates(unittest.TestCase):
    def test_2_postponed_and_canceled_games_light_nothing(self):
        raw = answer(ev("2026-12-01T00:00Z"), ev("2026-12-03T00:00Z", "STATUS_POSTPONED"),
                     ev("2026-12-05T00:00Z", "STATUS_CANCELED"))
        self.assertEqual(parse_dates(raw, NY), ["2026-11-30"])

    def test_3_after_midnight_counts_for_that_evening(self):
        # 10:30 PM in Los Angeles is 1:30 AM in Philadelphia: Saturday night's game.
        self.assertEqual(parse_dates(answer(ev("2026-12-06T06:30Z")), NY), ["2026-12-05"])
        # A time ESPN hasn't set yet: its own day, whatever the placeholder hour.
        self.assertEqual(parse_dates(answer(ev("2026-12-28T05:00Z", time_valid=False)), ZoneInfo("America/Los_Angeles")),
                         ["2026-12-28"])


class Refresh(unittest.TestCase):
    def setUp(self):
        self.g = GameDays(Path(tempfile.mkdtemp()), fetch=self.fetch)
        self.answers = {"2": answer(ev("2026-12-01T00:00Z")), "3": answer()}
        self.urls = []

    def fetch(self, url):
        self.urls.append(url)
        return self.answers[url.rsplit("=", 1)[1]]

    def test_1_each_season_asked_for_by_name(self):
        self.g.refresh(FLYERS, NY)
        self.assertTrue(all("seasontype=" in u for u in self.urls), self.urls)
        self.assertEqual(sorted(u.rsplit("=", 1)[1] for u in self.urls), ["2", "3"])

    def test_4_an_empty_answer_keeps_the_known_nights(self):
        self.g.refresh(FLYERS, NY)
        self.answers["2"] = answer()
        self.g.refresh(FLYERS, NY)
        c = self.g.cache["nhl-phi"]
        self.assertEqual(c["dates"], ["2026-11-30"])
        self.assertIn("kept", c["error"])

    def test_5_one_refresh_at_a_time(self):
        slow = threading.Event()
        inside, most = [0], [0]

        def fetch(url):
            inside[0] += 1
            most[0] = max(most[0], inside[0])
            time.sleep(0.05)
            inside[0] -= 1
            return self.answers[url.rsplit("=", 1)[1]]
        self.g.fetch = fetch
        ts = [threading.Thread(target=self.g.refresh, args=(FLYERS, NY)) for _ in range(3)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(most[0], 1)

    def test_6_a_new_time_zone_works_the_dates_out_again(self):
        now = [1000.0]
        self.g.now = lambda: now[0]
        self.g.refresh(FLYERS, NY)
        self.g.next_at = now[0] + gameday.EVERY
        tz = [NY]
        self.g.stop = type("S", (), {"n": 0, "wait": lambda s, t: (setattr(s, "n", s.n + 1) or s.n > 2)})()
        self.urls.clear()
        tz[0] = ZoneInfo("America/Los_Angeles")
        self.g._loop(lambda: FLYERS, lambda: tz[0])
        self.assertTrue(self.urls, "refreshed for the new time zone")
        self.assertEqual(gameday.EVERY, 6 * 3600)


class LateGames433(unittest.TestCase):
    """4.3.3 (tests/repro_scores_late_game.py): the score watcher finds a game
    after midnight on tomorrow's board, but not one a day away."""

    def board(self, *evs):
        return json.dumps({"events": list(evs)}).encode()

    def game(self, when, state="pre"):
        return {"id": "1", "date": when, "status": {"type": {"state": state, "shortDetail": ""}},
                "competitions": [{"competitors": [{"team": {"abbreviation": "PHI"}, "score": "0"},
                                                  {"team": {"abbreviation": "LA"}, "score": "0"}]}]}

    def run_at(self, when):
        from datetime import date, datetime
        from eaveluxos.scores import ScoreWatch
        urls = []
        w = ScoreWatch(lambda *a: None, now=lambda: datetime(2026, 12, 6, 2, tzinfo=timezone.utc).timestamp(),
                       fetch=lambda u: urls.append(u) or (self.board(self.game(when)) if "dates=" in u else self.board()))
        team = {"nhl-phi": {"league": "nhl", "team": "phi", "name": "Flyers", "min_points": 1}}
        w.check(team, {"nhl-phi": {date(2026, 12, 5)}}, date(2026, 12, 5), hour=21)
        return w.summary()["nhl-phi"]["state"], urls, w

    def test_found_tonight(self):
        st, urls, w = self.run_at("2026-12-06T06:30Z")
        self.assertEqual(st, "pre")
        self.assertTrue(urls[1].endswith("dates=20261206"))
        self.assertLess(w.next_at["nhl"] - w.now(), 15 * 60 + 1)

    def test_not_a_game_a_day_away(self):
        st, *_ = self.run_at("2026-12-07T00:00Z")
        self.assertEqual(st, "missing")


class Screen(unittest.TestCase):
    def test_7_says_why_nothing_was_checked(self):
        js = (Path(__file__).resolve().parent.parent / "eaveluxos" / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn("Not checked while this team has neither game-day lights nor celebrations on", js)


if __name__ == "__main__":
    unittest.main()
