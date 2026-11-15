# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""3.16: alert flashes with their own pattern, length and zone; severe
weather alerts from NWS; score celebrations from ESPN's scoreboard."""
import copy
import json
import unittest
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from eaveluxos import scores
from eaveluxos.controller import Controller
from eaveluxos.schedule import ConfigError, Effect, Location, build_config
from eaveluxos.store import DEFAULT_SETTINGS
from eaveluxos.triggers import (ALERT_STALE, AlertWatch, MAX_SLOTS, PRESETS, build_alert_settings,
                                flash_effect, parse_alerts, zone_payload)
from tests.test_controller import FakeAPI, FakeWeather

NY = ZoneInfo("America/New_York")


def settings(**extra):
    s = copy.deepcopy(DEFAULT_SETTINGS)
    s["location"].update(latitude=39.95, longitude=-75.17)
    s["rules"] = [{"name": "Night", "on": "18:00", "off": "23:00", "effect": "warm_white"}]
    s.update(extra)
    return s


def custom(colors, counts, mode=0):
    return Effect.from_config("x", {"colors": colors, "counts": counts, "custom_mode": mode})


def expand(pixels):
    """Pixels -> one entry per bulb: color int, or None when off ("X")."""
    out = []
    for p in pixels:
        out += [None if p["disable"] else p["color"]] * p["count"]
    return out


class ZoneTests(unittest.TestCase):
    def test_zone_lights_only_its_bulbs(self):
        pl = zone_payload(custom(["#00FF00"], [1]).payload, 41, 80, 300)
        bulbs = expand(pl["pixels"])
        self.assertEqual(len(bulbs), 300)              # covers the whole address space: never repeats
        self.assertTrue(all(b is None for b in bulbs[:40] + bulbs[80:]))
        self.assertTrue(all(b == 0x00FF00 for b in bulbs[40:80]))
        self.assertTrue(all(p["count"] <= 90 for p in pl["pixels"]))
        self.assertLessEqual(len(pl["pixels"]), MAX_SLOTS)

    def test_pattern_repeats_inside_the_zone_and_keeps_its_motion(self):
        pl = zone_payload(custom(["#FF0000", "#FFFFFF"], [3, 3], mode=1).payload, 1, 24, 100)
        bulbs = expand(pl["pixels"])
        self.assertEqual(bulbs[:24], ([0xFF0000] * 3 + [0xFFFFFF] * 3) * 4)
        self.assertTrue(all(b is None for b in bulbs[24:]))
        self.assertEqual(pl["mode"], 1)

    def test_too_many_repeats_are_stretched_to_fit_30_slots(self):
        pl = zone_payload(custom(["#FF0000", "#00C000", "#FFFFFF"], [2, 2, 2]).payload, 101, 600, 900)
        self.assertLessEqual(len(pl["pixels"]), MAX_SLOTS)
        bulbs = expand(pl["pixels"])
        self.assertEqual(len(bulbs), 900)
        self.assertEqual({b for b in bulbs[100:600]}, {0xFF0000, 0x00C000, 0xFFFFFF})
        self.assertTrue(all(b is None for b in bulbs[:100] + bulbs[600:]))

    def test_refusals(self):
        builtin = Effect.from_config("b", {"builtin": 5})
        with self.assertRaises(ValueError):
            zone_payload(builtin.payload, 1, 10, 100)
        with self.assertRaises(ValueError):
            zone_payload(custom(["#FF0000"], [1]).payload, 90, 120, 100)   # past the last bulb
        many = custom(["#FF0000", "#00FF00"] * 15, [1] * 30)
        with self.assertRaises(ValueError):                                # 30 colors + dark bulbs on both sides
            zone_payload(many.payload, 50, 60, 100)


class FlashEffectTests(unittest.TestCase):
    def setUp(self):
        self.cfg = build_config(settings(), {"client_id": "x", "client_secret": "y"})
        self.zones = [{"name": "Front porch", "start": 11, "end": 30}]

    def test_alert_pattern_color_and_own_pattern(self):
        e = flash_effect(self.cfg.effects, None, effect="Package")
        self.assertEqual(e.label, PRESETS["package"]["label"])
        self.assertEqual(e.payload["pixels"][0]["color"], 0x00FF00)
        self.assertEqual(flash_effect(self.cfg.effects, None, color="#ff0000").payload["pixels"][0]["color"], 0xFF0000)
        self.assertIs(flash_effect(self.cfg.effects, None, effect="Warm white"), self.cfg.effects["warm_white"])
        self.assertIs(flash_effect(self.cfg.effects, None, effect="christmas"), self.cfg.effects["christmas"])
        self.assertIsNone(flash_effect(self.cfg.effects, None))           # nothing named: the security pattern

    def test_zone_by_name_any_case(self):
        e = flash_effect(self.cfg.effects, None, effect="alarm", zone="front PORCH", zones=self.zones, total=100)
        bulbs = expand(e.payload["pixels"])
        self.assertTrue(all(b == 0xFF0000 for b in bulbs[10:30]))
        self.assertIn("Front porch", e.label)

    def test_mistakes_explain_themselves(self):
        for kw in ({"effect": "nope"}, {"color": "green"},
                   {"effect": "alarm", "zone": "Garage", "zones": self.zones, "total": 100},
                   {"effect": "alarm", "zone": "Front porch", "zones": self.zones, "total": None},
                   {"zone": "Front porch", "zones": self.zones, "total": 100}):
            with self.subTest(kw=kw), self.assertRaises(ValueError):
                flash_effect(self.cfg.effects, None, **kw)


class ControllerFlashTests(unittest.TestCase):
    def setUp(self):
        self.cfg = build_config(settings(), {"client_id": "x", "client_secret": "y"})
        self.clock = [datetime(2026, 11, 20, 19, 0, tzinfo=NY)]
        self._orig = Location.now
        Location.now = lambda loc: self.clock[0]
        self.api = FakeAPI()
        self.c = Controller(self.cfg, self.api, weather=FakeWeather())

    def tearDown(self):
        Location.now = self._orig

    def at(self, h, m=0, s=0):
        self.clock[0] = datetime(2026, 11, 20, h, m, s, tzinfo=NY)
        self.c.next_try = 0
        self.c.tick()
        return self.c._target()

    def test_alert_flash_for_seconds_then_back(self):
        self.at(19)
        eff = flash_effect(self.cfg.effects, None, effect="package")
        self.assertTrue(self.c.start_flash(seconds=15, effect=eff, label="Package at the door", kind="alert"))
        t = self.c._target()
        self.assertEqual((t.reason, t.source, t.effect.label), ("flash", "Package at the door", eff.label))
        self.assertEqual(self.api.calls[-1][1], PRESETS["package"]["custom_mode"])
        self.assertEqual(self.at(19, 0, 10).reason, "flash")
        t = self.at(19, 0, 16)
        self.assertEqual((t.reason, t.effect.key), ("schedule", "warm_white"))
        self.assertEqual(self.c.status()["flash"]["label"], None)

    def test_security_flash_still_works_without_a_pattern_named(self):
        self.at(19)
        self.c.start_flash(2)
        t = self.c._target()
        self.assertEqual((t.source, t.effect.key), ("Security flash", "security_white"))
        self.assertEqual(self.at(19, 2, 1).reason, "schedule")

    def test_seconds_are_kept_in_range(self):
        self.at(19)
        self.c.start_flash(seconds=1, effect=self.cfg.effects["christmas"])
        self.assertEqual((self.c.flash["until"] - self.clock[0]).total_seconds(), 5)

    def test_only_if_on_skips_daylight_and_music(self):
        self.at(12)
        self.assertFalse(self.c.start_flash(seconds=15, effect=self.cfg.effects["christmas"], kind="score", only_if_on=True))
        self.assertIsNone(self.c.flash)
        self.at(19)
        self.c.start_music(30)
        self.assertFalse(self.c.start_flash(seconds=15, effect=self.cfg.effects["christmas"], kind="score", only_if_on=True))
        self.c.stop_music()
        self.assertTrue(self.c.start_flash(seconds=15, effect=self.cfg.effects["christmas"], kind="score", only_if_on=True))

    def test_a_score_does_not_cut_a_security_flash_short(self):
        self.at(19)
        self.c.start_flash(5)
        self.assertFalse(self.c.start_flash(seconds=15, effect=self.cfg.effects["christmas"], kind="score", only_if_on=True))
        self.assertEqual(self.c._target().source, "Security flash")

    def test_loop_wakes_when_a_short_flash_ends(self):
        """The loop sleeps only until the flash ends, not a full interval."""
        import threading
        import time
        self.cfg.interval = 3600
        real = [datetime.now(NY)]
        Location.now = lambda loc: datetime.now(NY)
        th = threading.Thread(target=self.c.run_forever, daemon=True)
        th.start()
        try:
            time.sleep(0.5)
            self.c.start_flash(seconds=5, effect=self.cfg.effects["christmas"])
            self.assertEqual(self.c._target().reason, "flash")
            deadline = time.time() + 9
            while time.time() < deadline and self.c.flash:
                time.sleep(0.2)
            self.assertIsNone(self.c.flash, "the flash should have ended within seconds")
        finally:
            self.c.stop_event.set()
            th.join(5)
        self.assertFalse(th.is_alive(), "stopping must not wait out the interval")
        del real


def nws(*events, ends="2026-11-20T23:00:00-05:00", status="Actual"):
    return {"features": [{"properties": {"id": f"urn:{e}:{ends}", "event": e, "headline": f"{e} for Delaware County",
                                         "ends": ends, "status": status, "messageType": "Alert"}}
                         for i, e in enumerate(events)]}


class WeatherAlertTests(unittest.TestCase):
    def test_parse_keeps_chosen_warnings_only(self):
        found = parse_alerts(nws("Tornado Warning", "Tornado Watch", "Winter Storm Warning", "Flood Advisory"), ["tornado", "storm"])
        self.assertEqual([a["event"] for a in found], ["Tornado Warning"])
        self.assertEqual(parse_alerts(nws("Tornado Warning", status="Test"), ["tornado"]), [])
        self.assertEqual(parse_alerts({"weird": 1}, ["tornado"]), [])
        self.assertEqual(parse_alerts(None, ["tornado"]), [])

    def test_settings_checked(self):
        eff = build_config(settings(), {"client_id": "x", "client_secret": "y"}).effects
        self.assertFalse(build_alert_settings({}, eff)["enabled"])
        a = build_alert_settings({"weather_alerts": {"enabled": True, "groups": ["winter"], "effect": "severe"}}, eff)
        self.assertEqual((a["enabled"], a["groups"], a["turn_on"]), (True, ["winter"], False))
        for bad in ({"groups": ["meteor"]}, {"effect": "missing"}, "yes"):
            with self.subTest(bad=bad), self.assertRaises(ConfigError):
                build_alert_settings({"weather_alerts": bad}, eff)

    def make(self, turn_on=False):
        s = settings(weather_alerts={"enabled": True, "groups": ["tornado", "winter"], "effect": "severe", "turn_on": turn_on})
        cfg = build_config(s, {"client_id": "x", "client_secret": "y"})
        self.clock = [datetime(2026, 11, 20, 19, 0, tzinfo=NY)]
        self._orig = Location.now
        self.addCleanup(setattr, Location, "now", self._orig)
        Location.now = lambda loc: self.clock[0]
        self.feed = nws("Winter Storm Warning")
        c = Controller(cfg, FakeAPI(), weather=FakeWeather())
        c.wx_alerts.fetch = lambda url: self.feed
        c.wx_alerts.refresh(force=True)
        return c

    def at(self, c, h, m=0):
        self.clock[0] = datetime(2026, 11, 20, h, m, tzinfo=NY)
        c.next_try = 0
        c.tick()
        return c._target()

    def test_alert_replaces_lights_while_on_then_ends(self):
        c = self.make()
        t = self.at(c, 19)
        self.assertEqual((t.reason, t.source, t.effect.label), ("alert", "Winter Storm Warning", PRESETS["severe"]["label"]))
        self.assertEqual(c.status()["alert"]["event"], "Winter Storm Warning")
        self.assertFalse(self.at(c, 12).on, "only while the lights are on unless set to turn them on")
        self.feed = nws()
        c.wx_alerts.refresh(force=True)
        self.assertEqual(self.at(c, 19, 5).reason, "schedule")

    def test_turn_on_lights_the_house_in_daytime(self):
        c = self.make(turn_on=True)
        t = self.at(c, 12)
        self.assertTrue(t.on)
        self.assertEqual(t.reason, "alert")

    def test_dismiss_and_ended_and_stale_alerts(self):
        c = self.make()
        self.at(c, 19)
        self.assertTrue(c.dismiss_alert())
        self.assertEqual(self.at(c, 19, 1).reason, "schedule")
        self.assertFalse(c.dismiss_alert())
        self.feed = nws("Tornado Warning")                      # a new warning shows again
        c.wx_alerts.refresh(force=True)
        self.assertEqual(self.at(c, 19, 2).source, "Tornado Warning")
        self.feed = nws("Tornado Warning", ends="2026-11-20T19:10:00-05:00")
        c.wx_alerts.refresh(force=True)
        self.assertEqual(self.at(c, 19, 11).reason, "schedule")   # past its end time
        self.feed = nws("Blizzard Warning")
        c.wx_alerts.refresh(force=True)
        self.assertEqual(self.at(c, 19, 12).reason, "alert")
        c.wx_alerts.updated -= ALERT_STALE + 1                   # no good check for over 2 hours
        self.assertEqual(self.at(c, 19, 13).reason, "schedule")

    def test_failed_check_keeps_last_answer_and_says_why(self):
        c = self.make()

        def down(url):
            raise RuntimeError("NWS alerts unreachable: timed out")
        c.wx_alerts.fetch = down
        c.wx_alerts.refresh(force=True)
        self.assertEqual(self.at(c, 19).reason, "alert")
        self.assertIn("unreachable", c.status()["alert"]["error"])

    def test_alert_never_interrupts_a_music_show_and_flash_wins(self):
        c = self.make()
        self.at(c, 19)
        c.start_music(30)
        self.assertEqual(self.at(c, 19, 1).reason, "music")
        c.stop_music()
        c.start_flash(5)
        self.assertEqual(self.at(c, 19, 2).reason, "flash")

    def test_alert_url_is_for_this_point(self):
        seen = []
        w = AlertWatch(39.95001, -75.17004, ["tornado"], fetch=lambda u: seen.append(u) or nws())
        w.refresh(force=True)
        self.assertEqual(seen, ["https://api.weather.gov/alerts/active?point=39.95,-75.17"])
        w.refresh()                                              # not due again for 5 minutes
        self.assertEqual(len(seen), 1)


def board(state, phi, dal, gid="401"):
    return json.dumps({"events": [{"id": gid, "date": "2026-11-22T18:00Z",
                                   "status": {"type": {"state": state, "shortDetail": "Q2 5:00"}},
                                   "competitions": [{"competitors": [
                                       {"homeAway": "home", "score": str(phi), "team": {"abbreviation": "PHI"}},
                                       {"homeAway": "away", "score": str(dal), "team": {"abbreviation": "DAL"}}]}]}]}).encode()


class ScoreTests(unittest.TestCase):
    TEAM = {"nfl-phi": {"name": "Eagles", "league": "nfl", "team": "phi", "effect": "team", "seconds": 15, "min_points": 3,
                        "only_when_on": True}}
    DAY = date(2026, 11, 22)

    def setUp(self):
        self.parties, self.feed, self.t = [], board("pre", 0, 0), [1000.0]
        self.w = scores.ScoreWatch(lambda team, pts, g: self.parties.append((team["name"], pts)),
                                   fetch=lambda url: self.feed, now=lambda: self.t[0])

    def step(self, feed, dt=30):
        self.feed, self.t[0] = feed, self.t[0] + dt
        self.w.check(self.TEAM, {"nfl-phi": {self.DAY}}, self.DAY, force=True)

    def test_celebrates_new_scores_only(self):
        self.step(board("pre", 0, 0))
        self.step(board("in", 0, 0))
        self.step(board("in", 7, 0))                 # touchdown
        self.step(board("in", 7, 7))                 # the other team scored
        self.step(board("in", 10, 7))                # field goal
        self.step(board("post", 17, 7))              # final: never celebrated
        self.assertEqual(self.parties, [("Eagles", 7), ("Eagles", 3)])
        self.assertEqual(self.w.summary()["nfl-phi"]["state"], "post")

    def test_starting_mid_game_does_not_celebrate_the_score_so_far(self):
        self.step(board("in", 14, 3))
        self.assertEqual(self.parties, [])
        self.step(board("in", 21, 3))
        self.assertEqual(self.parties, [("Eagles", 7)])

    def test_small_scores_and_quick_repeats(self):
        self.step(board("in", 0, 0))
        self.step(board("in", 6, 0))                 # touchdown
        self.step(board("in", 7, 0), dt=60)          # extra point: below 3 points
        self.step(board("in", 14, 0), dt=60)         # touchdown
        self.step(board("in", 21, 0), dt=10)         # within the cooldown after it
        self.step(board("in", 28, 0), dt=60)
        self.assertEqual(self.parties, [("Eagles", 6), ("Eagles", 7), ("Eagles", 7)])

    def test_only_game_days_and_polling_pace(self):
        calls = []
        self.w.fetch = lambda url: calls.append(url) or self.feed
        self.w.check(self.TEAM, {"nfl-phi": {date(2026, 11, 30)}}, self.DAY)
        self.assertEqual(calls, [])                  # not a game day: ESPN isn't asked
        self.feed = board("in", 0, 0)
        self.w.check(self.TEAM, {"nfl-phi": {self.DAY}}, self.DAY)
        self.assertEqual(calls, ["https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"])
        self.w.check(self.TEAM, {"nfl-phi": {self.DAY}}, self.DAY)
        self.assertEqual(len(calls), 1)              # live: next look in 20 s
        self.t[0] += scores.LIVE_EVERY
        self.w.check(self.TEAM, {"nfl-phi": {self.DAY}}, self.DAY + timedelta(days=1))   # past midnight
        self.assertEqual(len(calls), 2)

    def test_bad_answers_are_survived(self):
        for raw in (b"not json", b"{}", json.dumps({"events": [{"status": {"type": {"state": "in"}}, "competitions": [
                {"competitors": [{"score": "x", "team": {"abbreviation": "PHI"}}]}]}]}).encode()):
            self.feed = raw
            self.t[0] += 100
            self.w.check(self.TEAM, {"nfl-phi": {self.DAY}}, self.DAY, force=True)
        self.assertEqual(self.parties, [])

    def test_celebration_settings(self):
        s = settings(gameday={"enabled": True, "celebrate_seconds": 20, "teams": [
            {"league": "nfl", "team": "phi", "name": "Eagles", "effect": "christmas", "celebrate": True},
            {"league": "nba", "team": "phi", "name": "76ers", "effect": "christmas"}]})
        cel = build_config(s, {"client_id": "x", "client_secret": "y"}).celebrate
        self.assertEqual(list(cel), ["nfl-phi"])
        self.assertEqual((cel["nfl-phi"]["seconds"], cel["nfl-phi"]["min_points"]), (20, 3))
        s["gameday"]["celebrate_seconds"] = 500
        with self.assertRaises(ConfigError):
            build_config(s, {"client_id": "x", "client_secret": "y"})


if __name__ == "__main__":
    unittest.main()
