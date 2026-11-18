# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""4.6: patterns of this app's own colors and built-in effects shown live
over the home network, as the Trimlight app does while editing. The bytes
here are the ones the Trimlight app sent on Nov 17, 2026 (7:24-7:26 PM)."""
import unittest

from eaveluxos import lanlink as L
from eaveluxos import localmode
from tests.test_local43 import ServerBase

DEV = "TL-EDGE-01"


class Messages(unittest.TestCase):
    def test_own_colors_as_the_trimlight_app_sent_them(self):
        # 7:25:54: five white, five red, repeated; mode 1, speed 0x81, brightness 0xbc
        px = [{"index": i, "count": 5, "color": 0xFFFFFF if i % 2 == 0 else 0xFF0000, "disable": False} for i in range(30)]
        sub, data = L.preview_message({"category": 1, "mode": 1, "speed": 0x81, "brightness": 0xBC, "pixels": px})
        self.assertEqual(sub, 0x0D)
        self.assertEqual(len(data), 0x99)
        self.assertEqual(data[:13].hex(" "), "01 81 bc 05 ff ff ff 01 05 ff 00 00 01")
        # 7:26:49: red 5, then an empty slot with a color in it
        sub, data = L.preview_message({"category": 1, "mode": 0, "speed": 0x80, "brightness": 0xFF, "pixels": [
            {"index": 0, "count": 5, "color": 0xFF0000}, {"index": 1, "count": 0, "color": 0x36D7D7}]})
        self.assertEqual(data[:13].hex(" "), "00 80 ff 05 ff 00 00 01 00 36 d7 d7 01")
        self.assertEqual(data[13:], bytes([0, 0, 0, 0, 1]) * 28)

    def test_built_in_effect_as_the_trimlight_app_sent_it(self):
        # 7:24:08: effect 45, speed 0x7d, brightness 255; 7:24:32 with reverse
        self.assertEqual(L.preview_message({"category": 0, "mode": 45, "speed": 0x7D, "brightness": 255, "pixelLen": 30}),
                         (0x03, bytes.fromhex("00 7d ff 2d 00")))
        self.assertEqual(L.preview_message({"category": 0, "mode": 45, "speed": 0xEA, "brightness": 255,
                                            "pixelLen": 30, "reverse": True})[1], bytes.fromhex("00 ea ff 2d 01"))

    def test_what_doesnt_fit_goes_through_the_cloud(self):
        for e in ({"category": 0, "mode": 45, "speed": 1, "brightness": 1, "pixelLen": 12},       # length not seen
                  {"category": 1, "mode": 0, "speed": 1, "brightness": 1,
                   "pixels": [{"index": i, "count": 1, "color": 1} for i in range(31)]},          # 31 colors
                  {"category": 1, "mode": 0, "speed": 1, "brightness": 1, "pixels": [{"index": 0, "count": 300, "color": 1}]}):
            with self.assertRaises(ValueError):
                L.preview_message(e)


class Live(ServerBase):
    def setUp(self):
        super().setUp()
        self.app.local_commands(True)
        self.app.ctrl.devices = [{"deviceId": DEV, "name": "Trimlight"}]

    def sent(self, sub):
        return [b for _, _, b in self.ctl.frames(L.CMD_REQUEST) if b[0] == sub]

    def cloud(self):
        return [p for p, _ in self.F.STATE["log"] if p.startswith("/device/effect/")]

    def apply(self, payload, kind="custom"):
        from eaveluxos.schedule import Effect
        self.app.ctrl.known_on = True
        self.app.ctrl._apply(True, Effect("x", "X", kind, payload=payload, colors=[]))

    def test_own_colors_live(self):
        with self.assertLogs("eaveluxos.localmode", "INFO") as cm:
            self.apply({"category": 1, "mode": 1, "speed": 60, "brightness": 220,
                        "pixels": [{"index": 0, "count": 4, "color": 0xFF0000, "disable": False}]})
        self.assertEqual(len(self.sent(L.SUB_PREVIEW)), 1)
        self.assertEqual(self.cloud(), [])
        self.assertEqual(self.app.ctrl.lan_sent[DEV], {"pattern"})
        self.assertIn("showed a pattern of this app's, brightness 220", cm.output[-1])

    def test_built_in_live(self):
        self.apply({"category": 0, "mode": 45, "speed": 100, "brightness": 200, "pixelLen": 30, "reverse": False}, "builtin")
        self.assertEqual(self.sent(L.SUB_LIVE), [L.request(L.SUB_LIVE, bytes([0, 100, 200, 45, 0]))])
        self.assertEqual(self.cloud(), [])

    def test_brightness_slider_sends_it_again(self):
        """Home's slider re-sends the pattern with the new brightness, as the
        Trimlight app's slider does (7:26:03)."""
        e = {"category": 1, "mode": 0, "speed": 128, "brightness": 200,
             "pixels": [{"index": 0, "count": 4, "color": 0xFF0000, "disable": False}]}
        self.apply(e)
        self.apply({**e, "brightness": 90})
        self.assertEqual([b[5] for b in self.sent(L.SUB_PREVIEW)], [200, 90])

    def test_cloud_when_it_cant_go_this_way(self):
        self.apply({"category": 0, "mode": 45, "speed": 100, "brightness": 200, "pixelLen": 12}, "builtin")
        self.assertEqual(self.sent(L.SUB_LIVE), [])
        self.assertEqual(self.cloud(), ["/device/effect/preview"])

    def test_setting_off_means_cloud(self):
        self.app.local_commands(False)
        self.apply({"category": 1, "mode": 0, "speed": 1, "brightness": 1,
                    "pixels": [{"index": 0, "count": 4, "color": 0xFF0000}]})
        self.assertEqual(self.sent(L.SUB_PREVIEW), [])
        self.assertEqual(self.cloud(), ["/device/effect/preview"])


# What came after the saved patterns in the controller's state, Nov 17, 2026
# at 7:20 PM (timer 1 on, 7:00-7:15 PM) and Nov 16 at 4:03 PM (both off, as
# Trimlight's cloud also reported them that afternoon).
TAIL_NOV17 = bytes.fromhex("01010a00010100130013" "0f000100000200030200808b0000") + bytes(150) + bytes.fromhex(
    "0101ff00003c030000001a0b1113140f02")
TAIL_NOV16 = bytes.fromhex("01010a00000100000100" "02000100000200030200 7fff0000".replace(" ", "")) + bytes(150)


class Timers(unittest.TestCase):
    def test_read_as_seen(self):
        t = L.read_daily(TAIL_NOV17)
        self.assertEqual(t[0], {"id": 0, "enable": True, "effectId": 1, "repetition": 0, "start": "19:00", "end": "19:15"})
        self.assertEqual(t[1], {"id": 1, "enable": False, "effectId": 1, "repetition": 0, "start": "00:02", "end": "00:03"})
        t = L.read_daily(TAIL_NOV16)
        self.assertEqual([(x["enable"], x["start"], x["end"]) for x in t], [(False, "00:01", "00:02"), (False, "00:02", "00:03")])

    def test_nothing_guessed(self):
        self.assertIsNone(L.read_daily(bytes(37)))
        self.assertIsNone(L.read_daily(TAIL_NOV17[:10]))
        bad = bytearray(TAIL_NOV17); bad[4] = 7                  # on/off that isn't 0 or 1
        self.assertIsNone(L.read_daily(bytes(bad)))
        bad = bytearray(TAIL_NOV17); bad[18] = 9                 # not followed by the pattern showing now
        self.assertIsNone(L.read_daily(bytes(bad)))


class TimersShown(ServerBase):
    def test_local_mode_lists_them_with_pattern_names(self):
        self.ctl.holds["tail"] = TAIL_NOV17
        st = self.app.local_state(fresh=True)
        self.assertEqual(st["daily"][0]["start"], "19:00")
        self.assertTrue(st["daily"][0]["enable"])
        names = {p["id"]: p["name"] for p in st["patterns"]}
        self.assertEqual(st["daily"][0]["pattern"], names.get(1))
        self.assertEqual(st["daily"][0]["repeat"], "today only")

    def test_none_when_not_readable(self):
        self.assertIsNone(self.app.local_state(fresh=True)["daily"])


class Reconnect(unittest.TestCase):
    def test_the_wait_is_twelve_seconds(self):
        src = (localmode.__file__)
        self.assertIn("RECONNECT_WAIT = 12", open(src, encoding="utf-8").read())


if __name__ == "__main__":
    unittest.main()
