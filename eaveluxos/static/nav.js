/* SPDX-License-Identifier: MIT
   Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)

   The app's tabs and where each address goes (4.0). Seven tabs; Create
   opens from Patterns; Lights, Date & Time and Settings are sections of
   Setup; the Manual is the ? button. Old addresses (#create, #lights,
   #time, #settings) still work. Plain logic, tested with Node (4.0.1).
   Works as a plain <script> (window.Nav) and as a Node module (tests). */
(function (root) {
  'use strict';

  const TABS = [['home','Home'],['patterns','Patterns'],['schedule','Schedule'],['alerts','Alerts'],['music','Music'],['map','House'],['setup','Setup']];
  const TAB_OF = { create: 'patterns', lights: 'setup', color: 'setup', local: 'setup', backups: 'setup',
    time: 'setup', access: 'setup', app: 'setup' };
  // 4.9.2: Color correction, Local mode and Pattern backups have their own
  // sections (they were folded panels under Lights & controller).
  const SETUP_SECS = [['lights', 'Lights & controller'], ['color', 'Color correction'], ['local', 'Local mode'],
    ['backups', 'Pattern backups'], ['time', 'Location & time'], ['access', 'Accounts & access'], ['app', 'App']];
  const ADMIN_SECS = ['local', 'backups'];                     // Administrators only, as the panels were
  const VIEW_ALIAS = { settings: 'access', setup: null };      // setup: the last Setup section used

  /* view asked for -> {view, tab, setup (is a Setup section), replace (an
     old or unknown address: correct it rather than add a Back step)}. */
  function resolve(asked, known, lastSetup) {
    let view = asked, replace = false;
    if (view in VIEW_ALIAS) { view = VIEW_ALIAS[view] || lastSetup || 'lights'; replace = true; }
    if (!known(view)) { view = 'home'; replace = true; }
    const tab = TAB_OF[view] || view;
    return { view, tab, replace, setup: SETUP_SECS.some(([k]) => k === view) };
  }

  const api = { TABS, TAB_OF, SETUP_SECS, ADMIN_SECS, VIEW_ALIAS, resolve };
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.Nav = api;
})(typeof window !== 'undefined' ? window : globalThis);
