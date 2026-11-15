// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
// 3.17 house photo tools (static/housefx.js). Run: node tests/housefx_check.js
'use strict';
const assert = require('assert');
const path = require('path');
const H = require(path.join(__dirname, '..', 'eaveluxos', 'static', 'housefx.js'));
const P = require(path.join(__dirname, '..', 'eaveluxos', 'static', 'painter.js'));

const near = (a, b, msg) => assert.ok(Math.abs(a - b) < 1e-6, `${msg}: ${a} vs ${b}`);

// lineBulbs: evenly spaced along the line, in bulb order
{
  const b = H.lineBulbs([[0, 50], [100, 50]], [], 1, 10);
  assert.strictEqual(b.length, 10);
  assert.deepStrictEqual(b.map(p => p.b), [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
  near(b[0].x, 5, 'first bulb half a step in'); near(b[9].x, 95, 'last bulb half a step from the end');
  b.forEach(p => near(p.y, 50, 'on the line'));
}
// counting down runs the other way
{
  const b = H.lineBulbs([[0, 0], [10, 0]], [], 20, 11);
  assert.deepStrictEqual(b.map(p => p.b), [20, 19, 18, 17, 16, 15, 14, 13, 12, 11]);
  assert.ok(b[0].x < b[9].x, 'bulb 20 sits at the first point');
}
// wire-only stretches get no bulbs
{
  const b = H.lineBulbs([[0, 0], [10, 0], [90, 0], [100, 0]], [1], 1, 4);
  assert.ok(b.every(p => p.x <= 10 || p.x >= 90), 'nothing on the wire-only stretch');
  assert.strictEqual(b.filter(p => p.x <= 10).length, 2);
}
// bent lines follow the bends
{
  const b = H.lineBulbs([[0, 0], [10, 0], [10, 10]], [], 1, 4);
  assert.ok(b.slice(0, 2).every(p => p.y === 0) && b.slice(2).every(p => p.x === 10));
}
// bad input: nothing, not an error
assert.deepStrictEqual(H.lineBulbs([[0, 0]], [], 1, 5), []);
assert.deepStrictEqual(H.lineBulbs([[0, 0], [0, 0]], [], 1, 5), []);
assert.deepStrictEqual(H.lineBulbs([[0, 0], [9, 0]], [], 0, 5), []);

// sideBulbs only counts lines with bulbs; nearest finds within a radius
{
  const lines = [{ points: [[0, 0], [10, 0]], wire: [], bulbs: { from: 1, to: 5 } }, { points: [[0, 9], [9, 9]], wire: [] }];
  const all = H.sideBulbs(lines);
  assert.strictEqual(all.length, 5);
  assert.strictEqual(H.nearest(all, 1, 0.5, 3).b, 1);
  assert.strictEqual(H.nearest(all, 50, 50, 3), null);
}

// colorsAt: static patterns repeat; zoned-off bulbs are off and skipped by motion
{
  const def = { segs: [{ c: '#FF0000', n: 2 }, { c: 'off', n: 1 }, { c: '#0000FF', n: 1 }], mode: 0, speed: 100, brightness: 255 };
  const c = H.colorsAt(def, 8, 0);
  assert.deepStrictEqual(c.map(x => x.off ? 'off' : x.c.join(',')), ['255,0,0', '255,0,0', 'off', '0,0,255', '255,0,0', '255,0,0', 'off', '0,0,255']);
  near(c[0].a, 1, 'full brightness');
  const moving = H.colorsAt({ ...def, mode: 1, speed: 255 }, 8, 1);
  assert.deepStrictEqual(moving.map(x => x.off), c.map(x => x.off), 'zoned-off bulbs stay put while the rest move');
  assert.ok(H.colorsAt({ segs: [], mode: 0 }, 3, 0).every(x => x.off), 'no colors: dark');
}

// dim and scenes
assert.strictEqual(H.dim('#FF8040', 50), '#804020');
assert.strictEqual(H.dim('#FFFFFF', 100), '#FFFFFF');
assert.strictEqual(H.dim('off', 50), 'off');
{
  const canvas = H.sceneCanvas(20, [{ color: '#FFC58A', level: 100, bulbs: [2, 3, 4] }, { color: '#FFFFFF', level: 50, bulbs: [10, 4] }]);
  assert.strictEqual(canvas.length, 20);
  assert.deepStrictEqual(canvas.slice(0, 5), ['off', '#FFC58A', '#FFC58A', '#808080', 'off']);
  assert.strictEqual(canvas[9], '#808080');
  const segs = P.compress(canvas);
  assert.strictEqual(segs.reduce((n, s) => n + s.n, 0), 20, 'covers every bulb, so it never repeats');
  assert.strictEqual(segs.length, 6);
  assert.throws(() => H.sceneCanvas(0, []), /bulbs/);
  // a dark stretch over 90 bulbs takes two slots
  assert.strictEqual(P.compress(H.sceneCanvas(200, [{ color: '#FFFFFF', bulbs: [1] }])).length, 4);
}
assert.deepStrictEqual(H.around(10, 3, 100), [9, 10, 11]);
assert.deepStrictEqual(H.around(1, 5, 100), [1, 2, 3]);
assert.deepStrictEqual(H.around(100, 3, 100), [99, 100]);
assert.deepStrictEqual(H.around(5, 1, 100), [5]);

console.log('housefx ok');
