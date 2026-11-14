# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""The Schedule tab's month view (3.15)."""
import copy
import shutil
import tempfile
import unittest
from pathlib import Path

from eaveluxos.server import ApiError, App
from eaveluxos.store import DEFAULT_SETTINGS

JS = (Path(__file__).resolve().parent.parent / "eaveluxos" / "static" / "app.js").read_text(encoding="utf-8")


class MonthView(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = Path(tempfile.mkdtemp())
        cls.app = App(cls.dir, start=False)
        s = copy.deepcopy(DEFAULT_SETTINGS)
        s["location"].update(latitude=39.95, longitude=-75.16)
        s["setup_done"] = True
        cls.app.store.save_settings(s)
        cls.app.store.save_secrets(client_id="x", client_secret="y")
        cls.app.rebuild()
        cls.year = cls.app.cfg.loc.now().year

    @classmethod
    def tearDownClass(cls):
        cls.app.store.close()
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_a_whole_month(self):
        dec = self.app.upcoming(21, f"{self.year}-12")
        self.assertEqual(len(dec), 31)
        self.assertEqual(dec[0]["date"], f"{self.year}-12-01")
        self.assertEqual(dec[-1]["date"], f"{self.year}-12-31")
        self.assertEqual({w["rule"] for w in dec[10]["windows"]}, {"Christmas season"})
        feb = self.app.upcoming(21, f"{self.year + 1}-02")
        self.assertIn(len(feb), (28, 29))
        self.assertTrue(all(w["rule"] == "Every night" for d in feb for w in d["windows"]))

    def test_list_still_starts_today(self):
        self.assertEqual(len(self.app.upcoming(21)), 21)

    def test_bad_months_are_refused(self):
        for bad in ("2026-13", "2026-1", "december", f"{self.year + 5}-01", "2026-12x"):
            with self.assertRaises(ApiError, msg=bad):
                self.app.upcoming(21, bad)

    def test_screen(self):
        self.assertIn("function upcomingPanel", JS)
        self.assertIn("upcoming?month=${ym}", JS)
        self.assertIn('class="cal" role="grid"', JS)


if __name__ == "__main__":
    unittest.main()
