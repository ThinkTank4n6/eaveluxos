# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""4.4: everyday commands over the home network (opt-in), Resync with
Trimlight's cloud, a pause after the greeting, and the reachability check
taking its turn for the connection."""
import copy
import time
import unittest
from pathlib import Path

from eaveluxos import lanlink as L
from tests.test_local43 import ServerBase

ROOT = Path(__file__).resolve().parent.parent
DEV = "TL-EDGE-01"


class Commands(ServerBase):
    def setUp(self):
        super().setUp()
        self.app.ctrl.devices = [{"deviceId": DEV, "name": "Trimlight"}]

    def turn(self, on):
        self.app.local_commands(on)              # saving settings can make a new controller object
        self.app.ctrl.devices = [{"deviceId": DEV, "name": "Trimlight"}]

    def subs(self):
        return [b[0] for _, _, b in self.ctl.frames(L.CMD_REQUEST)]

    def cloud(self):
        return [p for p, _ in self.F.STATE["log"] if p in ("/device/update", "/device/effect/view")]

    def test_off_by_default_everything_through_the_cloud(self):
        self.app.ctrl._switch(DEV, 1)
        self.assertEqual(self.subs(), [])
        self.assertEqual(self.cloud(), ["/device/update"])

    def test_on_off_and_saved_patterns_over_the_home_network(self):
        self.turn(True)
        self.app.ctrl._switch(DEV, 1)
        self.app.ctrl._show_saved(DEV, 9)
        self.app.ctrl._switch(DEV, 0)
        reqs = [b for _, _, b in self.ctl.frames(L.CMD_REQUEST)]
        self.assertEqual(reqs, [L.request(L.SUB_POWER, bytes([1])), L.request(L.SUB_SHOW, bytes([9])), L.request(L.SUB_POWER, bytes([0]))])
        self.assertEqual(self.cloud(), [])
        self.assertTrue(self.app.ctrl.lan_sent[DEV])
        self.assertEqual(self.app.ctrl.lan.switch(DEV), 1)       # what the controller says

    def test_right_after_the_computer_starts(self):
        """No failure yet means usable, even when the clock that counts
        from start-up is still under 5 minutes."""
        from unittest import mock
        self.turn(True)
        with mock.patch("eaveluxos.localmode.time.monotonic", return_value=12.0):
            self.assertTrue(self.app.ctrl.lan.usable(DEV))

    def test_each_one_in_the_log(self):
        """4.4.1: a command that went over the home network says so."""
        self.turn(True)
        with self.assertLogs("eaveluxos.localmode", "INFO") as cm:
            self.app.ctrl._switch(DEV, 0)
            self.app.ctrl._show_saved(DEV, 12)
        self.assertEqual([r.getMessage() for r in cm.records],
                         ["Over the home network (127.0.0.1): lights off.",
                          "Over the home network (127.0.0.1): showed saved pattern 12."])

    def test_timer_mode_always_through_the_cloud(self):
        self.turn(True)
        self.app.ctrl._switch(DEV, 2)
        self.assertEqual(self.subs(), [])
        self.assertEqual(self.cloud(), ["/device/update"])

    def test_no_answer_falls_back_to_the_cloud_for_a_while(self):
        self.turn(True)
        self.ctl.close()
        with self.assertLogs("eaveluxos.localmode", "WARNING"):
            self.app.ctrl._switch(DEV, 1)
        self.assertEqual(self.cloud(), ["/device/update"])
        self.assertNotIn(DEV, self.app.ctrl.lan_sent)
        self.assertFalse(self.app.ctrl.lan.usable(DEV))           # the cloud for 5 minutes

    def test_not_during_a_show_or_a_local_job(self):
        self.turn(True)
        self.app.lanshow.running = lambda: True
        self.app.ctrl._switch(DEV, 1)
        self.assertEqual(self.subs(), [])
        self.app.lanshow.running = lambda: False
        with self.app.local_busy:
            self.app.ctrl._switch(DEV, 1)
        self.assertEqual(self.subs(), [])

    def test_the_setting_survives_a_new_address(self):
        self.turn(True)
        self.app.musiclink_address("127.0.0.1")
        self.assertTrue(self.app.store.settings["lan"]["commands"])

    def test_panel(self):
        js = (ROOT / "eaveluxos" / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="lccmd"', js)
        self.assertIn("api('local/commands'", js)
        # 4.4.1: shown with the address, not only after a good read
        self.assertIn("head + cmd + pick + '<div id=\"lcbody\">", js)
        body = js[js.index("$('#lcbody', box).innerHTML = `<p class=\"small\">Ports"):js.index("box.onchange = e =>")]
        self.assertNotIn('id="lccmd"', body)

    def test_on_then_a_pattern_of_its_own_colors(self):
        """4.4.1 (review #1): "on" over the home network, the pattern through
        the cloud: on/off is still checked with the controller, and Home
        shows what the controller says."""
        self.turn(True)
        c = self.app.ctrl
        c._switch(DEV, 1)
        c._sent(DEV, "pattern", False)                  # what _apply does after a cloud preview
        self.assertEqual(c.lan_sent[DEV], {"switch"})
        c._show_saved(DEV, 9)
        self.assertEqual(c.lan_sent[DEV], {"switch", "pattern"})
        c.lan.failed_at[DEV] = time.monotonic()          # home network out: both through the cloud
        c._switch(DEV, 0); c._show_saved(DEV, 9)
        self.assertNotIn(DEV, c.lan_sent)

    def test_a_show_starting_meanwhile_wins(self):
        """4.4.1 (review #3): a show from this computer that started while a
        command waited for the connection isn't ended by it."""
        self.turn(True)
        lan, calls = self.app.ctrl.lan, []
        real = lan.io.acquire
        def acquire(*a, **k):
            got = real(*a, **k)
            self.app.lanshow.running = lambda: True      # the show started while this waited
            return got
        lan.io = type("IO", (), {"acquire": staticmethod(acquire), "release": staticmethod(self.app.lan_io.release)})()
        self.assertFalse(lan.power(DEV, True))
        self.assertEqual(self.subs(), [])

    def test_unexpected_trouble_still_uses_the_cloud(self):
        """4.4.1 (review #4): anything going wrong over the home network falls
        back to the cloud instead of leaving the lights as they were."""
        self.turn(True)
        lan = self.app.ctrl.lan
        def broken(host):
            raise IndexError("odd answer")
        lan.link_factory = broken
        with self.assertLogs("eaveluxos.localmode", "WARNING"):
            self.app.ctrl._switch(DEV, 1)
        self.assertEqual(self.cloud(), ["/device/update"])
        self.assertFalse(self.app.lan_io.locked())


FALL = {"category": 1, "mode": 0, "speed": 128, "brightness": 139,
        "pixels": [{"index": 0, "count": 4, "color": 0xFF6300, "disable": False},
                   {"index": 1, "count": 2, "color": 0x561003, "disable": False}]}


class SameAsSaved(ServerBase):
    """4.4.2: this app's own copy of a pattern saved on the controller is
    shown by its number over the home network."""
    def setUp(self):
        super().setUp()
        self.app.local_commands(True)
        self.app.ctrl.devices = [{"deviceId": DEV, "name": "Trimlight"}]
        self.ctl.holds["patterns"][19] = L.pattern_record(19, "Fall", 0, 128, 139,
                                                          [(4, (0xFF, 0x63, 0x00), True), (2, (0x56, 0x10, 0x03), True)])

    def shown(self):
        return [b[3] for _, _, b in self.ctl.frames(L.CMD_REQUEST) if b[0] == L.SUB_SHOW]

    def cloud(self):
        return [p for p, _ in self.F.STATE["log"] if p in ("/device/update", "/device/effect/preview", "/device/effect/view")]

    def apply(self, payload):
        from eaveluxos.schedule import Effect
        self.app.ctrl.known_on = True
        self.app.ctrl._apply(True, Effect("fall", "Fall", "custom", payload=payload, colors=[]))

    def test_the_same_look_is_shown_by_its_number(self):
        with self.assertLogs("eaveluxos.localmode", "INFO") as cm:
            self.apply(dict(FALL))
        self.assertEqual(self.shown(), [19])
        self.assertEqual(self.cloud(), [])
        self.assertEqual(self.app.ctrl.lan_sent[DEV], {"pattern"})
        self.assertIn("showed saved pattern 19", cm.output[-1])

    def test_a_different_brightness_is_shown_live(self):
        """4.6: no saved match: shown live over the home network (it went
        through the cloud before)."""
        self.apply({**FALL, "brightness": 255})                  # American Flag on Nov 16: 255 here, 188 there
        self.assertEqual(self.shown(), [])
        self.assertEqual(self.cloud(), [])
        previews = [b for _, _, b in self.ctl.frames(L.CMD_REQUEST) if b[0] == L.SUB_PREVIEW]
        self.assertEqual(len(previews), 1)
        self.assertEqual(previews[0][3:6], bytes([0, 128, 255]), "mode, speed, brightness")
        self.assertIsNone(self.app.ctrl.lan.failed_at.get(DEV), "no match isn't a failure")

    def test_not_on_the_controller_isnt_read_again_for_a_while(self):
        self.apply({**FALL, "speed": 1})
        reads = len([1 for _, _, b in self.ctl.frames(L.CMD_REQUEST) if b[0] == L.SUB_TIME])
        self.apply({**FALL, "speed": 2})
        self.assertEqual(len([1 for _, _, b in self.ctl.frames(L.CMD_REQUEST) if b[0] == L.SUB_TIME]), reads)
        self.apply(dict(FALL))                                   # one the controller had: read fresh, shown
        self.assertEqual(self.shown(), [19])

    def test_its_number_comes_from_a_fresh_read(self):
        self.apply(dict(FALL))
        rec = self.ctl.holds["patterns"].pop(19)                 # moved to number 7 since (Local mode)
        self.ctl.holds["patterns"][7] = bytes([7]) + rec[1:]
        self.apply(dict(FALL))
        self.assertEqual(self.shown(), [19, 7])

    def test_built_in_effects_and_splits_stay_on_the_cloud(self):
        from eaveluxos.localmode import look_of
        self.assertIsNone(look_of({"category": 0, "mode": 5, "speed": 100, "brightness": 200, "pixelLen": 30}))
        self.assertIsNone(look_of({**FALL, "pixels": [{"index": i, "count": 1, "color": 1} for i in range(31)]}))

    def test_an_ignored_first_request_is_sent_again(self):
        """4.4.2: the controller sometimes ignores a request on a new
        connection; once more on a fresh one before using the cloud."""
        self.ctl.silent_reads = 1
        self.apply(dict(FALL))
        self.assertEqual(self.shown(), [19])
        self.assertIsNone(self.app.ctrl.lan.failed_at.get(DEV))


class Stretch(ServerBase):
    """4.4.3: Nov 17, 2:56-6:00 AM, the controller answered keep-alives but
    no read. 74 warnings; now one, a reminder each hour, and a line when it
    answers again. Reads are asked again on the same connection first."""
    def setUp(self):
        super().setUp()
        self.app.local_commands(True)
        self.app.ctrl.devices = [{"deviceId": DEV, "name": "Trimlight"}]
        self.lan = self.app.ctrl.lan

    def test_asked_again_on_the_same_connection(self):
        self.ctl.silent_reads = 1
        n = self.ctl.connections
        self.assertIn(self.lan.switch(DEV), (0, 1))
        self.assertEqual(self.ctl.connections - n, 1, "answered on the same connection")
        self.assertIsNone(self.lan.trouble.get(DEV))

    def test_one_warning_then_hourly_then_works_again(self):
        self.ctl.silent_reads = 99
        with self.assertLogs("eaveluxos.localmode", "INFO") as cm:
            self.assertIsNone(self.lan.switch(DEV))
            n = self.ctl.connections
            self.lan.failed_at.pop(DEV, None)         # 5 minutes later
            self.assertIsNone(self.lan.switch(DEV))
            self.assertEqual(self.ctl.connections - n, 1, "one connection per try during a stretch")
            since, said = self.lan.trouble[DEV]
            self.lan.trouble[DEV] = (since, said - 3600)   # an hour later
            self.lan.failed_at.pop(DEV, None)
            self.assertIsNone(self.lan.switch(DEV))
            self.ctl.silent_reads = 0
            self.lan.failed_at.pop(DEV, None)
            self.assertIn(self.lan.switch(DEV), (0, 1))
        warnings = [r.getMessage() for r in cm.records if r.levelname == "WARNING"]
        self.assertEqual(len(warnings), 2, warnings)
        self.assertIn("didn't work", warnings[0])
        self.assertIn("still isn't working (since", warnings[1])
        self.assertIn("works again", cm.records[-1].getMessage())
        self.assertIsNone(self.lan.trouble.get(DEV))


class Resync(ServerBase):
    def test_asks_the_controller_to_send_the_cloud_a_fresh_copy(self):
        r = self.app.resync_cloud()
        self.assertTrue(r["ok"])
        self.assertIn("/device/notify-update-shadow", [p for p, _ in self.F.STATE["log"]])
        self.assertFalse([p for p, _ in self.F.STATE["log"] if p.endswith(("/save", "/delete", "/update"))],
                         "changes nothing on the controller")

    def test_not_twice_in_a_row_and_each_controller_tried(self):
        """4.4.1 (review #7): a second tap within 30 seconds is refused; one
        controller's trouble doesn't skip the others."""
        from eaveluxos.server import ApiError
        self.app.resync_cloud()
        with self.assertRaises(ApiError):
            self.app.resync_cloud()
        self.app._resync_at = None
        api = self.app.client()
        self.app.target_devices = lambda: ["A", "B"]
        seen = []
        def resync(dev, now):
            seen.append(dev)
            if dev == "A":
                from eaveluxos.api import TrimlightError
                raise TrimlightError("no")
        self.app.client = lambda: type("Api", (), {"resync": staticmethod(resync), "get_device": staticmethod(lambda *a, **k: {})})()
        r = self.app.resync_cloud()
        self.assertEqual(seen, ["A", "B"])
        self.assertEqual([d["ok"] for d in r["devices"]], [False, True])

    def test_messages_point_to_it_not_to_the_trimlight_app(self):
        from eaveluxos.api import UNREADABLE_HELP
        self.assertIn("Resync with Trimlight's cloud", UNREADABLE_HELP)
        for f in ("api.py", "safety.py"):
            self.assertNotIn("Open the Trimlight Edge app", (ROOT / "eaveluxos" / f).read_text(encoding="utf-8"))
        js = (ROOT / "eaveluxos" / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn("data-resync", js)


class Connection(ServerBase):
    def test_a_pause_after_the_greeting(self):
        old, L.GREET_PAUSE = L.GREET_PAUSE, 0.3
        self.addCleanup(setattr, L, "GREET_PAUSE", old)
        t = time.monotonic()
        L.Link("127.0.0.1").open().close()
        self.assertGreaterEqual(time.monotonic() - t, 0.3)
        self.assertIn("GREET_PAUSE = 0.5", (ROOT / "eaveluxos" / "lanlink.py").read_text(encoding="utf-8"))

    def test_the_reachability_check_waits_its_turn(self):
        before = len(self.ctl.got)
        n_conn = self.ctl.most_active
        with self.app.lan_io:
            self.app.lan_seen.clear()
            self.app.lan_home()
            time.sleep(0.3)
        self.assertEqual(self.ctl.most_active, n_conn, "no connection opened while busy")

    def test_busy_keeps_what_was_known_and_checks_again_later(self):
        """4.4.1: busy isn't proof it answers (a connection may be stuck
        waiting on a controller that's gone), and the next look checks."""
        addr = self.app._lan_address()
        with self.app.lan_io:
            self.app.lan_seen[addr] = {"ok": False, "at": 0.0, "checking": False, "gen": 0}
            self.app.lan_home()
            time.sleep(0.3)
            self.assertIs(self.app.lan_seen[addr]["ok"], False)
            self.assertFalse(self.app.lan_seen[addr]["checking"])
        self.app.lan_home()
        for _ in range(50):
            if self.app.lan_seen[addr]["ok"]:
                break
            time.sleep(0.05)
        self.assertTrue(self.app.lan_seen[addr]["ok"])


if __name__ == "__main__":
    unittest.main()
