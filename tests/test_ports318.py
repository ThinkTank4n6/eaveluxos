# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""3.18.1: Trimlight has no "off" for a port. Saving start 0, end 0 was
refused ("code 12000 (Invalid parameter [port -> start])"); a port marked
not connected now keeps what the controller holds, and the app leaves it out
of the bulb count. The ports below are the owner's real controller
(firmware 1.17.77): ports 1-4, the two unused ones reading bulbs 1-600."""
import copy
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from tests import fake_trimlight as F

REAL = [{"id": 1, "start": 1, "end": 83}, {"id": 2, "start": 84, "end": 138},
        {"id": 3, "start": 1, "end": 600}, {"id": 4, "start": 1, "end": 600}]
ROOT = Path(__file__).resolve().parent.parent


class PortTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import eaveluxos.api
        cls.cloud = F.start()
        cls._saved = eaveluxos.api.BASE_URL
        eaveluxos.api.BASE_URL = f"http://127.0.0.1:{cls.cloud.server_address[1]}/trimlight"

    @classmethod
    def tearDownClass(cls):
        import eaveluxos.api
        eaveluxos.api.BASE_URL = cls._saved

    def setUp(self):
        from eaveluxos.server import App
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
        F.STATE["dev"]["ports"] = self._ports
        self.app.store.close()
        shutil.rmtree(self.d, ignore_errors=True)

    def save(self, ports):
        return self.app.update_device({"deviceId": self.dev, "ports": ports})

    def test_the_cloud_refuses_start_0(self):
        from eaveluxos.api import TrimlightAPI, TrimlightError
        api = TrimlightAPI(F.CID, F.SECRET)
        with self.assertRaises(TrimlightError) as cm:
            api.update_device(self.dev, {"ports": [{"id": 3, "start": 0, "end": 0}]})
        self.assertIn("port -> start", str(cm.exception))

    def test_not_connected_ports_keep_the_controllers_numbers(self):
        """What the Lights tab sends for "Not connected": start 0, end 0."""
        before = self.app.devices()[0]
        self.assertEqual(self.app._bulbs, 600, "the never-set-up ports used to count")
        self.save([{"id": 0, "start": 1, "end": 83}, {"id": 1, "start": 84, "end": 138},
                   {"id": 2, "start": 0, "end": 0}, {"id": 3, "start": 0, "end": 0}])
        self.assertEqual(F.STATE["dev"]["ports"], REAL, "nothing invalid sent; the controller is unchanged")
        self.assertEqual(self.app.store.settings["service"]["unused_ports"], {self.dev: [2, 3]})
        ports = self.app.devices()[0]["ports"]
        self.assertEqual([p["unused"] for p in ports], [False, False, True, True])
        self.assertEqual(self.app.address_space(), 138)
        self.assertEqual(len(before["ports"]), 4)

    def test_a_changed_connected_port_is_still_saved(self):
        self.save([{"id": 0, "start": 1, "end": 90}, {"id": 1, "start": 91, "end": 145},
                   {"id": 2, "start": 0, "end": 0}, {"id": 3, "start": 0, "end": 0}])
        self.assertEqual(F.STATE["dev"]["ports"][:2], [{"id": 1, "start": 1, "end": 90}, {"id": 2, "start": 91, "end": 145}])
        self.assertEqual(self.app.address_space(), 145)

    def test_connecting_a_port_again(self):
        self.save([{"id": 0, "start": 1, "end": 83}, {"id": 1, "start": 84, "end": 138},
                   {"id": 2, "start": 0, "end": 0}, {"id": 3, "start": 0, "end": 0}])
        self.save([{"id": 0, "start": 1, "end": 83}, {"id": 1, "start": 84, "end": 138},
                   {"id": 2, "start": 139, "end": 200}, {"id": 3, "start": 0, "end": 0}])
        self.assertEqual(self.app.store.settings["service"]["unused_ports"], {self.dev: [3]})
        self.assertEqual(F.STATE["dev"]["ports"][2], {"id": 3, "start": 139, "end": 200})
        self.save([{"id": i, "start": s, "end": e} for i, (s, e) in enumerate(((1, 83), (84, 138), (139, 200), (201, 260)))])
        self.assertNotIn(self.dev, self.app.store.settings["service"].get("unused_ports", {}))

    def test_a_port_with_no_valid_numbers_is_left_out(self):
        F.STATE["dev"]["ports"][3] = {"id": 4, "start": 0, "end": 0}       # how some controllers report it
        self.save([{"id": 0, "start": 1, "end": 83}, {"id": 1, "start": 84, "end": 138},
                   {"id": 2, "start": 0, "end": 0}, {"id": 3, "start": 0, "end": 0}])
        self.assertEqual(F.STATE["dev"]["ports"][3], {"id": 4, "start": 0, "end": 0})

    def test_every_port_off_is_still_refused(self):
        from eaveluxos.server import ApiError
        with self.assertRaises(ApiError):
            self.save([{"id": i, "start": 0, "end": 0} for i in range(4)])

    def test_malformed_list_is_refused(self):
        from eaveluxos.server import ApiError
        s = copy.deepcopy(self.app.store.settings)
        s.setdefault("service", {})["unused_ports"] = {self.dev: [7]}
        with self.assertRaises(ApiError):
            self.app.save_settings(s, s["_rev"])

    def test_screens(self):
        js = (ROOT / "eaveluxos" / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn(">Not connected</label>", js)
        self.assertIn("p.end > 0 && !p.unused", js)
        self.assertIn("reads' : 'read'} bulbs 1\u2013600", js)
        self.assertIn("await loadSettings().catch(() => {}); VIEWS.lights();", js)


if __name__ == "__main__":
    unittest.main()
