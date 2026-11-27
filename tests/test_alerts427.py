# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""4.27: "EaveLuxOS was off" after a power cut, and the list of sent alerts."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from eaveluxos.alerts import AlertError, Alerts


class Down(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.t = [1_000_000.0]
        self.sent, self.notes = [], []

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def run_app(self, enabled=True, fail=False):
        def send(url, title, msg, tags, prio):
            if fail:
                raise AlertError("The ntfy server answered 500.")
            self.sent.append((title, msg, prio))
        a = Alerts(self.dir, now=lambda: self.t[0], send=send, clock=lambda ts: f"T{int(ts)}", note=self.notes.append)
        if enabled:
            a.update({"enabled": True})
        a.start()
        a.stop.set()               # steps are run by hand
        return a

    def test_power_cut_is_reported_once_when_back(self):
        a = self.run_app()
        self.t[0] += 60; a.step()
        last = self.t[0]
        self.t[0] += 6000          # off 100 minutes, never quit
        b = self.run_app()
        self.t[0] += 60; b.step()
        self.assertEqual([s[0] for s in self.sent], ["EaveLuxOS: the app was off"])
        self.assertIn(f"from about T{int(last)} to T{int(last) + 6000}", self.sent[0][1])
        self.assertIn("100 minutes", self.sent[0][1])
        self.assertEqual(self.sent[0][2], "high")
        self.assertEqual(len(self.notes), 1)               # in Activity too
        self.t[0] += 60; b.step()
        self.assertEqual(len(self.sent), 1)                # once

    def test_short_restart_and_quit_are_not_reported(self):
        a = self.run_app()
        self.t[0] += 60; a.step()
        self.t[0] += 120           # an update restart: 2 minutes
        b = self.run_app()
        self.t[0] += 60; b.step()
        b.quitting()
        self.t[0] += 60; b.step()                          # a step between Quit and the exit keeps "quit"
        self.t[0] += 86400         # quit on purpose, started a day later
        c = self.run_app()
        self.t[0] += 60; c.step()
        self.assertEqual(self.sent, [])
        self.assertEqual(self.notes, [])

    def test_noted_even_with_alerts_off_or_the_event_off(self):
        a = self.run_app(enabled=False)
        self.t[0] += 60; a.step()
        self.t[0] += 3600
        b = self.run_app(enabled=False)
        self.t[0] += 60; b.step()
        self.assertEqual(self.sent, [])
        self.assertEqual(len(self.notes), 1)
        b.update({"enabled": True, "events": {"down": False}})
        self.t[0] += 3600
        c = self.run_app()
        self.t[0] += 60; c.step()
        self.assertEqual(self.sent, [])
        self.assertEqual(len(self.notes), 2)

    def test_first_ever_start_is_not_a_power_cut(self):
        b = self.run_app()
        self.t[0] += 60; b.step()
        self.assertEqual(self.sent, [])

    def test_a_garbled_alive_file_is_ignored(self):
        (self.dir / "alive.json").write_text('{"at": true}', encoding="utf-8")
        b = self.run_app()
        self.t[0] += 60; b.step()
        self.assertEqual(self.sent, [])


class History(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.t = [1_000_000.0]
        self.fail = False

        def send(url, title, msg, tags, prio):
            if self.fail:
                raise AlertError("Couldn't reach the ntfy server: timed out")
        self.cond = {}
        self.a = Alerts(self.dir, probe=lambda: self.cond, now=lambda: self.t[0], send=send)
        self.a.update({"enabled": True})

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_sent_and_failed_are_listed_newest_first_and_kept(self):
        self.a.test()
        self.fail = True
        self.t[0] += 10
        with self.assertRaises(AlertError):
            self.a.test()
        self.cond = {"update": (True, "4.27.0")}
        self.t[0] += 10
        self.a.step()
        h = self.a.settings()["history"]
        self.assertEqual([(x["title"], x["ok"]) for x in h],
                         [("New version", False), ("test", False), ("test", True)])
        self.assertIn("timed out", h[0]["error"])
        again = Alerts(self.dir, now=lambda: self.t[0], send=lambda *a: None)
        self.assertEqual(len(again.settings()["history"]), 3)

    def test_at_most_20_and_bad_entries_dropped(self):
        for i in range(30):
            self.t[0] += 1
            self.a.test()
        self.assertEqual(len(self.a.settings()["history"]), 20)
        raw = json.loads((self.dir / "alerts.json").read_text())
        raw["history"] = [{"at": "x", "title": 3}, {"at": 5, "title": "ok", "ok": True}, "junk"]
        (self.dir / "alerts.json").write_text(json.dumps(raw))
        b = Alerts(self.dir, send=lambda *a: None)
        self.assertEqual([x["title"] for x in b.settings()["history"]], ["ok"])

    def test_offline_waits_10_minutes(self):
        sent = []
        a = Alerts(self.dir, probe=lambda: {"offline": (True, "Trimlight")}, now=lambda: self.t[0],
                   send=lambda u, t, m, g, p: sent.append(m))
        a.update({"enabled": True})
        for _ in range(9):
            self.t[0] += 60; a.step()
        self.assertEqual(sent, [])
        for _ in range(2):
            self.t[0] += 60; a.step()
        self.assertEqual(len(sent), 1)
        self.assertIn("10 minutes", sent[0])


if __name__ == "__main__":
    unittest.main()
