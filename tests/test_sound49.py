# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""4.9: a celebration sound. A clip of a sound file you have plays through
the app computer's speakers when a team scores. The files here are made up
by the test (silent MP3 frames, a WAV tone), never a real recording."""
import copy
import io
import math
import os
import struct
import tempfile
import unittest
import wave
from pathlib import Path

from eaveluxos import sound as S
from eaveluxos.schedule import ConfigError, build_config
from eaveluxos.store import DEFAULT_SETTINGS

FRAME = b"\xff\xfb\x90\x00"            # MPEG-1 Layer III, 128 kbit/s, 44.1 kHz: 417 bytes, 1152 samples
FRAME_LEN, FRAME_S = 417, 1152 / 44100


def mp3(seconds: float, id3=True, xing=True, v1tag=True) -> bytes:
    n = int(seconds / FRAME_S)
    frames = [FRAME + bytes(FRAME_LEN - 4)] * n
    if xing:
        frames.insert(0, FRAME + b"\x00" * 32 + b"Xing" + bytes(FRAME_LEN - 40))
    head = b""
    if id3:
        body = b"TIT2" + bytes(200)
        size = len(body)
        head = b"ID3\x03\x00\x00" + bytes([(size >> 21) & 127, (size >> 14) & 127, (size >> 7) & 127, size & 127]) + body
    return head + b"".join(frames) + (b"TAG" + bytes(125) if v1tag else b"")


def wav(seconds: float, rate=8000) -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(i / 10))) for i in range(int(seconds * rate))))
    return out.getvalue()


class Files(unittest.TestCase):
    def test_mp3_is_known_and_measured(self):
        data = mp3(60)
        self.assertEqual(S.kind_of(data), "mp3")
        self.assertAlmostEqual(S.length_of(data, "mp3"), 60, delta=0.1)

    def test_mp3_cut_between_frames(self):
        data = mp3(60)
        clip = S.cut(data, "mp3", 10, 20)
        self.assertEqual(len(clip) % FRAME_LEN, 0, "whole frames only")
        self.assertTrue(clip.startswith(FRAME))
        self.assertAlmostEqual(S.length_of(clip, "mp3"), 20, delta=0.1)
        self.assertNotIn(b"Xing", clip)
        self.assertNotIn(b"ID3", clip[:3])

    def test_wav_cut_between_samples(self):
        data = wav(40)
        self.assertEqual(S.kind_of(data), "wav")
        clip = S.cut(data, "wav", 5, 20)
        with wave.open(io.BytesIO(clip)) as w:
            self.assertEqual((w.getnframes(), w.getframerate()), (20 * 8000, 8000))

    def test_a_short_file_plays_what_there_is(self):
        self.assertAlmostEqual(S.length_of(S.cut(mp3(8), "mp3", 0, 20), "mp3"), 8, delta=0.1)

    def test_refused(self):
        with self.assertRaises(S.SoundError):
            S.check_upload(b"not a sound at all" * 100)
        with self.assertRaises(S.SoundError):
            S.check_upload(b"")
        with self.assertRaises(S.SoundError):
            S.check_upload(b"\0" * (S.UPLOAD_MAX + 1))
        with self.assertRaises(S.SoundError):
            S.cut(mp3(10), "mp3", 0, 31)
        with self.assertRaises(S.SoundError):
            S.cut(mp3(10), "mp3", 20, 5)
        with self.assertRaises(S.SoundError):
            S.cut(wav(2), "wav", 5, 5)
        self.assertEqual(S.check_upload(mp3(30))[0], "mp3")

    def test_stray_header_bytes_arent_sound(self):
        junk = bytes(1000) + FRAME + bytes(50) + mp3(5, id3=False, xing=False, v1tag=False)
        self.assertAlmostEqual(S.length_of(junk, "mp3"), 5, delta=0.1)


class Review(unittest.TestCase):
    """The code review of 4.9, before release."""
    def test_1_a_second_goal_while_the_first_plays(self):
        import subprocess
        import sys
        root = Path(__file__).resolve().parent.parent
        r = subprocess.run([sys.executable, str(root / "tests" / "repro_sound_locked.py")], capture_output=True,
                           text=True, encoding="utf-8", timeout=60, cwd=root)
        self.assertIn("OK:", r.stdout, r.stdout + r.stderr)

    def test_2_large_cover_art(self):
        art = b"APIC" + bytes(600_000)
        size = len(art)
        tag = b"ID3\x03\x00\x00" + bytes([(size >> 21) & 127, (size >> 14) & 127, (size >> 7) & 127, size & 127]) + art
        data = tag + mp3(20, id3=False)
        self.assertEqual(S.check_upload(data)[0], "mp3")


class Players(unittest.TestCase):
    def test_mac_uses_afplay(self):
        ran = []
        p = S.Player("Darwin", which=lambda x: "/usr/bin/afplay" if x == "afplay" else None,
                     popen=lambda cmd, **k: ran.append(cmd) or type("P", (), {"poll": lambda s: 0})())
        self.assertTrue(p.supported())
        self.assertTrue(p.play(Path("/x/clip.mp3"), "mp3", 0.1))
        self.assertEqual(ran, [["afplay", "/x/clip.mp3"]])

    def test_linux_picks_a_player_for_the_kind(self):
        have = {"mpg123", "aplay"}
        p = S.Player("Linux", which=lambda x: x if x in have else None)
        self.assertEqual(p._linux_cmd(Path("c.mp3"), "mp3")[0], "mpg123")
        self.assertEqual(p._linux_cmd(Path("c.wav"), "wav")[0], "aplay")
        self.assertFalse(S.Player("Linux", which=lambda x: None).supported())

    def test_windows_opens_plays_and_closes(self):
        import time
        sent = []
        p = S.Player("Windows", mci=lambda cmd: sent.append(cmd) or 0)
        p.play(Path(r"C:\Data\sounds\nhl-phi-clip.mp3"), "mp3", 0.2)
        for _ in range(60):
            if any(c.startswith("close") for c in sent):
                break
            time.sleep(0.05)
        self.assertEqual(sent, [r'open "C:\Data\sounds\nhl-phi-clip.mp3" type mpegvideo alias elxsound',
                                "play elxsound", "close elxsound"])


class Settings(unittest.TestCase):
    def cfg(self, sound):
        s = copy.deepcopy(DEFAULT_SETTINGS)
        s["location"].update(latitude=39.95, longitude=-75.17)
        s["effects"]["fly"] = {"label": "Flyers", "colors": ["#F74902", "#000000"], "counts": [4, 4]}
        s["gameday"] = {"enabled": False, "celebrate_enabled": True,
                        "teams": [{"league": "nhl", "team": "phi", "name": "Flyers", "effect": "fly", "celebrate": True,
                                   **({"sound": sound} if sound is not None else {})}]}
        return build_config(s, {"client_id": "x", "client_secret": "y"})

    def test_kept_with_the_team(self):
        c = self.cfg({"name": "horn.mp3", "kind": "mp3", "start": 0, "seconds": 20, "on": True})
        self.assertEqual(c.celebrate["nhl-phi"]["sound"]["seconds"], 20)
        self.assertFalse(self.cfg({"name": "h", "kind": "mp3", "start": 0, "seconds": 20, "on": False}).celebrate["nhl-phi"]["sound"]["on"])
        self.assertIsNone(self.cfg(None).celebrate["nhl-phi"]["sound"])

    def test_refused(self):
        for bad in ({"kind": "mp3", "start": 0, "seconds": 31}, {"kind": "ogg", "start": 0, "seconds": 5},
                    {"kind": "mp3", "start": -1, "seconds": 5}, "horn.mp3", {"kind": "mp3", "start": True, "seconds": 5}):
            with self.subTest(bad=bad), self.assertRaises(ConfigError) as e:
                self.cfg(bad)
            self.assertIn("sound", str(e.exception))


class Server(unittest.TestCase):
    """Upload, listen, play and celebrate, through the App (no controller)."""
    def setUp(self):
        from eaveluxos.server import App
        self.dir = Path(tempfile.mkdtemp())
        self.app = App(self.dir, start=False)
        played = self.played = []
        self.app.player = type("P", (), {"supported": lambda s, k="mp3": True,
                                         "play": lambda s, path, kind, secs: played.append((Path(path).read_bytes(), kind, secs)) or True})()
        s = copy.deepcopy(self.app.store.settings)
        s["effects"]["fly"] = {"label": "Flyers", "colors": ["#F74902", "#000000"], "counts": [4, 4]}
        s["gameday"] = {"enabled": False, "celebrate_enabled": True, "celebrate_only_when_on": False,
                        "teams": [{"league": "nhl", "team": "phi", "name": "Flyers", "effect": "fly", "celebrate": True}]}
        self.app.store.save_settings(s)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.dir, ignore_errors=True)

    def set_sound(self, **kw):
        s = copy.deepcopy(self.app.store.settings)
        s["gameday"]["teams"][0]["sound"] = {"name": "horn.mp3", "kind": "mp3", "start": 2, "seconds": 20, "on": True, **kw}
        self.app.store.save_settings(s)

    def test_upload_listen_play_remove(self):
        from eaveluxos.server import ApiError
        r = self.app.sound_upload("nhl-phi", mp3(45), "Goal horn.mp3")
        self.assertEqual((r["kind"], round(r["length"])), ("mp3", 45))
        self.assertTrue((self.app.store.dir / "sounds" / "nhl-phi.sound").is_file())
        self.set_sound()
        data, kind = self.app.sound_clip("nhl-phi")
        self.assertAlmostEqual(S.length_of(data, "mp3"), 20, delta=0.1)
        self.assertTrue(self.app.sound_test("nhl-phi")["played"])
        self.assertEqual(self.played[0][1:], ("mp3", 20.0))
        self.app.sound_delete("nhl-phi")
        self.assertFalse((self.app.store.dir / "sounds" / "nhl-phi.sound").exists())
        with self.assertRaises(ApiError):
            self.app.sound_clip("nhl-phi")

    def test_only_for_a_team_on_the_list_and_a_real_team_name(self):
        from eaveluxos.server import ApiError
        for team in ("nfl-dal", "../../etc", "nhl-phi/../x", ""):
            with self.subTest(team=team), self.assertRaises(ApiError):
                self.app.sound_upload(team, mp3(5), "x.mp3")
        with self.assertRaises(ApiError):
            self.app.sound_upload("nhl-phi", b"<html>not a sound</html>" * 50, "x.mp3")

    def test_celebrate_plays_it_unless_unticked(self):
        self.app.sound_upload("nhl-phi", mp3(30), "horn.mp3")
        flashes = []

        class Ctrl:
            def start_flash(self, **k):
                flashes.append(k)
                return True

            def note(self, *a, **k):
                pass
        for on, expect in ((True, 1), (False, 1)):
            self.set_sound(on=on)
            s = copy.deepcopy(self.app.store.settings)
            s["location"].update(latitude=39.95, longitude=-75.17)
            c = Ctrl()
            c.cfg = build_config(s, {"client_id": "x", "client_secret": "y"})
            self.app.ctrl = c
            self.assertTrue(self.app.celebrate({**c.cfg.celebrate["nhl-phi"], "key": "nhl-phi"}, 1, {}))
            self.assertEqual(len(self.played), expect, "Play the sound unticked: lights only")
        self.assertEqual(len(flashes), 2, "the lights celebrate either way")
        self.app.ctrl = None


if __name__ == "__main__":
    unittest.main()


try:
    from playwright.sync_api import sync_playwright
except ImportError:            # pragma: no cover
    sync_playwright = None

from tests.test_multi45 import TwoBase  # noqa: E402


@unittest.skipIf(sync_playwright is None, "Playwright isn't installed")
class Browser(TwoBase):
    SHOTS = None

    def test_choose_trim_untick_listen_remove(self):
        import threading
        import time
        from eaveluxos.server import make_server
        played = []
        self.app.player = type("P", (), {"supported": lambda s, k="mp3": True,
                                         "play": lambda s, p, k, secs: played.append(secs) or True})()
        s = copy.deepcopy(self.app.store.settings)
        s["effects"]["fly"] = {"label": "Flyers", "colors": ["#F74902", "#000000"], "counts": [4, 4]}
        s["gameday"] = {"enabled": False, "celebrate_enabled": True,
                        "teams": [{"league": "nhl", "team": "phi", "name": "Flyers", "effect": "fly", "celebrate": True}]}
        self.app.store.save_settings(s)
        self.app.rebuild()
        srv = make_server(self.app, "127.0.0.1", 0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        f = Path(tempfile.mkdtemp()) / "Goal horn.mp3"
        f.write_bytes(mp3(40))
        try:
            pw = sync_playwright().start()
            br = pw.chromium.launch(args=["--autoplay-policy=no-user-gesture-required"])
        except Exception as e:
            self.skipTest(f"Chromium can't start: {e}")
        self.addCleanup(pw.stop)
        self.addCleanup(br.close)
        errors = []

        def until(cond, what):
            for _ in range(160):
                if cond():
                    return
                time.sleep(0.05)
            self.fail(f"never: {what}")
        team = lambda: self.app.store.settings["gameday"]["teams"][0]
        for size in ({"width": 390, "height": 844}, {"width": 1300, "height": 900}):
            ctx = br.new_context(viewport=size)
            self.addCleanup(ctx.close)
            pg = ctx.new_page()
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.goto(f"http://localhost:{srv.server_address[1]}/#schedule")
            pg.wait_for_selector('[data-fold="game"]')
            if "closed" in (pg.get_attribute('[data-fold="game"]', "class") or ""):
                pg.click('[data-fold="game"] .foldbar')
            if size["width"] == 390:
                pg.wait_for_selector("[data-gdsndfile]")
                self.assertEqual(pg.evaluate("document.documentElement.scrollWidth"), 390, "fits a phone")
                pg.set_input_files("[data-gdsndfile]", str(f))
                until(lambda: (team().get("sound") or {}).get("name") == "Goal horn.mp3", "the sound saved")
                self.assertEqual((team()["sound"]["seconds"], team()["sound"]["kind"]), (20, "mp3"))
                pg.wait_for_selector("[data-gdsndsecs]")
                self.assertEqual(pg.evaluate("document.documentElement.scrollWidth"), 390, "still fits")
                if self.SHOTS:
                    pg.locator(".soundrow").screenshot(path=f"{self.SHOTS}/sound-390.png")
                continue
            pg.wait_for_selector("[data-gdsndsecs]")
            pg.fill("[data-gdsndstart]", "3")
            pg.dispatch_event("[data-gdsndstart]", "change")
            until(lambda: team()["sound"]["start"] == 3, "start saved")
            pg.wait_for_selector("[data-gdsndsecs]")
            pg.fill("[data-gdsndsecs]", "15")
            pg.dispatch_event("[data-gdsndsecs]", "change")
            until(lambda: team()["sound"]["seconds"] == 15, "length saved")
            pg.click("[data-gdsndpc]")
            until(lambda: played == [15.0], "played on the app computer")
            with pg.expect_response(lambda r: "api/sound/clip" in r.url) as got:
                pg.click("[data-gdsndhere]")
            self.assertEqual((got.value.status, got.value.headers.get("content-type")), (200, "audio/mpeg"))
            n = pg.evaluate("""fetch('api/sound/clip?team=nhl-phi', {headers: {'X-Requested-With': 'eaveluxos'}})
                               .then(r => r.arrayBuffer()).then(b => b.byteLength)""")
            self.assertEqual(n, len(S.cut(mp3(40), "mp3", 3, 15)), "the part that plays, as the app cuts it")
            pg.wait_for_selector("[data-gdsndon]")
            pg.uncheck("[data-gdsndon]")
            until(lambda: team()["sound"]["on"] is False, "unticked")
            pg.wait_for_selector("[data-gdsnddel]")
            pg.click("[data-gdsnddel]")
            until(lambda: "sound" not in team(), "removed")
        self.assertEqual(errors, [])
