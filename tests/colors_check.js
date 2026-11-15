/* 3.20: reading color names and codes (static/colors.js). The names come
   from the app (colornames.py), passed in as JSON by test_colors320.py. */
'use strict';
const assert = require('assert');
const C = require('../eaveluxos/static/colors.js');
const N = JSON.parse(require('fs').readFileSync(process.argv[2], 'utf8'));
const p = t => C.parse(t, N);
const eq = (t, colors, unknown = []) => assert.deepStrictEqual(p(t), { colors, unknown }, t);

eq('crimson', ['#DC143C']);
eq('Forest Green', ['#228B22']);
eq('forestgreen', ['#228B22']);
eq('FOREST-GREEN', ['#228B22']);
eq('medium violet red', ['#C71585']);                  // the longest name wins
eq('light slate grey', ['#778899']);                   // grey = gray
eq('FF1493', ['#FF1493']);
eq('#ff1493', ['#FF1493']);
eq('#f0a', ['#FF00AA']);
eq('255, 20, 147', ['#FF1493']);
eq('rgb(255, 20, 147)', ['#FF1493']);
eq('FF C0 CB', ['#FFC0CB']);                           // hex pairs, as on the charts
eq('80 80 00', ['#808000']);                           // "00": hex pairs
eq('128 128 0', ['#808000']);                          // decimal
eq('Red  FF 00 00  255 0 0\nCrimson DC 14 3C 220 20 60', ['#FF0000', '#DC143C']);   // chart rows: one color each
eq('crimson and forest green, then gold', ['#DC143C', '#228B22', '#FFD700']);
eq('FF0000, 00C000, FFFFFF', ['#FF0000', '#00C000', '#FFFFFF']);
eq('blurple', [], ['blurple']);
eq('facade', [], ['facade']);                          // a word, not a code
eq('#ZZZ', [], ['#ZZZ']);
eq('256 0 0', [], ['256', '0', '0']);
eq('', []);

const n = C.nearest('#DC143C', N);
assert.strictEqual(n.name, 'Crimson'); assert.ok(n.exact);
const w = C.nearest('#E0A060', N);
assert.ok(!w.exact && w.name, 'a near name for any color');
assert.strictEqual(C.nearest('#000001', N).name, 'Black');
assert.strictEqual(C.nearest('nope', N), null);
console.log('colors ok');
