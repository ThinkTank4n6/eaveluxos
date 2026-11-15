/* SPDX-License-Identifier: MIT
   Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)

   House photo tools (3.17): where each bulb sits on a traced roofline, the
   animated preview's colors (shared by Create's strip preview and the house
   photo), and architectural scenes (lit groups of bulbs, the rest dark).
   Works as a plain <script> (window.HouseFX) and as a Node module (tests). */
(function (root) {
  'use strict';

  /* Bulbs `from`..`to` (1-based; `to` below `from` runs the other way),
     spread evenly along a traced line, skipping "wire only" stretches.
     points: [[x%, y%], ...]; wire: indexes of segments without bulbs.
     Returns [{b, x, y}] in the photo's percent coordinates. */
  function lineBulbs(points, wire, from, to) {
    const a = Math.round(+from), z = Math.round(+to);
    if (!(a >= 1 && z >= 1) || !Array.isArray(points) || points.length < 2) return [];
    const skip = new Set(wire || []), segs = [];
    let total = 0;
    for (let i = 0; i < points.length - 1; i++) {
      if (skip.has(i)) continue;
      const [x1, y1] = points[i], [x2, y2] = points[i + 1], len = Math.hypot(x2 - x1, y2 - y1);
      if (len > 0) { segs.push({ x1, y1, x2, y2, len, at: total }); total += len; }
    }
    const n = Math.abs(z - a) + 1, step = z >= a ? 1 : -1, out = [];
    if (!total) return out;
    let s = 0;
    for (let k = 0; k < n; k++) {
      const d = (k + 0.5) / n * total;
      while (s < segs.length - 1 && segs[s].at + segs[s].len < d) s++;
      const g = segs[s], f = Math.min(1, Math.max(0, (d - g.at) / g.len));
      out.push({ b: a + k * step, x: g.x1 + (g.x2 - g.x1) * f, y: g.y1 + (g.y2 - g.y1) * f });
    }
    return out;
  }

  /* Every positioned bulb on one side's lines (lines with a bulb range). */
  function sideBulbs(lines) {
    const out = [];
    for (const ln of lines || []) if (ln.bulbs) out.push(...lineBulbs(ln.points, ln.wire, ln.bulbs.from, ln.bulbs.to));
    return out;
  }

  /* The positioned bulb nearest (x%, y%), within `max` percent. */
  function nearest(bulbs, x, y, max) {
    let best = null, bd = max === undefined ? Infinity : max;
    for (const p of bulbs) { const d = Math.hypot(p.x - x, p.y - y); if (d <= bd) { bd = d; best = p; } }
    return best;
  }

  const rgb = h => { const n = parseInt(String(h).slice(1), 16); return [n >> 16, n >> 8 & 255, n & 255]; };

  /* An approximation of the controller's custom motions: the color and
     brightness (0-1) of bulbs 0..N-1 at time t seconds. def: {segs: [{c, n}]
     ('off' = zoned off), mode, speed, brightness}. Zoned-off bulbs get
     {off: true}; the pattern repeats over N bulbs like on the house. */
  function colorsAt(def, N, t) {
    const segs = def.segs || [], out = new Array(N);
    const layout = []; segs.forEach(s => { for (let k = 0; k < s.n; k++) layout.push(s.c === 'off'); });
    const P = []; segs.forEach(s => { if (s.c !== 'off') for (let k = 0; k < s.n; k++) P.push(rgb(s.c)); });
    const LA = layout.length || 1, L = P.length || 1, mode = def.mode || 0;
    const rate = 2 + (def.speed ?? 100) / 255 * 28, pos = t * rate;
    const bright = 0.25 + 0.75 * (def.brightness ?? 200) / 255, half = (N - 1) / 2;
    const idx = j => P[((j % L) + L) % L];
    let active = -1;
    for (let i = 0; i < N; i++) {
      const zoned = layout[i % LA];
      if (!zoned) active++;
      if (zoned || !P.length) { out[i] = { c: [0, 0, 0], a: 0, off: true }; continue; }
      const ai = active, d = Math.abs(i - half), fl = Math.floor(pos);
      let c = idx(ai), a = 1;
      if (mode === 1) c = idx(ai - fl); else if (mode === 2) c = idx(ai + fl);
      else if (mode === 3) c = idx(Math.round(d) - fl); else if (mode === 4) c = idx(Math.round(d) + fl);
      else if (mode === 5) { const r = Math.sin(i * 12.9898 + Math.floor(pos / 3) * 78.233) * 43758.5453; a = (r - Math.floor(r)) > .8 ? 1 : .18; }
      else if (mode === 6) a = .12 + .88 * (.5 - .5 * Math.cos(2 * Math.PI * t * rate / 40));
      else if (mode >= 7 && mode <= 10) {
        const span = mode <= 8 ? N + 14 : half + 14, head = pos % span;
        const x = mode === 7 ? i : mode === 8 ? N - 1 - i : mode === 9 ? d : half - d;
        const dist = head - x; a = dist >= 0 && dist < 14 ? 1 - dist / 14 : .05;
      } else if (mode >= 11 && mode <= 14) {
        const x = mode === 11 ? i : mode === 12 ? -i : mode === 13 ? d : -d;
        a = .15 + .85 * (.5 + .5 * Math.sin(2 * Math.PI * (x - pos) / 22));
      } else if (mode === 15) a = Math.floor(t * rate / 3) % 2 ? 1 : .04;
      else if (mode === 16) {
        const cols = segs.filter(s => s.c !== 'off').map(s => rgb(s.c)), k = (t * rate / 20) % cols.length, j = Math.floor(k), f = k - j;
        const A = cols[j], B = cols[(j + 1) % cols.length]; c = [0, 1, 2].map(m => A[m] + (B[m] - A[m]) * f);
      }
      out[i] = { c, a: a * bright, off: false };
    }
    return out;
  }

  /* A color at `pct` percent of its brightness: how one pattern can hold a
     dim group and a bright group (the controller has one brightness). */
  function dim(hex, pct) {
    if (hex === 'off') return 'off';
    const k = Math.max(0, Math.min(100, +pct)) / 100;
    return '#' + rgb(hex).map(v => Math.round(v * k).toString(16).padStart(2, '0')).join('').toUpperCase();
  }

  /* An architectural scene: every bulb dark ('off', skipped by motion) except
     the groups' bulbs, each group in its color at its level. Later groups win
     where they overlap. Returns one color per bulb (a painter canvas). */
  function sceneCanvas(total, groups) {
    const T = Math.round(+total);
    if (!(T >= 1 && T <= 10000)) throw new Error('The number of bulbs isn’t known yet. Open Setup › Lights & controller once, then try again.');
    const out = new Array(T).fill('off');
    for (const g of groups || []) {
      const c = dim(g.color, g.level ?? 100);
      for (const b of g.bulbs || []) if (b >= 1 && b <= T) out[b - 1] = c === '#000000' ? 'off' : c;
    }
    return out;
  }

  /* Bulbs centered on `b`: width 3 -> b-1, b, b+1. */
  function around(b, width, total) {
    const w = Math.max(1, Math.round(+width) || 1), lo = b - Math.floor((w - 1) / 2), out = [];
    for (let i = lo; i < lo + w; i++) if (i >= 1 && i <= total) out.push(i);
    return out;
  }

  /* How many bulbs each group really lights (a later group wins a bulb two
     groups share), for the group buttons (3.17.1). */
  function sceneOwners(total, groups) {
    const owner = new Map();
    (groups || []).forEach((g, i) => (g.bulbs || []).forEach(b => { if (b >= 1 && b <= total) owner.set(b, i); }));
    const out = (groups || []).map(() => 0);
    for (const i of owner.values()) out[i]++;
    return out;
  }

  /* Typed bulb numbers, the keyboard way to build a scene: "10-12, 40, 55-53"
     -> [10, 11, 12, 40, 53, 54, 55] (3.17.1). */
  function parseBulbs(text, total) {
    const out = new Set();
    for (const part of String(text || '').split(/[,\s]+/).filter(Boolean)) {
      const m = part.match(/^(\d+)(?:-(\d+))?$/);
      if (!m) throw new Error(`“${part}” isn’t a bulb number or a range like 10-12.`);
      let a = +m[1], z = m[2] ? +m[2] : a;
      if (a > z) [a, z] = [z, a];
      if (a < 1 || z > total) throw new Error(`Bulbs go from 1 to ${total}.`);
      if (z - a > 10000) throw new Error('That range is too long.');
      for (let b = a; b <= z; b++) out.add(b);
    }
    return [...out].sort((x, y) => x - y);
  }

  /* Bulbs a scene was made for: its runs add up to the whole address space. */
  const sceneTotal = e => (e && e.counts ? e.counts.reduce((n, c) => n + (+c || 0), 0) : 0);

  const api = { lineBulbs, sideBulbs, nearest, colorsAt, dim, sceneCanvas, around, sceneOwners, parseBulbs, sceneTotal };
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.HouseFX = api;
})(typeof window !== 'undefined' ? window : globalThis);
