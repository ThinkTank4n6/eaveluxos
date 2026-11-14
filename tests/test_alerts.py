# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Phone alerts through ntfy (3.15)."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from eaveluxos import alerts
from eaveluxos.alerts import AlertError, Alerts, check_server


class AlertTiming(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.t = [1_000_000.0]
        self.cond = {}
        self.sent = []
        self.a = Alerts(self.dir, probe=lambda: self.cond, now=lambda: self.t[0],
                        send=lambda url, title, msg, tags, prio: self.sent.append((url, title, msg)))
        self.a.update({"enabled": True})

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def minutes(self, n):
        for _ in range(n):
            self.t[0] += 60
            self.a.step()

    def titles(self):
        return [t for _, t, _ in self.sent]

    def test_a_problem_waits_then_alerts_once_then_says_when_fixed(self):
        self.cond = {"offline": (True, "Trimlight")}
        self.minutes(14)
        self.assertEqual(self.sent, [])                                  # not for a short blip
        self.minutes(2)
        self.assertEqual(self.titles(), ["EaveLuxOS: Controller offline"])
        self.assertIn("Trimlight has been offline", self.sent[0][2])
        self.minutes(120)
        self.assertEqual(len(self.sent), 1)                              # not every minute
        self.cond = {}
        self.minutes(1)
        self.assertEqual(self.titles()[-1], "EaveLuxOS: back to normal")
        self.assertIn("Trimlight is back online", self.sent[-1][2])

    def test_repeats_every_6_hours_while_it_lasts(self):
        self.cond = {"failed": (True, "timed out")}
        self.minutes(6 * 60 + 15)
        self.assertEqual(self.titles(), ["EaveLuxOS: Lights didn't change"] * 2)

    def test_a_blip_that_clears_sends_nothing(self):
        self.cond = {"unreadable": (True, "your controller")}
        self.minutes(5)
        self.cond = {}
        self.minutes(30)
        self.assertEqual(self.sent, [])

    def test_new_version_once_and_remembered(self):
        self.cond = {"update": (True, "3.16.0")}
        self.minutes(3)
        self.assertEqual(self.titles(), ["EaveLuxOS: New version"])
        again = Alerts(self.dir, probe=lambda: self.cond, now=lambda: self.t[0],
                       send=lambda *a: self.sent.append(a))
        again.step()
        self.assertEqual(len(self.sent), 1)                              # not again after a restart

    def test_off_or_event_off_sends_nothing(self):
        self.a.update({"events": {"offline": False}})
        self.cond = {"offline": (True, "Trimlight")}
        self.minutes(30)
        self.a.update({"enabled": False})
        self.cond = {"failed": (True, "x")}
        self.minutes(30)
        self.assertEqual(self.sent, [])

    def test_send_failure_is_retried_next_minute(self):
        calls = []

        def flaky(*a):
            calls.append(a)
            if len(calls) == 1:
                raise AlertError("Couldn't reach the ntfy server")
        self.a.send_raw = flaky
        self.cond = {"failed": (True, "x")}
        self.minutes(12)
        self.assertEqual(len(calls), 2)

    def test_messages_go_to_the_topic(self):
        self.a.test()
        self.assertEqual(self.sent[0][0], f"https://ntfy.sh/{self.a.settings()['topic']}")


class AlertSettings(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_defaults_off_with_a_hard_to_guess_topic(self):
        s = Alerts(self.dir).settings()
        self.assertFalse(s["enabled"])
        self.assertRegex(s["topic"], r"^eaveluxos-[0-9a-f]{16}$")
        self.assertNotEqual(s["topic"], Alerts(Path(tempfile.mkdtemp())).settings()["topic"])

    def test_servers(self):
        self.assertEqual(check_server("https://ntfy.sh/"), "https://ntfy.sh")
        self.assertEqual(check_server("http://192.168.1.20:8080"), "http://192.168.1.20:8080")
        for bad in ("http://ntfy.sh", "https://ntfy.sh/x?y=1", "ftp://a", "https://user:pw@ntfy.sh", "http://8.8.8.8", ""):
            with self.assertRaises(AlertError, msg=bad):
                check_server(bad)

    def test_bad_input_is_refused(self):
        a = Alerts(self.dir)
        for bad in ({"topic": "short"}, {"topic": "has space in it!"}, {"enabled": "yes"}, {"server": "http://example.com"}):
            with self.assertRaises(AlertError, msg=bad):
                a.update(bad)

    def test_damaged_file(self):
        (self.dir / "alerts.json").write_text('{"enabled": true, "topic": "x", "server": "ftp://a"', encoding="utf-8")
        s = Alerts(self.dir).settings()
        self.assertFalse(s["enabled"])
        self.assertEqual(s["server"], "https://ntfy.sh")
        (self.dir / "alerts.json").write_text(json.dumps({"enabled": True, "topic": "no"}), encoding="utf-8")
        self.assertFalse(Alerts(self.dir).settings()["enabled"])         # an invalid topic can't be on

    def test_not_in_the_settings_document(self):
        import eaveluxos.server as srv
        self.assertIn("/api/alerts", srv.ADMIN_GETS)
        self.assertNotIn("/api/alerts/settings", srv.EDITOR_POSTS)
        self.assertNotIn("/api/alerts/test", srv.EDITOR_POSTS)


class Probe(unittest.TestCase):
    def test_app_reports_conditions(self):
        from eaveluxos.server import App
        d = Path(tempfile.mkdtemp())
        try:
            app = App(d, start=False)

            class C:
                fail_count, last_error, read_error = 3, "timed out", "code 12006 (Device data could not be parsed)"
                status_cache = {"data": [{"name": "Trimlight", "online": False}, {"name": "Garage", "online": True}]}
            app.ctrl = C()
            p = app.alert_probe()
            self.assertEqual(p["failed"], (True, "timed out"))
            self.assertEqual(p["offline"], (True, "Trimlight"))
            self.assertTrue(p["unreadable"][0])
            self.assertFalse(p["update"][0])
            app.store.close()
        finally:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
