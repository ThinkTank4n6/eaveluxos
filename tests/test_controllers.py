# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Several controllers on one account: the Lights page lists each one, and
changes go to the controller picked, never another."""
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

PORTS = [{"id": 0, "start": 1, "end": 60}] + [{"id": i, "start": 0, "end": 0} for i in (1, 2, 3)]


class SeveralControllersTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import eaveluxos.api
        cls._fake = copy.deepcopy({k: F.STATE.get(k) for k in ("dev", "more", "fail_get")})
        deck = copy.deepcopy(F.STATE["dev"])
        deck.update(deviceId="TL-DECK", name="Deck", ports=copy.deepcopy(PORTS))
        garage = copy.deepcopy(F.STATE["dev"])
        garage.update(deviceId="TL-GARAGE", name="Garage", connectivity=0, switchState=0)
        F.STATE["dev"]["name"] = "House"
        F.STATE["more"] = [deck, garage]
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
        s["service"] = {**s["service"], "devices": ["TL-EDGE-01", "TL-DECK"]}
        cls.app.store.save_settings(s)
        cls.app.store.save_secrets(client_id=F.CID, client_secret=F.SECRET)
        cls.app.rebuild()
        cls.srv = make_server(cls.app, "127.0.0.1", 0)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        import eaveluxos.api
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.app.store.close()
        shutil.rmtree(cls.dir, ignore_errors=True)
        for k, v in cls._fake.items():
            if v is None:
                F.STATE.pop(k, None)
            else:
                F.STATE[k] = v
        env, base = cls._saved
        if env is None:
            os.environ.pop("TRIMLIGHT_API_BASE", None)
        else:
            os.environ["TRIMLIGHT_API_BASE"] = env
        eaveluxos.api.BASE_URL = base

    def tearDown(self):
        F.STATE.pop("fail_get", None)

    def call(self, path, body=None):
        h = {"Content-Type": "application/json", "X-Requested-With": "eaveluxos"}
        r = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}",
                                   data=None if body is None else json.dumps(body).encode(), headers=h)
        try:
            with urllib.request.urlopen(r, timeout=30) as x:
                return x.status, json.loads(x.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def devices(self):
        st, r = self.call("/api/devices")
        self.assertEqual(st, 200, r)
        return {d["id"]: d for d in (r if isinstance(r, list) else r.get("devices", r))}

    def ctrl(self, did):
        return F.STATE["dev"] if did == "TL-EDGE-01" else next(x for x in F.STATE["more"] if x["deviceId"] == did)

    def test_every_controller_is_listed_with_its_own_details(self):
        d = self.devices()
        self.assertEqual(set(d), {"TL-EDGE-01", "TL-DECK", "TL-GARAGE"})
        self.assertEqual((d["TL-DECK"]["name"], d["TL-DECK"]["ports"][0]["end"]), ("Deck", 60))
        self.assertEqual(d["TL-EDGE-01"]["ports"][0]["end"], 83)
        self.assertFalse(d["TL-GARAGE"]["online"])
        self.assertEqual(d["TL-GARAGE"]["switch"], 0)
        self.assertEqual({k: v["selected"] for k, v in d.items()},
                         {"TL-EDGE-01": True, "TL-DECK": True, "TL-GARAGE": False})

    def test_ports_saved_to_the_picked_controller_only(self):
        house_before = copy.deepcopy(self.ctrl("TL-EDGE-01")["ports"])
        new = [{"id": 0, "start": 1, "end": 75}] + [{"id": i, "start": 0, "end": 0} for i in (1, 2, 3)]
        st, r = self.call("/api/device/update", {"deviceId": "TL-DECK", "ports": new})
        self.assertEqual(st, 200, r)
        self.assertEqual(self.ctrl("TL-DECK")["ports"][0]["end"], 75)
        self.assertEqual(self.ctrl("TL-EDGE-01")["ports"], house_before)
        self.call("/api/device/update", {"deviceId": "TL-DECK", "ports": copy.deepcopy(PORTS)})

    def test_rename_goes_to_the_picked_controller_only(self):
        st, r = self.call("/api/device/update", {"deviceId": "TL-GARAGE", "name": "Garage & Shed"})
        self.assertEqual(st, 200, r)
        self.assertEqual(self.ctrl("TL-GARAGE")["name"], "Garage & Shed")
        self.assertEqual((self.ctrl("TL-EDGE-01")["name"], self.ctrl("TL-DECK")["name"]), ("House", "Deck"))
        self.call("/api/device/update", {"deviceId": "TL-GARAGE", "name": "Garage"})

    def test_one_controller_not_answering_does_not_hide_the_others(self):
        F.STATE["fail_get"] = {"TL-DECK"}
        d = self.devices()
        self.assertIn("error", d["TL-DECK"])
        self.assertNotIn("error", d["TL-EDGE-01"])
        self.assertEqual(d["TL-EDGE-01"]["ports"][0]["end"], 83)

    def test_no_controller_named_is_refused(self):
        st, r = self.call("/api/device/update", {"name": "X"})
        self.assertEqual(st, 400)


if __name__ == "__main__":
    unittest.main()
