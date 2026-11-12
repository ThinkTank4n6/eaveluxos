// SPDX-License-Identifier: MIT
// Checks for eaveluxos/static/roofline.js, run by tests/test_roofline.py with Node.
'use strict';
const assert = require('assert');
const RL = require('../eaveluxos/static/roofline.js');

// A synthetic gable: bright sky above a dark house whose roofline peaks in the middle.
const w = 200, h = 150, data = new Uint8ClampedArray(w * h * 4);
const roofY = x => 40 + Math.abs(x - w / 2) * 0.5;               // 40 at the peak, 90 at the edges
for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
  const i = (y * w + x) * 4, v = y < roofY(x) ? 210 : 40;
  data[i] = data[i + 1] = data[i + 2] = v; data[i + 3] = 255;
}
const res = RL.detectRoofline({ data, width: w, height: h });
assert.strictEqual(res.quality, 'strong', res.message);
assert(res.points.length >= 3 && res.points.length <= 60, 'simplified to a few points');
for (const [px, py] of res.points) {
  const x = px / 100 * (w - 1), y = py / 100 * (h - 1);
  assert(Math.abs(y - roofY(x)) <= 4, `point ${px},${py} is on the roofline`);
}
const peak = res.points.reduce((a, b) => (b[1] < a[1] ? b : a));
assert(Math.abs(peak[0] - 50) < 5, 'peak near the middle');

// A blank photo gives no suggestion; bad input is refused.
const flat = new Uint8ClampedArray(w * h * 4).fill(128);
assert.deepStrictEqual(RL.detectRoofline({ data: flat, width: w, height: h }).points, []);
assert.throws(() => RL.detectRoofline({ data, width: w, height: h }, { top: 50, bottom: 55 }), /10%/);
assert.throws(() => RL.detectRoofline({ data: new Uint8ClampedArray(16), width: 2, height: 2 }), /Unsupported/);

// Wire-only marks follow inserted and deleted points.
assert.deepStrictEqual(RL.insertWirePoint([1], 2, 4), [1, 2]);   // split a wire-only stretch: both halves stay wire
assert.deepStrictEqual(RL.insertWirePoint([2], 1, 4), [3]);
assert.deepStrictEqual(RL.deleteWirePoint([0, 2], 1, 4), [0, 1]);
assert.deepStrictEqual(RL.roofSegments({ points: [[0, 0], [1, 1], [2, 2]], wire: [1] }).map(s => s.lit), [true, false]);

// Flat diagram: every side, escaped names, pins with bulb numbers.
const svg = RL.flatHouseSvg([{ id: 'front', name: 'Front <&>' }, { id: 'shed', name: 'Shed' }],
  { front: [{ id: 'a', kind: 'ridge', points: [[0, 50], [50, 10], [100, 50]], wire: [1] }] },
  [{ name: 'Peak "A"', bulb: 42, side: 'front', x: .5, y: .1 }]);
assert(svg.startsWith('<svg') && svg.includes('Front &lt;&amp;&gt;') && !svg.includes('<&>'));
assert(svg.includes('Peak &quot;A&quot; · 42') && svg.includes('No roofline traced yet') && svg.includes('stroke-dasharray'));
assert(RL.validSection({ id: 'a', kind: 'edge', points: [[0, 0], [100, 100]] }));
assert(!RL.validSection({ id: 'a', kind: 'edge', points: [[0, 0], [101, 0]] }));
console.log('roofline ok');
