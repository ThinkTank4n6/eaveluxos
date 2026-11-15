/* 3.18.2 review #3: mood follow reports by the clock, not by timer ticks,
   so a background tab (timers slowed to once a second, or once a minute)
   still reports well within the 3 minutes before the lights go back. */
'use strict';
const assert = require('assert');
const M = require('../eaveluxos/static/mood.js');

function loud(win) { for (let i = 0; i < 5; i++) win.add(0.12, i % 2 ? 0.05 : 0.001, 100); }

// A normal tab: a sample every 100 ms, a report every 10 seconds.
let r = new M.Reporter(), w = new M.Window(), sent = [];
for (let t = 0; t <= 30000; t += 100) { w.add(0.12, (t / 100) % 3 ? 0.001 : 0.05, 100); const lv = r.step(t, w); if (lv) sent.push(t); }
assert.deepStrictEqual(sent, [10000, 20000, 30000], 'every 10 seconds by the clock');

// A background tab: one sample a minute. Counting 100 ticks would report
// once every 100 minutes; by the clock it's every sample.
r = new M.Reporter(); w = new M.Window(); sent = [];
for (let t = 0; t <= 5 * 60000; t += 60000) { loud(w); if (r.step(t, w)) sent.push(t); }
assert.strictEqual(sent.length, 5, 'a report for each minute: ' + sent);
assert.ok(sent.every((t, i) => i === 0 || t - sent[i - 1] < 3 * 60000), 'never 3 minutes without word');

// A short pause between songs isn't the end; 30 seconds of quiet is.
r = new M.Reporter(); w = new M.Window(); const lv = [];
r.step(0, w);
for (let t = 10000; t <= 60000; t += 10000) { w.add(0.001, 0, 100); lv.push(r.step(t, w)); }
assert.deepStrictEqual(lv, [null, null, 'quiet', 'quiet', 'quiet', 'quiet'], 'quiet only after 30 seconds');

// Slow background ticks count their real length toward the 30 seconds.
r = new M.Reporter(); w = new M.Window();
r.step(0, w); w.add(0.001, 0, 250);
assert.strictEqual(r.step(60000, w), 'quiet', 'a minute of quiet is quiet, even in one slow tick');
console.log('review318 ok');
