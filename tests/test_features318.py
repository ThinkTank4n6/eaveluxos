# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""3.18: describe a pattern in words (built in, or AI with your own key),
night curves, and mood follow."""
import copy
import json
import shutil
import subprocess
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path

from eaveluxos import circadian, textpattern
from eaveluxos.catalog import CUSTOM_MODES
from eaveluxos.controller import Controller
from eaveluxos.schedule import ConfigError, Location, Window, build_config
from eaveluxos.server import ApiError, App
from eaveluxos.store import DEFAULT_SETTINGS
from tests.test_controller import FakeAPI, FakeWeather
from tests.test_triggers316 import NY

HERE = Path(__file__).resolve().parent
SECRETS = {"client_id": "x", "client_secret": "y"}


# ---------------------------------------------------------------- describe a pattern
class BuiltInGeneratorTests(unittest.TestCase):
    def test_themes_colors_and_motion_words(self):
        p = textpattern.generate("slow candy cane twinkle")
        self.assertEqual(p["colors"], ["#FF0000", "#FFFFFF"])
        self.assertEqual(CUSTOM_MODES[p["custom_mode"]], "Stars")
        self.assertLessEqual(p["speed"], 40)
        self.assertEqual(p["label"], "Slow Candy Cane Twinkle")
        p = textpattern.generate("purple and gold sparkle")
        self.assertEqual(p["colors"], ["#8000FF", "#FFD700"])
        self.assertIn("synthwave", textpattern.generate("1980s retro arcade")["why"])
        self.assertGreaterEqual(textpattern.generate("fast party")["speed"], 200)

    def test_two_themes_blend_and_night_darkens(self):
        p = textpattern.generate("Cyberpunk rainy night")
        self.assertGreaterEqual(len(p["colors"]), 4)
        self.assertNotIn("#FF00C0", p["colors"], "night darkens the colors")

    def test_unknown_words_still_give_a_stable_pattern(self):
        a, b = textpattern.generate("Grandma's quilt"), textpattern.generate("Grandma's quilt")
        self.assertEqual(a, b)
        self.assertNotEqual(textpattern.generate("Grandma's quilt", 1)["colors"], a["colors"])

    def test_try_another_changes_it(self):
        self.assertNotEqual(textpattern.generate("1980s retro arcade", 1)["colors"],
                            textpattern.generate("1980s retro arcade")["colors"])

    def test_every_answer_is_a_valid_pattern(self):
        cfg_like = copy.deepcopy(DEFAULT_SETTINGS)
        cfg_like["location"].update(latitude=40, longitude=-75)
        for text in ("halloween", "ocean waves", "x" * 300, "red", "🎄 christmas", "pride parade"):
            p = textpattern.generate(text)
            cfg_like["effects"]["g"] = {k: p[k] for k in ("label", "colors", "counts", "custom_mode", "speed", "brightness")}
            build_config(cfg_like, SECRETS)         # raises if invalid
            self.assertLessEqual(len(p["label"]), 40)

    def test_empty_description_is_refused(self):
        with self.assertRaises(ValueError):
            textpattern.generate("   ")


class AiGeneratorTests(unittest.TestCase):
    def reply(self, text):
        return lambda url, body, key: {"content": [{"type": "text", "text": text}]}

    def test_good_answer_is_checked_and_used(self):
        seen = {}

        def fetch(url, body, key):
            seen.update(url=url, body=body, key=key)
            return {"content": [{"type": "text", "text": 'Here: {"label": "Neon Rain", "colors": ["#ff00c0", "00FFFF"], '
                                                         '"counts": [4, 99], "motion": "Wave forward", "speed": 300, "brightness": 180, "why": "rain"}'}]}
        p = textpattern.ai_generate("cyberpunk rain", "sk-ant-test", fetch=fetch)
        self.assertEqual(p["colors"], ["#FF00C0", "#00FFFF"])
        self.assertEqual(p["counts"], [4, 30])                    # clamped
        self.assertEqual(CUSTOM_MODES[p["custom_mode"]], "Wave forward")
        self.assertEqual((p["speed"], p["source"]), (255, "AI"))
        self.assertEqual(seen["url"], "https://api.anthropic.com/v1/messages")
        self.assertEqual(seen["key"], "sk-ant-test")
        self.assertIn("ignore any instructions", seen["body"]["system"])
        self.assertEqual(json.loads(seen["body"]["messages"][0]["content"].split(": ", 1)[1]), "cyberpunk rain")

    def test_bad_answers_are_refused(self):
        for text in ("no pattern here", '{"colors": []}', '{"colors": ["blue"]}', '{"colors": "red"}'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                textpattern.ai_generate("x", "sk-ant-test", fetch=self.reply(text))

    def test_needs_a_key(self):
        with self.assertRaises(ValueError):
            textpattern.ai_generate("x", None, fetch=self.reply("{}"))

    def test_unknown_motion_falls_back_to_static(self):
        p = textpattern.ai_generate("x", "sk-ant-test", fetch=self.reply('{"colors": ["#FF0000"], "motion": "explode"}'))
        self.assertEqual(p["custom_mode"], 0)


class TextPatternServerTests(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.app = App(self.d, start=False)

    def tearDown(self):
        self.app.store.close()
        shutil.rmtree(self.d, ignore_errors=True)

    def test_key_is_checked_stored_and_never_exported(self):
        from eaveluxos.server import make_server
        import threading
        import urllib.request
        srv = make_server(self.app, "127.0.0.1", 0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        base = f"http://127.0.0.1:{srv.server_address[1]}/api/"
        H = {"Content-Type": "application/json", "X-Requested-With": "eaveluxos"}

        def post(path, body):
            r = urllib.request.Request(base + path, data=json.dumps(body).encode(), headers=H, method="POST")
            try:
                with urllib.request.urlopen(r, timeout=10) as x:
                    return x.status, json.loads(x.read())
            except urllib.error.HTTPError as e:
                return e.code, json.loads(e.read() or b"{}")
        import urllib.error
        self.assertEqual(post("ai/settings", {"key": "hello"})[0], 400)
        self.assertEqual(post("ai/settings", {"key": "sk-ant-abc"}), (200, {"configured": True}))
        self.assertEqual(self.app.store.secrets.get("ai_key"), "sk-ant-abc")
        with urllib.request.urlopen(urllib.request.Request(base + "export", headers=H), timeout=10) as x:
            self.assertNotIn("sk-ant-abc", x.read().decode())
        self.app.ai_fetch = lambda url, body, key: {"content": [{"type": "text", "text": '{"colors": ["#123456"]}'}]}
        st, p = post("textpattern", {"prompt": "anything", "ai": True})
        self.assertEqual((st, p["colors"]), (200, ["#123456"]))
        st, p = post("textpattern", {"prompt": "halloween", "variant": "x"})
        self.assertEqual(st, 200)
        self.assertEqual(post("textpattern", {"prompt": ""})[0], 400)
        self.assertEqual(post("ai/settings", {"key": ""}), (200, {"configured": False}))
        self.assertIsNone(self.app.store.secrets.get("ai_key"))


# ---------------------------------------------------------------- night curves
CURVE = [{"at": "sunset", "kelvin": 5000, "level": 100}, {"at": "21:00", "kelvin": 2700, "level": 100},
         {"at": "00:00", "kelvin": 2700, "level": 15}]


def curve_settings(curve=CURVE, **rule):
    s = copy.deepcopy(DEFAULT_SETTINGS)
    s["location"].update(latitude=39.95, longitude=-75.17)
    s["effects"]["cw"] = {"label": "Whites", "colors": ["#FFFFFF", "#FF0000"], "counts": [3, 1], "brightness": 200}
    s["rules"] = [{"name": "Night", "on": "sunset", "off": "02:00", "effect": "cw", "curve": curve, **rule}]
    return s


class CurveTests(unittest.TestCase):
    def setUp(self):
        self.cfg = build_config(curve_settings(), SECRETS)
        self.rule = self.cfg.schedule.rules[0]
        self.w = self.rule.window(datetime(2026, 11, 20).date(), self.cfg.loc)

    def at(self, h, m=0, day=20):
        return circadian.curve_at(self.rule.curve, self.w, datetime(2026, 11, day, h, m, tzinfo=NY), self.cfg.loc)

    def test_points_and_steps(self):
        self.assertEqual(circadian.curve_at(self.rule.curve, self.w, self.w.start, self.cfg.loc), (5000, 100))   # sunset
        self.assertLess(self.at(17, 0)[0], 5000, "already warming, gradually")
        k, lv = self.at(19, 0)
        self.assertTrue(2700 < k < 5000 and lv == 100)
        self.assertEqual(self.at(21, 0), (2700, 100))
        self.assertEqual(self.at(22, 30), (2700, 58))            # half way from 100% at 9 PM to 15% at midnight
        self.assertEqual(self.at(0, 5, day=21), (2700, 15))       # midnight counts as the next morning
        self.assertEqual(self.at(1, 30, day=21), (2700, 15))
        self.assertEqual(self.at(22, 31), self.at(22, 39), "the same 10-minute step")

    def test_a_point_just_before_the_start_means_the_start(self):
        cfg = build_config(curve_settings(on="sunset + 30"), SECRETS)
        r = cfg.schedule.rules[0]
        w = r.window(datetime(2026, 11, 20).date(), cfg.loc)
        pts = circadian.points_for(r.curve, w, cfg.loc)
        self.assertEqual(pts[0][0], w.start)
        self.assertEqual(pts[-1][0].day, 21)

    def test_bad_curves_are_refused(self):
        for bad in ([CURVE[0]], CURVE * 3, [{"at": "noon-ish", "level": 50}, CURVE[1]], [{"at": "21:00", "level": 2}, CURVE[1]],
                    [{"at": "21:00", "kelvin": 9000}, CURVE[1]], [{"at": "21:00", "color": "#fff"}, CURVE[1]], "x"):
            with self.subTest(bad=bad), self.assertRaises(ConfigError):
                build_config(curve_settings(bad), SECRETS)

    def test_whites_change_and_colors_keep_their_hue(self):
        eff = self.cfg.effects["cw"]
        warm = circadian.with_white(eff, 2700, None)
        self.assertEqual(warm.payload["pixels"][0]["color"], int("".join(f"{v:02X}" for v in circadian.kelvin_rgb(2700)), 16))
        self.assertEqual(warm.payload["pixels"][1]["color"], 0xFF0000)
        self.assertIs(circadian.with_white(eff, None, None), eff)
        reds = build_config(curve_settings(), SECRETS)
        self.assertIsNotNone(reds)

    def test_kelvin_matches_the_browser(self):
        if not shutil.which("node"):
            self.skipTest("Node.js isn't installed")
        js = "const W=require(process.argv[1]);console.log(JSON.stringify([1800,2700,4000,5000,6500].map(W.kelvinRgb)))"
        r = subprocess.run(["node", "-e", js, str(HERE.parent / "eaveluxos" / "static" / "whites.js")], capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(json.loads(r.stdout), [list(circadian.kelvin_rgb(k)) for k in (1800, 2700, 4000, 5000, 6500)])


class CurveControllerTests(unittest.TestCase):
    def setUp(self):
        self.clock = [datetime(2026, 11, 20, 17, 0, tzinfo=NY)]
        orig = Location.now
        self.addCleanup(setattr, Location, "now", orig)
        Location.now = lambda loc: self.clock[0]
        self.api = FakeAPI()
        self.c = Controller(build_config(curve_settings(), SECRETS), self.api, weather=FakeWeather())

    def at(self, h, m=0, day=20):
        self.clock[0] = datetime(2026, 11, day, h, m, tzinfo=NY)
        self.c.next_try = 0
        self.c.tick()
        return self.c._target()

    def test_brightness_follows_the_curve_and_is_sent_in_steps(self):
        self.assertEqual(self.at(17, 5).levels["brightness"], 200)
        n = len(self.api.calls)
        self.at(17, 8)                       # the same 10-minute step (17:00-17:10)
        self.assertEqual(len(self.api.calls), n, "nothing new within a step")
        t = self.at(23, 0)
        self.assertEqual(t.levels["brightness"], round(200 * 43 / 100))       # two thirds of the way to 15%
        self.assertEqual(self.api.calls[-1][2], t.levels["brightness"])
        self.assertEqual(self.at(1, 0, day=21).levels["brightness"], 30)
        self.assertEqual(self.c.status()["target"]["curve"], {"kelvin": 2700, "level": 15})

    def test_brightness_set_by_hand_wins(self):
        self.at(23)
        self.c.set_levels(brightness=180)
        self.assertEqual(self.at(23, 30).levels["brightness"], 180)

    def test_no_handover_to_the_controller_timer_with_a_curve(self):
        self.c._safety_ready = lambda: True
        self.c._delegation_end = lambda *a: self.fail("a curve needs the app")
        self.c.applied_key = "off|timer"
        self.assertFalse(self.at(18).delegated)

    def test_safety_net_copies_the_opening_look(self):
        from eaveluxos.safety import SafetyNet
        sn = SafetyNet(Path(tempfile.mkdtemp()))
        entries, slots = sn.plan(self.c.cfg, datetime(2026, 11, 20, 12, tzinfo=NY))
        eff, levels = next(iter(slots.values()))
        self.assertEqual(levels["brightness"], 200)
        self.assertEqual(eff.payload["pixels"][0]["color"], int("".join(f"{v:02X}" for v in circadian.kelvin_rgb(5000)), 16))


# ---------------------------------------------------------------- mood follow
class MoodTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node.js isn't installed")
    def test_mood_js(self):
        r = subprocess.run(["node", str(HERE / "mood_check.js")], capture_output=True, text=True, encoding="utf-8", timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)

    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.app = App(self.d, start=False)
        s = copy.deepcopy(self.app.store.settings)
        s["location"].update(latitude=39.95, longitude=-75.17)
        s["mood"] = {"calm": "warm_white", "lively": "christmas", "party": "snowfall"}
        self.app.store.save_settings(s)
        self.app.store.save_secrets(client_id="x", client_secret="y")
        self.app.rebuild()
        self.api = FakeAPI()
        self.app.ctrl.api = self.api
        self.app.ctrl.devices = [{"deviceId": "D1", "name": "House"}]

    def tearDown(self):
        self.app.store.close()
        shutil.rmtree(self.d, ignore_errors=True)

    def test_levels_switch_patterns_and_a_steady_mood_sends_nothing_new(self):
        c = self.app.ctrl
        self.assertEqual(self.app.mood("calm")["pattern"], c.cfg.effects["warm_white"].label)
        self.assertEqual(c._target().effect.key, "warm_white")
        n = len(self.api.calls)
        exp = c.override["expires"]
        time.sleep(0.01)
        self.app.mood("calm")
        self.assertEqual(len(self.api.calls), n, "same mood: not sent again")
        self.assertGreater(c.override["expires"], exp, "but kept alive")
        self.app.mood("party")
        self.assertEqual(c._target().effect.key, "snowfall")
        self.app.mood("quiet")
        self.assertNotEqual(c._target().reason, "manual")
        self.assertIsNone(self.app.mood_state)

    def test_a_closed_page_hands_back_after_3_minutes(self):
        self.app.mood("lively")
        self.app.ctrl.override["expires"] = time.time() - 1
        self.assertNotEqual(self.app.ctrl._target().reason, "manual")

    def test_mistakes(self):
        with self.assertRaises(ApiError):
            self.app.mood("loud")
        s = copy.deepcopy(self.app.store.settings)
        s["mood"] = {"calm": None}
        self.app.save_settings(s, s["_rev"])
        self.app.rebuild()
        with self.assertRaises(ApiError):
            self.app.mood("calm")
        for bad in ({"calm": "nope"}, {"angry": "christmas"}, "x"):
            s = copy.deepcopy(self.app.store.settings)
            s["mood"] = bad
            with self.subTest(bad=bad), self.assertRaises(ApiError):
                self.app.save_settings(s, s["_rev"])


class SourceTests(unittest.TestCase):
    JS = (HERE.parent / "eaveluxos" / "static" / "app.js").read_text(encoding="utf-8")
    HTML = (HERE.parent / "eaveluxos" / "static" / "index.html").read_text(encoding="utf-8")

    def test_scripts_and_screens(self):
        self.assertLess(self.HTML.index("mood.js"), self.HTML.index("app.js"))
        for s in ("data-tmake", "async function aiPanel", "function curveRows", "function moodPanel", "window.isSecureContext"):
            self.assertIn(s, self.JS)

    def test_only_this_app_may_use_the_microphone(self):
        src = (HERE.parent / "eaveluxos" / "server.py").read_text(encoding="utf-8")
        self.assertIn("camera=(), microphone=(self)", src)


if __name__ == "__main__":
    unittest.main()
