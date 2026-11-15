/* SPDX-License-Identifier: MIT
   Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)

   Named colors and color codes (3.20): read what people type or paste from
   the RGB charts shared in Trimlight groups, and name any color.
   - parse("crimson, forest green") / parse("FF1493") / parse("#ff1493") /
     parse("255, 20, 147") / parse("FF 14 93") / a whole pasted list.
   - nearest("#DC143C") -> {name: "Crimson", exact: true}.
   The names (with their LED notes) come from the app (colornames.py, in
   the catalog), passed in, so there's one list.
   Works as a plain <script> (window.Colors) and as a Node module (tests). */
(function (root) {
  'use strict';

  const key = s => String(s).toLowerCase().replace(/[^a-z]/g, '').replace(/grey/g, 'gray');
  const FILLER = new Set(['and', 'then', 'with', 'or', 'to', 'plus', 'the', 'a', 'of', 'rgb', 'hex', 'color', 'colors', 'colour', 'colours']);
  const up2 = n => n.toString(16).padStart(2, '0').toUpperCase();
  const toHex = (r, g, b) => '#' + up2(r) + up2(g) + up2(b);

  function index(names) {
    const m = new Map();
    for (const c of names || []) m.set(key(c.name), c);
    return m;
  }

  /* text -> {colors: ['#RRGGBB', ...], unknown: ['word', ...]}. A line
     copied from a chart ("Red  FF 00 00  255 0 0") names one color three
     ways, so the same color twice in a row on one line counts once. */
  function parse(text, names) {
    const byKey = index(names), colors = [], unknown = [];
    for (const line of String(text || '').split(/\r?\n/)) {
      const r = parseLine(line, byKey);
      r.colors.forEach((c, i) => { if (i === 0 || c !== r.colors[i - 1]) colors.push(c); });
      unknown.push(...r.unknown);
    }
    return { colors, unknown };
  }

  function parseLine(text, byKey) {
    const toks = String(text || '').match(/#[0-9A-Za-z]+|[0-9A-Za-z]+/g) || [];     // whole runs: "and" stays a word
    const colors = [], unknown = [];
    const isDec = t => /^\d{1,3}$/.test(t) && +t <= 255;
    const isPair = t => /^[0-9a-fA-F]{2}$/.test(t);
    const isWord = t => /^[A-Za-z]+$/.test(t);
    for (let i = 0; i < toks.length;) {
      const t = toks[i];
      // #RGB, #RRGGBB
      if (t[0] === '#') {
        const h = t.slice(1);
        if (/^[0-9a-fA-F]{6}$/.test(h)) colors.push('#' + h.toUpperCase());
        else if (/^[0-9a-fA-F]{3}$/.test(h)) colors.push('#' + h.split('').map(c => c + c).join('').toUpperCase());
        else unknown.push(t);
        i++; continue;
      }
      // RRGGBB without "#" (with a digit, or written in capitals, so a word like "facade" isn't a color)
      if (/^[0-9a-fA-F]{6}$/.test(t) && (/\d/.test(t) || t === t.toUpperCase())) { colors.push('#' + t.toUpperCase()); i++; continue; }
      // Three numbers: "255 20 147" (decimal) or "FF 14 93" (hex pairs, as on the charts)
      const three = toks.slice(i, i + 3);
      if (three.length === 3) {
        const hexy = three.every(isPair) && three.some(x => /[a-fA-F]/.test(x) || /^0\d$/.test(x));
        if (hexy) { colors.push('#' + three.join('').toUpperCase()); i += 3; continue; }
        if (three.every(isDec)) { colors.push(toHex(+three[0], +three[1], +three[2])); i += 3; continue; }
      }
      // Names, longest first: "medium violet red" before "violet red" before "red".
      if (isWord(t)) {
        let hit = null, len = 0;
        for (let n = Math.min(4, toks.length - i); n >= 1; n--) {
          const words = toks.slice(i, i + n);
          if (!words.every(isWord)) continue;
          const c = byKey.get(key(words.join('')));
          if (c) { hit = c; len = n; break; }
        }
        if (hit) { colors.push(hit.hex.toUpperCase()); i += len; continue; }
        if (!FILLER.has(t.toLowerCase())) unknown.push(t);
        i++; continue;
      }
      unknown.push(t); i++;
    }
    return { colors, unknown };
  }

  /* The name of a color, or the closest one (by how different it looks,
     roughly: a weighted RGB distance). */
  function nearest(hex, names) {
    const n = parseInt(String(hex).replace('#', ''), 16);
    if (!(n >= 0) || !names || !names.length) return null;
    const r = n >> 16 & 255, g = n >> 8 & 255, b = n & 255;
    let best = null, bd = Infinity;
    for (const c of names) {
      const m = parseInt(c.hex.slice(1), 16), cr = m >> 16 & 255, cg = m >> 8 & 255, cb = m & 255;
      const rm = (r + cr) / 2, dr = r - cr, dg = g - cg, db = b - cb;
      const d = (2 + rm / 256) * dr * dr + 4 * dg * dg + (2 + (255 - rm) / 256) * db * db;
      if (d < bd) { bd = d; best = c; }
    }
    return best && { name: best.name, hex: best.hex, exact: bd === 0, led: best.led };
  }

  const api = { parse, nearest, key };
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.Colors = api;
})(typeof window !== 'undefined' ? window : globalThis);
