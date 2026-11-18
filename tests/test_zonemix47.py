# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""4.7: Combine patterns by zone (static/zonemix.js), run with Node."""
import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MIX = ROOT / "eaveluxos" / "static" / "zonemix.js"
XMAS = {"colors": ["#FF0000", "#00FF00"], "counts": [3, 3], "brightness": 220}
THANKS = {"colors": ["#FF6300", "#561003", "#FFC062"], "counts": [4, 4, 4], "brightness": 139}
FLAG = {"colors": ["#FF0000", "#FFFFFF", "#0033FF"], "counts": [4, 4, 4], "brightness": 255}
ZONES = [{"start": 1, "end": 45}, {"start": 46, "end": 95}, {"start": 96, "end": 138}]


def combine(**kw):
    js = f"const Z = require({json.dumps(str(MIX))}); try {{ console.log(JSON.stringify(Z.combine({json.dumps(kw)}))); }} " \
         f"catch (e) {{ console.log(JSON.stringify({{error: e.message}})); }}"
    return json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True, encoding="utf-8", check=True).stdout)


def bulbs(segs):
    out = []
    for s in segs:
        out += [s["c"]] * s["n"]
    return out


@unittest.skipUnless(shutil.which("node"), "Node.js isn't installed")
class Combine(unittest.TestCase):
    def test_three_patterns_on_three_zones(self):
        r = combine(zones=ZONES, picks=[XMAS, THANKS, FLAG], base="off", total=138)
        self.assertLessEqual(len(r["segs"]), 30)
        b = bulbs(r["segs"])
        self.assertEqual(len(b), 138, "every bulb, once: the pattern never repeats onto other zones")
        self.assertEqual(r["brightness"], 255)
        self.assertEqual(set(b[95:]), {"#FF0000", "#FFFFFF", "#0033FF"}, "the flag along its zone")
        self.assertEqual(b[95:107], ["#FF0000"] * 4 + ["#FFFFFF"] * 4 + ["#0033FF"] * 4, "and kept exact")
        self.assertNotIn("2", r["stretched"])
        self.assertEqual(set(b[:45]), {"#DC0000", "#00DC00"}, "Christmas, darkened to its 220 of 255")
        self.assertEqual(len(set(b[45:95])), 3, "Thanksgiving's three colors")

    def test_fits_without_stretching_when_it_can(self):
        r = combine(zones=ZONES, picks=[FLAG, None, None], base="#000000", total=138)
        self.assertEqual(r["stretched"], {})
        b = bulbs(r["segs"])
        self.assertEqual(set(b[45:]), {"#000000"}, "a zone left as the rest shows the rest")

    def test_later_zones_win_where_they_overlap(self):
        r = combine(zones=[{"start": 1, "end": 100}, {"start": 50, "end": 60}],
                    picks=[{"colors": ["#FF0000"], "counts": [5]}, {"colors": ["#0000FF"], "counts": [5]}],
                    total=100)
        b = bulbs(r["segs"])
        self.assertEqual(set(b[49:60]), {"#0000FF"})
        self.assertEqual(set(b[:49] + b[60:]), {"#FF0000"})

    def test_long_runs_split_at_90_bulbs(self):
        r = combine(zones=[{"start": 1, "end": 200}], picks=[{"colors": ["#FFFFFF"], "counts": [3]}], total=200)
        self.assertEqual([s["n"] for s in r["segs"]], [90, 90, 20])

    def test_too_many_zones_says_so(self):
        zones = [{"start": i * 2 + 1, "end": i * 2 + 2} for i in range(40)]
        picks = [{"colors": ["#FF0000" if i % 2 else "#00FF00"], "counts": [1]} for i in range(40)]
        r = combine(zones=zones, picks=picks, total=80)
        self.assertIn("allows 30", r["error"])

    def test_zones_beyond_the_lights_say_so(self):
        r = combine(zones=[{"start": 200, "end": 260}], picks=[FLAG], total=138)
        self.assertIn("outside the 138 bulbs", r["error"])

    def test_sixty_per_block_controllers(self):
        """Review #1: some controllers take 60 bulbs per block."""
        r = combine(zones=[{"start": 1, "end": 200}], picks=[{"colors": ["#FFFFFF"], "counts": [3]}], total=200, perSlot=60)
        self.assertEqual([s["n"] for s in r["segs"]], [60, 60, 60, 20])

    def test_nothing_chosen(self):
        self.assertIn("at least one zone", combine(zones=ZONES, picks=[None, None, None], total=138)["error"])

    def test_off_and_painted_patterns_carry_through(self):
        scene = {"colors": ["off", "#FFC062"], "counts": [2, 1]}
        r = combine(zones=[{"start": 1, "end": 9}], picks=[scene], total=9)
        self.assertEqual(bulbs(r["segs"]), ["off", "off", "#FFC062"] * 3)


class Wired(unittest.TestCase):
    def test_in_the_designer(self):
        js = (ROOT / "eaveluxos" / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn("data-combinezones", js)
        self.assertIn("ZoneMix.combine(", js)
        self.assertIn("const perSlot = (S.status && S.status.slot_limit) || PER_SLOT;", js)
        self.assertIn('<script src="zonemix.js"></script>', (ROOT / "eaveluxos" / "static" / "index.html").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()


try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

from tests.test_local43 import ServerBase   # noqa: E402


@unittest.skipIf(sync_playwright is None, "Playwright isn't installed")
class Browser(ServerBase):
    SHOTS = None

    def test_combine_preview_and_save(self):
        import copy
        import threading
        import time
        from eaveluxos.server import make_server
        s = copy.deepcopy(self.app.store.settings)
        s.setdefault("effects", {}).update({
            "christmas": {"label": "Christmas", **XMAS},
            "thanksgiving": {"label": "Thanksgiving", **THANKS},
            "flag": {"label": "American Flag", **FLAG}})
        s["map"] = {**(s.get("map") or {}), "total_bulbs": 138,
                    "zones": [{"name": n, **z} for n, z in zip(("Garage", "Main roof", "Porch"), ZONES)]}
        self.app.store.save_settings(s)
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
        for w in (1300, 390):
            pg = br.new_context(viewport={"width": w, "height": 1000}).new_page()
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.goto(base + "#create")
            pg.wait_for_selector("[data-combinezones]")
            pg.click("[data-combinezones]")
            pg.wait_for_selector("#dlg[open] select[name=p0]")
            pg.select_option("select[name=p0]", "christmas")
            pg.select_option("select[name=p1]", "thanksgiving")
            pg.select_option("select[name=p2]", "flag")
            note = pg.inner_text("[data-cmnote]")
            self.assertIn("of 30 color blocks", note)
            self.assertIn("Garage (colors 2× as long)", note)
            self.assertEqual(pg.locator("[data-cmprev] .strand i").count(), 26)
            self.assertEqual(pg.evaluate("document.documentElement.scrollWidth"), w, "fits")
            if self.SHOTS:
                pg.screenshot(path=f"{self.SHOTS}/combine-{w}.png", full_page=True)
            pg.check("input[name=mv][value=move]")
            pg.click("#dlg button.primary")
            pg.wait_for_selector("#dlg:not([open])", state="attached")
            self.assertEqual(pg.input_value("#dname"), "Christmas + Thanksgiving + American Flag")
            self.assertIn("26 of 30 color slots", pg.inner_text("#main"))
            if w == 1300:
                pg.click("[data-save]")
                for _ in range(100):
                    effs = self.app.store.settings.get("effects", {})
                    hit = [e for e in effs.values() if e.get("label") == "Christmas + Thanksgiving + American Flag"]
                    if hit:
                        break
                    time.sleep(0.05)
                self.assertTrue(hit, "saved as a pattern")
                self.assertEqual(len(hit[0]["colors"]), 26)
                self.assertEqual(sum(hit[0]["counts"]), 138)
                self.assertEqual(hit[0]["custom_mode"], 1, "moving: the first motion")
                self.assertEqual(hit[0]["brightness"], 255)
        self.assertEqual(errors, [])
