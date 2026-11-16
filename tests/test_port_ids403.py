# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""4.0.3: saving ports failed with code 12000 "Invalid parameter [port -> id]"
on a controller that reports its ports as 1-4 (firmware 1.17.77). A refused
save changes nothing, so the app tries the other numbering once, remembers
what worked and reads the controller back to check."""
import copy
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from tests import fake_trimlight as F
from tests.test_port_numbers import REAL

DEV = "TL-EDGE-01"


class PortIds(unittest.TestCase):
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
        self.saved = copy.deepcopy(F.STATE["dev"]["ports"])
        F.STATE["dev"]["ports"] = copy.deepcopy(REAL)
        self.app._port_base.clear()
        self.app._port_write_base.clear()
        F.STATE["log"].clear()

    def tearDown(self):
        F.STATE["dev"]["ports"] = self.saved
        F.STATE.pop("write_from_zero", None)

    def updates(self):
        return [b["payload"]["ports"] for p, b in F.STATE["log"] if p == "/device/update" and "ports" in b["payload"]]

    def screen(self):          # what Save to controller sends: all four rows, 3 and 4 not connected
        return {"deviceId": DEV, "ports": [{"id": 0, "start": 1, "end": 90}, {"id": 1, "start": 91, "end": 138},
                                           {"id": 2, "start": 0, "end": 0}, {"id": 3, "start": 0, "end": 0}]}

    def test_cloud_that_takes_0_to_3_saves_the_right_ports(self):
        F.STATE["write_from_zero"] = True
        with self.assertLogs("eaveluxos.web", "WARNING") as cm:
            r = self.app.update_device(self.screen())
        self.assertEqual(r, {"ok": True})
        self.assertEqual(F.STATE["dev"]["ports"], [{"id": 1, "start": 1, "end": 90}, {"id": 2, "start": 91, "end": 138},
                                                   {"id": 3, "start": 1, "end": 600}, {"id": 4, "start": 1, "end": 600}])
        tries = self.updates()
        self.assertEqual([[p["id"] for p in t] for t in tries], [[1, 2, 3, 4], [0, 1, 2, 3]])
        self.assertTrue(any("saved numbered 0-3" in m for m in cm.output))
        F.STATE["log"].clear()                       # remembered: the next save goes straight through
        self.app.update_device({"deviceId": DEV, "ports": [{"id": 1, "start": 91, "end": 140}]})
        self.assertEqual([[p["id"] for p in t] for t in self.updates()], [[1]])
        self.assertEqual(F.STATE["dev"]["ports"][1], {"id": 2, "start": 91, "end": 140})

    def test_cloud_that_takes_1_to_4_sends_once(self):
        self.app.update_device(self.screen())
        self.assertEqual([[p["id"] for p in t] for t in self.updates()], [[1, 2, 3, 4]])
        self.assertEqual(F.STATE["dev"]["ports"][0], {"id": 1, "start": 1, "end": 90})

    def test_other_refusals_are_not_retried(self):
        F.STATE["write_from_zero"] = True
        self.app._port_write_base[DEV] = 0
        from eaveluxos.server import ApiError
        with self.assertRaises(ApiError) as cm:
            self.app.update_device({"deviceId": DEV, "ports": [{"id": 0, "start": 50, "end": 10}]})
        self.assertEqual(len(self.updates()), 0, "refused here before Trimlight is asked")
        self.app.update_device({"deviceId": DEV, "ports": [{"id": 0, "start": 1, "end": 90}]})
        self.assertEqual(len(self.updates()), 1)
        self.assertIn("start", str(cm.exception))

    def test_refused_both_ways_changes_nothing_and_says_so(self):
        F.STATE["dev"]["ports"] = [{"id": 7, "start": 1, "end": 5}]      # nothing matches either numbering
        self.app._port_base[DEV] = 1
        from eaveluxos.server import ApiError
        with self.assertRaises(ApiError) as cm:
            self.app.update_device({"deviceId": DEV, "ports": [{"id": 0, "start": 1, "end": 90}]})
        self.assertIn("both ways", str(cm.exception))
        self.assertEqual(len(self.updates()), 2)
        self.assertEqual(F.STATE["dev"]["ports"], [{"id": 7, "start": 1, "end": 5}])

    def test_name_only_changes_are_untouched(self):
        F.STATE["write_from_zero"] = True
        name = F.STATE["dev"].get("name")
        try:
            self.app.update_device({"deviceId": DEV, "name": "Front"})
            self.assertEqual(F.STATE["dev"]["name"], "Front")
        finally:
            F.STATE["dev"]["name"] = name

    def test_page_shows_the_note(self):
        js = (Path(__file__).resolve().parent.parent / "eaveluxos" / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn("toast(r && r.note ? r.note : r && r.local ?", js)


if __name__ == "__main__":
    unittest.main()
