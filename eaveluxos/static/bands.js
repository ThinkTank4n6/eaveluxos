/* SPDX-License-Identifier: MIT
   Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)

   Music from this computer (4.1, experimental): turn what the browser hears
   into the 16 sound levels the Trimlight controller's music mode takes, the
   same way the Trimlight app does with a phone's microphone: 16 frequency
   bands from low to high, each 0-255, about 9 times a second.
   edges() and levels() are plain logic (tested with Node); the browser part
   (microphone or the computer's sound, analyser, sending) is in app.js.
   Works as a plain <script> (window.Bands) and as a Node module (tests). */
(function (root) {
  'use strict';

  const COUNT = 16;
  const LOW_HZ = 40, HIGH_HZ = 12000;     // bass to the top of most music
  const FLOOR_DB = -90, SPAN_DB = 60;     // -90 dB and below is 0, -30 dB and above is 255

  /* For an analyser: the FFT bins that make up each band, log-spaced like
     hearing. Every band gets at least one bin. */
  function edges(sampleRate, fftSize) {
    const bins = fftSize / 2, hz = sampleRate / fftSize, out = [];
    let start = Math.max(1, Math.floor(LOW_HZ / hz));
    for (let i = 0; i < COUNT; i++) {
      const top = LOW_HZ * Math.pow(HIGH_HZ / LOW_HZ, (i + 1) / COUNT);
      let end = Math.min(bins, Math.max(start + 1, Math.round(top / hz)));
      if (i === COUNT - 1) end = Math.max(end, start + 1);
      out.push([Math.min(start, bins - 1), Math.min(end, bins)]);
      start = Math.min(end, bins - 1);
    }
    return out;
  }

  /* db: an analyser's getFloatFrequencyData (decibels per bin). gainDb: the
     page's Input level, added before scaling. Each band is its loudest bin,
     scaled so quiet is near 0 and loud music reaches the top, with a curve
     that keeps soft parts low (as the app's levels were). */
  function levels(db, bandEdges, gainDb) {
    const g = Number.isFinite(gainDb) ? gainDb : 0, out = [];
    for (const [a, b] of bandEdges) {
      let peak = -Infinity;
      for (let i = a; i < b; i++) if (db[i] > peak) peak = db[i];
      if (!Number.isFinite(peak)) { out.push(0); continue; }
      const x = Math.min(1, Math.max(0, (peak + g - FLOOR_DB) / SPAN_DB));
      out.push(Math.round(255 * x * x));
    }
    return out;
  }

  const api = { COUNT, LOW_HZ, HIGH_HZ, edges, levels };
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.Bands = api;
})(typeof window !== 'undefined' ? window : globalThis);
