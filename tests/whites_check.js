// SPDX-License-Identifier: MIT
// Checks for eaveluxos/static/whites.js, run by tests/test_whites.py with Node.
'use strict';
const assert = require('assert');
const W = require('../eaveluxos/static/whites.js');

// Reference points of the blackbody fit.
assert.strictEqual(W.kelvinHex(2700), '#FFA757');
assert.strictEqual(W.kelvinHex(6500), '#FFFEFA');
assert.deepStrictEqual(W.kelvinRgb(1800), [255, 126, 0]);

// Warmer = less blue and green; cooler = more, all the way up.
let prev = W.kelvinRgb(W.MIN);
for (let k = W.MIN + 100; k <= W.MAX; k += 100) {
  const c = W.kelvinRgb(k);
  assert.strictEqual(c[0], 255, `red stays full at ${k} K`);
  assert.ok(c[1] >= prev[1] && c[2] >= prev[2], `cooler at ${k} K`);
  prev = c;
}

// Out of range or nonsense: clamped, never NaN.
assert.strictEqual(W.kelvinHex(100), W.kelvinHex(W.MIN));
assert.strictEqual(W.kelvinHex(50000), W.kelvinHex(W.MAX));
assert.match(W.kelvinHex('x'), /^#[0-9A-F]{6}$/);

// Presets: in range, warm to cool, unique.
const ks = W.PRESETS.map(p => p.k);
assert.deepStrictEqual(ks, [...ks].sort((a, b) => a - b));
assert.ok(ks.every(k => k >= W.MIN && k <= W.MAX));
assert.strictEqual(new Set(W.PRESETS.map(p => W.kelvinHex(p.k))).size, W.PRESETS.length);
console.log('whites ok');
