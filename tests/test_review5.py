# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Fixes from the 3.11 code review: races, time zones east of UTC, the
security flash, duplicate patterns, controller list changes, and more."""
import copy
import threading
import time
import unittest

from eaveluxos.controller import Controller
from eaveluxos.schedule import build_config
from eaveluxos.store import DEFAULT_SETTINGS


class FakeAPI:
    clock_offset_min = 0

    def __init__(self, ids=("d1",)):
        self.ids, self.sent = list(ids), []
        self.gate, self.slow = threading.Event(), False

    def list_devices(self):
        return [{"deviceId": i, "name": i} for i in self.ids]

    def get_device(self, dev, now):
        return {"switchState": 1, "connectivity": 1, "effects": []}

    def set_switch(self, dev, state):
        self.sent.append((dev, "switch", state))

    def preview_effect(self, dev, payload):
        if self.slow:
            self.gate.wait(5)
        self.sent.append((dev, "preview", payload["pixels"][0]["color"]))


def make_cfg(color="#FFB46B", devices=(), security="security_white", tz="America/New_York", lat=39.9, lon=-75.3, rules=None):
    s = copy.deepcopy(DEFAULT_SETTINGS)
    s["location"] = {"latitude": lat, "longitude": lon, "timezone": tz}
    s["rules"] = rules or [{"name": "All day", "on": "00:00", "off": "23:59", "effect": "warm_white"}]
    s["effects"]["warm_white"]["colors"] = [color]
    s["service"]["devices"] = list(devices)
    s["security"]["effect"] = security
    return build_config(s, {"client_id": "x", "client_secret": "y"})


class ReloadRace(unittest.TestCase):
    def test_reload_during_a_send_is_not_lost(self):
        api = FakeAPI()
        c = Controller(make_cfg(), api)
        c.tick()
        c.applied_key = None
        api.slow = True
        t = threading.Thread(target=c.tick)
        t.start()
        time.sleep(0.2)                       # the scheduler is mid-send
        r = threading.Thread(target=c.reload, args=(make_cfg("#0000FF"),))
        r.start()
        time.sleep(0.2)
        api.slow = False
        api.gate.set()
        t.join()
        r.join()
        c.tick()
        self.assertEqual(api.sent[-1], ("d1", "preview", 0x0000FF))


class EastOfUtc(unittest.TestCase):
    RULES = [{"name": "Morning", "on": "05:00", "off": "sunrise", "effect": "warm_white"},
             {"name": "Late", "on": "00:15", "off": "00:45", "effect": "warm_white"},
             {"name": "Evening", "on": "sunset", "off": "23:00", "effect": "warm_white"}]

    def test_day_plans_match_the_windows(self):
        from datetime import date
        for tz, lat, lon in (("Australia/Sydney", -33.87, 151.2), ("Pacific/Auckland", -36.85, 174.76),
                             ("Europe/London", 51.5, -0.1), ("America/New_York", 39.9, -75.3)):
            cfg = make_cfg(tz=tz, lat=lat, lon=lon, rules=self.RULES)
            for d in (date(2026, 1, 15), date(2026, 7, 15), date(2026, 11, 20)):
                want = [r.name for r in cfg.schedule.rules if r.window(d, cfg.loc)]
                got = [p.rule.name for p in cfg.schedule.day_plans(d)]
                self.assertEqual(sorted(got), sorted(want), f"{tz} {d}")


class FlashPatternRemoved(unittest.TestCase):
    def test_flash_ends_when_its_pattern_is_cleared(self):
        c = Controller(make_cfg(), FakeAPI())
        c.start_flash(5)
        c.reload(make_cfg(security=""))          # used to raise KeyError: None
        st = c.status()
        self.assertFalse(st["flash"]["active"])
        self.assertEqual(st["target"]["reason"], "schedule")
        self.assertIsNone(c.flash)


class SlotFallback(unittest.TestCase):
    PAYLOAD = {"id": -1, "name": "x", "category": 1, "mode": 0, "speed": 1, "brightness": 1,
               "pixels": [{"index": 0, "count": 90, "color": 1, "disable": False}]}

    def run_save(self, error):
        from eaveluxos import api as apimod
        calls = []

        class T(apimod.TrimlightAPI):
            def _request(self, method, path, body=None):
                calls.append(len(body["payload"]["pixels"]))
                if len(calls) == 1:
                    raise error
                return {"id": 7}
        saved = apimod.TrimlightAPI.slot_limit
        try:
            try:
                T("a", "b").save_effect("d1", dict(self.PAYLOAD))
            except apimod.TrimlightError:
                pass
            return calls, apimod.TrimlightAPI.slot_limit
        finally:
            apimod.TrimlightAPI.slot_limit = saved

    def test_network_error_is_not_resent(self):
        from eaveluxos.api import TrimlightError
        calls, limit = self.run_save(TrimlightError("timed out", "network"))
        self.assertEqual(calls, [1])          # no second (duplicate) save
        self.assertEqual(limit, 90)

    def test_server_error_is_not_resent(self):
        from eaveluxos.api import TrimlightError
        calls, _ = self.run_save(TrimlightError("HTTP 504", "http", 504))
        self.assertEqual(calls, [1])

    def test_refusal_still_splits(self):
        from eaveluxos.api import TrimlightError
        calls, limit = self.run_save(TrimlightError("code 1001", "api"))
        self.assertEqual(calls, [1, 2])
        self.assertEqual(limit, 60)


class ControllerListChanges(unittest.TestCase):
    def test_added_controller_is_switched_on(self):
        api = FakeAPI(ids=("d1", "d2"))
        c = Controller(make_cfg(devices=["d1"]), api)
        c.tick()
        api.sent.clear()
        c.reload(make_cfg(devices=["d1", "d2"]))
        self.assertIn(("d2", "switch", 1), api.sent)
        self.assertIn(("d2", "preview", 0xFFB46B), api.sent)

    def test_refresh_devices_resends_everything(self):
        api = FakeAPI(ids=("d1",))
        c = Controller(make_cfg(), api)
        c.tick()
        api.sent.clear()
        c.refresh_devices()
        c.tick()
        self.assertEqual(api.sent, [("d1", "switch", 1), ("d1", "preview", 0xFFB46B)])


class ButtonsDontWaitOnMaintenance(unittest.TestCase):
    def test_actions_skip_the_safety_copy_and_read_back(self):
        c = Controller(make_cfg(), FakeAPI())
        calls = []
        c._maintenance = lambda t: calls.append(t)
        c.manual(False)
        c.resume()
        c.start_flash(1)
        c.stop_flash()
        self.assertEqual(calls, [])
        c.tick()                                  # the scheduler's own pass still does it
        self.assertEqual(len(calls), 1)


class WeatherEither(unittest.TestCase):
    def test_station_down_keeps_the_forecast(self):
        from eaveluxos.weather import WeatherService

        def fetch(url):
            if "/points/" in url:
                return {"properties": {"forecastHourly": "H", "observationStations": "S"}}
            if url == "S":
                return {"features": [{"properties": {"stationIdentifier": "KPHL"}}]}
            if "/observations/" in url:
                raise RuntimeError("NWS returned HTTP 500")
            return {"properties": {"periods": [{"shortForecast": "Light Snow", "temperature": 30,
                                                "temperatureUnit": "F", "startTime": "x"}]}}
        w = WeatherService(39.9, -75.3, "either", 15, fetch=fetch)
        w.refresh()
        cur = w.current()
        self.assertTrue(cur["fresh"])
        self.assertIn("snow", cur["tags"])

    def test_both_down_is_an_error(self):
        from eaveluxos.weather import WeatherService

        def fetch(url):
            if "/points/" in url:
                return {"properties": {"forecastHourly": "H", "observationStations": "S"}}
            raise RuntimeError("NWS unreachable")
        w = WeatherService(39.9, -75.3, "either", 15, fetch=fetch)
        w.refresh()
        self.assertFalse(w.current()["fresh"])
        self.assertIn("unreachable", w.current()["error"])


class SunFarFromItsClock(unittest.TestCase):
    def test_events_fall_on_the_day_asked(self):
        from datetime import date
        from zoneinfo import ZoneInfo
        from eaveluxos.sun import sun_times
        for tz, lat, lon in (("Pacific/Kiritimati", 1.87, -157.4), ("Pacific/Apia", -13.83, -171.76),
                             ("Pacific/Tongatapu", -21.14, -175.2), ("Pacific/Auckland", -36.85, 174.76),
                             ("America/New_York", 39.9, -75.3), ("Pacific/Honolulu", 21.3, -157.86)):
            for d in (date(2026, 1, 15), date(2026, 6, 21), date(2026, 11, 20)):
                st = sun_times(d, lat, lon, ZoneInfo(tz))
                for k, v in st.items():
                    self.assertEqual(v.date(), d, f"{tz} {d} {k}")
                self.assertLess(st["sunrise"], st["noon"])
                self.assertLess(st["noon"], st["sunset"])


class WeatherNightly(unittest.TestCase):
    def test_nightly_weather_rule_rotates_by_night(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        s = copy.deepcopy(DEFAULT_SETTINGS)
        s["location"] = {"latitude": 39.9, "longitude": -75.3, "timezone": "America/New_York"}
        s["weather_rules"] = [{"name": "Snow", "when": ["snow"], "effect": ["snowfall", "christmas"], "rotate": "nightly"}]
        wr = build_config(s, {"client_id": "x", "client_secret": "y"}).weather_rules[0]
        self.assertTrue(wr.nightly)
        self.assertNotIn("every 0 min", wr.effect_label)
        ny = ZoneInfo("America/New_York")
        nights = [wr.pick(datetime(2026, 12, d, 17, 0, tzinfo=ny), datetime(2026, 12, d, 22, 0, tzinfo=ny))[0].key
                  for d in (1, 2, 3)]
        self.assertEqual(len(set(nights[:2])), 2)          # a different pattern the next night
        self.assertEqual(nights[0], nights[2])
        a = wr.pick(datetime(2026, 12, 1, 17, 0, tzinfo=ny), datetime(2026, 12, 1, 17, 1, tzinfo=ny))
        b = wr.pick(datetime(2026, 12, 1, 17, 0, tzinfo=ny), datetime(2026, 12, 1, 23, 59, tzinfo=ny))
        self.assertEqual(a, b)                             # and it holds all night


class WindowCacheThreads(unittest.TestCase):
    def test_clear_between_check_and_read(self):
        from datetime import date
        sch = make_cfg().schedule
        rule = sch.rules[0]

        class ClearsOnRead(dict):          # another thread clears the cache right after the check
            def __contains__(self, k):
                r = dict.__contains__(self, k)
                self.clear()
                return r
        sch._wcache = ClearsOnRead()
        sch._wcache[(rule.order, date(2026, 12, 1))] = sch.rules[0].window(date(2026, 12, 1), sch.loc)
        self.assertIsNotNone(sch._window(rule, date(2026, 12, 1)))


class SavedPatternLevels(unittest.TestCase):
    def test_id_only_pattern_matches_by_id(self):
        from eaveluxos.schedule import Effect
        c = Controller(make_cfg(), FakeAPI())
        c.saved = {"d1": {"": {"id": 1, "name": "", "brightness": 10, "speed": 10},
                          "candy": {"id": 5, "name": "Candy", "brightness": 200, "speed": 90}}}
        eff = Effect.from_config("k", {"saved_id": 5})
        self.assertEqual(c.base_levels(eff), {"brightness": 200, "speed": 90})
        self.assertEqual(c.base_levels(Effect.from_config("k", {"saved": "candy"})), {"brightness": 200, "speed": 90})
        self.assertEqual(c.base_levels(Effect.from_config("k", {"saved_id": 9})), {})


class PatternCheck(unittest.TestCase):
    """The read-back also checks the pattern showing (currentEffect)."""

    class Cloud(FakeAPI):
        def __init__(self, report=lambda sent: sent):
            super().__init__()
            self.report, self.current, self.gets = report, None, 0

        def preview_effect(self, dev, payload):
            super().preview_effect(dev, payload)
            self.current = self.report({**payload, "id": -1})

        def get_device(self, dev, now):
            self.gets += 1
            return {"switchState": 1, "connectivity": 1, "effects": [], "currentEffect": self.current}

    def run_checks(self, c, n):
        for _ in range(n):
            c.last_verify = 0.0
            c.tick()

    def previews(self, api):
        return [x for x in api.sent if x[1] == "preview"]

    def test_pattern_changed_in_trimlight_app_is_restored(self):
        api = self.Cloud()
        c = Controller(make_cfg(), api)
        c.tick()
        self.run_checks(c, 2)
        self.assertEqual(len(self.previews(api)), 1)            # matches: nothing resent
        api.current = {"id": 4, "category": 0, "mode": 12, "speed": 140, "brightness": 255}   # Rainbow, chosen in the app
        self.run_checks(c, 1)
        self.assertEqual(len(self.previews(api)), 1)            # one reading isn't enough
        self.run_checks(c, 1)
        c.tick()                                                # the scheduler's next pass sends it
        self.assertEqual(len(self.previews(api)), 2)            # two in a row: restored
        self.assertEqual(api.current["pixels"][0]["color"], 0xFFB46B)
        self.assertIn("pattern", c.events[0]["msg"] + c.events[1]["msg"])
        self.run_checks(c, 1)                                   # the check 30 s after a send confirms it
        api.current = {"id": 4, "category": 0, "mode": 12, "speed": 140, "brightness": 255}   # and again later
        self.run_checks(c, 2)
        c.tick()
        self.assertEqual(len(self.previews(api)), 3)            # a real change is restored again

    def test_controller_reporting_differently_doesnt_flap(self):
        api = self.Cloud(report=lambda sent: {**sent, "brightness": sent["brightness"] - 1})
        c = Controller(make_cfg(), api)
        c.tick()
        self.run_checks(c, 12)                                  # an hour of checks
        self.assertEqual(len(self.previews(api)), 2)            # one restore at most, then it stops trying

    def test_no_current_effect_reported_changes_nothing(self):
        api = self.Cloud(report=lambda sent: None)              # older firmware: no currentEffect
        c = Controller(make_cfg(), api)
        c.tick()
        self.run_checks(c, 6)
        self.assertEqual(len(self.previews(api)), 1)

    def test_matching(self):
        from eaveluxos.controller import effect_matches
        sent = {"category": 1, "mode": 0, "speed": 100, "brightness": 180,
                "pixels": [{"index": 0, "count": 90, "color": 5, "disable": False}]}
        split = {**sent, "id": -1, "pixels": [{"index": 0, "count": 60, "color": 5, "disable": False},
                                              {"index": 1, "count": 30, "color": 5, "disable": False}]}
        self.assertTrue(effect_matches(split, sent))            # split into 60-bulb runs: same pattern
        self.assertFalse(effect_matches({**sent, "id": 3}, sent))   # a saved pattern runs instead of the preview
        self.assertTrue(effect_matches({"id": 3}, {**sent, "id": 3}))
        self.assertFalse(effect_matches({**sent, "id": -1}, {**sent, "id": 3}))
        self.assertIsNone(effect_matches(None, sent))
        self.assertIsNone(effect_matches(sent, None))


@unittest.skipIf(__import__("os").name == "nt", "POSIX permissions")
class MakeCertKeyFile(unittest.TestCase):
    def test_leftover_temp_file_doesnt_loosen_the_key(self):
        import os
        import stat
        import tempfile
        from pathlib import Path
        try:
            from eaveluxos.tlscert import make_cert
            import cryptography  # noqa: F401
        except ImportError:
            self.skipTest("cryptography isn't installed")
        d = Path(tempfile.mkdtemp())
        (d / "key.tmp").write_text("leftover")
        os.chmod(d / "key.tmp", 0o644)
        make_cert(d)
        self.assertEqual(stat.S_IMODE(os.stat(d / "key.pem").st_mode), 0o600)
        self.assertFalse((d / "key.tmp").exists() or (d / "cert.tmp").exists())


class SystemdUnit(unittest.TestCase):
    def test_percent_and_dollar_in_the_folder_name(self):
        import shlex
        import tempfile
        from pathlib import Path
        from unittest import mock
        from eaveluxos import autostart
        home = Path(tempfile.mkdtemp())
        app = home / "Lights 100% $HOME"
        app.mkdir()
        ok = mock.Mock(returncode=0, stderr="")
        with mock.patch.object(autostart.platform, "system", return_value="Linux"), \
                mock.patch.object(autostart.Path, "home", return_value=home), \
                mock.patch.object(autostart.subprocess, "run", return_value=ok):
            autostart.set_enabled(app, True)
        unit = (home / ".config/systemd/user/eaveluxos.service").read_text()
        work = next(l for l in unit.splitlines() if l.startswith("WorkingDirectory="))
        self.assertEqual(work, "WorkingDirectory=" + str(app).replace("%", "%%"))
        start = next(l for l in unit.splitlines() if l.startswith("ExecStart="))[len("ExecStart="):]
        words = [w.replace("%%", "%").replace("$$", "$") for w in shlex.split(start)]
        self.assertEqual(words[1], str(app / "main.py"))
        self.assertNotIn("$HOME", start.replace("$$HOME", ""))     # not left for systemd to expand


if __name__ == "__main__":
    unittest.main()
