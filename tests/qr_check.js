/* 3.19: the QR encoder. Prints the modules of a few codes as JSON for
   test_share319.py, which decodes them with OpenCV where it's installed,
   and checks the basics here (sizes, finder patterns, quiet zone in the SVG). */
'use strict';
const assert = require('assert');
const Q = require('../eaveluxos/static/qr.js');
const texts = JSON.parse(process.argv[2] || '["HELLO"]');
const out = [];
for (const [t, ecl] of texts) {
  const q = Q.encode(t, ecl);
  assert.strictEqual(q.size, q.version * 4 + 17);
  for (const [x, y] of [[0, 0], [q.size - 7, 0], [0, q.size - 7]]) {     // the three finder squares
    for (let i = 0; i < 7; i++) assert.ok(q.modules[y][x + i] && q.modules[y + i][x] && q.modules[y + 6][x + i] && q.modules[y + i][x + 6]);
    assert.ok(q.modules[y + 3][x + 3] && !q.modules[y + 1][x + 1]);
  }
  out.push({ t, v: q.version, m: q.modules.map(r => r.map(c => (c ? 1 : 0)).join('')) });
}
const svg = Q.svg('ELX1:abc');
assert.ok(svg.startsWith('<svg') && svg.includes('viewBox="0 0 29 29"'), 'version 1 plus a 4-module quiet zone each side');
assert.throws(() => Q.encode('x'.repeat(3000), 'L'), /Too much/);
console.log(JSON.stringify(out));
