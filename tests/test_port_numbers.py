# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Ports numbered 1-4 by the controller (3.13.2). Trimlight Edge firmware
1.17.77 reports its ports as ids 1-4; the Lights tab assumed 0-3, so every
port showed one row down, port 4 disappeared, and saving would have written
that shifted layout."""
import copy
import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from tests import fake_trimlight as F
from eaveluxos.api import TrimlightAPI, port_base

# The layout in the owner's controller backup of Nov 13, 2026.
REAL = [{"id": 1, "start": 1, "end": 83}, {"id": 2, "start": 84, "end": 138},
        {"id": 3, "start": 1, "end": 600}, {"id": 4, "start": 1, "end": 600}]


class PortBase(unittest.TestCase):
    def test_detects_numbering(self):
        self.assertEqual(port_base(REAL), 1)
        self.assertEqual(port_base([{"id": i, "start": 0, "end": 0} for i in range(4)]), 0)
        self.assertEqual(port_base([]), 0)
        self.assertEqual(port_base([{"id": 4, "start": 1, "end": 2}]), 1)


class LightsTabPorts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import eaveluxos.api
        cls.cloud = F.start()
        cls._saved = (os.environ.get("TRIMLIGHT_API_BASE"), eaveluxos.api.BASE_URL)
        os.environ["TRIMLIGHT_API_BASE"] = f"http://127.0.0.1:{cls.cloud.server_address[1]}/trimlight"
        eaveluxos.api.BASE_URL = os.environ["TRIMLIGHT_API_BASE"]
        from eaveluxos.server import App
        cls.dir = Path(tempfile.mkdtemp())
        cls.app = App(cls.dir, start=False)
        s = copy.deepcopy(cls.app.store.settings)
        s["location"].update(latitude=39.95, longitude=-75.16)
        s["setup_done"] = True
        cls.app.store.save_settings(s)
        cls.app.store.save_secrets(client_id=F.CID, client_secret=F.SECRET)

    @classmethod
    def tearDownClass(cls):
        import eaveluxos.api
        cls.app.store.close()
        shutil.rmtree(cls.dir, ignore_errors=True)
        env, base = cls._saved
        if env is None:
            os.environ.pop("TRIMLIGHT_API_BASE", None)
        else:
            os.environ["TRIMLIGHT_API_BASE"] = env
        eaveluxos.api.BASE_URL = base

    def setUp(self):
        self.saved_ports = copy.deepcopy(F.STATE["dev"]["ports"])
        self.app._port_base.clear()

    def tearDown(self):
        F.STATE["dev"]["ports"] = self.saved_ports

    def listing(self):
        return next(d for d in self.app.devices() if d["id"] == "TL-EDGE-01")

    def set_ports(self, ports):
        F.STATE["dev"]["ports"] = copy.deepcopy(ports)

    def test_shows_ports_1_to_4_as_the_controller_has_them(self):
        self.set_ports(REAL)
        ports = self.listing()["ports"]
        self.assertEqual([(p["id"], p["start"], p["end"]) for p in ports],
                         [(0, 1, 83), (1, 84, 138), (2, 1, 600), (3, 1, 600)])   # screen rows Port 1..4

    def test_numbering_is_logged_once(self):
        """Review #8 (3.14.1): say when a controller is read as 1-4."""
        self.set_ports(REAL)
        with self.assertLogs("eaveluxos.web", "INFO") as cm:
            self.listing()
            self.listing()
        self.assertEqual(sum("numbers its ports 1-4" in m for m in cm.output), 1)

    def test_save_writes_back_in_the_controllers_numbers(self):
        self.set_ports(REAL)
        self.listing()
        F.STATE["log"].clear()
        self.app.update_device({"deviceId": "TL-EDGE-01", "ports": [{"id": 0, "start": 1, "end": 90}]})
        sent = next(b for p, b in F.STATE["log"] if p == "/device/update")["payload"]["ports"]
        self.assertEqual(sent, [{"id": 1, "start": 1, "end": 90}])

    def test_save_before_listing_asks_the_controller_first(self):
        self.set_ports(REAL)
        F.STATE["log"].clear()
        self.app.update_device({"deviceId": "TL-EDGE-01", "ports": [{"id": 3, "start": 1, "end": 500}]})
        sent = next(b for p, b in F.STATE["log"] if p == "/device/update")["payload"]["ports"]
        self.assertEqual(sent, [{"id": 4, "start": 1, "end": 500}])

    def test_zero_based_controllers_unchanged(self):
        ports = self.listing()["ports"]
        self.assertEqual([p["id"] for p in ports], [p["id"] for p in self.saved_ports])


class SafetyNetLeavesReusedNumbers(unittest.TestCase):
    def test_remove_keeps_a_new_pattern_that_took_over_its_number(self):
        from eaveluxos.safety import SafetyNet
        from tests.test_safety import BASE
        d = Path(tempfile.mkdtemp())
        saved = copy.deepcopy(F.STATE["dev"])
        try:
            F.STATE["dev"]["effects"].append({"id": 20, "name": "My new pattern", "category": 1, "mode": 0,
                                              "pixels": [{"index": 0, "count": 1, "color": 255, "disable": False}]})
            net = SafetyNet(d)
            net.state["devices"]["TL-EDGE-01"] = {"effects": {"fall|{}": 20}, "calendar": []}
            net._save()
            F.STATE["log"].clear()
            api = TrimlightAPI(F.CID, F.SECRET, base_url=BASE)
            self.assertTrue(net.remove(api, ["TL-EDGE-01"], datetime(2026, 11, 13, 19, 0, tzinfo=ZoneInfo("America/New_York"))))
            self.assertNotIn("/device/effect/delete", [p for p, _ in F.STATE["log"]])
            self.assertIn(20, [e["id"] for e in F.STATE["dev"]["effects"]])
        finally:
            F.STATE["dev"] = saved
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
