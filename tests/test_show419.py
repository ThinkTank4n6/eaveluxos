# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""4.19 show and effects: fades between the schedule's patterns, and the
weather shown on the lights."""
import copy
import unittest
from unittest import mock

from eaveluxos import lanlink as L
from eaveluxos import transitions as T
from eaveluxos import weatherlook as W
from eaveluxos.schedule import ConfigError, WeatherRule
from tests.test_local43 import ServerBase

DEV = "TL-EDGE-01"


def pat(colors, counts=None, bright=200):
    return {"category": 1, "mode": 3, "speed": 120, "brightness": bright,
            "pixels": [{"index": i, "count": n, "color": c, "disable": False}
                       for i, (c, n) in enumerate(zip(colors, counts or [1] * len(colors)))]}


class Frames(unittest.TestCase):
    def test_from_old_to_new(self):
        fr = T.frames(pat([0xFF0000]), pat([0x0000FF], bright=100), 2)
        self.assertEqual(len(fr), 2 * T.FPS)
        self.assertEqual(fr[-1]["pixels"][0]["color"], 0x0000FF, "the last frame is the new colors")
        self.assertEqual(fr[-1]["brightness"], 100)
        mid = fr[len(fr) // 2 - 1]["pixels"][0]["color"]
        self.assertTrue(0 < (mid >> 16) < 255 and 0 < (mid & 255) < 255, hex(mid))
        self.assertTrue(all(f["mode"] == 0 for f in fr), "still frames: the pattern's motion starts after")

    def test_in_from_dark_and_out_to_dark(self):
        fin = T.frames(None, pat([0xFFFFFF]), 2)
        self.assertLess(fin[0]["brightness"], 100)
        self.assertEqual(fin[-1]["pixels"][0]["color"], 0xFFFFFF)
        fout = T.frames(pat([0xFFFFFF]), None, 2)
        self.assertEqual(fout[-1]["pixels"][0]["color"], 0)

    def test_the_new_slots_with_the_old_colors_along_the_lights(self):
        old = pat([0xFF0000, 0x00FF00], [2, 2])                 # R R G G R R G G ...
        new = pat([0x111111, 0x222222, 0x333333], [1, 1, 2])    # slots start on bulbs 0, 1, 2
        first = T.frames(old, new, 2, fps=100)[0]["pixels"]
        self.assertEqual([p["count"] for p in first], [1, 1, 2])
        self.assertGreater(first[0]["color"] >> 16, 200, "bulb 0 was red")
        self.assertGreater(first[2]["color"] >> 8 & 255, 200, "bulb 2 was green")
        self.assertLessEqual(len(first), 30)

    def test_nothing_to_fade(self):
        self.assertEqual(T.frames(pat([1]), pat([2]), 0), [])
        self.assertEqual(T.frames({"category": 0, "mode": 5}, pat([2]), 3), [], "a built-in's colors aren't known")
        self.assertEqual(T.frames(None, None, 3), [])
        self.assertEqual(len(T.frames(pat([1]), pat([2]), 99)), T.MAX_SECONDS * T.FPS)

    def test_setting(self):
        self.assertEqual(T.check(None), 0)
        self.assertEqual(T.check({"fade_seconds": 3}), 3)
        for bad in (4, -1, True, "3"):
            with self.assertRaises(ConfigError):
                T.check({"fade_seconds": bad})


class Fades(ServerBase):
    def setUp(self):
        super().setUp()
        self.app.local_commands(True)
        self.c = self.app.ctrl
        self.c.devices = [{"deviceId": DEV, "name": "Trimlight"}]
        s = copy.deepcopy(self.app.store.settings)
        s["transitions"] = {"fade_seconds": 2}
        self.app.save_settings(s)
        self.c = self.app.ctrl
        self.c.devices = [{"deviceId": DEV, "name": "Trimlight"}]

    def previews(self):
        return [f for f in self.ctl.frames(L.CMD_REQUEST) if f[2][:1] == bytes([L.SUB_PREVIEW])]

    def custom_key(self, but=None):
        return next(k for k, e in self.c.cfg.effects.items() if e.kind == "custom" and k != but)

    def test_a_scheduled_change_fades_over_the_home_network(self):
        a = self.custom_key()
        b = self.custom_key(a)
        self.c._apply(True, self.c.cfg.effects[a], {})
        self.c.known_on = True
        n = len(self.previews())
        with mock.patch("time.sleep"):
            self.c._apply(True, self.c.cfg.effects[b], {}, fade=2)
        self.assertGreaterEqual(len(self.previews()) - n, 2 * T.FPS + 1, "the steps, then the pattern")
        self.assertFalse(self.cloud_pattern_writes())

    def test_only_the_schedules_own_changes_fade(self):
        seen = []
        real = self.c._apply

        def spy(*a, **k):
            seen.append(k.get("fade"))
            return real(*a, **k)
        with mock.patch.object(self.c, "_apply", spy), mock.patch("time.sleep"):
            self.c.next_try, self.c.applied_key = 0, None
            self.c.tick()                         # nothing sent yet (a start, a restore): at once
            self.c.manual(True, self.custom_key())
            self.c.tick()                         # a choice made now: at once
            self.c.override = None
            self.assertIn(self.c._target(commit=False).reason, ("schedule", "weather"))
            self.c.applied_key = "an earlier pattern of the schedule's"
            self.c.tick()                         # the schedule's own change: a fade
        self.assertEqual(seen, [0, 0, 2])


class Review(Fades):
    def test_1_a_press_ends_a_fade(self):
        import threading
        import time
        import subprocess
        import sys
        from pathlib import Path
        script = str(Path(__file__).with_name("repro_min_fade_blocks_press.py"))
        self.assertIn("BUG:", subprocess.run([sys.executable, script], capture_output=True, text=True, timeout=60).stdout)
        self.assertIn("OK:", subprocess.run([sys.executable, script, "--fixed"], capture_output=True, text=True, timeout=60).stdout)
        a, b = self.custom_key(), None
        b = self.custom_key(a)
        self.c._apply(True, self.c.cfg.effects[a], {})
        self.c.known_on = True
        t = threading.Thread(target=self.c._apply, args=(True, self.c.cfg.effects[b], {}), kwargs={"fade": 8})
        t0 = time.monotonic()
        t.start()
        time.sleep(0.6)
        self.c.manual(False)                      # "Lights off" pressed
        t.join(10)
        self.assertLess(time.monotonic() - t0, 3, "the 8-second fade stopped")

    def test_2_several_controllers_share_the_fade(self):
        self.c.devices = [{"deviceId": d, "name": d} for d in (DEV, "B", "C")]
        got = []
        with mock.patch.object(self.c.lan, "fade", lambda dev, fr, every, cancel=None: got.append(len(fr))):
            self.c._fade(DEV, pat([0xFF0000]), pat([0x00FF00]), 3)
        self.assertEqual(got, [T.FPS], "1 second each, not 3")

    def test_3_the_same_colors_again_dont_fade(self):
        self.assertEqual(T.frames(pat([0xFF0000]), pat([0xFF0000]), 3), [])
        self.assertTrue(T.frames(pat([0xFF0000], bright=60), pat([0xFF0000], bright=200), 3), "a brightness change still does")

    def test_try_a_fade(self):
        # 4.21.2: what the lights show before is set here, not left to the
        # time of day. On GitHub at 5:44 PM the schedule already showed this
        # pattern, and a fade to the same colors (rightly) sends nothing.
        a = self.custom_key()
        b = next(k for k, e in self.c.cfg.effects.items()
                 if e.kind == "custom" and e.payload.get("pixels") != self.c.cfg.effects[a].payload.get("pixels"))
        self.c.known_on = True
        self.c.sent_effect = {DEV: dict(self.c.cfg.effects[a].payload)}
        got = []
        with mock.patch.object(self.c.lan, "fade", lambda dev, fr, every, cancel=None: got.append(len(fr))):
            self.app.ctrl.try_fade(b, 2)
        self.assertTrue(got)
        got.clear()
        self.c.sent_effect = {DEV: dict(self.c.cfg.effects[b].payload)}
        with mock.patch.object(self.c.lan, "fade", lambda dev, fr, every, cancel=None: got.append(len(fr))):
            self.app.ctrl.try_fade(b, 2)
        self.assertEqual(got, [], "already showing: nothing to fade")
        self.assertTrue(self.c.override and self.c.override.get("on"))
        with self.assertRaises(ValueError):
            self.c.try_fade("nope", 2)


class Weather(unittest.TestCase):
    def test_temperature_colors(self):
        self.assertEqual(W.temp_color(-20), W.temp_color(10), "colder than the scale: its coldest")
        self.assertTrue(W.temp_color(10).endswith("FF"), "freezing is blue")
        self.assertTrue(W.temp_color(95).startswith("#FF2"), "hot is red")
        self.assertEqual(W.temperature_config(47)[0], "wx_temp_45")
        self.assertEqual(W.temperature_config(48)[0], "wx_temp_50")
        self.assertEqual(W.temperature_effect(70).kind, "custom")

    def test_rule(self):
        r = WeatherRule.from_config(0, {"name": "Temperature colors", "temperature_colors": True}, {})
        self.assertTrue(r.temperature)
        self.assertFalse(r.matches(set(), None), "no reading, no color")
        self.assertTrue(r.matches({"clear"}, 40))
        with self.assertRaises(ConfigError):
            WeatherRule.from_config(0, {"name": "x", "effect": "nope"}, {})

    def test_add_looks(self):
        s0 = {"effects": {"wx_rain": {"label": "Mine", "colors": ["#123456"]}}, "weather_rules": [{"name": "snow", "when": ["snow"], "effect": "x"}]}
        s, added = W.add_looks(s0)
        self.assertEqual(s["effects"]["wx_rain"]["label"], "Mine", "nothing of yours is changed")
        self.assertEqual(sum(1 for r in s["weather_rules"] if r["name"].lower() == "snow"), 1)
        self.assertTrue(s["weather"]["enabled"])
        self.assertIn("weather rule Temperature colors", added)
        self.assertEqual(W.add_looks(s)[1], [], "twice adds nothing")


class WeatherOnTheLights(ServerBase):
    def test_looks_are_added_and_the_temperature_shows(self):
        r = self.app.weather_looks()
        self.assertTrue(r["added"])
        c = self.app.ctrl
        self.assertTrue(any(w.temperature for w in c.cfg.weather_rules))
        self.assertIn("wx_storm", c.cfg.effects)
        cur = {"fresh": True, "tags": {"clear"}, "temp_f": 28.0}
        c.weather = mock.Mock(current=lambda: cur)
        from datetime import datetime
        w = c.cfg.schedule.active_window(c.cfg.loc.now()) or next(
            x for x in (c.cfg.schedule.active_window(datetime(2026, 11, 23, 19, 0, tzinfo=c.cfg.loc.tz)),) if x)
        eff = c._scheduled(w, w.start, {})[3]
        self.assertEqual(eff.key, "wx_temp_30")
        cur.update(tags={"rain"})
        self.assertEqual(c._scheduled(w, w.start, {})[3].key, "wx_rain", "rain shows rain, whatever the temperature")


if __name__ == "__main__":
    unittest.main()


try:
    from playwright.sync_api import sync_playwright
except ImportError:            # pragma: no cover
    sync_playwright = None


@unittest.skipIf(sync_playwright is None, "Playwright isn't installed")
class Browser(ServerBase):
    def test_fades_and_weather_looks(self):
        import threading
        import time
        from eaveluxos.server import make_server
        srv = make_server(self.app, "127.0.0.1", 0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        base = f"http://localhost:{srv.server_address[1]}/"
        try:
            pw = sync_playwright().start()
            br = pw.chromium.launch()
        except Exception as e:
            self.skipTest(f"Chromium can't start: {e}")
        self.addCleanup(pw.stop)
        self.addCleanup(br.close)
        errors = []

        def until(cond, what):
            for _ in range(200):
                if cond():
                    return
                time.sleep(0.05)
            self.fail(f"never: {what}")

        def unfold(pg, key):
            pg.wait_for_selector(f'[data-fold="{key}"]')
            if "closed" in (pg.get_attribute(f'[data-fold="{key}"]', "class") or ""):
                pg.click(f'[data-fold="{key}"] .foldbar')
        for size in ({"width": 1300, "height": 900}, {"width": 390, "height": 844}):
            pg = br.new_page(viewport=size)
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.goto(base + "#schedule")
            unfold(pg, "fades")
            pg.wait_for_selector("#fadesec")
            self.assertEqual(pg.evaluate("document.documentElement.scrollWidth"), size["width"])
            if size["width"] > 1000:
                pg.select_option("#fadesec", "3")
                until(lambda: (self.app.store.settings.get("transitions") or {}).get("fade_seconds") == 3, "saved")
                self.assertEqual(self.app.ctrl.cfg.fade_seconds, 3)
                pg.goto(base + "#alerts")
                unfold(pg, "weather")
                pg.click("[data-wxlooks]")
                pg.locator("#dlg button[value=yes]").click()
                until(lambda: "wx_storm" in self.app.store.settings["effects"], "the looks added")
                pg.wait_for_selector("text=the temperature as a color")
                pg.click("[data-addwx]")
                pg.wait_for_selector("#dlg input[name=tempcol]")
                pg.check("#dlg input[name=tempcol]")
                self.assertTrue(pg.locator("#dlg [data-wxpick]").is_hidden())
                pg.click("#dlg [data-close]") if pg.query_selector("#dlg [data-close]") else pg.keyboard.press("Escape")
            pg.close()
        self.assertEqual(errors, [])
