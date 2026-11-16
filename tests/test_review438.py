# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""4.3.8: a cloud read is tried once more after a network hiccup; a change
never is."""
import unittest
from pathlib import Path

from eaveluxos.api import TrimlightAPI, TrimlightError


class Flaky(TrimlightAPI):
    def __init__(self, fails, kind="network"):
        super().__init__("id", "secret")
        self.fails, self.kind, self.calls = fails, kind, []

    def _request(self, method, path, body=None):
        self.calls.append(path)
        if self.fails:
            self.fails -= 1
            raise TrimlightError(f"Network error calling {path}: timed out", self.kind)
        return {"data": [{"deviceId": "x"}]} if path.endswith("/devices") else {"ok": 1}


class ReadRetry(unittest.TestCase):
    def test_a_read_is_tried_once_more(self):
        api = Flaky(1)
        self.assertEqual(api.list_devices(), [{"deviceId": "x"}])
        self.assertEqual(len(api.calls), 2)
        api = Flaky(1)
        self.assertEqual(api.get_device("x", __import__("datetime").datetime(2026, 11, 16, 12)), {"ok": 1})

    def test_only_once_and_only_for_network_trouble(self):
        with self.assertRaises(TrimlightError):
            Flaky(2).list_devices()
        api = Flaky(1, kind="api")
        with self.assertRaises(TrimlightError):
            api.list_devices()
        self.assertEqual(len(api.calls), 1)

    def test_a_change_is_never_repeated(self):
        api = Flaky(1)
        with self.assertRaises(TrimlightError):
            api.calendar_save("x", {"id": 1})
        self.assertEqual(len(api.calls), 1)

    def test_status_says_when_it_was_last_copied(self):
        js = (Path(__file__).resolve().parent.parent / "eaveluxos" / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn("(last copied ${esc(d.last_sync_label)})", js)


class Review439(unittest.TestCase):
    def js(self):
        return (Path(__file__).resolve().parent.parent / "eaveluxos" / "static" / "app.js").read_text(encoding="utf-8")

    def test_no_search_for_an_empty_place(self):
        self.assertIn("Type a town or ZIP code first.", self.js())

    def test_rejected_keys_say_what_to_check(self):
        src = (Path(__file__).resolve().parent.parent / "eaveluxos" / "server.py").read_text(encoding="utf-8")
        self.assertIn("computer's date and time are right (Trimlight checks them too)", src)

    def test_timers_numbered_from_1(self):
        src = (Path(__file__).resolve().parent.parent / "eaveluxos" / "safety.py").read_text(encoding="utf-8")
        self.assertIn("list(range(1, MAX_CALENDAR)) + [0]", src)


class Paused439(unittest.TestCase):
    """4.3.9: every 12006 came within minutes of the backup timer's calendar
    writes (Nov 13 17:22->17:26, Nov 15 17:52->17:56, Nov 16 13:46->13:50)."""

    def setUp(self):
        import eaveluxos.safety as S
        self.S = S
        S.PAUSED = True
        self.addCleanup(setattr, S, "PAUSED", False)

    def test_turned_on_it_stays_off(self):
        import copy
        from eaveluxos.schedule import build_config
        from eaveluxos.store import DEFAULT_SETTINGS
        s = copy.deepcopy(DEFAULT_SETTINGS)
        s["location"].update(latitude=39.95, longitude=-75.16)
        s["safety"] = {"enabled": True, "days": 7}
        cfg = build_config(s, {"client_id": "x", "client_secret": "y"})
        self.assertFalse(cfg.safety["enabled"])
        self.assertTrue(cfg.safety["wanted"])

    def test_the_hardware_test_skips_the_timer(self):
        src = (Path(__file__).resolve().parent.parent / "eaveluxos" / "hwtest.py").read_text(encoding="utf-8")
        self.assertIn('"paused since 4.3.9"', src)

    def test_the_panel_says_so(self):
        js = (Path(__file__).resolve().parent.parent / "eaveluxos" / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn("Paused in this version.", js)

    def test_shipped_paused(self):
        src = (Path(__file__).resolve().parent.parent / "eaveluxos" / "safety.py").read_text(encoding="utf-8")
        self.assertIn("\nPAUSED = True\n", src)


if __name__ == "__main__":
    unittest.main()
