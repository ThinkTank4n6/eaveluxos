// SPDX-License-Identifier: MIT
// 3.18 mood follow logic (static/mood.js). Run: node tests/mood_check.js
'use strict';
const assert = require('assert');
const path = require('path');
const M = require(path.join(__dirname, '..', 'eaveluxos', 'static', 'mood.js'));

assert.strictEqual(M.classify({ rms: 0.005, onsets: 3 }), 'quiet');
assert.strictEqual(M.classify(null), 'quiet');
assert.strictEqual(M.classify({ rms: 0.03, onsets: 0.3 }), 'calm');
assert.strictEqual(M.classify({ rms: 0.09, onsets: 1.8 }), 'lively');
assert.strictEqual(M.classify({ rms: 0.2, onsets: 4 }), 'party');
// hysteresis: just over a boundary keeps the previous level
const edge = { rms: 0.0665, onsets: 1.6 };          // score just over the calm/lively cut
assert.strictEqual(M.classify(edge), 'lively');
assert.strictEqual(M.classify(edge, 'calm'), 'calm');
// Window: steady sound has no onsets; regular peaks do
const w = new M.Window();
for (let i = 0; i < 100; i++) w.add(0.05, 0.01);
assert.strictEqual(w.features().onsets, 0);
const near = (a, b) => assert.ok(Math.abs(a - b) < 1e-9, `${a} vs ${b}`);
near(w.features().rms, 0.05);
w.reset();
for (let i = 0; i < 100; i++) w.add(0.1, i % 5 === 0 ? 0.1 : 0.01);   // a peak every 0.5 s
const f = w.features();
assert.ok(f.onsets > 1.5 && f.onsets <= 2, `onsets ${f.onsets}`);
console.log('mood ok');
