# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""The status webhook, and the Home Assistant package in tools/home-assistant."""
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

ROOT = Path(__file__).resolve().parent.parent
TOKEN = "t" * 32


class StatusWebhookTests(unittest.TestCase):
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

    def req(self, method, path, body=None, token=TOKEN):
        h = {"Content-Type": "application/json"}
        if token:
            h["X-Token"] = token
        r = urllib.request.Request(self.base + path, method=method, headers=h,
                                   data=None if body is None else json.dumps(body).encode())
        try:
            with urllib.request.urlopen(r, timeout=30) as x:
                return x.status, json.loads(x.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def test_status_with_get_like_home_assistant(self):
        before = len(self.app.ctrl.events)
        st, r = self.req("GET", "/api/hook/status")
        self.assertEqual(st, 200, r)
        for k in ("on", "effect", "effect_key", "reason", "source", "brightness", "speed", "flash", "music", "patterns"):
            self.assertIn(k, r)
        keys = {p["key"]: p["label"] for p in r["patterns"]}
        self.assertEqual(keys["christmas"], "Christmas")
        self.assertEqual(len(self.app.ctrl.events), before)   # polling isn't logged

    def test_status_with_post_too(self):
        self.assertEqual(self.req("POST", "/api/hook/status", {})[0], 200)

    def test_status_needs_the_token_in_the_header(self):
        self.assertEqual(self.req("GET", "/api/hook/status", token=None)[0], 403)
        self.assertEqual(self.req("GET", "/api/hook/status", token="wrong")[0], 403)
        st, r = self.req("GET", f"/api/hook/status?token={TOKEN}", token=None)
        self.assertEqual(st, 400)

    def test_get_cannot_change_the_lights(self):
        self.req("POST", "/api/hook/off", {})
        st, _ = self.req("GET", "/api/hook/on")
        self.assertNotEqual(st, 200)
        self.assertFalse(self.req("GET", "/api/hook/status")[1]["on"])

    def test_what_home_assistant_sends(self):
        st, r = self.req("POST", "/api/hook/on", {"effect": "christmas"})            # set_effect
        self.assertEqual((st, r["on"], r["effect_key"]), (200, True, "christmas"), r)
        st, r = self.req("POST", "/api/hook/levels", {"brightness": "128"})           # set_level (text)
        self.assertEqual((st, r["brightness"]), (200, 128), r)
        st, r = self.req("POST", "/api/hook/off", {})                                 # turn_off
        self.assertFalse(r["on"])
        st, r = self.req("POST", "/api/hook/on", {})                                  # turn_on: tonight's pattern
        self.assertTrue(r["on"])
        self.req("POST", "/api/hook/resume", {})


class PackageFileTests(unittest.TestCase):
    def load(self):
        try:
            import yaml
        except ImportError:
            self.skipTest("PyYAML not installed")

        class Loader(yaml.SafeLoader):
            pass
        Loader.add_constructor("!secret", lambda loader, node: f"<secret:{node.value}>")
        return yaml.load((ROOT / "tools/home-assistant/eaveluxos.yaml").read_text(encoding="utf-8"), Loader=Loader)

    def test_pieces_fit_together(self):
        cfg = self.load()
        rest = cfg["rest"][0]
        self.assertEqual((rest["method"], rest["resource"]), ("GET", "<secret:eaveluxos_status_url>"))
        self.assertEqual(rest["headers"]["X-Token"], "<secret:eaveluxos_token>")
        self.assertEqual(rest["sensor"][0]["unique_id"], "eaveluxos_pattern")   # sensor.eaveluxos_pattern
        cmd = cfg["rest_command"]["eaveluxos"]
        self.assertIn("/api/hook/{{ hook }}", cmd["url"])
        self.assertEqual((cmd["method"], cmd["headers"]["X-Token"]), ("POST", "<secret:eaveluxos_token>"))
        light = cfg["light"][0]["lights"]["house_lights"]
        for k in ("turn_on", "turn_off", "set_level", "set_effect"):
            self.assertEqual(light[k][0]["action"], "rest_command.eaveluxos", k)
        hooks = {light[k][0]["data"]["hook"] for k in ("turn_on", "turn_off", "set_level", "set_effect")}
        self.assertEqual(hooks, {"on", "off", "levels"})
        text = json.dumps(cfg)
        self.assertNotIn("sensor.eaveluxos_status", text)                          # every reference is the real sensor

    def test_templates(self):
        try:
            import jinja2
        except ImportError:
            self.skipTest("Jinja2 not installed")
        cfg = self.load()
        state = {"on": True, "brightness": 200, "patterns": [{"key": "christmas", "label": "Christmas"},
                                                             {"key": "fourth_of_july", "label": "Fourth of July"}]}
        env = jinja2.Environment()
        env.filters["to_json"] = json.dumps
        env.globals["state_attr"] = lambda ent, attr: state.get(attr)
        light = cfg["light"][0]["lights"]["house_lights"]
        body = light["set_effect"][0]["data"]["body"]["effect"]
        self.assertEqual(env.from_string(body).render(effect="Fourth of July").strip(), "fourth_of_july")
        self.assertEqual(env.from_string(body).render(effect="Nope").strip(), "")
        effects = env.from_string(light["effect_list_template"]).render()
        self.assertIn("Fourth of July", effects)
        sensor = cfg["rest"][0]["sensor"][0]["value_template"]
        self.assertEqual(env.from_string(sensor).render(value_json={"on": False, "effect": "X"}), "Off")
        payload = cfg["rest_command"]["eaveluxos"]["payload"]
        self.assertEqual(json.loads(env.from_string(payload).render(body={"brightness": "128"})), {"brightness": "128"})
        self.assertEqual(json.loads(env.from_string(payload).render()), {})


if __name__ == "__main__":
    unittest.main()
