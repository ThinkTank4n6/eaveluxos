// SPDX-License-Identifier: MIT
// 3.17.1 review checks for the browser modules. Run: node tests/review317_check.js
'use strict';
const assert = require('assert');
const path = require('path');
const P = require(path.join(__dirname, '..', 'eaveluxos', 'static', 'painter.js'));
const H = require(path.join(__dirname, '..', 'eaveluxos', 'static', 'housefx.js'));

// #2 slots at 60 bulbs per slot: a dark gap of 75 takes one slot at 90, two at 60
{
  const groups = [];
  for (let i = 0; i < 14; i++) groups.push({ color: '#FFC58A', bulbs: [i * 78 + 76, i * 78 + 77, i * 78 + 78] });
  const canvas = H.sceneCanvas(14 * 78 + 10, groups);
  assert.strictEqual(P.slotsAt(canvas, 90), 29);
  assert.ok(P.slotsAt(canvas, 60) > 30, 'too many at 60');
  assert.strictEqual(P.slotsAt(canvas), P.slotsNeeded(canvas), 'no limit given: the usual 90');
}
// #9 a bulb two groups share counts for the later group only
assert.deepStrictEqual(H.sceneOwners(20, [{ bulbs: [1, 2, 3] }, { bulbs: [3, 4] }]), [2, 2]);
assert.deepStrictEqual(H.sceneOwners(5, [{ bulbs: [9] }]), [0], 'past the last bulb: not counted');

// #11 typed bulb numbers
assert.deepStrictEqual(H.parseBulbs('10-12, 40 55-53', 100), [10, 11, 12, 40, 53, 54, 55]);
assert.deepStrictEqual(H.parseBulbs('  ', 100), []);
assert.throws(() => H.parseBulbs('10-200', 100), /1 to 100/);
assert.throws(() => H.parseBulbs('ten', 100), /isn/);
assert.throws(() => H.parseBulbs('0', 100), /1 to 100/);

// #7 a scene's bulb count is what it was made for
assert.strictEqual(H.sceneTotal({ counts: [9, 3, 126] }), 138);
assert.strictEqual(H.sceneTotal({}), 0);
console.log('review317 ok');
