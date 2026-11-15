# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""3.18.2: fixes from the 3.18.1 code review, one test (or more) each."""
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
from eaveluxos.controller import Controller
from eaveluxos.schedule import Location, build_config
from eaveluxos.server import AI_PER_DAY, AI_PER_MINUTE, MOOD_MINUTES, SENSITIVE, ApiError, App
from tests.test_controller import FakeAPI, FakeWeather
from tests.test_features318 import SECRETS, curve_settings
from tests.test_triggers316 import NY, nws

HERE = Path(__file__).resolve().parent


class MoodApp(unittest.TestCase):
    def setUp(self):
        self.clock = datetime(2026, 11, 20, 19, 0, tzinfo=NY)
        orig = Location.now
        self.addCleanup(setattr, Location, "now", orig)
        Location.now = lambda loc: self.clock
        self.d = Path(tempfile.mkdtemp())
        self.app = App(self.d, start=False)
        s = copy.deepcopy(self.app.store.settings)
        s["location"].update(latitude=39.95, longitude=-75.17)
        s["rules"] = [{"name": "Night", "on": "18:00", "off": "23:00", "effect": "warm_white"}]
        s["weather_alerts"] = {"enabled": True, "groups": ["winter"], "effect": "severe", "turn_on": False}
        s["mood"] = {"calm": "warm_white", "lively": "christmas", "party": "snowfall"}
        self.app.store.save_settings(s)
        self.app.store.save_secrets(client_id="x", client_secret="y")
        self.app.rebuild()
        self.c = self.app.ctrl
        self.c.api = FakeAPI()
        self.c.devices = [{"deviceId": "D1", "name": "House"}]

    def tearDown(self):
        self.app.store.close()
        shutil.rmtree(self.d, ignore_errors=True)

    def warning(self):
        self.c.wx_alerts.fetch = lambda u: nws("Winter Storm Warning", ends="2099-01-01T00:00:00Z")
        self.c.wx_alerts.refresh(force=True)
        self.assertEqual(self.c._target().reason, "alert")


class ReviewMoodRanking(MoodApp):
    def test_1_mood_never_dismisses_a_weather_warning(self):
        """The most important one (tests/repro_mood_alert.py): music during a
        storm warning used to dismiss the warning for up to 7 days."""
        self.warning()
        self.app.mood("lively")
        self.app.mood("party")
        self.assertEqual(self.c._target().reason, "alert", "the warning stays on top")
        self.assertEqual(self.c.alert_dismissed, {})
        # When the warning ends, mood follow's pattern shows.
        self.c.wx_alerts.fetch = lambda u: {"features": []}
        self.c.wx_alerts.refresh(force=True)
        t = self.c._target()
        self.assertEqual((t.reason, t.effect.key), ("manual", "snowfall"))
        # A choice made by hand still dismisses it, as before (3.16.1).
        self.warning()
        self.c.manual(True, "warm_white")
        self.assertIn("winter storm warning", self.c.alert_dismissed)

    def test_1_repro_script_runs(self):
        r = subprocess.run(["python3", str(HERE / "repro_mood_alert.py")], capture_output=True, text=True,
                           encoding="utf-8", timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertLessEqual(len((HERE / "repro_mood_alert.py").read_text(encoding="utf-8").splitlines()), 20)

    def test_1_mood_doesnt_end_a_music_show(self):
        self.c.music = {"until": None, "since": self.clock}
        self.app.mood("party")
        self.assertEqual(self.c._target().reason, "music")
        self.assertIsNotNone(self.c.music)

    def test_4_quiet_ends_only_mood_follows_pattern(self):
        self.app.mood("lively")
        self.c.manual(True, "warm_white")            # chosen by hand while listening
        self.app.mood("quiet")
        t = self.c._target()
        self.assertEqual((t.reason, t.effect.key), ("manual", "warm_white"), "the hand-picked pattern stays")
        self.c.resume()                               # the user goes back to the schedule
        self.app.mood("lively")
        self.assertEqual(self.c._target().effect.key, "christmas")
        self.app.mood("stop")
        self.assertNotEqual(self.c._target().reason, "manual", "mood's own pattern does end")

    def test_5_a_hand_picked_pattern_wins_until_it_ends(self):
        self.c.manual(True, "warm_white", expires_min=10)
        r = self.app.mood("party")
        self.assertTrue(r["waiting"])
        self.assertEqual(self.c._target().effect.key, "warm_white")
        self.c.override["expires"] = time.time() - 1       # the hand-picked one ends
        self.app.mood("party")
        self.assertEqual(self.c._target().effect.key, "snowfall", "then mood takes over")

    def test_5_one_listening_page_at_a_time(self):
        self.app.mood("calm", "tabA")
        with self.assertRaises(ApiError) as cm:
            self.app.mood("party", "tabB")
        self.assertEqual(cm.exception.code, 409)
        self.assertEqual(self.app.mood("quiet", "tabB"), {"active": False})
        self.assertEqual(self.c._target().effect.key, "warm_white", "the other page can't end it either")
        self.app.mood_state["at"] -= MOOD_MINUTES * 60 + 1      # the first page went silent
        self.assertTrue(self.app.mood("party", "tabB")["active"])
        self.assertEqual(self.app.mood_state["tab"], "tabB")
        with self.assertRaises(ApiError):
            self.app.mood("party", "x" * 41)

    def test_11_the_end_note_names_mood_follow(self):
        self.app.mood("lively")
        self.c.override["expires"] = time.time() - 1
        self.c.next_try = 0
        self.c.tick()
        notes = " ".join(e["msg"] for e in self.c.events)
        self.assertIn("Mood follow ended", notes)
        self.assertNotIn("Preview ended", notes)


class ReviewAi(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.app = App(self.d, start=False)
        self.app.store.save_secrets(ai_key="sk-test")
        self.bodies = []
        reply = {"content": [{"type": "text", "text": json.dumps({"label": "Ice", "colors": ["#80C0FF"], "motion": 0})}]}
        self.app.ai_fetch = lambda url, body, key: self.bodies.append(body) or reply

    def tearDown(self):
        self.app.store.close()
        shutil.rmtree(self.d, ignore_errors=True)

    def test_2_the_ai_key_needs_the_password_again(self):
        self.assertIn("/api/ai/settings", SENSITIVE)

    def test_9_ai_calls_are_limited(self):
        for _ in range(AI_PER_MINUTE):
            self.app.ai_pattern("icy blue")
        with self.assertRaises(ApiError) as cm:
            self.app.ai_pattern("icy blue")
        self.assertEqual(cm.exception.code, 429)
        self.assertEqual(len(self.bodies), AI_PER_MINUTE, "the refused one cost nothing")
        self.app.ai_calls = [time.time() - 3600] * AI_PER_DAY      # a busy day, spread out
        with self.assertRaises(ApiError) as cm:
            self.app.ai_pattern("icy blue")
        self.assertIn("daily limit", str(cm.exception))
        self.app.ai_calls = [time.time() - 86401] * AI_PER_DAY     # yesterday doesn't count
        self.app.ai_pattern("icy blue")

    def test_10_the_model_is_a_setting(self):
        self.app.ai_pattern("icy blue")
        self.assertEqual(self.bodies[-1]["model"], textpattern.AI_MODEL)
        s = copy.deepcopy(self.app.store.settings)
        s["ai"] = {"model": "claude-sonnet-5-5"}
        self.app.store.save_settings(s)
        self.app.ai_pattern("icy blue")
        self.assertEqual(self.bodies[-1]["model"], "claude-sonnet-5-5")
        bad = copy.deepcopy(s)
        bad["ai"] = {"model": "Not a model!"}
        with self.assertRaises(ApiError):
            self.app.validate(bad)

    def test_10_a_retired_model_says_so(self):
        import urllib.error
        import urllib.request
        orig = urllib.request.urlopen
        self.addCleanup(setattr, urllib.request, "urlopen", orig)

        def gone(*a, **k):
            raise urllib.error.HTTPError("u", 404, "Not Found", {}, None)
        urllib.request.urlopen = gone
        with self.assertRaises(ValueError) as cm:
            textpattern.ai_generate("icy", "sk-x", model="claude-old-1")
        self.assertIn("claude-old-1", str(cm.exception))
        self.assertIn("wasn't found", str(cm.exception))

    def test_10_editors_cant_change_the_model_and_files_dont_carry_it(self):
        from eaveluxos.server import HOUSEHOLD_KEYS, PRIVATE_KEYS
        self.assertIn("ai", HOUSEHOLD_KEYS)
        self.assertIn("ai", PRIVATE_KEYS)


class ReviewCurve(unittest.TestCase):
    def setUp(self):
        self.clock = [datetime(2026, 11, 20, 19, 0, tzinfo=NY)]
        orig = Location.now
        self.addCleanup(setattr, Location, "now", orig)
        Location.now = lambda loc: self.clock[0]

    def ctrl(self, **effect):
        s = curve_settings()
        s["effects"]["cw"].update(effect)
        self.api, self.wx = FakeAPI(), FakeWeather()
        return Controller(build_config(s, SECRETS), self.api, weather=self.wx)

    def at(self, c, h, m=0, day=20):
        self.clock[0] = datetime(2026, 11, day, h, m, tzinfo=NY)
        c.next_try = 0
        c.tick()
        return c._target()

    def test_6_a_moving_pattern_steps_every_30_minutes(self):
        self.assertFalse(circadian.moves(build_config(curve_settings(), SECRETS).effects["cw"]))
        c = self.ctrl(custom_mode=6)
        self.assertTrue(circadian.moves(c.cfg.effects["cw"]))
        keys = set()
        for m in range(0, 60, 5):
            keys.add(self.at(c, 23, m).key)
        self.assertEqual(len(keys), 2, "23:00 and 23:30 only, not every 10 minutes")
        c = self.ctrl()                                        # a still pattern: 10-minute steps, as before
        keys = {self.at(c, 23, m).key for m in range(0, 60, 5)}
        self.assertEqual(len(keys), 6)

    def test_6_a_weather_pattern_keeps_its_whites(self):
        c = self.ctrl()
        self.wx.tags = {"snow"}
        t = self.at(c, 23)
        self.assertEqual(t.reason, "weather")
        snow = c.cfg.effects["snowfall"]
        self.assertEqual(t.effect.payload["pixels"], snow.payload["pixels"], "snow white stays snow white")
        self.assertLess(t.levels["brightness"], 200, "but it still dims with the curve")
        self.wx.tags = set()
        t = self.at(c, 23, 10)
        self.assertNotEqual(t.effect.payload["pixels"][0]["color"], c.cfg.effects["cw"].payload["pixels"][0]["color"],
                            "the scheduled pattern's whites still follow the curve")


class ReviewWords(unittest.TestCase):
    def test_8_warm_white_and_white_are_both_colors(self):
        self.assertEqual(textpattern.generate("warm white and white")["colors"], ["#FFC58A", "#FFFFFF"])
        self.assertEqual(textpattern.generate("hot pink and pink")["colors"], ["#FF1080", "#FF60A0"])
        self.assertEqual(textpattern.generate("warm white")["colors"], ["#FFC58A"])
        self.assertEqual(textpattern.generate("white then warm white")["colors"], ["#FFFFFF", "#FFC58A"])


class ReviewPorts(unittest.TestCase):
    """#7 and #12, on the owner's real port layout."""
    @classmethod
    def setUpClass(cls):
        import eaveluxos.api
        from tests import fake_trimlight as F
        cls.F = F
        cls.cloud = F.start()
        cls._saved = eaveluxos.api.BASE_URL
        eaveluxos.api.BASE_URL = f"http://127.0.0.1:{cls.cloud.server_address[1]}/trimlight"

    @classmethod
    def tearDownClass(cls):
        import eaveluxos.api
        eaveluxos.api.BASE_URL = cls._saved

    def setUp(self):
        from tests.test_ports318 import REAL
        F = self.F
        self._ports = copy.deepcopy(F.STATE["dev"]["ports"])
        F.STATE["dev"]["ports"] = copy.deepcopy(REAL)
        self.d = Path(tempfile.mkdtemp())
        self.app = App(self.d, start=False)
        s = copy.deepcopy(self.app.store.settings)
        s["location"].update(latitude=39.95, longitude=-75.16)
        self.app.store.save_settings(s)
        self.app.store.save_secrets(client_id=F.CID, client_secret=F.SECRET)
        self.app.rebuild()
        self.dev = self.app.devices()[0]["id"]

    def tearDown(self):
        self.F.STATE["dev"]["ports"] = self._ports
        self.app.store.close()
        shutil.rmtree(self.d, ignore_errors=True)

    def save(self, ports):
        return self.app.update_device({"deviceId": self.dev, "ports": ports})

    def test_7_saving_some_ports_keeps_the_others_not_connected(self):
        self.save([{"id": 0, "start": 1, "end": 83}, {"id": 1, "start": 84, "end": 138},
                   {"id": 2, "start": 0, "end": 0}, {"id": 3, "start": 0, "end": 0}])
        self.save([{"id": 0, "start": 1, "end": 90}])          # an older page or the API: port 1 only
        self.assertEqual(self.app.store.settings["service"]["unused_ports"], {self.dev: [2, 3]})
        self.assertEqual(self.app.address_space(), 138)
        self.save([{"id": 2, "start": 139, "end": 200}])       # port 3 is plugged in after all
        self.assertEqual(self.app.store.settings["service"]["unused_ports"], {self.dev: [3]})

    def test_12_a_port_given_bulbs_here_isnt_taken_for_never_set_up(self):
        ports = {p["id"]: p for p in self.app.devices()[0]["ports"]}
        self.assertFalse(any(p["set_here"] for p in ports.values()))
        self.save([{"id": 0, "start": 1, "end": 83}, {"id": 1, "start": 84, "end": 138},
                   {"id": 2, "start": 1, "end": 600}, {"id": 3, "start": 0, "end": 0}])
        ports = {p["id"]: p for p in self.app.devices()[0]["ports"]}
        self.assertEqual([ports[i]["set_here"] for i in range(4)], [True, True, False, False],
                         "1-600 sent back unchanged is still the never-set-up reading")
        s = copy.deepcopy(self.app.store.settings)               # "It's really connected"
        s["service"]["ports_set"][self.dev].append(2)
        self.app.store.save_settings(s)
        self.assertTrue(self.app.devices()[0]["ports"][2]["set_here"])
        bad = copy.deepcopy(s)
        bad["service"]["ports_set"] = {self.dev: ["x"]}
        with self.assertRaises(ApiError):
            self.app.validate(bad)

    def test_12_the_page_checks_set_here(self):
        js = (HERE.parent / "eaveluxos" / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn("!p.set_here && p.start === 1 && p.end === 600", js)
        self.assertIn("data-portreal", js)


class ReviewHardwareTest(unittest.TestCase):
    def test_13_a_cloud_that_takes_0_0_is_reported_without_failing(self):
        from tests import fake_trimlight as F
        from tests.test_open_issues import HardwareTestScript
        F.STATE["port_off_ok"] = True
        try:
            code, report, before, after = HardwareTestScript._run(self)
        finally:
            F.STATE.pop("port_off_ok", None)
        self.assertIn("[NO  ] Port 0-0 refused", report)
        self.assertIn("had no bulbs before", report)
        self.assertEqual(after["ports"], before["ports"])


class ReviewSources(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node.js isn't installed")
    def test_3_mood_reports_by_the_clock(self):
        r = subprocess.run(["node", str(HERE / "review318_check.js")], capture_output=True, text=True,
                           encoding="utf-8", timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_3_the_page_uses_the_clock_and_one_tab(self):
        js = (HERE.parent / "eaveluxos" / "static" / "app.js").read_text(encoding="utf-8")
        self.assertNotIn("ticks % 100", js)
        self.assertIn("new Mood.Reporter()", js)
        self.assertIn("createScriptProcessor", js)
        self.assertIn("tab: MOOD.tab", js)
        self.assertIn("'pagehide'", js)


if __name__ == "__main__":
    unittest.main()
