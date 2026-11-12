# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Scheduler behavior with a fake controller: overrides, flash, weather,
read-back restore, and that status never waits on the network."""
import copy
import threading
import time
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from eaveluxos.controller import Controller
from eaveluxos.schedule import Location, build_config
from eaveluxos.store import DEFAULT_SETTINGS

NY = ZoneInfo("America/New_York")


class FakeAPI:
    def __init__(self):
        self.switch, self.calls, self.delay = 0, [], 0.0
        self.clock_offset_min = 0

    def list_devices(self):
        return [{"deviceId": "D1", "name": "House"}]

    def get_device(self, d, now):
        time.sleep(self.delay)
        return {"name": "House", "connectivity": 1, "switchState": self.switch, "effects": []}

    def set_switch(self, d, v):
        time.sleep(self.delay)
        self.switch = v
        self.calls.append(("switch", v))

    def preview_effect(self, d, p):
        time.sleep(self.delay)
        self.calls.append(("preview", p.get("mode"), p.get("brightness")))


class FakeWeather:
    def __init__(self):
        self.tags = set()

    def refresh(self, force=False):
        pass

    def current(self):
        return {"tags": self.tags, "temp_f": 30, "summary": "", "fresh": True}


class ControllerTests(unittest.TestCase):
    def setUp(self):
        s = copy.deepcopy(DEFAULT_SETTINGS)
        s["location"].update(latitude=39.95, longitude=-75.17)
        s["rules"] = [{"name": "Night", "on": "18:00", "off": "23:00", "effect": "warm_white", "brightness": 60}]
        self.cfg = build_config(s, {"client_id": "x", "client_secret": "y"})
        self.clock = [datetime(2026, 11, 20, 12, 0, tzinfo=NY)]
        self._orig_now = Location.now
        Location.now = lambda loc: self.clock[0]
        self.api = FakeAPI()
        self.wx = FakeWeather()
        self.c = Controller(self.cfg, self.api, weather=self.wx)

    def tearDown(self):
        Location.now = self._orig_now

    def at(self, h, m=0, day=20):
        self.clock[0] = datetime(2026, 11, day, h, m, tzinfo=NY)
        self.c.next_try = 0
        self.c.tick()
        return self.c._target()

    def test_schedule_on_off_and_levels(self):
        self.assertFalse(self.at(12).on)
        t = self.at(18, 1)
        self.assertTrue(t.on)
        self.assertEqual(self.api.switch, 1)
        self.assertEqual(self.api.calls[-1][2], 60)  # rule brightness
        self.assertFalse(self.at(23, 1).on)
        self.assertEqual(self.api.switch, 0)

    def test_manual_override_ends_at_next_scheduled_change(self):
        self.at(12)
        self.c.manual(True, "christmas")
        self.assertEqual(self.c._target().reason, "manual")
        self.assertEqual(self.at(18, 1).reason, "schedule")

    def test_flash_then_back_to_off(self):
        self.at(12)
        self.c.start_flash(5)
        self.assertEqual(self.c._target().reason, "flash")
        self.assertTrue(self.at(12, 6).on is False)
        self.assertEqual(self.api.switch, 0)

    def test_weather_keeps_rule_brightness(self):
        self.cfg.weather_rules  # default has a snow rule at priority 150
        self.at(19)
        self.wx.tags = {"snow"}
        t = self.at(19, 1)
        self.assertEqual(t.reason, "weather")
        self.assertEqual(t.levels.get("brightness"), 60)

    def test_restores_after_outside_change(self):
        self.at(19)
        self.assertEqual(self.api.switch, 1)
        self.api.switch = 2  # controller fell back to its own timer mode
        for _ in range(3):
            self.c.last_verify = 0
            self.at(19, 5)
        self.assertEqual(self.api.switch, 1)

    def test_status_does_not_wait_for_cloud(self):
        self.at(12)
        self.api.delay = 2.0
        th = threading.Thread(target=lambda: self.c.manual(True, "christmas"))
        th.start()
        time.sleep(0.2)
        t0 = time.time()
        self.c.status()
        self.assertLess(time.time() - t0, 0.5)
        th.join()


if __name__ == "__main__":
    unittest.main()
