/* SPDX-License-Identifier: MIT
   Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)

   Music sync 2.0 (4.13): zones that follow the music. Each zone of the house
   follows the bass, the mids, the treble or the beat, in its own color,
   shown as a glow (the whole zone brightens with it) or a meter (it fills
   along the zone, from its first bulb, or its last if it runs the other
   way). Everything else is dark or a color of your choice.

   frame() turns the music now into one pattern (at most 30 color blocks of
   up to perSlot bulbs, like any pattern of your own colors), which the app
   shows live on the controller. Levels are rounded to a few steps, so a
   frame only differs from the last when something visible changed.

   Plain logic, tested with Node. Works as a plain <script> (window.MusicZones)
   and as a Node module (tests). */
(function (root) {
  'use strict';

  const FOLLOWS = ['bass', 'mid', 'treble', 'beat', 'off'];
  const SHOWS = ['glow', 'meter'];
  const GLOW_STEPS = 8, METER_STEPS = 10;

  const hex = c => /^#[0-9A-Fa-f]{6}$/.test(String(c)) ? String(c).toUpperCase() : '#000000';
  function dim(c, k) {
    const n = parseInt(hex(c).slice(1), 16);
    return '#' + [16, 8, 0].map(s => Math.round(((n >> s) & 255) * k).toString(16).padStart(2, '0')).join('').toUpperCase();
  }

  /* zones: the House tab's zones (for one controller); maps: [{zone (its
     index), follows, shows, color}]; base: '#000000' or a color for the rest;
     music: {bass, mid, treble, pulse} (0-1). Returns {colors, counts, key}. */
  function frame({ zones, maps, base = '#000000', total, music, perSlot = 90, maxSlots = 30 }) {
    if (!(total >= 1)) throw new Error('The number of bulbs isn’t known yet.');
    const px = new Array(total).fill(hex(base));
    for (const m of maps || []) {
      const z = zones[m.zone];
      if (!z || !FOLLOWS.includes(m.follows) || m.follows === 'off') continue;
      const a = Math.max(1, z.start), b = Math.min(total, z.end);
      if (a > b) continue;
      const v = Math.max(0, Math.min(1, m.follows === 'beat' ? +music.pulse || 0 : +music[m.follows] || 0));
      if (m.shows === 'meter') {
        const len = b - a + 1, lit = Math.round(Math.round(v * METER_STEPS) / METER_STEPS * len);
        for (let i = 0; i < len; i++) {
          const on = z.reverse ? i >= len - lit : i < lit;
          px[a - 1 + i] = on ? hex(m.color) : '#000000';
        }
      } else {
        const c = dim(m.color, Math.round(v * GLOW_STEPS) / GLOW_STEPS);
        for (let i = a; i <= b; i++) px[i - 1] = c;
      }
    }
    const colors = [], counts = [];
    for (const c of px) {
      const k = colors.length - 1;
      if (k >= 0 && colors[k] === c && counts[k] < perSlot) counts[k]++;
      else { colors.push(c); counts.push(1); }
    }
    if (colors.length > maxSlots) throw new Error(`That needs ${colors.length} color blocks; a controller takes ${maxSlots}. Use fewer zones or fewer meters.`);
    return { colors, counts, key: colors.map((c, i) => c + counts[i]).join('') };
  }

  /* The most color blocks these choices can need (each meter half full, each
     glow lit), to say before a show whether it fits. */
  function worst({ zones, maps, base, total, perSlot = 90 }) {
    const half = { bass: 0.5, mid: 0.5, treble: 0.5, pulse: 0.5 };
    try { return frame({ zones, maps, base, total, music: half, perSlot, maxSlots: Infinity }).colors.length; }
    catch { return Infinity; }
  }

  const api = { FOLLOWS, SHOWS, frame, worst, dim };
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.MusicZones = api;
})(typeof window !== 'undefined' ? window : globalThis);
