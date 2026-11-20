# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""4.16: camera calibration. The controller shows a few coded frames (each
bulb's number in binary, a short repeating pattern that fits 30 color
blocks); the camera reads every bulb's number and place from them; bulbs in
a row become lines with each found bulb pinned, saved as a new version of
the elevation with the camera's photo."""
import copy
import json
import subprocess
import threading
import time
import unittest
from pathlib import Path

from tests.test_multi45 import DECK, TwoBase

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "eaveluxos" / "static"

try:
    from playwright.sync_api import sync_playwright
except ImportError:            # pragma: no cover
    sync_playwright = None

# A night photo, made up: N bulbs up a gable and along an eave, a street lamp,
# noise; shake (pixels) and uneven bulbs, for each of the frames.
SIM = r"""
const C = require(%s);
function run(N, W, sigma, shake, vary, mirror) {
  const H = Math.round(W * 9 / 16), pos = [];
  const a = Math.min(N, Math.round(N * 0.55));
  for (let n = 1; n <= a; n++) { const t = (n - 1) / Math.max(1, a - 1); pos[n] = t < .5 ? [0.15 + t * 0.7, 0.55 - t * 0.6] : [0.15 + t * 0.7, 0.25 + (t - .5) * 0.6]; }
  for (let n = a + 1; n <= N; n++) { const t = (n - a - 1) / Math.max(1, N - a - 1); pos[n] = [0.1 + t * 0.8, 0.72]; }
  let seed = 11; const rnd = () => (seed = seed * 16807 %% 2147483647) / 2147483647;
  const gain = Array.from({ length: N + 1 }, () => 1 - vary * rnd());
  const shot = f => {
    const g = new Float32Array(W * H), ox = (rnd() - .5) * 2 * shake, oy = (rnd() - .5) * 2 * shake;
    for (let i = 0; i < g.length; i++) g[i] = 12 + rnd() * 10;
    const blob = (cx, cy, r, A) => { for (let y = Math.max(0, cy - 3 * r | 0); y < Math.min(H, cy + 3 * r + 1); y++) for (let x = Math.max(0, cx - 3 * r | 0); x < Math.min(W, cx + 3 * r + 1); x++) g[y * W + x] += A * Math.exp(-((x - cx) ** 2 + (y - cy) ** 2) / (2 * r * r)); };
    blob(W * .92, H * .2, 6, 180);
    for (let n = 1; n <= N; n++) if (C.lit(f, n)) {
      blob(pos[n][0] * W + ox, pos[n][1] * H + oy, sigma, 200 * gain[n]);
      if (mirror && n > N - mirror) blob(pos[n][0] * W + ox, (pos[n][1] + .15) * H + oy, sigma, 200 * gain[n]);
    }
    return Uint8Array.from(g, v => Math.min(255, v));
  };
  const fr = C.frames(N, 90), sh = { bits: [] };
  for (const f of fr) { const s = shot(f); if (f.kind === 'dark') sh.dark = s; else if (f.kind === 'full') sh.full = s; else (sh.bits[f.bit] = sh.bits[f.bit] || [])[f.kind === 'bit' ? 0 : 1] = s; }
  const r = C.decode(sh, W, H, N);
  const err = r.bulbs.filter(b => !mirror || b.y < 80).map(b => Math.hypot(b.x / 100 - pos[b.bulb][0], (b.y / 100 - pos[b.bulb][1]) * 9 / 16) * 100);
  const s = C.toSections(r.bulbs, 9 / 16);
  return { frames: fr.length, blocks: Math.max(...fr.map(f => f.effect.colors.length)), counts: Math.max(...fr.flatMap(f => f.effect.counts)),
           found: new Set(r.bulbs.map(b => b.bulb)).size, dets: r.bulbs.length, err: Math.max(0, ...err),
           sections: s.sections.map(x => [x.bulbs.from, x.bulbs.to, x.pins.length, x.points.length]), dropped: s.dropped };
}
"""


def node(js):
    try:
        out = subprocess.run(["node", "-e", js], capture_output=True, text=True, encoding="utf-8", timeout=120)
    except FileNotFoundError:
        raise unittest.SkipTest("Node isn't installed")
    if out.returncode:
        raise AssertionError(out.stderr)
    return json.loads(out.stdout)


def sim(*cases):
    return node(SIM % json.dumps(str(STATIC / "calib.js")) + "console.log(JSON.stringify([%s].map(a => run(...a))));"
                % ",".join(json.dumps(c) for c in cases))


class Decode(unittest.TestCase):
    def test_every_bulb_found_where_it_is(self):
        for (N, W, sigma, shake, vary), r in zip(
                [(106, 480, 1.1, 0, 0), (106, 320, 1.2, 0, 0.5), (106, 640, 1.5, 1.5, 0.6), (300, 960, 1.2, 1, 0.5)],
                sim([106, 480, 1.1, 0, 0, 0], [106, 320, 1.2, 0, 0.5, 0], [106, 640, 1.5, 1.5, 0.6, 0], [300, 960, 1.2, 1, 0.5, 0])):
            with self.subTest(N=N, W=W, shake=shake):
                if shake < 1.5:
                    self.assertEqual(r["found"], N)
                else:                         # a phone that moves 1.5 pixels between frames: nearly all
                    self.assertGreaterEqual(r["found"], N - 3)
                self.assertLess(r["err"], 1.0, "within 1% of the photo's width")
                self.assertEqual([s[:2] for s in r["sections"]], [[1, round(N * 0.55)], [round(N * 0.55) + 1, N]], "a gable and an eave")
                self.assertEqual(r["dropped"], [])

    def test_frames_fit_any_controller(self):
        for N, r in zip((50, 106, 1000), sim([50, 480, 1, 0, 0, 0], [106, 480, 1, 0, 0, 0], [1000, 960, 0.8, 0, 0, 0])):
            with self.subTest(N=N):
                self.assertLessEqual(r["blocks"], 30)
                self.assertLessEqual(r["counts"], 90)
        self.assertEqual(sim([106, 480, 1, 0, 0, 0])[0]["frames"], 16, "2 + 2 x 7 bits, not 106")

    def test_a_mirrored_run(self):
        r = sim([106, 640, 1.1, 0, 0, 20])[0]
        self.assertEqual(r["found"], 106)
        self.assertEqual(r["dets"], 126, "the 20 mirrored bulbs, in both places")
        self.assertEqual(len(r["sections"]), 3, "and a line of their own")

    def test_lines_have_room(self):
        got = node("""const C = require(%s);
            const b = Array.from({length: 450}, (_, i) => ({bulb: i + 1, x: 5 + i * 0.2, y: 50 + Math.sin(i / 7) * 3}));
            const s = C.toSections(b, 0.56);
            console.log(JSON.stringify(s.sections.map(x => [x.bulbs.from, x.bulbs.to, x.pins.length, x.points.length])));"""
                   % json.dumps(str(STATIC / "calib.js")))
        self.assertEqual([g[:3] for g in got], [[1, 200, 200], [201, 400, 200], [401, 450, 50]])
        self.assertTrue(all(2 <= g[3] <= 100 for g in got))


class Review(unittest.TestCase):
    def test_1_a_preview_ends_on_the_choice_it_covered(self):
        from tests import reprorun
        reprorun.run(self, "repro_preview_end.py", 120)

    def test_2_lines_that_dont_fit_are_counted(self):
        got = node("""const C = require(%s);
            const b = []; for (let k = 0; k < 45; k++) for (let i = 0; i < 4; i++) b.push({bulb: k * 10 + i + 1, x: k * 2 + i * 0.3, y: k %% 2 ? 10 : 60});
            const s = C.toSections(b, 0.56); console.log(JSON.stringify({n: s.sections.length, cut: s.cut}));""" % json.dumps(str(STATIC / "calib.js")))
        self.assertEqual(got, {"n": 40, "cut": 5})


class GlobalPreview(TwoBase):
    def test_3_a_preview_for_every_controller_also_goes_back(self):
        c = self.app.ctrl
        c.manual(True, "christmas")
        from eaveluxos.schedule import Effect
        e = Effect.from_config("_try", {"label": "x", "colors": ["#FFFFFF"], "counts": [3]}, None)
        c.manual(True, obj=e, expires_min=10)
        c.manual(True, obj=e, expires_min=10)
        c.end_preview()
        self.assertEqual((c.override or {}).get("effect"), "christmas")
        c.manual(True, obj=e, expires_min=10)
        c.override["expires"] = 0.0 + 1
        c.next_try = 0
        c.tick()
        self.assertEqual((c.override or {}).get("effect"), "christmas", "and when it ends by itself")


@unittest.skipIf(sync_playwright is None, "Playwright isn't installed")
class Browser(TwoBase):
    SHOTS = None

    def test_calibrate_with_a_camera(self):
        import io

        from PIL import Image

        from eaveluxos.server import make_server
        b = io.BytesIO()
        Image.new("RGB", (640, 360), (20, 24, 40)).save(b, "JPEG")
        self.app.save_photo(self.app.photo_path("front"), b.getvalue())
        from tests.test_multi45 import FRONT
        self.app.ctrl.devices = [{"deviceId": DECK, "name": "Deck"}, {"deviceId": FRONT, "name": "Front"}]
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
        ctx = br.new_context(viewport={"width": 1100, "height": 900})
        self.addCleanup(ctx.close)
        # A camera that sees the house as the controller was last told to light it, a moment later
        ctx.add_init_script("""(() => {
          const W = 640, H = 360, cv = document.createElement('canvas'); cv.width = W; cv.height = H;
          const g = cv.getContext('2d'); window.__shown = null; window.__N = 0;
          const of = window.fetch;
          window.fetch = (u, o) => { try { const b = o && o.body && JSON.parse(o.body);
            if (String(u).endsWith('api/action') && b && b.action === 'try') setTimeout(() => { window.__shown = b.effect; }, 300); } catch (e) {}
            return of(u, o); };
          const colorAt = (e, n) => { const L = e.counts.reduce((a, b) => a + b, 0); let k = (n - 1) % L;
            for (let i = 0; i < e.counts.length; i++) { if (k < e.counts[i]) return e.colors[i]; k -= e.counts[i]; } };
          const draw = () => { g.fillStyle = '#0c0e18'; g.fillRect(0, 0, W, H); const N = window.__N, e = window.__shown;
            if (e && N) for (let n = 1; n <= N; n++) if (colorAt(e, n) === '#FFFFFF') {
              const t = (n - 1) / (N - 1), x = 40 + t * 560, y = 300 - Math.sin(t * Math.PI) * 200;
              g.fillStyle = '#fff'; g.beginPath(); g.arc(x, y, 1.6, 0, 7); g.fill(); }
            requestAnimationFrame(draw); };
          draw();
          navigator.mediaDevices.getUserMedia = async () => cv.captureStream(30);
        })();""")
        pg = ctx.new_page()
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(base + "#map")
        pg.wait_for_selector("#hdev")
        pg.select_option("#hdev", DECK)
        pg.wait_for_selector("[data-calib]")
        n = pg.evaluate("addressSpace(houseDev())")
        pg.evaluate(f"window.__N = {n}")
        pg.click("[data-calib]")
        pg.wait_for_selector("#dlg [data-cstart]:not([disabled])")
        pg.click("#dlg [data-cstart]")
        for _ in range(900):
            if "Found" in pg.inner_text("#dlg [data-cs]") or "No bulbs" in pg.inner_text("#dlg [data-cs]"):
                break
            time.sleep(0.1)
        text = pg.inner_text("#dlg [data-cs]")
        self.assertIn(f"Found {n} of {n} bulbs", text)
        self.assertIsNone(self.app.ctrl.dev_override.get(DECK), "the lights back on the schedule")
        if self.SHOTS:
            pg.locator("#dlg").screenshot(path=f"{self.SHOTS}/calibrated.png")
        pg.click("#dlg [data-csave]")
        mp = lambda: self.app.store.settings.get("map") or {}
        for _ in range(200):
            if any(x.get("name") == "Calibrated" for x in mp().get("sides", [])):
                break
            time.sleep(0.05)
        side = next(x for x in mp()["sides"] if x.get("name") == "Calibrated")
        self.assertEqual(side["of"], "front")
        lines = mp()["rooflines"][side["id"]]
        pins = [p for ln in lines for p in ln["pins"]]
        self.assertEqual(sorted({p[0] for p in pins}), list(range(1, n + 1)))
        p50 = next(p for p in pins if p[0] == 50)
        t = 49 / (n - 1)
        self.assertAlmostEqual(p50[1], (40 + t * 560) / 640 * 100, delta=1)
        front = next(x for x in mp()["sides"] if x["id"] == "front")
        self.assertEqual((front.get("use"), front.get("device")), (side["id"], DECK))
        self.assertTrue(self.app.photo_path(side["id"]).exists())
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
