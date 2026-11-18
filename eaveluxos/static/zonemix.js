/* SPDX-License-Identifier: MIT
   Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)

   Combine patterns by zone (4.7): one pattern that lays a different pattern's
   colors along each zone of the house, for example Christmas on the garage,
   Thanksgiving on the main roof and American Flag on the porch.

   A controller shows one pattern at a time: at most 30 color blocks (each up
   to 90 bulbs here, as everywhere in the designer) with one motion and speed.
   So each zone's pattern is repeated along that zone only, and when the whole
   would need more than 30 blocks, the busiest zone's colors are made longer
   (each color 2, 3, ... times as many bulbs) until it fits. The colors and
   their order stay; a pattern with many small colors gets chunkier.

   A controller also has one brightness. A zone whose pattern is dimmer than
   the brightest one is darkened to match its own brightness, as Paint by
   zone does.

   Plain logic, tested with Node. Works as a plain <script> (window.ZoneMix)
   and as a Node module (tests). */
(function (root) {
  'use strict';

  const OFF = 'off';

  function dim(hex, factor) {
    if (hex === OFF || factor >= 1) return hex;
    const n = parseInt(hex.slice(1), 16);
    const ch = s => Math.round(((n >> s) & 255) * factor);
    return '#' + [16, 8, 0].map(s => ch(s).toString(16).padStart(2, '0')).join('').toUpperCase();
  }

  /* [color, count] runs that repeat a pattern's colors along len bulbs, each
     color k times as long. */
  function tile(pick, len, k) {
    const seq = pick.colors.map((c, i) => [c, (Number(pick.counts[i]) || 0) * k]).filter(([, n]) => n > 0);
    if (!seq.length) return [[OFF, len]];
    const out = [];
    for (let left = len, i = 0; left > 0; i = (i + 1) % seq.length) {
      const n = Math.min(left, seq[i][1]);
      out.push([seq[i][0], n]);
      left -= n;
    }
    return out;
  }

  function merge(runs) {
    const out = [];
    for (const [c, n] of runs) {
      if (out.length && out[out.length - 1][0] === c) out[out.length - 1][1] += n;
      else out.push([c, n]);
    }
    return out;
  }

  const blocks = (runs, perSlot) => runs.reduce((t, [, n]) => t + Math.ceil(n / perSlot), 0);

  /* zones: [{start, end}] (later ones win where they overlap); picks: one per
     zone, {colors, counts, brightness} or null (that zone shows the rest);
     base: 'off' or a color for everything else. Returns {segs, brightness,
     stretched: {zoneIndex: k}}; throws when even one block per zone is too
     many. */
  function combine({ zones, picks, base = OFF, total, maxSlots = 30, perSlot = 90 }) {
    if (!(total >= 1)) throw new Error('No bulbs to combine on.');
    const owner = new Array(total).fill(-1);
    zones.forEach((z, i) => {
      if (!picks[i]) return;
      for (let b = Math.max(1, z.start); b <= Math.min(total, z.end); b++) owner[b - 1] = i;
    });
    if (!owner.some(o => o >= 0)) {
      // Review #4 (4.7): zones saved when the house had more bulbs
      throw new Error(picks.some(Boolean) ? `The chosen zones are outside the ${total} bulbs the lights have now. Check them on the House tab.`
        : 'Choose a pattern for at least one zone.');
    }
    const regions = [];
    owner.forEach((o, b) => {
      const r = regions[regions.length - 1];
      if (r && r.owner === o) r.len++;
      else regions.push({ owner: o, start: b + 1, len: 1 });
    });
    const used = [...new Set(owner.filter(o => o >= 0))];
    const top = Math.max(...used.map(i => Number(picks[i].brightness ?? 255)), 1);
    const shaded = {};
    for (const i of used) {
      const f = Number(picks[i].brightness ?? 255) / top;
      shaded[i] = { ...picks[i], colors: picks[i].colors.map(c => c === OFF ? OFF : dim(String(c).toUpperCase(), f)) };
    }
    const k = Object.fromEntries(used.map(i => [i, 1]));
    const build = () => merge(regions.flatMap(r => r.owner < 0 ? [[base, r.len]] : tile(shaded[r.owner], r.len, k[r.owner])));
    const zoneBlocks = i => regions.filter(r => r.owner === i).reduce((t, r) => t + blocks(merge(tile(shaded[i], r.len, k[i])), perSlot), 0);
    const floor = i => regions.filter(r => r.owner === i).reduce((t, r) => t + Math.ceil(r.len / perSlot), 0);
    let runs = build();
    while (blocks(runs, perSlot) > maxSlots) {
      // Stretch the zone using the most blocks that can still give some up.
      const can = used.filter(i => zoneBlocks(i) > floor(i));
      if (!can.length) {
        throw new Error(`That needs ${blocks(runs, perSlot)} color blocks even with one color per zone, but a controller ` +
          `allows ${maxSlots}. Use fewer zones, or let some show the rest.`);
      }
      const i = can.reduce((a, b) => zoneBlocks(b) > zoneBlocks(a) ? b : a);
      k[i]++;
      runs = build();
    }
    const segs = [];
    for (const [c, n] of runs) for (let left = n; left > 0; left -= perSlot) segs.push({ c, n: Math.min(perSlot, left) });
    const stretched = Object.fromEntries(Object.entries(k).filter(([, v]) => v > 1).map(([i, v]) => [i, v]));
    return { segs, brightness: top, stretched };
  }

  const api = { combine, tile, dim, OFF };
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.ZoneMix = api;
})(typeof window !== 'undefined' ? window : globalThis);
