# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""3.17: bulbs placed on the house photo (preview and scenes), brightness
per zone, and patterns split by controller."""
import copy
import shutil
import subprocess
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

from eaveluxos.controller import Controller
from eaveluxos.safety import for_device
from eaveluxos.schedule import ConfigError, Location, build_config
from eaveluxos.server import ApiError, App
from eaveluxos.store import DEFAULT_SETTINGS
from tests.test_controller import FakeAPI, FakeWeather
from tests.test_triggers316 import NY

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SECRETS = {"client_id": "x", "client_secret": "y"}


class HouseFxJs(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node.js isn't installed")
    def test_housefx_js(self):
        r = subprocess.run(["node", str(HERE / "housefx_check.js")], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_page_loads_housefx_before_the_app(self):
        html = (ROOT / "eaveluxos" / "static" / "index.html").read_text(encoding="utf-8")
        self.assertLess(html.index("housefx.js"), html.index("app.js"))
        self.assertLess(html.index("painter.js"), html.index("app.js"))


class MapBulbsTests(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.app = App(self.d, start=False)

    def tearDown(self):
        self.app.store.close()
        shutil.rmtree(self.d, ignore_errors=True)

    def save_line(self, **extra):
        s = copy.deepcopy(self.app.store.settings)
        s["map"] = {"rooflines": {"front": [{"id": "r1", "kind": "edge", "points": [[0, 10], [100, 12]], "wire": [], **extra}]}}
        self.app.save_settings(s, s["_rev"])

    def test_lines_can_carry_their_bulb_numbers(self):
        self.save_line(bulbs={"from": 84, "to": 40})
        self.assertEqual(self.app.store.settings["map"]["rooflines"]["front"][0]["bulbs"], {"from": 84, "to": 40})

    def test_bad_bulb_numbers_are_refused(self):
        for bad in ({"from": 0, "to": 5}, {"from": 1}, {"from": 1, "to": 20000}, {"from": True, "to": 5},
                    {"from": 1, "to": 5, "x": 1}, [1, 5]):
            with self.subTest(bad=bad), self.assertRaises(ApiError):
                self.save_line(bulbs=bad)
        with self.assertRaises(ApiError):
            self.save_line(color="#fff")                 # other unknown fields are still refused

    def test_a_scene_is_an_ordinary_pattern_that_keeps_its_groups(self):
        s = copy.deepcopy(self.app.store.settings)
        s["effects"]["accents"] = {"label": "Window accents", "colors": ["off", "#FFC58A", "off", "#808080", "off"],
                                   "counts": [9, 3, 30, 3, 55], "custom_mode": 0, "speed": 0, "brightness": 255,
                                   "scene": {"groups": [{"color": "#FFC58A", "level": 100, "bulbs": [10, 11, 12]},
                                                        {"color": "#FFFFFF", "level": 50, "bulbs": [43, 44, 45]}]}}
        self.app.save_settings(s, s["_rev"])
        st = copy.deepcopy(self.app.store.settings)
        st["location"].update(latitude=39.95, longitude=-75.17)
        eff = build_config(st, SECRETS).effects["accents"]
        self.assertEqual([p["disable"] for p in eff.payload["pixels"]], [True, False, True, False, True])
        self.assertEqual(self.app.store.settings["effects"]["accents"]["scene"]["groups"][1]["level"], 50)


def split_settings(split, rest=None, rules=True):
    s = copy.deepcopy(DEFAULT_SETTINGS)
    s["location"].update(latitude=39.95, longitude=-75.17)
    s["effects"]["upstairs_garage"] = {"label": "Upstairs / garage", "split": split, **({"rest": rest} if rest else {})}
    if rules:
        s["rules"] = [{"name": "Night", "on": "18:00", "off": "23:00", "effect": "upstairs_garage"}]
    return s


class SplitConfigTests(unittest.TestCase):
    def test_parts_link_to_patterns(self):
        cfg = build_config(split_settings({"D1": "christmas", "D2": "off"}), SECRETS)
        e = cfg.effects["upstairs_garage"]
        self.assertEqual(e.kind, "split")
        self.assertIs(e.for_device("D1"), cfg.effects["christmas"])
        self.assertIsNone(e.for_device("D2"))
        self.assertIs(e.for_device("D9"), cfg.effects["christmas"], "a controller not named shows the first pattern on")
        self.assertEqual(e.swatches()[:1], cfg.effects["christmas"].swatches()[:1])
        self.assertIs(cfg.effects["warm_white"].for_device("D1"), cfg.effects["warm_white"])

    def test_mistakes_are_explained(self):
        for split in ({"D1": "nope"}, {"D1": "off", "D2": "off"}, {}, {"D1": 5}, "D1"):
            with self.subTest(split=split), self.assertRaises(ConfigError):
                build_config(split_settings(split, rules=False), SECRETS)
        s = split_settings({"D1": "christmas"}, rules=False)
        s["effects"]["nested"] = {"label": "Nested", "split": {"D1": "upstairs_garage"}}
        with self.assertRaises(ConfigError):
            build_config(s, SECRETS)

    def test_a_changed_part_changes_the_split(self):
        """The safety net's change check reads the split's payload."""
        a = build_config(split_settings({"D1": "christmas", "D2": "warm_white"}), SECRETS).effects["upstairs_garage"].payload
        s = split_settings({"D1": "christmas", "D2": "warm_white"})
        s["effects"]["christmas"]["brightness"] = 50
        b = build_config(s, SECRETS).effects["upstairs_garage"].payload
        self.assertNotEqual(a, b)


class TwoControllerAPI(FakeAPI):
    def __init__(self):
        super().__init__()
        self.state = {"D1": 0, "D2": 0}

    def list_devices(self):
        return [{"deviceId": "D1", "name": "Upstairs"}, {"deviceId": "D2", "name": "Garage"}]

    def get_device(self, d, now):
        return {"name": d, "connectivity": 1, "switchState": self.state[d], "effects": []}

    def set_switch(self, d, v):
        self.state[d] = v
        self.calls.append(("switch", d, v))

    def preview_effect(self, d, p):
        self.calls.append(("preview", d, p.get("mode"), p.get("speed")))


class SplitControllerTests(unittest.TestCase):
    def setUp(self):
        self.clock = [datetime(2026, 11, 20, 19, 0, tzinfo=NY)]
        orig = Location.now
        self.addCleanup(setattr, Location, "now", orig)
        Location.now = lambda loc: self.clock[0]

    def run_at(self, split, h=19):
        s = split_settings(split)
        s["effects"]["slow_twinkle"] = {"label": "Slow twinkle", "colors": ["#FFC58A"], "counts": [1], "custom_mode": 5, "speed": 20}
        s["effects"]["security_white"]["speed"] = 0
        cfg = build_config(s, SECRETS)
        api = TwoControllerAPI()
        c = Controller(cfg, api, weather=FakeWeather())
        self.clock[0] = datetime(2026, 11, 20, h, 0, tzinfo=NY)
        c.tick()
        return c, api

    def test_each_controller_runs_its_own_motion_and_speed(self):
        c, api = self.run_at({"D1": "slow_twinkle", "D2": "security_white"})
        previews = {x[1]: x[2:] for x in api.calls if x[0] == "preview"}
        self.assertEqual(previews, {"D1": (5, 20), "D2": (0, 0)})
        self.assertEqual(api.state, {"D1": 1, "D2": 1})
        self.assertEqual(c.sent_effect["D1"]["mode"], 5)

    def test_a_part_can_leave_a_controller_off_and_the_next_pattern_turns_it_on(self):
        c, api = self.run_at({"D1": "slow_twinkle", "D2": "off"})
        self.assertEqual(api.state, {"D1": 1, "D2": 0})
        self.assertFalse(c.known_on, "not every controller is on")
        c.manual(True, "warm_white")
        self.assertEqual(api.state, {"D1": 1, "D2": 1})

    def test_the_off_controller_is_not_restored_as_wrong(self):
        c, api = self.run_at({"D1": "slow_twinkle", "D2": "off"})
        for _ in range(3):                       # two readings in a row would restore it
            c.last_verify = 0
            c._maintenance(c._target())
        self.assertEqual(api.state["D2"], 0)
        self.assertEqual(c.mismatches, 0)

    def test_safety_net_plan_per_controller(self):
        cfg = build_config(split_settings({"D1": "christmas", "D2": "off"}), SECRETS)
        e = cfg.effects["upstairs_garage"]
        entries = [{"slot": "s", "label": e.label, "month": 11, "day": 20, "start": [18, 0], "end": [23, 0]}]
        slots = {"s": (e, {})}
        en1, sl1 = for_device(entries, slots, "D1")
        self.assertIs(sl1["s"][0], cfg.effects["christmas"])
        self.assertEqual(en1[0]["label"], cfg.effects["christmas"].label)
        en2, sl2 = for_device(entries, slots, "D2")
        self.assertEqual((en2, sl2), ([], {}), "that controller stays off: no timer copy")
        plain = {"s": (cfg.effects["warm_white"], {})}
        self.assertEqual(for_device(entries, plain, "D2")[1], plain)


class SplitServerTests(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.app = App(self.d, start=False)

    def tearDown(self):
        self.app.store.close()
        shutil.rmtree(self.d, ignore_errors=True)

    def test_import_follows_renamed_parts(self):
        s = copy.deepcopy(self.app.store.settings)
        s["effects"]["mine"] = {"label": "Mine", "colors": ["#123456"], "counts": [1]}
        self.app.save_settings(s, s["_rev"])
        incoming = {"effects": {"mine": {"label": "Theirs", "colors": ["#FF0000"], "counts": [1]},
                                "split_it": {"label": "Split", "split": {"X1": "mine", "X2": "off"}}}}
        self.app.import_settings({"settings": incoming, "mode": "merge"})
        effs = self.app.store.settings["effects"]
        self.assertEqual(effs["split_it"]["split"]["X1"], "mine_2")
        self.assertEqual(effs["mine"]["label"], "Mine")

    def test_split_patterns_can_not_be_saved_in_the_trimlight_app(self):
        self.app.store.settings  # noqa
        s = copy.deepcopy(self.app.store.settings)
        s["effects"]["sp"] = {"label": "Sp", "split": {"D1": "christmas"}}
        self.app.save_settings(s, s["_rev"])
        with self.assertRaises(ApiError):
            self.app.save_to_controller({"name": "Sp", "effect": {"label": "Sp", "split": {"D1": "christmas"}}})


class SourceTests(unittest.TestCase):
    JS = (ROOT / "eaveluxos" / "static" / "app.js").read_text(encoding="utf-8")

    def test_zone_brightness_dims_the_zone_color(self):
        self.assertIn("function zoneColor(f, i)", self.JS)
        self.assertIn("HouseFX.dim(c, +f['l' + i].value || 100)", self.JS)

    def test_adjusting_a_line_keeps_its_bulbs(self):
        self.assertIn("if (before && before.bulbs) line.bulbs = { ...before.bulbs };", self.JS)

    def test_both_previews_share_one_motion_model(self):
        self.assertEqual(self.JS.count("HouseFX.colorsAt("), 2)

    def test_patterns_used_by_a_split_can_not_be_deleted_unnoticed(self):
        self.assertIn("the split pattern", self.JS)


if __name__ == "__main__":
    unittest.main()
