# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""4.12: the House Mapping Studio.

- Place bulbs: a bulb dragged to where it really sits is pinned there; the
  bulbs between pins spread out evenly again along the line.
- Zone alignment: nudge a zone's ends while it's lit (first bulb green, last
  red), and a zone can run the other way.
- The whole house at once: one pattern, tonight's schedule (each controller
  its own), or a pattern for each zone.
- Elevations: front, side and rear elevations by name, versions of each (day
  and night, before and after), and one elevation exported and imported as a
  file with its photos."""
import copy
import io
import json
import subprocess
import threading
import time
import unittest
from pathlib import Path

from eaveluxos.server import ApiError, App
from tests.test_multi45 import DECK, FRONT, TwoBase

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "eaveluxos" / "static"

try:
    from playwright.sync_api import sync_playwright
except ImportError:            # pragma: no cover
    sync_playwright = None


def node(js: str) -> dict:
    try:
        out = subprocess.run(["node", "-e", js], capture_output=True, text=True, encoding="utf-8", timeout=30)
    except FileNotFoundError:
        raise unittest.SkipTest("Node isn't installed")
    if out.returncode:
        raise AssertionError(out.stderr)
    return json.loads(out.stdout)


class Pins(unittest.TestCase):
    def run_js(self, body):
        return node("const H = require(%s); const Z = require(%s); console.log(JSON.stringify((() => { %s })()));"
                    % (json.dumps(str(STATIC / "housefx.js")), json.dumps(str(STATIC / "zonemix.js")), body))

    def test_without_pins_nothing_changes(self):
        got = self.run_js("return H.lineBulbs([[0, 50], [100, 50]], [], 1, 10).map(p => [p.b, +p.x.toFixed(2), p.pinned]);")
        self.assertEqual([x[1] for x in got], [5, 15, 25, 35, 45, 55, 65, 75, 85, 95])
        self.assertFalse(any(x[2] for x in got))

    def test_a_pin_holds_and_the_rest_respread(self):
        got = self.run_js("return H.lineBulbs([[0, 50], [100, 50]], [], 1, 11, [[6, 30, 40]]).map(p => [p.b, +p.x.toFixed(2), +p.y.toFixed(2), p.pinned]);")
        self.assertEqual(got[5], [6, 30, 40, True])
        left = [x[1] for x in got[:5]]
        gaps = [b - a for a, b in zip(left, left[1:])]
        self.assertLess(max(gaps) - min(gaps), 0.02, f"evenly spread before the pin: {left}")
        right = [x[1] for x in got[6:]]
        gaps = [b - a for a, b in zip(right, right[1:])]
        self.assertLess(max(gaps) - min(gaps), 0.02, f"and after it: {right}")
        self.assertTrue(all(a[2] < 50 for a in got[1:10]), "the bulbs near it follow it up")

    def test_counting_down_and_bad_pins(self):
        got = self.run_js("""return H.lineBulbs([[0, 50], [100, 50]], [1], 11, 1, [[1, 95, 50], [6, 30, 50], [99, 1, 1], [6, 70, 50], 'x'])
            .map(p => [p.b, +p.x.toFixed(1), p.pinned]);""")
        self.assertEqual(got[-1], [1, 95, True], "bulb 1 is at the line's end, where it's pinned")
        self.assertEqual(got[5], [6, 30, True], "the first pin for a bulb counts; outside the range is ignored")
        self.assertEqual(sum(1 for x in got if x[2]), 2)

    def test_set_pin(self):
        got = self.run_js("""const l = {pins: [[5, 1, 1]]};
            const a = H.setPin(l, 3, 10.04, 120); const b = H.setPin({pins: a}, 5, null, null);
            let tooMany = null; try { H.setPin({pins: Array.from({length: 200}, (_, i) => [i + 1, 1, 1])}, 500, 1, 1); } catch (e) { tooMany = e.message; }
            return {a, b, tooMany};""")
        self.assertEqual(got["a"], [[3, 10, 100], [5, 1, 1]])
        self.assertEqual(got["b"], [[3, 10, 100]])
        self.assertIn("200", got["tooMany"])

    def test_a_zone_that_runs_the_other_way(self):
        got = self.run_js("""const pick = {colors: ['#FF0000', '#0000FF'], counts: [1, 3], brightness: 255};
            const r = rev => Z.combine({zones: [{start: 1, end: 8, reverse: rev}], picks: [pick], total: 8}).segs.map(s => [s.c, s.n]);
            return {fwd: r(false), back: r(true)};""")
        self.assertEqual(got["fwd"], [["#FF0000", 1], ["#0000FF", 3], ["#FF0000", 1], ["#0000FF", 3]])
        self.assertEqual(got["back"], [["#0000FF", 3], ["#FF0000", 1], ["#0000FF", 3], ["#FF0000", 1]])


class MapChecks(unittest.TestCase):
    def ok(self, m):
        App._validate_map(m)

    def bad(self, m):
        with self.assertRaises(ApiError):
            App._validate_map(m)

    def test_elevations_and_versions(self):
        self.ok({"sides": [{"id": "front", "name": "Front elevation", "kind": "front", "use": "front-night", "vname": "Day"},
                           {"id": "front-night", "name": "Night", "of": "front"},
                           {"id": "garage", "name": "Garage side elevation", "kind": "side"}]})
        for sides in ([{"id": "front", "name": "F", "kind": "roof"}],
                      [{"id": "a", "name": "A"}, {"id": "b", "name": "B", "of": "a"}, {"id": "c", "name": "C", "of": "b"}],
                      [{"id": "a", "name": "A", "of": "a"}],
                      [{"id": "a", "name": "A", "use": "z"}, {"id": "z", "name": "Z"}],
                      [{"id": "a", "name": "A"}, {"id": "a", "name": "B"}],
                      [{"id": "a", "name": "A", "secret": 1}],
                      [{"id": f"s{i}", "name": "S"} for i in range(81)]):
            with self.subTest(sides=sides):
                self.bad({"sides": sides})

    def test_pins(self):
        line = {"id": "a", "kind": "edge", "points": [[0, 0], [100, 0]], "bulbs": {"from": 1, "to": 50}}
        self.ok({"rooflines": {"front": [{**line, "pins": [[3, 10.5, 0], [9, 99, 100]]}]}})
        for pins in ([[3, 10, 101]], [[3, 1, 1], [3, 2, 2]], [[0, 1, 1]], [[True, 1, 1]], [[3, 1]], "x",
                     [[i + 1, 1, 1] for i in range(201)]):
            with self.subTest(pins=pins):
                self.bad({"rooflines": {"front": [{**line, "pins": pins}]}})

    def test_zone_direction(self):
        self.ok({"zones": [{"name": "Porch", "start": 1, "end": 9, "reverse": True}]})
        self.bad({"zones": [{"name": "Porch", "start": 1, "end": 9, "reverse": "yes"}]})


class Review(unittest.TestCase):
    """Fixes from the 4.12 code review."""

    def test_1_deleting_a_version_deletes_its_photo(self):
        r = subprocess.run([__import__("sys").executable, str(ROOT / "tests" / "repro_version_photo_left.py")], capture_output=True,
                           text=True, encoding="utf-8", timeout=120, cwd=ROOT)
        self.assertRegex(r.stdout, r"^(OK|SKIP):", r.stdout + r.stderr)

    def test_2_a_version_of_an_elevation_that_isnt_there(self):
        with self.assertRaises(ApiError):
            App._validate_map({"sides": [{"id": "front", "name": "F"}, {"id": "gone-night", "name": "Night", "of": "gone"}]})

    def test_4_zone_ends_never_match_the_middle(self):
        got = node("""const vm = require('vm'); const src = require('fs').readFileSync(%s, 'utf8');
            const a = src.indexOf('function runsToSegs'), b = src.indexOf('/* Paint zones over');
            const c = src.indexOf('function zoneCheckDef'), d = src.indexOf('/* The elevations (as shown');
            const ctx = {PER_SLOT: 90, MAX_SLOTS: 30}; vm.createContext(ctx);
            vm.runInContext(src.slice(a, b) + src.slice(c, d), ctx);
            const two = ctx.zoneCheckDef(5, 6, 10, '#FFFFFF', false), red = ctx.zoneCheckDef(2, 8, 10, '#FF0000', true);
            console.log(JSON.stringify({two: two.colors, red: red.colors, counts: red.counts}));""" % json.dumps(str(STATIC / "app.js")))
        self.assertEqual(got["two"], ["#000000", "#00FF00", "#FF0000", "#000000"])
        self.assertEqual(got["red"], ["#000000", "#FF0000", "#FFC062", "#00FF00", "#000000"], "the other way: red first")
        self.assertEqual(got["counts"], [1, 1, 5, 1, 2])


class Tonight(TwoBase):
    def test_each_controller_from_noon_to_noon(self):
        s = copy.deepcopy(self.app.store.settings)
        s["rules"] = [{"name": "Deck", "on": "18:00", "off": "21:00", "effect": "warm_white", "controllers": [DECK]},
                      {"name": "Front", "on": "17:00", "off": "23:00", "effect": "christmas", "controllers": [FRONT]}]
        self.app.save_settings(s)
        self.app.ctrl.devices = [{"deviceId": DECK, "name": "Deck"}, {"deviceId": FRONT, "name": "Front"}]
        r = self.app.house_tonight()
        self.assertEqual(set(r["devices"]), {DECK, FRONT})
        deck, front = r["devices"][DECK], r["devices"][FRONT]
        self.assertEqual([(x["effect"], x["start"][11:16], x["end"][11:16]) for x in deck], [("warm_white", "18:00", "21:00")])
        self.assertEqual([(x["effect"], x["rule"]) for x in front], [("christmas", "Front")])
        self.assertLess(r["start"], r["now"])
        self.assertLess(r["now"], r["end"])


@unittest.skipIf(sync_playwright is None, "Playwright isn't installed")
class Browser(TwoBase):
    SHOTS = None

    def test_the_studio(self):
        from PIL import Image
        from eaveluxos.server import make_server
        b = io.BytesIO()
        Image.new("RGB", (600, 400), (90, 110, 150)).save(b, "JPEG")
        self.app.save_photo(self.app.photo_path("front"), b.getvalue())
        s = copy.deepcopy(self.app.store.settings)
        s["effects"].update({"red": {"label": "Red", "colors": ["#FF0000"], "counts": [4]},
                             "blue": {"label": "Blue", "colors": ["#0000FF", "#FFFFFF"], "counts": [3, 3], "custom_mode": 1}})
        s["map"] = {"total_bulbs": 100, "zones": [{"name": "Porch", "start": 10, "end": 30}, {"name": "Roof", "start": 40, "end": 90}],
                    "rooflines": {"front": [{"id": "a", "kind": "edge", "points": [[10, 40], [90, 40]], "wire": [], "bulbs": {"from": 1, "to": 100}}]},
                    "landmarks": [{"name": "Peak", "bulb": 50, "side": "front", "x": 0.5, "y": 0.38}]}
        self.app.save_settings(s)
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

        def until(cond, what, n=160):
            for _ in range(n):
                if cond():
                    return
                time.sleep(0.05)
            self.fail(f"never: {what}")
        mp = lambda: self.app.store.settings.get("map") or {}
        side = lambda i: next((x for x in mp().get("sides", []) if x["id"] == i), {})
        pg = br.new_page(viewport={"width": 1300, "height": 1000}, accept_downloads=True)
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(base + "#map")
        pg.wait_for_selector("[data-ver]")
        self.assertIn("Front elevation", pg.inner_text("#main"))
        self.assertIn("Rear elevation", pg.inner_text("#main"))

        # --- Place bulbs: drag bulb 50 up to where it really is
        pg.click('[data-hvmode="bulbs"]')
        pg.wait_for_selector("#hvcv[tabindex]")
        pg.wait_for_timeout(300)
        box = pg.locator("#hvcv").bounding_box()
        x0 = box["x"] + box["width"] * (10 + 49.5 / 100 * 80) / 100
        y0 = box["y"] + box["height"] * 0.40
        pg.mouse.move(x0, y0)
        pg.mouse.down()
        pg.mouse.move(x0, y0 - box["height"] * 0.05, steps=4)
        pg.mouse.move(x0, y0 - box["height"] * 0.10, steps=4)
        pg.mouse.up()
        until(lambda: (mp()["rooflines"]["front"][0].get("pins") or [[0]])[0][0] == 50, "bulb 50 pinned")
        pin = mp()["rooflines"]["front"][0]["pins"][0]
        self.assertAlmostEqual(pin[2], 30, delta=1.5)
        pg.wait_for_selector("[data-hvlight]")
        pg.click("[data-hvlight]")
        until(lambda: self.app.ctrl.override is not None, "bulb 50 lit on the house")
        if self.SHOTS:
            pg.locator("#hvbox").screenshot(path=f"{self.SHOTS}/place-bulbs.png")

        # --- A night version, from the same rooflines and pins, shown in the whole house
        pg.click("[data-addver]")
        pg.fill("#dlg input[name=nm]", "Night")
        pg.locator("#dlg .primary").last.click()
        until(lambda: side("front-night").get("of") == "front", "the version")
        self.assertEqual(mp()["rooflines"]["front-night"][0]["pins"], mp()["rooflines"]["front"][0]["pins"])
        self.assertTrue(any(l.get("side") == "front-night" for l in mp()["landmarks"]), "its pins too")
        pg.wait_for_selector("[data-usever]")
        pg.click("[data-usever]")
        until(lambda: side("front").get("use") == "front-night", "shown in the whole house")

        # --- Zone alignment: one later at the start, the other way, lit while nudged
        if "closed" in (pg.get_attribute('[data-fold="zones"]', "class") or ""):
            pg.click('[data-fold="zones"] .foldbar')
        pg.click('[data-editzone="0"]')
        pg.wait_for_selector("#dlg [data-zcv]")
        pg.click("#dlg [data-zlight]")
        until(lambda: self.app.ctrl.override is not None and "Zone 10" in str(self.app.ctrl.override.get("effect")), "the zone lit, ends marked")
        k1 = self.app.ctrl.override["effect"]
        pg.click('#dlg [data-znudge="s"][data-by="1"]')
        pg.check("#dlg input[name=zrev]")
        until(lambda: self.app.ctrl.override["effect"] != k1, "the house follows the nudge")
        self.assertIn("Zone 11", self.app.ctrl.override["effect"])
        self.assertIn("Front elevation", pg.inner_text("#dlg [data-zsides]"))
        if self.SHOTS:
            pg.locator("#dlg").screenshot(path=f"{self.SHOTS}/zone.png")
        pg.locator("#dlg .primary").last.click()
        until(lambda: mp()["zones"][0].get("start") == 11, "saved")
        self.assertTrue(mp()["zones"][0]["reverse"])
        self.assertIn("runs the other way", pg.inner_text("#main"))

        # --- The whole house: one pattern, tonight, a pattern for each zone
        pg.click('[data-fold="whole"] .foldbar')
        pg.wait_for_selector("[data-wh='0']")
        self.assertIn("Night", pg.inner_text("#wholebox"), "the version shown in the whole house")
        pg.click('[data-whsrc="tonight"]')
        pg.wait_for_selector("#what")
        pg.click("[data-whplay]")
        v0 = float(pg.eval_on_selector("#what", "e => e.value"))
        until(lambda: float(pg.eval_on_selector("#what", "e => e.value")) > v0, "playing through the night")
        pg.click('[data-whsrc="zones"]')
        pg.select_option('[data-whpick="0"]', "red")
        pg.select_option('[data-whpick="1"]', "blue")
        if self.SHOTS:
            pg.wait_for_timeout(400)
            pg.locator("#wholebox").screenshot(path=f"{self.SHOTS}/whole.png")
        pg.click("[data-whcombine]")
        pg.wait_for_selector("#dlg select[name=p1]")
        self.assertEqual(pg.eval_on_selector("#dlg select[name=p0]", "e => e.value"), "red")
        self.assertEqual(pg.eval_on_selector("#dlg select[name=p1]", "e => e.value"), "blue")
        pg.click("#dlg [type=button].ghost, #dlg button.ghost")

        # --- Export the front elevation, then import it as a new one
        pg.goto(base + "#map")
        pg.wait_for_selector("[data-exportelev]")
        with pg.expect_download() as dl:
            pg.click("[data-exportelev]")
        path = dl.value.path()
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        self.assertEqual((data["format"], data["name"], data["use"]), ("eaveluxos-elevation", "Front elevation", 1))
        self.assertEqual([v["name"] for v in data["versions"]], ["Main", "Night"])
        self.assertTrue(data["versions"][0]["photo"].startswith("data:image/"))
        pg.set_input_files("#elevfile", path)
        until(lambda: any(x.get("name") == "Front elevation (2)" for x in mp().get("sides", [])), "imported")
        new = next(x for x in mp()["sides"] if x.get("name") == "Front elevation (2)")
        night = next(x for x in mp()["sides"] if x.get("of") == new["id"])
        self.assertEqual(new.get("use"), night["id"])
        self.assertEqual(mp()["rooflines"][new["id"]][0]["pins"][0][0], 50)
        self.assertTrue(self.app.photo_path(new["id"]).exists(), "its photo came along")
        self.assertTrue(any(l.get("side") == night["id"] and l["name"] == "Peak" for l in mp()["landmarks"]))
        # Deleting the copy removes its photo, rooflines and pins
        pg.wait_for_selector("[data-delelev]")
        pg.click("[data-delelev]")
        pg.click("#dlg button.danger")
        until(lambda: not any(x.get("name") == "Front elevation (2)" for x in mp().get("sides", [])), "deleted")
        self.assertNotIn(new["id"], mp()["rooflines"])
        self.assertFalse(self.app.photo_path(new["id"]).exists())
        if self.SHOTS:
            pg.screenshot(path=f"{self.SHOTS}/house.png", full_page=True)
        # A phone
        ph = br.new_page(viewport={"width": 390, "height": 844})
        ph.on("pageerror", lambda e: errors.append(str(e)))
        ph.goto(base + "#map")
        ph.wait_for_selector("[data-ver]")
        self.assertEqual(ph.evaluate("document.documentElement.scrollWidth"), 390, "fits a phone")
        ph.close()
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
