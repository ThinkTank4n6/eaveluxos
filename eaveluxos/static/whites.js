/* SPDX-License-Identifier: MIT
   Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
   White by color temperature. Trimlight bulbs are RGB, with no white chip,
   so a white is a mix of red, green and blue. kelvinHex() gives the mix that
   matches a color temperature (warm candlelight 1800 K to daylight 6500 K),
   from a fit to the blackbody curve (Tanner Helland's well-known one).
   The app's color correction (Lights › Color correction) then adjusts it for
   the bulbs, as for every other color.
   Works as a plain <script> (window.Whites) and as a Node module (tests). */
(function (root) {
  'use strict';
  const MIN = 1800, MAX = 6500;
  const PRESETS = [
    { k: 2200, name: 'Candlelight' }, { k: 2700, name: 'Warm white' }, { k: 3000, name: 'Soft white' },
    { k: 4000, name: 'Neutral white' }, { k: 5000, name: 'Cool white' }, { k: 6500, name: 'Daylight' }];
  const clamp = v => Math.max(0, Math.min(255, Math.round(v)));
  function kelvinRgb(k) {
    const t = Math.max(MIN, Math.min(MAX, Number(k) || 2700)) / 100;
    const r = t <= 66 ? 255 : 329.698727446 * Math.pow(t - 60, -0.1332047592);
    const g = t <= 66 ? 99.4708025861 * Math.log(t) - 161.1195681661 : 288.1221695283 * Math.pow(t - 60, -0.0755148492);
    const b = t >= 66 ? 255 : t <= 19 ? 0 : 138.5177312231 * Math.log(t - 10) - 305.0447927307;
    return [clamp(r), clamp(g), clamp(b)];
  }
  function kelvinHex(k) {
    return '#' + kelvinRgb(k).map(v => v.toString(16).padStart(2, '0')).join('').toUpperCase();
  }
  const api = { MIN, MAX, PRESETS, kelvinRgb, kelvinHex };
  if (typeof module !== 'undefined' && module.exports) module.exports = api; else root.Whites = api;
})(typeof window !== 'undefined' ? window : globalThis);
