/* SPDX-License-Identifier: MIT
   Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
   Roofline detection, segment helpers and the flat diagram are adapted from
   Trimlight Home Studio, Copyright (c) 2026 Thomas Kay and contributors,
   MIT License (see LICENSE, "Third-party notices").

   House rooflines for the House map: an outline suggestion from a photo
   (computed in the browser, so photos never leave this app), helpers for
   "wire only" segments (stretches of wire without bulbs), and a flat
   diagram of every side as SVG.

   A roofline section is { id, kind: 'edge'|'ridge', points: [[x,y]...],
   wire: [segment indexes] } with x and y in percent of the photo (0-100).
   Works as a plain <script> (window.Roofline) and as a Node module (tests). */
(function (root) {
  'use strict';

  const DEFAULT_SIDES = [
    { id: 'front', name: 'Front' }, { id: 'right', name: 'Right side' }, { id: 'back', name: 'Back' },
    { id: 'left', name: 'Left side' }, { id: 'shed', name: 'Shed' },
  ];
  const LIMITS = { sections: 40, points: 100 };

  /* Ramer-Douglas-Peucker: drop points that lie within `tolerance` of a line. */
  function simplify(points, tolerance = 1.5) {
    if (points.length < 3) return points;
    const a = points[0], b = points[points.length - 1], dx = b[0] - a[0], dy = b[1] - a[1], len = dx * dx + dy * dy;
    let max = 0, index = 0;
    for (let i = 1; i < points.length - 1; i++) {
      const p = points[i];
      const t = len ? Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / len)) : 0;
      const d = Math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy);
      if (d > max) { max = d; index = i; }
    }
    if (max <= tolerance) return [a, b];
    return [...simplify(points.slice(0, index + 1), tolerance).slice(0, -1), ...simplify(points.slice(index), tolerance)];
  }

  /* Suggest the outer roofline in an ImageData-like {data, width, height}
     (at most 640x640). Looks for the strongest horizontal light/dark edge
     between `top` and `bottom` percent of the height, then follows it from
     left to right, penalizing jumps to unrelated edges (dynamic programming).
     Returns {points (percent), quality: 'strong'|'review'|'low', message}. */
  function detectRoofline(img, opts = {}) {
    const { data, width: w, height: h } = img;
    const top = opts.top ?? 8, bottom = opts.bottom ?? 78;
    if (!Number.isInteger(w) || !Number.isInteger(h) || w < 20 || h < 20 || w > 640 || h > 640 || data.length !== w * h * 4)
      throw new Error('Unsupported detection image.');
    if (!Number.isFinite(top) || !Number.isFinite(bottom) || top < 0 || bottom > 100 || bottom - top < 10)
      throw new Error('Choose a search band at least 10% tall.');
    const y0 = Math.max(2, Math.round(h * top / 100)), y1 = Math.min(h - 3, Math.round(h * bottom / 100)), n = y1 - y0 + 1;
    const gray = new Float32Array(w * h);
    for (let i = 0; i < gray.length; i++) gray[i] = 0.299 * data[i * 4] + 0.587 * data[i * 4 + 1] + 0.114 * data[i * 4 + 2];
    // Vertical contrast: rows above vs rows below each pixel, 3 pixels wide.
    const edge = new Float32Array(w * n);
    let peak = 0;
    for (let x = 2; x < w - 2; x++) {
      for (let y = y0; y <= y1; y++) {
        let above = 0, below = 0;
        for (let k = -1; k <= 1; k++) {
          above += gray[(y - 2) * w + x + k] + gray[(y - 1) * w + x + k];
          below += gray[(y + 1) * w + x + k] + gray[(y + 2) * w + x + k];
        }
        const strength = Math.abs(below - above) / 6;
        edge[x * n + y - y0] = strength;
        if (strength > peak) peak = strength;
      }
    }
    if (peak < 18) return { points: [], quality: 'low', message: 'No clear roof edge found. Try a daylight photo, or trace it by hand.' };
    // Best left-to-right path: each column may move at most 3 rows, each row of
    // movement costs 7, and lower rows cost slightly more (roofs are on top).
    let prev = new Float32Array(n);
    const parents = new Int16Array(w * n);
    for (let x = 2; x < w - 2; x++) {
      const next = new Float32Array(n);
      for (let j = 0; j < n; j++) {
        let best = -Infinity, from = j;
        for (let d = -3; d <= 3; d++) {
          const k = j + d;
          if (k < 0 || k >= n) continue;
          const score = prev[k] - Math.abs(d) * 7;
          if (score > best) { best = score; from = k; }
        }
        next[j] = best + edge[x * n + j] - (j / n) * 0.7;
        parents[x * n + j] = from;
      }
      prev = next;
    }
    let j = 0;
    for (let k = 1; k < n; k++) if (prev[k] > prev[j]) j = k;
    const points = [];
    let support = 0;
    for (let x = w - 3; x >= 2; x--) {
      if (edge[x * n + j] > Math.max(16, peak * 0.13)) support++;
      points.push([x, y0 + j]);
      j = parents[x * n + j];
    }
    points.reverse();
    const ratio = support / points.length;
    if (ratio < 0.3) return { points: [], quality: 'low', message: 'The edge is too broken up to suggest. Narrow the search band, or trace it by hand.' };
    let reduced = simplify(points, 2);
    for (let tol = 3; reduced.length > 60; tol++) reduced = simplify(points, tol);
    return {
      points: reduced.map(([x, y]) => [round1(x / (w - 1) * 100), round1(y / (h - 1) * 100)]),
      quality: ratio > 0.7 ? 'strong' : 'review',
      message: 'Suggested outer roofline. Check it around trees, gutters and peaks; add ridges and hidden edges by hand.',
    };
  }

  const round1 = v => Math.round(v * 10) / 10;

  /* The segments of a section: segment i joins points i and i+1. */
  function roofSegments(line) {
    const wire = line.wire || [];
    return line.points.slice(1).map((b, i) => ({ a: line.points[i], b, index: i, lit: !wire.includes(i) }));
  }
  /* Keep "wire only" marks on the right segments when a point is inserted at `at`. */
  function insertWirePoint(wire, at, length) {
    return [...new Set(wire.flatMap(i => (i === at - 1 && at < length) ? [i, i + 1] : [i >= at ? i + 1 : i]))];
  }
  /* ...or deleted at `at`. */
  function deleteWirePoint(wire, at, length) {
    return [...new Set(wire.flatMap(i => {
      if (i === at - 1 || i === at) return at > 0 && at < length - 1 ? [at - 1] : [];
      return [i > at ? i - 1 : i];
    }))];
  }

  const xmlEsc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  /* Every side as a panel, three per row: roof edges (green), ridges (purple,
     dashed), wire-only stretches (gray, dotted) and landmark pins with bulb
     numbers. Self-contained SVG, so it can be downloaded as a file. */
  function flatHouseSvg(sides, rooflines, landmarks, title) {
    const W = 400, H = 300, cols = Math.min(3, Math.max(1, sides.length)), rows = Math.ceil(sides.length / cols);
    const px = x => 24 + x * 3.52, py = y => 56 + y * 2.2;
    const panels = sides.map((side, i) => {
      const lines = (rooflines && rooflines[side.id]) || [];
      const pins = (landmarks || []).filter(l => l.side === side.id && l.x != null);
      const body = lines.length ? lines.flatMap(l => roofSegments(l).map(({ a, b, lit }) =>
        `<line x1="${px(a[0])}" y1="${py(a[1])}" x2="${px(b[0])}" y2="${py(b[1])}" stroke="${!lit ? '#8A93B5' : l.kind === 'ridge' ? '#C7B2FF' : '#62D682'}" stroke-width="${lit ? 3 : 1.5}" stroke-linecap="round"${!lit ? ' stroke-dasharray="3 5"' : l.kind === 'ridge' ? ' stroke-dasharray="7 5"' : ''}/>`)).join('')
        : `<text x="${W / 2}" y="${H / 2 + 20}" text-anchor="middle" fill="#8A93B5" font-size="14">No roofline traced yet</text>`;
      const marks = pins.map(l => `<circle cx="${px(l.x * 100)}" cy="${py(l.y * 100)}" r="4.5" fill="#FFC062"/><text x="${px(l.x * 100) + 7}" y="${py(l.y * 100) - 6}" fill="#FFE2B0" font-size="11">${xmlEsc(l.name)} · ${l.bulb}</text>`).join('');
      const count = lines.reduce((n, l) => n + l.points.length - 1, 0);
      return `<g transform="translate(${(i % cols) * W},${Math.floor(i / cols) * H})"><rect x="8" y="8" width="${W - 16}" height="${H - 16}" rx="12" fill="#171C33" stroke="#2C3563"/>
        <text x="24" y="38" fill="#ECEFFA" font-size="18" font-weight="600">${xmlEsc(side.name)}</text>
        <text x="${W - 24}" y="38" text-anchor="end" fill="#8A93B5" font-size="12">${lines.length ? `${lines.length} section${lines.length === 1 ? '' : 's'} · ${count} segment${count === 1 ? '' : 's'}` : ''}</text>${body}${marks}</g>`;
    }).join('');
    const total = rows * H;
    return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${cols * W} ${total + 44}" width="${cols * W}" height="${total + 44}" font-family="system-ui, sans-serif" role="img" aria-label="${xmlEsc(title || 'Flat diagram of the house rooflines')}">
      <rect width="100%" height="100%" fill="#0F1328"/>${panels}
      <text x="24" y="${total + 28}" fill="#8A93B5" font-size="13">Green: roof edge · Purple dashed: ridge · Gray dotted: wire only (no bulbs) · Orange: landmarks with bulb numbers · Traced from photos, not to scale</text></svg>`;
  }

  /* Same rules the server enforces (server.py _validate_map). */
  function validSection(l) {
    return l && typeof l.id === 'string' && /^[A-Za-z0-9_-]{1,40}$/.test(l.id) && (l.kind === 'edge' || l.kind === 'ridge')
      && Array.isArray(l.points) && l.points.length >= 2 && l.points.length <= LIMITS.points
      && l.points.every(p => Array.isArray(p) && p.length === 2 && p.every(v => Number.isFinite(v) && v >= 0 && v <= 100));
  }

  const api = { DEFAULT_SIDES, LIMITS, simplify, detectRoofline, roofSegments, insertWirePoint, deleteWirePoint, flatHouseSvg, validSection };
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.Roofline = api;
})(typeof window !== 'undefined' ? window : globalThis);
