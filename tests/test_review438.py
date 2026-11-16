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


if __name__ == "__main__":
    unittest.main()
