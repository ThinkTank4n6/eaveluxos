# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""4.13: Music sync 2.0.

- What the music is doing (static/beat.js): bass, mids and treble with an
  automatic level, beats, and the tempo.
- Zones that follow the music (static/musiczones.js), shown live on the
  controller (musicsync.py), only after a speed test, at a careful pace that
  slows down when the controller lags and stops when it stops answering.
- Sound delay and a music file played in the page (in the browser)."""
import copy
import json
import subprocess
import threading
import time
import unittest
from pathlib import Path

from eaveluxos import lanlink as L
from eaveluxos import musicsync as M
from eaveluxos.server import ApiError, App
from tests import fake_lan
from tests.test_local43 import WithController
from tests.test_multi45 import DECK, FRONT, TwoBase

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "eaveluxos" / "static"

try:
    from playwright.sync_api import sync_playwright
except ImportError:            # pragma: no cover
    sync_playwright = None


def node(js: str):
    try:
        out = subprocess.run(["node", "-e", js], capture_output=True, text=True, encoding="utf-8", timeout=60)
    except FileNotFoundError:
        raise unittest.SkipTest("Node isn't installed")
    if out.returncode:
        raise AssertionError(out.stderr)
    return json.loads(out.stdout)


SIM = """
const B = require(%s);
function sim(bpm, opt = {}) {
  const fps = opt.fps || 47, secs = opt.secs || 12, S = B.create(48000, 2048); let beats = 0, last, seed = 7;
  const rnd = () => (seed = (seed * 16807) %% 2147483647) / 2147483647, period = 60 / bpm, outs = [];
  for (let f = 0; f < secs * fps; f++) {
    const t = f / fps, ph = (t %% period) / period, kick = bpm ? Math.exp(-ph * period / 0.08) : 0, db = new Float32Array(1024);
    for (let i = 0; i < 1024; i++) {
      const hz = i * 48000 / 2048; let v = -70 + rnd() * 6;
      if (hz < 250) v = -50 + 40 * kick + rnd() * 3; else if (hz < 4000) v = (opt.mid ?? -45) + rnd() * 4; else if (opt.treble) v = opt.treble + rnd() * 3;
      db[i] = v;
    }
    last = B.step(S, db, t); if (last.beat) beats++; outs.push(last);
  }
  return { beats, bpm: last.bpm, conf: last.conf, mid: last.mid, treble: last.treble, maxBass: Math.max(...outs.map(o => o.bass)) };
}
""" % json.dumps(str(STATIC / "beat.js"))


class Analysis(unittest.TestCase):
    def test_tempo_and_beats(self):
        got = node(SIM + "console.log(JSON.stringify([90, 120, 128, 150, 174].map(b => [b, sim(b)])));")
        for bpm, r in got:
            with self.subTest(bpm=bpm):
                self.assertAlmostEqual(r["bpm"], bpm, delta=2.5)
                expected = 12 * bpm / 60
                self.assertGreaterEqual(r["beats"], expected - 2, "about one beat per kick")
                self.assertLessEqual(r["beats"], expected + 1)

    def test_a_slower_frame_rate_still_finds_it(self):
        got = node(SIM + "console.log(JSON.stringify(sim(128, {fps: 30, secs: 14})));")
        self.assertAlmostEqual(got["bpm"], 128, delta=3)

    def test_bands_and_silence(self):
        got = node(SIM + "console.log(JSON.stringify({kicks: sim(120), quiet: sim(0, {mid: -90}), bright: sim(0, {treble: -20})}));")
        self.assertGreater(got["kicks"]["maxBass"], 0.6, "the kicks fill the bass")
        self.assertEqual(got["quiet"]["beats"], 0, "no beats in a steady hum")
        self.assertIsNone(got["quiet"]["bpm"])
        self.assertGreater(got["bright"]["treble"], 0.4)


class Zones(unittest.TestCase):
    def run_js(self, body):
        return node("const Z = require(%s); console.log(JSON.stringify((() => { %s })()));" % (json.dumps(str(STATIC / "musiczones.js")), body))

    def test_glow_meter_and_the_other_way(self):
        got = self.run_js("""
            const zones = [{name: 'Porch', start: 1, end: 10}, {name: 'Roof', start: 21, end: 40, reverse: true}];
            const maps = [{zone: 0, follows: 'bass', shows: 'glow', color: '#FF8000'}, {zone: 1, follows: 'treble', shows: 'meter', color: '#0000FF'}];
            const f = m => Z.frame({zones, maps, total: 50, music: m});
            return {half: f({bass: 0.5, treble: 0.3}), same: f({bass: 0.52, treble: 0.31}).key === f({bass: 0.5, treble: 0.3}).key,
                    full: f({bass: 1, treble: 1}), none: f({bass: 0, treble: 0})};""")
        h = got["half"]
        self.assertEqual([list(x) for x in zip(h["colors"], h["counts"])],
                         [["#804000", 10], ["#000000", 24], ["#0000FF", 6], ["#000000", 10]], "meters fill from the far end when reversed")
        self.assertTrue(got["same"], "a tiny change isn't a new frame")
        self.assertEqual([list(x) for x in zip(got["full"]["colors"], got["full"]["counts"])],
                         [["#FF8000", 10], ["#000000", 10], ["#0000FF", 20], ["#000000", 10]])
        self.assertEqual(got["none"]["colors"], ["#000000"])

    def test_the_beat_a_base_color_and_too_many_blocks(self):
        got = self.run_js("""
            const zones = Array.from({length: 16}, (_, i) => ({name: 'z' + i, start: i * 6 + 1, end: i * 6 + 5}));
            const maps = zones.map((z, i) => ({zone: i, follows: 'beat', shows: 'meter', color: '#FFFFFF'}));
            let err = null; try { Z.frame({zones, maps, total: 100, music: {pulse: 0.5}}); } catch (e) { err = e.message; }
            const one = Z.frame({zones: [zones[0]], maps: [{...maps[0], shows: 'glow'}], base: '#101010', total: 20, music: {pulse: 1}});
            return {err, worst: Z.worst({zones, maps, total: 100}), one: [one.colors, one.counts]};""")
        self.assertIn("color blocks", got["err"])
        self.assertGreater(got["worst"], 30)
        self.assertEqual(got["one"], [["#FFFFFF", "#101010"], [5, 15]])


class Frames(unittest.TestCase):
    def test_preview_data(self):
        sub, data = M.preview_data(["#FF0000", "#000000"], [10, 90])
        self.assertEqual(sub, L.SUB_PREVIEW)
        self.assertEqual(len(data), 153)
        self.assertEqual(data[:3], bytes([0, 0, 255]), "still, full brightness")
        self.assertEqual(data[3:8], bytes([10, 255, 0, 0, 1]))
        for bad in ((["#FF0000"], [0]), (["red"], [3]), (["#FF0000"] * 31, [1] * 31), ([], []), (["#FF0000"], [256]), (["#GG0000"], [1])):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                M.preview_data(*bad)


class Stream(WithController):
    def setUp(self):
        super().setUp()
        for k, v in {"PING_EVERY": 0.2, "LOST_AFTER": 1.0, "RISE_AFTER": 0.6, "SLOW_MS": 300, "OK_MS": 150}.items():
            self.addCleanup(setattr, M, k, getattr(M, k))
            setattr(M, k, v)

    def previews(self):
        return [b for _, _, b in self.ctl.frames(L.CMD_REQUEST) if b[:1] == bytes([L.SUB_PREVIEW])]

    def test_speed_test_finds_the_pace_it_keeps_up_with(self):
        self.ctl.max_fps = 4
        r = M.speed_test("127.0.0.1", rates=(2, 4, 6, 8), seconds=1.2)
        self.assertEqual(r["fps"], 4, r)
        self.assertEqual([x["fps"] for x in r["rates"]], [2, 4, 6], "stops at the first that lags")
        self.assertFalse(r["rates"][-1]["ok"])
        self.assertTrue(self.previews(), "frames went out")

    def test_only_the_latest_frame_at_most_the_pace(self):
        ended = []
        z = M.ZoneStreamer(on_end=lambda why, sid: ended.append(why))
        z.start("127.0.0.1", "tab", 4, "s1")
        self.addCleanup(z.stop)
        t0 = time.monotonic()
        while time.monotonic() - t0 < 1.5:
            z.feed(["#FF0000", "#000000"], [5, int((time.monotonic() - t0) * 40) % 90 + 1], "tab")     # a new frame every time
            time.sleep(0.01)
        n = len(self.previews())
        self.assertLessEqual(n, 8, "4 a second, never every frame fed")
        self.assertGreaterEqual(n, 4)
        same = len(self.previews())
        for _ in range(20):
            z.feed(["#00FF00"], [50], "tab")
            time.sleep(0.02)
        self.assertEqual(len(self.previews()) - same, 1, "the same frame is sent once")
        self.assertFalse(z.feed(["#00FF00"], [50], "other page"))
        z.stop("tab")
        self.assertEqual(ended, ["stopped"])

    def test_slows_down_when_the_controller_lags(self):
        self.ctl.max_fps = 3
        z = M.ZoneStreamer()
        z.start("127.0.0.1", "tab", 8, "s1")
        self.addCleanup(z.stop)
        self.assertEqual(z.status()["fps"], 4, "starts at 4 even when the test allowed more")
        # 4.16.1: until it has slowed down (at most 12 s): GitHub's Mac sent only
        # 13 frames in 4 s on a busy day, too few to see two late answers in a row
        t0, k = time.monotonic(), 0
        while time.monotonic() - t0 < 12:
            k += 1
            z.feed(["#FF0000"], [1 + k % 200], "tab")
            time.sleep(0.02)
            if time.monotonic() - t0 > 4 and z.status()["slowed"] >= 1 and z.status()["fps"] <= 3:
                break
        st = z.status()
        self.assertLessEqual(st["fps"], 3, st)
        self.assertGreaterEqual(st["slowed"], 1)

    def test_stops_when_the_controller_stops_answering(self):
        ended = []
        self.ctl.answer_pings = 3                      # the open's keep-alive, then two, then nothing
        z = M.ZoneStreamer(on_end=lambda why, sid: ended.append((why, sid)))
        z.start("127.0.0.1", "tab", 4, "s9")
        for _ in range(150):
            if not z.running():
                break
            z.feed(["#FF0000"], [3], "tab")
            time.sleep(0.03)
        self.assertFalse(z.running())
        self.assertEqual(ended[0][0], "lost")
        self.assertEqual(ended[0][1], "s9")
        self.assertRegex(z.status()["error"], "(stopped answering|didn't answer)")


class Review(unittest.TestCase):
    """Fixes from the 4.13 code review."""

    def test_1_one_late_answer_doesnt_slow_the_show(self):
        from tests import reprorun
        reprorun.run(self, "repro_zone_hiccup.py", 120)


class ReviewStream(WithController):
    def test_2_a_speed_test_isnt_failed_by_one_late_answer(self):
        self.ctl.slow_pings = 2          # the first is the opening keep-alive; the second lands in the 2-a-second burst
        r = M.speed_test("127.0.0.1", rates=(2, 4), seconds=1.6)
        self.assertEqual(r["fps"], 4, r)
        self.ctl.slow_pings = 99         # but a controller late every time fails
        self.assertEqual(M.speed_test("127.0.0.1", rates=(2,), seconds=1.6)["fps"], 0)


class App413(TwoBase):
    def setUp(self):
        super().setUp()
        self.app.local_address(DECK, "127.0.0.1")
        self.app.local_address(FRONT, "127.0.0.2")
        self.addCleanup(setattr, M, "TEST_SECONDS", M.TEST_SECONDS)
        self.addCleanup(setattr, M, "RATES", M.RATES)
        M.TEST_SECONDS, M.RATES = 0.6, (2, 4)
        self.app.ctrl.devices = [{"deviceId": DECK, "name": "Deck"}, {"deviceId": FRONT, "name": "Front"}]
        s = copy.deepcopy(self.app.store.settings)
        s["map"] = {"zones": [{"name": "Rail", "start": 1, "end": 40, "device": DECK}]}
        s["music_zones"] = {"maps": [{"zone": "Rail", "device": DECK, "follows": "bass", "shows": "meter", "color": "#FF6600"}]}
        self.app.save_settings(s)

    def test_a_show_needs_its_speed_test_and_ends_with_the_schedule_back(self):
        with self.assertRaises(ApiError) as e:
            self.app.musiczones({"op": "start", "tab": "t1", "devices": [DECK]})
        self.assertIn("speed test", str(e.exception))
        r = self.app.musiczones({"op": "test", "device": DECK})
        self.assertEqual(r["fps"], 4)
        self.assertEqual(self.app.store.settings["music_zones"]["tested"][DECK]["fps"], 4)
        self.assertIsNone(self.app.ctrl.music, "the schedule is back after the test")
        st = self.app.musiczones({"op": "start", "tab": "t1", "devices": [DECK]})
        self.assertTrue(st["running"])
        self.assertTrue(self.app.ctrl.music, "the app steps aside, as in any music show")
        with self.assertRaises(ApiError):
            self.app.musiclink({"op": "start", "tab": "t2", "pattern": 0, "sensitivity": 8})
        n = len([b for _, _, b in self.ctl.frames(L.CMD_REQUEST) if b[:1] == bytes([L.SUB_PREVIEW])])
        r = self.app.musiczones({"op": "frame", "tab": "t1", "frames": {DECK: {"colors": ["#FF6600", "#000000"], "counts": [20, 90]}}})
        self.assertTrue(r["running"])
        for _ in range(60):
            if len([b for _, _, b in self.ctl.frames(L.CMD_REQUEST) if b[:1] == bytes([L.SUB_PREVIEW])]) > n:
                break
            time.sleep(0.05)
        last = [b for _, _, b in self.ctl.frames(L.CMD_REQUEST) if b[:1] == bytes([L.SUB_PREVIEW])][-1]
        self.assertEqual(last[3 + 3:3 + 8], bytes([20, 255, 102, 0, 1]), "the frame as sent")
        with self.assertRaises(ApiError):
            self.app.musiczones({"op": "frame", "tab": "t1", "frames": {DECK: {"colors": ["#FF6600"], "counts": [300]}}})
        self.app.musiczones({"op": "stop", "tab": "t1"})
        self.assertFalse(self.app.musiczones_status()["running"])
        self.assertIsNone(self.app.ctrl.music)

    def test_3_stop_names_its_page(self):
        with self.assertRaises(ApiError):
            self.app.musiczones({"op": "stop"})

    def test_test_results_only_come_from_the_test(self):
        s = copy.deepcopy(self.app.store.settings)
        s["music_zones"]["tested"] = {DECK: {"fps": 8}}
        self.app.save_settings(s)
        self.assertNotIn(DECK, self.app.store.settings["music_zones"].get("tested", {}))

    def test_checked(self):
        for mz in ({"maps": [{"zone": "Rail", "follows": "loud", "shows": "glow", "color": "#FF0000"}]},
                   {"maps": [{"zone": "Rail", "follows": "bass", "shows": "glow", "color": "red"}]},
                   {"maps": [], "base": "black"}, {"maps": [], "extra": 1}):
            with self.subTest(mz=mz), self.assertRaises(ApiError):
                App._validate_music_zones(mz)


@unittest.skipIf(sync_playwright is None, "Playwright isn't installed")
class Browser(TwoBase):
    SHOTS = None

    def test_zones_follow_a_fake_microphone(self):
        from eaveluxos.server import make_server
        self.app.local_address(DECK, "127.0.0.1")
        self.app.ctrl.devices = [{"deviceId": DECK, "name": "Deck"}, {"deviceId": FRONT, "name": "Front"}]
        self.addCleanup(setattr, M, "TEST_SECONDS", M.TEST_SECONDS)
        self.addCleanup(setattr, M, "RATES", M.RATES)
        M.TEST_SECONDS, M.RATES = 0.5, (2, 4)
        s = copy.deepcopy(self.app.store.settings)
        s["map"] = {"zones": [{"name": "Rail", "start": 1, "end": 40}, {"name": "Steps", "start": 41, "end": 60}]}
        self.app.save_settings(s)
        srv = make_server(self.app, "127.0.0.1", 0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        base = f"http://localhost:{srv.server_address[1]}/"
        try:
            pw = sync_playwright().start()
            br = pw.chromium.launch(args=["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
                                          "--autoplay-policy=no-user-gesture-required"])
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
        mz = lambda: self.app.store.settings.get("music_zones") or {}
        pg = br.new_page(viewport={"width": 1300, "height": 1100})
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(base + "#music")
        pg.wait_for_selector('[data-lkeng="zones"]')
        pg.click('[data-lkeng="zones"]')
        pg.wait_for_selector(f'[data-lkzdev="{DECK}"]')
        pg.check(f'[data-lkzdev="{DECK}"]')
        pg.wait_for_selector('select[data-f="follows"]')
        sel = pg.locator('select[data-f="follows"]')
        sel.nth(0).select_option("bass")
        pg.locator('select[data-f="shows"]').nth(0).select_option("meter")
        sel.nth(1).select_option("beat")
        until(lambda: len(mz().get("maps", [])) == 2, "the choices saved")
        self.assertEqual({(m["zone"], m["follows"], m["shows"]) for m in mz()["maps"]}, {("Rail", "bass", "meter"), ("Steps", "beat", "glow")})
        self.assertTrue(pg.locator("[data-lkgo]").is_disabled(), "not before the speed test")
        pg.click(f'[data-lkztest="{DECK}"]')
        pg.click("#dlg .primary")
        until(lambda: (mz().get("tested", {}).get(DECK) or {}).get("fps") == 4, "the speed test", n=300)
        pg.wait_for_selector("[data-lkgo]:not([disabled])")
        if self.SHOTS:
            pg.locator("#linkbox").screenshot(path=f"{self.SHOTS}/zones.png")
        n0 = len(self.ctl.frames(L.CMD_REQUEST))
        pg.click("[data-lkgo]")
        pg.wait_for_selector("#lkmeters")
        until(lambda: self.app.musiczones_status()["devices"][DECK]["show"].get("frames", 0) >= 3, "frames reach the controller", n=300)
        self.assertGreater(len(self.ctl.frames(L.CMD_REQUEST)), n0)
        until(lambda: "BPM" in pg.inner_text("#lkmeters") or "tempo" in pg.inner_text("#lkmeters"), "the tempo line")
        until(lambda: pg.evaluate("!!(LINK.music && LINK.music.pulse > 0.2)"), "beats from the fake microphone's beeps")
        if self.SHOTS:
            pg.wait_for_timeout(1500)
            pg.locator("#linkbox").screenshot(path=f"{self.SHOTS}/running.png")
        pg.click("[data-lkstop]")
        until(lambda: not self.app.musiczones_status()["running"], "stopped")
        self.assertIsNone(self.app.ctrl.music)
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
