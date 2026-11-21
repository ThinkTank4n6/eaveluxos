# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""4.15: reliability.

- Who wins tonight: what shows when, what it beats and why, and warnings.
- Controller health: every request to Trimlight's cloud counted per
  controller, with the home-network check.
- Smart recovery: choices made by hand, a security flash and a music show
  come back after the app restarts; a scheduled change while it was off still
  ends a choice; what was just sent isn't sent again unless it's wrong.
- Find and match: controllers on the home network, matched by their ports.
- Updates that install: SHA-256 checked, the previous version kept, and back
  to it by itself when the new one doesn't start."""
import copy
import hashlib
import io
import json
import os
import tempfile
import time
import unittest
import zipfile
from pathlib import Path

from eaveluxos import conflicts, health, selfupdate
from eaveluxos.controller import Controller
from eaveluxos.server import ApiError
from tests.test_multi45 import DECK, FRONT, TwoBase


class WhoWins(TwoBase):
    def test_a_night(self):
        s = copy.deepcopy(self.app.store.settings)
        s["rules"] = [{"name": "Every night", "on": "17:00", "off": "23:00", "effect": "warm_white"},
                      {"name": "Party", "on": "19:00", "off": "22:00", "effect": "christmas"},
                      {"name": "Deck late", "on": "21:00", "off": "23:30", "effect": "christmas", "priority": 150, "controllers": [DECK]}]
        s["weather_rules"] = [{"name": "Snowing", "when": ["snow"], "effect": "snowfall", "priority": 150}]
        s.setdefault("weather", {})["enabled"] = True      # 4.16.4: counted only while weather is on
        self.app.save_settings(s)
        self.app.ctrl.devices = [{"deviceId": DECK, "name": "Deck"}, {"deviceId": FRONT, "name": "Front"}]
        r = self.app.conflicts("2026-11-20")
        deck = [(x["start"][11:16], x["end"][11:16], x["winner"]["name"], [b["name"] for b in x["beaten"]])
                for x in r["devices"][DECK] if x["on"]]
        self.assertEqual(deck, [("17:00", "19:00", "Every night", []), ("19:00", "21:00", "Every night", ["Party"]),
                                ("21:00", "22:00", "Deck late", ["Every night", "Party"]), ("22:00", "23:00", "Deck late", ["Every night"]),
                                ("23:00", "23:30", "Deck late", [])])
        front = [x["winner"]["name"] for x in r["devices"][FRONT] if x["on"]]
        self.assertNotIn("Deck late", front, "a rule for the Deck never reaches the Front")
        first = r["devices"][FRONT][1]
        self.assertEqual([w["name"] for w in first["weather"]], ["Snowing"], "snow could take over (150 > 100)")
        levels = [w["level"] for w in r["warnings"]]
        self.assertEqual(levels.count("tie"), 1)
        self.assertIn("listed first", next(w["text"] for w in r["warnings"] if w["level"] == "tie"))
        self.assertTrue(any(w["level"] == "hidden" and w["rule"] == "Party" for w in r["warnings"]))
        with self.assertRaises(ApiError):
            self.app.conflicts("12/24")


class Health(TwoBase):
    def test_requests_are_counted_and_the_home_network_checked(self):
        self.app.local_address(DECK, "127.0.0.1")
        self.app.ctrl.next_try = 0
        self.app.ctrl.tick()
        r = self.app.health_status()
        deck = next(d for d in r["devices"] if d["id"] == DECK)
        self.assertGreater(deck["today"]["ok"], 0, "the scheduler's requests count")
        self.assertEqual(deck["success"], 100)
        self.assertEqual(deck["firmware"], "1.17.77")
        self.assertEqual(len(deck["days"]), 14)
        r = self.app.health_check()
        deck = next(d for d in r["devices"] if d["id"] == DECK)
        self.assertIsNotNone(deck["lan"]["ms"], "greeted on the home network")
        front = next(d for d in r["devices"] if d["id"] == FRONT)
        self.assertIsNone(front["lan"], "no address, no check")

    def test_failures_and_the_file(self):
        d = Path(tempfile.mkdtemp())
        h = health.Health(d)
        h.record("A", "/v1/x/device/update", 120, True)
        h.record("A", "/v1/x/device/update", 900, False, "code 12006 (data error)", 12006)
        s = h.summary("A")
        self.assertEqual((s["today"]["ok"], s["today"]["fail"], s["success"]), (1, 1, 50))
        self.assertIn("12006", s["error"]["error"])
        h.save(force=True)
        self.assertEqual(health.Health(d).summary("A")["today"]["fail"], 1, "kept across restarts")


class Recovery(TwoBase):
    def again(self):
        """The app restarted: a new scheduler with the same data folder."""
        c = self.app.ctrl
        return Controller(c.cfg, c.api, data_dir=self.app.store.dir)

    def test_choices_come_back(self):
        c = self.app.ctrl
        c.next_try = 0
        c.tick()
        c.manual(False)
        c.manual_one(FRONT, True, "christmas")
        c._save_state()
        n = self.again()
        self.assertFalse(n.dev_override.get(DECK, {}).get("on", n.override and n.override.get("on")), "Off, by hand")
        self.assertEqual(n.dev_override[FRONT]["effect"], "christmas")
        self.assertTrue(any("brought back" in e["msg"] for e in n.events))

    def test_a_flash_and_a_show_come_back_but_not_a_page_show(self):
        c = self.app.ctrl
        c.start_flash(minutes=5)
        c._save_state()
        n = self.again()
        self.assertIsNotNone(n.flash)
        self.assertEqual(n.flash["kind"], "security")
        c.stop_flash()
        c.start_music(30, by="lan:abc")
        c._save_state()
        self.assertIsNone(self.again().music, "a show from this computer's page ended with the app")
        c.stop_music()
        c.start_music(30)
        c._save_state()
        self.assertIsNotNone(self.again().music)

    def test_a_scheduled_change_while_off_ends_a_choice(self):
        c = self.app.ctrl
        c.next_try = 0
        c.tick()
        c.manual(False)
        c._save_state()
        st = json.loads(Path(c.state_path).read_text(encoding="utf-8"))
        st["sched_key"] = "on|Some other night|2026-01-01T17:00:00-05:00"
        Path(c.state_path).write_text(json.dumps(st), encoding="utf-8")
        n = self.again()
        n.devices = list(c.devices)
        t = n._target()
        self.assertIsNone(n.override, "the schedule moved on while the app was off")
        self.assertNotEqual(t.reason, "manual")

    def test_what_was_just_sent_isnt_sent_again(self):
        c = self.app.ctrl
        c.next_try = 0
        c.tick()
        c._save_state()
        writes = lambda: len([p for p, _ in self.F.STATE["log"] if p.endswith(("/device/update", "/device/effect/preview"))])
        n = self.again()
        n.next_try = 0
        before = writes()
        n.tick(maintenance=False)
        self.assertEqual(writes(), before, "nothing sent again right after the restart")
        self.assertEqual(n.applied_key, c.applied_key)
        # An old saved state is checked by sending
        st = json.loads(Path(c.state_path).read_text(encoding="utf-8"))
        st["saved_at"] = time.time() - 7200
        Path(c.state_path).write_text(json.dumps(st), encoding="utf-8")
        self.assertIsNone(self.again().applied_key)


class Discover(TwoBase):
    def test_found_and_matched_by_ports(self):
        from eaveluxos import lanlink
        orig = lanlink.find
        self.addCleanup(setattr, lanlink, "find", orig)
        lanlink.find = lambda *a, **k: ["127.0.0.1", "127.0.0.2"]
        r = self.app.local_discover()
        got = {f["address"]: f.get("match") for f in r["found"]}
        self.assertEqual(got, {"127.0.0.1": DECK, "127.0.0.2": FRONT})
        self.assertIn("Front Porch", next(f for f in r["found"] if f["address"] == "127.0.0.2")["patterns"])

    def test_scan_stays_on_the_home_network(self):
        from eaveluxos import lanlink
        self.assertEqual(lanlink.scan("8.8.8.8"), [], "never a public network")
        self.assertEqual(lanlink.scan("127.0.0.1"), [])
        self.assertEqual(lanlink.scan("not an address"), [])


def release_zip(files: dict) -> bytes:
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        for n, data in files.items():
            z.writestr(f"EaveLuxOS/{n}", data)
    return b.getvalue()


class FakeProc:
    def __init__(self, code=None):
        self.returncode = code

    def poll(self):
        return self.returncode

    def terminate(self):
        self.returncode = -15

    def wait(self, timeout=None):
        return self.returncode

    def kill(self):
        self.returncode = -9


class Updates(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.data = Path(tempfile.mkdtemp())
        (self.dir / "EaveLuxOS.exe").write_bytes(b"old gui")
        (self.dir / "EaveLuxOS-cli.exe").write_bytes(b"old cli")
        self.zip = release_zip({"EaveLuxOS.exe": b"new gui", "EaveLuxOS-cli.exe": b"new cli"})
        self.sums = f"{hashlib.sha256(self.zip).hexdigest()}  EaveLuxOS-Windows.zip\n0000  other\n".encode()
        self.served = {"https://github.com/x/SHA256SUMS.txt": self.sums, "https://github.com/x/EaveLuxOS-Windows.zip": self.zip}
        self.rel = {"version": "4.16.0", "assets": {"EaveLuxOS-Windows.zip": "https://github.com/x/EaveLuxOS-Windows.zip",
                                                    "SHA256SUMS.txt": "https://github.com/x/SHA256SUMS.txt"}}
        self.calls = []

    def opener(self, url):
        return io.BytesIO(self.served[url])

    def updater(self, new_answers="4.16.0", new_proc=None):
        p = selfupdate.plan(frozen=True, system="Windows", exe=self.dir / "EaveLuxOS.exe", supervised=False)
        self.clock = [0.0]
        procs = [new_proc or FakeProc(), FakeProc()]

        def spawn():
            self.calls.append(("spawn", (self.dir / "EaveLuxOS.exe").read_bytes()))
            return procs.pop(0)
        return selfupdate.Updater(self.data, plan_=p, stop=lambda: self.calls.append("stop"), spawn=spawn,
                                  answers=lambda: new_answers, quit=lambda: self.calls.append("quit"),
                                  sleep=lambda s: self.clock.__setitem__(0, self.clock[0] + s), clock=lambda: self.clock[0],
                                  opener=self.opener)

    def test_install_keeps_the_previous_version(self):
        up = self.updater()
        new = up.prepare(self.rel, "EaveLuxOS-Windows.zip")
        up.install(new, "4.15.0", "4.16.0")
        self.assertEqual((self.dir / "EaveLuxOS.exe").read_bytes(), b"new gui")
        self.assertEqual((self.dir / "EaveLuxOS.exe.previous").read_bytes(), b"old gui")
        self.assertEqual((self.dir / "EaveLuxOS-cli.exe").read_bytes(), b"new cli")
        self.assertEqual(self.calls, ["stop", ("spawn", b"new gui"), "quit"])
        self.assertEqual(up.state()["stage"], "done")
        self.assertTrue(up.can_roll_back())

    def test_a_damaged_download_is_never_used(self):
        self.served["https://github.com/x/EaveLuxOS-Windows.zip"] = self.zip[:-10] + b"x" * 10
        up = self.updater()
        with self.assertRaises(selfupdate.UpdateError) as e:
            up.prepare(self.rel, "EaveLuxOS-Windows.zip")
        self.assertIn("SHA-256", str(e.exception))
        self.assertEqual((self.dir / "EaveLuxOS.exe").read_bytes(), b"old gui")

    def test_back_by_itself_when_the_new_one_doesnt_start(self):
        for how in ("closes", "wrong version"):
            with self.subTest(how=how):
                self.setUp()
                up = self.updater(new_answers="4.15.0" if how == "wrong version" else None,
                                  new_proc=FakeProc(1) if how == "closes" else None)
                up.install(up.prepare(self.rel, "EaveLuxOS-Windows.zip"), "4.15.0", "4.16.0")
                self.assertEqual((self.dir / "EaveLuxOS.exe").read_bytes(), b"old gui", "the old one back")
                self.assertEqual(self.calls[-2:], [("spawn", b"old gui"), "quit"], "and started again")
                st = up.state()
                self.assertEqual((st["stage"], st["to"], st["frm"]), ("rolled_back", "4.16.0", "4.15.0"))

    def test_roll_back_by_hand(self):
        up = self.updater()
        up.install(up.prepare(self.rel, "EaveLuxOS-Windows.zip"), "4.15.0", "4.16.0")
        self.calls.clear()
        up2 = self.updater(new_answers="4.15.0")
        up2.roll_back("4.16.0")
        self.assertEqual((self.dir / "EaveLuxOS.exe").read_bytes(), b"old gui")
        self.assertEqual(self.calls[-1], "quit")

    def test_only_github_and_only_what_fits(self):
        with self.assertRaises(selfupdate.UpdateError):
            selfupdate._open("https://example.com/EaveLuxOS-Windows.zip")
        for kw, part in (({"frozen": False}, "source code"), ({"system": "Darwin"}, "Mac"), ({"supervised": True}, "service")):
            args = {"frozen": True, "system": "Windows", "exe": self.dir / "EaveLuxOS.exe", "supervised": False, **kw}
            with self.subTest(kw=kw):
                p = selfupdate.plan(**args)
                self.assertFalse(p["ok"])
                self.assertIn(part, p["why"])
        self.assertFalse(selfupdate.plan(frozen=True, system="Linux", exe="/opt/eaveluxos/eaveluxos", supervised=False)["ok"])
        bad = release_zip({"EaveLuxOS.exe": b"only one"})
        f = self.dir / "x.zip"
        f.write_bytes(bad)
        with self.assertRaises(selfupdate.UpdateError):
            selfupdate.unpack(f, self.dir / "n", "windows", ["EaveLuxOS.exe", "EaveLuxOS-cli.exe"])


class Review(unittest.TestCase):
    def test_1_a_controller_back_online_is_set_again_at_once(self):
        from tests import reprorun
        reprorun.run(self, "repro_power_back.py", 120)


class ReviewUpdates(Updates):
    def test_2_the_download_goes_afterward(self):
        up = self.updater()
        up.install(up.prepare(self.rel, "EaveLuxOS-Windows.zip"), "4.15.0", "4.16.0")
        self.assertTrue((self.dir / ".eaveluxos-update").is_dir())
        self.updater().cleanup()
        self.assertFalse((self.dir / ".eaveluxos-update").exists())
        self.assertTrue((self.dir / "EaveLuxOS.exe.previous").exists(), "the previous version stays, to go back")


class AppUpdates(TwoBase):
    def test_from_source_says_how(self):
        r = self.app.update_summary()
        self.assertFalse(r["install"]["ok"])
        self.assertIn("source code", r["install"]["why"])
        with self.assertRaises(ApiError):
            self.app.update_install()
        self.assertFalse(r["auto"])


if __name__ == "__main__":
    unittest.main()


try:
    from playwright.sync_api import sync_playwright
except ImportError:            # pragma: no cover
    sync_playwright = None


@unittest.skipIf(sync_playwright is None, "Playwright isn't installed")
class Browser(TwoBase):
    SHOTS = None

    def test_the_new_screens(self):
        import threading
        from eaveluxos import lanlink
        from eaveluxos.server import make_server
        s = copy.deepcopy(self.app.store.settings)
        s["rules"] = [{"name": "Every night", "on": "17:00", "off": "23:00", "effect": "warm_white"},
                      {"name": "Party", "on": "19:00", "off": "22:00", "effect": "christmas"}]
        self.app.save_settings(s)
        self.app.local_address(DECK, "127.0.0.1")
        orig = lanlink.find
        self.addCleanup(setattr, lanlink, "find", orig)
        lanlink.find = lambda *a, **k: ["127.0.0.1", "127.0.0.2"]
        srv = make_server(self.app, "127.0.0.1", 0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        base = f"http://localhost:{srv.server_address[1]}/"
        try:
            pw = sync_playwright().start()
            br = pw.chromium.launch()
        except Exception as e:
            self.skipTest(f"Chromium can't start: {e}")
        self.addCleanup(pw.stop)
        self.addCleanup(br.close)
        errors = []

        def until(cond, what, n=200):
            for _ in range(n):
                if cond():
                    return
                time.sleep(0.05)
            self.fail(f"never: {what}")
        pg = br.new_page(viewport={"width": 1300, "height": 1000})
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(base + "#schedule")
        pg.wait_for_selector('[data-fold="whowins"]')
        if "closed" in (pg.get_attribute('[data-fold="whowins"]', "class") or ""):
            pg.click('[data-fold="whowins"] .foldbar')
        pg.wait_for_selector("#windate")
        self.assertIn("listed first", pg.inner_text("#winbox"))
        pg.fill("#windate", "2026-12-24")
        pg.dispatch_event("#windate", "change")
        until(lambda: pg.eval_on_selector("#windate", "e => e.value") == "2026-12-24" and "Beats" in pg.inner_text("#winbox"), "another night")
        if self.SHOTS:
            pg.locator("#winbox").screenshot(path=f"{self.SHOTS}/whowins.png")
        pg.goto(base + "#health")
        pg.wait_for_selector(".hcard")
        self.assertEqual(pg.locator(".hcard").count(), 2)
        pg.click("[data-hcheck]")
        until(lambda: "answered in" in pg.inner_text("#main") and "ms (" in pg.inner_text("#main"), "the check")
        if self.SHOTS:
            pg.screenshot(path=f"{self.SHOTS}/health.png", full_page=True)
        pg.goto(base + "#local")
        pg.wait_for_selector("[data-lcdisc]")
        pg.click("[data-lcdisc]")
        pg.wait_for_selector("[data-lcmatch]")
        self.assertIn("This is", pg.inner_text("#lcfound"))
        pg.click("[data-lcmatch]")
        until(lambda: ((self.app.store.settings.get("lan") or {}).get("devices") or {}).get(FRONT) == "127.0.0.2", "the Front's address saved")
        if self.SHOTS:
            pg.screenshot(path=f"{self.SHOTS}/discover.png", full_page=True)
        pg.goto(base + "#app")
        pg.wait_for_selector("#updbox h2")
        self.assertEqual(errors, [])
