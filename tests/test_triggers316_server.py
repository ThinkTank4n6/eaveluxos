# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""3.16 end to end: webhook alerts with a pattern, zone and length; the
triggers endpoint; dismissing a weather alert; a score celebration."""
import copy
import json
import os
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from tests import fake_trimlight as F
from tests.test_triggers316 import nws

TOKEN = "z" * 32
H = {"Content-Type": "application/json", "X-Requested-With": "eaveluxos"}


class TriggerServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import eaveluxos.api
        cls.cloud = F.start()
        cls._saved = (os.environ.get("TRIMLIGHT_API_BASE"), eaveluxos.api.BASE_URL)
        os.environ["TRIMLIGHT_API_BASE"] = f"http://127.0.0.1:{cls.cloud.server_address[1]}/trimlight"
        eaveluxos.api.BASE_URL = os.environ["TRIMLIGHT_API_BASE"]
        from eaveluxos.server import App, make_server
        cls.dir = Path(tempfile.mkdtemp())
        cls.app = App(cls.dir, start=False)
        s = copy.deepcopy(cls.app.store.settings)
        s["location"].update(latitude=39.95, longitude=-75.16)
        s["setup_done"] = True
        s["map"] = {"zones": [{"name": "Front porch", "start": 11, "end": 30}]}
        cls.app.store.save_settings(s)
        cls.app.store.save_secrets(client_id=F.CID, client_secret=F.SECRET, webhook_token=TOKEN)
        cls.app.rebuild()
        cls.srv = make_server(cls.app, "127.0.0.1", 0)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        import eaveluxos.api
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.app.store.close()
        shutil.rmtree(cls.dir, ignore_errors=True)
        env, base = cls._saved
        if env is None:
            os.environ.pop("TRIMLIGHT_API_BASE", None)
        else:
            os.environ["TRIMLIGHT_API_BASE"] = env
        eaveluxos.api.BASE_URL = base

    def setUp(self):
        self.app.ctrl.stop_flash()

    def hook(self, action, body):
        r = urllib.request.Request(f"{self.base}/api/hook/{action}", method="POST",
                                   headers={"Content-Type": "application/json", "X-Token": TOKEN},
                                   data=json.dumps(body).encode())
        try:
            with urllib.request.urlopen(r, timeout=30) as x:
                return x.status, json.loads(x.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def test_webhook_zone_alert_reaches_the_controller(self):
        st, r = self.hook("flash", {"effect": "package", "zone": "Front porch", "seconds": 20, "label": "Package"})
        self.assertEqual(st, 200, r)
        self.assertTrue(r["flash"])
        self.assertEqual(r["source"], "Package")
        sent = F.STATE["dev"]["currentEffect"]
        bulbs = []
        for p in sent["pixels"]:
            bulbs += [None if p["disable"] else p["color"]] * p["count"]
        self.assertEqual(len(bulbs), 138)                      # the controller's bulbs (last port end)
        self.assertEqual(set(bulbs[10:30]), {0x00FF00})
        self.assertEqual(set(bulbs[:10] + bulbs[30:]), {None})
        left = (self.app.ctrl.flash["until"] - self.app.ctrl.cfg.loc.now()).total_seconds()
        self.assertTrue(15 <= left <= 20, left)

    def test_webhook_color_defaults_to_30_seconds_and_mistakes_are_400(self):
        st, r = self.hook("flash", {"color": "#FF0000"})
        self.assertEqual(st, 200, r)
        left = (self.app.ctrl.flash["until"] - self.app.ctrl.cfg.loc.now()).total_seconds()
        self.assertTrue(25 <= left <= 30, left)
        for bad in ({"effect": "nope"}, {"effect": "alarm", "zone": "Garage"}, {"color": "#12"}, {"effect": "alarm", "seconds": "soon"}):
            with self.subTest(bad=bad):
                st, r = self.hook("flash", bad)
                self.assertEqual(st, 400, r)

    def test_plain_flash_is_still_the_security_flash(self):
        st, r = self.hook("flash", {})
        self.assertEqual(st, 200, r)
        self.assertEqual(r["source"], "Security flash")
        self.assertEqual(r["effect_key"], "security_white")

    def test_triggers_endpoint_and_dismiss(self):
        r = urllib.request.Request(f"{self.base}/api/triggers", headers=H)
        with urllib.request.urlopen(r, timeout=10) as x:
            tr = json.loads(x.read())
        self.assertIn("package", [p["key"] for p in tr["presets"]])
        self.assertEqual(tr["zones"][0]["name"], "Front porch")
        self.assertIn("tornado", [g["key"] for g in tr["alert_groups"]])
        # dismiss_alert is a known webhook action (nothing to dismiss: still fine)
        self.assertEqual(self.hook("dismiss_alert", {})[0], 200)

    def test_weather_alert_settings_round_trip(self):
        s = copy.deepcopy(self.app.store.settings)
        s["weather_alerts"] = {"enabled": True, "groups": ["winter"], "effect": "severe", "turn_on": True}
        self.app.store.save_settings(s)
        self.app.rebuild()
        c = self.app.ctrl
        self.assertIsNotNone(c.wx_alerts)
        c.wx_alerts.fetch = lambda url: nws("Winter Storm Warning", ends="2099-01-01T00:00:00Z")
        c.wx_alerts.refresh(force=True)
        c.tick(maintenance=False)
        self.assertEqual(c.status()["target"]["reason"], "alert")
        self.assertEqual(self.hook("dismiss_alert", {})[0], 200)
        self.assertNotEqual(c.status()["target"]["reason"], "alert")
        s = copy.deepcopy(self.app.store.settings)
        s["weather_alerts"]["enabled"] = False
        self.app.store.save_settings(s)
        self.app.rebuild()
        self.assertIsNone(self.app.ctrl.wx_alerts)

    def test_score_celebration_flashes_team_colors_moving(self):
        s = copy.deepcopy(self.app.store.settings)
        s["effects"]["team_nfl_phi"] = {"label": "Eagles colors", "colors": ["#004C54", "#FFFFFF"], "counts": [4, 4], "custom_mode": 0}
        s["gameday"] = {"enabled": True, "celebrate_seconds": 15, "celebrate_only_when_on": False,
                        "teams": [{"league": "nfl", "team": "phi", "name": "Eagles", "effect": "team_nfl_phi", "celebrate": True}]}
        self.app.store.save_settings(s)
        self.app.rebuild()
        team = {**self.app.cfg.celebrate["nfl-phi"], "key": "nfl-phi"}
        self.assertTrue(self.app.celebrate(team, 7, {}))
        t = self.app.ctrl._target(commit=False)
        self.assertEqual((t.reason, t.source), ("flash", "Eagles scored!"))
        self.assertEqual(t.effect.payload["mode"], 1)                       # chase, not static
        self.assertEqual(self.app.cfg.effects["team_nfl_phi"].payload["mode"], 0)   # the pattern itself is untouched
        self.assertFalse(self.app.celebrate({**team, "key": "mlb-phi"}, 1, {}))  # not a celebrating team

    def test_alarm_webhook_is_urgent_and_a_package_waits(self):
        """3.16.1 review #1: a package alert can't end an alarm; the reply says so."""
        st, r = self.hook("flash", {"effect": "alarm", "minutes": 10, "label": "Alarm"})
        self.assertEqual((st, r["flash_started"]), (200, True))
        st, r = self.hook("flash", {"effect": "package", "seconds": 15, "label": "Package"})
        self.assertEqual((st, r["flash_started"], r["source"]), (200, False, "Alarm"))
        st, r = self.hook("flash", {"effect": "package", "seconds": 15, "label": "Package", "urgent": True})
        self.assertEqual((r["flash_started"], r["source"]), (True, "Package"))

    def test_celebrate_uses_the_schedulers_own_settings(self):
        """3.16.1 review #14: settings swapped at that moment can't mix."""
        s = copy.deepcopy(self.app.store.settings)
        s["effects"]["team_nfl_phi"] = {"label": "Eagles colors", "colors": ["#004C54"], "counts": [4], "custom_mode": 0}
        s["gameday"] = {"enabled": True, "celebrate_only_when_on": False,
                        "teams": [{"league": "nfl", "team": "phi", "name": "Eagles", "effect": "team_nfl_phi", "celebrate": True}]}
        self.app.store.save_settings(s)
        self.app.rebuild()
        team = {**self.app.ctrl.cfg.celebrate["nfl-phi"], "key": "nfl-phi"}
        real, self.app.cfg = self.app.cfg, None              # mid-rebuild
        try:
            self.assertTrue(self.app.celebrate(team, 7, {}))
        finally:
            self.app.cfg = real


if __name__ == "__main__":
    unittest.main()
