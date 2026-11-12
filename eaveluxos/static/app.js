'use strict';
/* SPDX-License-Identifier: MIT
   Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6) */
/* EaveLuxOS GUI. Plain JavaScript, no build step, no external files. */

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const clone = o => JSON.parse(JSON.stringify(o));
const S = { session:null, status:null, settings:null, catalog:null, devices:null, account:null, view:'home', timers:[] };

/* ---------------------------------------------------------------- api */
/* The sign-in token is kept in this origin's storage (scheme + host + PORT),
   not in a cookie: browsers send cookies to every port on a host, so another
   web app on the same computer would receive them. */
const TOKEN_KEY = 'eaveluxos_session';
const token = {
  get() {
    try {
      let t = localStorage.getItem(TOKEN_KEY);
      for (const oldKey of ['lumaos_session', 'tls_session']) {   // keys used under earlier names
        const old = localStorage.getItem(oldKey);
        if (!t && old) { localStorage.setItem(TOKEN_KEY, old); t = old; }
        if (old) localStorage.removeItem(oldKey);
      }
      return t;
    } catch { return null; }
  },
  set(v) { try { v ? localStorage.setItem(TOKEN_KEY, v) : localStorage.removeItem(TOKEN_KEY); } catch { /* private mode */ } },
};
function authHeaders() { const t = token.get(); return t ? { 'X-Session': t } : {}; }
async function api(path, opts = {}) {
  const init = { method: opts.method || (opts.body !== undefined ? 'POST' : 'GET'), headers: { 'X-Requested-With': 'eaveluxos', ...authHeaders() }, cache: 'no-store' };
  if (opts.body !== undefined) { init.headers['Content-Type'] = 'application/json'; init.body = JSON.stringify(opts.body); }
  const r = await fetch('api/' + path, init);
  let data = null;
  try { data = await r.json(); } catch { /* empty */ }
  if (r.status === 401 && path !== 'session') { token.set(null); await boot(); throw new Error('Please sign in.'); }
  // Security changes from a phone ask for the app password again (server: SENSITIVE).
  if (r.status === 403 && data && data.reauth && opts.body !== undefined && (opts._tries || 0) < 3) {
    const pw = await askPassword(data.error);
    if (pw === null) throw new Error('Canceled.');
    return api(path, { ...opts, body: { ...opts.body, confirm_password: pw }, _tries: (opts._tries || 0) + 1 });
  }
  if (!r.ok) throw new Error((data && data.error) || `Request failed (${r.status})`);
  return data;
}
function toast(msg, bad = false) {
  const t = $('#toast');
  t.textContent = msg; t.className = 'toast' + (bad ? ' bad' : ''); t.hidden = false;
  clearTimeout(toast._t); toast._t = setTimeout(() => t.hidden = true, bad ? 6000 : 3000);
}
async function busy(btn, fn) {
  const b = btn instanceof Element ? btn : null;
  if (b) { b.disabled = true; b.dataset.label = b.innerHTML; }
  try { return await fn(); }
  catch (e) { toast(e.message, true); throw e; }
  finally { if (b) { b.disabled = false; } }
}
const quiet = p => p.catch(() => {});

/* ---------------------------------------------------------------- formatting */
function hm12(hhmm) { if (!hhmm) return '—'; const [h, m] = hhmm.split(':').map(Number); return `${(h % 12) || 12}:${String(m).padStart(2, '0')} ${h < 12 ? 'AM' : 'PM'}`; }
const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const DAYS = ['mon','tue','wed','thu','fri','sat','sun'];
const DAYNAMES = { mon:'Mon', tue:'Tue', wed:'Wed', thu:'Thu', fri:'Fri', sat:'Sat', sun:'Sun' };
function slug(label, taken) {
  let base = String(label).toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '') || 'pattern';
  if (/^\d/.test(base)) base = 'p_' + base;
  let k = base, n = 2; while (taken[k]) k = `${base}_${n++}`; return k;
}
const hex = n => '#' + (n >>> 0).toString(16).padStart(6, '0').slice(-6).toUpperCase();
const swi = c => c === 'off' ? '<i class="off" title="Zoned off"></i>' : `<i style="background:${esc(c)}"></i>`;
function swatches(list, max = 6) { return list && list.length ? `<span class="sw">${list.slice(0, max).map(swi).join('')}</span>` : ''; }
function strand(colors, counts) {
  if (!colors || !colors.length) return '';
  return `<div class="strand" aria-hidden="true">${colors.map((c, i) => `<i ${c === 'off' ? 'class="off" ' : ''}style="${c === 'off' ? '' : `background:${esc(c)};`}flex-grow:${counts ? (counts[i] || 1) : 1}"></i>`).join('')}</div>`;
}
function effectSwatches(def) {
  if (!def) return [];
  if (def.colors) return def.colors;
  if (def.builtin !== undefined && S.catalog) return S.catalog.builtin[def.builtin]?.swatches || [];
  return [];
}
function effectKind(def) {
  if (!def) return '';
  if (def.colors) return `Custom · ${S.catalog ? S.catalog.custom_modes[def.custom_mode || 0] : ''}`;
  if (def.builtin !== undefined) return `Built-in · ${S.catalog ? S.catalog.builtin.find(b => b.mode === def.builtin)?.name : def.builtin}`;
  return 'Saved in the Trimlight app';
}

/* ---------------------------------------------------------------- dialogs */
/* Its own <dialog>, so it can open on top of whichever dialog made the request. */
function askPassword(message) {
  return new Promise(res => {
    let d = $('#reauth');
    if (!d) { d = document.createElement('dialog'); d.id = 'reauth'; document.body.append(d); }
    d.innerHTML = `<form method="dialog"><h2>Confirm it's you</h2><p>${esc(message)}</p>
      <label class="field">App password<input type="password" autocomplete="current-password" required></label>
      <div class="foot"><button type="button" class="ghost" value="no">Cancel</button><button class="primary" value="yes">Confirm</button></div></form>`;
    const input = $('input', d);
    let done = false;
    const finish = v => { if (done) return; done = true; if (d.open) d.close(); res(v); };
    $('button.ghost', d).addEventListener('click', () => finish(null));
    $('form', d).addEventListener('submit', e => { e.preventDefault(); finish(input.value); });
    d.addEventListener('close', () => finish(null), { once: true });
    d.showModal();
    input.focus();
  });
}
function dialog(html, onSubmit, opts = {}) {
  const d = $('#dlg');
  d.innerHTML = `<form method="dialog" novalidate>${html}
    <div class="foot">${opts.extraFoot || ''}<button type="button" class="ghost" data-close>Cancel</button>
    ${onSubmit ? `<button class="primary" value="ok">${esc(opts.ok || 'Save')}</button>` : ''}</div></form>`;
  const form = $('form', d);
  form.addEventListener('click', e => { if (e.target.closest('[data-close]')) d.close(); });
  form.addEventListener('submit', async e => {
    e.preventDefault();
    const btn = $('button.primary', form);
    try { await busy(btn, () => onSubmit(form)); d.close(); } catch { /* toast shown */ }
  });
  d.showModal();
  if (opts.onOpen) opts.onOpen(form);
  return form;
}
function confirmBox(title, body, okLabel = 'Continue', danger = false) {
  return new Promise(res => {
    const d = $('#dlg');
    d.innerHTML = `<form method="dialog"><h2>${esc(title)}</h2><p>${body}</p><div class="foot">
      <button type="button" class="ghost" value="no">Cancel</button><button class="${danger ? 'danger' : 'primary'}" value="yes">${esc(okLabel)}</button></div></form>`;
    $$('button', d).forEach(b => b.addEventListener('click', () => { d.close(); res(b.value === 'yes'); }));
    d.showModal();
  });
}

/* ---------------------------------------------------------------- ribbon */
const ICONS = {
  manual: '<path d="M4.5 5.5A2 2 0 0 1 6.5 3.5H19v14H6.5a2 2 0 0 0-2 2z"/><path d="M4.5 19.5a2 2 0 0 0 2 2H19v-4"/><path d="M8.5 7.5h6M8.5 10.5h6"/>',
  home: '<path d="M4 11.5 12 5l8 6.5V19a1 1 0 0 1-1 1h-4.5v-5h-5v5H5a1 1 0 0 1-1-1z"/>',
  patterns: '<circle cx="6" cy="8" r="2.4"/><circle cx="12" cy="6" r="2.4"/><circle cx="18" cy="8" r="2.4"/><path d="M3 15c3 2.5 6 3.5 9 3.5s6-1 9-3.5"/>',
  create: '<path d="M4 20l4-1 10.5-10.5a2.1 2.1 0 0 0-3-3L5 16z"/><path d="M14 7l3 3"/>',
  schedule: '<rect x="3.5" y="5" width="17" height="15" rx="2"/><path d="M3.5 10h17M8 3v4M16 3v4"/><path d="M12 13.5v3h2.5"/>',
  map: '<path d="M3.5 11 12 4.5l8.5 6.5"/><path d="M5.5 9.8V19.5h13V9.8"/><circle cx="12" cy="13" r="2.2"/><path d="M12 15.2v2.3"/>',
  lights: '<path d="M4 7h16M4 12h16M4 17h16"/><circle cx="8" cy="7" r="1.6"/><circle cx="15" cy="12" r="1.6"/><circle cx="10" cy="17" r="1.6"/>',
  time: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
  settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
};
const TABS = [['home','Home'],['patterns','Patterns'],['create','Create'],['map','House map'],['schedule','Schedule'],['lights','Lights'],['time','Date & Time'],['settings','Settings'],['manual','Manual']];
const icon = n => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[n]}</svg>`;
function buildRibbon() {
  $('#ribbon').innerHTML = TABS.map(([k, l]) => `<button data-tab="${k}">${icon(k)}<span>${l}</span></button>`).join('');
  $('#ribbon').addEventListener('click', e => { const b = e.target.closest('[data-tab]'); if (b) go(b.dataset.tab); });
}
function go(view, extra) {
  S.view = view; S.timers.forEach(clearInterval); S.timers = [];
  if (location.hash !== '#' + view) history.replaceState(null, '', '#' + view);
  $$('#ribbon button').forEach(b => b.setAttribute('aria-current', b.dataset.tab === view ? 'page' : 'false'));
  $('#ribbon button[aria-current=page]')?.scrollIntoView({ inline: 'nearest', block: 'nearest' });
  document.body.classList.remove('lit', 'flashing');
  const mm = $('#main'); mm.onclick = mm.oninput = mm.onchange = null;
  const fn = VIEWS[view] || VIEWS.home;
  quiet(fn(extra));
  window.scrollTo(0, 0);
}
const VIEWS = {};

/* ---------------------------------------------------------------- data loaders */
async function loadSettings() { S.settings = await api('settings'); return S.settings; }
async function saveSettings(next, msg = 'Saved') {
  next._rev = S.settings._rev;
  try {
    const r = await api('settings', { body: next });
    next._rev = r._rev; S.settings = next; toast(msg);
  } catch (e) {
    if (/another device/.test(e.message)) { await loadSettings(); if (VIEWS[S.view]) quiet(VIEWS[S.view]()); }
    throw e;
  }
  quiet(refreshStatus());
}
async function loadCatalog() { if (!S.catalog) S.catalog = await api('catalog'); return S.catalog; }
async function loadDevices(force) { if (!S.devices || force) S.devices = await api('devices'); return S.devices; }
async function refreshStatus() {
  try { S.status = await api('status'); } catch (e) { setPill('bad', "Can't reach the app"); throw e; }
  const st = S.status;
  if (st.setup_only) setPill('', 'Setup needed');
  else if (st.setup && st.setup.problem) setPill('bad', 'Check settings');
  else if (st.error) setPill('bad', "Can't reach lights");
  else setPill('ok', st.target.on ? 'Lights on' : 'Lights off');
  return st;
}
function setPill(kind, text) { const p = $('#pill'); p.className = 'pill' + (kind ? ' ' + kind : ''); p.textContent = text; }

/* ---------------------------------------------------------------- boot, sign-in, wizard */
async function boot() {
  S.session = await api('session');
  const s = S.session;
  if (s.version) $('#legalver').textContent = `EaveLuxOS ${s.version}`;
  if (!s.authed) return gate();
  $('#top').hidden = false;
  const u = s.user || { role: 'admin', local: true };
  document.body.dataset.role = u.role;
  $('#who').hidden = !!u.local;
  $('#who').textContent = u.local ? '' : `${u.username} · ${ROLE_NAMES[u.role] || u.role}`;
  $('#viewonly').hidden = u.role !== 'viewer';
  if (!$('#ribbon').children.length) buildRibbon();
  await Promise.all([loadSettings(), loadCatalog()]);
  if (!s.setup.wizard_done && u.role === 'admin') return wizard(0);
  go((location.hash || '#home').slice(1));
}
const ROLE_NAMES = { admin: 'Administrator', editor: 'Editor', viewer: 'Viewer' };
const role = () => (S.session && S.session.user && S.session.user.role) || 'admin';
const isAdmin = () => role() === 'admin';
function gate() {
  $('#top').hidden = true;
  $('#viewonly').hidden = true;
  const pw = S.session.password_set;
  $('#main').innerHTML = `<div class="gate"><div class="panel stack">
    <h1 style="font-size:1.6rem">EaveLuxOS</h1>
    ${pw ? `<p class="muted">Sign in with your EaveLuxOS account.</p>
      <label class="field">User name<input type="text" id="guser" autocomplete="username" autocapitalize="none" spellcheck="false"></label>
      <label class="field">Password<input type="password" id="gpw" autocomplete="current-password"></label>`
    : S.session.setup_open ? `<p class="muted">Setup isn't finished. Finish it on the computer running the app, or enter the 6-digit setup code shown in its window or log.</p>
      <label class="field">Setup code<input type="text" id="gpw" inputmode="numeric" autocomplete="one-time-code" maxlength="6"></label>`
    : `<p class="muted">To use the app from this device, first create an account on the computer running it (Settings › Accounts).</p>`}
    ${pw || S.session.setup_open ? '<button class="primary" id="gbtn">Sign in</button>' : ''}
    ${location.protocol === 'http:' && !S.session.local ? `<p class="note small">This connection isn't encrypted, so others on your network could see the password.
      For HTTPS, run <code>python3 main.py make-cert</code> on the app computer (see the manual).</p>` : ''}</div></div>`;
  if (!$('#gbtn')) return;
  const submit = () => busy($('#gbtn'), async () => {
    const res = await api('login', { body: pw ? { username: $('#guser').value.trim().toLowerCase() || 'admin', password: $('#gpw').value, device: navigator.userAgent }
      : { code: $('#gpw').value.trim(), device: navigator.userAgent } });
    token.set(res.token);
    $('#toast').hidden = true;
    await boot();
  }).catch(() => {});
  $('#gbtn').onclick = submit;
  $('#gpw').addEventListener('keydown', e => { if (e.key === 'Enter') submit(); });
  ($('#guser') || $('#gpw')).focus();
}

const WIZ = ['Welcome', 'Trimlight account', 'Controllers', 'Location', 'Phone access', 'Done'];
async function wizard(step) {
  $$('#ribbon button').forEach(b => b.setAttribute('aria-current', 'false'));
  const m = $('#main');
  const shell = body => `<div class="wizard"><div class="steps">${WIZ.map((_, i) => `<i class="${i <= step ? 'on' : ''}"></i>`).join('')}</div>
    <div class="panel stack"><p class="small muted">Step ${step + 1} of ${WIZ.length}</p>${body}</div></div>`;
  const next = () => wizard(step + 1);
  if (step === 0) {
    m.innerHTML = shell(`<h1 style="font-size:1.6rem">Welcome</h1>
      <p>This app runs your Trimlight Edge lights on true sunrise and sunset times, handles daylight saving time correctly, and lets you design patterns and schedules from any phone or computer at home.</p>
      <p>You'll need the <b>Client ID</b> and <b>Client Secret</b> for the Trimlight API. Don't have them yet? Get them at <a href="https://trimlight.ledhue.com/trimlight/v1/api-credentials/apply" target="_blank" rel="noopener noreferrer">Trimlight's API credentials page</a>: sign in with your Trimlight account email and password (or an emailed code) and choose <b>Get API credentials</b>. The Manual (section 2) has the steps.</p>
      <div class="row"><button class="primary" id="w1">Get started</button><button class="ghost" id="wskip">Skip setup for now</button></div>`);
    $('#w1').onclick = next; $('#wskip').onclick = () => go('home');
  } else if (step === 1) {
    const acct = await api('account');
    m.innerHTML = shell(`<h2>Your Trimlight account</h2>
      <p class="muted">These stay on this computer. The secret is never shown again or sent to other devices.</p>
      <p class="note">Don't have them? Open <a href="https://trimlight.ledhue.com/trimlight/v1/api-credentials/apply" target="_blank" rel="noopener noreferrer">Trimlight's API credentials page</a>, sign in with your Trimlight account email and password (or an emailed code), choose <b>Get API credentials</b>, and paste the two codes here exactly as shown.</p>
      <label class="field">Client ID<input type="text" id="cid" autocomplete="off" spellcheck="false" value="${esc(acct.client_id)}"></label>
      <label class="field">Client Secret<input type="password" id="csec" autocomplete="off" spellcheck="false" placeholder="${acct.secret_hint ? 'Saved (' + esc(acct.secret_hint) + '). Leave empty to keep it.' : ''}"></label>
      <div class="row"><button class="primary" id="wtest">Test and continue</button><button class="ghost" id="wback">Back</button></div>
      <p class="note" id="wres"></p>`);
    $('#wback').onclick = () => wizard(0);
    $('#wtest').onclick = e => busy(e.currentTarget, async () => {
      const r = await api('credentials', { body: { client_id: $('#cid').value, client_secret: $('#csec').value } });
      S.wizDevices = r.devices; toast(`Connected. Found ${r.devices.length} controller${r.devices.length === 1 ? '' : 's'}.`);
      next();
    }).catch(() => {});
  } else if (step === 2) {
    const devs = S.wizDevices || await api('devices').catch(() => []);
    const chosen = S.settings.service?.devices || [];
    m.innerHTML = shell(`<h2>Which controllers should this app run?</h2>
      ${devs.length ? `<div class="stack">${devs.map(d => `<label class="check"><input type="checkbox" value="${esc(d.id)}" ${!chosen.length || chosen.includes(d.id) ? 'checked' : ''}>
        <span><b>${esc(d.name)}</b><br><span class="small muted">${d.online ? 'Online' : 'Offline'} · ${esc(d.id)}</span></span></label>`).join('')}</div>`
        : `<p class="callout warn">No controllers were found on this account. Make sure the controller is paired in the Trimlight Edge app.</p>`}
      <div class="row"><button class="primary" id="wnext">Continue</button><button class="ghost" id="wback">Back</button></div>`);
    $('#wback').onclick = () => wizard(1);
    $('#wnext').onclick = e => busy(e.currentTarget, async () => {
      const ids = $$('input[type=checkbox]:checked', m).map(i => i.value);
      const next2 = clone(S.settings); next2.service = { ...(next2.service || {}), devices: ids.length === devs.length ? [] : ids };
      await saveSettings(next2, 'Saved'); next();
    }).catch(() => {});
  } else if (step === 3) {
    m.innerHTML = shell(`<h2>Where are the lights?</h2>
      <p class="muted">Sunrise and sunset are calculated for this spot, and the time zone sets daylight saving time.</p>
      <div id="locbox"></div>
      <div class="row"><button class="primary" id="wnext">Save and continue</button><button class="ghost" id="wback">Back</button></div>`);
    const loc = await locationEditor($('#locbox'));
    $('#wback').onclick = () => wizard(2);
    $('#wnext').onclick = e => busy(e.currentTarget, async () => {
      const next2 = clone(S.settings); next2.location = loc.value();
      if (!next2.location.latitude && !next2.location.longitude) throw new Error('Choose your town or enter latitude and longitude.');
      await saveSettings(next2); next();
    }).catch(() => {});
  } else if (step === 4) {
    const acct = await api('account');
    const urls = acct.addresses.map(ip => `${acct.scheme || 'http'}://${ip}:${acct.port}/`);
    m.innerHTML = shell(`<h2>Use it from your phone</h2>
      <p>Create your Administrator account so phones and other computers at home can sign in. You can add accounts for other people later (Settings › Accounts), as Editors or Viewers.</p>
      ${acct.password_set ? '<p class="callout ok">An account already exists.</p>' : `
      <label class="field">User name<input type="text" id="nuser" autocomplete="username" autocapitalize="none" spellcheck="false" value="admin" maxlength="64"></label>
      <label class="field">Password<input type="password" id="np1" autocomplete="new-password" placeholder="At least 8 characters"></label>
      <label class="field">Type it again<input type="password" id="np2" autocomplete="new-password"></label>`}
      ${urls.length ? `<p class="note">On your phone, connected to your home Wi-Fi, open ${urls.map(u => `<code>${esc(u)}</code>`).join(' or ')}. In Safari, tap Share › Add to Home Screen to get an app icon.</p>` : ''}
      <div class="row"><button class="primary" id="wnext">Continue</button>${acct.password_set ? '' : '<button class="ghost" id="wskip">Skip. I\u2019ll only use this computer</button>'}</div>`);
    if ($('#wskip')) $('#wskip').onclick = next;
    $('#wnext').onclick = e => busy(e.currentTarget, async () => {
      if (acct.password_set) return next();
      if ($('#np1').value !== $('#np2').value) throw new Error("The passwords don't match.");
      const r = await api('users', { body: { username: $('#nuser').value.trim().toLowerCase(), role: 'admin', password: $('#np1').value } });
      if (r.token) token.set(r.token);
      toast('Account created'); next();
    }).catch(() => {});
  } else {
    const n = clone(S.settings); n.setup_done = true; await saveSettings(n, 'Setup complete');
    m.innerHTML = shell(`<h2>You're set</h2>
      <p>The app now runs your lights. It already has starter patterns and a schedule (every night from 15 minutes after sunset until 11 PM, plus holiday seasons) that you can change on the Schedule tab.</p>
      <p class="callout"><b>One step in the Trimlight Edge app:</b> set the controller to <b>Manual</b> and turn off its own timers, so the two schedules don't fight.</p>
      <div class="row"><button class="primary" id="wdone">Go to Home</button></div>`);
    $('#wdone').onclick = () => go('home');
  }
}

/* ---------------------------------------------------------------- HOME */
VIEWS.home = async () => {
  const m = $('#main');
  m.innerHTML = `<div class="view"><p class="muted">Loading…</p></div>`;
  const render = st => {
    if (S.view !== 'home') return;
    if (st.setup_only) {
      m.innerHTML = `<div class="view">${(st.setup.warnings || []).map(w => `<p class="callout warn">${esc(w)}</p>`).join('')}<div class="panel stack"><h1 style="font-size:1.5rem">Almost ready</h1>
        <p>${esc(st.setup.problem || 'Finish setup to start the schedule.')}</p>
        <div class="row"><button class="primary" id="hwiz">Open setup</button></div></div></div>`;
      $('#hwiz').onclick = () => wizard(st.setup.credentials ? 3 : 1);
      return;
    }
    const t = st.target, nextTxt = st.next_change ? `${st.next_change}${st.next_change_day ? ' ' + st.next_change_day : ''}` : null;
    document.body.classList.toggle('lit', t.on);
    document.body.classList.toggle('flashing', t.reason === 'flash');
    let head = t.on ? 'The lights are on' : 'The lights are off', sub;
    if (t.reason === 'flash') { head = 'Security flash'; sub = `${t.effect} until ${st.flash.until}, then back to normal.`; }
    else if (t.reason === 'manual') sub = (t.on ? `${t.effect}, set by hand` : 'Turned off by hand') + (nextTxt ? `. The schedule takes over at ${nextTxt}.` : '.');
    else if (t.on && t.reason === 'weather') sub = `${t.source}: ${t.effect} until ${st.window.end}, instead of ${st.window.rule}.`;
    else if (t.on && st.window) sub = `${st.window.rule}: ${t.effect} until ${st.window.end}.` + (t.delegated ? ' The controller is running tonight from its own timer, so the lights go off on time even if this computer stops.' : '');
    else sub = nextTxt ? `Next on at ${nextTxt}.` : 'Nothing scheduled this week.';
    if (!t.applied && !st.error) sub += ' Sending…';
    const pct = v => (Math.max(0, Math.min(1440, v)) / 1440 * 100) + '%';
    const sm = st.sun_min, sky = [];
    const band = (a, b, c) => (a != null && b != null && b > a) && sky.push(`<div class="sky" style="left:${pct(a)};width:calc(${pct(b)} - ${pct(a)});background:${c}"></div>`);
    band(sm.dawn ?? sm.sunrise, sm.sunrise, 'var(--twilight)'); band(sm.sunrise, sm.sunset, 'var(--day)'); band(sm.sunset, sm.dusk ?? sm.sunset, 'var(--twilight)');
    st.strip.forEach(w => sky.push(`<div class="lit" title="${esc(w.rule)}" style="left:${pct(w.start)};width:calc(${pct(w.end)} - ${pct(w.start)})"></div>`));
    sky.push(`<div class="now" style="left:${pct(st.now_min)}"></div>`);
    const canAdjust = t.on && t.reason !== 'flash';
    const lv = st.levels;
    const wx = st.weather;
    let prevAbbr = null;
    const effects = Object.entries(S.settings.effects || {});
    m.innerHTML = `<div class="view">
      <div class="cols wide-left">
        <div class="stack">
          <div class="hero">${(st.setup?.warnings || []).map(w => `<div class="callout warn" style="margin-bottom:12px">${esc(w)} <button class="small" data-dismisswarn>Got it</button></div>`).join('')}
            ${st.setup?.problem ? `<p class="callout warn" style="margin-bottom:12px">${esc(st.setup.problem)}</p>` : ''}
            <h1>${esc(head)}</h1><p>${esc(sub)}</p>
            ${st.error ? `<p class="callout warn" style="margin-top:10px">Can't reach the lights right now: ${esc(st.error)}</p>` : ''}</div>
          <div><div class="strip" aria-label="Today, midnight to midnight">${sky.join('')}</div>
            <div class="ticks"><span style="left:0">12 AM</span><span style="left:25%">6 AM</span><span style="left:50%">Noon</span><span style="left:75%">6 PM</span><span style="left:100%">12 AM</span></div>
            <div class="legend"><span>Sunrise <b>${esc(st.sun.sunrise ?? '—')}</b></span><span>Sunset <b>${esc(st.sun.sunset ?? '—')}</b></span><span>Now <b>${esc(st.now_label)} ${esc(st.tz)}</b></span></div>
            ${wx ? `<p class="note" style="margin-top:6px">${!wx.fresh ? `Weather unavailable${wx.error ? ': ' + esc(wx.error) : ''}. Weather rules are paused.` : `Weather: ${esc(wx.summary)}${wx.match ? (wx.active ? `. ${esc(wx.match)} is running.` : `. Matches ${esc(wx.match)}.`) : '.'}`}</p>` : ''}
            ${st.rotation ? `<p class="note">${st.rotation.nightly ? `A different pattern each night: ${esc(st.rotation.labels.join(', '))}.` : `Rotating ${esc(st.rotation.labels.join(', '))} every ${st.rotation.minutes} min.`}</p>` : ''}
          </div>
          <div class="panel"><h2>Turn on</h2>
            <div class="chips">${effects.map(([k, e]) => `<button data-on="${esc(k)}" class="${t.on && t.effect_key === k ? 'current' : ''}">${swatches(effectSwatches(e), 4)}${esc(e.label || k)}</button>`).join('')}</div>
            <div class="row" style="margin-top:12px"><button data-act="off" class="ghost">Turn off</button>
              ${(st.override || lv.adjusted) ? '<button data-act="resume" class="ghost">Return to schedule</button>' : ''}
              ${st.flash.available ? `<button data-act="${st.flash.active ? 'stop_flash' : 'flash'}" class="ghost danger">${st.flash.active ? 'Stop flash' : `Security flash (${st.flash.minutes} min)`}</button>` : ''}</div>
          </div>
          <div class="panel"><h2>Brightness and speed</h2>
            <div class="levels" aria-disabled="${!canAdjust}" style="margin-top:12px">
              ${[['brightness', 'Brightness'], ['speed', 'Speed']].map(([k, l]) => `<label>${l}<input type="range" min="0" max="255" data-level="${k}" value="${lv[k] ?? 128}" ${!canAdjust || lv[k] == null ? 'disabled' : ''}><output>${lv[k] == null ? '—' : Math.round(lv[k] / 2.55) + '%'}</output></label>`).join('')}
            </div>
            <p class="note" style="margin-top:8px">${!t.on ? 'Turn the lights on to adjust them.' : t.reason === 'flash' ? 'Locked during the security flash.' : lv.brightness == null ? 'Levels appear once the controller reports this saved pattern.' : lv.adjusted ? 'Adjusted by hand until the next scheduled change.' : 'Changes last until the next scheduled change.'}</p>
          </div>
        </div>
        <div class="stack">
          <div class="panel"><div class="panel-head"><h2>This week</h2><button class="small ghost" data-tabjump="schedule">Edit schedule</button></div>
            <table class="week"><tbody>${st.days.map((d, i) => {
              const dst = prevAbbr && d.abbr !== prevAbbr ? ` <span class="dst">${esc(d.abbr)} starts</span>` : ''; prevAbbr = d.abbr;
              return `<tr class="${i === 0 ? 'today' : ''}"><td class="d">${i === 0 ? 'Today' : esc(d.dow)}<small>${esc(d.label)}</small></td>
                <td>${d.on ? `<span class="num">${esc(d.on)} – ${esc(d.off)}</span><div class="r">${esc(d.rule)}</div>` : '<span class="r">Off</span>'}${dst}</td>
                <td class="sun num">☀ ${esc(d.sunrise ?? '—')}<br>☾ ${esc(d.sunset ?? '—')}</td></tr>`; }).join('')}</tbody></table></div>
          <div class="panel"><details><summary>Controllers and activity</summary>
            <ul class="log">${st.devices.map(d => d.error ? `<li class="warning">${esc(d.error)}</li>` : `<li><b>${esc(d.name)}</b>: ${d.online ? 'online' : 'offline'}, ${esc(d.switch)}, firmware ${esc(d.firmware)}</li>`).join('')}</ul>
            <ul class="log">${st.events.map(e => `<li class="${esc(e.level)}"><time>${esc(e.label || e.t)}</time>${esc(e.msg)}</li>`).join('')}</ul>
          </details></div>
        </div>
      </div></div>`;
  };
  const act = async (body, btn) => busy(btn, async () => { S.status = await api('action', { body }); render(S.status); }).catch(() => {});
  m.onclick = e => {
    const b = e.target.closest('button'); if (!b) return;
    if (b.dataset.on) act({ action: 'on', effect: b.dataset.on }, b);
    else if (b.dataset.act) act({ action: b.dataset.act }, b);
    else if (b.dataset.tabjump) go(b.dataset.tabjump);
    else if (b.dataset.dismisswarn !== undefined) busy(b, () => api('warnings/dismiss', { body: {} })).then(async () => render(await refreshStatus())).catch(() => {});
  };
  m.oninput = e => { if (e.target.dataset.level) e.target.nextElementSibling.textContent = Math.round(e.target.value / 2.55) + '%'; };
  m.onchange = e => { if (e.target.dataset.level) act({ action: 'levels', [e.target.dataset.level]: Number(e.target.value) }); };
  render(await refreshStatus());
  S.timers.push(setInterval(async () => { if (!document.hidden && !$('#dlg').open && document.activeElement?.type !== 'range') render(await refreshStatus()); }, 30000));
};

/* ---------------------------------------------------------------- shared pattern helpers */
function usedBy(key) {
  const s = S.settings, out = [];
  (s.rules || []).forEach(r => { const e = Array.isArray(r.effect) ? r.effect : [r.effect]; if (e.includes(key)) out.push(`schedule rule “${r.name}”`); });
  (s.weather_rules || []).forEach(r => { const e = Array.isArray(r.effect) ? r.effect : [r.effect]; if (e.includes(key)) out.push(`weather rule “${r.name}”`); });
  if (s.security?.effect === key) out.push('the security flash');
  return out;
}
function fromController(e) {
  const base = { label: e.name };
  if (e.category === 0) return { ...base, builtin: e.mode, speed: e.speed ?? 100, brightness: e.brightness ?? 200, pixel_len: e.pixelLen || 30, reverse: !!e.reverse };
  const px = (e.pixels || []).filter(p => p.count > 0).sort((a, b) => a.index - b.index);
  if (e.category === 1 && px.length) return { ...base, colors: px.map(p => p.disable ? 'off' : hex(p.color)), counts: px.map(p => Math.min(90, p.count)), custom_mode: Math.min(16, e.mode || 0), speed: e.speed ?? 100, brightness: e.brightness ?? 200 };
  return { ...base, saved: e.name };
}
function totalBulbs() {
  const d = (S.devices || []).find(x => x.selected && x.ports) || (S.devices || []).find(x => x.ports);
  if (!d) return 100;
  const ends = d.ports.filter(p => p.end > 0).map(p => p.end);
  return ends.length ? Math.max(...ends) : 100;
}
function builtinDialog(def, onSave, title) {
  const isSaved = def.saved !== undefined;
  dialog(`<h2>${esc(title)}</h2>
    <label class="field">Name<input type="text" name="label" maxlength="40" required value="${esc(def.label || '')}"></label>
    ${isSaved ? '<p class="note">This pattern lives in the Trimlight app. Its colors are edited there.</p>' : `
    <p class="note">${esc(effectKind(def))}</p>
    <label class="field">Speed <input type="range" name="speed" min="0" max="255" value="${def.speed ?? 100}"></label>
    <label class="field">Brightness <input type="range" name="brightness" min="0" max="255" value="${def.brightness ?? 200}"></label>
    <label class="field">Sequencing spacing <span class="hint">The Trimlight app's third slider: how many bulbs one repeat covers (1–90)</span>
      <input type="number" name="pixel_len" min="1" max="90" value="${def.pixel_len ?? 30}"></label>
    <label class="check"><input type="checkbox" name="reverse" ${def.reverse ? 'checked' : ''}> Reverse direction</label>`}`,
  async f => {
    const label = f.label.value.trim(); if (!label) throw new Error('Give the pattern a name.');
    const out = { ...def, label };
    if (!isSaved) Object.assign(out, { speed: +f.speed.value, brightness: +f.brightness.value, pixel_len: Math.max(1, Math.min(90, +f.pixel_len.value || 30)), reverse: f.reverse.checked });
    await onSave(out);
  });
}
async function addPattern(def) {
  const n = clone(S.settings); n.effects = n.effects || {};
  const key = slug(def.label, n.effects); n.effects[key] = def;
  await saveSettings(n, `Added “${def.label}” to your patterns`);
  return key;
}

/* ---------------------------------------------------------------- PATTERNS */
VIEWS.patterns = async (tab) => {
  S.ptab = tab || S.ptab || 'mine';
  const m = $('#main');
  const head = `<div class="panel-head"><h2>Patterns</h2><div class="seg" role="group" aria-label="Pattern source">
    ${[['mine', 'My patterns'], ['controller', 'In the Trimlight app'], ['builtin', 'Built-in (180)']].map(([k, l]) => `<button data-ptab="${k}" aria-pressed="${S.ptab === k}">${l}</button>`).join('')}</div>
    <button class="primary" data-new>New pattern</button></div>`;
  m.innerHTML = `<div class="view">${head}<div id="pbody"><p class="muted">Loading…</p></div></div>`;
  const body = $('#pbody');
  const tryDef = (def, btn) => busy(btn, () => api('action', { body: { action: 'try', effect: def } })).then(() => toast(`Showing “${def.label}” for 15 minutes, then back to the schedule`)).catch(() => {});

  if (S.ptab === 'mine') {
    const effs = Object.entries(S.settings.effects || {});
    body.innerHTML = `<div class="cards">${effs.map(([k, e]) => `<div class="card">
      <div class="title"><b>${esc(e.label || k)}</b></div>
      ${e.colors ? strand(e.colors, e.counts) : strand(effectSwatches(e))}
      <p class="small muted">${esc(effectKind(e))}${usedBy(k).length ? ` · used by ${usedBy(k).length}` : ''}</p>
      <div class="actions"><button class="small" data-on="${esc(k)}">Turn on</button><button class="small ghost" data-edit="${esc(k)}">Edit</button><button class="small ghost danger" data-del="${esc(k)}">Delete</button></div>
    </div>`).join('')}</div>`;
  } else if (S.ptab === 'controller') {
    let devs;
    try { devs = await loadDevices(); } catch (e) { body.innerHTML = `<p class="callout warn">${esc(e.message)}</p>`; return; }
    const d = devs.find(x => x.selected && x.effects) || devs.find(x => x.effects);
    if (!d) { body.innerHTML = '<p class="callout">No controller reported its pattern library.</p>'; return; }
    S.ctrlEffects = d.effects;
    body.innerHTML = `<p class="note" style="margin-bottom:12px">Patterns saved in the Trimlight app on <b>${esc(d.name)}</b>. Add them to your patterns to use them in schedules.</p>
      <div class="cards">${d.effects.map((e, i) => { const def = fromController(e); return `<div class="card">
        <div class="title"><b>${esc(e.name)}</b></div>${def.colors ? strand(def.colors, def.counts) : strand(effectSwatches(def))}
        <p class="small muted">${esc(effectKind(def))}</p>
        <div class="actions"><button class="small" data-ctry="${i}">Try</button><button class="small ghost" data-cadd="${i}">Add to my patterns</button></div></div>`; }).join('')}</div>`;
  } else {
    S.bgroup = S.bgroup || 'All';
    const groups = ['All', ...S.catalog.groups];
    body.innerHTML = `<div class="panel stack"><div class="row"><input type="search" id="bq" placeholder="Search, e.g. red green" class="grow" style="max-width:340px" value="${esc(S.bq || '')}"></div>
      <div class="chips" role="group" aria-label="Effect group">${groups.map(g => `<button class="small ${S.bgroup === g ? 'current' : ''}" data-bgroup="${esc(g)}">${esc(g)}</button>`).join('')}</div>
      <div class="list" id="blist"></div></div>`;
    const draw = () => {
      const q = ($('#bq').value || '').toLowerCase().split(/\s+/).filter(Boolean);
      const list = S.catalog.builtin.filter(b => (S.bgroup === 'All' || b.group === S.bgroup) && q.every(w => b.name.toLowerCase().includes(w)));
      $('#blist').innerHTML = list.length ? list.map(b => `<div class="item"><span class="idx num">${b.mode}</span>${swatches(b.swatches)}
        <div class="grow"><div class="name">${esc(b.name)}</div><div class="sub">${esc(b.group)}</div></div>
        <button class="small" data-btry="${b.mode}">Try</button><button class="small ghost" data-badd="${b.mode}">Add</button></div>`).join('')
        : '<p class="muted">No built-in effects match.</p>';
    };
    draw();
    $('#bq').oninput = e => { S.bq = e.target.value; draw(); };
  }

  m.onclick = async e => {
    const b = e.target.closest('button'); if (!b) return;
    const d = b.dataset;
    if (d.ptab) return VIEWS.patterns(d.ptab);
    if (d.new) return go('create', {});
    if (d.bgroup) { S.bgroup = d.bgroup; return VIEWS.patterns('builtin'); }
    if (d.on) return busy(b, () => api('action', { body: { action: 'on', effect: d.on } })).then(() => toast('Turned on until the next scheduled change')).catch(() => {});
    if (d.edit) {
      const def = S.settings.effects[d.edit];
      if (def.colors) return go('create', { key: d.edit });
      return builtinDialog(def, async out => { const n = clone(S.settings); n.effects[d.edit] = out; await saveSettings(n); VIEWS.patterns(); }, 'Edit pattern');
    }
    if (d.del) {
      const users = usedBy(d.del);
      if (users.length) return confirmBox("Can't delete yet", `This pattern is used by ${esc(users.join(', '))}. Change those first.`, 'OK');
      if (!await confirmBox('Delete pattern?', `“${esc(S.settings.effects[d.del].label || d.del)}” will be removed from your patterns. Patterns in the Trimlight app aren't affected.`, 'Delete', true)) return;
      const n = clone(S.settings); delete n.effects[d.del];
      return busy(b, () => saveSettings(n, 'Deleted')).then(() => VIEWS.patterns()).catch(() => {});
    }
    if (d.ctry) return tryDef(fromController(S.ctrlEffects[+d.ctry]), b);
    if (d.cadd) { const def = fromController(S.ctrlEffects[+d.cadd]); return busy(b, () => addPattern(def)).catch(() => {}); }
    if (d.btry) { const bi = S.catalog.builtin.find(x => x.mode === +d.btry); return tryDef({ label: bi.name, builtin: bi.mode, speed: 128, brightness: 200, pixel_len: 30 }, b); }
    if (d.badd) { const bi = S.catalog.builtin.find(x => x.mode === +d.badd);
      return builtinDialog({ label: bi.name, builtin: bi.mode, speed: 128, brightness: 200, pixel_len: 30 }, async out => { await addPattern(out); }, 'Add built-in effect'); }
  };
};

/* ---------------------------------------------------------------- CREATE (designer) */
const lum = h => { if (h === 'off') return 0; const n = parseInt(h.slice(1), 16); return (0.299 * (n >> 16) + 0.587 * (n >> 8 & 255) + 0.114 * (n & 255)) / 255; };
VIEWS.create = async (opts = {}) => {
  if (opts.key !== undefined || !S.design || opts.fresh) {
    const def = opts.key ? S.settings.effects[opts.key] : null;
    S.design = def ? { key: opts.key, label: def.label || opts.key, segs: def.colors.map((c, i) => ({ c: c.toUpperCase(), n: (def.counts || [])[i] || 3 })),
      mode: def.custom_mode || 0, speed: def.speed ?? 100, brightness: def.brightness ?? 200, sel: 0 }
      : { key: null, label: '', segs: [{ c: '#FF0000', n: 4 }, { c: '#00FF00', n: 4 }, { c: '#FFFFFF', n: 4 }], mode: 0, speed: 100, brightness: 200, sel: 0 };
  }
  quiet(loadDevices());
  const D = S.design, m = $('#main');
  const def = () => ({ label: D.label.trim() || 'Untitled', colors: D.segs.map(s => s.c), counts: D.segs.map(s => s.n), custom_mode: D.mode, speed: D.speed, brightness: D.brightness });
  const render = () => {
    const s = D.segs[D.sel];
    m.innerHTML = `<div class="view"><div class="panel-head"><h2>${D.key ? 'Edit pattern' : 'Create a pattern'}</h2>
        ${D.key ? '<button class="ghost" data-newd>Start a new one</button>' : ''}</div>
      <div class="cols wide-left">
        <div class="stack">
          <div class="panel stack">
            <label class="field">Name<input type="text" id="dname" maxlength="40" placeholder="e.g. Candy cane" value="${esc(D.label)}"></label>
            ${D.paint ? `</div>${painterHtml(D)}<div hidden>` : ''}
            <div class="row" style="justify-content:space-between"><h3>Colors in order</h3>
              <span class="small ${D.segs.length > 30 ? 'callout warn' : 'muted'}">${D.segs.length} of 30 color slots</span></div>
            <div class="row"><button class="small ghost" data-paintbulbs>Paint bulbs</button><button class="small ghost" data-paintzones>Paint by zone</button><span class="note">Paint single bulbs, ranges or every Nth bulb, or color named sections of the house (zones from House map).</span></div>
            <div><p class="note">Each circle is one color; the number is how many bulbs it covers (up to 90). The sequence repeats along your roofline. Black is a dark color that moves with the pattern; ✕ zones bulbs off so they stay dark and are skipped by any movement, for example over a bedroom window.</p></div>
            <div class="segs">${D.segs.map((g, i) => `<button class="segbtn ${g.c === 'off' ? 'off' : ''}" data-seg="${i}" aria-pressed="${i === D.sel}" aria-label="${g.c === 'off' ? 'Zoned off' : 'Color ' + (i + 1)}, ${g.n} bulbs"
               style="${g.c === 'off' ? '' : `background:${g.c};`}color:${lum(g.c) > .55 ? '#111' : '#fff'}">${g.n}</button>`).join('')}
              ${D.segs.length < 30 ? '<button class="segbtn add" data-addseg aria-label="Add a color">+</button>' : ''}</div>
            ${s ? `<div class="stack" style="gap:10px"><h3>Selected color ${D.sel + 1}</h3>
              <div class="palette">${S.catalog.palette.map(p => `<button data-color="${p.hex}" title="${esc(p.name)}" aria-label="${esc(p.name)}" style="background:${p.hex}"></button>`).join('')}
                <button data-color="off" class="off" title="Zone off (✕): these bulbs stay dark and don't move" aria-label="Zone off"></button>
                <label class="custom" title="Any color"><input type="color" id="cpick" value="${s.c === 'off' ? '#000000' : s.c.toLowerCase()}" aria-label="Pick any color"></label></div>
              <div class="row"><span class="small">Bulbs</span><span class="stepper"><button data-n="-1" aria-label="Fewer">−</button>
                <input type="number" id="segn" min="1" max="90" value="${s.n}" aria-label="Bulbs for this color"><button data-n="1" aria-label="More">+</button></span>
                <button class="small ghost" data-mv="-1" ${D.sel === 0 ? 'disabled' : ''}>Move left</button><button class="small ghost" data-mv="1" ${D.sel === D.segs.length - 1 ? 'disabled' : ''}>Move right</button>
                <button class="small ghost danger" data-rm ${D.segs.length < 2 ? 'disabled' : ''}>Remove</button></div></div>` : ''}
          </div>
          <div class="panel stack">
            <label class="field">Animation<select id="dmode">${S.catalog.custom_modes.map((n, i) => `<option value="${i}" ${i === D.mode ? 'selected' : ''}>${esc(n)}</option>`).join('')}</select></label>
            ${D.mode >= 7 && D.mode <= 14 && D.segs.some(g => g.c !== 'off' && g.n <= 5) ? '<p class="callout small">Comet and Wave only run when each color covers more than 5 bulbs (Trimlight guide). Raise the colors set to 5 or fewer.</p>' : ''}
            ${(D.mode === 1 || D.mode === 2) && D.segs.filter(g => g.c !== 'off').every(g => g.n === 1) ? '<p class="note">Tip: a chase with 1 bulb per color runs very fast. Add black spaces or larger counts to slow it down.</p>' : ''}
            <label class="field">Speed<input type="range" id="dspeed" min="0" max="255" value="${D.speed}"></label>
            <label class="field">Brightness<input type="range" id="dbright" min="0" max="255" value="${D.brightness}"></label>
          </div>
        </div>
        <div class="stack">
          <div class="panel stack"><h3>Preview</h3><canvas class="preview" id="cv" height="160" aria-label="Animated preview of the pattern"></canvas>
            <p class="note" id="cvnote"></p></div>
          <div class="panel stack">
            <button data-try>Try on my lights</button>
            <label class="check"><input type="checkbox" id="alsoapp"> Also add it to the Trimlight app's library</label>
            <button class="primary" data-save>${D.key ? 'Save changes' : 'Save pattern'}</button>
            <p class="note">Saved patterns appear in Patterns, Home and the schedule editor.</p>
          </div>
        </div>
      </div></div>`;
    $('#dname').oninput = e => D.label = e.target.value;
    $('#dmode').onchange = e => { D.mode = +e.target.value; render(); };
    $('#dspeed').oninput = e => D.speed = +e.target.value;
    $('#dbright').oninput = e => D.brightness = +e.target.value;
    const cp = $('#cpick'); if (cp) cp.oninput = e => { D.segs[D.sel].c = e.target.value.toUpperCase(); repaintSegs(); };
    const sn = $('#segn'); if (sn) sn.onchange = e => { D.segs[D.sel].n = Math.max(1, Math.min(90, +e.target.value || 1)); render(); };
    // While painting, the preview shows the painted pattern (if it fits).
    const painted = D.paint && PT.compress(D.paint.canvas);
    startPreview($('#cv'), painted && painted.length <= PT.MAX_SLOTS ? { ...D, segs: painted } : D, $('#cvnote'));
    if (D.paint) painterDraw(D);
  };
  VIEWS.createRender = render;
  const repaintSegs = () => { const b = $(`[data-seg="${D.sel}"]`); if (b) { const g = D.segs[D.sel]; b.classList.toggle('off', g.c === 'off'); b.style.background = g.c === 'off' ? '' : g.c; b.style.color = lum(g.c) > .55 ? '#111' : '#fff'; } };
  m.onclick = async e => {
    const b = e.target.closest('button'); if (!b) return;
    const d = b.dataset;
    if (painterClick(D, d)) return;
    if (d.paintbulbs !== undefined) { painterOpen(D); render(); }
    else if (d.seg) { D.sel = +d.seg; render(); }
    else if (d.addseg !== undefined) { D.segs.push({ c: D.segs[D.sel]?.c || '#FFFFFF', n: 3 }); D.sel = D.segs.length - 1; render(); }
    else if (d.color) { D.segs[D.sel].c = d.color; render(); }
    else if (d.n) { const g = D.segs[D.sel]; g.n = Math.max(1, Math.min(90, g.n + +d.n)); render(); }
    else if (d.mv) { const j = D.sel + +d.mv; [D.segs[D.sel], D.segs[j]] = [D.segs[j], D.segs[D.sel]]; D.sel = j; render(); }
    else if (d.rm !== undefined) { D.segs.splice(D.sel, 1); D.sel = Math.max(0, D.sel - 1); render(); }
    else if (d.newd !== undefined) { VIEWS.create({ fresh: true }); }
    else if (d.paintzones !== undefined) zonePainter(D, render);
    else if (d.try !== undefined) busy(b, () => api('action', { body: { action: 'try', effect: def() } })).then(() => toast('Showing on your lights for 15 minutes, then back to the schedule')).catch(() => {});
    else if (d.save !== undefined) busy(b, async () => {
      const label = D.label.trim(); if (!label) { $('#dname').focus(); throw new Error('Give the pattern a name first.'); }
      const n = clone(S.settings); n.effects = n.effects || {};
      const key = D.key || slug(label, n.effects);
      n.effects[key] = { ...def(), label };
      await saveSettings(n, D.key ? 'Changes saved' : `Saved “${label}”`);
      D.key = key;
      if ($('#alsoapp').checked) { await api('device/save_effect', { body: { name: label.slice(0, 30), effect: def() } }); toast(`Saved “${label}” here and in the Trimlight app`); }
      render();
    }).catch(() => {});
  };
  m.onchange = e => { painterChange(D, e.target); };
  render();
};

/* Animated approximation of the controller's custom modes. */
function startPreview(cv, D, note) {
  const ctx = cv.getContext('2d'); const t0 = performance.now(); const view = S.view;
  const rgb = h => { const n = parseInt(h.slice(1), 16); return [n >> 16, n >> 8 & 255, n & 255]; };
  const frame = now => {
    if (S.view !== view || !cv.isConnected) return;
    const dpr = window.devicePixelRatio || 1, W = cv.clientWidth * dpr, H = 160 * dpr;
    if (cv.width !== W) { cv.width = W; cv.height = H; }
    const N = Math.min(totalBulbs(), 300), gap = 15 * dpr, perRow = Math.max(10, Math.floor((W - gap) / gap)), rows = Math.ceil(N / perRow);
    const rowH = Math.min(26 * dpr, (H - 8 * dpr) / rows);
    note.textContent = `${totalBulbs()} bulbs${totalBulbs() > 300 ? ' (first 300 shown)' : ''}. The preview approximates how the controller animates; outlined bulbs are zoned off.`;
    // Full layout (for zoned-off positions) and the moving content (everything else).
    const layout = []; D.segs.forEach(s => { for (let k = 0; k < s.n; k++) layout.push(s.c === 'off'); });
    const P = []; D.segs.forEach(s => { if (s.c !== 'off') for (let k = 0; k < s.n; k++) P.push(rgb(s.c)); });
    const LA = layout.length || 1;
    const L = P.length || 1, t = (now - t0) / 1000, rate = 2 + D.speed / 255 * 28, pos = t * rate, mode = D.mode;
    const bright = 0.25 + 0.75 * D.brightness / 255, half = (N - 1) / 2;
    ctx.clearRect(0, 0, W, H);
    let active = -1;
    for (let i = 0; i < N; i++) {
      const zoned = layout[i % LA];
      if (!zoned) active++;
      const ai = active;
      let c = P.length ? P[((ai % L) + L) % L] : [0, 0, 0], a = zoned || !P.length ? 0 : 1;
      const d = Math.abs(i - half), fl = Math.floor(pos);
      const idx = j => P[((j % L) + L) % L];
      if (zoned || !P.length) { /* stays dark */ }
      else if (mode === 1) c = idx(ai - fl); else if (mode === 2) c = idx(ai + fl);
      else if (mode === 3) c = idx(Math.round(d) - fl); else if (mode === 4) c = idx(Math.round(d) + fl);
      else if (mode === 5) { const r = Math.sin(i * 12.9898 + Math.floor(pos / 3) * 78.233) * 43758.5453; a = (r - Math.floor(r)) > .8 ? 1 : .18; }
      else if (mode === 6) a = .12 + .88 * (.5 - .5 * Math.cos(2 * Math.PI * t * rate / 40));
      else if (mode >= 7 && mode <= 10) {
        const span = mode <= 8 ? N + 14 : half + 14, head = pos % span;
        const x = mode === 7 ? i : mode === 8 ? N - 1 - i : mode === 9 ? d : half - d;
        const dist = head - x; a = dist >= 0 && dist < 14 ? 1 - dist / 14 : .05;
      } else if (mode >= 11 && mode <= 14) {
        const x = mode === 11 ? i : mode === 12 ? -i : mode === 13 ? d : -d;
        a = .15 + .85 * (.5 + .5 * Math.sin(2 * Math.PI * (x - pos) / 22));
      } else if (mode === 15) a = Math.floor(t * rate / 3) % 2 ? 1 : .04;
      else if (mode === 16) {
        const cols = D.segs.filter(s => s.c !== 'off').map(s => rgb(s.c)), k = (t * rate / 20) % cols.length, j = Math.floor(k), f = k - j;
        const A = cols[j], B = cols[(j + 1) % cols.length]; c = [0, 1, 2].map(n => A[n] + (B[n] - A[n]) * f);
      }
      a *= bright;
      const x = gap / 2 + (i % perRow) * gap + gap / 2, y = 4 * dpr + Math.floor(i / perRow) * rowH + rowH / 2;
      const r = Math.min(5 * dpr, rowH / 3);
      if (zoned) { ctx.strokeStyle = 'rgba(160,160,190,.35)'; ctx.lineWidth = dpr; ctx.beginPath(); ctx.arc(x, y, r, 0, 7); ctx.stroke(); continue; }
      ctx.fillStyle = `rgba(${c[0]},${c[1]},${c[2]},${a * .22})`; ctx.beginPath(); ctx.arc(x, y, r * 2, 0, 7); ctx.fill();
      ctx.fillStyle = `rgba(${c[0]},${c[1]},${c[2]},${Math.max(a, .06)})`; ctx.beginPath(); ctx.arc(x, y, r, 0, 7); ctx.fill();
    }
    requestAnimationFrame(frame);
  };
  requestAnimationFrame(frame);
}

/* ---------------------------------------------------------------- SCHEDULE */
const SUNK = { sunset: 'Sunset', dusk: 'Dusk (after sunset)', sunrise: 'Sunrise', dawn: 'Dawn (before sunrise)', clock: 'A set time' };
function parseT(s) {
  s = String(s || '').trim();
  let m = s.match(/^(sunrise|sunset|dawn|dusk)\s*(?:([+-])\s*(\d+))?/i);
  if (m) return { kind: m[1].toLowerCase(), off: (m[2] === '-' ? -1 : 1) * (+m[3] || 0) };
  m = s.match(/^(\d{1,2}):(\d{2})\s*(am|pm)?$/i);
  if (m) { let h = +m[1]; if (m[3]) h = (h % 12) + (m[3].toLowerCase() === 'pm' ? 12 : 0); return { kind: 'clock', time: `${String(h % 24).padStart(2, '0')}:${m[2]}` }; }
  return { kind: 'sunset', off: 0 };
}
const buildT = t => t.kind === 'clock' ? t.time : (t.off ? `${t.kind} ${t.off < 0 ? '-' : '+'} ${Math.abs(t.off)}` : t.kind);
function humanT(s) {
  const t = parseT(s);
  if (t.kind === 'clock') return hm12(t.time);
  const name = t.kind[0].toUpperCase() + t.kind.slice(1);
  return t.off ? `${name} ${t.off < 0 ? '−' : '+'} ${Math.abs(t.off)} min` : name;
}
function humanDates(r) {
  if (!r.dates) return 'All year';
  const [a, b] = String(r.dates).split('..'); const f = x => { const [mo, d] = x.split('-').map(Number); return `${MONTHS[mo - 1]} ${d}`; };
  return b ? `${f(a)} – ${f(b)}` : f(a);
}
function humanDays(days) {
  if (!days || days === 'all' || days === 'everyday') return 'Every day';
  if (days === 'weekdays') return 'Weekdays'; if (days === 'weekends') return 'Weekends';
  const set = new Set(days.map(d => d.slice(0, 3).toLowerCase()));
  if (set.size === 7) return 'Every day';
  return DAYS.filter(d => set.has(d)).map(d => DAYNAMES[d]).join(', ');
}
const effLabel = k => S.settings.effects?.[k]?.label || k;
const prio = r => r.priority ?? (r.dates ? 200 : 100);
const prioLabel = p => p >= 200 ? 'Holiday' : p >= 150 ? 'High' : p >= 100 ? 'Everyday' : 'Low';
function timeField(name, label, val) {
  const t = parseT(val);
  return `<fieldset class="stack" style="border:1px solid var(--line);border-radius:12px;padding:12px;gap:8px"><legend class="small" style="font-weight:650;padding:0 4px">${label}</legend>
    <select name="${name}_kind" data-tkind="${name}">${Object.entries(SUNK).map(([k, l]) => `<option value="${k}" ${k === t.kind ? 'selected' : ''}>${l}</option>`).join('')}</select>
    <div class="row" data-tsun="${name}" ${t.kind === 'clock' ? 'hidden' : ''}><input type="number" name="${name}_off" min="-240" max="240" value="${t.off || 0}" aria-label="Minutes offset"><span class="small muted">minutes (use − for before)</span></div>
    <input type="time" name="${name}_time" data-tclock="${name}" value="${t.time || '23:00'}" ${t.kind === 'clock' ? '' : 'hidden'} aria-label="Time"></fieldset>`;
}
function patternPicker(selected, rotate, nightly = false, allowNightly = true) {
  const keys = Object.keys(S.settings.effects || {});
  const opts = v => keys.map(k => `<option value="${esc(k)}" ${k === v ? 'selected' : ''}>${esc(effLabel(k))}</option>`).join('');
  const list = (Array.isArray(selected) ? selected : [selected]).filter(Boolean);
  if (!list.length) list.push(keys[0]);
  return `<div class="stack" style="gap:8px" data-picker><span class="small" style="font-weight:650">Pattern${list.length > 1 ? 's (rotate in this order)' : ''}</span>
    ${list.map(v => `<div class="row" data-prow><select name="pattern" class="grow" style="flex:1">${opts(v)}</select>${list.length > 1 ? '<button type="button" class="small ghost" data-prm aria-label="Remove">✕</button>' : ''}</div>`).join('')}
    <div class="row"><button type="button" class="small ghost" data-padd>Add a pattern to rotate</button></div>
    <div class="stack" style="gap:6px" ${list.length > 1 ? '' : 'hidden'} data-rot>
      <label class="check"><input type="radio" name="rotmode" value="minutes" ${!nightly || !allowNightly ? 'checked' : ''}><span class="row small" style="gap:6px">Switch every <input type="number" name="rotate" min="1" max="720" value="${rotate || 15}" style="width:5.5em"> minutes</span></label>
      ${allowNightly ? `<label class="check"><input type="radio" name="rotmode" value="nightly" ${nightly ? 'checked' : ''}><span class="small">A different one each night, in this order</span></label>` : ''}</div></div>`;
}
function wirePicker(form) {
  form.addEventListener('click', e => {
    const b = e.target.closest('button'); if (!b) return;
    const pk = $('[data-picker]', form);
    const cur = $$('select[name=pattern]', form).map(s => s.value), rot = form.rotate?.value;
    const nightly = $('input[name=rotmode]:checked', form)?.value === 'nightly', allow = !!$('input[name=rotmode][value=nightly]', form) || form.dataset.nightly === '1';
    if (b.dataset.padd !== undefined) { cur.push(cur[cur.length - 1]); pk.outerHTML = patternPicker(cur, rot, nightly, allow); }
    if (b.dataset.prm !== undefined) { const i = $$('[data-prow]', form).indexOf(b.closest('[data-prow]')); cur.splice(i, 1); pk.outerHTML = patternPicker(cur, rot, nightly, allow); }
  });
  form.addEventListener('change', e => {
    const k = e.target.dataset.tkind;
    if (k) { const clock = e.target.value === 'clock'; $(`[data-tsun="${k}"]`, form).hidden = clock; $(`[data-tclock="${k}"]`, form).hidden = !clock; }
  });
}
function readPicker(form, out) {
  const pats = $$('select[name=pattern]', form).map(s => s.value);
  if (!pats.length || !pats[0]) throw new Error('Create a pattern first (Create tab).');
  delete out.rotate; delete out.rotate_minutes;
  if (pats.length > 1) {
    out.effect = pats;
    if ($('input[name=rotmode]:checked', form)?.value === 'nightly') out.rotate = 'nightly';
    else out.rotate_minutes = Math.max(1, +form.rotate.value || 15);
  } else out.effect = pats[0];
}
const readT = (f, n) => buildT(f[n + '_kind'].value === 'clock' ? { kind: 'clock', time: f[n + '_time'].value || '23:00' } : { kind: f[n + '_kind'].value, off: +f[n + '_off'].value || 0 });
function mdSelect(name, val) {
  const [mo, d] = (val || '12-01').split('-').map(Number);
  return `<span class="row" style="gap:6px"><select name="${name}_m" style="width:auto">${MONTHS.map((x, i) => `<option value="${i + 1}" ${i + 1 === mo ? 'selected' : ''}>${x}</option>`).join('')}</select>
    <input type="number" name="${name}_d" min="1" max="31" value="${d}" style="width:5em" aria-label="Day"></span>`;
}

function ruleDialog(idx) {
  const rules = S.settings.rules || [];
  const r = idx === undefined ? { name: '', on: 'sunset + 15', off: '23:00', effect: Object.keys(S.settings.effects || {})[0] } : rules[idx];
  const [ds, de] = r.dates ? String(r.dates).split('..') : ['12-01', '12-31'];
  const days = !r.days || r.days === 'all' ? DAYS : r.days === 'weekdays' ? DAYS.slice(0, 5) : r.days === 'weekends' ? DAYS.slice(5) : r.days.map(x => x.slice(0, 3).toLowerCase());
  const p = r.priority;
  const form = dialog(`<h2>${idx === undefined ? 'New schedule rule' : 'Edit rule'}</h2>
    <label class="field">Name<input type="text" name="name" maxlength="50" required value="${esc(r.name)}" placeholder="e.g. Christmas season"></label>
    <div class="stack" style="gap:8px"><span class="small" style="font-weight:650">When in the year</span>
      <label class="check"><input type="radio" name="season" value="all" ${!r.dates ? 'checked' : ''}> All year</label>
      <label class="check"><input type="radio" name="season" value="range" ${r.dates ? 'checked' : ''}> Only between</label>
      <div class="row" data-range ${r.dates ? '' : 'hidden'}>${mdSelect('ds', ds)}<span class="muted">and</span>${mdSelect('de', de || ds)}</div>
      <p class="hint" data-range ${r.dates ? '' : 'hidden'}>Ranges can cross New Year, like Nov 27 – Jan 6.</p></div>
    <div class="stack" style="gap:8px"><span class="small" style="font-weight:650">Days of the week</span>
      <div class="chips">${DAYS.map(d => `<label class="check" style="gap:6px"><input type="checkbox" name="day" value="${d}" ${days.includes(d) ? 'checked' : ''}>${DAYNAMES[d]}</label>`).join('')}</div></div>
    <div class="cols" style="gap:10px">${timeField('on', 'Turn on at', r.on)}${timeField('off', 'Turn off at', r.off)}</div>
    <p class="hint">If the off time is earlier than the on time, it means the next morning. Sunrise as the off time uses the next morning's real sunrise.</p>
    ${patternPicker(r.effect, r.rotate_minutes, r.rotate === 'nightly', true)}
    <label class="check"><input type="checkbox" name="usebright" ${r.brightness !== undefined ? 'checked' : ''}> Use its own brightness</label>
    <input type="range" name="brightness" min="0" max="255" value="${r.brightness ?? 120}" ${r.brightness !== undefined ? '' : 'hidden'} aria-label="Brightness">
    <label class="field">When rules overlap, this one is
      <select name="prio">${[[200, 'Holiday: beats everyday rules (200)'], [100, 'Everyday (100)'], [90, 'Low: only when nothing else is on (90)'], ['custom', 'Custom number…']]
        .map(([v, l]) => `<option value="${v}" ${(p === undefined ? '' : (p === 200 || p === 100 || p === 90 ? p : 'custom')) == v ? 'selected' : ''}>${l}</option>`).join('')}
        <option value="" ${p === undefined ? 'selected' : ''}>Automatic (holiday if it has dates)</option></select></label>
    <input type="number" name="prio_n" min="0" max="999" value="${p ?? 150}" ${p !== undefined && ![200, 100, 90].includes(p) ? '' : 'hidden'} aria-label="Priority number">`,
  async f => {
    const out = { name: f.name.value.trim() };
    if (!out.name) throw new Error('Give the rule a name.');
    if (rules.some((x, i) => i !== idx && x.name === out.name)) throw new Error('Another rule already has that name.');
    if (f.season.value === 'range') {
      const md = n => `${String(f[n + '_m'].value).padStart(2, '0')}-${String(Math.max(1, Math.min(31, +f[n + '_d'].value || 1))).padStart(2, '0')}`;
      out.dates = `${md('ds')}..${md('de')}`;
    }
    const dsel = $$('input[name=day]:checked', f).map(x => x.value);
    if (!dsel.length) throw new Error('Pick at least one day.');
    if (dsel.length < 7) out.days = dsel;
    out.on = readT(f, 'on'); out.off = readT(f, 'off');
    readPicker(f, out);
    if (f.usebright.checked) out.brightness = +f.brightness.value;
    if (f.prio.value === 'custom') out.priority = +f.prio_n.value || 0; else if (f.prio.value !== '') out.priority = +f.prio.value;
    const n = clone(S.settings); n.rules = n.rules || [];
    if (idx === undefined) n.rules.push(out); else n.rules[idx] = out;
    await saveSettings(n, 'Schedule saved'); VIEWS.schedule();
  }, { onOpen: f => {
    f.dataset.nightly = '1';
    wirePicker(f);
    f.addEventListener('change', e => {
      if (e.target.name === 'season') $$('[data-range]', f).forEach(x => x.hidden = e.target.value !== 'range');
      if (e.target.name === 'usebright') f.brightness.hidden = !e.target.checked;
      if (e.target.name === 'prio') f.prio_n.hidden = e.target.value !== 'custom';
    });
  } });
  return form;
}

const WX = [['snow', 'Snow'], ['rain', 'Rain'], ['storm', 'Thunderstorm'], ['fog', 'Fog'], ['wind', 'Windy'], ['cloudy', 'Cloudy'], ['clear', 'Clear'], ['freezing', 'Freezing (32°F or below)']];
function weatherDialog(idx) {
  const list = S.settings.weather_rules || [];
  const r = idx === undefined ? { name: '', when: ['snow'], effect: Object.keys(S.settings.effects || {})[0], priority: 150 } : list[idx];
  const when = Array.isArray(r.when) ? r.when : r.when ? [r.when] : [];
  dialog(`<h2>${idx === undefined ? 'New weather rule' : 'Edit weather rule'}</h2>
    <label class="field">Name<input type="text" name="name" maxlength="50" value="${esc(r.name)}" placeholder="e.g. Snowing"></label>
    <div class="stack" style="gap:8px"><span class="small" style="font-weight:650">When the weather is any of</span>
      <div class="chips">${WX.map(([k, l]) => `<label class="check" style="gap:6px"><input type="checkbox" name="when" value="${k}" ${when.includes(k) ? 'checked' : ''}>${l}</label>`).join('')}</div></div>
    <div class="row"><label class="field">Colder than (°F)<input type="number" name="below_f" value="${r.below_f ?? ''}" placeholder="optional"></label>
      <label class="field">Warmer than (°F)<input type="number" name="above_f" value="${r.above_f ?? ''}" placeholder="optional"></label></div>
    ${patternPicker(r.effect, r.rotate_minutes, false, false)}
    <label class="field">Priority <span class="hint">Weather only replaces a scheduled rule with a lower number. 150 beats everyday rules (100) but not holidays (200).</span>
      <input type="number" name="priority" min="0" max="999" value="${r.priority ?? 150}"></label>`,
  async f => {
    const out = { name: f.name.value.trim() || 'Weather', when: $$('input[name=when]:checked', f).map(x => x.value), priority: +f.priority.value || 150 };
    if (f.below_f.value !== '') out.below_f = +f.below_f.value;
    if (f.above_f.value !== '') out.above_f = +f.above_f.value;
    if (!out.when.length && out.below_f === undefined && out.above_f === undefined) throw new Error('Pick a condition or a temperature.');
    readPicker(f, out);
    const n = clone(S.settings); n.weather_rules = n.weather_rules || [];
    if (idx === undefined) n.weather_rules.push(out); else n.weather_rules[idx] = out;
    await saveSettings(n, 'Weather rule saved'); VIEWS.schedule();
  }, { onOpen: wirePicker });
}

async function importFromApp() {
  const devs = await loadDevices(true);
  const d = devs.find(x => x.selected && x.effects) || devs.find(x => x.effects);
  if (!d) throw new Error('No controller reported its timers.');
  const byId = Object.fromEntries((d.effects || []).map(e => [e.id, e]));
  const found = [];
  const hhmm = t => `${String((t.hours || 0) % 24).padStart(2, '0')}:${String((t.minutes || 0) % 60).padStart(2, '0')}`;
  (d.calendar || []).forEach(c => byId[c.effectId] && found.push({ src: byId[c.effectId], rule: { name: `${byId[c.effectId].name} (from app calendar)`,
    dates: `${String(c.startDate.month).padStart(2, '0')}-${String(c.startDate.day).padStart(2, '0')}..${String(c.endDate.month).padStart(2, '0')}-${String(c.endDate.day).padStart(2, '0')}`,
    on: hhmm(c.startTime), off: hhmm(c.endTime) } }));
  (d.daily || []).filter(x => x.enable && [1, 2, 3].includes(x.repetition)).forEach(x => byId[x.effectId] && found.push({ src: byId[x.effectId], rule: {
    name: `${byId[x.effectId].name} (from app daily timer ${x.id + 1})`, ...(x.repetition === 2 ? { days: 'weekdays' } : x.repetition === 3 ? { days: 'weekends' } : {}),
    on: hhmm(x.startTime), off: hhmm(x.endTime) } }));
  if (!found.length) return confirmBox('Nothing to import', 'The Trimlight app has no enabled timers or calendar entries on this controller (rotating “combined” timers can\u2019t be imported).', 'OK');
  dialog(`<h2>Import timers from the Trimlight app</h2><p class="note">Fixed clock times come across as they are. Afterward you can switch them to sunset-based times.</p>
    <div class="stack">${found.map((x, i) => `<label class="check"><input type="checkbox" name="pick" value="${i}" checked><span><b>${esc(x.rule.name)}</b><br>
      <span class="small muted">${esc(humanDates(x.rule))}, ${esc(humanDays(x.rule.days))}, ${esc(hm12(x.rule.on))} to ${esc(hm12(x.rule.off))}</span></span></label>`).join('')}</div>`,
  async f => {
    const n = clone(S.settings); n.effects = n.effects || {}; n.rules = n.rules || [];
    for (const i of $$('input[name=pick]:checked', f).map(x => +x.value)) {
      const { src, rule } = found[i];
      let key = Object.keys(n.effects).find(k => n.effects[k].label === src.name);
      if (!key) { key = slug(src.name, n.effects); n.effects[key] = fromController(src); }
      let name = rule.name, k = 2; while (n.rules.some(r => r.name === name)) name = `${rule.name} ${k++}`;
      n.rules.push({ ...rule, name, effect: key });
    }
    await saveSettings(n, 'Imported'); VIEWS.schedule();
  }, { ok: 'Import' });
}

VIEWS.schedule = async () => {
  const m = $('#main'), s = S.settings;
  const rules = (s.rules || []).map((r, i) => ({ r, i })).sort((a, b) => prio(b.r) - prio(a.r) || a.i - b.i);
  const effs = s.effects || {};
  m.innerHTML = `<div class="view">
    <div class="panel-head"><h2>Schedule</h2><button class="ghost" data-import>Import from Trimlight app</button><button class="primary" data-addrule>Add a rule</button></div>
    <div class="cols wide-left">
      <div class="stack">
        <div class="panel"><h2>Rules</h2><p class="note" style="margin-top:4px">When rules overlap, the higher one in this list wins.</p>
          <div class="list" style="margin-top:8px">${rules.length ? rules.map(({ r, i }) => { const pats = Array.isArray(r.effect) ? r.effect : [r.effect];
            return `<div class="item"><div class="grow" data-rulename="${esc(r.name)}"><div class="row" style="gap:8px"><span class="name">${esc(r.name)}</span><span class="badge ${prio(r) >= 200 ? 'hi' : ''}">${prioLabel(prio(r))} · ${prio(r)}</span></div>
              <div class="sub">${esc(humanDates(r))} · ${esc(humanDays(r.days))} · ${esc(humanT(r.on))} → ${esc(humanT(r.off))}</div>
              <div class="sub">${swatches(effectSwatches(effs[pats[0]]), 4)} ${esc(pats.map(effLabel).join(' / '))}${pats.length > 1 ? (r.rotate === 'nightly' ? ', a different one each night' : `, every ${r.rotate_minutes} min`) : ''}${r.brightness !== undefined ? `, brightness ${Math.round(r.brightness / 2.55)}%` : ''}</div></div>
              <button class="small ghost" data-editrule="${i}">Edit</button><button class="small ghost danger" data-delrule="${i}" aria-label="Delete ${esc(r.name)}">Delete</button></div>`; }).join('')
            : '<p class="muted">No rules yet. Add one to turn the lights on automatically.</p>'}</div></div>
        <div class="panel stack"><div class="panel-head"><h2>Weather</h2><label class="check"><input type="checkbox" id="wxon" ${s.weather?.enabled ? 'checked' : ''}> On</label></div>
          <p class="note">Uses the US National Weather Service. Weather only changes the pattern while a rule has the lights on.</p>
          <div class="list">${(s.weather_rules || []).map((r, i) => { const pats = Array.isArray(r.effect) ? r.effect : [r.effect]; const w = Array.isArray(r.when) ? r.when : r.when ? [r.when] : [];
            return `<div class="item"><div class="grow"><div class="row" style="gap:8px"><span class="name">${esc(r.name)}</span><span class="badge">${r.priority ?? 150}</span></div>
              <div class="sub">${esc([...w.map(x => (WX.find(y => y[0] === x) || [0, x])[1]), r.below_f !== undefined ? `below ${r.below_f}°F` : '', r.above_f !== undefined ? `above ${r.above_f}°F` : ''].filter(Boolean).join(', '))} → ${esc(pats.map(effLabel).join(' / '))}</div></div>
              <button class="small ghost" data-editwx="${i}">Edit</button><button class="small ghost danger" data-delwx="${i}">Delete</button></div>`; }).join('') || '<p class="muted">No weather rules.</p>'}</div>
          <div class="row"><button class="small" data-addwx>Add a weather rule</button>
            <label class="row small">Check with<select id="wxuse" style="width:auto">${[['either', 'now or next hour'], ['observed', 'current conditions'], ['forecast', 'next-hour forecast']].map(([k, l]) => `<option value="${k}" ${(s.weather?.use || 'either') === k ? 'selected' : ''}>${l}</option>`).join('')}</select></label></div>
        </div>
        <div class="panel stack"><h2>Security flash</h2><p class="note">Bright lights on demand from Home, a webhook or Home Assistant, then back to normal.</p>
          <div class="row"><label class="field grow">Pattern<select id="secp"><option value="">Off</option>${Object.keys(effs).map(k => `<option value="${esc(k)}" ${s.security?.effect === k ? 'selected' : ''}>${esc(effLabel(k))}</option>`).join('')}</select></label>
            <label class="field">Minutes<input type="number" id="secm" min="1" max="240" value="${s.security?.minutes ?? 5}"></label></div>
          <div><button class="small" data-savesec>Save</button></div></div>
        <div class="panel stack" id="safetybox"><p class="muted">Loading…</p></div>
      </div>
      <div class="panel"><h2>Coming up</h2><div id="upc" class="list" style="margin-top:8px"><p class="muted">Loading…</p></div></div>
    </div></div>`;
  safetyPanel($('#safetybox'));
  api('rulecheck').then(rc => { for (const [name, info] of Object.entries(rc)) {
    if (!info.blocked_by) continue;
    const el = $$('[data-rulename]', m).find(x => x.dataset.rulename === name);
    if (el) el.insertAdjacentHTML('beforeend', `<div class="callout warn small" style="margin-top:6px">Never runs in the next year: \u201c${esc(info.blocked_by)}\u201d wins on all its nights. ${esc(info.hint)}</div>`);
  } }).catch(() => {});
  api('upcoming?days=21').then(list => {
    $('#upc').innerHTML = list.length ? list.map(d => `<div class="item"><div style="width:5.5em" class="small"><b>${esc(new Date(d.date + 'T12:00').toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' }))}</b></div>
      <div class="grow">${d.on ? `<div class="num">${esc(hm12(d.on_label))} – ${esc(hm12(d.off_label))}</div><div class="sub">${esc(d.rule)}</div>` : '<span class="sub">Off</span>'}
        ${d.dst_change ? `<div class="dst">${esc(d.abbr)} starts today</div>` : ''}</div><div class="sub num">☾ ${esc(hm12(d.sunset))}</div></div>`).join('')
      : '<p class="muted">Finish setup to see upcoming times.</p>';
  }).catch(e => { $('#upc').innerHTML = `<p class="muted">${esc(e.message)}</p>`; });
  m.onclick = async e => {
    const b = e.target.closest('button'); if (!b) return; const d = b.dataset;
    if (d.addrule !== undefined) { if (!Object.keys(effs).length) return toast('Create a pattern first.', true); ruleDialog(); }
    else if (d.editrule) ruleDialog(+d.editrule);
    else if (d.delrule) { if (await confirmBox('Delete rule?', `“${esc(s.rules[+d.delrule].name)}” will be removed.`, 'Delete', true)) { const n = clone(s); n.rules.splice(+d.delrule, 1); await busy(null, () => saveSettings(n, 'Deleted')).catch(() => {}); VIEWS.schedule(); } }
    else if (d.addwx !== undefined) weatherDialog();
    else if (d.editwx) weatherDialog(+d.editwx);
    else if (d.delwx) { const n = clone(s); n.weather_rules.splice(+d.delwx, 1); await busy(b, () => saveSettings(n, 'Deleted')).catch(() => {}); VIEWS.schedule(); }
    else if (d.savesec !== undefined) { const n = clone(s); n.security = { effect: $('#secp').value || null, minutes: Math.max(1, Math.min(240, +$('#secm').value || 5)) }; busy(b, () => saveSettings(n)).catch(() => {}); }
    else if (d.import !== undefined) busy(b, importFromApp).catch(() => {});
  };
  m.onchange = e => {
    if (e.target.id === 'wxon' || e.target.id === 'wxuse') {
      const n = clone(S.settings); n.weather = { ...(n.weather || {}), enabled: $('#wxon').checked, use: $('#wxuse').value };
      busy(null, () => saveSettings(n, n.weather.enabled ? 'Weather rules on' : 'Weather rules off')).catch(() => {});
    }
  };
};

/* ---------------------------------------------------------------- location editor (wizard + Date & Time) */
async function locationEditor(box) {
  const loc = { latitude: 0, longitude: 0, timezone: 'America/New_York', dst_mode: 'auto', ...(S.settings.location || {}) };
  const tzs = await api('timezones');
  box.innerHTML = `<div class="stack">
    <div class="row"><input type="search" id="lq" placeholder="Search your town, e.g. Media, PA" class="grow" style="flex:1;min-width:200px">
      <button type="button" id="lgo">Search</button>${window.isSecureContext && navigator.geolocation ? '<button type="button" class="ghost" id="lgeo">Use this device\u2019s location</button>' : ''}</div>
    <div class="results" id="lres"></div>
    <div class="row"><label class="field grow">Latitude<input type="number" step="0.0001" id="llat" value="${loc.latitude || ''}" placeholder="39.9"></label>
      <label class="field grow">Longitude<input type="number" step="0.0001" id="llon" value="${loc.longitude || ''}" placeholder="-75.4"></label></div>
    <p class="hint" style="margin-top:-4px">In the Americas, longitude is negative (for example −75.4).</p>
    <label class="field">Time zone<select id="ltz"><optgroup label="Common">${tzs.common.map(z => `<option value="${z}" ${z === loc.timezone ? 'selected' : ''}>${z.replace(/_/g, ' ')}</option>`).join('')}</optgroup>
      <optgroup label="All time zones">${tzs.all.filter(z => !tzs.common.includes(z)).map(z => `<option value="${z}" ${z === loc.timezone ? 'selected' : ''}>${z.replace(/_/g, ' ')}</option>`).join('')}</optgroup></select></label>
    <div class="stack" style="gap:8px"><span class="small" style="font-weight:650">Daylight saving time</span>
      <div class="radio-cards">
        <label><input type="radio" name="dst" value="auto" ${loc.dst_mode === 'auto' ? 'checked' : ''}><span><b>Automatic (recommended)</b><br><span class="small muted" id="dstinfo">Follows the official rules for this time zone.</span></span></label>
        <label><input type="radio" name="dst" value="on" ${loc.dst_mode === 'on' ? 'checked' : ''}><span><b>Always daylight saving time</b><br><span class="small muted">Clock stays one hour ahead of standard time all year.</span></span></label>
        <label><input type="radio" name="dst" value="off" ${loc.dst_mode === 'off' ? 'checked' : ''}><span><b>Always standard time</b><br><span class="small muted">Never moves the clock forward in spring. (Arizona and Hawaii are already handled by Automatic.)</span></span></label>
      </div></div></div>`;
  const tzInfo = async () => {
    try {
      const i = await api('tzinfo?name=' + encodeURIComponent($('#ltz', box).value));
      $('#dstinfo', box).textContent = !i.has_dst ? `This time zone doesn't use daylight saving time (${i.std_abbr} all year).`
        : `Now ${i.abbr_now}. Next change ${new Date(i.next_change.at.slice(0, 10) + 'T12:00').toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' })}: clocks go from ${hm12(i.next_change.clock_from)} to ${hm12(i.next_change.clock_to)} (${i.next_change.from} → ${i.next_change.to}).`;
    } catch { /* ignore */ }
  };
  tzInfo();
  $('#ltz', box).onchange = tzInfo;
  const search = () => busy($('#lgo', box), async () => {
    const r = await api('geocode?q=' + encodeURIComponent($('#lq', box).value));
    $('#lres', box).innerHTML = r.length ? r.map((x, i) => `<button type="button" data-pick="${i}">${esc([x.name, x.region, x.country].filter(Boolean).join(', '))} <span class="muted small">${x.lat}, ${x.lon}</span></button>`).join('')
      : '<p class="muted small">No places found. Try the nearest larger town.</p>';
    $('#lres', box).onclick = e => { const b = e.target.closest('[data-pick]'); if (!b) return; const x = r[+b.dataset.pick];
      $('#llat', box).value = x.lat; $('#llon', box).value = x.lon;
      if (x.timezone && [...$('#ltz', box).options].some(o => o.value === x.timezone)) { $('#ltz', box).value = x.timezone; tzInfo(); }
      $('#lres', box).innerHTML = `<p class="callout ok small">Using ${esc([x.name, x.region].filter(Boolean).join(', '))}.</p>`; };
  }).catch(() => {});
  $('#lgo', box).onclick = search;
  $('#lq', box).addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); search(); } });
  const geo = $('#lgeo', box);
  if (geo) geo.onclick = () => navigator.geolocation.getCurrentPosition(p => {
    $('#llat', box).value = p.coords.latitude.toFixed(4); $('#llon', box).value = p.coords.longitude.toFixed(4);
    const z = Intl.DateTimeFormat().resolvedOptions().timeZone; if ([...$('#ltz', box).options].some(o => o.value === z)) { $('#ltz', box).value = z; tzInfo(); }
  }, () => toast("Location wasn't shared.", true));
  return { value: () => ({ latitude: +$('#llat', box).value || 0, longitude: +$('#llon', box).value || 0, timezone: $('#ltz', box).value,
    dst_mode: $('input[name=dst]:checked', box)?.value || 'auto' }) };
}

/* ---------------------------------------------------------------- LIGHTS (ports, bulbs, LED type) */
VIEWS.lights = async (opts = {}) => {
  const m = $('#main');
  if (!opts.keep) { S.portDraft = null; m.innerHTML = '<div class="view"><h2>Lights</h2><p class="muted">Asking the controller…</p></div>'; }
  let devs;
  try { devs = await loadDevices(!opts.keep); } catch (e) { m.innerHTML = `<div class="view"><h2>Lights</h2><p class="callout warn">${esc(e.message)}</p></div>`; return; }
  if (!devs.length) { m.innerHTML = '<div class="view"><h2>Lights</h2><p class="callout">No controllers on this account.</p></div>'; return; }
  S.lightDev = devs.some(d => d.id === S.lightDev) ? S.lightDev : (devs.find(d => d.selected) || devs[0]).id;
  const d = devs.find(x => x.id === S.lightDev);
  const ports = [0, 1, 2, 3].map(i => { const p = (d.ports || []).find(x => x.id === i) || { id: i, start: 0, end: 0 }; return { ...p, off: !(p.start > 0 && p.end > 0) }; });
  const on = ports.filter(p => !p.off);
  const sequential = on.every((p, i) => p.start === (i === 0 ? 1 : on[i - 1].end + 1));
  S.portMode = S.portMode && S.portModeDev === d.id ? S.portMode : (sequential ? 'simple' : 'advanced'); S.portModeDev = d.id;
  const P = S.portDraft && S.portDraft.dev === d.id ? S.portDraft.P : ports.map(p => ({ ...p, count: p.off ? 0 : p.end - p.start + 1 }));
  S.portDraft = { dev: d.id, P };
  const chosen = S.settings.service?.devices || [];
  const draw = () => {
    if (S.portMode === 'simple') { let next = 1; P.forEach(p => { if (p.count > 0) { p.start = next; p.end = next + p.count - 1; p.off = false; next = p.end + 1; } else { p.off = true; p.start = p.end = 0; } }); }
    const max = Math.max(1, ...P.filter(p => !p.off).map(p => p.end));
    $('#pmap').innerHTML = P.map(p => `<div class="lane" title="Port ${p.id + 1}">${p.off ? '' : `<i style="left:${(p.start - 1) / max * 100}%;width:${(p.end - p.start + 1) / max * 100}%"></i>`}
      <span>Port ${p.id + 1}: ${p.off ? 'off' : `bulbs ${p.start}–${p.end}`}</span></div>`).join('');
    $('#ptotal').textContent = `${max === 1 && P.every(p => p.off) ? 0 : max} bulbs in the pattern${P.some((p, i) => !p.off && P.some((q, j) => j !== i && !q.off && p.start <= q.end && q.start <= p.end)) ? '. Overlapping ports show the same bulbs (mirrored).' : '.'}`;
  };
  m.innerHTML = `<div class="view"><div class="panel-head"><h2>Lights</h2>
      ${devs.length > 1 ? `<select id="ldev" style="width:auto">${devs.map(x => `<option value="${esc(x.id)}" ${x.id === d.id ? 'selected' : ''}>${esc(x.name)}</option>`).join('')}</select>` : ''}
      <span class="badge ${d.online ? 'hi' : ''}">${d.online ? 'Online' : 'Offline'}</span><span class="small muted">Firmware ${esc(d.firmware || '?')}</span></div>
    ${d.error ? `<p class="callout warn">${esc(d.error)}</p>` : ''}
    <div class="cols wide-left">
      <div class="panel stack"><div class="panel-head"><h2>Ports and bulbs</h2>
          <div class="seg"><button data-pm="simple" aria-pressed="${S.portMode === 'simple'}">Simple</button><button data-pm="advanced" aria-pressed="${S.portMode === 'advanced'}">Advanced</button></div></div>
        <p class="note">${S.portMode === 'simple' ? 'Enter how many bulbs are on each port. Use 0 for an unused port. Ports are numbered in order along the roofline.' : 'Set the first and last bulb number for each port. Ports may overlap to mirror the same section of the pattern.'}</p>
        <div class="ports">${P.map(p => `<div class="port"><b>Port ${p.id + 1}</b><div class="vals">
          ${S.portMode === 'simple' ? `<input type="number" min="0" max="2048" data-pc="${p.id}" value="${p.count}" aria-label="Bulbs on port ${p.id + 1}"><span class="small muted">bulbs</span>`
          : `<label class="check" style="gap:6px"><input type="checkbox" data-poff="${p.id}" ${p.off ? 'checked' : ''}>Off</label>
             <input type="number" min="1" max="2048" data-ps="${p.id}" value="${p.off ? '' : p.start}" ${p.off ? 'disabled' : ''} aria-label="First bulb"><span class="muted">to</span>
             <input type="number" min="1" max="2048" data-pe="${p.id}" value="${p.off ? '' : p.end}" ${p.off ? 'disabled' : ''} aria-label="Last bulb">`}</div></div>`).join('')}</div>
        <div class="portmap" id="pmap"></div><p class="note" id="ptotal"></p>
        <div class="row"><button class="primary" data-saveports>Save to controller</button><button class="ghost" data-reload>Undo changes</button></div>
      </div>
      <div class="stack">
        <div class="panel stack"><h2>Controller</h2>
          <label class="field">Name<input type="text" id="lname" maxlength="30" value="${esc(d.name)}"></label>
          <label class="field">LED chip<select id="lic">${S.catalog.ic_types.map((n, i) => `<option value="${i}" ${d.ic === i ? 'selected' : ''}>${n}</option>`).join('')}</select></label>
          <label class="field">Color order <span class="hint">Trimlight systems are almost always RGB. Change it only if Test colors shows the wrong color.</span>
            <select id="lco">${S.catalog.color_orders.map((n, i) => `<option value="${i}" ${d.colorOrder === i ? 'selected' : ''}>${n}</option>`).join('')}</select></label>
          <div><button data-savedev>Save controller settings</button></div>
          <div class="row"><span class="small">Test colors:</span>${[['Red', '#FF0000'], ['Green', '#00FF00'], ['Blue', '#0000FF'], ['White', '#FFFFFF']].map(([n, c]) => `<button class="small" data-test="${c}">${swatches([c], 1)}${n}</button>`).join('')}</div>
        </div>
        ${devs.length > 1 ? `<div class="panel stack"><h2>Controlled by this app</h2>${devs.map(x => `<label class="check"><input type="checkbox" data-ctl="${esc(x.id)}" ${!chosen.length || chosen.includes(x.id) ? 'checked' : ''}>${esc(x.name)}</label>`).join('')}
          <div><button class="small" data-savectl>Save</button></div></div>` : ''}
      </div>
    </div></div>`;
  draw();
  m.oninput = e => {
    const t = e.target, ds = t.dataset;
    if (ds.pc !== undefined) P[+ds.pc].count = Math.max(0, Math.min(2048, +t.value || 0));
    if (ds.ps !== undefined) P[+ds.ps].start = +t.value || 1;
    if (ds.pe !== undefined) P[+ds.pe].end = +t.value || 1;
    if (ds.poff !== undefined) { const p = P[+ds.poff]; p.off = t.checked; if (!p.off && !p.start) { p.start = 1; p.end = 50; } return VIEWS.lightsRedraw(); }
    if (ds.pc !== undefined || ds.ps !== undefined || ds.pe !== undefined) draw();
  };
  VIEWS.lightsRedraw = () => { m.querySelectorAll('[data-ps],[data-pe]').forEach(i => { const p = P[+(i.dataset.ps ?? i.dataset.pe)]; i.disabled = p.off; if (!p.off) i.value = i.dataset.ps !== undefined ? p.start : p.end; }); draw(); };
  m.onchange = e => { if (e.target.id === 'ldev') { S.lightDev = e.target.value; S.portMode = null; S.portDraft = null; VIEWS.lights({ keep: true }); } };
  m.onclick = async e => {
    const b = e.target.closest('button'); if (!b) return; const ds = b.dataset;
    if (ds.pm) {
      if (ds.pm === 'simple' && S.portMode !== 'simple') {
        const on = P.filter(p => !p.off), seq = on.every((p, i) => p.start === (i === 0 ? 1 : on[i - 1].end + 1));
        if (!seq && !await confirmBox('Switch to Simple?', 'Simple mode lays the ports end to end, so overlapping or gapped ports will be rearranged when you save.', 'Switch')) return;
        P.forEach(p => p.count = p.off ? 0 : p.end - p.start + 1);
      }
      S.portMode = ds.pm; return VIEWS.lights({ keep: true });
    }
    if (ds.reload !== undefined) { S.portMode = null; return VIEWS.lights(); }
    if (ds.saveports !== undefined) {
      const bad = P.find(p => !p.off && !(p.start >= 1 && p.end >= p.start && p.end <= 2048));
      if (bad) return toast(`Port ${bad.id + 1}: the first bulb must be 1 or more and not after the last bulb (max 2048).`, true);
      if (!await confirmBox('Save ports to the controller?', 'The lights may flicker while the controller applies the new layout.', 'Save')) return;
      return busy(b, () => api('device/update', { body: { deviceId: d.id, ports: P.map(p => ({ id: p.id, start: p.off ? 0 : p.start, end: p.off ? 0 : p.end })) } }))
        .then(() => { toast('Ports saved'); S.portMode = null; VIEWS.lights(); }).catch(() => {});
    }
    if (ds.savedev !== undefined) {
      const body = { deviceId: d.id };
      const name = $('#lname').value.trim(); if (name !== d.name) body.name = name;
      if (+$('#lic').value !== d.ic) body.ic = +$('#lic').value;
      if (+$('#lco').value !== d.colorOrder) body.colorOrder = +$('#lco').value;
      if (Object.keys(body).length === 1) return toast('Nothing changed');
      if (body.colorOrder !== undefined && body.colorOrder !== 0 && !await confirmBox('Change the color order?', 'Trimlight systems are almost always RGB. Only change this if Test colors shows the wrong colors.', 'Change it')) return;
      if ((body.ic !== undefined) && !await confirmBox('Change the LED chip type?', 'Trimlight systems use UCS1903 as standard. Only change this if your installer told you to; the wrong setting makes the lights misbehave until it\u2019s set back.', 'Change it')) return;
      return busy(b, () => api('device/update', { body })).then(() => { toast('Controller updated'); S.devices = null; }).catch(() => {});
    }
    if (ds.test) return busy(b, () => api('action', { body: { action: 'try', effect: { label: 'Color test', colors: [ds.test], counts: [1], custom_mode: 0, brightness: 220 } } }))
      .then(() => toast('Showing a test color for 15 minutes, or until you tap Return to schedule on Home.')).catch(() => {});
    if (ds.savectl !== undefined) {
      const ids = $$('[data-ctl]:checked', m).map(i => i.dataset.ctl);
      if (!ids.length) return toast('Keep at least one controller.', true);
      const n = clone(S.settings); n.service = { ...(n.service || {}), devices: ids.length === devs.length ? [] : ids };
      return busy(b, () => saveSettings(n)).catch(() => {});
    }
  };
};

/* ---------------------------------------------------------------- DATE & TIME */
VIEWS.time = async () => {
  S.timers.forEach(clearInterval); S.timers = [];
  const m = $('#main');
  let st = null; try { st = await refreshStatus(); } catch { /* setup mode */ }
  const fetched = Date.now();
  m.innerHTML = `<div class="view"><h2>Date and time</h2>
    <div class="cols">
      <div class="stack">
        <div class="panel stack"><p class="small muted">This computer's time, used for your schedule</p>
          <div class="clock" id="clk">—</div><p class="muted" id="clkd"></p><div id="skew"></div>
          <p class="note">The clock itself comes from the computer's operating system, which keeps it right over the internet. This screen sets your location, time zone and daylight saving time.</p></div>
        <div class="panel stack"><h2>Sun today</h2>
          ${st && st.sun ? `<div class="legend" style="gap:22px"><span>Dawn <b>${esc(st.sun.dawn || '—')}</b></span><span>Sunrise <b>${esc(st.sun.sunrise || '—')}</b></span><span>Sunset <b>${esc(st.sun.sunset || '—')}</b></span><span>Dusk <b>${esc(st.sun.dusk || '—')}</b></span></div>`
            : '<p class="muted">Set your location to see sun times.</p>'}</div>
        <div class="panel stack"><h2>Controller clock</h2>
          <p class="note">This app sends the correct time to your controllers every day, so their clocks stay right through daylight saving changes. You only need these buttons if you also use the Trimlight app's own timers.</p>
          <div><button data-sync>Send the time now</button></div>
          ${(S.settings.controller?.clock_offset_min || 0) !== 0 ? `<p class="callout small">The controllers are set ${Math.abs(S.settings.controller.clock_offset_min)} minutes ${S.settings.controller.clock_offset_min > 0 ? 'ahead of' : 'behind'} the real time. <button class="small ghost" data-resetcdt>Use the real time</button></p>` : ''}
          <div class="row"><input type="datetime-local" id="cdt" style="max-width:260px" aria-label="Date and time for the controllers"><button class="ghost" data-sendcdt>Use this time on the controllers</button></div>
          <p class="note">A chosen time is kept as a fixed difference from the real time, so it stays set. This only affects the controllers' own clocks, not this app's schedule.</p></div>
      </div>
      <div class="panel stack"><h2>Location, time zone and daylight saving</h2><div id="locbox"></div>
        <div><button class="primary" data-saveloc>Save</button></div></div>
    </div></div>`;
  const loc = await locationEditor($('#locbox'));
  if (st && st.now) {
    const serverMs = Date.parse(st.now), skew = serverMs - fetched, off = st.now.match(/([+-])(\d\d):(\d\d)$/);
    const offMin = off ? (off[1] === '-' ? -1 : 1) * (+off[2] * 60 + +off[3]) : 0;
    if (Math.abs(skew) > 120000) $('#skew').innerHTML = `<p class="callout warn small">This device's clock and the app computer's clock differ by ${Math.round(Math.abs(skew) / 60000)} minutes. Check the computer's date and time settings.</p>`;
    const tick = () => {
      const wall = new Date(Date.now() + skew + offMin * 60000);
      $('#clk').textContent = wall.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit', second: '2-digit', timeZone: 'UTC' });
      $('#clkd').textContent = `${wall.toLocaleDateString([], { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric', timeZone: 'UTC' })} · ${st.tz} (UTC${off ? off[0].slice(0, 6) : ''})`;
    };
    tick(); S.timers.push(setInterval(tick, 1000));
  }
  m.onclick = e => {
    const b = e.target.closest('button'); if (!b) return; const d = b.dataset;
    if (d.saveloc !== undefined) busy(b, async () => { const n = clone(S.settings); n.location = loc.value();
      if (!n.location.latitude && !n.location.longitude) throw new Error('Choose your town or enter latitude and longitude.');
      await saveSettings(n, 'Location and time saved'); VIEWS.time(); }).catch(() => {});
    if (d.sync !== undefined) busy(b, () => api('device/clock', { body: {} })).then(r => toast(`Sent ${r.label} to ${r.sent.length} controller${r.sent.length === 1 ? '' : 's'}`)).catch(() => {});
    if (d.sendcdt !== undefined) { const v = $('#cdt').value; if (!v) return toast('Pick a date and time first.', true);
      busy(b, () => api('device/clock', { body: { datetime: v } })).then(async r => { toast(`Controllers set to ${r.label}`); await loadSettings(); VIEWS.time(); }).catch(() => {}); }
    if (d.resetcdt !== undefined) busy(b, () => api('device/clock', { body: { reset: true } })).then(async () => { toast('Controllers use the real time again'); await loadSettings(); VIEWS.time(); }).catch(() => {});
  };
};

/* ---------------------------------------------------------------- SETTINGS */
VIEWS.settings = async () => {
  const m = $('#main');
  const a = S.account = await api('account');
  const urls = a.addresses.map(ip => `${a.scheme || 'http'}://${ip}:${a.port}/`);
  const local = S.session.local, admin = isAdmin(), me = a.user || {}, signedIn = !me.local && !me.setup;
  const hours = h => h < 24 ? `${h} hour${h === 1 ? '' : 's'}` : `${h / 24} day${h === 24 ? '' : 's'}`;
  m.innerHTML = `<div class="view"><h2>Settings</h2>
    <div class="cols">
      <div class="stack">
        ${admin ? `<div class="panel stack"><h2>Trimlight account</h2>
          <p class="note">Your API Client ID and Client Secret come from <a href="https://trimlight.ledhue.com/trimlight/v1/api-credentials/apply" target="_blank" rel="noopener noreferrer">Trimlight's API credentials page</a> (Manual, section 2). They're stored only on the computer running this app, encrypted.</p>
          <label class="field">Client ID<input type="text" id="scid" autocomplete="off" spellcheck="false" value="${esc(a.client_id)}"></label>
          <label class="field">Client Secret<input type="password" id="ssec" autocomplete="off" spellcheck="false" placeholder="${a.secret_hint ? 'Saved (' + esc(a.secret_hint) + '). Type a new one to replace it.' : 'Paste your Client Secret'}"></label>
          <div><button class="primary" data-cred>Test and save</button></div></div>` : ''}
        ${signedIn ? `<div class="panel stack"><h2>Your account</h2>
          <p>Signed in as <b>${esc(me.username)}</b> · ${esc(ROLE_NAMES[me.role] || me.role)}</p>
          <label class="field">Current password<input type="password" id="pcur" autocomplete="current-password"></label>
          <label class="field">New password<input type="password" id="pnew" autocomplete="new-password" placeholder="At least 8 characters"></label>
          <div class="row"><button data-setpw>Change password</button><button class="ghost" data-logout>Sign out of this device</button></div>
          <p class="note">Changing your password signs you out on every other device.</p></div>` : ''}
        ${admin ? `<div class="panel stack"><h2>Accounts</h2>
          <p class="note"><b>Administrators</b> can do everything. <b>Editors</b> design patterns, schedules and the house map and control the lights, but can't change accounts, the Trimlight connection, location or other household settings. <b>Viewers</b> can only look. At least one active Administrator always remains.</p>
          <div class="list" id="users"><p class="muted small">Loading…</p></div>
          <details><summary>Add an account</summary><div class="stack" style="margin-top:10px">
            <label class="field">User name<input type="text" id="nuname" maxlength="64" autocapitalize="none" spellcheck="false" placeholder="e.g. sam"></label>
            <label class="field">Role<select id="nurole"><option value="viewer">Viewer</option><option value="editor">Editor</option><option value="admin">Administrator</option></select></label>
            <label class="field">Password<input type="password" id="nupw" autocomplete="new-password" placeholder="At least 8 characters"></label>
            <div><button data-adduser>Add account</button></div></div></details>
          ${a.password_set ? `<label class="field">Stay signed in while unused for
            <select id="idle">${a.session_idle_choices.map(h => `<option value="${h}" ${h === a.session_idle_hours ? 'selected' : ''}>${hours(h)}</option>`).join('')}</select></label>
            <p class="note">Every sign-in also ends ${a.session_max_days} days after it began.</p>
            <div class="row"><button class="ghost" data-signout>Sign out all devices</button></div>
            <label class="check"><input type="checkbox" id="locallogin" ${a.local_login ? 'checked' : ''}> Require signing in on this computer too</label>
            <p class="note">Useful if other people or programs use this computer. Forgot a password? On this computer run <code>python3 main.py reset-password NAME</code>.</p>` : '<p class="note">Until an account exists, only this computer can use the app.</p>'}</div>` : ''}
        <div class="panel stack"><h2>Phones and other computers</h2>
          ${urls.length ? `<p>Open ${urls.map(u => `<code>${esc(u)}</code>`).join(' or ')} on any device on your home Wi-Fi. In Safari, Share › Add to Home Screen makes it an app.</p>` : ''}
          <p class="note">${a.password_set ? 'Each person signs in with their own account.' : 'Create an account (Settings › Accounts) so other devices can sign in.'}</p></div>
        <div class="panel stack"><h2>Share and back up</h2>
          <p class="note">Export your patterns and schedule to a file you can keep or share with other Trimlight owners. It never includes your Trimlight credentials, passwords or location.</p>
          <div class="row"><button data-export>Export patterns and schedule</button>${role() !== 'viewer' ? '<label class="btn" tabindex="0">Import a file<input type="file" id="impf" accept=".json,application/json" hidden></label>' : ''}</div></div>
      </div>
      <div class="stack">
        ${admin ? `<div class="panel stack"><h2>App address</h2>
          <p class="note">The app uses port <b>${a.port}</b>${urls.length ? ` (<code>${esc(urls[0])}</code>)` : ''}. Change it if another program on this computer needs that port.</p>
          <div class="row"><label class="field">Port<input type="number" id="pport" min="1024" max="65535" value="${a.port}" style="width:8em"></label>
            <button data-port style="align-self:end">Restart on new port</button></div>
          <p class="note">Phones and bookmarks need the new address afterward. The schedule pauses for a few seconds while the app restarts.</p></div>
        <div class="panel stack"><h2>Start automatically</h2>
          ${a.autostart.supported ? `<label class="check"><input type="checkbox" id="auto" ${a.autostart.enabled ? 'checked' : ''}> Start this app when the computer starts</label>
            ${a.autostart.note ? `<p class="note">${esc(a.autostart.note)}</p>` : ''}` : '<p class="muted">Not available on this system.</p>'}</div>
        <div class="panel stack"><h2>Webhooks</h2>
          <p class="note">Let Home Assistant, IFTTT or a motion sensor trigger the lights, for example a security flash at night.</p>
          <label class="check"><input type="checkbox" id="hook" ${a.webhook_token ? 'checked' : ''}> Allow webhooks</label>
          ${a.webhook_token ? `<label class="field">Token <span class="hint">Treat it like a password.</span><input type="text" readonly value="${esc(a.webhook_token)}" id="htok"></label>
            <div class="row"><button class="small" data-copy="htok">Copy token</button><button class="small ghost" data-regen>Make a new token</button></div>
            <p class="small">Example:</p><pre class="code">curl -X POST -H "X-Token: ${esc(a.webhook_token)}" \\\n  http://${esc(a.addresses[0] || 'THIS-PC')}:${a.port}/api/hook/flash</pre>
            <p class="note">Actions: flash, stop_flash, on (with {"effect": "name"}), off, resume, levels. Send the token in the X-Token header, or as "token" in a JSON body for services that can't set headers. Tokens in the web address are refused.</p>` : ''}</div>
        <div class="panel stack"><h2>Version history</h2>
          <p class="note">Every save is kept (the last 100). Restoring brings back the patterns, schedule and house map from that moment; your account, phones and app address stay as they are.</p>
          <div class="list" id="hist"><p class="muted small">Loading…</p></div></div>` : ''}
        <div class="panel stack"><h2>Setup and about</h2>
          ${admin ? '<div><button class="ghost" data-wizard>Run the setup assistant again</button></div>' : ''}
          <p class="small muted">Version ${esc(a.version)}${a.python ? ` · Python ${esc(a.python)}<br>Data folder: <code>${esc(a.data_dir)}</code>` : ''}</p>
          <p class="small muted">EaveLuxOS, the intelligent lighting control platform. © 2026 Christopher A. Tankelewicz (ThinkTank4n6). Free software under the MIT License. Works with Trimlight Edge controllers; not affiliated with or endorsed by Trimlight. The house roofline tools and bulb painter are adapted from Trimlight Home Studio (© 2026 Thomas Kay and contributors, MIT License).</p>
          ${!local ? (signedIn ? '' : '<div><button class="ghost" data-logout>Sign out of this device</button></div>') : '<div><button class="ghost danger" data-quit>Quit the app</button></div><p class="note">Your lights only follow the schedule while the app is running.</p>'}</div>
      </div>
    </div></div>`;
  const drawUsers = async () => {
    const box = $('#users'); if (!box) return;
    const list = await api('users').catch(e => { box.innerHTML = `<p class="callout warn">${esc(e.message)}</p>`; return null; });
    if (!list) return;
    box.innerHTML = list.length ? list.map(u => `<div class="item" data-uid="${esc(u.id)}"><div class="grow"><div class="name">${esc(u.username)}${me.username === u.username && signedIn ? ' <span class="small muted">(you)</span>' : ''}</div>
      <div class="sub">${esc(ROLE_NAMES[u.role])}${u.disabled ? ' · <b>disabled</b>' : ''}</div></div>
      <button class="small ghost" data-edituser="${esc(u.id)}">Edit</button></div>`).join('')
      : '<p class="muted small">No accounts yet. Add an Administrator account for yourself first.</p>';
    S.users = list;
  };
  drawUsers();
  if (admin) api('history?limit=15').then(h => {
    $('#hist').innerHTML = h.length ? h.map((v, i) => `<div class="item"><div class="grow"><div class="name">${esc(new Date(v.saved_at).toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }))}</div>
      <div class="sub">${esc(v.summary)}${i === 0 ? ' · current' : ''}</div></div>${i === 0 ? '' : `<button class="small ghost" data-restore="${v.rev}">Restore</button>`}</div>`).join('')
      : '<p class="muted small">No saves yet.</p>';
  }).catch(() => {});
  const editUser = u => dialog(`<h2>Edit ${esc(u.username)}</h2>
      <label class="field">User name<input type="text" name="un" maxlength="64" autocapitalize="none" spellcheck="false" value="${esc(u.username)}"></label>
      <label class="field">Role<select name="role">${Object.entries(ROLE_NAMES).map(([k, v]) => `<option value="${k}" ${k === u.role ? 'selected' : ''}>${v}</option>`).join('')}</select></label>
      <label class="field">New password <span class="hint">Leave empty to keep it.</span><input type="password" name="pw" autocomplete="new-password"></label>
      <label class="check"><input type="checkbox" name="dis" ${u.disabled ? 'checked' : ''}> Disabled (can't sign in)</label>
      <p class="note">Saving signs this account out on its devices. At least one active Administrator must remain.</p>`,
    async f => {
      await api('users', { body: { id: u.id, username: f.un.value.trim().toLowerCase(), role: f.role.value, disabled: f.dis.checked, ...(f.pw.value ? { password: f.pw.value } : {}) } });
      toast('Account saved'); await boot();
      if (S.session.authed) VIEWS.settings();
    }, { ok: 'Save', extraFoot: `<button type="button" class="ghost danger" data-deluser="${esc(u.id)}">Delete account</button>`,
      onOpen: f => { $('[data-deluser]', f.closest('dialog')).onclick = async () => {
        $('#dlg').close();
        if (!await confirmBox(`Delete ${esc(u.username)}?`, 'The account is removed and signed out everywhere. To pause access instead, edit it and tick Disabled.', 'Delete', true)) return;
        busy(null, () => api('users/delete', { body: { id: u.id } })).then(() => { toast('Account deleted'); drawUsers(); }).catch(() => {});
      }; } });
  m.onclick = async e => {
    const b = e.target.closest('button'); if (!b) return; const d = b.dataset;
    if (d.restore && await confirmBox('Restore this version?', 'Your current patterns, schedule and house map are replaced by the ones from that save. The current version stays in the history, so you can switch back.', 'Restore'))
      return busy(b, () => api('history/restore', { body: { rev: +d.restore } })).then(async () => { await loadSettings(); toast('Restored'); VIEWS.settings(); }).catch(() => {});
    if (d.cred !== undefined) busy(b, () => api('credentials', { body: { client_id: $('#scid').value, client_secret: $('#ssec').value } }))
      .then(r => { toast(`Connected. ${r.devices.length} controller${r.devices.length === 1 ? '' : 's'} found.`); S.devices = null; VIEWS.settings(); }).catch(() => {});
    if (d.setpw !== undefined) busy(b, () => api('password', { body: { new: $('#pnew').value, current: $('#pcur').value } })).then(() => { toast('Password changed. Other devices are signed out.'); VIEWS.settings(); }).catch(() => {});
    if (d.adduser !== undefined) busy(b, () => api('users', { body: { username: $('#nuname').value.trim().toLowerCase(), role: $('#nurole').value, password: $('#nupw').value } }))
      .then(async r => { if (r.token) token.set(r.token); toast('Account added'); S.session = await api('session'); VIEWS.settings(); }).catch(() => {});
    if (d.edituser) { const u = (S.users || []).find(x => x.id === d.edituser); if (u) editUser(u); }
    if (d.signout !== undefined && await confirmBox('Sign out all devices?', 'Everyone has to sign in again, including you on this device unless it’s the app computer.', 'Sign out all', true))
      busy(b, () => api('sessions/end_all', { body: {} })).then(() => { toast('All devices signed out'); boot(); }).catch(() => {});
    if (d.logout !== undefined) { await api('logout', { body: {} }).catch(() => {}); token.set(null); boot(); }
    if (d.regen !== undefined && await confirmBox('Make a new token?', 'Anything using the old token stops working until you update it.', 'Make new token'))
      busy(b, () => api('webhook', { body: { enable: true } })).then(() => VIEWS.settings()).catch(() => {});
    if (d.copy) { const el = $('#' + d.copy); el.select(); navigator.clipboard?.writeText(el.value).then(() => toast('Copied'), () => document.execCommand('copy')); }
    if (d.wizard !== undefined) wizard(0);
    if (d.port !== undefined) {
      const np = +$('#pport').value;
      if (!np || np === a.port) return toast('Enter a different port number.', true);
      if (!await confirmBox(`Move the app to port ${np}?`, `The app restarts on <code>${esc(location.protocol + '//' + location.hostname + ':' + np + '/')}</code>. Update phone bookmarks and Home Screen icons to the new address.`, 'Restart')) return;
      busy(b, () => api('port', { body: { port: np } })).then(() => {
        $('#main').innerHTML = `<div class="gate"><div class="panel stack"><h2>Moving to port ${np}…</h2><p class="muted">This page reopens on the new address in a few seconds.</p></div></div>`;
        setTimeout(() => { location.href = `${location.protocol}//${location.hostname}:${np}/#settings`; }, 5000);
      }).catch(() => {});
    }
    if (d.quit !== undefined && await confirmBox('Quit the app?', 'The schedule stops until you start the app again.', 'Quit', true)) {
      await api('quit', { body: {} }).catch(() => {}); $('#main').innerHTML = '<div class="gate"><div class="panel"><h2>The app has stopped</h2><p class="muted">Double-click the launcher to start it again.</p></div></div>'; $('#top').hidden = true; }
    if (d.export !== undefined) busy(b, async () => {
      const data = await api('export');
      const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }));
      const link = Object.assign(document.createElement('a'), { href: url, download: `eaveluxos-patterns-${new Date().toISOString().slice(0, 10)}.json` });
      document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 2000);
    }).catch(() => {});
  };
  m.onchange = async e => {
    const t = e.target;
    if (t.id === 'auto') busy(null, () => api('autostart', { body: { enabled: t.checked } })).then(r => toast(r.enabled ? 'Will start automatically' : 'Won’t start automatically')).catch(() => { t.checked = !t.checked; });
    if (t.id === 'locallogin') busy(null, () => api('local_login', { body: { enabled: t.checked } })).then(r => toast(r.local_login ? 'This computer now asks you to sign in too' : 'This computer no longer asks you to sign in')).catch(() => { t.checked = !t.checked; });
    if (t.id === 'idle') busy(null, () => api('session_policy', { body: { idle_hours: +t.value } })).then(r => toast(`Sign-ins now end after ${hours(r.idle_hours)} without use`)).catch(() => { t.value = a.session_idle_hours; });
    if (t.id === 'hook') busy(null, () => api('webhook', { body: { enable: t.checked } })).then(() => VIEWS.settings()).catch(() => {});
    if (t.id === 'impf' && t.files[0]) {
      let data; try { data = JSON.parse(await t.files[0].text()); } catch { return toast("That file isn't a valid export.", true); }
      t.value = '';
      const s = data.settings || data;
      const counts = `${Object.keys(s.effects || {}).length} patterns and ${(s.rules || []).length} rules`;
      dialog(`<h2>Import ${esc(counts)}?</h2>
        <label class="check"><input type="radio" name="mode" value="merge" checked><span><b>Add to mine</b><br><span class="small muted">Adds patterns and rules whose names you don't already have.</span></span></label>
        ${admin ? `<label class="check"><input type="radio" name="mode" value="replace"><span><b>Replace mine</b><br><span class="small muted">Your patterns and schedule are replaced. Location and controllers stay.</span></span></label>` : ''}`,
        async f => { await api('import', { body: { settings: s, mode: (f.mode && f.mode.value) || 'merge' } }); await loadSettings(); toast('Imported'); }, { ok: 'Import' });
    }
  };
};

/* ---------------------------------------------------------------- manual */
VIEWS.manual = async () => {
  const m = $('#main');
  m.innerHTML = '<div class="view"><h2>Manual</h2><p class="muted">Loading…</p></div>';
  const r = await fetch('docs/MANUAL.md', { cache: 'no-store' });
  if (!r.ok) { m.innerHTML = `<div class="view"><h2>Manual</h2><p class="callout warn">The manual isn't included in this copy of the app. It's MANUAL.md in the app's download.</p></div>`; return; }
  m.innerHTML = `<div class="view manual">
    <div class="panel-head"><h2>Manual</h2><span class="row"><input type="search" id="mq" placeholder="Find in the manual" aria-label="Find in the manual" style="max-width:260px">
      <a class="btn small ghost" href="docs/MANUAL.md" target="_blank" rel="noopener">Plain text</a></span></div>
    <p class="note" id="mnone" hidden>No section mentions that.</p>
    <article class="panel md" id="mdoc">${window.Markdown.render(await r.text())}</article></div>`;
  // Group the document into sections (one per h2) for "Find in the manual".
  const doc = $('#mdoc'), sections = [];
  let cur = null;
  for (const el of [...doc.children]) {
    if (el.tagName === 'H2' || !cur) { cur = { els: [] }; sections.push(cur); }
    cur.els.push(el);
  }
  m.oninput = e => {
    if (e.target.id !== 'mq') return;
    const q = e.target.value.trim().toLowerCase();
    let shown = 0;
    for (const sec of sections) {
      const hit = !q || sec.els.some(el => el.textContent.toLowerCase().includes(q));
      sec.els.forEach(el => { el.hidden = !hit; }); if (hit) shown++;
    }
    $('#mnone').hidden = shown > 0;
  };
  // Links to sections scroll within the manual instead of changing the app's address.
  m.onclick = e => {
    const a = e.target.closest('a[href^="#"]'); if (!a) return;
    e.preventDefault();
    const q = $('#mq'); if (q.value) { q.value = ''; m.oninput({ target: q }); }
    const target = doc.querySelector(`[id="${CSS.escape(a.getAttribute('href').slice(1))}"]`);
    if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };
};

/* ---------------------------------------------------------------- start */
window.addEventListener('hashchange', () => { const v = location.hash.slice(1); if (S.session?.authed && v !== S.view && VIEWS[v]) go(v); });
boot().catch(e => { $('#main').innerHTML = `<div class="gate"><p class="callout warn">Can't reach the app: ${esc(e.message)}</p></div>`; });

/* ---------------------------------------------------------------- HOUSE MAP: bulb finder, photos, landmarks, zones */
const MAX_SLOTS = 30, PER_SLOT = 90;
/* Photos need the sign-in header too, so fetch them and show them as blob URLs. */
const photoCache = {};
async function loadPhoto(side) {
  const key = side + ':' + (S.photoV || 0);
  if (photoCache[key]) return photoCache[key];
  const r = await fetch('api/photo/' + encodeURIComponent(side), { headers: authHeaders(), cache: 'no-store' });
  if (!r.ok) throw new Error('no photo');
  for (const k of Object.keys(photoCache)) if (k.startsWith(side + ':')) { URL.revokeObjectURL(photoCache[k]); delete photoCache[k]; }
  return (photoCache[key] = URL.createObjectURL(await r.blob()));
}
/* Four sides of the house plus a shed are always there; added sides follow. */
function mapData() {
  const m = S.settings.map || {}, saved = m.sides || [];
  const sides = [...window.Roofline.DEFAULT_SIDES.map(d => saved.find(x => x.id === d.id) || d), ...saved.filter(x => !window.Roofline.DEFAULT_SIDES.some(d => d.id === x.id))];
  return { total_bulbs: m.total_bulbs ?? null, sides, landmarks: m.landmarks || [], zones: m.zones || [], rooflines: clone(m.rooflines || {}) };
}
function addressSpace() { return mapData().total_bulbs || totalBulbs(); }
async function saveMap(mut, msg) { const n = clone(S.settings); n.map = mapData(); mut(n.map); await saveSettings(n, msg); }

/* Runs of [color, count] -> designer segments, each at most 90 bulbs. */
function runsToSegs(runs) {
  const segs = [];
  for (const [c, n] of runs) for (let left = n; left > 0; left -= PER_SLOT) segs.push({ c, n: Math.min(PER_SLOT, left) });
  return segs;
}
/* One highlight over the whole address space, so the pattern never repeats onto other bulbs. */
function highlightDef(start, end, total, color) {
  const runs = [];
  if (start > 1) runs.push(['#000000', start - 1]);
  runs.push([color, end - start + 1]);
  if (end < total) runs.push(['#000000', total - end]);
  const segs = runsToSegs(runs);
  if (segs.length > MAX_SLOTS) throw new Error(`That needs ${segs.length} color slots; the controller allows ${MAX_SLOTS}. Use a smaller address space.`);
  return { label: start === end ? `Bulb ${start}` : `Bulbs ${start}–${end}`, colors: segs.map(s => s.c), counts: segs.map(s => s.n), custom_mode: 0, brightness: 255, speed: 0 };
}
/* Paint zones over the address space; later zones win where they overlap. */
function paintZones(assign, base, total) {
  const arr = new Array(total).fill(base);
  for (const { start, end, color } of assign) for (let i = Math.max(1, start); i <= Math.min(total, end); i++) arr[i - 1] = color;
  const runs = [];
  for (const c of arr) { if (runs.length && runs[runs.length - 1][0] === c) runs[runs.length - 1][1]++; else runs.push([c, 1]); }
  return runsToSegs(runs);
}

VIEWS.map = async () => {
  const m = $('#main');
  m.innerHTML = '<div class="view"><h2>House map</h2><p class="muted">Loading…</p></div>';
  await loadDevices().catch(() => {});
  S.photos = new Set(await api('photos').catch(() => []));
  S.finder = S.finder || { bulb: 1, end: 1, range: false, step: 1, color: '#FFC062', live: false, side: 'front', placing: false };
  const F = S.finder;
  const render = () => {
    const md = mapData(), T = addressSpace();
    F.bulb = Math.max(1, Math.min(T, F.bulb)); F.end = Math.max(F.bulb, Math.min(T, F.end));
    if (!md.sides.some(x => x.id === F.side)) F.side = md.sides[0].id;
    const pins = md.landmarks.map((l, i) => ({ ...l, i })).filter(l => l.side === F.side && l.x != null);
    const inSel = b => F.range ? b >= F.bulb && b <= F.end : b === F.bulb;
    const ports = ((S.devices || []).find(x => x.selected && x.ports) || {}).ports || [];
    if (R.tracing) F.placing = false;
    const RF = roofHtml(md, F.side);
    m.innerHTML = `<div class="view">
      <div class="panel-head"><h2>House map</h2><span class="muted small">Find a bulb, pin it on a photo, trace the roofline, name the corners and sections.</span></div>
      ${RF.flat}
      <div class="cols wide-left">
        <div class="stack">
          <div class="panel stack">
            <div class="row" role="tablist" aria-label="Sides of the house">${md.sides.map(x => `<button class="small ${x.id === F.side ? 'current' : ''}" data-side="${esc(x.id)}">${esc(x.name)}</button>`).join('')}
              <button class="small ghost" data-addside>Add a side</button></div>
            <div class="photo" id="photo" data-placing="${F.placing}" data-tracing="${R.tracing}">
              ${S.photos.has(F.side) ? `<img id="pimg" alt="Photo of the ${esc(md.sides.find(x => x.id === F.side).name)}">` : ''}
              ${RF.overlay}
              <div class="nophoto" ${S.photos.has(F.side) ? 'hidden' : ''}><p>No photo of this side yet.</p><p class="small muted">Take one at night with the lights on, from the street.</p></div>
              ${pins.map(l => `<button class="pin ${inSel(l.bulb) ? 'on' : ''}" style="left:${l.x * 100}%;top:${l.y * 100}%" data-pin="${l.i}" title="${esc(l.name)}: bulb ${l.bulb}"><span>${esc(l.name)}</span></button>`).join('')}
            </div>
            <div class="row"><label class="btn small">${'Upload photo'}<input type="file" id="pfile" accept="image/*" hidden></label>
              <button class="small ${F.placing ? 'current' : 'ghost'}" data-place>${F.placing ? 'Tap the photo where the bulb is…' : `Pin bulb ${F.bulb} on this photo`}</button>
              <button class="small ghost danger" data-delphoto>Remove photo</button></div>
            ${RF.tools}
            <p class="note">Photos stay on this computer and are never included in exported pattern files. Roofline detection runs in this browser.</p>
          </div>
          <div class="cols">
            <div class="panel stack"><h2>Landmarks</h2>
              <div class="row"><input type="text" id="lmname" maxlength="60" placeholder="e.g. Front gable peak" class="grow" style="flex:1"><button class="small" data-savelm>Save bulb ${F.bulb}</button></div>
              <div class="list">${md.landmarks.length ? md.landmarks.map((l, i) => ({ ...l, i })).sort((a, b) => a.bulb - b.bulb).map(l => `<div class="item"><div class="grow"><div class="name">${esc(l.name)}</div>
                <div class="sub">Bulb ${l.bulb}${l.side ? ' · ' + esc((md.sides.find(x => x.id === l.side) || {}).name || l.side) : ''}${l.x != null ? ' · pinned' : ''}</div></div>
                <button class="small" data-golm="${l.i}">Show</button><button class="small ghost danger" data-dellm="${l.i}" aria-label="Delete ${esc(l.name)}">✕</button></div>`).join('')
                : '<p class="muted small">Find a corner or peak with the finder, give it a name, and save it here.</p>'}</div></div>
            <div class="panel stack"><h2>Zones</h2>
              <div class="row"><input type="text" id="zname" maxlength="60" placeholder="e.g. Garage roof" class="grow" style="flex:1"><button class="small" data-savezone ${F.range ? '' : 'disabled'}>Save ${F.range ? `${F.bulb}–${F.end}` : 'range'}</button></div>
              ${F.range ? '' : '<p class="note">Turn on <b>Select a range</b> in the finder to save a section of roofline.</p>'}
              <div class="list">${md.zones.length ? md.zones.map((z, i) => `<div class="item"><div class="grow"><div class="name">${esc(z.name)}</div><div class="sub">Bulbs ${z.start}–${z.end} (${z.end - z.start + 1})</div></div>
                <button class="small" data-gozone="${i}">Show</button><button class="small ghost danger" data-delzone="${i}" aria-label="Delete ${esc(z.name)}">✕</button></div>`).join('')
                : '<p class="muted small">Zones are named sections, like "garage roof", that you can paint in Create.</p>'}</div></div>
          </div>
        </div>
        <div class="stack">
          <div class="panel stack finder"><h2>Bulb finder</h2>
            <div class="bignum"><button class="ghost" data-step="-1" aria-label="Previous">‹</button>
              <div><span class="num" id="fbulb">${F.range ? `${F.bulb}–${F.end}` : F.bulb}</span><small>of ${T} addresses</small></div>
              <button class="ghost" data-step="1" aria-label="Next">›</button></div>
            <div class="row"><span class="small">Move by</span>${[1, 5, 10, 25].map(n => `<button class="small ${F.step === n ? 'current' : ''}" data-by="${n}">${n}</button>`).join('')}</div>
            <label class="row small">Go to bulb <input type="number" id="fgo" min="1" max="${T}" value="${F.bulb}" style="width:7em"></label>
            <label class="check"><input type="checkbox" id="frange" ${F.range ? 'checked' : ''}> Select a range</label>
            ${F.range ? `<div class="row"><label class="field">First<input type="number" id="fs" min="1" max="${T}" value="${F.bulb}"></label><label class="field">Last<input type="number" id="fe" min="1" max="${T}" value="${F.end}"></label></div>
              <p class="note">The arrows move the whole range.</p>` : ''}
            <div class="row"><span class="small">Highlight color</span><label class="custom-swatch" style="background:${esc(F.color)}"><input type="color" id="fcolor" value="${esc(F.color.toLowerCase())}" aria-label="Highlight color"></label></div>
            <label class="check"><input type="checkbox" id="flive" ${F.live ? 'checked' : ''}> Update the house as I move</label>
            <button class="primary" data-show>Show on house</button>
            <button class="ghost" data-resume>Return to schedule</button>
            <p class="note">Everything else goes dark while the finder shows. The schedule comes back by itself 10 minutes after your last change. Bulb numbers are pattern addresses: if two ports overlap (a mirrored run), one number lights in both places.</p>
          </div>
          <div class="panel stack"><h2>Address space</h2>
            <p class="small">${ports.length ? 'From the controller: ' + ports.map(p => p.start && p.end ? `Port ${p.id + 1} ${p.start}–${p.end}` : `Port ${p.id + 1} off`).join(', ') + '.' : 'Port layout unknown until the controller answers.'}</p>
            <label class="field">Use a different total <span class="hint">Leave empty to use the controller's ports (${totalBulbs()}).</span>
              <input type="number" id="ftotal" min="1" max="10000" value="${md.total_bulbs ?? ''}" placeholder="${totalBulbs()}"></label>
            <div><button class="small" data-savetotal>Save</button></div></div>
        </div>
      </div></div>`;
    const img = $('#pimg');
    if (img) {
      img.onload = () => roofWire(mapData(), F.side);
      loadPhoto(F.side).then(url => { img.src = url; }).catch(() => { img.hidden = true; $('.nophoto', m).hidden = false; });
    }
    roofWire(md, F.side);
  };
  VIEWS.mapRender = render;
  let liveTimer = null;
  const show = async (btn) => {
    const T = addressSpace(); const def = highlightDef(F.bulb, F.range ? F.end : F.bulb, T, F.color);
    await api('action', { body: { action: 'try', effect: def, minutes: 10 } });
  };
  const soft = () => {  // update numbers without rebuilding the inputs being typed in
    $('#fbulb').textContent = F.range ? `${F.bulb}–${F.end}` : F.bulb;
    const sz = $('[data-savezone]'); if (sz) sz.textContent = F.range ? `Save ${F.bulb}–${F.end}` : 'Save range';
    const sl = $('[data-savelm]'); if (sl) sl.textContent = `Save bulb ${F.bulb}`;
    const pl = $('[data-place]'); if (pl && !F.placing) pl.textContent = `Pin bulb ${F.bulb} on this photo`;
    const md = mapData();
    $$('.pin', m).forEach(el => { const l = md.landmarks[+el.dataset.pin]; el.classList.toggle('on', F.range ? l.bulb >= F.bulb && l.bulb <= F.end : l.bulb === F.bulb); });
    if (F.live) { clearTimeout(liveTimer); liveTimer = setTimeout(() => show().catch(e => toast(e.message, true)), 500); }
  };
  const moved = () => {
    render();
    if (F.live) { clearTimeout(liveTimer); liveTimer = setTimeout(() => show().catch(e => toast(e.message, true)), 500); }
  };
  m.onclick = async e => {
    const b = e.target.closest('button'), photo = e.target.closest('#photo');
    if (await roofClick(e, b, mapData(), F.side)) return;
    if (!b && photo && F.placing) {
      const r = photo.getBoundingClientRect(), x = (e.clientX - r.left) / r.width, y = (e.clientY - r.top) / r.height;
      F.placing = false;
      const md = mapData(), existing = md.landmarks.findIndex(l => l.bulb === F.bulb && l.side === F.side);
      dialog(`<h2>Name this spot</h2><label class="field">Name<input type="text" name="nm" maxlength="60" required value="${esc(existing >= 0 ? md.landmarks[existing].name : '')}" placeholder="e.g. Front gable peak"></label>
        <p class="note">Bulb ${F.bulb} on the ${esc(md.sides.find(s => s.id === F.side).name.toLowerCase())} photo.</p>`, async f => {
        const nm = f.nm.value.trim(); if (!nm) throw new Error('Give it a name.');
        await saveMap(mp => { const lm = { name: nm, bulb: F.bulb, side: F.side, x: Math.round(x * 1000) / 1000, y: Math.round(y * 1000) / 1000 };
          if (existing >= 0) mp.landmarks[existing] = lm; else mp.landmarks.push(lm); }, 'Pinned');
        render();
      }, { ok: 'Save pin', onOpen: f => f.nm.focus() });
      return render();
    }
    if (!b) return; const d = b.dataset, md = mapData(), T = addressSpace();
    if (d.side) {
      if (R.tracing) return toast('Save or cancel the roofline section first.', true);
      F.side = d.side; F.placing = false; R.hint = ''; return render(); }
    if (d.step) { const k = +d.step * F.step, w = F.end - F.bulb; F.bulb = Math.max(1, Math.min(T - (F.range ? w : 0), F.bulb + k)); F.end = F.range ? F.bulb + w : F.bulb; return moved(); }
    if (d.by) { F.step = +d.by; return render(); }
    if (d.show !== undefined) return busy(b, show).then(() => toast(F.range ? `Showing bulbs ${F.bulb}–${F.end}` : `Showing bulb ${F.bulb}`)).catch(() => {});
    if (d.resume !== undefined) return busy(b, () => api('action', { body: { action: 'resume' } })).then(() => toast('Back on the schedule')).catch(() => {});
    if (d.place !== undefined) { if (R.tracing) return toast('Save or cancel the roofline section first.', true); F.placing = !F.placing; return render(); }
    if (d.pin) { const l = md.landmarks[+d.pin]; F.range = false; F.bulb = F.end = l.bulb; return moved(); }
    if (d.golm) { const l = md.landmarks[+d.golm]; F.range = false; F.bulb = F.end = l.bulb; if (l.side) F.side = l.side; render(); return busy(b, show).catch(() => {}); }
    if (d.dellm) return busy(b, () => saveMap(mp => mp.landmarks.splice(+d.dellm, 1), 'Landmark deleted')).then(render).catch(() => {});
    if (d.savelm !== undefined) { const nm = $('#lmname').value.trim(); if (!nm) return toast('Type a name first.', true);
      return busy(b, () => saveMap(mp => mp.landmarks.push({ name: nm, bulb: F.bulb, side: F.side }), `Saved \u201c${nm}\u201d as bulb ${F.bulb}`)).then(render).catch(() => {}); }
    if (d.gozone) { const z = md.zones[+d.gozone]; F.range = true; F.bulb = z.start; F.end = z.end; render(); return busy(b, show).catch(() => {}); }
    if (d.delzone) return busy(b, () => saveMap(mp => mp.zones.splice(+d.delzone, 1), 'Zone deleted')).then(render).catch(() => {});
    if (d.savezone !== undefined) { const nm = $('#zname').value.trim(); if (!nm) return toast('Type a zone name first.', true);
      return busy(b, () => saveMap(mp => mp.zones.push({ name: nm, start: F.bulb, end: F.end }), `Saved zone \u201c${nm}\u201d`)).then(render).catch(() => {}); }
    if (d.addside !== undefined) return dialog(`<h2>Add a side</h2><label class="field">Name<input type="text" name="nm" maxlength="30" placeholder="e.g. Shed"></label>`, async f => {
      const nm = f.nm.value.trim(); if (!nm) throw new Error('Give it a name.');
      const id = nm.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 40) || 'side';
      await saveMap(mp => { if (!mp.sides.some(x => x.id === id)) mp.sides.push({ id, name: nm }); }, 'Side added'); F.side = id; render(); }, { ok: 'Add' });
    if (d.delphoto !== undefined) { if (!await confirmBox('Remove this photo?', 'Pins on it stay saved and come back if you upload a new photo.', 'Remove', true)) return;
      return busy(b, () => api('photo/delete', { body: { side: F.side } })).then(() => { S.photos.delete(F.side); render(); }).catch(() => {}); }
    if (d.savetotal !== undefined) { const v = $('#ftotal').value; return busy(b, () => saveMap(mp => mp.total_bulbs = v ? Math.max(1, Math.min(10000, +v)) : null, 'Saved')).then(render).catch(() => {}); }
  };
  m.onchange = async e => {
    const t = e.target, T = addressSpace();
    if (t.id === 'frange') { F.range = t.checked; F.end = F.range ? Math.min(T, F.bulb + 9) : F.bulb; return moved(); }
    if (t.id === 'fgo') { const w = F.end - F.bulb; F.bulb = Math.max(1, Math.min(T, +t.value || 1)); F.end = F.range ? Math.min(T, F.bulb + w) : F.bulb;
      t.value = F.bulb; const fs = $('#fs'), fe = $('#fe'); if (fs) { fs.value = F.bulb; fe.value = F.end; } return soft(); }
    if (t.id === 'fs' || t.id === 'fe') {
      const a = Math.max(1, Math.min(T, +$('#fs').value || 1)), z = Math.max(1, Math.min(T, +$('#fe').value || a));
      F.bulb = Math.min(a, z); F.end = Math.max(a, z); $('#fgo').value = F.bulb; return soft(); }
    if (t.id === 'fcolor') { F.color = t.value.toUpperCase(); t.parentElement.style.background = F.color; return soft(); }
    if (t.id === 'flive') { F.live = t.checked; return; }
    if (t.id === 'rkind') { R.kind = t.value === 'ridge' ? 'ridge' : 'edge'; return render(); }
    if (t.id === 'rtop' || t.id === 'rbottom') {
      const top = Math.max(0, Math.min(90, +$('#rtop').value || 0)), bottom = Math.max(top + 10, Math.min(100, +$('#rbottom').value || 100));
      R.top = top; R.bottom = bottom; R.showBand = true; return render(); }
    if (t.id === 'pfile' && t.files[0]) {
      const traced = (mapData().rooflines[F.side] || []).length;
      if (traced && !await confirmBox('Replace this photo?', `The ${traced} roofline section${traced === 1 ? ' was' : 's were'} traced on the old photo and will be removed. Landmark pins stay.`, 'Replace', true)) { t.value = ''; return; }
      try {
        if (traced) await saveMap(mp => { delete mp.rooflines[F.side]; }, 'Old rooflines removed');
        roofReset();
        const bmp = await createImageBitmap(t.files[0], { imageOrientation: 'from-image' });
        const k = Math.min(1, 1600 / Math.max(bmp.width, bmp.height)), cv = document.createElement('canvas');
        cv.width = Math.round(bmp.width * k); cv.height = Math.round(bmp.height * k); cv.getContext('2d').drawImage(bmp, 0, 0, cv.width, cv.height);
        let data = cv.toDataURL('image/jpeg', 0.82); if (data.length > 1_900_000) data = cv.toDataURL('image/jpeg', 0.6);
        await busy(null, () => api('photo', { body: { side: F.side, data } })); S.photoV = Date.now(); S.photos.add(F.side); toast('Photo saved'); render();
      } catch (err) { if (!/Request|photo/i.test(err.message)) toast("That image couldn't be opened. Try a JPEG or PNG.", true); }
    }
  };
  render();
};


/* ---------------------------------------------------------------- HOUSE MAP: rooflines (3.4)
   Each side's photo can carry traced roofline sections (see roofline.js).
   Auto-detect suggests the outer roofline from the photo, in this browser;
   the suggestion is a draft to adjust, and never replaces saved sections. */
const RL = window.Roofline;
const R = { tracing: false, draft: [], wire: [], kind: 'edge', editing: null, selected: null, history: [], top: 8, bottom: 78,
  flat: false, hint: '', aspect: 75, drag: null, dragged: false, dragEnd: 0 };
const roofId = () => 'r' + Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
function roofReset() { Object.assign(R, { tracing: false, draft: [], wire: [], editing: null, selected: null, history: [], hint: '' }); }
function roofRemember() { R.history = [...R.history.slice(-29), { draft: R.draft.map(p => [...p]), wire: [...R.wire] }]; }
function roofBegin(line) {
  Object.assign(R, { tracing: true, draft: line ? line.points.map(p => [...p]) : [], wire: [...(line?.wire || [])],
    kind: line?.kind || 'edge', editing: line?.id || null, selected: null, history: [], hint: '' });
}
/* SVG over the photo. The viewBox keeps the photo's proportions so points stay
   round: x runs 0-100 and y runs 0-aspect (stored y is percent of height). */
function roofSvg(md, side) {
  const A = R.aspect, Y = y => (y * A / 100).toFixed(2);
  const saved = (md.rooflines[side] || []).filter(l => l.id !== R.editing);
  const color = (l, lit) => !lit ? '#8A93B5' : l.kind === 'ridge' ? '#C7B2FF' : '#62D682';
  const dash = (l, lit) => !lit ? '1 1.6' : l.kind === 'ridge' ? '2.4 1.6' : '';
  let out = '';
  if (!R.tracing && S.photos.has(side) && R.showBand) out += `<rect class="band" x="0" y="0" width="100" height="${Y(R.top)}"/><rect class="band" x="0" y="${Y(R.bottom)}" width="100" height="${(A - R.bottom * A / 100).toFixed(2)}"/>
    <path class="bandline" d="M0 ${Y(R.top)}H100M0 ${Y(R.bottom)}H100" vector-effect="non-scaling-stroke"/>`;
  out += saved.flatMap(l => RL.roofSegments(l).map(s => `<line class="${R.tracing ? '' : 'seg'}" data-line="${esc(l.id)}" x1="${s.a[0]}" y1="${Y(s.a[1])}" x2="${s.b[0]}" y2="${Y(s.b[1])}"
    stroke="${color(l, s.lit)}" stroke-width="${s.lit ? 3 : 2}" stroke-linecap="round" vector-effect="non-scaling-stroke" ${dash(l, s.lit) ? `stroke-dasharray="${dash(l, s.lit)}"` : ''} opacity="${R.tracing ? .45 : 1}"><title>${esc(l.kind === 'ridge' ? 'Ridge' : 'Roof edge')}: click to adjust</title></line>`)).join('');
  if (R.tracing) {
    const l = { kind: R.kind, points: R.draft, wire: R.wire };
    out += RL.roofSegments(l).map(s => `<line data-seg="${s.index}" x1="${s.a[0]}" y1="${Y(s.a[1])}" x2="${s.b[0]}" y2="${Y(s.b[1])}" stroke="${color(l, s.lit)}"
      stroke-width="${s.lit ? 4 : 2.5}" stroke-linecap="round" vector-effect="non-scaling-stroke" ${dash(l, s.lit) ? `stroke-dasharray="${dash(l, s.lit)}"` : ''} style="pointer-events:visibleStroke;cursor:pointer"><title>Click: lights / wire only</title></line>`).join('');
    out += R.draft.map(([x, y], i) => `<circle class="pt" data-pt="${i}" cx="${x}" cy="${Y(y)}" r="${R.selected === i ? 1.5 : 1.1}" fill="${R.selected === i ? '#62D682' : '#FFFFFF'}"
      stroke="#171C33" stroke-width="1.5" vector-effect="non-scaling-stroke" tabindex="0" role="button" aria-label="Roofline point ${i + 1}"/>`).join('');
  }
  return `<svg class="roof ${R.tracing ? 'tracing' : ''}" id="roofsvg" viewBox="0 0 100 ${A.toFixed(2)}" preserveAspectRatio="none" aria-label="Rooflines on this photo">${out}</svg>`;
}
function roofHtml(md, side) {
  const lines = md.rooflines[side] || [], has = S.photos.has(side);
  const sideName = (md.sides.find(x => x.id === side) || {}).name || side;
  const flat = R.flat ? `<div class="panel stack"><div class="row"><h2 class="grow">Flat diagram</h2>
      <button class="small" data-flatsvg>Download SVG</button><button class="small ghost" data-flat>Close</button></div>
      <div class="flatmap">${RL.flatHouseSvg(md.sides, md.rooflines, md.landmarks, 'Flat diagram of every side')}</div>
      <p class="note">Every side unfolded, with landmark pins and their bulb numbers. Traced from your photos, so it isn't to scale.</p></div>` : '';
  const toolbar = R.tracing ? `<div class="roofbar">
      <label class="field">Kind<select id="rkind"><option value="edge" ${R.kind === 'edge' ? 'selected' : ''}>Roof edge / eave</option><option value="ridge" ${R.kind === 'ridge' ? 'selected' : ''}>Ridge</option></select></label>
      <button class="small ghost" data-rundo ${R.history.length ? '' : 'disabled'}>Undo</button>
      ${R.selected !== null ? `<button class="small ghost" data-rdelpt>Delete point ${R.selected + 1}</button><button class="small ghost" data-rappend>Add at the end</button>` : ''}
      <button class="small primary" data-rsave ${R.draft.length < 2 ? 'disabled' : ''}>Save section</button><button class="small ghost" data-rcancel>Cancel</button></div>
      <p class="note">${R.draft.length} point${R.draft.length === 1 ? '' : 's'}${R.selected !== null ? ` · point ${R.selected + 1} selected` : ''}. Tap the photo to add a point${R.selected !== null ? ' after the selected one' : ''}; drag points (or use the arrow keys) to adjust. Tap a stretch between points to mark it <b>wire only</b> (no bulbs there).</p>`
    : has ? `<div class="roofbar"><button class="small" data-rdetect>Auto-detect roofline</button><button class="small ghost" data-rtrace>Trace by hand</button>
      <label class="field">Search from %<input type="number" id="rtop" min="0" max="90" value="${R.top}"></label>
      <label class="field">to %<input type="number" id="rbottom" min="10" max="100" value="${R.bottom}"></label>
      <button class="small ghost" data-flat>${R.flat ? 'Hide' : 'Show'} flat diagram</button></div>` : `<div class="roofbar"><button class="small ghost" data-flat>${R.flat ? 'Hide' : 'Show'} flat diagram</button></div>`;
  const list = !R.tracing && lines.length ? `<div class="list">${lines.map((l, i) => `<div class="item"><div class="grow"><div class="name">${l.kind === 'ridge' ? 'Ridge' : 'Roof edge'} ${i + 1}</div>
      <div class="sub">${l.points.length} points${(l.wire || []).length ? ` · ${l.wire.length} wire-only stretch${l.wire.length === 1 ? '' : 'es'}` : ''}</div></div>
      <button class="small ghost" data-redit="${esc(l.id)}">Adjust</button><button class="small ghost danger" data-rdel="${esc(l.id)}" aria-label="Delete this section">✕</button></div>`).join('')}</div>` : '';
  const hint = R.hint ? `<p class="callout" role="status">${esc(R.hint)}</p>` : '';
  const legend = `<p class="small muted legend-dots">Rooflines on the ${esc(sideName.toLowerCase())}:<i style="background:#62D682"></i>roof edge<i style="background:#C7B2FF"></i>ridge<i style="background:#8A93B5"></i>wire only</p>`;
  return { flat, overlay: has ? roofSvg(md, side) : '', tools: `<div class="stack">${legend}${toolbar}${hint}${list}</div>` };
}
function roofRedraw(md, side) { const svg = $('#roofsvg'); if (svg) svg.outerHTML = roofSvg(md, side); roofWire(md, side); }
function roofPos(svg, e) {
  const r = svg.getBoundingClientRect();
  return [Math.round(Math.max(0, Math.min(100, (e.clientX - r.left) / r.width * 100)) * 10) / 10,
          Math.round(Math.max(0, Math.min(100, (e.clientY - r.top) / r.height * 100)) * 10) / 10];
}
/* Pointer and keyboard handling on the overlay (re-attached after each draw). */
function roofWire(md, side) {
  const svg = $('#roofsvg'); if (!svg) return;
  const img = $('#pimg');
  if (img && img.naturalWidth && Math.abs(R.aspect - img.naturalHeight / img.naturalWidth * 100) > .01) {
    R.aspect = img.naturalHeight / img.naturalWidth * 100; return roofRedraw(md, side);
  }
  svg.onpointerdown = e => {
    const pt = e.target.closest('[data-pt]'); if (!pt || !R.tracing) return;
    e.preventDefault(); roofRemember(); R.drag = +pt.dataset.pt; R.selected = R.drag; R.dragged = false;
    svg.setPointerCapture(e.pointerId);
  };
  svg.onpointermove = e => {
    if (R.drag === null) return;
    R.draft[R.drag] = roofPos(svg, e); R.dragged = true;
    const c = svg.querySelector(`[data-pt="${R.drag}"]`); if (c) { c.setAttribute('cx', R.draft[R.drag][0]); c.setAttribute('cy', R.draft[R.drag][1] * R.aspect / 100); }
  };
  svg.onpointerup = svg.onpointercancel = e => {
    if (R.drag === null) return;
    if (svg.hasPointerCapture(e.pointerId)) svg.releasePointerCapture(e.pointerId);
    R.drag = null;
    if (!R.dragged) R.history.pop();
    else R.dragEnd = performance.now();   // the click that ends a drag isn't a new point
    R.dragged = false;
    roofRedraw(md, side);
  };
  svg.onkeydown = e => {
    const pt = e.target.closest('[data-pt]'); if (!pt || !R.tracing) return;
    const i = +pt.dataset.pt, k = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }[e.key];
    if (k) {
      e.preventDefault(); roofRemember(); R.selected = i;
      R.draft[i] = [Math.max(0, Math.min(100, R.draft[i][0] + k[0] * (e.shiftKey ? 2 : .5))), Math.max(0, Math.min(100, R.draft[i][1] + k[1] * (e.shiftKey ? 2 : .5)))];
      roofRedraw(md, side); $(`#roofsvg [data-pt="${i}"]`)?.focus();
    } else if (e.key === 'Delete' || e.key === 'Backspace') { e.preventDefault(); R.selected = i; roofDeletePoint(); VIEWS.mapRender(); }
  };
}
function roofDeletePoint() {
  if (R.selected === null) return;
  roofRemember();
  R.wire = RL.deleteWirePoint(R.wire, R.selected, R.draft.length);
  R.draft.splice(R.selected, 1); R.selected = null;
}
async function roofDetect() {
  const img = $('#pimg'); if (!img || !img.naturalWidth) throw new Error('The photo is still loading.');
  const k = Math.min(1, 320 / Math.max(img.naturalWidth, img.naturalHeight)), c = document.createElement('canvas');
  c.width = Math.round(img.naturalWidth * k); c.height = Math.round(img.naturalHeight * k);
  const ctx = c.getContext('2d', { willReadFrequently: true }); ctx.drawImage(img, 0, 0, c.width, c.height);
  const res = RL.detectRoofline(ctx.getImageData(0, 0, c.width, c.height), { top: R.top, bottom: R.bottom });
  if (!res.points.length) { R.hint = res.message; return; }
  roofBegin(); R.draft = res.points;
  R.hint = res.message + (res.quality === 'strong' ? '' : ' This one needs a careful look.') + ' Then choose Save section.';
}
/* Clicks in the map view that belong to the roofline tools. Returns true if handled. */
async function roofClick(e, b, md, side) {
  const svg = e.target.closest('#roofsvg');
  if (!b && R.tracing && performance.now() - R.dragEnd < 300) return true;
  if (!b && svg) {
    const pt = e.target.closest('[data-pt]'), seg = e.target.closest('[data-seg]'), saved = e.target.closest('[data-line]');
    if (R.tracing && pt) { R.selected = +pt.dataset.pt; VIEWS.mapRender(); return true; }
    if (R.tracing && seg) { roofRemember(); const i = +seg.dataset.seg; R.wire = R.wire.includes(i) ? R.wire.filter(x => x !== i) : [...R.wire, i]; VIEWS.mapRender(); return true; }
    if (R.tracing) {
      if (R.draft.length >= RL.LIMITS.points) { toast(`At most ${RL.LIMITS.points} points per section.`, true); return true; }
      roofRemember();
      const p = roofPos(svg, e), at = R.selected === null ? R.draft.length : R.selected + 1;
      R.wire = RL.insertWirePoint(R.wire, at, R.draft.length);
      R.draft.splice(at, 0, p); R.selected = at; VIEWS.mapRender(); return true;
    }
    if (saved) { const l = (md.rooflines[side] || []).find(x => x.id === saved.dataset.line); if (l) { roofBegin(l); VIEWS.mapRender(); } return true; }
    return false;
  }
  if (!b) return false;
  const d = b.dataset;
  if (d.flat !== undefined) { R.flat = !R.flat; VIEWS.mapRender(); return true; }
  if (d.flatsvg !== undefined) {
    const url = URL.createObjectURL(new Blob([RL.flatHouseSvg(md.sides, md.rooflines, md.landmarks)], { type: 'image/svg+xml' }));
    const a = Object.assign(document.createElement('a'), { href: url, download: 'eaveluxos-house-rooflines.svg' });
    document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 2000); return true;
  }
  if (d.rdetect !== undefined) { await busy(b, roofDetect).catch(err => { R.hint = err.message; }); R.showBand = false; VIEWS.mapRender(); return true; }
  if (d.rtrace !== undefined) { roofBegin(); VIEWS.mapRender(); return true; }
  if (d.rundo !== undefined) { const h = R.history.pop(); if (h) { R.draft = h.draft; R.wire = h.wire; R.selected = null; } VIEWS.mapRender(); return true; }
  if (d.rdelpt !== undefined) { roofDeletePoint(); VIEWS.mapRender(); return true; }
  if (d.rappend !== undefined) { R.selected = null; VIEWS.mapRender(); return true; }
  if (d.rcancel !== undefined) { roofReset(); VIEWS.mapRender(); return true; }
  if (d.rsave !== undefined) {
    const line = { id: R.editing || roofId(), kind: R.kind, points: R.draft.map(p => [...p]), wire: [...R.wire].sort((x, y) => x - y) };
    if (!RL.validSection(line)) { toast('That section needs 2 to 100 points on the photo.', true); return true; }
    await busy(b, () => saveMap(mp => {
      const list = (mp.rooflines[side] || []).slice(), i = list.findIndex(l => l.id === line.id);
      if (i >= 0) list[i] = line; else { if (list.length >= RL.LIMITS.sections) throw new Error(`At most ${RL.LIMITS.sections} sections per side.`); list.push(line); }
      mp.rooflines[side] = list;
    }, 'Roofline saved')).then(() => { roofReset(); VIEWS.mapRender(); }).catch(() => {});
    return true;
  }
  if (d.redit) { const l = (md.rooflines[side] || []).find(x => x.id === d.redit); if (l) { roofBegin(l); VIEWS.mapRender(); } return true; }
  if (d.rdel) {
    if (!await confirmBox('Delete this roofline section?', 'It’s removed from this side and from the flat diagram.', 'Delete', true)) return true;
    await busy(b, () => saveMap(mp => { mp.rooflines[side] = (mp.rooflines[side] || []).filter(l => l.id !== d.rdel); if (!mp.rooflines[side].length) delete mp.rooflines[side]; }, 'Section deleted')).catch(() => {});
    VIEWS.mapRender(); return true;
  }
  return false;
}


/* ---------------------------------------------------------------- CREATE: bulb painter (3.5)
   Paint the pattern bulb by bulb, by range or every Nth bulb, either within
   one repeat of the sequence or across the whole house, then turn it back
   into color runs (painter.js). The controller holds 30 runs, so the slot
   count is shown live and Apply is refused past 30. */
const PT = window.Painter;
function painterOpen(D) {
  const unit = PT.expand(D.segs);
  D.paint = { scope: 'repeat', canvas: unit.length ? unit : ['#FFFFFF'], hist: [], color: D.segs[D.sel]?.c || '#FF0000',
    from: 1, to: Math.min(unit.length || 1, 10), step: 3, width: 1, anchor: null, hover: '' };
}
function painterSet(P, next) { P.hist = [...P.hist.slice(-49), P.canvas]; P.canvas = next; }
function painterHtml(D) {
  const P = D.paint, T = addressSpace(), slots = PT.slotsNeeded(P.canvas), over = slots > PT.MAX_SLOTS;
  const zones = mapData().zones;
  const sw = c => c === 'off' ? 'class="off"' : `style="background:${esc(c)}"`;
  return `<div class="panel stack painter">
    <div class="row" style="justify-content:space-between"><h3>Paint bulbs</h3>
      <span class="small ${over ? 'callout warn' : 'muted'}" id="pslots">${slots} of ${PT.MAX_SLOTS} color slots</span></div>
    <div class="row">
      <label class="check"><input type="radio" name="pscope" value="repeat" ${P.scope === 'repeat' ? 'checked' : ''}><span><b>One repeat</b> <span class="small muted">· repeats along the roofline</span></span></label>
      <label class="check"><input type="radio" name="pscope" value="house" ${P.scope === 'house' ? 'checked' : ''}><span><b>Whole house</b> <span class="small muted">· bulbs 1–${T}, no repeat</span></span></label></div>
    ${P.scope === 'repeat' ? `<label class="row small">Bulbs in one repeat <input type="number" id="plen" min="1" max="${PT.MAX_SLOTS * PT.PER_SLOT}" value="${P.canvas.length}" style="width:7em"></label>` : ''}
    <canvas class="strip" id="pstrip" aria-label="Bulbs ${1}–${P.canvas.length}. Click a bulb to paint it; Shift-click to paint a range."></canvas>
    <p class="small muted" id="phover">${esc(P.hover || 'Click a bulb to paint it. Shift-click another bulb to paint everything between.')}</p>
    <div class="stack" style="gap:8px"><span class="small">Paint color</span>
      <div class="palette">${S.catalog.palette.map(p => `<button data-pcolor="${p.hex}" title="${esc(p.name)}" aria-label="${esc(p.name)}" aria-pressed="${P.color === p.hex}" style="background:${p.hex}"></button>`).join('')}
        <button data-pcolor="off" class="off" title="Zone off: dark and skipped by movement" aria-label="Zone off" aria-pressed="${P.color === 'off'}"></button>
        <label class="custom" title="Any color"><input type="color" id="ppick" value="${P.color === 'off' ? '#000000' : P.color.toLowerCase()}" aria-label="Pick any paint color"></label>
        <span class="chip-now"><i ${sw(P.color)}></i>${P.color === 'off' ? 'Zone off' : esc(P.color)}</span></div></div>
    <div class="paintgrid">
      <label class="field">First bulb<input type="number" id="pfrom" min="1" max="${P.canvas.length}" value="${P.from}"></label>
      <label class="field">Last bulb<input type="number" id="pto" min="1" max="${P.canvas.length}" value="${P.to}"></label>
      ${P.scope === 'house' && zones.length ? `<label class="field">Or a zone<select id="pzone"><option value="">Choose…</option>${zones.map((z, i) => `<option value="${i}">${esc(z.name)} (${z.start}–${z.end})</option>`).join('')}</select></label>` : ''}
      <div class="row" style="align-self:end"><button class="small" data-prange>Paint range</button></div>
      <label class="field">Every N bulbs<input type="number" id="pstep" min="2" max="${P.canvas.length}" value="${P.step}"></label>
      <label class="field">Width<input type="number" id="pwidth" min="1" max="89" value="${P.width}"></label>
      <div class="row" style="align-self:end"><button class="small" data-pevery>Paint every ${P.step}${P.width > 1 ? ` (${P.width} wide)` : 'th'}</button></div>
    </div>
    <p class="note">“Every” paints within First–Last: every 4 with width 2 from bulb 1 paints 1–2, 5–6, 9–10…</p>
    <div class="row"><button class="small ghost" data-pfill>Fill everything</button><button class="small ghost" data-pundo ${P.hist.length ? '' : 'disabled'}>Undo</button></div>
    ${over ? `<p class="callout warn">The controller stores at most ${PT.MAX_SLOTS} color runs (a run is a stretch of one color, up to ${PT.PER_SLOT} bulbs). This needs ${slots}. Use fewer separate bulbs or ranges${P.scope === 'house' ? ', or paint one repeat instead of the whole house' : ''}.</p>` : ''}
    <div class="row"><button class="primary" data-papply ${over ? 'disabled' : ''}>Use this pattern</button><button class="ghost" data-pcancel>Cancel</button></div>
  </div>`;
}
/* Draw the strip: one dot per bulb, numbers every 10, the First–Last range
   outlined, and (whole house) the House map's landmarks marked below. */
function painterDraw(D) {
  const cv = $('#pstrip'); if (!cv) return;
  const P = D.paint, N = P.canvas.length, dpr = window.devicePixelRatio || 1;
  const Wcss = cv.clientWidth || 600, cell = N > 600 ? 9 : N > 200 ? 12 : 16, perRow = Math.max(10, Math.floor((Wcss - 8) / cell));
  const rows = Math.ceil(N / perRow), rowH = cell + 12, Hcss = rows * rowH + 6;
  cv.style.height = Hcss + 'px'; cv.width = Wcss * dpr; cv.height = Hcss * dpr;
  const ctx = cv.getContext('2d'); ctx.scale(dpr, dpr); ctx.clearRect(0, 0, Wcss, Hcss);
  const marks = P.scope === 'house' ? new Set(mapData().landmarks.map(l => l.bulb)) : new Set();
  const a = Math.min(P.from, P.to), b = Math.max(P.from, P.to);
  ctx.font = '9px system-ui, sans-serif'; ctx.textAlign = 'center';
  for (let i = 0; i < N; i++) {
    const x = 4 + (i % perRow) * cell + cell / 2, y = 3 + Math.floor(i / perRow) * rowH + cell / 2 + 9, r = cell / 2 - 1.5, c = P.canvas[i];
    if ((i + 1) % 10 === 0 || i === 0) { ctx.fillStyle = 'rgba(128,136,170,.9)'; ctx.fillText(String(i + 1), x, y - r - 2.5); }
    if (i + 1 >= a && i + 1 <= b) { ctx.fillStyle = 'rgba(244,166,35,.22)'; ctx.fillRect(x - cell / 2, y - cell / 2, cell, cell); }
    ctx.beginPath(); ctx.arc(x, y, r, 0, 7);
    if (c === 'off') { ctx.strokeStyle = 'rgba(150,155,185,.7)'; ctx.lineWidth = 1; ctx.stroke(); ctx.beginPath(); ctx.moveTo(x - r * .6, y - r * .6); ctx.lineTo(x + r * .6, y + r * .6); ctx.stroke(); }
    else { ctx.fillStyle = c; ctx.fill(); ctx.strokeStyle = 'rgba(0,0,0,.35)'; ctx.lineWidth = .8; ctx.stroke(); }
    if (marks.has(i + 1)) { ctx.fillStyle = '#F4A623'; ctx.beginPath(); ctx.moveTo(x, y + r + 1); ctx.lineTo(x - 3, y + r + 5); ctx.lineTo(x + 3, y + r + 5); ctx.fill(); }
  }
  const at = e => { const rc = cv.getBoundingClientRect(), col = Math.floor((e.clientX - rc.left - 4) / cell), row = Math.floor((e.clientY - rc.top - 3) / rowH);
    const i = row * perRow + col; return col >= 0 && col < perRow && i >= 0 && i < N ? i + 1 : null; };
  cv.onmousemove = e => { const n = at(e), h = $('#phover'); if (!h) return;
    const lm = n && P.scope === 'house' ? mapData().landmarks.find(l => l.bulb === n) : null;
    h.textContent = n ? `Bulb ${n}: ${P.canvas[n - 1] === 'off' ? 'zoned off' : P.canvas[n - 1]}${lm ? ` · ${lm.name}` : ''}` : (P.hover || ''); };
  cv.onclick = e => {
    const n = at(e); if (!n) return;
    try {
      if (e.shiftKey && P.anchor) { const [f, t] = [Math.min(P.anchor, n), Math.max(P.anchor, n)]; painterSet(P, PT.paintRange(P.canvas, f, t, P.color)); P.from = f; P.to = t; }
      else { painterSet(P, PT.paintBulb(P.canvas, n, P.color)); P.from = P.to = n; }
      P.anchor = n; P.hover = `Painted ${P.from === P.to ? `bulb ${n}` : `bulbs ${P.from}–${P.to}`}.`;
      VIEWS.createRender();
    } catch (err) { toast(err.message, true); }
  };
}
/* Clicks and changes inside the painter. Returns true if handled. */
function painterClick(D, d) {
  const P = D.paint; if (!P) return false;
  const run = (fn, what) => { try { painterSet(P, fn()); P.hover = what; VIEWS.createRender(); } catch (err) { toast(err.message, true); } return true; };
  if (d.pcolor) { P.color = d.pcolor; VIEWS.createRender(); return true; }
  if (d.prange !== undefined) return run(() => PT.paintRange(P.canvas, P.from, P.to, P.color), `Painted bulbs ${P.from}\u2013${P.to}.`);
  if (d.pevery !== undefined) return run(() => PT.paintEvery(P.canvas, P.from, P.to, P.step, P.width, P.color),
    `Painted every ${P.step} bulbs${P.width > 1 ? `, ${P.width} at a time,` : ''} from ${P.from} to ${P.to}.`);
  if (d.pfill !== undefined) return run(() => PT.fill(P.canvas, P.color), 'Filled every bulb.');
  if (d.pundo !== undefined) { if (P.hist.length) P.canvas = P.hist.pop(); P.hover = 'Undone.'; VIEWS.createRender(); return true; }
  if (d.pcancel !== undefined) { D.paint = null; VIEWS.createRender(); return true; }
  if (d.papply !== undefined) {
    const segs = PT.compress(P.canvas);
    if (segs.length > PT.MAX_SLOTS) { toast(`That needs ${segs.length} color slots; the controller allows ${PT.MAX_SLOTS}.`, true); return true; }
    D.segs = segs; D.sel = 0; D.paint = null;
    toast(`${segs.length} color slot${segs.length === 1 ? '' : 's'}. Save the pattern to keep it.`);
    VIEWS.createRender(); return true;
  }
  return false;
}
function painterChange(D, t) {
  const P = D.paint; if (!P) return false;
  const N = P.canvas.length, int = (v, lo, hi, dflt) => Math.max(lo, Math.min(hi, Math.round(+v) || dflt));
  if (t.name === 'pscope') {
    if (t.value === 'house' && P.scope !== 'house') { painterSet(P, PT.expand(PT.compress(P.canvas), addressSpace())); P.scope = 'house'; }
    else if (t.value === 'repeat') P.scope = 'repeat';
    P.from = 1; P.to = Math.min(P.canvas.length, 10); VIEWS.createRender(); return true;
  }
  if (t.id === 'plen') { if (+t.value === P.canvas.length) return true; try { painterSet(P, PT.resize(P.canvas, t.value)); P.to = Math.min(P.to, P.canvas.length); P.from = Math.min(P.from, P.to); } catch (err) { toast(err.message, true); } VIEWS.createRender(); return true; }
  if (t.id === 'pfrom') { P.from = int(t.value, 1, N, 1); t.value = P.from; painterDraw(D); return true; }
  if (t.id === 'pto') { P.to = int(t.value, 1, N, N); t.value = P.to; painterDraw(D); return true; }
  // Number boxes update in place: re-rendering on "change" (fired on blur) would
  // swap out the button the person is clicking.
  const everyLabel = () => { const btn = $('[data-pevery]'); if (btn) btn.textContent = `Paint every ${P.step}${P.width > 1 ? ` (${P.width} wide)` : 'th'}`; };
  if (t.id === 'pstep') { P.step = int(t.value, 2, Math.max(2, N), 3); t.value = P.step; everyLabel(); return true; }
  if (t.id === 'pwidth') { P.width = int(t.value, 1, 89, 1); t.value = P.width; everyLabel(); return true; }
  if (t.id === 'ppick') { P.color = t.value.toUpperCase(); VIEWS.createRender(); return true; }
  if (t.id === 'pzone' && t.value !== '') { const z = mapData().zones[+t.value]; P.from = Math.min(z.start, N); P.to = Math.min(z.end, N); VIEWS.createRender(); return true; }
  return false;
}

/* Paint-by-zone dialog for the designer. */
function zonePainter(D, rerender) {
  const md = mapData(), T = addressSpace();
  if (!md.zones.length) return confirmBox('No zones yet', 'Open <b>House map</b>, select a range with the bulb finder and save it as a zone (for example \u201cGarage roof\u201d). Then come back here to paint it.', 'OK');
  const opts = sel => `<option value="">Leave as the rest</option>${S.catalog.palette.map(p => `<option value="${p.hex}" ${sel === p.hex ? 'selected' : ''}>${esc(p.name)}</option>`).join('')}<option value="off">\u2715 Zone off</option><option value="custom">Other color\u2026</option>`;
  dialog(`<h2>Paint by zone</h2><p class="note">${T} bulbs. Later zones in the list win where zones overlap.</p>
    <div class="stack">${md.zones.map((z, i) => `<div class="row"><div class="grow" style="min-width:9em"><b>${esc(z.name)}</b><div class="small muted">Bulbs ${z.start}\u2013${z.end}</div></div>
      <select name="z${i}" style="width:auto">${opts('')}</select><input type="color" name="c${i}" value="#ffffff" hidden aria-label="Color for ${esc(z.name)}"></div>`).join('')}</div>
    <label class="field">Everything else<select name="base"><option value="off">\u2715 Zone off (dark, never moves)</option><option value="#000000">Black</option>${S.catalog.palette.filter(p => p.hex !== '#000000').map(p => `<option value="${p.hex}">${esc(p.name)}</option>`).join('')}</select></label>
    <p class="note" data-slots></p>`,
  async f => {
    const assign = md.zones.map((z, i) => ({ start: z.start, end: z.end, color: f['z' + i].value === 'custom' ? f['c' + i].value.toUpperCase() : f['z' + i].value })).filter(a => a.color);
    if (!assign.length) throw new Error('Choose a color for at least one zone.');
    const segs = paintZones(assign, f.base.value, T);
    if (segs.length > MAX_SLOTS) throw new Error(`That needs ${segs.length} color slots, but the controller allows ${MAX_SLOTS}. Use fewer zones or larger ones.`);
    D.segs = segs; D.sel = 0; D.mode = 0;
    if (!D.label) D.label = 'Zones';
    toast('Zones painted. Preview it, then save.'); rerender();
  }, { ok: 'Paint', onOpen: f => {
    const upd = () => {
      md.zones.forEach((_, i) => { f['c' + i].hidden = f['z' + i].value !== 'custom'; });
      const assign = md.zones.map((z, i) => ({ start: z.start, end: z.end, color: f['z' + i].value === 'custom' ? f['c' + i].value : f['z' + i].value })).filter(a => a.color);
      const n = assign.length ? paintZones(assign, f.base.value, T).length : 0;
      $('[data-slots]', f).textContent = n ? `Uses ${n} of ${MAX_SLOTS} color slots.${n > MAX_SLOTS ? ' Too many.' : ''}` : '';
    };
    f.addEventListener('change', upd); f.addEventListener('input', upd); upd();
  } });
}

/* Safety net panel (Schedule tab). */
async function safetyPanel(box) {
  let st;
  try { st = await api('safety'); } catch (e) { box.innerHTML = `<p class="muted">${esc(e.message)}</p>`; return; }
  const devs = Object.values(st.devices || {});
  const conflicts = devs.flatMap(d => d.conflicts || []);
  box.innerHTML = `<div class="panel-head"><h2>Safety net</h2><label class="check"><input type="checkbox" id="sfon" ${st.enabled ? 'checked' : ''}> On</label></div>
    <p class="note">Copies the next nights into the controller's own timers, so the lights still come on and go off if this computer or the internet is down.
      The app keeps running the lights as usual. It backs up the controller before every change, only touches timers and patterns it created itself (named \u201cAuto \u2026\u201d), and checks every write.</p>
    ${st.enabled ? `
      <label class="row small">Copy the next <select id="sfdays" style="width:auto">${[3, 5, 7, 10, 14].map(n => `<option ${n === st.days ? 'selected' : ''}>${n}</option>`).join('')}</select> nights</label>
      ${devs.length ? devs.map(d => `<p class="callout small ${d.ok ? 'ok' : 'warn'}">${d.ok ? 'Armed' : 'Not armed'}: ${esc(d.message || '')}${d.last_sync_label ? ` <span class="muted">(${esc(d.last_sync_label)})</span>` : ''}
        ${d.backup ? `<br><a href="#" data-backup="${esc(d.backup)}">Download the controller backup taken before this change</a>` : ''}</p>`).join('') : '<p class="note">Waiting for the first copy (a few seconds after the app talks to the controller).</p>'}
      ${conflicts.includes('daily') ? `<p class="callout warn small">The Trimlight app's daily timers are on. In Timer mode they would run too. <button class="small" data-dailyoff>Turn them off</button></p>` : ''}
      ${conflicts.some(c => c.startsWith('calendar:')) ? '<p class="callout small">The controller also has calendar events made in the Trimlight app. They\u2019re left alone, but they will run in Timer mode too if their dates overlap.</p>' : ''}
      ${st.plan.length ? `<details><summary>What the controller will do on its own</summary><div class="list">${st.plan.map(p => `<div class="item"><div class="grow"><b>${esc(p.date.replace(/^(\d\d)-(\d\d)$/, (_, mo, dy) => MONTHS[+mo - 1] + ' ' + (+dy)))}</b> <span class="sub">${esc(p.rule)}</span></div>
        <span class="num small">${esc(hm12(p.on))} \u2013 ${esc(hm12(p.off))}</span><span class="small">${esc(p.pattern)}</span></div>`).join('')}</div></details>` : ''}
      <div><button class="small" data-sfsync>Update now</button></div>
      <p class="note">On a normal night the controller now runs the lights itself from its copy, so they also go off on time if this computer stops. After a manual change, weather or the security flash, the app keeps control for the rest of that night; if it stops then, the lights stay on until it returns. Weather, minute-by-minute rotation, sliders and anything after midnight need the app.</p>` : ''}`;
  box.onchange = async e => {
    if (e.target.id === 'sfon' || e.target.id === 'sfdays') {
      const n = clone(S.settings); n.safety = { enabled: $('#sfon', box).checked, days: +($('#sfdays', box)?.value || st.days || 7) };
      await busy(null, () => saveSettings(n, n.safety.enabled ? 'Safety net on' : 'Safety net off. Removing its timers from the controller.')).catch(() => {});
      setTimeout(() => safetyPanel(box), 2500);
    }
  };
  box.onclick = async e => {
    const a = e.target.closest('[data-backup]');
    if (a) { e.preventDefault(); const data = await api('safety/backup?file=' + encodeURIComponent(a.dataset.backup));
      const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }));
      const link = Object.assign(document.createElement('a'), { href: url, download: a.dataset.backup }); document.body.append(link); link.click(); link.remove(); return; }
    const b = e.target.closest('button'); if (!b) return;
    if (b.dataset.sfsync !== undefined) busy(b, () => api('safety/sync', { body: {} })).then(() => { toast('Safety net updated'); safetyPanel(box); }).catch(() => {});
    if (b.dataset.dailyoff !== undefined && await confirmBox('Turn off the Trimlight app\u2019s daily timers?', 'The controller is backed up first. You can turn them back on in the Trimlight app.', 'Turn off'))
      busy(b, () => api('safety/daily_off', { body: {} })).then(r => { toast(`Turned off ${r.turned_off} daily timer${r.turned_off === 1 ? '' : 's'}`); api('safety/sync', { body: {} }).then(() => safetyPanel(box)); }).catch(() => {});
  };
}
