# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""4.1: music from this computer. The controller's local messages (checked
against frames from a real capture), the connection, the stream, the app's
endpoints and roles, and the capture kit's decoder."""
import copy
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path

from eaveluxos import lanlink as L
from tests import fake_lan

ROOT = Path(__file__).resolve().parent.parent

# Frames from the November 2026 capture (firmware 1.17.77): nothing private.
REAL = {
    "time": "5350544543480400000a9d9054596a158cc8c4651889dce64350e9fce9eef3e2e6eee5dbe6",
    "ping": "5350544543480b00000155a54008ad1ba589aa210d2629c1df412223",
    "ack": "5350544543480b00000100",
    "music": "5350544543480400001a86d7b46c71e87ff129335bbabb7add07e8e4e8ffeae917e8e8d4e0e8e8e8e8e8e8e8e8e8e8e8e8e8e8e8e8",
    "levels": "5350544543480a00001abf2967aa03345b9745620b77cc5f5326dcd0dccbddde23dcdce0d2dcdcdcddc4dcdcdcdcd5dbdcdcdcdcdc",
    # the second capture: lights off, lights on, leaving Music
    "off": "53505445434804000004a159f2b21d2754542e64d9e4f3cb4c932c2e2c2d2c",
    "on": "53505445434804000004a221a256b30839bb16b3a023feaaf5299597959494",
    "leave": "53505445434804000004d1d7f1c27d651ae122eb8fdb1db3d9b5c6c2c6c7c8",
}


def wait_for(cond, secs=3.0):
    end = time.monotonic() + secs
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.02)
    return cond()


class Frames(unittest.TestCase):
    def test_real_frames_decode_and_encode_byte_for_byte(self):
        for name, hx in REAL.items():
            raw = bytes.fromhex(hx)
            msgs, rest = L.parse(raw, final=True)
            self.assertEqual(rest, b"", name)
            kind, cmd, body = msgs[0]
            if kind == "frame":
                self.assertEqual(L.frame(cmd, body, key=raw[26]), raw, name)
        _, _, t = L.parse(bytes.fromhex(REAL["time"]))[0][0]
        self.assertEqual(t, L.time_payload(datetime(2026, 11, 15, 12, 50, 15)))
        _, _, m = L.parse(bytes.fromhex(REAL["music"]))[0][0]
        self.assertEqual(m, L.music_payload(2, 1, 8))
        self.assertEqual(L.read_music(m), {"source": 2, "pattern": 1, "sensitivity": 8, "levels": [0] * 16})
        _, cmd, lv = L.parse(bytes.fromhex(REAL["levels"]))[0][0]
        self.assertEqual(cmd, L.CMD_LEVELS)
        self.assertEqual(L.read_music(lv)["levels"], [0, 0, 0, 1, 24, 0, 0, 0, 0, 9, 7, 0, 0, 0, 0, 0])
        body = lambda k: L.parse(bytes.fromhex(REAL[k]))[0][0][2]
        self.assertEqual(body("off"), L.request(L.SUB_POWER, b"\x00"))
        self.assertEqual(body("on"), L.request(L.SUB_POWER, b"\x01"))
        self.assertEqual(body("leave"), L.request(L.SUB_MODE, bytes([L.MODE_NORMAL])))

    def test_greeting_is_new_each_time(self):
        seen = {L.greeting() for _ in range(20)}
        self.assertGreater(len(seen), 15)
        for g in seen:
            self.assertEqual(g[:6], b"S\x01\x00\x00\x04\x04")
            self.assertTrue(all(chr(c) in L.GREETING_CHARS for c in g[6:]))
            self.assertEqual(L.parse(g)[0][0][0], "hello")

    def test_arrives_in_pieces(self):
        stream = b"".join(bytes.fromhex(REAL[k]) for k in ("ack", "time", "ack", "levels"))
        stream = b"S\x01\x00\x00\x03\x03abc" + stream
        whole = L.parse(stream, final=True)[0]
        for cut in range(1, len(stream)):
            got, rest = L.parse(stream[:cut])
            more, rest = L.parse(rest + stream[cut:], final=True)
            self.assertEqual(got + more, whole, cut)
            self.assertEqual(rest, b"")

    def test_part_of_a_frame_is_not_taken_for_a_short_answer(self):
        ping = bytes.fromhex(REAL["ping"])
        self.assertEqual(L.parse(ping[:11], short=False), ([], ping[:11]), "waits for the rest")
        self.assertEqual(L.parse(bytes.fromhex(REAL["ack"]))[0], [("short", 11, b"\x00")])

    def test_damaged_and_strange(self):
        bad = bytearray(bytes.fromhex(REAL["music"]))
        bad[30] ^= 1
        with self.assertRaises(L.LinkError):
            L.parse(bytes(bad), final=True)
        for junk in (b"HTTP/1.1 400", b"\x00" * 12):
            with self.assertRaises(L.LinkError):
                L.parse(junk)
        huge = L.MAGIC + b"\x04\x00\xff\xff"
        self.assertEqual(L.parse(huge)[0], [])          # 65535 is allowed, just not here yet
        with self.assertRaises(L.LinkError):
            L.parse(L.MAGIC + b"\x04\x00" + (L.MAX_FRAME + 1).to_bytes(2, "big") if L.MAX_FRAME < 0xFFFF else b"HTTP")

    def test_checks(self):
        for bad in (dict(source=3, pattern=0, sensitivity=5), dict(source=1, pattern=-1, sensitivity=5),
                    dict(source=1, pattern=20, sensitivity=5), dict(source=1, pattern=0, sensitivity=0),
                    dict(source=1, pattern=0, sensitivity=15)):
            with self.assertRaises(ValueError, msg=bad):
                L.music_payload(**bad)
        for bad in ([0] * 15, [256] + [0] * 15, [-1] + [0] * 15, [0.5] + [0] * 15):
            with self.assertRaises(ValueError):
                L.music_payload(1, 0, 5, bad)
        self.assertEqual(L.check_address(" 10.168.168.35 "), "10.168.168.35")
        for bad in ("8.8.8.8", "example.com", "", "192.168.1", "::1"):
            with self.assertRaises(L.LinkError, msg=bad):
                L.check_address(bad)
        os.environ.pop("EAVELUXOS_LAN_TEST", None)
        with self.assertRaises(L.LinkError):
            L.check_address("127.0.0.1")

    def test_names(self):
        self.assertEqual(L.names_in(fake_lan.DUMP), ["VALENTINE'S DAY", "CHRISTMAS", "American Flag"])


class LinkAndStream(unittest.TestCase):
    def setUp(self):
        self.ctl = fake_lan.FakeController()
        self.addCleanup(self.ctl.close)
        self.make = lambda host: L.Link(host, self.ctl.port, timeout=1.0)

    def test_hello_ping_and_read(self):
        with self.make("127.0.0.1") as link:
            self.assertTrue(link.greeting.startswith(b"cG0o"))
            self.assertLess(link.ping(), 1000)
            dump = link.read_all(datetime(2026, 11, 15, 12, 50, 15))
        self.assertEqual(self.ctl.got[0][:2], ("hello", None))
        self.assertEqual(len(self.ctl.got[0][2]), 4)
        self.assertIn(b"CHRISTMAS", dump)
        self.assertEqual(self.ctl.errors, [])

    def test_unreachable_and_silent(self):
        with self.assertRaises(L.LinkError) as cm:
            L.Link("127.0.0.1", 1, timeout=0.5).open()
        self.assertIn("Couldn't reach", str(cm.exception))
        quiet = fake_lan.FakeController(greet=False)
        self.addCleanup(quiet.close)
        with self.assertRaises(L.LinkError) as cm:
            L.Link("127.0.0.1", quiet.port, timeout=0.4).open()
        self.assertIn("didn't answer", str(cm.exception))

    def test_stream_sends_levels_settings_and_keepalives(self):
        ended = []
        st = L.Streamer(on_end=ended.append, idle=0.6, link_factory=self.make)
        st.start("127.0.0.1", 3, 9, "tab1")
        self.assertTrue(st.running())
        st.feed([10] * 16, "tab1")
        self.assertTrue(wait_for(lambda: any(L.read_music(b)["levels"] == [10] * 16 for _, _, b in self.ctl.frames(L.CMD_LEVELS))))
        self.assertTrue(st.adjust("tab1", sensitivity=12))
        self.assertTrue(wait_for(lambda: any((L.read_music(b) or {}).get("sensitivity") == 12 for _, _, b in self.ctl.frames(L.CMD_REQUEST))))
        self.assertFalse(st.feed([1] * 16, "other tab"), "another page can't feed it")
        with self.assertRaises(L.LinkError):
            st.start("127.0.0.1", 3, 9, "other tab")
        first = L.read_music(self.ctl.frames(L.CMD_REQUEST)[0][2])
        self.assertEqual(first, {"source": 1, "pattern": 3, "sensitivity": 9, "levels": [0] * 16})
        self.assertTrue(wait_for(lambda: not st.running(), 3), "quiet page: ends by itself")
        self.assertEqual(ended, ["idle"])
        self.assertEqual(self.ctl.frames(L.CMD_REQUEST)[-1][2], L.request(L.SUB_MODE, bytes([L.MODE_NORMAL])),
                         "leaves music mode at the end, like the Trimlight app")
        gaps = self.ctl.frames(L.CMD_LEVELS)
        self.assertGreater(len(gaps), 3)
        self.assertEqual(self.ctl.errors, [], "every frame checked out")

    def test_stop_and_wanted(self):
        ended = []
        st = L.Streamer(on_end=ended.append, link_factory=self.make)
        st.start("127.0.0.1", 0, 5, "t")
        self.assertTrue(st.stop("t"))
        self.assertFalse(st.running())
        flag = {"on": True}
        st.start("127.0.0.1", 0, 5, "t", wanted=lambda: flag["on"])
        flag["on"] = False
        self.assertTrue(wait_for(lambda: not st.running()))
        self.assertEqual(ended, ["stopped", "app"])

    def test_lost_connection_reconnects_then_gives_up(self):
        flaky = fake_lan.FakeController(close_after=4)
        self.addCleanup(flaky.close)
        ended = []
        st = L.Streamer(on_end=ended.append, link_factory=lambda h: L.Link(h, flaky.port, timeout=0.5))
        st.start("127.0.0.1", 0, 5, "t")
        for _ in range(60):
            st.feed([5] * 16, "t")
            time.sleep(0.03)
            if not st.running():
                break
        self.assertTrue(wait_for(lambda: not st.running(), 5))
        self.assertGreaterEqual(flaky.connections, 2, "tried again")
        self.assertEqual(ended, ["lost"])
        self.assertEqual(flaky.errors, [])
        self.assertTrue(st.status()["error"])


class AppEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import eaveluxos.api
        from tests import fake_trimlight as F
        cls.F = F
        cls.cloud = F.start()
        cls._saved = eaveluxos.api.BASE_URL
        eaveluxos.api.BASE_URL = f"http://127.0.0.1:{cls.cloud.server_address[1]}/trimlight"
        os.environ["EAVELUXOS_LAN_TEST"] = "1"
        from eaveluxos.server import App
        cls.dir = Path(tempfile.mkdtemp())
        cls.app = App(cls.dir, start=False)
        s = copy.deepcopy(cls.app.store.settings)
        s["location"].update(latitude=39.95, longitude=-75.16)
        s["setup_done"] = True
        cls.app.store.save_settings(s)
        cls.app.store.save_secrets(client_id=F.CID, client_secret=F.SECRET)
        cls.app.rebuild()

    @classmethod
    def tearDownClass(cls):
        import eaveluxos.api
        cls.app.store.close()
        shutil.rmtree(cls.dir, ignore_errors=True)
        eaveluxos.api.BASE_URL = cls._saved
        os.environ.pop("EAVELUXOS_LAN_TEST", None)

    def setUp(self):
        self.ctl = fake_lan.FakeController()
        self.addCleanup(self.ctl.close)
        self._port = L.TCP_PORT
        L.TCP_PORT = self.ctl.port
        self.addCleanup(lambda: setattr(L, "TCP_PORT", self._port))
        self.addCleanup(lambda: self.app.lanshow.stop())

    def test_address_and_test(self):
        from eaveluxos.server import ApiError
        with self.assertRaises(ApiError):
            self.app.musiclink_address("8.8.8.8")
        st = self.app.musiclink_address("127.0.0.1")
        self.assertEqual(st["address"], "127.0.0.1")
        r = self.app.musiclink_test(read=True)
        self.assertIn("CHRISTMAS", r["names"])
        clock = [b for _, _, b in self.ctl.frames(L.CMD_REQUEST) if b[0] == L.SUB_TIME]
        self.assertEqual(len(clock), 1, "Read sets the clock once, like the Trimlight app")
        self.app.musiclink_test()
        self.assertEqual(len([b for _, _, b in self.ctl.frames(L.CMD_REQUEST) if b[0] == L.SUB_TIME]), 1,
                         "Test connection only says hello")
        self.app.musiclink_address("")
        self.assertNotIn("lan", self.app.store.settings)
        with self.assertRaises(ApiError):
            self.app.save_settings({**copy.deepcopy(self.app.store.settings), "lan": {"address": "1.1.1.1"}})

    def test_show_start_feed_stop(self):
        from eaveluxos.server import ApiError
        self.app.musiclink_address("127.0.0.1")
        c = self.app.ctrl
        with self.assertRaises(ApiError):
            self.app.musiclink({"op": "start", "tab": "p1", "pattern": 0, "sensitivity": 99})
        self.assertIsNone(c.music, "a refused start starts nothing")
        st = self.app.musiclink({"op": "start", "tab": "p1", "pattern": 2, "sensitivity": 8, "minutes": 30})
        self.assertTrue(st["running"])
        subs = lambda: [b[0] for _, _, b in self.ctl.frames(L.CMD_REQUEST)][:2]
        self.assertTrue(wait_for(lambda: len(subs()) == 2))
        self.assertEqual(subs(), [L.SUB_TIME, L.SUB_MUSIC], "opens like the Trimlight app: clock, then music")
        self.assertEqual(c.music.get("by"), "lan")
        self.assertTrue(self.app.musiclink({"op": "levels", "tab": "p1", "levels": [50] * 16})["running"])
        self.assertTrue(wait_for(lambda: any(L.read_music(b)["levels"] == [50] * 16 for _, _, b in self.ctl.frames(L.CMD_LEVELS))))
        with self.assertRaises(ApiError):
            self.app.musiclink({"op": "start", "tab": "p2", "pattern": 2, "sensitivity": 8})
        self.assertFalse(self.app.musiclink({"op": "levels", "tab": "p2", "levels": [1] * 16})["running"])
        with self.assertRaises(ApiError):
            self.app.musiclink({"op": "levels", "tab": "p1", "levels": [300] * 16})
        self.app.musiclink({"op": "set", "tab": "p1", "pattern": 4})
        self.assertTrue(wait_for(lambda: any((L.read_music(b) or {}).get("pattern") == 4 for _, _, b in self.ctl.frames(L.CMD_REQUEST))))
        self.app.musiclink({"op": "stop", "tab": "p1"})
        self.assertTrue(wait_for(lambda: c.music is None), "the schedule comes back")
        self.assertFalse(self.app.musiclink_status()["running"])

    def test_stopping_the_show_in_the_app_stops_the_stream(self):
        self.app.musiclink_address("127.0.0.1")
        self.app.musiclink({"op": "start", "tab": "p1", "pattern": 0, "sensitivity": 8})
        self.app.ctrl.stop_music()
        self.assertTrue(wait_for(lambda: not self.app.lanshow.running()))
        self.assertIsNone(self.app.ctrl.music)

    def test_unreachable_controller_starts_nothing(self):
        from eaveluxos.server import ApiError
        self.app.musiclink_address("127.0.0.1")
        L.TCP_PORT = 1
        with self.assertRaises(ApiError) as cm:
            self.app.musiclink({"op": "start", "tab": "p1", "pattern": 0, "sensitivity": 8})
        self.assertEqual(cm.exception.code, 502)
        self.assertIsNone(self.app.ctrl.music)

    def test_roles(self):
        from eaveluxos import server
        self.assertIn("/api/musiclink", server.EDITOR_POSTS)
        for admin_only in ("/api/musiclink/address", "/api/musiclink/test", "/api/musiclink/find"):
            self.assertNotIn(admin_only, server.EDITOR_POSTS)
            self.assertNotIn(admin_only, server.VIEWER_POSTS)
        self.assertIn("lan", server.HOUSEHOLD_KEYS)
        self.assertIn("lan", server.PRIVATE_KEYS)


class Bands(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node.js isn't installed")
    def test_bands(self):
        js = r"""
const B = require(process.argv[1]);
const e = B.edges(48000, 2048), out = {edges: e};
const db = new Float32Array(1024).fill(-120);
out.silent = B.levels(db, e, 0);
const loud = new Float32Array(1024).fill(-20);
out.loud = B.levels(loud, e, 0);
const bass = new Float32Array(1024).fill(-120); bass[3] = -40;
out.bass = B.levels(bass, e, 0);
out.boost = B.levels(bass, e, 12);
console.log(JSON.stringify(out));"""
        r = subprocess.run(["node", "-e", js, str(ROOT / "eaveluxos" / "static" / "bands.js")],
                           capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        o = json.loads(r.stdout)
        self.assertEqual(len(o["edges"]), 16)
        self.assertTrue(all(b > a for a, b in o["edges"]), "every band has a bin")
        self.assertTrue(all(o["edges"][i][1] <= o["edges"][i + 1][0] + 1 for i in range(15)), "in order")
        self.assertEqual(o["silent"], [0] * 16)
        self.assertEqual(o["loud"], [255] * 16)
        self.assertGreater(max(o["bass"][:3]), 100)
        self.assertEqual(o["bass"][5:], [0] * 11, "only the low bands")
        self.assertGreater(max(o["boost"]), max(o["bass"]))

    def test_page(self):
        js = (ROOT / "eaveluxos" / "static" / "app.js").read_text(encoding="utf-8")
        html = (ROOT / "eaveluxos" / "static" / "index.html").read_text(encoding="utf-8")
        self.assertLess(html.index("bands.js"), html.index("app.js"))
        for s in ("linkPanel($('#linkbox'))", "api('musiclink', { body: { op: 'levels'", "if (LINK.busy) return;",
                  "getDisplayMedia", "op: 'stop', tab: LINK.tab }, keepalive: true"):
            self.assertIn(s, js)


class CaptureTool(unittest.TestCase):
    def test_decodes_trimlight_messages(self):
        """A small capture made of the real frames: the report says what they are."""
        phone, ctl = (10, 215, 173, 1), (10, 168, 168, 35)

        def pkt(src, dst, sp, dp, seq, data):
            tcp = struct.pack("!HHIIBBHHH", sp, dp, seq, 0, 5 << 4, 0x18, 65535, 0, 0) + data
            ip = struct.pack("!BBHHHBBH4s4s", 0x45, 0, 20 + len(tcp), 0, 0, 64, 6, 0, bytes(src), bytes(dst)) + tcp
            return ip
        frames = [(phone, ctl, 45244, 8586, b"S\x01\x00\x00\x04\x04+D56"),
                  (ctl, phone, 8586, 45244, b"S\x01\x00\x00\x03\x03tok"),
                  (phone, ctl, 45244, 8586, bytes.fromhex(REAL["time"])),
                  (phone, ctl, 45244, 8586, bytes.fromhex(REAL["ping"])),
                  (ctl, phone, 8586, 45244, bytes.fromhex(REAL["ack"])),
                  (phone, ctl, 45244, 8586, bytes.fromhex(REAL["music"]))] + \
                 [(phone, ctl, 45244, 8586, bytes.fromhex(REAL["levels"]))] * 5 + \
                 [(phone, ctl, 45244, 8586, bytes.fromhex(REAL[k])) for k in ("leave", "off", "on")]
        seqs = {}
        body = b""
        t0 = 1_763_229_015
        for i, (s, d, sp, dp, data) in enumerate(frames):
            seq = seqs.get(s, 1000)
            seqs[s] = seq + len(data)
            raw = pkt(s, d, sp, dp, seq, data)
            body += struct.pack("<IIII", t0 + i, 0, len(raw), len(raw)) + raw
            if i == 3:     # a retransmission: same bytes again, must not be decoded twice
                body += struct.pack("<IIII", t0 + i, 500, len(raw), len(raw)) + raw
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d, True)
        cap = d / "c.pcap"
        cap.write_bytes(struct.pack("<IHHiIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, 101) + body)
        # Not -I: that would ignore PYTHONIOENCODING, which stands in for a Windows console here.
        r = subprocess.run([sys.executable, "-s", str(ROOT / "tools" / "music-capture" / "summarize_capture.py"),
                            str(cap), "--controller", "10.168.168.35"], capture_output=True, text=True,
                           encoding="utf-8", timeout=60,
                           env={**os.environ, "PYTHONIOENCODING": "cp1252"})   # as on a Windows console
        self.assertEqual(r.returncode, 0, r.stderr)
        out = r.stdout
        self.assertIn("### Decoded Trimlight messages", out)
        self.assertIn("↔", out, "printed as UTF-8 even where the console isn't (Windows, 4.1.0)")
        self.assertIn("set the controller's clock | 2026-11-15 12:50:15 (Sun)", out)
        self.assertIn("music settings | input: the controller's own input (Auxiliary IN); music pattern 1; sensitivity 8", out)
        self.assertIn("sound levels (and 4 more", out)
        self.assertEqual(out.count("| keep-alive |"), 1, "the retransmitted keep-alive is shown once")
        self.assertIn("keep-alive answer", out)
        for words in ("back to normal (out of music mode)", "| lights off |", "| lights on |"):
            self.assertIn(words, out)


if __name__ == "__main__":
    unittest.main()


try:
    from playwright.sync_api import sync_playwright
except ImportError:          # pragma: no cover
    sync_playwright = None


@unittest.skipIf(sync_playwright is None, "Playwright isn't installed")
class Browser(unittest.TestCase):
    """The whole way: a browser's (fake) microphone, the Music page, the app,
    and the pretend controller getting sound levels."""

    def test_music_from_this_computer(self):
        import threading
        import eaveluxos.api
        from eaveluxos.server import App, make_server
        from tests import fake_trimlight as F
        cloud = F.start()
        saved = eaveluxos.api.BASE_URL
        eaveluxos.api.BASE_URL = f"http://127.0.0.1:{cloud.server_address[1]}/trimlight"
        self.addCleanup(setattr, eaveluxos.api, "BASE_URL", saved)
        os.environ["EAVELUXOS_LAN_TEST"] = "1"
        self.addCleanup(os.environ.pop, "EAVELUXOS_LAN_TEST", None)
        ctl = fake_lan.FakeController()
        self.addCleanup(ctl.close)
        port = L.TCP_PORT
        L.TCP_PORT = ctl.port
        self.addCleanup(setattr, L, "TCP_PORT", port)
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d, True)
        app = App(d, start=False)
        self.addCleanup(app.store.close)
        s = copy.deepcopy(app.store.settings)
        s["location"].update(latitude=39.95, longitude=-75.16)
        s["setup_done"] = True
        s["lan"] = {"address": "127.0.0.1"}
        app.store.save_settings(s)
        app.store.save_secrets(client_id=F.CID, client_secret=F.SECRET)
        app.rebuild()
        self.addCleanup(app.lanshow.stop)
        srv = make_server(app, "127.0.0.1", 0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        base = f"http://localhost:{srv.server_address[1]}/"
        try:
            pw = sync_playwright().start()
            br = pw.chromium.launch(args=["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"])
        except Exception as e:
            self.skipTest(f"Chromium can't start: {e}")
        self.addCleanup(pw.stop)
        self.addCleanup(br.close)
        errors = []
        for size in ({"width": 1300, "height": 900}, {"width": 390, "height": 844}):
            ctx = br.new_context(viewport=size)
            self.addCleanup(ctx.close)
            pg = ctx.new_page()
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.goto(base + "#music")
            pg.wait_for_selector("#linkbox [data-lkgo]")
            self.assertEqual(pg.input_value("#lkaddr"), "127.0.0.1")
            if size["width"] == 390:
                self.assertEqual(pg.evaluate("document.documentElement.scrollWidth"), 390, "fits a phone")
                continue
            pg.click("#linkbox [data-lktest]")
            pg.wait_for_selector("#lkout .callout")
            self.assertIn("The controller answered", pg.inner_text("#lkout"))
            pg.click("#linkbox [data-lkgo]")
            pg.wait_for_selector("#linkbars")
            ok = wait_for(lambda: any(any(L.read_music(b)["levels"]) for _, _, b in ctl.frames(L.CMD_LEVELS)), 8)
            self.assertTrue(ok, "the controller got sound levels from the browser")
            self.assertEqual(app.ctrl.music.get("by"), "lan")
            self.assertTrue(pg.is_disabled("[data-moodgo]") or not pg.query_selector("[data-moodgo]"))
            pg.click("#linkbox [data-lkstop]")
            self.assertTrue(wait_for(lambda: app.ctrl.music is None, 5), "Stop hands the lights back")
        self.assertEqual(errors, [])
        self.assertEqual(ctl.errors, [])
