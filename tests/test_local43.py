# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""4.3: local mode. Patterns are saved, put back and deleted, and ports set,
over the home network, checked by reading the controller back; nothing about
patterns goes through Trimlight's cloud any more."""
import copy
import json
import os
import re
import shutil
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from eaveluxos import lanlink as L
from eaveluxos.localmode import Local, LocalError, as_backup
from tests import fake_lan

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(__file__).resolve().parent / "data"


def fixture(name) -> bytes:
    return bytes.fromhex("".join(x for x in (DATA / name).read_text().splitlines() if not x.startswith("#")))


FACTORY = fixture("edge-factory-state.hex")
SAVED = fixture("edge-pattern-save.hex")


def custom(pid, name, colors, mode=0, speed=128, brightness=200, category=1):
    return {"id": pid, "name": name, "category": category, "mode": mode, "speed": speed, "brightness": brightness,
            "pixels": [{"index": i, "count": n, "color": c, "disable": False} for i, (n, c) in enumerate(colors)]
            + [{"index": i, "count": 0, "color": 0, "disable": False} for i in range(len(colors), 30)]}


def factory_holds():
    st = L.read_state(FACTORY)
    pats = {}
    for p in st["patterns"]:
        pats[p["id"]] = L.pattern_record(p["id"], p["name"], p["mode"], p["speed"], p["brightness"],
                                         [(c, tuple(bytes.fromhex(col[1:])), on) for c, col, on in p["slots"]])
    return {"ports": [(1, 600, 1)] * 4, "patterns": pats}


class Layout(unittest.TestCase):
    """Against what a real controller and the real Trimlight app sent."""

    def test_reads_a_real_controller(self):
        st = L.read_state(FACTORY)
        self.assertEqual([p["id"] for p in st["patterns"]], list(range(1, 10)))
        self.assertEqual(st["patterns"][8]["name"], "CHRISTMAS")
        self.assertEqual(st["patterns"][8]["slots"][:2], [[5, "#FF0000", 1], [5, "#00FF00", 1]])
        self.assertEqual(st["ports"], [{"port": i, "start": 1, "end": 600} for i in range(1, 5)])

    def test_writes_records_as_the_trimlight_app_does(self):
        rec = SAVED[3:]
        p = L.read_record(rec)
        self.assertEqual((p["id"], p["name"], p["mode"], p["speed"], p["brightness"]), (10, "test1126", 0, 128, 255))
        mine = L.record_from_effect(10, {"name": "test1126", "category": 1, "mode": 0, "speed": 128, "brightness": 255,
                                         "pixels": [{"index": i, "count": c, "color": int(col[1:], 16), "disable": not on}
                                                    for i, (c, col, on) in enumerate(p["slots"])]})
        self.assertEqual(mine, rec)
        self.assertEqual(L.request(L.SUB_PATTERN_SAVE, mine), SAVED)
        self.assertEqual(L.request(L.SUB_PORT, bytes([0, 0, 1, 0, 0x53, 1])), bytes.fromhex("0a0006000001005301"))
        self.assertEqual(L.read_state(L.state_payload([(1, 600)] * 4, [L.pattern_record(1, "A", 0, 1, 2, [])]))["patterns"][0]["name"], "A")

    def test_refuses_what_it_cant_write(self):
        with self.assertRaises(ValueError):
            L.record_from_effect(5, {"name": "Chase", "category": 0, "mode": 3})
        with self.assertRaises(ValueError):
            L.record_from_effect(5, custom(5, "Long", [(300, 0xFF0000)]))
        with self.assertRaises(ValueError):
            L.record_from_effect(5, custom(5, "", [(3, 0xFF0000)]))
        with self.assertRaises(L.LinkError):
            L.read_state(L.request(L.SUB_TIME, b"\x01" * 30))       # says 1 pattern, holds none


class WithController(unittest.TestCase):
    def setUp(self):
        os.environ["EAVELUXOS_LAN_TEST"] = "1"
        self.ctl = fake_lan.FakeController(holds=factory_holds())
        self.addCleanup(self.ctl.close)
        self.port, L.TCP_PORT = L.TCP_PORT, self.ctl.port
        self.addCleanup(setattr, L, "TCP_PORT", self.port)
        self.backups = []
        self.loc = Local("127.0.0.1", backup=self.backups.append, gap=0.05)

    def tearDown(self):
        os.environ.pop("EAVELUXOS_LAN_TEST", None)

    def ids(self):
        return sorted(self.ctl.holds["patterns"])


class Patterns(WithController):
    BACKUP = {"effects": [custom(10, "American Flag", [(5, 0xFFFFFF), (5, 0xFF0000)], mode=1),
                          custom(11, "Dolly", [(3, 0xFF00FF)]),
                          custom(9, "Christmas", [(1, 0x00FF00)]),                 # already there (other capitals)
                          custom(20, "Chase", [], category=0),                     # a built-in effect
                          custom(30, "Dolly", [(3, 0x00FFFF)])]}                  # the same name twice

    def test_puts_back_one_at_a_time_with_their_old_numbers(self):
        r = self.loc.restore(self.BACKUP, [10, 11, 9, 20, 30])
        self.assertEqual(r, {"restored": ["American Flag", "Dolly"], "skipped": ["Christmas"],
                             "duplicates": ["Dolly"], "builtin": ["Chase"]})
        self.assertEqual(self.ids(), list(range(1, 12)))
        back = L.read_record(self.ctl.holds["patterns"][10])
        self.assertEqual((back["name"], back["mode"], back["slots"][1]), ("American Flag", 1, [5, "#FF0000", 1]))
        self.assertEqual(len(self.backups), 1)
        self.assertEqual(len(as_backup(L.read_state(FACTORY))["effects"]), 9)
        # Each pattern: a keep-alive answered, create, then save; then read back.
        subs = [b[0] for _, _, b in self.ctl.frames(L.CMD_REQUEST)]
        self.assertEqual(subs, [0x15, 0x0F, 0x0E, 0x15, 0x0F, 0x0E, 0x15])

    def test_a_taken_number_gets_the_first_free_one(self):
        self.ctl.holds["patterns"][10] = L.pattern_record(10, "Mine", 0, 1, 2, [])
        self.loc.restore(self.BACKUP, [10])
        self.assertEqual(L.read_record(self.ctl.holds["patterns"][11])["name"], "American Flag")

    def test_stops_at_the_first_difference(self):
        self.ctl.ignore = {L.SUB_PATTERN_NEW, L.SUB_PATTERN_SAVE}     # it doesn't take the save
        with self.assertRaises(LocalError) as cm:
            self.loc.restore(self.BACKUP, [10, 11])
        self.assertIn("Stopped after “American Flag”", str(cm.exception))
        self.assertIn("Put back before it: none", str(cm.exception))
        saves = [b[3] for _, _, b in self.ctl.frames(L.CMD_REQUEST) if b[0] == L.SUB_PATTERN_SAVE]
        self.assertEqual(saves, [10, 10], "sent once more when it didn't take (4.3.8), never a second pattern")

    def test_a_controller_with_two_patterns_on_one_number_is_left_alone(self):
        good = self.ctl.holds["patterns"]
        bad = L.state_payload([(1, 600)] * 4, [good[1], good[1]])
        with self.assertRaises(LocalError):
            self.loc._start(type("Fake", (), {"state": lambda s, now: L.read_state(bad)})())

    def test_save_and_delete(self):
        pid = self.loc.save(custom(0, "Porch", [(2, 0xFFB46B)]))
        self.assertEqual(pid, 10)
        with self.assertRaises(LocalError):
            self.loc.save(custom(0, "porch", [(2, 0xFFB46B)]))            # the name is taken
        with self.assertRaises(LocalError) as cm:
            self.loc.delete(10, "Something else")                       # not that pattern: nothing deleted
        self.assertIn("nothing was deleted", str(cm.exception))
        self.assertIn(10, self.ids())
        self.loc.delete(10, "Porch")
        self.assertNotIn(10, self.ids())


class Ports(WithController):
    def test_sets_ports_and_reads_them_back(self):
        changed = self.loc.ports([{"start": 1, "end": 83, "on": True}, {"start": 84, "end": 138, "on": True},
                                  {"start": 1, "end": 600, "on": False}, {"start": 1, "end": 600, "on": False}])
        self.assertEqual(len(changed), 4)
        self.assertEqual(self.ctl.holds["ports"], [(1, 83, 1), (84, 138, 1), (1, 600, 0), (1, 600, 0)])

    def test_refuses_bad_layouts_before_writing(self):
        for bad in ([{"start": 0, "end": 5, "on": True}] * 4, [{"start": 1, "end": 5, "on": False}] * 4, []):
            with self.assertRaises(LocalError):
                self.loc.ports(bad)
        self.assertEqual(self.ctl.frames(L.CMD_REQUEST), [])

    def test_a_port_that_doesnt_take_stops(self):
        self.ctl.ignore = {L.SUB_PORT}
        with self.assertRaises(LocalError) as cm:
            self.loc.ports([{"start": 1, "end": 83, "on": True}] + [{"start": 1, "end": 600, "on": True}] * 3)
        self.assertIn("Stopped at port 1", str(cm.exception))


class ServerBase(WithController):
    def setUp(self):
        super().setUp()
        import eaveluxos.api
        from eaveluxos.server import App
        from tests import fake_trimlight as F
        self.F = F
        cloud = F.start()
        saved = eaveluxos.api.BASE_URL
        eaveluxos.api.BASE_URL = f"http://127.0.0.1:{cloud.server_address[1]}/trimlight"
        self.addCleanup(setattr, eaveluxos.api, "BASE_URL", saved)
        self.dev = copy.deepcopy(F.STATE["dev"])
        self.addCleanup(F.STATE.__setitem__, "dev", self.dev)
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d, True)
        self.app = App(d, start=False)
        self.addCleanup(self.app.store.close)
        s = copy.deepcopy(self.app.store.settings)
        s["location"].update(latitude=39.95, longitude=-75.16)
        s["setup_done"] = True
        s["lan"] = {"address": "127.0.0.1"}
        self.app.store.save_settings(s)
        self.app.store.save_secrets(client_id=F.CID, client_secret=F.SECRET)
        self.app.rebuild()
        F.STATE["log"].clear()

    def cloud_pattern_writes(self):
        return [p for p, _ in self.F.STATE["log"] if p.startswith("/device/effect/") and p.endswith(("/save", "/delete"))]



class Server(ServerBase):
    """The app: Pattern backups, the designer and the Lights tab go over the
    home network, and Trimlight's cloud never saves or deletes a pattern."""

    def test_put_back_from_a_backup(self):
        self.app.safety.backup_dir.mkdir(parents=True, exist_ok=True)
        name = "TL-EDGE-01-20261113-172240-460361.json"
        (self.app.safety.backup_dir / name).write_text(json.dumps(Patterns.BACKUP), encoding="utf-8")
        r = self.app.restore_patterns(name, [10, 11])
        self.assertEqual(r["restored"], ["American Flag", "Dolly"])
        self.assertEqual(self.cloud_pattern_writes(), [])
        self.assertTrue([f for f in self.app.safety.backup_dir.glob("TL-EDGE-01-*.json") if f.name != name],
                        "the controller as read first is kept as a backup")
        st = self.app.local_state()
        self.assertEqual(st["patterns"][-1]["name"], "Dolly")

    def test_designer_saves_on_the_controller(self):
        r = self.app.save_to_controller({"name": "Porch", "effect": {"colors": ["#FFB46B"], "counts": [2]}})
        self.assertEqual(r["saved"][0]["id"], 10)
        self.assertEqual(self.cloud_pattern_writes(), [])

    def test_lights_tab_ports_go_over_the_home_network(self):
        r = self.app.update_device({"deviceId": "TL-EDGE-01", "ports": [{"id": 0, "start": 1, "end": 83},
                                    {"id": 1, "start": 84, "end": 138}, {"id": 2, "start": 0, "end": 0},
                                    {"id": 3, "start": 0, "end": 0}]})
        self.assertTrue(r["local"])
        self.assertEqual(self.ctl.holds["ports"], [(1, 83, 1), (84, 138, 1), (1, 600, 0), (1, 600, 0)])
        self.assertNotIn("/device/update", [p for p, _ in self.F.STATE["log"]])

    def test_delete_and_no_address(self):
        from eaveluxos.server import ApiError
        self.app.local_delete(9, "CHRISTMAS")
        self.assertNotIn(9, self.ids())
        s = copy.deepcopy(self.app.store.settings)
        s.pop("lan")
        self.app.store.save_settings(s)
        with self.assertRaises(ApiError) as cm:
            self.app.save_to_controller({"name": "Porch", "effect": {"colors": ["#FFB46B"], "counts": [2]}})
        self.assertIn("home network", str(cm.exception))
        self.assertEqual(self.cloud_pattern_writes(), [])

    def test_backup_timer_off_deletes_no_pattern(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        d = self.F.STATE["dev"]
        d["effects"].append({"id": 30, "name": "Auto Fall", "category": 1, "mode": 0, "pixels": []})
        self.app.safety.state["devices"]["TL-EDGE-01"] = {"effects": {"fall|{}": 30}, "calendar": []}
        notes = []
        self.assertTrue(self.app.safety.remove(self.app.client(), ["TL-EDGE-01"],
                                               datetime(2026, 11, 15, 12, tzinfo=ZoneInfo("America/New_York")),
                                               lambda m, lvl=0: notes.append(m)))
        self.assertEqual(self.cloud_pattern_writes(), [])
        self.assertIn("Auto Fall", notes[-1])


class ReviewFixes431(ServerBase):
    """The 4.3.0 review (tests/repro_off_port_readback.py is #1)."""

    def test_1_a_port_switched_off_isnt_judged_by_its_numbers(self):
        self.ctl.off_reads_zero = True
        changed = self.loc.ports([{"start": 1, "end": 83, "on": True}, {"start": 84, "end": 138, "on": True},
                                  {"start": 1, "end": 600, "on": False}, {"start": 1, "end": 600, "on": False}])
        self.assertEqual(len(changed), 4)
        self.assertEqual(self.ctl.holds["ports"][3], (1, 600, 0))

    def test_2_a_controller_that_tidies_unused_slots_still_passes(self):
        self.ctl.tidies_slots = True
        e = custom(10, "Leftovers", [(3, 0xFF0000)])
        e["pixels"][5]["color"] = 0x7241DA            # an unused slot keeps a color, as the Trimlight app leaves them
        self.assertEqual(self.loc.restore({"effects": [e, custom(11, "Next", [(2, 0x00FF00)])]}, [10, 11])["restored"],
                         ["Leftovers", "Next"])

    def test_3_reading_the_controller_keeps_the_clock_offset(self):
        s = copy.deepcopy(self.app.store.settings)
        s.setdefault("controller", {})["clock_offset_min"] = 90
        self.app.store.save_settings(s)
        self.app.rebuild()
        before = self.app.now()
        self.app.local_state()
        t = next(b for _, _, b in self.ctl.frames(L.CMD_REQUEST) if b[0] == L.SUB_TIME)[3:]
        sent = datetime(2000 + t[0], t[1], t[2], t[4], t[5], t[6])
        want = (before.replace(tzinfo=None) + __import__("datetime").timedelta(minutes=90))
        self.assertLess(abs((sent - want).total_seconds()), 5)

    def test_4_one_job_at_a_time(self):
        from eaveluxos.server import ApiError
        self.app.local_busy.acquire()
        try:
            with self.assertRaises(ApiError) as cm:
                self.app.local_delete(9, "CHRISTMAS")
            self.assertIn("Another change", str(cm.exception))
            with self.assertRaises(ApiError):
                self.app.musiclink({"op": "start", "tab": "t1", "pattern": 0, "sensitivity": 8})
        finally:
            self.app.local_busy.release()
        self.assertIn(9, self.ids())

    def test_5_each_port_once(self):
        from eaveluxos.server import ApiError
        with self.assertRaises(ApiError):
            self.app.update_device({"deviceId": "TL-EDGE-01", "ports": [{"id": 0, "start": 1, "end": 9}] * 2
                                    + [{"id": 1, "start": 1, "end": 9}, {"id": 2, "start": 1, "end": 9}]})
        self.assertEqual(self.ctl.frames(L.CMD_REQUEST), [])

    def test_6_a_short_answer_is_refused_cleanly(self):
        with self.assertRaises(L.LinkError):
            L.read_state(L.request(L.SUB_TIME, b"\x01" * 10) + b"\x00" * 40)

    def test_7_works_while_the_cloud_is_down(self):
        from eaveluxos.server import ApiError
        self.app.store.settings.setdefault("service", {})["devices"] = []
        self.app.target_devices = lambda ids=None: (_ for _ in ()).throw(ApiError("cloud down", 502))
        self.app.ctrl.devices = [{"deviceId": "TL-EDGE-01"}]
        self.assertEqual(len(self.app.local_state()["patterns"]), 9)

    def test_8_names_too_long_for_the_controller(self):
        with self.assertRaises(LocalError):
            self.loc.save(custom(0, "A name much too long for it", [(1, 0xFF0000)]))


class Reliability436(ServerBase):
    """4.3.6: Pattern backups said "The controller didn't answer" while Test
    connection read the controller fine."""

    def test_a_keep_alive_comes_first(self):
        self.ctl.needs_ping = True
        self.assertEqual(len(self.loc.read()["patterns"]), 9)

    def test_panels_opened_together_share_one_connection(self):
        import threading
        out, errs = [], []

        def read():
            try:
                out.append(self.app.local_state(fresh=True))
            except Exception as e:          # noqa: BLE001
                errs.append(e)
        ts = [threading.Thread(target=read) for _ in range(3)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual((len(out), errs), (3, []))
        self.assertEqual(self.ctl.most_active, 1, "one connection at a time")
        n = len([1 for _, _, b in self.ctl.frames(L.CMD_REQUEST) if b[0] == L.SUB_TIME])
        self.app.local_state()
        self.assertEqual(len([1 for _, _, b in self.ctl.frames(L.CMD_REQUEST) if b[0] == L.SUB_TIME]), n,
                         "a read seconds ago is shared")

    def test_tries_once_more(self):
        self.ctl.silent_reads = 1
        self.assertEqual(len(self.loc.read()["patterns"]), 9)

    def test_not_during_a_show_from_this_computer(self):
        from eaveluxos.server import ApiError
        self.app.lanshow.running = lambda: True
        with self.assertRaises(ApiError) as cm:
            self.app.local_state()
        self.assertIn("music show", str(cm.exception))

    def test_back_up_now(self):
        from eaveluxos import restore
        r = self.app.local_backup()
        self.assertEqual(r["patterns"], 9)
        listed = restore.list_backups(self.app.safety.backup_dir)
        self.assertIn(r["file"], [b["file"] for b in listed])
        det = restore.read_backup(self.app.safety.backup_dir, r["file"])
        self.assertEqual(len(restore.patterns_in(det)), 9)

    def test_screen(self):
        js = (ROOT / "eaveluxos" / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn("data-lcbackup", js)
        self.assertIn("so patterns can\\u2019t be put back yet", js)


class ReviewFixes436(ServerBase):
    """The 4.3.6 review (tests/repro_show_vs_read.py is #1)."""

    def test_1_a_show_waits_for_a_read(self):
        import threading
        done, seen = threading.Event(), []
        self.app.lanshow.start = lambda *a, **k: seen.append(done.is_set())
        self.app.lan_io.acquire()
        t = threading.Thread(target=self.app.musiclink, args=({"op": "start", "tab": "t1", "pattern": 0, "sensitivity": 8},))
        t.start()
        t.join(0.3)
        done.set()
        self.app.lan_io.release()
        t.join(5)
        self.assertEqual(seen, [True])
        self.app.ctrl.stop_music()

    def test_1_no_read_once_a_show_has_the_connection(self):
        loc, _ = self.app.local(write=False)
        loc.blocked = lambda: True
        with self.assertRaises(LocalError) as cm:
            loc.read()
        self.assertIn("music show", str(cm.exception))
        self.assertFalse(self.app.lan_io.locked())

    def test_2_back_up_now_saves_its_own_read(self):
        from eaveluxos import restore
        self.app._after_local_write = lambda dev: None
        real = self.app._local_read

        def read(fresh=False):
            r = real(fresh)
            self.app._local_seen = (0.0, None, None)        # a change elsewhere clears the shared read
            return r
        self.app._local_read = read
        r = self.app.local_backup()
        det = restore.read_backup(self.app.safety.backup_dir, r["file"])
        self.assertEqual(len(det["effects"]), 9)

    def test_3_a_new_address_reads_again(self):
        self.app.local_state()
        self.app._local_seen = (self.app._local_seen[0], {"ports": [], "patterns": []}, "10.0.0.99")
        self.assertEqual(len(self.app.local_state()["patterns"]), 9)

    def test_5_a_celebration_without_its_pattern_is_reported(self):
        from tests.test_celebrate435 import settings
        from eaveluxos.schedule import ConfigError, build_config
        s = settings(enabled=False, celebrate_enabled=True)
        s["gameday"]["teams"][0]["effect"] = "gone"
        with self.assertRaises(ConfigError):
            build_config(s, {"client_id": "x", "client_secret": "y"})


class SlowController438(WithController):
    """4.3.8: on Nov 15 a pattern put back fourth in a row wasn't there one
    second later, and putting it back again worked."""

    def test_a_change_that_shows_late_passes(self):
        self.ctl.late_reads = 1             # the first read after a change still shows the old state
        r = self.loc.restore(Patterns.BACKUP, [10, 11])
        self.assertEqual(r["restored"], ["American Flag", "Dolly"])
        saves = [b[3] for _, _, b in self.ctl.frames(L.CMD_REQUEST) if b[0] == L.SUB_PATTERN_SAVE]
        self.assertEqual(saves, [10, 11], "no resend needed")

    def test_a_change_that_didnt_take_is_sent_once_more(self):
        self.ctl.drop_saves = 1             # the first save is lost
        r = self.loc.restore(Patterns.BACKUP, [10, 11])
        self.assertEqual(r["restored"], ["American Flag", "Dolly"])
        self.assertEqual(L.read_record(self.ctl.holds["patterns"][10])["name"], "American Flag")


class FirstRead439(WithController):
    def test_a_job_reads_once_more_before_giving_up(self):
        self.ctl.silent_reads = 1
        self.assertEqual(self.loc.save(custom(0, "Porch", [(2, 0xFFB46B)])), 10)

    def test_says_what_to_check(self):
        self.ctl.silent_reads = 4
        with self.assertRaises(LocalError) as cm:
            self.loc.save(custom(0, "Porch", [(2, 0xFFB46B)]))
        self.assertIn("Trimlight Edge app is open", str(cm.exception))


class Mislabeled4310(unittest.TestCase):
    """Nov 16, 2026, 3:13 PM: the controller answered a read with 1,940 bytes
    whose length said 1,855, while Trimlight's cloud couldn't parse it (12006)."""

    def mislabeled(self):
        body = L.state_payload([(1, 600)] * 4, [L.pattern_record(i, f"P{i}", 0, 1, 2, []) for i in range(1, 10)],
                               tail=b"\x00" * 249)
        f = bytearray(L.frame(L.CMD_REQUEST, body))
        f[8:10] = (len(body) - 58).to_bytes(2, "big")
        return bytes(f), body

    def test_read_as_the_length_its_check_fits(self):
        f, body = self.mislabeled()
        msgs, rest = L.parse(f + L.frame(L.CMD_PING, b"\x01"), resync=True)
        self.assertEqual([(m[0], m[2]) for m in msgs][0], ("frame", body))
        self.assertEqual(rest, b"")
        self.assertEqual(len(L.read_state(body)["patterns"]), 9)

    def test_waits_while_more_may_come(self):
        f, _ = self.mislabeled()
        self.assertEqual(L.parse(f[:-40], resync=True), ([], f[:-40]))

    def test_an_unreadable_one_is_kept_for_a_look(self):
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d, True)
        old, L.DUMP_DIR = L.DUMP_DIR, d
        self.addCleanup(setattr, L, "DUMP_DIR", old)
        for i in range(7):
            L.save_unread("10.0.0.5", bytes([i]) * 200)
        kept = sorted(d.glob("lan-unread-*.bin"))
        self.assertEqual(len(kept), L.DUMPS_KEPT)
        self.assertEqual([f.read_bytes()[0] for f in kept], [2, 3, 4, 5, 6], "the newest, none overwritten")

    def test_same_instant_never_overwrites(self):
        from unittest import mock
        from datetime import datetime as real
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d, True)
        old, L.DUMP_DIR = L.DUMP_DIR, d
        self.addCleanup(setattr, L, "DUMP_DIR", old)
        frozen = mock.Mock(wraps=real)
        frozen.now.return_value = real(2026, 11, 16, 20, 33, 49, 488586)     # Windows: the same tick each time
        with mock.patch.object(L, "datetime", frozen):
            for i in range(3):
                L.save_unread("10.0.0.5", bytes([i]) * 200)
        self.assertEqual(len(list(d.glob("lan-unread-*.bin"))), 3)

    def test_backups_keep_the_raw_answer(self):
        st = L.read_state(FACTORY)
        self.assertEqual(as_backup(st)["controller_raw"], FACTORY.hex())


class GoesQuiet4312(WithController):
    """Nov 16, 2026, 4:06 PM: "Local restore stopped at 'American Flag': the
    connection failed: The controller didn't answer." """

    def test_asked_again_on_a_fresh_connection(self):
        self.ctl.quiet_after_save = 1
        r = self.loc.restore(Patterns.BACKUP, [10, 11])
        self.assertEqual(r["restored"], ["American Flag", "Dolly"])
        saves = [b[3] for _, _, b in self.ctl.frames(L.CMD_REQUEST) if b[0] == L.SUB_PATTERN_SAVE]
        self.assertEqual(saves, [10, 11], "found already saved: not sent twice")

    def test_still_stops_when_it_stays_quiet(self):
        self.ctl.quiet_after_save = 5
        self.ctl.silent_reads = 99
        with self.assertRaises(LocalError) as cm:
            self.loc.restore(Patterns.BACKUP, [10, 11])
        self.assertIn("didn't answer", str(cm.exception))
        self.assertLessEqual(sum(1 for _, _, b in self.ctl.frames(L.CMD_REQUEST) if b[0] == L.SUB_PATTERN_SAVE), 1,
                             "never a second pattern")


class Overstated4313(WithController):
    """Nov 16, 2026, 4:43 PM: Pattern backups kept saying "didn't answer"
    and nothing was saved: an answer whose length says more than it holds."""

    def test_read_anyway(self):
        self.ctl.overstate = 40
        self.assertEqual(len(self.loc.read()["patterns"]), 9)

    def test_message_has_one_period(self):
        self.ctl.silent_reads = 9
        with self.assertRaises(LocalError) as cm:
            self.loc.read()
        self.assertNotIn("..", str(cm.exception))


class SampleFilesReachGitHub(unittest.TestCase):
    """4.3.4: ".gitignore" kept tests/data off GitHub, so its tests failed there."""

    def test_not_ignored(self):
        import shutil as sh
        import subprocess
        if not (sh.which("git") and (ROOT / ".git").exists()):
            self.skipTest("not a git checkout")
        files = [str(f.relative_to(ROOT)) for f in DATA.iterdir()]
        r = subprocess.run(["git", "check-ignore", *files], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.stdout.strip(), "", "ignored by .gitignore: " + r.stdout)


class NoCloudPatternWrites(unittest.TestCase):
    def test_nothing_calls_them(self):
        for f in (ROOT / "eaveluxos").glob("*.py"):
            if f.name == "api.py":
                continue
            src = f.read_text(encoding="utf-8")
            self.assertFalse(re.search(r"\.(save_effect|effect_delete)\(", src), f"{f.name} saves or deletes a pattern through the cloud")

    def test_panel(self):
        js = (ROOT / "eaveluxos" / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn("async function localPanel", js)
        self.assertIn("fold('local'", js)


if __name__ == "__main__":
    unittest.main()
