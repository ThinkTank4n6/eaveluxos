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
  power: '<path d="M12 3.5v8"/><path d="M7.2 6.6a7.5 7.5 0 1 0 9.6 0"/>',
  bulbon: '<path d="M9 17.5h6M10 21h4"/><path d="M8.2 14.2A6 6 0 1 1 15.8 14.2c-.8.8-1.3 1.8-1.3 2.9v.4h-5v-.4c0-1.1-.5-2.1-1.3-2.9z"/><path d="M12 2.2v-0M4 9.5H3M21 9.5h-1"/>',
  exit: '<path d="M14 4.5h4.5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1H14"/><path d="M10 8l-4 4 4 4M6 12h9.5"/>',
  music: '<path d="M9 17.5V6.5l10-2.2v11"/><circle cx="6.6" cy="17.6" r="2.4"/><circle cx="16.6" cy="15.4" r="2.4"/><path d="M9 9.6l10-2.2"/>',
  settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
};
const TABS = [['home','Home'],['patterns','Patterns'],['create','Create'],['map','House map'],['schedule','Schedule'],['music','Music'],['lights','Lights'],['time','Date & Time'],['settings','Settings'],['manual','Manual']];
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
  statusPill(S.status);
  return S.status;
}
function statusPill(st) {
  if (st.setup_only) setPill('', 'Setup needed');
  else if (st.setup && st.setup.problem) setPill('bad', 'Check settings');
  else if (st.target.reason === 'music') setPill('ok', 'Music show');
  else if (st.error) setPill('bad', "Can't reach lights");
  else setPill('ok', st.target.on ? 'Lights on' : 'Lights off');
  // The header On/Off: the one matching what the lights are doing is greyed
  // out. During a music show what the lights show isn't known: both work.
  const t = st.target || {}, music = t.reason === 'music';
  const on = $('#quick [data-q=on]'), off = $('#quick [data-q=off]');
  if (on) on.disabled = !!st.setup_only || (t.on && !music);
  if (off) off.disabled = !!st.setup_only || (!t.on && !music);
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
  buildQuick(u.role !== 'viewer', !!s.local);
  if (!$('#ribbon').children.length) buildRibbon();
  await Promise.all([loadSettings(), loadCatalog()]);
  if (!s.setup.wizard_done && u.role === 'admin') return wizard(0);
  // The status at the top right (and its On/Off buttons) on every page, not
  // only after Home or Music has loaded it; kept fresh while the tab is open.
  refreshStatus().catch(() => {});
  clearInterval(boot._pill);
  boot._pill = setInterval(() => { if (!document.hidden) refreshStatus().catch(() => {}); }, 60000);
  go((location.hash || '#home').slice(1));
}
/* Header buttons next to the status pill: lights on, lights off, and (only on
   the computer the app runs on) Quit. */
function buildQuick(canControl, local) {
  const q = $('#quick');
  const btn = (k, ic, label, title) => `<button type="button" class="qbtn${k === 'quit' ? ' qquit' : ''}" data-q="${k}" title="${title}" aria-label="${title}">${icon(ic)}<span class="qlbl">${label}</span></button>`;
  q.innerHTML = (canControl ? btn('on', 'bulbon', 'On', 'Turn the lights on') + btn('off', 'power', 'Off', 'Turn the lights off') : '')
    + (local ? btn('quit', 'exit', 'Quit', 'Quit the app') : '');
  q.hidden = !q.innerHTML;
  q.onclick = async e => {
    const b = e.target.closest('button'); if (!b) return;
    if (b.dataset.q === 'quit') return quitApp();
    const on = b.dataset.q === 'on';
    busy(b, async () => {
      S.status = await api('action', { body: { action: on ? 'on' : 'off' } });
      statusPill(S.status);
      const t = S.status.target;
      toast(on ? `Lights on: ${t.effect || 'on'}, until the next scheduled change.` : 'Lights off until the next scheduled change.');
      if (S.view === 'home' || S.view === 'music') VIEWS[S.view]();
    }).catch(() => {});
  };
}
/* Results of Settings › Phones › Check this computer. */
function lanShow(r) {
  const box = $('#lanresult'); if (!box) return;
  const w = r.windows, out = [];
  if (!w) {
    out.push(r.system === 'Darwin'
      ? '<p class="note">On a Mac: System Settings \u203a Network \u203a Firewall. If it\u2019s on, open <b>Options</b> and make sure EaveLuxOS is set to <b>Allow incoming connections</b>.</p>'
      : '<p class="note">On Linux, if a firewall is on (for example ufw), allow the port: <code>sudo ufw allow ' + esc(r.port) + '/tcp</code>.</p>');
  } else if (w.error) {
    out.push(`<p class="callout warn">${esc(w.error)}</p>`);
  } else {
    const ok = !w.public && !w.blocked_rules.length && w.allowed;
    if (w.public) out.push('<p class="callout warn"><b>This computer\u2019s network is set to Public,</b> so Windows blocks phones. Make it Private: <b>Settings \u203a Network &amp; internet</b>, click <b>Ethernet</b> or <b>Wi-Fi</b>, then your network, and choose <b>Private network</b>. Only do this on your home network.</p>');
    if (w.blocked_rules.length) out.push(`<p class="callout warn"><b>Windows Firewall is blocking this app</b> (probably from pressing Cancel when Windows first asked). Rule${w.blocked_rules.length > 1 ? 's' : ''}: ${w.blocked_rules.map(esc).join(', ')}.</p>`);
    else if (!w.allowed) out.push('<p class="callout">No Windows Firewall rule lets phones reach the app yet.</p>');
    if (w.blocked_rules.length || !w.allowed) out.push('<div class="row"><button class="primary small" data-lanallow>Let phones in</button></div><p class="note">Windows asks for permission on this computer. It switches off rules blocking this app and lets phones reach port ' + esc(r.port) + ' on Private networks only.'
      + (w.from_source && w.blocked_rules.length ? ' The app runs from Python here, so the rules it switches off are Python\u2019s: other Python programs are no longer blocked either.' : '') + '</p>');
    if (ok) out.push('<p class="callout" style="border-color:var(--ok)">Windows Firewall lets phones in. If a phone still can\u2019t open the address, check it\u2019s on the same home network (step 2), and try the other addresses above.</p>');
  }
  box.innerHTML = out.join('');
}
async function quitApp() {
  if (!await confirmBox('Quit the app?', 'The lights stay as they are now, but the schedule stops until you start the app again.', 'Quit', true)) return;
  let r;
  try { r = await api('quit', { body: {} }); } catch (e) { return toast(e.message, true); }
  $('#top').hidden = true;
  $('#main').innerHTML = `<div class="gate"><div class="panel"><h2>The app has stopped</h2><p class="muted">Double-click the launcher to start it again${r && r.starts_at_login ? ', or it starts by itself the next time you log in (Start automatically is on)' : ''}.</p></div></div>`;
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
    else if (t.reason === 'music') { head = 'Music show'; sub = `${st.music.scheduled ? t.source + ': t' : 'T'}he controller\u2019s music mode runs the lights${st.music.until ? ' until ' + st.music.until : ' until the show is stopped'}. Stop it on the Music tab.`; }
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
    const canAdjust = t.on && t.reason !== 'flash' && t.reason !== 'music';
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
            ${st.rotation ? `<p class="note">${st.rotation.nightly ? `A different pattern each night: ${esc(st.rotation.labels.join(', '))}.`
              : st.rotation.each ? `Playing in turn: ${esc(st.rotation.labels.map((l, i) => `${l} ${st.rotation.each[i]} min`).join(', '))}.`
              : `Rotating ${esc(st.rotation.labels.join(', '))} every ${st.rotation.minutes} min.`}</p>` : ''}
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
            <p class="note" style="margin-top:8px">${!t.on ? 'Turn the lights on to adjust them.' : t.reason === 'flash' ? 'Locked during the security flash.' : t.reason === 'music' ? 'Set in the Trimlight app during a music show.' : lv.brightness == null ? 'Levels appear once the controller reports this saved pattern.' : lv.adjusted ? 'Adjusted by hand until the next scheduled change.' : 'Changes last until the next scheduled change.'}</p>
          </div>
        </div>
        <div class="stack">
          <div class="panel"><div class="panel-head"><h2>This week</h2><button class="small ghost" data-tabjump="schedule">Edit schedule</button></div>
            <table class="week"><tbody>${st.days.map((d, i) => {
              const dst = prevAbbr && d.abbr !== prevAbbr ? ` <span class="dst">${esc(d.abbr)} starts</span>` : ''; prevAbbr = d.abbr;
              return `<tr class="${i === 0 ? 'today' : ''}"><td class="d">${i === 0 ? 'Today' : esc(d.dow)}<small>${esc(d.label)}</small></td>
                <td>${(d.windows || []).length ? d.windows.map(w => `<div class="win"><span class="num">${esc(w.on)} – ${esc(w.off)}</span><div class="r">${esc(w.rule)}</div></div>`).join('') : '<span class="r">Off</span>'}${dst}</td>
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
  // exact_colors: these values were tuned on the lights in the Trimlight app; don't gamma-correct them again
  if (e.category === 1 && px.length) return { ...base, colors: px.map(p => p.disable ? 'off' : hex(p.color)), counts: px.map(p => Math.min(90, p.count)), custom_mode: Math.min(16, e.mode || 0), speed: e.speed ?? 100, brightness: e.brightness ?? 200, exact_colors: true };
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
    ${[['mine', 'My patterns'], ['controller', 'In the Trimlight app'], ['builtin', 'Built-in (180)'], ['community', 'Community']].map(([k, l]) => `<button data-ptab="${k}" aria-pressed="${S.ptab === k}">${l}</button>`).join('')}</div>
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
  } else if (S.ptab === 'community') {
    // Reviewed patterns shared by other owners (community.py). Fetched only now.
    let lib;
    try { lib = await api('community' + (S.comRefresh ? '?refresh=1' : '')); }
    catch (e) {
      body.innerHTML = `<div class="panel stack"><p class="callout warn">${esc(e.message)}</p>
        <div class="row"><button class="small" data-comref>Try again</button></div>
        <p class="note">The community library is a list of patterns other EaveLuxOS owners have shared, reviewed before they appear. To share yours, see the Manual, \u201cShare patterns with other owners\u201d.</p></div>`;
      return;
    } finally { S.comRefresh = false; }
    S.community = lib.patterns;
    body.innerHTML = `<div class="panel stack"><div class="row"><input type="search" id="comq" placeholder="Search, e.g. christmas red" class="grow" style="max-width:340px" value="${esc(S.comq || '')}">
        <button class="small ghost" data-comref>Refresh</button></div><div class="cards" id="comlist"></div>
      <p class="note">${lib.patterns.length} patterns shared by other owners and reviewed before they appear. Adding one copies it to your patterns; it changes nothing else. To share yours, see the Manual, \u201cShare patterns with other owners\u201d.</p></div>`;
    const draw = () => {
      const q = ($('#comq').value || '').toLowerCase().split(/\s+/).filter(Boolean);
      const list = S.community.filter(p => q.every(w => `${p.name} ${p.author} ${p.description} ${p.tags.join(' ')}`.toLowerCase().includes(w)));
      $('#comlist').innerHTML = list.length ? list.map(p => `<div class="card">
        <div class="title"><b>${esc(p.name)}</b></div>${p.colors.length ? strand(p.colors) : ''}
        ${p.description ? `<p class="small">${esc(p.description)}</p>` : ''}
        <p class="small muted">${p.author ? `Shared by ${esc(p.author)}` : 'Shared by an EaveLuxOS owner'}${p.tags.length ? ` \u00b7 ${esc(p.tags.join(', '))}` : ''}</p>
        <div class="actions"><button class="small" data-comtry="${esc(p.id)}">Try</button><button class="small ghost" data-comadd="${esc(p.id)}">Add to my patterns</button></div></div>`).join('')
        : `<p class="muted">${S.community.length ? 'No community patterns match.' : 'No patterns have been shared yet.'}</p>`;
    };
    draw();
    $('#comq').oninput = e => { S.comq = e.target.value; draw(); };
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
        <button class="small" data-btry="${b.mode}">Try</button><button class="small ghost" data-badd="${b.mode}">Add</button>
        <button class="small ghost" data-brecreate="${b.mode}" title="Open in Create with these colors and the closest animation, to change the colors">Recreate with my colors</button></div>`).join('')
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
    if (d.comref !== undefined) { S.comRefresh = true; return VIEWS.patterns('community'); }
    if (d.comtry) return busy(b, async () => (await api('community/pattern?id=' + encodeURIComponent(d.comtry))).pattern)
      .then(def => tryDef(def, null)).catch(() => {});
    if (d.comadd) return busy(b, async () => addPattern((await api('community/pattern?id=' + encodeURIComponent(d.comadd))).pattern)).catch(() => {});
    if (d.ctry) return tryDef(fromController(S.ctrlEffects[+d.ctry]), b);
    if (d.cadd) { const def = fromController(S.ctrlEffects[+d.cadd]); return busy(b, () => addPattern(def)).catch(() => {}); }
    if (d.brecreate) return go('create', { recreate: +d.brecreate });
    if (d.btry) { const bi = S.catalog.builtin.find(x => x.mode === +d.btry); return tryDef({ label: bi.name, builtin: bi.mode, speed: 128, brightness: 200, pixel_len: 30 }, b); }
    if (d.badd) { const bi = S.catalog.builtin.find(x => x.mode === +d.badd);
      return builtinDialog({ label: bi.name, builtin: bi.mode, speed: 128, brightness: 200, pixel_len: 30 }, async out => { await addPattern(out); }, 'Add built-in effect'); }
  };
};

/* ---------------------------------------------------------------- CREATE (designer) */
const lum = h => { if (h === 'off') return 0; const n = parseInt(h.slice(1), 16); return (0.299 * (n >> 16) + 0.587 * (n >> 8 & 255) + 0.114 * (n & 255)) / 255; };
VIEWS.create = async (opts = {}) => {
  if (opts.recreate !== undefined) {
    // A built-in's colors are fixed in the controller, so start a custom pattern
    // with the same colors and the closest animation (catalog.recreate).
    const bi = S.catalog.builtin.find(x => x.mode === opts.recreate), r = bi && bi.recreate;
    if (r) S.design = { key: null, label: r.label, segs: r.colors.map((c, i) => ({ c, n: r.counts[i] || 3 })), mode: r.custom_mode,
      speed: r.speed, brightness: r.brightness, sel: 0, from: bi.name };
  } else if (opts.key !== undefined || !S.design || opts.fresh) {
    const def = opts.key ? S.settings.effects[opts.key] : null;
    S.design = def ? { key: opts.key, label: def.label || opts.key, segs: def.colors.map((c, i) => ({ c: c.toUpperCase(), n: (def.counts || [])[i] || 3 })),
      mode: def.custom_mode || 0, speed: def.speed ?? 100, brightness: def.brightness ?? 200, sel: 0, exact: !!def.exact_colors }
      : { key: null, label: '', segs: [{ c: '#FF0000', n: 4 }, { c: '#00FF00', n: 4 }, { c: '#FFFFFF', n: 4 }], mode: 0, speed: 100, brightness: 200, sel: 0 };
  }
  quiet(loadDevices());
  const D = S.design, m = $('#main');
  const def = () => ({ label: D.label.trim() || 'Untitled', colors: D.segs.map(s => s.c), counts: D.segs.map(s => s.n), custom_mode: D.mode, speed: D.speed, brightness: D.brightness,
    ...(D.exact ? { exact_colors: true } : {}) });
  const gOn = () => !!(S.settings.color && S.settings.color.enabled);
  const render = () => {
    const s = D.segs[D.sel];
    m.innerHTML = `<div class="view"><div class="panel-head"><h2>${D.key ? 'Edit pattern' : 'Create a pattern'}</h2>
        ${D.key ? '<button class="ghost" data-newd>Start a new one</button>' : ''}</div>
      ${D.from && !D.key ? `<p class="callout">Started from the built-in effect <b>${esc(D.from)}</b>: same colors, closest animation (${esc(S.catalog.custom_modes[D.mode] || '')}). Built-in effects can't be recolored on the controller, so this is a new pattern that moves a little differently. Change the colors, try it, then save it.</p>` : ''}
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
              ${whitesRow('data-color', 'ckelvin', s.c)}
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
            ${gOn() ? `<label class="check"><input type="checkbox" id="dexact" ${D.exact ? 'checked' : ''}> Exact colors <span class="small muted">(skip color correction for this pattern, for example colors already tuned on the lights)</span></label>` : ''}
          </div>
        </div>
        <div class="stack">
          <div class="panel stack"><h3>Preview</h3><canvas class="preview" id="cv" height="160" aria-label="Animated preview of the pattern"></canvas>
            <p class="note" id="cvnote"></p>
            ${gOn() && !D.exact ? `<p class="note">Color correction is on (gamma ${Number(S.settings.color.gamma || GAMMA.def).toFixed(1)}): the lights get adjusted colors so they look like this preview. Change it under Lights.</p>` : ''}</div>
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
    const dx = $('#dexact'); if (dx) dx.onchange = e => { D.exact = e.target.checked; render(); };
    const cp = $('#cpick'); if (cp) cp.oninput = e => { D.segs[D.sel].c = e.target.value.toUpperCase(); repaintSegs(); };
    const ck = $('#ckelvin'); if (ck) ck.oninput = e => {
      S.kelvin = +e.target.value; D.segs[D.sel].c = Whites.kelvinHex(S.kelvin);
      const v = $('[data-kval]', ck.closest('.whites')); if (v) v.textContent = `${S.kelvin} K`;
      repaintSegs(); };
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
/* Pattern(s) for a rule. Several rotate: every N minutes, a different one
   each night, or a playlist with its own minutes per pattern (each). */
function patternPicker(selected, rotate, nightly = false, allowNightly = true, each = null) {
  const keys = Object.keys(S.settings.effects || {});
  const opts = v => keys.map(k => `<option value="${esc(k)}" ${k === v ? 'selected' : ''}>${esc(effLabel(k))}</option>`).join('');
  const list = (Array.isArray(selected) ? selected : [selected]).filter(Boolean);
  if (!list.length) list.push(keys[0]);
  const useEach = Array.isArray(each) && each.length === list.length && !nightly;
  const mins = list.map((_, i) => (Array.isArray(each) && each[i]) || rotate || 15);
  return `<div class="stack" style="gap:8px" data-picker data-mode="${useEach ? 'each' : nightly && allowNightly ? 'nightly' : 'minutes'}"><span class="small" style="font-weight:650">Pattern${list.length > 1 ? 's (rotate in this order)' : ''}</span>
    ${list.map((v, i) => `<div class="row" data-prow><select name="pattern" class="grow" style="flex:1">${opts(v)}</select>
      ${list.length > 1 ? `<span class="row small each" style="gap:4px"><input type="number" name="each" min="1" max="1440" value="${mins[i]}" style="width:5em" aria-label="Minutes for pattern ${i + 1}"> min</span><button type="button" class="small ghost" data-prm aria-label="Remove">✕</button>` : ''}</div>`).join('')}
    <div class="row"><button type="button" class="small ghost" data-padd>Add a pattern to rotate</button></div>
    <div class="stack" style="gap:6px" ${list.length > 1 ? '' : 'hidden'} data-rot>
      <label class="check"><input type="radio" name="rotmode" value="minutes" ${!useEach && (!nightly || !allowNightly) ? 'checked' : ''}><span class="row small" style="gap:6px">Switch every <input type="number" name="rotate" min="1" max="720" value="${rotate || 15}" style="width:5.5em"> minutes</span></label>
      <label class="check"><input type="radio" name="rotmode" value="each" ${useEach ? 'checked' : ''}><span class="small">Its own time for each pattern (minutes next to each one)</span></label>
      ${allowNightly ? `<label class="check"><input type="radio" name="rotmode" value="nightly" ${nightly && !useEach ? 'checked' : ''}><span class="small">A different one each night, in this order</span></label>` : ''}</div></div>`;
}
function wirePicker(form) {
  form.addEventListener('click', e => {
    const b = e.target.closest('button'); if (!b) return;
    const pk = $('[data-picker]', form);
    const cur = $$('select[name=pattern]', form).map(s => s.value), rot = form.rotate?.value;
    const mode = $('input[name=rotmode]:checked', form)?.value, nightly = mode === 'nightly';
    const allow = !!$('input[name=rotmode][value=nightly]', form) || form.dataset.nightly === '1';
    const each = $$('input[name=each]', form).map(x => +x.value || +rot || 15);
    const keep = () => (mode === 'each' ? each : null);
    if (b.dataset.padd !== undefined) {
      cur.push(cur[cur.length - 1]);
      each.push(each[each.length - 1] || +rot || 15);
      pk.outerHTML = patternPicker(cur, rot, nightly, allow, keep());
    }
    if (b.dataset.prm !== undefined) {
      const i = $$('[data-prow]', form).indexOf(b.closest('[data-prow]'));
      cur.splice(i, 1); each.splice(i, 1);
      pk.outerHTML = patternPicker(cur, rot, nightly, allow, keep());
    }
  });
  form.addEventListener('change', e => {
    if (e.target.name === 'rotmode') { const pk = $('[data-picker]', form); if (pk) pk.dataset.mode = e.target.value; }
    const k = e.target.dataset.tkind;
    if (k) { const clock = e.target.value === 'clock'; $(`[data-tsun="${k}"]`, form).hidden = clock; $(`[data-tclock="${k}"]`, form).hidden = !clock; }
  });
}
function readPicker(form, out) {
  const pats = $$('select[name=pattern]', form).map(s => s.value);
  if (!pats.length || !pats[0]) throw new Error('Create a pattern first (Create tab).');
  delete out.rotate; delete out.rotate_minutes; delete out.rotate_each;
  if (pats.length > 1) {
    out.effect = pats;
    const mode = $('input[name=rotmode]:checked', form)?.value;
    if (mode === 'nightly') out.rotate = 'nightly';
    else if (mode === 'each') {
      out.rotate_each = $$('input[name=each]', form).map(x => Math.round(+x.value));
      if (out.rotate_each.some(m => !(m >= 1 && m <= 1440))) throw new Error('Give each pattern 1 to 1440 minutes.');
    } else out.rotate_minutes = Math.max(1, +form.rotate.value || 15);
  } else out.effect = pats[0];
}
const readT = (f, n) => buildT(f[n + '_kind'].value === 'clock' ? { kind: 'clock', time: f[n + '_time'].value || '23:00' } : { kind: f[n + '_kind'].value, off: +f[n + '_off'].value || 0 });
function mdSelect(name, val) {
  const [mo, d] = (val || '12-01').split('-').map(Number);
  return `<span class="row" style="gap:6px"><select name="${name}_m" style="width:auto">${MONTHS.map((x, i) => `<option value="${i + 1}" ${i + 1 === mo ? 'selected' : ''}>${x}</option>`).join('')}</select>
    <input type="number" name="${name}_d" min="1" max="31" value="${d}" style="width:5em" aria-label="Day"></span>`;
}

function ruleDialog(idx, template) {
  const rules = S.settings.rules || [];
  const r = idx === undefined ? (template || { name: '', on: 'sunset + 15', off: '23:00', effect: Object.keys(S.settings.effects || {})[0] }) : rules[idx];
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
    <p class="hint">If the off time is earlier than the on time, it means the next morning (for example sunset to sunrise). A rule never runs longer than 20 hours, so a 6:00 AM to sunrise rule simply skips days when the sun is already up by 6:00 AM.</p>
    ${patternPicker(r.effect, r.rotate_minutes, r.rotate === 'nightly', true, r.rotate_each)}
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
    ${patternPicker(r.effect, r.rotate_minutes, false, false, r.rotate_each)}
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
        <div class="panel"><h2>Rules</h2><p class="note" style="margin-top:4px">A day can have several rules that don't overlap, for example a morning one (6:00 AM to sunrise) and an evening one (sunset to 11:00 PM); each runs in its own time. Only where rules overlap does the higher priority win (or, with equal priority, the one higher in this list).</p>
          <div class="row" style="margin-top:6px"><button class="small ghost" data-addmorning>Add a morning schedule</button></div>
          <div class="list" style="margin-top:8px">${rules.length ? rules.map(({ r, i }) => { const pats = Array.isArray(r.effect) ? r.effect : [r.effect];
            return `<div class="item"><div class="grow" data-rulename="${esc(r.name)}"><div class="row" style="gap:8px"><span class="name">${esc(r.name)}</span><span class="badge ${prio(r) >= 200 ? 'hi' : ''}">${prioLabel(prio(r))} · ${prio(r)}</span></div>
              <div class="sub">${esc(humanDates(r))} · ${esc(humanDays(r.days))} · ${esc(humanT(r.on))} → ${esc(humanT(r.off))}</div>
              <div class="sub">${swatches(effectSwatches(effs[pats[0]]), 4)} ${pats.length > 1 && Array.isArray(r.rotate_each) ? esc(pats.map((p, i) => `${effLabel(p)} ${r.rotate_each[i]} min`).join(' / ')) + ', in turn'
                : esc(pats.map(effLabel).join(' / ')) + (pats.length > 1 ? (r.rotate === 'nightly' ? ', a different one each night' : `, every ${r.rotate_minutes} min`) : '')}${r.brightness !== undefined ? `, brightness ${Math.round(r.brightness / 2.55)}%` : ''}</div></div>
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
      <div class="grow">${(d.windows || []).length ? d.windows.map(w => `<div class="win"><div class="num">${esc(hm12(w.on_label))} – ${esc(hm12(w.off_label))}</div><div class="sub">${esc(w.rule)}</div></div>`).join('') : '<span class="sub">Off</span>'}
        ${d.dst_change ? `<div class="dst">${esc(d.abbr)} starts today</div>` : ''}</div><div class="sub num">☾ ${esc(hm12(d.sunset))}</div></div>`).join('')
      : '<p class="muted">Finish setup to see upcoming times.</p>';
  }).catch(e => { $('#upc').innerHTML = `<p class="muted">${esc(e.message)}</p>`; });
  m.onclick = async e => {
    const b = e.target.closest('button'); if (!b) return; const d = b.dataset;
    if (d.addrule !== undefined) { if (!Object.keys(effs).length) return toast('Create a pattern first.', true); ruleDialog(); }
    else if (d.addmorning !== undefined) { if (!Object.keys(effs).length) return toast('Create a pattern first.', true);
      ruleDialog(undefined, { name: 'Morning', on: '06:00', off: 'sunrise', effect: (rules.find(x => !x.r.dates) || {}).r?.effect || Object.keys(effs)[0] }); }
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
/* ---------------------------------------------------------------- color correction (3.8)
   Same formula as schedule.py gamma_correct: 255 * (v / 255) ** gamma per
   channel, and a channel that was on stays at least 1. */
const GAMMA = { min: 1.0, max: 3.5, def: 2.2 };
function gammaHex(hex, g) {
  if (!g || g === 1 || hex === 'off') return hex;
  const n = parseInt(hex.slice(1), 16);
  const ch = [16, 8, 0].map(sh => { const v = (n >> sh) & 255; const c = Math.round(255 * Math.pow(v / 255, g)); return v ? Math.max(1, c) : 0; });
  return '#' + ch.map(c => c.toString(16).padStart(2, '0')).join('').toUpperCase();
}
const rgbText = hex => { const n = parseInt(hex.slice(1), 16); return `${n >> 16}, ${n >> 8 & 255}, ${n & 255}`; };
function colorPanel(box) {
  const c = S.settings.color || {}, admin = isAdmin();
  const st = { on: !!c.enabled, g: Number(c.gamma) || GAMMA.def, pick: S.gammaPick || '#FFB46B' };
  const draw = () => {
    const out = gammaHex(st.pick, st.g);
    box.innerHTML = `<h2>Color correction</h2>
      <p class="note">Colors picked on a screen often look pale and washed out on LEDs: screens apply a gamma curve, LEDs don't. Gamma correction adjusts the colors sent to the lights so they look like what you pick. It applies to your own patterns; built-in effects and patterns saved in the Trimlight app aren't changed.</p>
      <label class="check"><input type="checkbox" id="gon" ${st.on ? 'checked' : ''} ${admin ? '' : 'disabled'}> Correct colors for the lights (gamma)</label>
      <label class="field">Gamma <b id="gval">${st.g.toFixed(1)}</b><input type="range" id="gamma" min="${GAMMA.min}" max="${GAMMA.max}" step="0.1" value="${st.g}" ${admin ? '' : 'disabled'}></label>
      <p class="hint">2.2 is a good start. If colors still look pale, try up to 2.8. 1.0 means no change.</p>
      <div class="gconv">
        <label class="field">Try a color<input type="color" id="gpick" value="${st.pick.toLowerCase()}"></label>
        <div class="gsw"><i style="background:${st.pick}"></i><span>As picked<br><code>${st.pick}</code><br><small>${rgbText(st.pick)}</small></span></div>
        <div class="gsw"><i style="background:${out}"></i><span>Sent to the lights<br><code>${out}</code><br><small>${rgbText(out)}</small></span></div>
      </div>
      <div class="row"><button class="small" data-gshow="raw">Show as picked</button><button class="small" data-gshow="fixed">Show corrected</button></div>
      <p class="note">Compare both on the house. The schedule comes back by itself 15 minutes later.</p>
      ${admin ? '<div><button class="primary" data-gsave>Save color correction</button></div>' : '<p class="note">Only an Administrator can change this.</p>'}`;
  };
  draw();
  box.oninput = e => {
    if (e.target.id === 'gamma') { st.g = Number(e.target.value); const v = $('#gval', box); v.textContent = st.g.toFixed(1); }
    if (e.target.id === 'gpick') { st.pick = S.gammaPick = e.target.value.toUpperCase(); }
    if (e.target.id === 'gamma' || e.target.id === 'gpick') {   // update the swatches without re-rendering the control in use
      const out = gammaHex(st.pick, st.g), sw = $$('.gsw', box);
      sw[0].querySelector('i').style.background = st.pick; sw[0].querySelector('span').innerHTML = `As picked<br><code>${st.pick}</code><br><small>${rgbText(st.pick)}</small>`;
      sw[1].querySelector('i').style.background = out; sw[1].querySelector('span').innerHTML = `Sent to the lights<br><code>${out}</code><br><small>${rgbText(out)}</small>`;
    }
  };
  box.onchange = e => { if (e.target.id === 'gon') st.on = e.target.checked; };
  box.onclick = e => {
    const b = e.target.closest('button'); if (!b) return; e.stopPropagation();
    if (b.dataset.gshow) {
      const color = b.dataset.gshow === 'raw' ? st.pick : gammaHex(st.pick, st.g);
      busy(b, () => api('action', { body: { action: 'try', minutes: 15, effect: { label: b.dataset.gshow === 'raw' ? 'Color as picked' : `Gamma ${st.g.toFixed(1)}`,
        colors: [color], counts: [1], custom_mode: 0, brightness: 255, exact_colors: true } } })).then(() => toast(`Showing ${color} on the lights`)).catch(() => {});
    }
    if (b.dataset.gsave !== undefined) {
      const n = clone(S.settings); n.color = { enabled: st.on, gamma: Math.round(st.g * 10) / 10 };
      busy(b, () => saveSettings(n, st.on ? `Color correction on (gamma ${st.g.toFixed(1)})` : 'Color correction off')).catch(() => {});
    }
  };
}

/* ---------------------------------------------------------------- music */
const SHOW_LENGTHS = [[30, '30 minutes'], [60, '1 hour'], [90, '1½ hours'], [120, '2 hours'], [180, '3 hours'], [0, 'Until I stop it']];
const fmtMin = n => n % 60 === 0 ? `${n / 60} hour${n === 60 ? '' : 's'}` : n > 60 ? `${Math.floor(n / 60)} h ${n % 60} min` : `${n} minutes`;
VIEWS.music = async () => {
  const m = $('#main');
  m.innerHTML = `<div class="view"><p class="muted">Loading…</p></div>`;
  const viewer = role() === 'viewer';
  const render = st => {
    if (S.view !== 'music') return;
    const s = S.settings, mc = s.music || {}, shows = mc.shows || [];
    if (st.setup_only) { m.innerHTML = `<div class="view"><div class="panel"><h2>Music</h2><p>Finish setup first (Home).</p></div></div>`; return; }
    const mu = st.music || {}, def = mc.minutes || 60;
    const lens = SHOW_LENGTHS.some(([v]) => v === def) ? SHOW_LENGTHS : [[def, fmtMin(def)], ...SHOW_LENGTHS];
    const state = mu.active
      ? `<div class="callout" style="border-color:var(--lamp)"><b>${mu.scheduled ? `Show night \u201c${esc(mu.source)}\u201d is on` : 'A music show is on'}</b>${mu.until ? ` until ${esc(mu.until)}` : ', until you stop it'}.
         This app isn\u2019t sending anything to the lights, so the controller\u2019s music mode can run them. ${mu.scheduled ? 'Stopping ends it for tonight only.' : ''}</div>`
      : `<p class="note">The lights follow the schedule now${mu.next ? `. Next show night: <b>${esc(mu.next.name)}</b>, ${esc(mu.next.day)} ${esc(mu.next.start)} \u2013 ${esc(mu.next.end)}` : ''}.</p>`;
    m.innerHTML = `<div class="view">
      <div class="panel-head"><h2>Music</h2></div>
      <div class="cols wide-left">
        <div class="stack">
          <div class="panel stack"><h2>Music show</h2>${state}
            ${mu.active
              ? `<div class="row"><button class="primary" data-mstop ${viewer ? 'disabled' : ''}>Stop the show</button></div>`
              : `<div class="row"><label class="field">How long<select id="mlen">${lens.map(([v, l]) => `<option value="${v}" ${v === def ? 'selected' : ''}>${esc(l)}</option>`).join('')}</select></label>
                 <button class="primary" data-mstart ${viewer ? 'disabled' : ''} ${st.flash?.active ? 'disabled title="A security flash is running"' : ''}>Start a music show</button></div>`}
            <p class="note">Starting a show doesn\u2019t make the lights dance by itself: it keeps this app from changing them while the controller\u2019s music mode runs. Choosing a pattern, Return to schedule or a security flash interrupts the show.</p>
          </div>
          <div class="panel stack"><h2>Then, on the controller</h2>
            <ol class="howto">
              <li>On a phone on your <b>home Wi-Fi</b> (music doesn\u2019t work away from home), open the <b>Trimlight Edge</b> app, choose your controller and tap <b>Music</b>.</li>
              <li>Choose <b>Auxiliary IN</b> if a player is plugged into the port on top of the controller (best: no delay, and the phone can be put away). Or choose <b>Microphone</b> and set the phone near the speaker.</li>
              <li>Pick a music pattern and set <b>Music Sensitivity</b>, then start the music.</li>
              <li>When you\u2019re done, press <b>Stop the show</b> here (or let it end on its own). The scheduled pattern comes back.</li>
            </ol>
            <p class="note">The Trimlight app can only switch music mode on over home Wi-Fi, and Trimlight\u2019s cloud (which this app uses) has no music controls. See \u201cMusic shows\u201d in the Manual for wiring a computer or speaker to the Aux port.</p>
          </div>
        </div>
        <div class="stack">
          <div class="panel stack"><div class="panel-head"><h2>Show nights</h2><button class="small" data-maddshow ${viewer ? 'hidden' : ''}>Add a show night</button></div>
            <p class="note">On these nights this app steps aside by itself, so a show started in the Trimlight app isn\u2019t switched back to the schedule.</p>
            <div class="list">${shows.length ? shows.map((r, i) => `<div class="item"><div class="grow"><span class="name">${esc(r.name)}</span>
                <div class="sub">${esc(humanDates(r))} \u00b7 ${esc(humanDays(r.days))} \u00b7 ${esc(humanT(r.on))} \u2192 ${esc(humanT(r.off))}</div></div>
                ${viewer ? '' : `<button class="small ghost" data-meditshow="${i}">Edit</button><button class="small ghost danger" data-mdelshow="${i}" aria-label="Delete ${esc(r.name)}">Delete</button>`}</div>`).join('')
              : '<p class="muted">None yet. Add one for nights you plan a show, like Fridays and Saturdays in December.</p>'}</div>
          </div>
          <div class="panel stack"><h2>Show length</h2>
            <div class="row"><label class="field">Usual length (minutes)<input type="number" id="mdef" min="5" max="360" value="${def}" ${viewer ? 'disabled' : ''}></label>
              <button class="small" data-msavedef ${viewer ? 'hidden' : ''}>Save</button></div>
            <p class="note">The length chosen first above, and for a show started from a webhook or Home Assistant.</p>
          </div>
        </div>
      </div></div>`;
  };
  try { render(await refreshStatus()); } catch (e) { m.innerHTML = `<div class="view"><p class="callout warn">${esc(e.message)}</p></div>`; return; }
  S.timers.push(setInterval(async () => { if (!document.hidden && !$('#dlg').open) render(await refreshStatus()); }, 15000));
  const act = (body, btn) => busy(btn, async () => { S.status = await api('action', { body }); statusPill(S.status); render(S.status); }).catch(() => {});
  m.onclick = async e => {
    const b = e.target.closest('button'); if (!b) return; const d = b.dataset;
    if (d.mstart !== undefined) act({ action: 'music', minutes: +$('#mlen').value }, b);
    else if (d.mstop !== undefined) act({ action: 'stop_music' }, b);
    else if (d.maddshow !== undefined) showDialog();
    else if (d.meditshow) showDialog(+d.meditshow);
    else if (d.mdelshow) {
      const shows = S.settings.music?.shows || [];
      if (await confirmBox('Delete show night?', `\u201c${esc(shows[+d.mdelshow].name)}\u201d will be removed.`, 'Delete', true)) {
        const n = clone(S.settings); n.music = { ...(n.music || {}), shows: [...shows] }; n.music.shows.splice(+d.mdelshow, 1);
        await busy(null, () => saveSettings(n, 'Deleted')).catch(() => {}); VIEWS.music();
      }
    } else if (d.msavedef !== undefined) {
      const v = Math.round(+$('#mdef').value);
      if (!(v >= 5 && v <= 360)) return toast('Use 5 to 360 minutes.', true);
      const n = clone(S.settings); n.music = { ...(n.music || {}), minutes: v };
      busy(b, () => saveSettings(n)).then(() => VIEWS.music()).catch(() => {});
    }
  };
};
function showDialog(idx) {
  const shows = S.settings.music?.shows || [];
  const r = idx === undefined ? { name: '', on: 'sunset + 30', off: '21:00', days: ['fri', 'sat'], dates: '12-01..12-31' } : shows[idx];
  const [ds, de] = r.dates ? String(r.dates).split('..') : ['12-01', '12-31'];
  const days = !r.days || r.days === 'all' ? DAYS : r.days === 'weekdays' ? DAYS.slice(0, 5) : r.days === 'weekends' ? DAYS.slice(5) : r.days.map(x => x.slice(0, 3).toLowerCase());
  return dialog(`<h2>${idx === undefined ? 'New show night' : 'Edit show night'}</h2>
    <label class="field">Name<input type="text" name="name" maxlength="50" required value="${esc(r.name)}" placeholder="e.g. Christmas shows"></label>
    <div class="stack" style="gap:8px"><span class="small" style="font-weight:650">When in the year</span>
      <label class="check"><input type="radio" name="season" value="all" ${!r.dates ? 'checked' : ''}> All year</label>
      <label class="check"><input type="radio" name="season" value="range" ${r.dates ? 'checked' : ''}> Only between</label>
      <div class="row" data-range ${r.dates ? '' : 'hidden'}>${mdSelect('ds', ds)}<span class="muted">and</span>${mdSelect('de', de || ds)}</div></div>
    <div class="stack" style="gap:8px"><span class="small" style="font-weight:650">Days of the week</span>
      <div class="chips">${DAYS.map(d => `<label class="check" style="gap:6px"><input type="checkbox" name="day" value="${d}" ${days.includes(d) ? 'checked' : ''}>${DAYNAMES[d]}</label>`).join('')}</div></div>
    <div class="cols" style="gap:10px">${timeField('on', 'Show starts', r.on)}${timeField('off', 'Show ends', r.off)}</div>
    <p class="hint">Between these times this app leaves the lights alone. After the end time the schedule takes over again.</p>`,
  async f => {
    const out = { name: f.name.value.trim() };
    if (!out.name) throw new Error('Give the show night a name.');
    if (shows.some((x, i) => i !== idx && x.name === out.name)) throw new Error('Another show night already has that name.');
    if (f.season.value === 'range') {
      const md = n => `${String(f[n + '_m'].value).padStart(2, '0')}-${String(Math.max(1, Math.min(31, +f[n + '_d'].value || 1))).padStart(2, '0')}`;
      out.dates = `${md('ds')}..${md('de')}`;
    }
    const dsel = $$('input[name=day]:checked', f).map(x => x.value);
    if (!dsel.length) throw new Error('Pick at least one day.');
    if (dsel.length < 7) out.days = dsel;
    out.on = readT(f, 'on'); out.off = readT(f, 'off');
    const n = clone(S.settings); n.music = { minutes: 60, ...(n.music || {}) }; n.music.shows = [...(n.music.shows || [])];
    if (idx === undefined) n.music.shows.push(out); else n.music.shows[idx] = out;
    await saveSettings(n, 'Show night saved'); VIEWS.music();
  }, { onOpen: f => {
    f.addEventListener('change', e => {
      if (e.target.name === 'season') $$('[data-range]', f).forEach(x => x.hidden = e.target.value !== 'range');
      const k = e.target.dataset.tkind;
      if (k) { const clock = e.target.value === 'clock'; $(`[data-tsun="${k}"]`, f).hidden = clock; $(`[data-tclock="${k}"]`, f).hidden = !clock; }
    });
  } });
}

/* Controller picker for accounts with several controllers (like the Trimlight
   app's Devices list). The cloud doesn't report IP addresses, so the cards
   show what it does report: online, what the lights are doing, bulbs. */
function devCards(devs, cur, chosen) {
  const bulbs = x => Math.max(0, ...(x.ports || []).filter(p => p.start > 0 && p.end > 0).map(p => p.end));
  const doing = x => x.error ? 'Couldn\u2019t read it' : x.switch === 0 ? 'Off' : x.switch === 2 ? 'On its own timer' : x.switch === 1 ? 'On' : '';
  return `<div class="devcards" role="tablist" aria-label="Controllers">${devs.map(x => {
    const run = !chosen.length || chosen.includes(x.id), n = bulbs(x), what = doing(x);
    return `<button type="button" class="devcard" role="tab" aria-selected="${x.id === cur}" data-dev="${esc(x.id)}">
      <span class="dc-top"><b>${esc(x.name || 'Controller')}</b><span class="dot ${x.online ? 'on' : ''}">${x.online ? 'Online' : 'Offline'}</span></span>
      <span class="dc-sub">${[what, n ? `${n} bulbs` : ''].filter(Boolean).map(esc).join(' \u00b7 ')}</span>
      ${run ? '' : '<span class="dc-tag">Not run by this app</span>'}</button>`;
  }).join('')}</div>`;
}
VIEWS.lights = async (opts = {}) => {
  const m = $('#main');
  if (!opts.keep) { S.portDraft = null; m.innerHTML = '<div class="view"><h2>Lights</h2><p class="muted">Asking the controller…</p></div>'; }
  let devs;
  const alone = msg => { m.innerHTML = `<div class="view"><h2>Lights</h2>${msg}<div class="panel stack" id="gbox" style="margin-top:16px;max-width:640px"></div></div>`; colorPanel($('#gbox')); };
  try { devs = await loadDevices(!opts.keep); } catch (e) { return alone(`<p class="callout warn">${esc(e.message)}</p>`); }
  if (!devs.length) return alone('<p class="callout">No controllers on this account.</p>');
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
  m.innerHTML = `<div class="view"><div class="panel-head"><h2>${devs.length > 1 ? `Lights: ${esc(d.name || 'Controller')}` : 'Lights'}</h2>
      <span class="badge ${d.online ? 'hi' : ''}">${d.online ? 'Online' : 'Offline'}</span><span class="small muted">Firmware ${esc(d.firmware || '?')}</span></div>
    ${devs.length > 1 ? devCards(devs, d.id, chosen) : ''}
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
        <div class="panel stack" id="gbox"></div>
        ${devs.length > 1 ? `<div class="panel stack"><h2>Controlled by this app</h2>${devs.map(x => `<label class="check"><input type="checkbox" data-ctl="${esc(x.id)}" ${!chosen.length || chosen.includes(x.id) ? 'checked' : ''}>${esc(x.name)}</label>`).join('')}
          <div><button class="small" data-savectl>Save</button></div></div>` : ''}
      </div>
    </div></div>`;
  draw();
  colorPanel($('#gbox'));
  m.oninput = e => {
    const t = e.target, ds = t.dataset;
    if (ds.pc !== undefined) P[+ds.pc].count = Math.max(0, Math.min(2048, +t.value || 0));
    if (ds.ps !== undefined) P[+ds.ps].start = +t.value || 1;
    if (ds.pe !== undefined) P[+ds.pe].end = +t.value || 1;
    if (ds.poff !== undefined) { const p = P[+ds.poff]; p.off = t.checked; if (!p.off && !p.start) { p.start = 1; p.end = 50; } return VIEWS.lightsRedraw(); }
    if (ds.pc !== undefined || ds.ps !== undefined || ds.pe !== undefined) draw();
  };
  VIEWS.lightsRedraw = () => { m.querySelectorAll('[data-ps],[data-pe]').forEach(i => { const p = P[+(i.dataset.ps ?? i.dataset.pe)]; i.disabled = p.off; if (!p.off) i.value = i.dataset.ps !== undefined ? p.start : p.end; }); draw(); };
  // Unsaved edits on this controller: ports, or the name / chip / color order fields.
  const dirty = () => P.some(p => { const o = ports[p.id]; return p.off !== o.off || (!p.off && (p.start !== o.start || p.end !== o.end)); })
    || ($('#lname') && $('#lname').value !== (d.name || '')) || ($('#lic') && +$('#lic').value !== d.ic)
    || ($('#lco') && +$('#lco').value !== d.colorOrder);
  m.onclick = async e => {
    const b = e.target.closest('button'); if (!b) return; const ds = b.dataset;
    if (ds.dev !== undefined) {
      if (ds.dev === d.id) return;
      if (dirty() && !await confirmBox(`Leave ${d.name || 'this controller'}?`, 'Your changes to it haven\u2019t been saved to the controller yet.', 'Discard changes', true)) return;
      S.lightDev = ds.dev; S.portMode = null; S.portDraft = null;
      return VIEWS.lights({ keep: true });
    }
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
          ${urls.length ? `<p>Open <code>${esc(urls[0])}</code> in the web browser on any phone or computer on your home Wi-Fi. It shows a sign-in page. In Safari, Share › Add to Home Screen makes it an app.</p>
            ${urls.length > 1 ? `<p class="note">If that address doesn't open, this computer has others: ${urls.slice(1).map(u => `<code>${esc(u)}</code>`).join(', ')}.</p>` : ''}` : ''}
          <p class="note">${a.password_set ? 'Each person signs in with their own account.' : 'Create an account (Settings › Accounts) so other devices can sign in.'}</p>
          <details class="lanhelp"><summary>A phone can\u2019t open it?</summary>
            <ol class="howto">
              <li>Type the address exactly, starting with <b>${esc(a.scheme || 'http')}://</b> and ending with <b>:${esc(a.port)}/</b>, in the phone\u2019s web browser.</li>
              <li>Use your <b>home Wi-Fi</b>, not mobile data, on the same network as this computer: not a guest or separate network on your router.</li>
              <li>This computer\u2019s firewall has to let phones in.${local ? ' Check it below.' : ' Open Settings on the computer running the app and use <b>Check this computer</b> there.'}</li>
            </ol>
            ${local ? '<div class="row"><button class="small" data-lancheck>Check this computer</button></div><div id="lanresult" class="stack" aria-live="polite"></div>' : ''}
          </details></div>
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
        if (!await confirmBox(`Delete ${u.username}?`, 'The account is removed and signed out everywhere. To pause access instead, edit it and tick Disabled.', 'Delete', true)) return;
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
    if (d.copy) { const el = $('#' + d.copy); el.select(); const manual = () => toast(/Mac|iPhone|iPad|iOS/i.test(navigator.userAgentData?.platform || navigator.userAgent) ? 'Selected. Press \u2318C to copy.' : 'Selected. Press Ctrl+C to copy.');
      if (navigator.clipboard?.writeText) navigator.clipboard.writeText(el.value).then(() => toast('Copied'), manual); else manual(); }
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
    if (d.quit !== undefined) quitApp();
    if (d.lancheck !== undefined) busy(b, async () => lanShow(await api('lan_check'))).catch(() => {});
    if (d.lanallow !== undefined) busy(b, async () => { const r = await api('lan_allow', { body: {} }); toast('Windows Firewall now lets phones in'); lanShow({ ...(await api('lan_check')) }); return r; }).catch(() => {});
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
/* Whites by color temperature (whites.js): preset buttons that set the color
   like any palette button (attr: data-color or data-pcolor), and a slider for
   anything in between. */
function whitesRow(attr, sliderId, current) {
  const k = S.kelvin || 2700;
  return `<div class="whites"><span class="small" style="font-weight:650">Whites</span>
    <div class="palette">${Whites.PRESETS.map(p => { const hex = Whites.kelvinHex(p.k);
      return `<button ${attr}="${hex}" title="${esc(p.name)} \u00b7 ${p.k} K" aria-label="${esc(p.name)}, ${p.k} K" aria-pressed="${current === hex}" style="background:${hex}"></button>`; }).join('')}</div>
    <label class="row small kelvin">Warm<input type="range" id="${sliderId}" min="${Whites.MIN}" max="${Whites.MAX}" step="100" value="${k}" aria-label="Color temperature">Cool
      <span class="muted" data-kval>${k} K</span></label></div>`;
}
/* Save a house photo. The original file goes to the app computer, which
   turns it upright, shrinks it and saves it, on its processor: the browser's
   own image handling can't be trusted on every computer (some graphics drivers
   turn photos solid green or striped). Only if the app computer can't read the
   file (an iPhone HEIC, or no image library when run from source) does this
   browser shrink it instead. */
async function uploadPhoto(side, file) {
  if (file.size <= 30_000_000) {
    const r = await fetch('api/photo/upload?side=' + encodeURIComponent(side), { method: 'POST', cache: 'no-store', body: file,
      headers: { 'X-Requested-With': 'eaveluxos', 'Content-Type': file.type || 'application/octet-stream', ...authHeaders() } });
    if (r.ok) return;
    const e = await r.json().catch(() => ({}));
    if (r.status === 401) throw new Error('Sign in again, then upload the photo.');
    if (r.status !== 415 && r.status !== 501) throw new Error(e.error || `Upload failed (${r.status}).`);
  }
  await api('photo', { body: { side, data: await shrinkPhoto(file) } });
}
/* Shrink a photo to at most 1600 px and encode it as JPEG, in this browser.
   Some graphics drivers return an all-green (or blank) image when the browser
   decodes or draws a photo on the graphics card. So: draw on a canvas kept in
   regular memory (willReadFrequently), check the result isn't one flat color,
   and if it is, try the browser's other image decoder before giving up. */
async function shrinkPhoto(file, max = 1600) {
  const decoders = [
    async () => { const bmp = await createImageBitmap(file, { imageOrientation: 'from-image' }); return { src: bmp, w: bmp.width, h: bmp.height, done: () => bmp.close() }; },
    async () => {
      const url = URL.createObjectURL(file), img = new Image(); img.src = url;
      try { await img.decode(); } catch (e) { URL.revokeObjectURL(url); throw e; }
      return { src: img, w: img.naturalWidth, h: img.naturalHeight, done: () => URL.revokeObjectURL(url) };
    }];
  let opened = false;
  for (const decode of decoders) {
    let d;
    try { d = await decode(); } catch { continue; }
    opened = true;
    try {
      if (!d.w || !d.h) continue;
      const k = Math.min(1, max / Math.max(d.w, d.h)), cv = document.createElement('canvas');
      cv.width = Math.max(1, Math.round(d.w * k)); cv.height = Math.max(1, Math.round(d.h * k));
      const ctx = cv.getContext('2d', { willReadFrequently: true });
      ctx.imageSmoothingQuality = 'high';
      ctx.drawImage(d.src, 0, 0, cv.width, cv.height);
      if (flatImage(ctx, cv.width, cv.height)) continue;
      let data = cv.toDataURL('image/jpeg', 0.82);
      if (data.length > 1_900_000) data = cv.toDataURL('image/jpeg', 0.6);
      return data;
    } finally { d.done(); }
  }
  throw new Error(opened
    ? 'This browser couldn\u2019t read that photo correctly (it came out as one flat color). Try another browser, or turn off "Use graphics acceleration" in the browser\u2019s settings.'
    : 'That image couldn\u2019t be opened. Try a JPEG or PNG.');
}
/* One flat color everywhere: a failed decode, not a photo. Samples a 24 x 24 grid. */
function flatImage(ctx, w, h) {
  const px = ctx.getImageData(0, 0, w, h).data, lo = [255, 255, 255], hi = [0, 0, 0];
  for (let gy = 0; gy < 24; gy++) for (let gx = 0; gx < 24; gx++) {
    const i = ((Math.floor((gy + 0.5) * h / 24) * w) + Math.floor((gx + 0.5) * w / 24)) * 4;
    for (let c = 0; c < 3; c++) { lo[c] = Math.min(lo[c], px[i + c]); hi[c] = Math.max(hi[c], px[i + c]); }
  }
  return hi.every((v, c) => v - lo[c] <= 4);
}
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
                <button class="small" data-gozone="${i}">Show</button><button class="small ghost" data-editzone="${i}" aria-label="Edit ${esc(z.name)}">Edit</button><button class="small ghost danger" data-delzone="${i}" aria-label="Delete ${esc(z.name)}">✕</button></div>`).join('')
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
    if (d.editzone) return zoneDialog(+d.editzone, F, render);
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
      const file = t.files[0]; t.value = '';
      try {
        await busy(null, () => uploadPhoto(F.side, file));
        // Only now, with the new photo saved, drop rooflines traced on the old one.
        if (traced) await saveMap(mp => { delete mp.rooflines[F.side]; }, 'Old rooflines removed');
        roofReset();
        S.photoV = Date.now(); S.photos.add(F.side); toast('Photo saved'); render();
      } catch { /* busy() has shown the error */ }
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
        <span class="chip-now"><i ${sw(P.color)}></i>${P.color === 'off' ? 'Zone off' : esc(P.color)}</span></div>
      ${whitesRow('data-pcolor', 'pkelvin', P.color)}</div>
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
  if (t.id === 'pkelvin') {
    // Update in place: re-rendering mid-drag would drop the slider.
    S.kelvin = +t.value; P.color = Whites.kelvinHex(S.kelvin);
    const chip = $('.painter .chip-now'); if (chip) chip.innerHTML = `<i style="background:${esc(P.color)}"></i>${esc(P.color)}`;
    const v = $('[data-kval]', t.closest('.whites')); if (v) v.textContent = `${S.kelvin} K`;
    return true;
  }
  if (t.id === 'pzone' && t.value !== '') { const z = mapData().zones[+t.value]; P.from = Math.min(z.start, N); P.to = Math.min(z.end, N); VIEWS.createRender(); return true; }
  return false;
}

/* Edit a zone: fix its name or bulb numbers (for example after a counting
   mistake), check it by lighting it, then save. */
function zoneDialog(i, F, rerender) {
  const md = mapData(), z = md.zones[i], T = addressSpace();
  if (!z) return;
  const read = f => {
    const name = f.zn.value.trim(), start = Number(f.zs.value), end = Number(f.ze.value);
    if (!name) throw new Error('Give the zone a name.');
    if (md.zones.some((o, j) => j !== i && o.name.trim().toLowerCase() === name.toLowerCase())) throw new Error(`There's already a zone named \u201c${name}\u201d.`);
    if (!Number.isInteger(start) || !Number.isInteger(end)) throw new Error('Bulb numbers must be whole numbers.');
    if (start < 1 || end > T) throw new Error(`Bulbs go from 1 to ${T}.`);
    if (end < start) throw new Error('The last bulb can\u2019t be before the first.');
    return { name, start, end };
  };
  dialog(`<h2>Edit zone</h2>
    <label class="field">Name<input type="text" name="zn" maxlength="60" required value="${esc(z.name)}"></label>
    <div class="row"><label class="field">First bulb<input type="number" name="zs" min="1" max="${T}" value="${z.start}"></label>
      <label class="field">Last bulb<input type="number" name="ze" min="1" max="${T}" value="${z.end}"></label></div>
    <p class="note" data-zcount>${z.end - z.start + 1} bulbs, out of ${T}.</p>
    <div class="row"><button type="button" class="small" data-zlight>Light these bulbs</button>
      ${F.range ? `<button type="button" class="small ghost" data-zfinder>Use the finder's range (${F.bulb}\u2013${F.end})</button>` : ''}</div>
    <p class="note">Light the zone to check it on the house before saving. The schedule comes back by itself 10 minutes after the last change.</p>`,
    async f => {
      const v = read(f);
      await saveMap(mp => { mp.zones[i] = { ...mp.zones[i], ...v }; }, `Zone \u201c${v.name}\u201d saved`);
      rerender();
    }, { ok: 'Save zone', onOpen: f => {
      const count = () => { const a = Number(f.zs.value), b = Number(f.ze.value); $('[data-zcount]', f).textContent = Number.isInteger(a) && Number.isInteger(b) && b >= a ? `${b - a + 1} bulbs, out of ${T}.` : 'Check the bulb numbers.'; };
      f.zs.oninput = f.ze.oninput = count;
      f.addEventListener('click', e => {
        const b = e.target.closest('button'); if (!b) return;
        if (b.dataset.zfinder !== undefined) { f.zs.value = F.bulb; f.ze.value = F.end; count(); }
        if (b.dataset.zlight !== undefined) {
          let v; try { v = read(f); } catch (err) { return toast(err.message, true); }
          busy(b, () => api('action', { body: { action: 'try', effect: highlightDef(v.start, v.end, T, F.color), minutes: 10 } }))
            .then(() => toast(`Showing bulbs ${v.start}\u2013${v.end}`)).catch(() => {});
        }
      });
    } });
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
      ${conflicts.includes('daily') ? `<p class="callout warn small">The Trimlight app's daily timers are on. They would run too whenever the controller is left in Timer mode, so the safety net waits until they're off. <button class="small" data-dailyoff>Turn them off</button></p>` : ''}
      ${conflicts.some(c => c.startsWith('calendar:')) ? '<p class="callout warn small">The controller has calendar events made in the Trimlight app on the coming nights. They would run too whenever the controller is left in Timer mode, so the safety net waits until they\u2019re removed in the Trimlight app (then choose Update now). Events on other dates are fine.</p>' : ''}
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
