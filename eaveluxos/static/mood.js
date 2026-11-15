/* SPDX-License-Identifier: MIT
   Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)

   Mood follow (3.18, beta): listen to the music through the app computer's
   microphone and say whether it's calm, lively or party loud, every 10
   seconds. Not beat sync: Trimlight's cloud takes a quarter to a full second
   per command, so the house follows the music's mood, not its beat.
   classify() and Window are plain logic (tested with Node); the browser part
   (microphone, analyser) is in app.js.
   Works as a plain <script> (window.Mood) and as a Node module (tests). */
(function (root) {
  'use strict';

  const LEVELS = ['quiet', 'calm', 'lively', 'party'];
  const QUIET_RMS = 0.012;          // below this the room is quiet
  const CUT = { calm: 0.38, lively: 0.68 };
  const HYST = 0.06;                // stay put near a boundary, so it doesn't flip back and forth

  /* features: {rms: average loudness 0-1, onsets: beats per second}.
     prev: the last level, for hysteresis. */
  function score(f) {
    return 0.55 * Math.min(1, (f.rms || 0) / 0.16) + 0.45 * Math.min(1, (f.onsets || 0) / 3.5);
  }
  function classify(f, prev) {
    if (!f || !(f.rms >= QUIET_RMS)) return 'quiet';
    const s = score(f);
    let lo = CUT.calm, hi = CUT.lively;
    if (prev === 'calm') lo += HYST;
    if (prev === 'lively') { lo -= HYST; hi += HYST; }
    if (prev === 'party') hi -= HYST;
    return s < lo ? 'calm' : s < hi ? 'lively' : 'party';
  }

  /* Collects 100 ms readings (rms, spectral flux) and turns a window of them
     into features: average loudness and onsets per second (a flux peak well
     above the recent average, at least 200 ms after the last one). */
  class Window {
    constructor() { this.rms = []; this.flux = []; this.onsets = 0; this.lastOnset = -1e9; this.t = 0; }
    add(rms, flux, dtMs = 100) {
      this.t += dtMs;
      const recent = this.flux.slice(-20), avg = recent.length ? recent.reduce((a, b) => a + b, 0) / recent.length : 0;
      if (recent.length >= 5 && flux > avg * 1.6 && flux > 0.002 && this.t - this.lastOnset >= 200) { this.onsets++; this.lastOnset = this.t; }
      this.rms.push(rms); this.flux.push(flux);
    }
    features() {
      const secs = Math.max(0.1, this.t / 1000), n = this.rms.length || 1;
      return { rms: this.rms.reduce((a, b) => a + b, 0) / n, onsets: this.onsets / secs };
    }
    reset() { this.rms = []; this.flux = []; this.onsets = 0; this.lastOnset = -1e9; this.t = 0; }
  }

  /* When to report, by the clock, not by counting timer ticks (3.18.2): a
     browser slows timers in a background tab to once a second, and Chrome
     to once a minute after a while, so counting 100 ticks of 100 ms could
     take far longer than the 3 minutes after which the lights go back to
     the schedule. step(now) returns the level to send, or null. */
  class Reporter {
    constructor(periodMs = 10000, quietMs = 30000) { this.period = periodMs; this.quietLimit = quietMs; this.start = null; this.quiet = 0; this.level = null; }
    step(now, win) {
      if (this.start === null) { this.start = now; return null; }
      const el = now - this.start;
      if (el < this.period) return null;
      this.start = now;
      const lv = classify(win.features(), this.level); win.reset();
      this.quiet = lv === 'quiet' ? this.quiet + el : 0;
      if (lv === 'quiet' && this.quiet < this.quietLimit) return null;    // a pause between songs isn't the end
      this.level = lv;
      return lv;
    }
  }

  const api = { LEVELS, classify, score, Window, Reporter };
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.Mood = api;
})(typeof window !== 'undefined' ? window : globalThis);
