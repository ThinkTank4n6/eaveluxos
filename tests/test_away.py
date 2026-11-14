# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Away mode (3.15)."""
import copy
import unittest
from datetime import date, timedelta
from pathlib import Path

from eaveluxos.schedule import ConfigError, away_shift, build_config, ts
from eaveluxos.store import DEFAULT_SETTINGS

SECRETS = {"client_id": "x", "client_secret": "y"}


def cfg(away=None):
    s = copy.deepcopy(DEFAULT_SETTINGS)
    s["location"].update(latitude=39.95, longitude=-75.16)
    if away is not None:
        s["away"] = away
    return build_config(s, SECRETS)


class AwayTests(unittest.TestCase):
    D0 = date(2027, 2, 1)                 # "Every night": sunset + 15 to 23:00

    def window(self, c, d):
        return c.schedule.day_plan(d)

    def test_times_move_within_the_limit_and_differ_night_to_night(self):
        plain = cfg()
        away = cfg({"enabled": True, "until": "2027-02-28", "minutes": 20, "seed": "abc"})
        shifts = set()
        for i in range(14):
            d = self.D0 + timedelta(days=i)
            a, b = self.window(plain, d), self.window(away, d)
            on, off = (ts(b.start) - ts(a.start)) / 60, (ts(b.end) - ts(a.end)) / 60
            self.assertLessEqual(abs(on), 20)
            self.assertLessEqual(abs(off), 20)
            shifts.add((round(on), round(off)))
        self.assertGreater(len(shifts), 7)                    # not the same every night

    def test_the_same_night_always_gets_the_same_times(self):
        a = {"enabled": True, "until": "2027-02-28", "minutes": 30, "seed": "abc"}
        self.assertEqual(self.window(cfg(a), self.D0).start, self.window(cfg(dict(a)), self.D0).start)   # e.g. after a restart
        self.assertEqual(away_shift("s", self.D0, "on", 30), away_shift("s", self.D0, "on", 30))

    def test_rules_that_meet_still_meet(self):
        """Found in the 3.15 screenshot check: a game night (sunset to 23:00)
        and "Every night" (sunset + 15 to 23:00) shifted by different amounts
        left a 6-minute switch back to the everyday pattern at the end."""
        from eaveluxos.schedule import Rule, TimeExpr
        c = cfg({"enabled": True, "until": "2027-02-28", "minutes": 20, "seed": "abc"})
        game = Rule(name="Game", on=TimeExpr.parse("sunset"), off=TimeExpr.parse("23:00"), effects=[c.effects["christmas"]],
                    priority=250, order=99, only_dates=frozenset({self.D0}))
        c.schedule.rules.append(game)
        c.schedule._wcache.clear()
        plans = c.schedule.day_plans(self.D0)
        self.assertEqual([p.rule.name for p in plans], ["Game"])        # no sliver of "Every night" after it

    def test_back_to_normal_after_the_return_date(self):
        plain = cfg()
        away = cfg({"enabled": True, "until": "2027-02-03", "minutes": 20, "seed": "abc"})
        d = date(2027, 2, 4)
        self.assertEqual(self.window(away, d).start, self.window(plain, d).start)
        self.assertEqual(self.window(cfg({"enabled": False, "until": "2027-02-28"}), self.D0).start,
                         self.window(plain, self.D0).start)

    def test_a_window_is_never_squeezed_away(self):
        c = cfg({"enabled": True, "until": "2027-12-31", "minutes": 60, "seed": "x"})
        for i in range(60):
            w = self.window(c, self.D0 + timedelta(days=i))
            self.assertGreaterEqual(ts(w.end) - ts(w.start), 15 * 60)

    def test_bad_settings(self):
        for bad in ({"enabled": True}, {"enabled": True, "until": "soon"}, {"enabled": True, "until": "2027-01-01", "minutes": 300},
                    {"enabled": True, "until": "2027-01-01", "minutes": "20"}, "on"):
            with self.assertRaises(ConfigError, msg=bad):
                cfg(bad)

    def test_screen(self):
        js = (Path(__file__).resolve().parent.parent / "eaveluxos" / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn("function awayPanel", js)
        self.assertIn("crypto.getRandomValues", js)            # each home its own pattern of shifts


if __name__ == "__main__":
    unittest.main()
