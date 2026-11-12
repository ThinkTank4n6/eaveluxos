/* SPDX-License-Identifier: MIT
   Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
   The idea of painting a pattern bulb by bulb, by range and by increment,
   then compressing it back into the controller's color runs, comes from
   Trimlight Home Studio, Copyright (c) 2026 Thomas Kay and contributors,
   MIT License (see LICENSE, "Third-party notices").

   Bulb painter: a pattern as one color per bulb (a "canvas"), the painting
   tools, and the conversion back to color runs ("segments" {c, n}) that the
   controller stores: at most MAX_SLOTS runs of at most PER_SLOT bulbs.
   'off' means zoned off (dark, skipped by any movement).
   Works as a plain <script> (window.Painter) and as a Node module (tests). */
(function (root) {
  'use strict';

  const MAX_SLOTS = 30, PER_SLOT = 90, MAX_BULBS = 10000;
  const COLOR = /^(#[0-9A-F]{6}|off)$/;

  function checkColor(c) {
    const v = String(c).toUpperCase() === 'OFF' ? 'off' : String(c).toUpperCase();
    if (!COLOR.test(v)) throw new Error('Choose a color.');
    return v;
  }

  /* Segments -> one color per bulb. With `length`, the sequence repeats (or is
     cut) to exactly that many bulbs, as it does along the roofline. */
  function expand(segs, length) {
    const unit = [];
    for (const s of segs) for (let k = 0; k < s.n; k++) unit.push(s.c);
    if (length === undefined) return unit;
    if (!unit.length) return new Array(length).fill('#000000');
    return Array.from({ length }, (_, i) => unit[i % unit.length]);
  }

  /* One color per bulb -> runs of equal colors, each split at PER_SLOT bulbs. */
  function compress(canvas) {
    const segs = [];
    for (const c of canvas) {
      const last = segs[segs.length - 1];
      if (last && last.c === c && last.n < PER_SLOT) last.n++;
      else segs.push({ c, n: 1 });
    }
    return segs;
  }
  const slotsNeeded = canvas => compress(canvas).length;

  /* Bulb numbers are 1-based, like the House map's bulb finder. */
  function clampRange(canvas, from, to) {
    const a = Math.round(+from), b = Math.round(+to);
    if (!Number.isFinite(a) || !Number.isFinite(b)) throw new Error('Enter bulb numbers.');
    if (a < 1 || b > canvas.length) throw new Error(`Bulbs go from 1 to ${canvas.length}.`);
    if (b < a) throw new Error('The last bulb can’t be before the first.');
    return [a, b];
  }
  function paintBulb(canvas, bulb, color) { return paintRange(canvas, bulb, bulb, color); }
  function paintRange(canvas, from, to, color) {
    const [a, b] = clampRange(canvas, from, to), c = checkColor(color), out = canvas.slice();
    for (let i = a; i <= b; i++) out[i - 1] = c;
    return out;
  }
  /* Every `step` bulbs from `from` to `to`, `width` bulbs at a time:
     from 2 to 20, every 4, width 2 paints 2-3, 6-7, 10-11, 14-15, 18-19. */
  function paintEvery(canvas, from, to, step, width, color) {
    const [a, b] = clampRange(canvas, from, to), c = checkColor(color);
    const s = Math.round(+step), w = Math.round(+width || 1);
    if (!(s >= 2)) throw new Error('“Every” needs 2 or more bulbs (1 would paint the whole range).');
    if (!(w >= 1 && w < s)) throw new Error('The width must be at least 1 and smaller than “every”.');
    const out = canvas.slice();
    for (let start = a; start <= b; start += s) for (let i = start; i < start + w && i <= b; i++) out[i - 1] = c;
    return out;
  }
  function fill(canvas, color) { return new Array(canvas.length).fill(checkColor(color)); }

  /* Grow or shrink one repeat of a sequence (new bulbs take the last color). */
  function resize(canvas, length) {
    const n = Math.round(+length);
    if (!(n >= 1 && n <= MAX_SLOTS * PER_SLOT)) throw new Error(`A repeat can be 1 to ${MAX_SLOTS * PER_SLOT} bulbs.`);
    const out = canvas.slice(0, n);
    while (out.length < n) out.push(canvas[canvas.length - 1] || '#000000');
    return out;
  }

  const api = { MAX_SLOTS, PER_SLOT, MAX_BULBS, expand, compress, slotsNeeded, paintBulb, paintRange, paintEvery, fill, resize, checkColor };
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.Painter = api;
})(typeof window !== 'undefined' ? window : globalThis);
