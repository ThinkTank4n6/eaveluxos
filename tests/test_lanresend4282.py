# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""4.28.2 (Chris's log, Nov 27): every pattern sent over the home network was
sent again about 6 minutes 40 seconds later as "changed outside this app",
when Trimlight's cloud caught up and described it its own way; and with the
lights off, a changed pattern report set them off again. Real changes from
outside are still put right."""
import logging
import unittest

from eaveluxos import controller as C
from eaveluxos.safety import _same_effect
from tests.test_power4166 import ShortPowerCut

DEV = "TL-EDGE-01"


def described(sent, **extra):
    """How the cloud reports a pattern sent over the home network: id -1 and
    all 30 slots, the empty ones with a count of 0."""
    px = list(sent.get("pixels") or [])
    px = px + [{"index": i, "count": 0, "color": 0, "disable": True} for i in range(len(px), 30)]
    return {**sent, "id": -1, "pixels": px, **extra}


class CloudCatchesUp(ShortPowerCut):
    def restores(self, n=4):
        return [m for m in self.check(n) if "changed outside" in m]

    def test_the_cloud_describing_it_its_own_way_isnt_a_change(self):
        self.F.STATE["dev"]["currentEffect"] = described(self.c.sent_effect[DEV])
        self.assertEqual(self.restores(), [])

    def test_a_report_with_fewer_details_isnt_a_change(self):
        self.F.STATE["dev"]["currentEffect"] = {"id": -1, "name": "Christmas", "category": 1}
        self.assertEqual(self.restores(), [], "4.16.6 allowed one resend here; now none")

    def test_no_pattern_reported_is_still_a_change(self):
        self.F.STATE["dev"]["currentEffect"] = {}
        self.assertTrue(self.restores(), "as after a power cut: kept as before")

    def test_another_saved_pattern_is_still_put_right(self):
        self.F.STATE["dev"]["currentEffect"] = {"id": 19, "name": "Fall", "category": 1}
        with self.assertLogs(C.log, logging.INFO) as cm:
            said = self.restores()
        self.assertTrue(said, "a different saved pattern is a change from outside")
        why = [r for r in cm.output if "What Trimlight's cloud reported" in r]
        self.assertTrue(why and "id 19" in why[0] and "sent over the home network" in why[0], cm.output)

    def test_another_animation_is_still_put_right(self):
        sent = self.c.sent_effect[DEV]
        self.F.STATE["dev"]["currentEffect"] = described(sent, mode=(sent.get("mode", 0) + 5) % 17)
        self.assertTrue(self.restores())


class LightsOff(ShortPowerCut):
    def setUp(self):
        super().setUp()
        self.c.manual(False)
        self.c.next_try = 0
        self.c.tick()
        self.assertEqual(self.c.lan_state.get(DEV), 0)
        self.F.STATE["dev"]["switchState"] = 0
        self.check(2)

    def test_a_pattern_report_while_off_isnt_a_change(self):
        self.F.STATE["dev"]["currentEffect"] = {"id": 19, "name": "Fall", "category": 1}
        said = [m for m in self.check(4) if "changed outside" in m]
        self.assertEqual(said, [], "the lights are off: the pattern isn't showing")


class Helpers(unittest.TestCase):
    def test_empty_slots_dont_count(self):
        a = {"category": 1, "mode": 1, "speed": 60, "brightness": 220,
             "pixels": [{"index": 0, "count": 4, "color": 1}, {"index": 1, "count": 4, "color": 2}]}
        self.assertTrue(_same_effect(described(a), a))
        self.assertFalse(_same_effect({**a, "pixels": a["pixels"][:1]}, a))

    def test_the_log_words(self):
        self.assertEqual(C._brief_effect(None), "none")
        s = C._brief_effect({"id": -1, "category": 1, "mode": 1, "speed": 60, "brightness": 220,
                             "pixels": [{"count": 4, "color": 0xFF0000}, {"count": 0, "color": 0}]})
        self.assertEqual(s, "id -1, kind 1, animation 1, speed 60, brightness 220, colors #FF0000x4")
        self.assertEqual(C._brief_seen('[1, null]'), "on")
        self.assertEqual(C._brief_seen(None), "nothing")


if __name__ == "__main__":
    unittest.main()
