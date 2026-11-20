/* SPDX-License-Identifier: MIT
   Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)

   Music sync 2.0 (4.13): what the music is doing, from the browser's FFT.

   - Bass (30-250 Hz), mids (250-4000 Hz) and treble (4-14 kHz), each 0-1,
     with an automatic level: each band follows its own loudest moment of the
     last few seconds, so a quiet song and a loud one both use the full range.
   - Beats: a sudden rise in the low end (spectral flux of the bass and low
     mids) above its own recent average plus spread, at most about 214 a
     minute. `pulse` is 1 on a beat and fades over about a quarter second.
   - Tempo (BPM): how often the onset curve repeats (autocorrelation over the
     last 8 seconds), between 60 and 200, leaning to 80-170 where most music
     sits, with how sure it is (0-1).

   Plain logic, tested with Node. Works as a plain <script> (window.Beat) and
   as a Node module (tests). */
(function (root) {
  'use strict';

  const RANGES = { bass: [30, 250], mid: [250, 4000], treble: [4000, 14000] };
  const ONSET = [30, 500];             // where kicks and bass notes start
  const ENV_HZ = 50;                   // the onset curve, sampled 50 times a second
  const ENV_SECONDS = 8;
  const MIN_GAP = 0.28;                // seconds between beats (about 214 a minute)
  const BPM_RANGE = [60, 200];

  function create(sampleRate, fftSize) {
    const hz = sampleRate / fftSize, bins = fftSize / 2;
    const span = ([lo, hi]) => [Math.max(1, Math.floor(lo / hz)), Math.min(bins, Math.max(Math.floor(lo / hz) + 2, Math.ceil(hi / hz)))];
    return {
      ranges: Object.fromEntries(Object.entries(RANGES).map(([k, r]) => [k, span(r)])), onset: span(ONSET),
      prev: null, peak: { bass: -60, mid: -60, treble: -60 }, t: null,
      flux: [], env: new Float32Array(ENV_HZ * ENV_SECONDS), envAt: null, filled: 0,
      lastBeat: -1e9, pulse: 0, bpm: null, conf: 0, nextTempo: 0, maybe: null, beats: [],
    };
  }

  const toLin = db => (Number.isFinite(db) ? Math.pow(10, db / 20) : 0);

  /* db: getFloatFrequencyData (decibels per bin); t: seconds (the audio
     clock). Returns {bass, mid, treble, beat, pulse, bpm, conf}. */
  function step(S, db, t) {
    const dt = S.t === null ? 0 : Math.max(0, Math.min(0.5, t - S.t));
    S.t = t;
    const out = {};
    // Bass, mids, treble: average power in decibels, against each band's own recent peak.
    for (const k of ['bass', 'mid', 'treble']) {
      const [a, b] = S.ranges[k];
      let p = 0;
      for (let i = a; i < b; i++) { const v = toLin(db[i]); p += v * v; }
      const lvl = 10 * Math.log10(p / Math.max(1, b - a) + 1e-12);
      S.peak[k] = Math.max(lvl, Math.max(-75, S.peak[k] - 4 * dt));       // falls 4 dB a second toward quiet
      out[k] = Math.min(1, Math.max(0, (lvl - (S.peak[k] - 30)) / 30));
      out[k] = Math.round(out[k] * out[k] * 1000) / 1000;                   // soft parts stay low, as the app's levels do
    }
    // Onsets: how much the low end rose since the last frame.
    const [a, b] = S.onset, lin = new Float32Array(b - a);
    let flux = 0, sum = 0;
    for (let i = a; i < b; i++) { lin[i - a] = toLin(db[i]); sum += lin[i - a]; if (S.prev) flux += Math.max(0, lin[i - a] - S.prev[i - a]); }
    S.prev = lin;
    S.flux.push([t, flux]);
    while (S.flux.length && t - S.flux[0][0] > 1.5) S.flux.shift();
    const vals = S.flux.map(x => x[1]), mean = vals.reduce((s, v) => s + v, 0) / vals.length;
    const sd = Math.sqrt(vals.reduce((s, v) => s + (v - mean) * (v - mean), 0) / vals.length);
    // A beat: well above the recent rises, and a real jump in the low end, not the flicker of a steady hum
    const beat = vals.length > 8 && flux > mean + 1.5 * sd && flux > 0.35 * sum && flux > 1e-4 && t - S.lastBeat >= MIN_GAP;
    if (beat) { S.lastBeat = t; S.pulse = 1; S.beats.push(t); } else S.pulse *= Math.exp(-dt / 0.12);
    while (S.beats.length && t - S.beats[0] > ENV_SECONDS) S.beats.shift();
    out.beat = beat;
    out.pulse = Math.round(S.pulse * 1000) / 1000;
    // The onset curve, 50 samples a second, for the tempo.
    const slot = Math.floor(t * ENV_HZ);
    if (S.envAt === null) S.envAt = slot;
    while (S.envAt < slot) { S.env.copyWithin(0, 1); S.env[S.env.length - 1] = 0; S.envAt++; S.filled = Math.min(S.env.length, S.filled + 1); }
    S.env[S.env.length - 1] = Math.max(S.env[S.env.length - 1], Math.max(0, flux - mean));
    if (t >= S.nextTempo) { S.nextTempo = t + 0.5; tempo(S); }
    out.bpm = S.bpm;
    out.conf = Math.round(S.conf * 100) / 100;
    return out;
  }

  /* The tempo from the onset curve's autocorrelation (Wiener-Khinchin
     not needed here: 400 samples, 35 lags). */
  function tempo(S) {
    const n = S.filled;
    if (n < ENV_HZ * 4) return;                       // 4 seconds before guessing
    if (S.beats.length < 4) { S.bpm = null; S.conf = 0; S.maybe = null; return; }   // no beat, no tempo (a hum, talk, silence)
    const x = S.env.subarray(S.env.length - n), m = x.reduce((s, v) => s + v, 0) / n;
    // Smoothed over three samples: frames don't land exactly every 20 ms, and
    // an onset split between two samples would hide the beat's own lag.
    const y = Array.from(x, (v, i) => (0.25 * (x[i - 1] ?? v) + 0.5 * v + 0.25 * (x[i + 1] ?? v)) - m);
    const r0 = y.reduce((s, v) => s + v * v, 0);
    if (r0 <= 1e-12) return;
    const lo = Math.floor(60 * ENV_HZ / BPM_RANGE[1]), hi = Math.ceil(60 * ENV_HZ / BPM_RANGE[0]);
    const ac = [];
    for (let L = 0; L <= hi + 1; L++) { let s = 0; for (let i = L; i < n; i++) s += y[i] * y[i - L]; ac[L] = s / r0; }
    let best = -1, bestScore = -Infinity;
    for (let L = lo; L <= hi; L++) {
      if (!(ac[L] >= ac[L - 1] && ac[L] >= ac[L + 1])) continue;          // peaks only
      const bpm = 60 * ENV_HZ / L, w = Math.exp(-0.5 * Math.pow(Math.log2(bpm / 120) / 0.9, 2));
      const score = ac[L] * (0.6 + 0.4 * w);
      if (score > bestScore) { bestScore = score; best = L; }
    }
    if (best < 0 || ac[best] < 0.1) return;
    // Twice the beat repeats too: take the beat itself when half the lag is nearly as strong.
    const half = Math.round(best / 2);
    if (half >= lo && ac[half] >= 0.5 * ac[best] && ac[half] >= ac[half - 1] - 0.02 && ac[half] >= ac[half + 1] - 0.02) best = half;
    // Between samples: a parabola through the peak and its neighbors.
    const a = ac[best - 1], b = ac[best], c = ac[best + 1], d = a - 2 * b + c;
    const lag = best + (d ? 0.5 * (a - c) / d : 0), bpm = 60 * ENV_HZ / lag;
    const conf = Math.max(0, Math.min(1, b));
    if (S.bpm && Math.abs(bpm - S.bpm) / S.bpm < 0.04) { S.bpm = Math.round((S.bpm * 0.7 + bpm * 0.3) * 10) / 10; S.conf = conf; S.maybe = null; return; }
    // A different tempo has to show up twice in a row (a second apart) before it replaces the one shown.
    if (!S.bpm || conf > S.conf + 0.15 || (S.maybe && Math.abs(S.maybe - bpm) / bpm < 0.04)) {
      S.bpm = Math.round(bpm * 10) / 10; S.conf = conf; S.maybe = null;
    } else S.maybe = bpm;
  }

  const api = { create, step, RANGES, ENV_HZ };
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.Beat = api;
})(typeof window !== 'undefined' ? window : globalThis);
