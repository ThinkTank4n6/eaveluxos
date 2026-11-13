# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Playlists: rotating patterns with their own minutes each (rotate_each)."""
import copy
import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from eaveluxos.controller import Controller
from eaveluxos.schedule import ConfigError, Location, build_config
from eaveluxos.store import DEFAULT_SETTINGS
from tests.test_music import CountingAPI

NY = ZoneInfo("America/New_York")
MIX = {"name": "Mix", "on": "18:00", "off": "23:00", "effect": ["christmas", "snowfall", "warm_white"], "rotate_each": [10, 5, 15]}


def cfg(rules=None, weather_rules=None):
    s = copy.deepcopy(DEFAULT_SETTINGS)
    s["location"].update(latitude=39.95, longitude=-75.17)
    s["rules"] = rules if rules is not None else [MIX]
    if weather_rules is not None:
        s["weather_rules"] = weather_rules
    return build_config(s, {"client_id": "x", "client_secret": "y"})


class PickTests(unittest.TestCase):
    def test_each_pattern_gets_its_own_time_then_repeats(self):
        r = cfg().schedule.rules[0]
        start = datetime(2026, 12, 4, 18, 0, tzinfo=NY)
        seq = [(m, r.pick(start, start + timedelta(minutes=m))) for m in (0, 9, 10, 14, 15, 29, 30, 44, 45, 60)]
        self.assertEqual([e.label for _, (e, _) in seq],
                         ["Christmas", "Christmas", "Snowfall", "Snowfall", "Warm white", "Warm white",
                          "Christmas", "Snowfall", "Warm white", "Christmas"])   # 44: 14 min into cycle 2
        steps = [s for _, (_, s) in seq]
        self.assertEqual(steps, sorted(steps))                   # only ever grows
        self.assertEqual(steps, [0, 0, 1, 1, 2, 2, 3, 4, 5, 6])   # one step per pattern shown

    def test_label(self):
        self.assertEqual(cfg().schedule.rules[0].effect_label,
                         "Christmas 10 min / Snowfall 5 min / Warm white 15 min (in turn)")

    def test_old_rules_unchanged(self):
        r = cfg([{**MIX, "rotate_each": None, "rotate_minutes": 20}]).schedule.rules[0]
        start = datetime(2026, 12, 4, 18, 0, tzinfo=NY)
        self.assertIsNone(r.rotate_each)
        self.assertEqual(r.pick(start, start + timedelta(minutes=45))[0].label, "Warm white")   # 3rd slot of 20 min

    def test_weather_rules_too(self):
        w = cfg(weather_rules=[{"name": "Snow", "when": ["snow"], "effect": ["snowfall", "warm_white"], "rotate_each": [3, 7]}]).weather_rules[0]
        start = datetime(2026, 12, 4, 18, 0, tzinfo=NY)
        self.assertEqual([w.pick(start, start + timedelta(minutes=m))[0].label for m in (0, 3, 9, 10)],
                         ["Snowfall", "Warm white", "Warm white", "Snowfall"])

    def test_bad_lists_are_refused(self):
        for bad in ({"rotate_each": [10, 5]}, {"rotate_each": [10, 0, 5]}, {"rotate_each": [10, 5, 1441]},
                    {"rotate_each": [10, "x", 5]}, {"rotate_each": "10"}, {"rotate_each": [10, 5, 15], "rotate": "nightly"}):
            with self.subTest(bad=bad), self.assertRaises(ConfigError):
                cfg([{**MIX, **bad}])

    def test_rotate_each_alone_is_enough(self):
        self.assertEqual(cfg().schedule.rules[0].rotate_minutes, 0)
        with self.assertRaises(ConfigError):                     # several patterns, no timing at all
            cfg([{k: v for k, v in MIX.items() if k != "rotate_each"}])


class SchedulerTests(unittest.TestCase):
    def setUp(self):
        self.clock = [datetime(2026, 12, 4, 18, 0, tzinfo=NY)]
        self._orig = Location.now
        Location.now = lambda loc: self.clock[0]

    def tearDown(self):
        Location.now = self._orig

    def test_switches_exactly_at_each_boundary(self):
        api = CountingAPI()
        c = Controller(cfg(), api)
        sent = []
        for m in range(0, 32):
            self.clock[0] = datetime(2026, 12, 4, 18, m, tzinfo=NY)
            c.next_try = 0
            c.tick()
            t = c._target(commit=False)
            if not sent or sent[-1][1] != t.effect.label:
                sent.append((m, t.effect.label))
        self.assertEqual(sent, [(0, "Christmas"), (10, "Snowfall"), (15, "Warm white"), (30, "Christmas")])
        previews = [x for x in api.calls if x[0] == "preview"]
        self.assertEqual(len(previews), 4)                       # one send per change, none in between

    def test_home_screen_shows_the_times(self):
        c = Controller(cfg(), CountingAPI())
        rot = c.status()["rotation"]
        self.assertEqual((rot["labels"], rot["each"]), (["Christmas", "Snowfall", "Warm white"], [10, 5, 15]))


if __name__ == "__main__":
    unittest.main()
