/* SPDX-License-Identifier: MIT
   Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)

   Camera calibration (4.16): find where every bulb is from a phone's camera.

   Lighting the bulbs one at a time would take a hundred frames or more.
   Instead each bulb's number is spelled out in binary over a few frames:
   in frame b, bulb n is lit when bit b of (n - 1) is 1. That frame is the
   same short pattern over and over (2^b bulbs dark, then 2^b lit), which a
   controller repeats along its lights, so it fits the controller's 30 color
   blocks however many bulbs there are. Each frame is also shown the other
   way round, and the camera compares the two, which works whatever the
   brightness. Plus a dark frame and an all-lit one. For 106 bulbs: 16
   frames.

   Each pixel that lights up then reads its bulb's number from the frames;
   pixels with the same number that touch are one bulb, its middle is where
   the bulb is. Bulbs in a row become roofline lines with each found bulb
   pinned (4.12), and missing ones spread evenly between.

   Plain logic, tested with Node. Works as a plain <script> (window.Calib)
   and as a Node module (tests). */
(function (root) {
  'use strict';

  const WHITE = '#FFFFFF', BLACK = '#000000';

  const bitsFor = n => Math.max(1, Math.ceil(Math.log2(Math.max(2, n))));

  /* One repeating pattern: runs of [color, count], each count split to at most perSlot. */
  function pattern(runs, perSlot, label) {
    const colors = [], counts = [];
    for (const [c, n] of runs) for (let left = n; left > 0; left -= perSlot) { colors.push(c); counts.push(Math.min(perSlot, left)); }
    return { label, colors, counts, custom_mode: 0, speed: 0, brightness: 255 };
  }

  /* The frames to show, in order: [{kind: 'dark'|'full'|'bit'|'inv', bit, effect}]. */
  function frames(total, perSlot = 90) {
    const B = bitsFor(total), out = [{ kind: 'dark', effect: pattern([[BLACK, 1]], perSlot, 'Calibration: dark') },
      { kind: 'full', effect: pattern([[WHITE, 1]], perSlot, 'Calibration: all') }];
    for (let b = 0; b < B; b++) {
      const k = 1 << b;
      out.push({ kind: 'bit', bit: b, effect: pattern([[BLACK, k], [WHITE, k]], perSlot, `Calibration ${2 * b + 1} of ${2 * B}`) });
      out.push({ kind: 'inv', bit: b, effect: pattern([[WHITE, k], [BLACK, k]], perSlot, `Calibration ${2 * b + 2} of ${2 * B}`) });
    }
    return out;
  }

  /* What the lights look like for one frame (for tests and a preview): is bulb n lit? */
  function lit(frame, n) {
    if (frame.kind === 'dark') return false;
    if (frame.kind === 'full') return true;
    const on = ((n - 1) >> frame.bit) & 1;
    return frame.kind === 'bit' ? on === 1 : on === 0;
  }

  /* Gray levels (0-255) of a canvas's RGBA pixels. */
  function gray(rgba) {
    const g = new Uint8Array(rgba.length / 4);
    for (let i = 0; i < g.length; i++) g[i] = (rgba[4 * i] * 77 + rgba[4 * i + 1] * 150 + rgba[4 * i + 2] * 29) >> 8;
    return g;
  }

  /* An Otsu threshold over the values above `floor`. */
  function otsu(values, floor) {
    const hist = new Float64Array(256);
    let n = 0;
    for (const v of values) if (v > floor) { hist[Math.min(255, v)]++; n++; }
    if (n < 4) return 255;
    let sum = 0;
    for (let i = 0; i < 256; i++) sum += i * hist[i];
    let sB = 0, wB = 0, best = 0, thr = floor + 1;
    for (let i = 0; i < 256; i++) {
      wB += hist[i]; if (!wB) continue;
      const wF = n - wB; if (!wF) break;
      sB += i * hist[i];
      const mB = sB / wB, mF = (sum - sB) / wF, v = wB * wF * (mB - mF) * (mB - mF);
      if (v > best) { best = v; thr = i; }
    }
    return thr;
  }

  /* shots: {dark, full, bits: [[pattern, inverse], ...]} of gray arrays w x h.
     Returns {bulbs: [{bulb, x, y (percent), size, conf}], lit: pixels that
     lit up, unsure: share of them that didn't read clearly, repeats}. */
  function decode(shots, w, h, total, opts = {}) {
    const B = shots.bits.length, N = w * h;
    const diff = new Int16Array(N);
    for (let i = 0; i < N; i++) diff[i] = shots.full[i] - shots.dark[i];
    const thr = Math.max(opts.minDiff ?? 24, otsu(diff, opts.minDiff ?? 24) * 0.6);
    const code = new Int32Array(N).fill(-1);
    let lit = 0, unsure = 0, neither = 0;
    for (let i = 0; i < N; i++) {
      const d = diff[i];
      if (d < thr) continue;
      lit++;
      let c = 0, weak = false, both = 0;
      for (let b = 0; b < B; b++) {
        const p = shots.bits[b][0][i], q = shots.bits[b][1][i], s = p - q;
        if (Math.abs(s) < 0.25 * d) weak = true;
        if (p - shots.dark[i] < 0.3 * d && q - shots.dark[i] < 0.3 * d) both++;
        if (s > 0) c |= 1 << b;
      }
      if (both) neither++;
      if (weak) { unsure++; continue; }
      if (c + 1 > total) continue;
      code[i] = c;
    }
    // Pixels that touch and read the same number: one bulb (flood fill)
    const seen = new Uint8Array(N), comps = new Map();
    const stack = [];
    for (let i = 0; i < N; i++) {
      if (code[i] < 0 || seen[i]) continue;
      const c = code[i];
      let area = 0, sx = 0, sy = 0, sw = 0;
      stack.push(i); seen[i] = 1;
      while (stack.length) {
        const j = stack.pop(), x = j % w, y = (j / w) | 0, wt = Math.max(1, diff[j]);
        area++; sx += x * wt; sy += y * wt; sw += wt;
        for (const k of [x > 0 ? j - 1 : -1, x < w - 1 ? j + 1 : -1, y > 0 ? j - w : -1, y < h - 1 ? j + w : -1]) {
          if (k >= 0 && !seen[k] && code[k] === c) { seen[k] = 1; stack.push(k); }
        }
      }
      if (!comps.has(c)) comps.set(c, []);
      comps.get(c).push({ area, x: sx / sw, y: sy / sw });
    }
    const minArea = opts.minArea ?? 2, bulbs = [];
    for (const [c, list] of comps) {
      list.sort((a, b) => b.area - a.area);
      const top = list[0];
      if (top.area < minArea) continue;
      // The same number in two places far apart: a mirrored run (two ports with the same bulb numbers)
      for (const k of list) {
        if (k !== top && (k.area < Math.max(minArea, top.area * 0.5) || Math.hypot(k.x - top.x, k.y - top.y) < w * 0.03)) continue;
        bulbs.push({ bulb: c + 1, x: Math.round(k.x / (w - 1) * 1000) / 10, y: Math.round(k.y / (h - 1) * 1000) / 10,
          size: k.area, conf: Math.min(1, k.area / Math.max(top.area, 1)) });
      }
    }
    bulbs.sort((a, b) => a.bulb - b.bulb || a.x - b.x);
    return { bulbs, lit, unsure: lit ? unsure / lit : 0, repeats: lit ? 1 - neither / lit > 0.6 : true, threshold: thr };
  }

  /* Bulbs found -> roofline lines: bulbs in number order that are close
     together make a line; each line runs from its first bulb to its last,
     with every found bulb pinned where it was seen (missing ones spread out
     between). aspect: height / width of the photo. */
  function toSections(bulbs, aspect = 0.5625, opts = {}) {
    const maxGap = opts.maxGap ?? 4, maxDist = opts.maxDist ?? 7, chains = [];
    const dist = (a, b) => Math.hypot(a.x - b.x, (a.y - b.y) * aspect);
    for (const d of [...bulbs].sort((a, b) => a.bulb - b.bulb)) {
      let best = null, bd = Infinity;
      for (const c of chains) {
        const last = c[c.length - 1], gap = d.bulb - last.bulb, dd = dist(last, d);
        if (gap >= 1 && gap <= maxGap && dd <= maxDist * gap && dd < bd) { best = c; bd = dd; }
      }
      if (best) best.push(d); else chains.push([d]);
    }
    const RL = root.Roofline || (typeof require === 'function' ? require('./roofline.js') : null);
    const simplify = RL ? RL.simplify : (p => p);
    const out = [], dropped = [];
    let n = 0;
    for (const c of chains) {
      if (c.length < 3) { dropped.push(...c.map(d => d.bulb)); continue; }
      // At most 200 pins and 100 points on one line: longer ones are split
      for (let i = 0; i < c.length; i += 200) {
        const part = c.slice(i, i + 200);
        if (part.length < 3) continue;
        let pts = part.map(d => [d.x, d.y]), tol = 0.4;
        let s = simplify(pts, tol);
        while (s.length > 100) { tol *= 1.6; s = simplify(pts, tol); }
        if (s.length < 2) s = [pts[0], pts[pts.length - 1]];
        out.push({ id: `cal${Date.now().toString(36)}${n++}`, kind: 'edge', points: s.map(p => [Math.round(p[0] * 10) / 10, Math.round(p[1] * 10) / 10]),
          bulbs: { from: part[0].bulb, to: part[part.length - 1].bulb }, pins: part.map(d => [d.bulb, d.x, d.y]) });
      }
    }
    // Review #2: an elevation holds 40 lines; say how many didn't fit rather than drop them quietly
    return { sections: out.slice(0, 40), dropped, cut: Math.max(0, out.length - 40) };
  }

  const api = { frames, lit, gray, otsu, decode, toSections, bitsFor };
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.Calib = api;
})(typeof window !== 'undefined' ? window : globalThis);
