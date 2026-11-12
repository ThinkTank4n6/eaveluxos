# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""3.6: several schedules a day, like the Trimlight Edge app's timers: for
example 6:00 AM to sunrise and sunset to 11:00 PM."""
import copy
import shutil
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from eaveluxos.schedule import build_config
from eaveluxos.server import App
from eaveluxos.store import DEFAULT_SETTINGS

NY = ZoneInfo("America/New_York")
MORNING = {"name": "Morning", "on": "06:00", "off": "sunrise", "effect": "warm_white"}
EVENING = {"name": "Evening", "on": "sunset", "off": "23:00", "effect": "warm_white"}


def cfg(*rules):
    s = copy.deepcopy(DEFAULT_SETTINGS)
    s["location"].update(latitude=39.9, longitude=-75.4, timezone="America/New_York")
    s["rules"] = list(rules)
    return build_config(s, {"client_id": "x", "client_secret": "y"})


def hm(t):
    return t.strftime("%H:%M")


class TwoADay(unittest.TestCase):
    def test_morning_and_evening_both_run(self):
        sch = cfg(EVENING, MORNING).schedule
        plans = sch.day_plans(date(2026, 12, 10))
        self.assertEqual([(p.rule.name, hm(p.start)) for p in plans], [("Morning", "06:00"), ("Evening", hm(plans[1].start))])
        self.assertEqual(hm(plans[1].end), "23:00")
        on = lambda h, m=0: (w := sch.active_window(datetime(2026, 12, 10, h, m, tzinfo=NY))) and w.rule.name
        self.assertEqual([on(5, 59), on(6, 30), on(12), on(18), on(23, 1)], [None, "Morning", None, "Evening", None])

    def test_morning_rule_skips_days_when_sun_is_up_before_6(self):
        sch = cfg(EVENING, MORNING).schedule
        self.assertEqual([p.rule.name for p in sch.day_plans(date(2026, 6, 21))], ["Evening"])
        self.assertIsNone(sch.active_window(datetime(2026, 6, 21, 12, 0, tzinfo=NY)))   # not 06:00 to the next sunrise
        self.assertIsNone(sch.active_window(datetime(2026, 6, 22, 3, 0, tzinfo=NY)))

    def test_overnight_windows_still_work(self):
        sch = cfg({"name": "All night", "on": "sunset", "off": "sunrise", "effect": "warm_white"}).schedule
        (p,) = sch.day_plans(date(2026, 12, 10))
        self.assertEqual(p.end.date(), date(2026, 12, 11))
        self.assertGreater((p.end - p.start).total_seconds(), 14 * 3600)

    def test_overlap_higher_priority_wins_and_the_other_fills_the_gaps(self):
        late = {"name": "Late", "dates": "12-31", "on": "20:00", "off": "00:30", "effect": "christmas"}
        plans = cfg(EVENING, late).schedule.day_plans(date(2026, 12, 31))
        self.assertEqual([(p.rule.name, hm(p.end)) for p in plans], [("Evening", "20:00"), ("Late", "00:30")])


class AppViews(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.app = App(self.dir, start=False)
        s = self.app.store.settings
        s["location"].update(latitude=39.9, longitude=-75.4)
        s["rules"] = [EVENING, MORNING]
        self.app.store.save_settings(s)
        self.app.store.save_secrets(client_id="x", client_secret="y")
        self.app.rebuild()

    def tearDown(self):
        self.app.store.close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_no_never_runs_warning_and_all_windows_listed(self):
        rc = self.app.rule_check()
        self.assertIsNone(rc["Morning"]["blocked_by"])
        self.assertGreater(rc["Morning"]["wins"], 100)
        winter = [d for d in self.app.upcoming(400) if d["date"].endswith("-12-10")][0]
        self.assertEqual([w["rule"] for w in winter["windows"]], ["Morning", "Evening"])
        self.assertEqual((winter["rule"], winter["on_label"]), ("Morning", "06:00"))     # older fields: the first one

    def test_safety_net_copies_both(self):
        entries, _ = self.app.safety.plan(self.app.cfg, datetime(2026, 12, 10, 12, 0, tzinfo=NY))
        today = [e for e in entries if (e["month"], e["day"]) == (12, 10)]
        self.assertEqual([e["rule"] for e in today], ["Morning", "Evening"])
        self.assertEqual(today[0]["start"], [6, 0])


if __name__ == "__main__":
    unittest.main()
