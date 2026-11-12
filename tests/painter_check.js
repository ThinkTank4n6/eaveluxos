// SPDX-License-Identifier: MIT
// Checks for eaveluxos/static/painter.js, run by tests/test_painter.py with Node.
'use strict';
const assert = require('assert');
const P = require('../eaveluxos/static/painter.js');
const R = '#FF0000', G = '#00FF00', W = '#FFFFFF', K = '#000000';

// expand / compress round trip, repeat to a length, 90-bulb runs.
const segs = [{ c: R, n: 2 }, { c: G, n: 1 }];
assert.deepStrictEqual(P.expand(segs), [R, R, G]);
assert.deepStrictEqual(P.expand(segs, 7), [R, R, G, R, R, G, R]);
assert.deepStrictEqual(P.compress(P.expand(segs)), segs);
assert.deepStrictEqual(P.compress(new Array(200).fill(W)), [{ c: W, n: 90 }, { c: W, n: 90 }, { c: W, n: 20 }]);
assert.deepStrictEqual(P.compress([R, 'off', 'off', R]), [{ c: R, n: 1 }, { c: 'off', n: 2 }, { c: R, n: 1 }]);

// Painting: single bulb, range, every Nth with width; nothing is changed in place.
const base = new Array(20).fill(K);
assert.deepStrictEqual(P.paintBulb(base, 5, R).map((c, i) => c === R ? i + 1 : 0).filter(Boolean), [5]);
assert.deepStrictEqual(base, new Array(20).fill(K));
assert.deepStrictEqual(P.paintRange(base, 3, 6, 'off').slice(1, 7), [K, 'off', 'off', 'off', 'off', K]);
const every = P.paintEvery(base, 2, 20, 4, 2, W).map((c, i) => c === W ? i + 1 : 0).filter(Boolean);
assert.deepStrictEqual(every, [2, 3, 6, 7, 10, 11, 14, 15, 18, 19]);
assert.deepStrictEqual(P.paintEvery(base, 1, 10, 3, 1, G).map((c, i) => c === G ? i + 1 : 0).filter(Boolean), [1, 4, 7, 10]);
assert.strictEqual(P.slotsNeeded(P.paintEvery(base, 1, 20, 2, 1, W)), 20);
assert.strictEqual(P.paintRange(base, 1, 1, '#ff00aa')[0], '#FF00AA');

// Bad input is refused with a message.
assert.throws(() => P.paintRange(base, 0, 3, R), /1 to 20/);
assert.throws(() => P.paintRange(base, 5, 4, R), /before the first/);
assert.throws(() => P.paintEvery(base, 1, 20, 1, 1, R), /2 or more/);
assert.throws(() => P.paintEvery(base, 1, 20, 3, 3, R), /width/);
assert.throws(() => P.paintBulb(base, 2, 'red'), /color/);
assert.throws(() => P.paintBulb(base, 2, '#FF00001;background:url(x)'), /color/);
assert.deepStrictEqual(P.resize([R, G], 4), [R, G, G, G]);
assert.deepStrictEqual(P.resize([R, G, W], 2), [R, G]);
assert.throws(() => P.resize([R], 0));

// The 30-slot ceiling: a whole house of 300 with every other bulb lit can't fit.
assert(P.slotsNeeded(P.paintEvery(new Array(300).fill(K), 1, 300, 2, 1, W)) > P.MAX_SLOTS);
console.log('painter ok');
