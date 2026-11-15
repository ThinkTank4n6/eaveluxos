/* 4.0.1: where each address goes (nav.js) and merging quick saves
   (merge.js). Runs with Node, so it runs on the GitHub test machines too. */
'use strict';
const assert = require('assert');
const Nav = require('../eaveluxos/static/nav.js');
const Merge = require('../eaveluxos/static/merge.js');

// ---- #12: routing
const views = new Set(['home', 'patterns', 'create', 'schedule', 'alerts', 'music', 'map', 'lights', 'time', 'access', 'app', 'manual']);
const known = v => views.has(v);
const r = (v, last) => Nav.resolve(v, known, last);
assert.deepStrictEqual(Nav.TABS.map(t => t[0]), ['home', 'patterns', 'schedule', 'alerts', 'music', 'map', 'setup']);
assert.deepStrictEqual(r('settings'), { view: 'access', tab: 'setup', replace: true, setup: true });
assert.deepStrictEqual(r('setup'), { view: 'lights', tab: 'setup', replace: true, setup: true });
assert.deepStrictEqual(r('setup', 'app'), { view: 'app', tab: 'setup', replace: true, setup: true }, 'the last Setup section');
assert.deepStrictEqual(r('create'), { view: 'create', tab: 'patterns', replace: false, setup: false });
assert.deepStrictEqual(r('time'), { view: 'time', tab: 'setup', replace: false, setup: true });
assert.deepStrictEqual(r('nonsense'), { view: 'home', tab: 'home', replace: true, setup: false });
assert.deepStrictEqual(r('manual'), { view: 'manual', tab: 'manual', replace: false, setup: false });
for (const [t] of Nav.TABS) if (t !== 'setup') assert.ok(known(t), t + ' has a view');

// ---- #1/#2: merging saves
const base = { _rev: 4, security: { effect: 'security_white', minutes: 5 }, weather: { enabled: false, use: 'either' },
               holidays: { enabled: true, list: [{ key: 'easter' }] }, away: { enabled: true } };
const a = JSON.parse(JSON.stringify(base)); a.security.minutes = 8;
const b = JSON.parse(JSON.stringify(base)); b.weather.enabled = true; delete b.away;
const ca = Merge.diff(base, a), cb = Merge.diff(base, b);
assert.deepStrictEqual(ca, [[['security', 'minutes'], 8]], 'only what changed, part by part');
assert.strictEqual(cb.length, 2);
const latest = JSON.parse(JSON.stringify(base)); latest._rev = 5; latest.holidays.list.push({ key: 'diwali' });  // saved elsewhere meanwhile
const out = Merge.apply(Merge.apply(JSON.parse(JSON.stringify(latest)), ca), cb);
assert.strictEqual(out.security.minutes, 8);
assert.strictEqual(out.security.effect, 'security_white', 'the rest of security kept');
assert.strictEqual(out.weather.enabled, true);
assert.ok(!('away' in out), 'a removed part is removed');
assert.strictEqual(out.holidays.list.length, 2, 'the save that landed first is kept');
assert.deepStrictEqual(Merge.diff(base, JSON.parse(JSON.stringify(base))), [], 'nothing changed');
const lst = JSON.parse(JSON.stringify(base)); lst.holidays.list[0].before = 3;
assert.deepStrictEqual(Merge.diff(base, lst), [[['holidays', 'list'], lst.holidays.list]], 'a list is one value');
const fresh = Merge.apply({}, [[['new', 'deep', 'x'], 1]]);
assert.deepStrictEqual(fresh, { new: { deep: { x: 1 } } });
console.log('review400 ok');
