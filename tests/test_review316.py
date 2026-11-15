# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""3.16.1: fixes from the code review of 3.16.0, one test (or more) each."""
import json
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

from eaveluxos import scores
from eaveluxos.controller import Controller
from eaveluxos.schedule import Location, build_config
from tests.test_controller import FakeAPI, FakeWeather
from tests.test_triggers316 import NY, board, nws, settings

ROOT = Path(__file__).resolve().parent.parent
WA = {"enabled": True, "groups": ["winter", "tornado"], "effect": "severe", "turn_on": False}


class Base(unittest.TestCase):
    def make(self, data_dir=None, **extra):
        self.clock = [datetime(2026, 11, 20, 19, 0, tzinfo=NY)]
        orig = Location.now
        self.addCleanup(setattr, Location, "now", orig)
        Location.now = lambda loc: self.clock[0]
        self.cfg = build_config(settings(**extra), {"client_id": "x", "client_secret": "y"})
        self.api = FakeAPI()
        c = Controller(self.cfg, self.api, weather=FakeWeather(), data_dir=data_dir)
        if c.wx_alerts:
            self.feed = nws("Winter Storm Warning")
            c.wx_alerts.fetch = lambda url: self.feed
            c.wx_alerts.refresh(force=True)
        return c

    def at(self, c, h, m=0, s=0):
        self.clock[0] = datetime(2026, 11, 20, h, m, s, tzinfo=NY)
        c.next_try = 0
        c.tick()
        return c._target()

    def refeed(self, c, feed):
        self.feed = feed
        c.wx_alerts.refresh(force=True)
        c._prune_dismissed(c.wx_alerts)


class FlashOrderTests(Base):
    # 1
    def test_short_alert_resumes_the_alarm_it_interrupted(self):
        c = self.make()
        self.at(c, 19)
        eff = self.cfg.effects
        self.assertTrue(c.start_flash(seconds=600, effect=eff["christmas"], label="Alarm", kind="alert"))
        self.assertTrue(c.start_flash(seconds=15, effect=eff["snowfall"], label="Package", kind="alert"))
        self.assertEqual(c._target().source, "Package")
        self.assertEqual(self.at(c, 19, 0, 20).source, "Alarm")          # back to the alarm, not the schedule
        self.assertEqual(self.at(c, 19, 10, 1).reason, "schedule")       # and it ends when it was due to
        c.stop_flash()
        self.assertEqual(c.flash_held, [])

    def test_an_urgent_alarm_can_not_be_replaced_by_a_lower_alert(self):
        c = self.make()
        self.at(c, 19)
        c.start_flash(seconds=600, effect=self.cfg.effects["christmas"], label="Alarm", kind="urgent")
        self.assertFalse(c.start_flash(seconds=15, effect=self.cfg.effects["snowfall"], label="Package", kind="alert"))
        self.assertEqual(c._target().source, "Alarm")

    # 2
    def test_score_never_cuts_a_security_flash_even_when_lights_off_is_allowed(self):
        c = self.make()
        self.at(c, 19)
        c.start_flash(10)
        self.assertFalse(c.start_flash(seconds=15, effect=self.cfg.effects["christmas"], kind="score", only_if_on=False))
        self.assertEqual(c._target().source, "Security flash")
        self.assertEqual((c.flash["until"] - self.clock[0]).total_seconds(), 600)

    # 3
    def test_flash_during_a_music_show(self):
        c = self.make()
        self.at(c, 19)
        c.start_music(60)
        self.at(c, 19, 1)
        n = len(self.api.calls)
        self.assertFalse(c.start_flash(seconds=15, effect=self.cfg.effects["christmas"], label="Package", kind="alert"))
        self.assertEqual(self.at(c, 19, 2).reason, "music")
        self.assertEqual(self.api.calls[n:], [], "nothing is sent, so music mode carries on")
        self.assertTrue(c.start_flash(5))                                   # the security flash ends the show
        self.assertIsNone(c.music)
        self.assertEqual(self.at(c, 19, 8).reason, "schedule", "afterward the schedule, not the flash pattern")

    # 4
    def test_weather_warning_beats_scores_and_alerts_but_not_urgent(self):
        c = self.make(weather_alerts=WA)
        self.assertEqual(self.at(c, 19).reason, "alert")
        self.assertFalse(c.start_flash(seconds=15, effect=self.cfg.effects["christmas"], kind="score", only_if_on=True))
        self.assertFalse(c.start_flash(seconds=15, effect=self.cfg.effects["christmas"], kind="alert"))
        self.assertEqual(self.at(c, 19, 1).reason, "alert")
        self.assertTrue(c.start_flash(seconds=60, effect=self.cfg.effects["christmas"], label="Alarm", kind="urgent"))
        self.assertEqual(self.at(c, 19, 1, 30).reason, "flash")
        self.assertEqual(self.at(c, 19, 2, 30).reason, "alert")


class AlertTests(Base):
    # 6
    def test_dismissal_sticks_through_updates_and_ends_with_the_warning(self):
        c = self.make(weather_alerts=WA)
        self.at(c, 19)
        self.assertTrue(c.dismiss_alert())
        self.refeed(c, nws("Winter Storm Warning", ends="2026-11-21T09:00:00-05:00"))   # NWS update: new id
        self.assertEqual(self.at(c, 19, 1).reason, "schedule")
        self.refeed(c, nws("Winter Storm Warning", "Tornado Warning"))                 # a different warning shows
        self.assertEqual(self.at(c, 19, 2).source, "Tornado Warning")
        self.refeed(c, nws())                                                            # all over
        self.assertEqual(c.alert_dismissed, {})
        self.refeed(c, nws("Winter Storm Warning"))                                      # the next storm shows again
        self.assertEqual(self.at(c, 19, 3).source, "Winter Storm Warning")

    def test_failed_check_does_not_forget_a_dismissal(self):
        c = self.make(weather_alerts=WA)
        self.at(c, 19)
        c.dismiss_alert()
        c.wx_alerts.updated = 0                                        # no good answer
        c._prune_dismissed(c.wx_alerts)
        self.assertIn("winter storm warning", c.alert_dismissed)

    # 7
    def test_changing_alert_settings_keeps_the_alert_showing(self):
        c = self.make(weather_alerts=WA)
        self.at(c, 19)
        c.wx_alerts.fetch = lambda url: self.fail("no new check needed")
        c.reload(build_config(settings(weather_alerts={**WA, "effect": "christmas"}), {"client_id": "x", "client_secret": "y"}))
        t = c._target()
        self.assertEqual((t.reason, t.effect.key), ("alert", "christmas"))
        c.reload(build_config(settings(weather_alerts={**WA, "groups": ["winter"]}), {"client_id": "x", "client_secret": "y"}))
        self.assertEqual(c._target().reason, "alert")                  # re-sorted from the last answer
        c.reload(build_config(settings(weather_alerts={**WA, "groups": ["tornado"]}), {"client_id": "x", "client_secret": "y"}))
        self.assertNotEqual(c._target().reason, "alert")

    # 8
    def test_off_by_hand_during_an_alert_turns_the_lights_off(self):
        c = self.make(weather_alerts={**WA, "turn_on": True})
        self.assertEqual(self.at(c, 19).reason, "alert")
        c.manual(False)
        t = self.at(c, 19, 1)
        self.assertEqual((t.reason, t.on), ("manual", False))
        self.assertIn("winter storm warning", c.alert_dismissed)

    # 9
    def test_dismissal_survives_a_restart_and_old_ones_expire(self):
        d = tempfile.mkdtemp()
        c = self.make(data_dir=d, weather_alerts=WA)
        self.at(c, 19)
        c.dismiss_alert()
        c2 = self.make(data_dir=d, weather_alerts=WA)
        self.assertEqual(self.at(c2, 19, 1).reason, "schedule")
        Path(d, "alert-dismissed.json").write_text(json.dumps({"winter storm warning": 1000.0}))   # long ago
        c3 = self.make(data_dir=d, weather_alerts=WA)
        self.assertEqual(self.at(c3, 19, 2).reason, "alert")


class ScoreReviewTests(unittest.TestCase):
    TEAM = {"key": "mlb-phi", "name": "Phillies", "league": "mlb", "team": "phi", "effect": "e", "seconds": 15, "min_points": 1}
    DAY = date(2026, 11, 22)

    def setUp(self):
        self.parties, self.t, self.urls = [], [1000.0], []
        self.boards = {}
        self.w = scores.ScoreWatch(lambda team, pts, g: self.parties.append(pts), fetch=self.fetch, now=lambda: self.t[0])

    def fetch(self, url):
        self.urls.append(url)
        return self.boards.get(url.split("?")[1] if "?" in url else "", b'{"events": []}')

    def teams(self, key="mlb-phi"):
        return {key: {k: v for k, v in self.TEAM.items() if k != "key"}}

    def look(self, today=None, hour=None, dt=60):
        self.t[0] += dt
        self.w.check(self.teams(), {"mlb-phi": {self.DAY}}, today or self.DAY, force=True, hour=hour)

    @staticmethod
    def two(g1, g2):
        return json.dumps({"events": json.loads(g1)["events"] + json.loads(g2)["events"]}).encode()

    # 5
    def test_doubleheader_follows_game_two(self):
        self.boards[""] = self.two(board("post", 3, 1, gid="1"), board("in", 0, 0, gid="2"))
        self.look()
        self.boards[""] = self.two(board("post", 3, 1, gid="1"), board("in", 2, 0, gid="2"))
        self.look()
        self.assertEqual(self.parties, [2])
        self.assertEqual(self.w.next_at["mlb"] - self.t[0], scores.LIVE_EVERY)

    # 10
    def test_team_missing_from_the_scoreboard_is_reported(self):
        self.boards[""] = board("in", 0, 0)
        self.w.check({"mlb-xyz": {**self.teams()["mlb-phi"], "team": "xyz"}}, {"mlb-xyz": {self.DAY}}, self.DAY, force=True)
        self.assertEqual(self.w.summary()["mlb-xyz"]["state"], "missing")

    # 11
    def test_last_nights_game_only_until_4_am_and_slow_after_final(self):
        self.boards[""] = board("post", 5, 2)
        self.look(today=date(2026, 11, 23), hour=2)
        self.assertEqual(len(self.urls), 1)
        self.assertEqual(self.w.next_at["mlb"] - self.t[0], scores.FINAL_EVERY)
        self.look(today=date(2026, 11, 23), hour=9)
        self.assertEqual(len(self.urls), 1, "not followed the next morning")

    # 12
    def test_game_past_midnight_is_found_on_its_own_day(self):
        self.boards[""] = board("in", 1, 0)
        self.look(hour=23)
        self.boards[""] = b'{"events": []}'                              # after midnight ESPN moved on
        self.boards["dates=20261122"] = board("in", 3, 0)
        self.look(today=date(2026, 11, 23), hour=0)
        self.assertEqual(self.parties, [2])
        self.assertIn("dates=20261122", self.urls[-1])

    # 13
    def test_a_score_taken_back_and_restored_is_celebrated_once(self):
        self.boards[""] = board("in", 0, 0)
        self.look()
        for s in (7, 0, 7):
            self.boards[""] = board("in", s, 0)
            self.look()
        self.assertEqual(self.parties, [7])

    # 16 (memory)
    def test_old_games_are_forgotten(self):
        for i in range(scores.KEEP_GAMES + 50):
            self.boards[""] = board("in", 0, 0, gid=str(i))
            self.look(dt=1)
        self.assertLessEqual(len(self.w.last), scores.KEEP_GAMES)
        self.assertLessEqual(len(self.w.high), scores.KEEP_GAMES)


class SourceTests(unittest.TestCase):
    # 15
    def test_viewers_do_not_get_the_dismiss_button(self):
        js = (ROOT / "eaveluxos" / "static" / "app.js").read_text(encoding="utf-8")
        line = next(ln for ln in js.splitlines() if 'data-act="dismiss_alert"' in ln)
        self.assertIn("role() !== 'viewer'", line)

    # 16 (docs)
    def test_manual_explains_zones_with_two_controllers(self):
        self.assertIn("more than one controller", (ROOT / "MANUAL.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
