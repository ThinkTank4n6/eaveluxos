/* SPDX-License-Identifier: MIT
   Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
   Light / Dark / Auto (3.15). Loaded in <head>, before anything is drawn, so
   a chosen theme never flashes the other one first. Kept per device. */
(function () {
  var t = null;
  try { t = localStorage.getItem('elx-theme'); } catch (e) { /* no storage: follow the system */ }
  if (t === 'light' || t === 'dark') document.documentElement.setAttribute('data-theme', t);
}());
