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
  const init = { method: opts.method || (opts.body !== undefined ? 'POST' : 'GET'), headers: { 'X-Requested-With': 'eaveluxos', ...authHeaders() }, cache: 'no-store', keepalive: !!opts.keepalive };
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

/* ---------------------------------------------------------------- folding panels (4.0)
   A panel that folds to one line with a summary ("Holidays · 3 on"), so a
   long tab fits a screen. Open or closed is remembered in this browser. */
function foldOpen(key, def) {
  try { const v = localStorage.getItem('fold:' + key); return v === null ? def : v === '1'; } catch { return def; }
}
const wide = () => window.innerWidth > 760;
function fold(key, title, inner, def = false) {
  const open = foldOpen(key, def);
  // Screen readers hear "Holidays, collapsed" and which region it opens (4.0.1).
  return `<section class="fold${open ? '' : ' closed'}" data-fold="${key}"><button type="button" class="foldbar" aria-expanded="${open}" aria-controls="fold-${key}">
    <span class="ft">${title}</span><span class="fs" data-sum="${key}"></span><span class="chev" aria-hidden="true"></span></button>
    <div class="foldbody" id="fold-${key}" role="region" aria-label="${esc(title)}">${inner}</div></section>`;
}
// A folded panel's contents load the first time it's opened (4.0.1).
const FOLD_LOAD = {};
function whenOpen(key, load) {
  const f = $(`[data-fold="${key}"]`);
  if (f && f.classList.contains('closed')) FOLD_LOAD[key] = load;
  else { delete FOLD_LOAD[key]; load(); }
}
document.addEventListener('click', e => {
  const b = e.target.closest('.foldbar'); if (!b) return;
  const f = b.closest('.fold'), open = f.classList.toggle('closed') === false;
  b.setAttribute('aria-expanded', open);
  try { localStorage.setItem('fold:' + f.dataset.fold, open ? '1' : '0'); } catch { /* private mode */ }
  const load = open && FOLD_LOAD[f.dataset.fold];
  if (load) { delete FOLD_LOAD[f.dataset.fold]; load(); }
});
// While typing in a field on a phone, the bottom tab bar steps aside, so it
// doesn't ride up above the on-screen keyboard over the field (4.0.1).
const TYPES_TEXT = /^(text|search|email|password|number|url|tel|date|time)$/;
const typing = el => el && (el.tagName === 'TEXTAREA' || (el.tagName === 'INPUT' && TYPES_TEXT.test(el.type)));
document.addEventListener('focusin', e => { if (typing(e.target)) document.body.classList.add('typing'); });
document.addEventListener('focusout', () => setTimeout(() => { if (!typing(document.activeElement)) document.body.classList.remove('typing'); }, 0));
const onOff = (on, text) => on ? text : 'Off';
const shortDay = d => new Date(d + 'T12:00').toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' });
const plural = (n, w) => `${n} ${w}${n === 1 ? '' : 's'}`;
const SUMS = {
  upcoming: () => {                    // 4.0.1: once tonight's lights are off, the next night
    const st = S.status; if (!st?.days) return '';
    if (st.window) return `On now: ${st.window.rule} until ${st.window.end}`;
    const today = st.days[0];
    if (today?.on && st.next_change && !st.next_change_day) return `Tonight ${today.on} – ${today.off}: ${today.effect || ''}`;
    const i = st.days.findIndex((d, k) => k > 0 && d.on);
    return i < 0 ? 'Nothing in the coming week' : `${i === 1 ? 'Tomorrow' : st.days[i].dow + ' ' + st.days[i].label} ${st.days[i].on} – ${st.days[i].off}: ${st.days[i].effect || ''}`;
  },
  holidays: () => { const h = S.settings.holidays || {}; const n = (h.list || []).length, nx = S.status?.coming?.holiday;
    return onOff(h.enabled && (n || h.country), [S.status?.holiday ? `today: ${S.status.holiday.name}` : nx ? `next: ${nx.name}, ${shortDay(nx.date)}` : '',
      n ? plural(n, 'holiday') : '', h.country ? `public holidays (${h.country.code})` : ''].filter(Boolean).join(' · ')); },
  game: () => { const g = S.settings.gameday || {}, nx = S.status?.coming?.game;
    const party = (g.celebrate_enabled ?? !!g.enabled) && (g.teams || []).some(t => t.celebrate);
    const what = [g.enabled ? 'lights' : '', party ? 'celebrations' : ''].filter(Boolean).join(' + ');
    return onOff((g.enabled || party) && (g.teams || []).length, `${what}${nx ? ` · next: ${nx.name}, ${shortDay(nx.date)}` : ''}`); },
  away: () => { const a = S.settings.away || {}; return a.enabled ? `On until ${a.until || '…'}` : 'Off'; },
  weather: () => { const w = S.settings.weather || {}, n = (S.settings.weather_rules || []).length; return onOff(w.enabled && n, plural(n, 'rule')); },
  wxalerts: () => { const w = S.settings.weather_alerts || {}; return onOff(w.enabled, plural((w.groups || []).length, 'kind') + ' of warning'); },
  security: () => { const c = S.settings.security || {}; return onOff(c.effect, `${effLabel(c.effect)} for ${c.minutes || 5} min`); },
  webhooks: () => S.account ? onOff(S.account.webhook_token, 'On') : '',
  safety: () => { const c = S.settings.safety || {}; return onOff(c.enabled, `On · ${c.days || 7} nights copied to the controller`); },
  ai: () => S.aiOn === undefined ? '' : S.aiOn ? 'A key is saved' : 'No key: Describe it uses the built-in generator',
  history: () => 'Every save is kept (the last 100)',
  usage: () => 'Hours on and estimated cost',
  color: () => { const c = S.settings.color || {}; return onOff(c.enabled, `On · gamma ${Number(c.gamma || 2.2).toFixed(1)}`); },
  landmarks: () => plural(((S.settings.map || {}).landmarks || []).length, 'landmark'),
  zones: () => plural(((S.settings.map || {}).zones || []).length, 'zone'),
  numbering: () => { const t = (S.settings.map || {}).total_bulbs; return t ? `${t} bulbs (set by hand)` : `${typeof totalBulbs === 'function' ? totalBulbs() : ''} bulbs, from the controller`; },
  mood: () => { const m = S.settings.mood || {}; return ['calm', 'lively', 'party'].every(k => m[k]) ? 'Ready: ' + ['calm', 'lively', 'party'].map(k => effLabel(m[k])).join(' / ') : 'Choose three patterns'; },
  shownights: () => { const r = (S.settings.music || {}).shows || []; return r.length ? r.map(x => x.name).join(', ') : 'None'; },
  showlen: () => fmtMin((S.settings.music || {}).minutes || 60),
  howto: () => 'Steps for the Trimlight app',
};
function foldSums() {
  for (const el of $$('[data-sum]')) {
    let t = '';
    try { t = SUMS[el.dataset.sum] ? SUMS[el.dataset.sum]() : ''; } catch { t = ''; }
    el.textContent = t || '';
  }
}

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
/* A color's name for people (3.20): "Crimson", or "#E0A060 · near Sandy Brown". */
function colorName(c) {
  if (c === 'off') return 'Zoned off';
  const n = S.catalog && window.Colors ? Colors.nearest(c, S.catalog.names) : null;
  return !n ? String(c).toUpperCase() : n.exact ? n.name : `${String(c).toUpperCase()} · near ${n.name}`;
}
function strand(colors, counts) {
  if (!colors || !colors.length) return '';
  return `<div class="strand" aria-hidden="true">${colors.map((c, i) => `<i title="${esc(colorName(c))}" ${c === 'off' ? 'class="off" ' : ''}style="${c === 'off' ? '' : `background:${esc(c)};`}flex-grow:${counts ? (counts[i] || 1) : 1}"></i>`).join('')}</div>`;
}
function effectSwatches(def) {
  if (!def) return [];
  if (def.split) {     // a different pattern on each controller (3.17)
    const out = [];
    [...Object.values(def.split), def.rest].forEach(k => effectSwatches((S.settings.effects || {})[k]).forEach(c => { if (!out.includes(c)) out.push(c); }));
    return out.slice(0, 30);
  }
  if (def.colors) return def.colors;
  if (def.builtin !== undefined && S.catalog) return S.catalog.builtin[def.builtin]?.swatches || [];
  return [];
}
function effectKind(def) {
  if (!def) return '';
  if (def.split) return `Split by controller · ${Object.keys(def.split).length + (def.rest && def.rest !== 'off' ? 1 : 0)} parts`;
  if (def.scene) return 'Scene (House tab)';
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
    try { if (await busy(btn, () => onSubmit(form)) !== false) d.close(); } catch { /* toast shown */ }   // false: keep it open (3.19)
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
  bolt: '<path d="M13.5 2.5 5 13.5h6l-1 8 8.5-11h-6z"/>',
  power: '<path d="M12 3.5v8"/><path d="M7.2 6.6a7.5 7.5 0 1 0 9.6 0"/>',
  bulbon: '<path d="M9 17.5h6M10 21h4"/><path d="M8.2 14.2A6 6 0 1 1 15.8 14.2c-.8.8-1.3 1.8-1.3 2.9v.4h-5v-.4c0-1.1-.5-2.1-1.3-2.9z"/><path d="M12 2.2v-0M4 9.5H3M21 9.5h-1"/>',
  star: '<path d="M12 3.5l2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 16.9l-5.2 2.7 1-5.8-4.3-4.1 5.9-.9z"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2.5v2M12 19.5v2M4.6 4.6l1.4 1.4M18 18l1.4 1.4M2.5 12h2M19.5 12h2M4.6 19.4L6 18M18 6l1.4-1.4"/>',
  moon: '<path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"/>',
  themeauto: '<circle cx="12" cy="12" r="8.5"/><path d="M12 3.5v17a8.5 8.5 0 0 0 0-17z" fill="currentColor"/>',
  exit: '<path d="M14 4.5h4.5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1H14"/><path d="M10 8l-4 4 4 4M6 12h9.5"/>',
  music: '<path d="M9 17.5V6.5l10-2.2v11"/><circle cx="6.6" cy="17.6" r="2.4"/><circle cx="16.6" cy="15.4" r="2.4"/><path d="M9 9.6l10-2.2"/>',
  alerts: '<path d="M6 16V11a6 6 0 0 1 12 0v5l1.5 2h-15z"/><path d="M10 20.5a2 2 0 0 0 4 0"/>',
  help: '<circle cx="12" cy="12" r="9"/><path d="M9.6 9.3a2.5 2.5 0 0 1 4.8.9c0 1.7-2.4 2.1-2.4 3.6"/><path d="M12 17h.01"/>',
  settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
};
/* 4.0: seven tabs. Create opens from Patterns; Lights, Date & Time and
   Settings are sections of Setup; the Manual is the ? button in the header.
   Old addresses (#create, #lights, #time, #settings) still work. */
const { TABS, TAB_OF, SETUP_SECS, VIEW_ALIAS } = Nav;          // nav.js (4.0.1)
const icon = n => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[n]}</svg>`;
function buildRibbon() {
  $('#ribbon').innerHTML = TABS.map(([k, l]) => `<button data-tab="${k}">${icon(k === 'setup' ? 'settings' : k)}<span>${l}</span></button>`).join('');
  $('#ribbon').addEventListener('click', e => { const b = e.target.closest('[data-tab]'); if (b) go(b.dataset.tab); });
}
// replace: true for the browser's own Back/Forward and for old addresses
// being corrected; otherwise each tab change is a step Back can undo (4.0.1).
function go(asked, extra, replace = false) {
  const r = Nav.resolve(asked, v => !!VIEWS[v], S.setupSec), view = r.view;
  replace = replace || r.replace;
  if (r.setup) S.setupSec = view;
  S.view = view; S.timers.forEach(clearInterval); S.timers = [];
  if (location.hash !== '#' + view) history[replace || !location.hash ? 'replaceState' : 'pushState'](null, '', '#' + view);
  const tab = r.tab;
  $$('#ribbon button').forEach(b => b.setAttribute('aria-current', b.dataset.tab === tab ? 'page' : 'false'));
  const sub = $('#subnav');
  if (sub) {
    sub.hidden = tab !== 'setup';
    sub.innerHTML = tab === 'setup' ? SETUP_SECS.filter(([k]) => !Nav.ADMIN_SECS.includes(k) || isAdmin()).map(([k, l]) => `<button data-sec="${k}" aria-current="${k === view ? 'page' : 'false'}">${l}</button>`).join('') : '';
    sub.onclick = e => { const b = e.target.closest('[data-sec]'); if (b) go(b.dataset.sec); };
    // On a phone the sections scroll sideways: keep the current one in view (4.0.1).
    const cur = $('[aria-current=page]', sub);
    if (cur) { const x = cur.getBoundingClientRect().left - sub.getBoundingClientRect().left + sub.scrollLeft;
      sub.scrollLeft = Math.max(0, x - (sub.clientWidth - cur.offsetWidth) / 2); }
  }
  $('#ribbon button[aria-current=page]')?.scrollIntoView({ inline: 'nearest', block: 'nearest' });
  document.body.classList.remove('lit', 'flashing');
  const mm = $('#main'); mm.onclick = mm.oninput = mm.onchange = null;
  const fn = VIEWS[view] || VIEWS.home;
  quiet(Promise.resolve(fn(extra)).finally(foldSums));
  window.scrollTo(0, 0);
}
const VIEWS = {};

/* ---------------------------------------------------------------- feature search (4.2.1)
   The box at the top of every page. Typing lists matching features
   (search.js); choosing one goes to its page, opens its panel, scrolls to
   it and outlines it for a moment. Enter takes the first; / jumps to the box. */
async function jumpTo(f) {
  if (f.f) { try { localStorage.setItem('fold:' + f.f, '1'); } catch { /* private mode */ } }
  go(f.v, f.x);
  const want = () => {
    if (f.f) return $(`#main [data-fold="${f.f}"]`);
    if (f.h) {
      const h = $$('#main h2, #main h3, #main summary').find(x => x.textContent.trim().startsWith(f.h));
      return h && (h.closest('.panel, .fold, details') || h);
    }
    return $('#main .view') || $('#main');
  };
  let el = null;
  for (let i = 0; i < 40 && !(el = want()); i++) await new Promise(r => setTimeout(r, 75));   // views load their data first
  if (!el) { toast(`\u201c${f.t}\u201d isn\u2019t shown here for your account.`); return; }
  const fd = el.closest('.fold');
  if (fd && fd.classList.contains('closed')) $('.foldbar', fd)?.click();      // already drawn closed: open it
  el.style.scrollMarginTop = (($('#top')?.offsetHeight || 0) + 14) + 'px';   // not under the sticky header
  el.scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start' });
  el.classList.remove('found', 'fade'); void el.offsetWidth; el.classList.add('found');
  setTimeout(() => el.classList.add('fade'), 1600);
  setTimeout(() => el.classList.remove('found', 'fade'), 3000);
}
function setupSearch() {
  const q = $('#q'), box = $('#qres');
  if (!q || !box || typeof Search === 'undefined') return;
  let hits = [], sel = 0;
  const close = () => { box.hidden = true; q.setAttribute('aria-expanded', 'false'); q.removeAttribute('aria-activedescendant'); };
  const draw = () => {
    hits = Search.find(q.value);
    if (!q.value.trim()) return close();
    sel = Math.min(sel, Math.max(0, hits.length - 1));
    box.innerHTML = hits.length ? hits.map((f, i) => `<button type="button" role="option" id="qr${i}" data-qi="${i}" aria-selected="${i === sel}">
      <span>${esc(f.t)}</span><small>${esc(f.w)}</small></button>`).join('') : '<p>No feature matches. Try another word, or the Manual (?).</p>';
    box.hidden = false; q.setAttribute('aria-expanded', 'true');
    if (hits.length) q.setAttribute('aria-activedescendant', 'qr' + sel);
  };
  const pick = i => { const f = hits[i]; if (!f) return; q.value = ''; close(); q.blur(); jumpTo(f); };
  q.addEventListener('input', () => { sel = 0; draw(); });
  q.addEventListener('focus', () => { if (q.value.trim()) draw(); });
  q.addEventListener('keydown', e => {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      if (!hits.length) return;
      e.preventDefault(); sel = (sel + (e.key === 'ArrowDown' ? 1 : hits.length - 1)) % hits.length; draw();
      $('#qr' + sel)?.scrollIntoView({ block: 'nearest' });
    } else if (e.key === 'Enter') { e.preventDefault(); pick(sel); }
    else if (e.key === 'Escape') { if (q.value) { q.value = ''; close(); } else q.blur(); }
  });
  box.addEventListener('mousedown', e => e.preventDefault());           // keep the box focused while clicking
  box.addEventListener('click', e => { const b = e.target.closest('[data-qi]'); if (b) pick(+b.dataset.qi); });
  // 4.5.1: only if it's still away: a search typed again within the 150 ms
  // (right after picking a result) kept its results hidden.
  q.addEventListener('blur', () => setTimeout(() => { if (document.activeElement !== q) close(); }, 150));
  document.addEventListener('keydown', e => {
    if (e.key === '/' && !typing(document.activeElement) && !e.ctrlKey && !e.metaKey && !e.altKey && !$('#dlg').open) {
      e.preventDefault(); q.focus();
    }
  });
}

/* ---------------------------------------------------------------- data loaders */
async function loadSettings() { S.settings = await api('settings'); return S.settings; }
/* Saving settings (4.0.1). A screen builds the whole settings document from
   S.settings, changes a part and calls saveSettings. Saves go one at a time:
   a save asked for while another is on its way waits, and only what it
   changed is put on top of the latest settings, so quick changes in a row
   all count (before, the second was refused as "changed on another
   device" and the first value stayed). Saves waiting together go as one,
   so version history isn't filled with tiny steps. A real change from
   another device is still caught: the server checks the version. */
const SAVEQ = { running: false, pending: null, timer: null };
function saveSettings(next, msg = 'Saved') {
  // 4.9.1: a pattern saved again from an editor keeps its folder
  for (const [k, e] of Object.entries((next && next.effects) || {})) {
    const was = ((S.settings && S.settings.effects) || {})[k];
    if (was && was.folder && e && typeof e === 'object' && !('folder' in e)) e.folder = was.folder;
  }
  const changes = Merge.diff(S.settings, next);
  return new Promise((resolve, reject) => {
    const job = SAVEQ.pending || (SAVEQ.pending = { changes: [], msg, waiters: [] });
    job.changes.push(...changes); job.msg = msg; job.waiters.push({ resolve, reject });
    // A short wait gathers changes made together (several fields at once).
    clearTimeout(SAVEQ.timer); SAVEQ.timer = setTimeout(pumpSaves, 120);
  });
}
async function pumpSaves() {
  if (SAVEQ.running || !SAVEQ.pending) return;
  const job = SAVEQ.pending; SAVEQ.pending = null; SAVEQ.running = true;
  const doc = Merge.apply(clone(S.settings), job.changes);
  doc._rev = S.settings._rev;
  try {
    const r = await api('settings', { body: doc });
    doc._rev = r._rev; S.settings = doc; toast(job.msg); foldSums();
    job.waiters.forEach(w => w.resolve());
    quiet(refreshStatus());
  } catch (e) {
    if (/another device/.test(e.message)) { await loadSettings(); if (VIEWS[S.view]) quiet(VIEWS[S.view]()); }
    job.waiters.forEach(w => w.reject(e));
  } finally {
    SAVEQ.running = false;
    if (SAVEQ.pending) pumpSaves();
  }
}
async function loadCatalog() { if (!S.catalog) S.catalog = await api('catalog'); return S.catalog; }
async function loadDevices(force) { if (!S.devices || force) S.devices = await api('devices'); return S.devices; }
async function refreshStatus() {
  try { S.status = await api('status'); } catch (e) { setPill('bad', "Can't reach the app"); throw e; }
  statusPill(S.status); foldSums();
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
  if (!$('#ribbon').children.length) { buildRibbon(); setupSearch(); }
  await Promise.all([loadSettings(), loadCatalog()]);
  if (!s.setup.wizard_done && u.role === 'admin') return wizard(0);
  // The status at the top right (and its On/Off buttons) on every page, not
  // only after Home or Music has loaded it; kept fresh while the tab is open.
  refreshStatus().catch(() => {});
  updateBar().catch(() => {});
  clearInterval(boot._pill);
  boot._pill = setInterval(() => { if (!document.hidden) refreshStatus().catch(() => {}); }, 60000);
  go((location.hash || '#home').slice(1), undefined, true);
  pwaStart();
}
/* "A new version is out" bar under the header (3.14). The app computer asks
   GitHub once a day; hiding the bar lasts until the next version. */
async function updateBar(fresh) {
  const bar = $('#updbar'), u = fresh || await api('update');
  S.update = u;
  let hidden = null; try { hidden = localStorage.getItem('elx-update-hidden'); } catch (e) { /* no storage */ }
  if (!u.newer || hidden === u.latest) { bar.hidden = true; return; }
  const how = u.download ? `<a class="btn small primary" href="${esc(u.download)}" target="_blank" rel="noopener noreferrer" title="${esc(u.download_name)}">${S.session?.local ? 'Download' : 'Download for the app computer'}</a>` : '';
  bar.innerHTML = `<span class="grow"><b>EaveLuxOS ${esc(u.latest)} is available.</b> You have ${esc(u.current)}. Your settings are kept when you update (Manual, section 23).</span>
    ${how}<a class="btn small ${u.download ? 'ghost' : 'primary'}" href="${esc(u.url)}" target="_blank" rel="noopener noreferrer">What's new</a>
    <button class="small ghost" data-updhide>Not now</button>`;
  bar.hidden = false;
  bar.onclick = e => { if (e.target.closest('[data-updhide]')) { try { localStorage.setItem('elx-update-hidden', u.latest); } catch (x) { /* no storage */ } bar.hidden = true; } };
}

/* Settings › Lights usage (3.15): hours on per month, counted by this app,
   with an optional cost estimate. */
async function usagePanel(box) {
  if (!box) return;
  let r; try { r = await api('runtime'); } catch (e) { box.innerHTML = `<h2>Lights usage</h2><p class="muted small">${esc(e.message)}</p>`; return; }
  const u = S.settings.usage || {}, ro = role() === 'viewer';
  const months = r.months || [], max = Math.max(1, ...months.map(m => m.hours));
  const cost = h => (u.watts && u.rate != null) ? h * u.watts / 1000 * u.rate : null;
  const now = months[months.length - 1] || { hours: 0 }, c = cost(now.hours);
  const label = k => new Date(k + '-15T12:00').toLocaleDateString([], { month: 'short' });
  box.innerHTML = `<h2>Lights usage</h2>
    <p><b class="num">${now.hours.toFixed(1)} hours</b> on this month${c != null ? `, about <b>$${c.toFixed(2)}</b>` : ''}.</p>
    <div class="bars" role="img" aria-label="Hours on per month">${months.map(m => `<div class="bar" title="${esc(label(m.month))}: ${m.hours} h${cost(m.hours) != null ? ` (about $${cost(m.hours).toFixed(2)})` : ''}">
      <span style="height:${Math.round(m.hours / max * 100)}%"></span><small>${esc(label(m.month)).slice(0, 1)}</small></div>`).join('')}</div>
    <details><summary class="small">Estimate the cost</summary><div class="row" style="margin-top:8px">
      <label class="field" style="flex:1;min-width:120px">Watts for the whole system <span class="hint">On the power supply's label (its maximum, so the estimate errs high)</span><input type="number" id="uswatts" min="0" max="5000" step="1" value="${u.watts ?? ''}" ${ro ? 'disabled' : ''}></label>
      <label class="field" style="flex:1;min-width:120px">Price per kWh ($) <span class="hint">From your electric bill</span><input type="number" id="usrate" min="0" max="5" step="0.001" value="${u.rate ?? ''}" ${ro ? 'disabled' : ''}></label></div>
      ${ro ? '' : '<div><button class="small ghost" data-ussave>Save</button></div>'}</details>
    <p class="note">Counted by this app while it runs, from when it sent an on state (a music show counts as on). Time the app wasn\u2019t running isn\u2019t counted.</p>`;
  box.onclick = e => {
    const b = e.target.closest('[data-ussave]'); if (!b) return;
    e.stopPropagation();
    const num = id => { const v = $(id).value.trim(); return v === '' ? null : Number(v); };
    const n = clone(S.settings); n.usage = { watts: num('#uswatts'), rate: num('#usrate') };
    busy(b, () => saveSettings(n)).then(() => usagePanel(box)).catch(() => {});
  };
}

/* Settings › Phone alerts (3.15): push messages through ntfy (free, no
   account) when the lights can't be reached, a controller is offline or
   unreadable, or a new version is out. Administrators only. */
const ALERT_EVENTS = [['failed', 'The lights can\u2019t be reached to turn on or off (after 10 minutes)'],
  ['offline', 'A controller is offline (after 15 minutes)'], ['unreadable', 'Trimlight can\u2019t read a controller (code 12006)'],
  ['update', 'A new EaveLuxOS version is out']];
async function alertPanel(box) {
  if (!box) return;
  let a; try { a = await api('alerts'); } catch (e) { box.innerHTML = `<h2>Phone alerts</h2><p class="muted small">${esc(e.message)}</p>`; return; }
  box.innerHTML = `<h2>Phone alerts</h2>
    <p class="note">Get a message on your phone when something needs you. It uses <b>ntfy</b>, a free app with no account.</p>
    <ol class="small" style="margin:0;padding-left:1.2em">
      <li>Install <b>ntfy</b> from the App Store or Google Play.</li>
      <li>In ntfy, tap <b>+</b> (Subscribe to topic) and enter this topic:
        <div class="row" style="margin:6px 0"><code id="altopic">${esc(a.topic)}</code><button class="small ghost" data-alcopy>Copy</button></div>
        ${a.server !== 'https://ntfy.sh' ? `<span class="muted">Use another server: ${esc(a.server)}</span>` : ''}</li>
      <li>Tap <b>Send a test</b> below.</li></ol>
    <div class="row"><button class="small" data-altest>Send a test</button></div>
    <label class="check"><input type="checkbox" id="alon" ${a.enabled ? 'checked' : ''}> <b>Send alerts</b></label>
    <div class="stack" style="gap:4px;margin-left:4px">${ALERT_EVENTS.map(([k, l]) => `<label class="check small"><input type="checkbox" data-alev="${k}" ${a.events[k] ? 'checked' : ''}> ${l}</label>`).join('')}</div>
    <details><summary class="small">Topic and server</summary><div class="stack" style="margin-top:8px">
      <label class="field">Topic <span class="hint">Anyone who knows it can read your alerts, so keep it hard to guess.</span><input type="text" id="altop" value="${esc(a.topic)}" maxlength="64"></label>
      <label class="field">ntfy server <span class="hint">Leave as is unless you run your own.</span><input type="url" id="alsrv" value="${esc(a.server)}"></label>
      <div><button class="small ghost" data-alsave>Save topic and server</button></div></div></details>
    <p class="note">A problem is sent once, then again at most every 6 hours, and a message follows when it\u2019s back to normal. Messages never include your address.</p>`;
  const save = (body, b) => busy(b, () => api('alerts/settings', { body })).then(r => { toast('Saved'); return r; });
  box.onchange = e => {
    const t = e.target;
    if (t.id === 'alon') save({ enabled: t.checked }).catch(() => { t.checked = !t.checked; });
    else if (t.dataset.alev) save({ events: { [t.dataset.alev]: t.checked } }).catch(() => { t.checked = !t.checked; });
  };
  box.onclick = e => {
    const b = e.target.closest('button'); if (!b) return;
    e.stopPropagation();
    if (b.dataset.alcopy !== undefined) { try { navigator.clipboard.writeText(a.topic); toast('Topic copied'); } catch (x) { toast('Select the topic and copy it.', true); } }
    else if (b.dataset.altest !== undefined) busy(b, () => api('alerts/test', { body: {} })).then(() => toast('Sent. Check your phone.')).catch(() => {});
    else if (b.dataset.alsave !== undefined) save({ topic: $('#altop').value.trim(), server: $('#alsrv').value.trim() }, b).then(() => alertPanel(box)).catch(() => {});
  };
}

/* Light / Dark / Auto (3.15): theme.js applies the saved choice before the
   page is drawn; this button cycles it. Kept per device. */
// The screen theme (4.0: labeled as a theme, so "Auto" isn't mistaken for the lights' schedule).
const THEMES = { auto: ['themeauto', 'Theme: auto', 'Screen theme: follows this device (tap for Light)'],
                 light: ['sun', 'Theme: light', 'Screen theme: Light (tap for Dark)'], dark: ['moon', 'Theme: dark', 'Screen theme: Dark (tap for Auto)'] };
function themeNow() { const t = document.documentElement.getAttribute('data-theme'); return t === 'light' || t === 'dark' ? t : 'auto'; }
function setTheme(t) {
  if (t === 'light' || t === 'dark') document.documentElement.setAttribute('data-theme', t);
  else { t = 'auto'; document.documentElement.removeAttribute('data-theme'); }
  try { if (t === 'auto') localStorage.removeItem('elx-theme'); else localStorage.setItem('elx-theme', t); } catch (e) { /* no storage: this visit only */ }
  // The phone's status-bar color follows the chosen theme too.
  const d = $('#tcdark'), l = $('#tclight');
  if (d && l) { d.media = t === 'auto' ? '(prefers-color-scheme: dark)' : t === 'dark' ? 'all' : 'not all';
                l.media = t === 'auto' ? '(prefers-color-scheme: light)' : t === 'light' ? 'all' : 'not all'; }
  return t;
}

/* Header buttons next to the status pill: lights on, lights off, the theme,
   and (only on the computer the app runs on) Quit. */
function buildQuick(canControl, local) {
  const q = $('#quick');
  const btn = (k, ic, label, title) => `<button type="button" class="qbtn${k === 'quit' ? ' qquit' : ''}" data-q="${k}" title="${title}" aria-label="${title}">${icon(ic)}<span class="qlbl">${label}</span></button>`;
  const th = THEMES[themeNow()];
  q.innerHTML = (canControl ? btn('on', 'bulbon', 'On', 'Turn the lights on') + btn('off', 'power', 'Off', 'Turn the lights off') : '')
    + btn('theme', th[0], th[1], th[2]) + btn('help', 'help', 'Manual', 'Open the manual')
    + (local ? btn('quit', 'exit', 'Quit', 'Quit the app') : '');
  q.hidden = !q.innerHTML;
  setTheme(themeNow());
  q.onclick = async e => {
    const b = e.target.closest('button'); if (!b) return;
    if (b.dataset.q === 'quit') return quitApp();
    if (b.dataset.q === 'help') return go('manual');
    if (b.dataset.q === 'theme') {
      const next = { auto: 'light', light: 'dark', dark: 'auto' }[themeNow()];
      setTheme(next);
      const [ic, label, title] = THEMES[next];
      b.innerHTML = `${icon(ic)}<span class="qlbl">${label}</span>`; b.title = title; b.setAttribute('aria-label', title);
      if (S.view === 'map' || S.view === 'create') VIEWS[S.view]();   // drawings pick up the new colors
      return;
    }
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
    : `<p class="muted">To use the app from this device, first create an account on the computer running it (Setup › Accounts & access).</p>`}
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
      <p>Create your Administrator account so phones and other computers at home can sign in. You can add accounts for other people later (Setup › Accounts & access), as Editors or Viewers.</p>
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
    const t = st.target;
    document.body.classList.toggle('lit', t.on);
    document.body.classList.toggle('flashing', t.reason === 'flash');
    const { head, sub } = stateLine(st);
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
            <p style="margin-top:8px"><a class="btn small ghost" href="#quick">Quick buttons</a></p>
            ${st.error ? `<p class="callout warn" style="margin-top:10px">Can't reach the lights right now: ${esc(st.error)}</p>` : ''}</div>
          ${tonightPanel(st)}
          <div><div class="strip" aria-label="Today, midnight to midnight">${sky.join('')}</div>
            <div class="ticks"><span style="left:0">12 AM</span><span style="left:25%">6 AM</span><span style="left:50%">Noon</span><span style="left:75%">6 PM</span><span style="left:100%">12 AM</span></div>
            <div class="legend"><span>Sunrise <b>${esc(st.sun.sunrise ?? '—')}</b></span><span>Sunset <b>${esc(st.sun.sunset ?? '—')}</b></span><span>Now <b>${esc(st.now_label)} ${esc(st.tz)}</b></span></div>
            ${wx ? `<p class="note" style="margin-top:6px">${!wx.fresh ? `Weather unavailable${wx.error ? ': ' + esc(wx.error) : ''}. Weather rules are paused.` : `Weather: ${esc(wx.summary)}${wx.match ? (wx.active ? `. ${esc(wx.match)} is running.` : `. Matches ${esc(wx.match)}.`) : '.'}`}</p>` : ''}
            ${st.rotation ? `<p class="note">${st.rotation.nightly ? `A different pattern each night: ${esc(st.rotation.labels.join(', '))}.`
              : st.rotation.each ? `Playing in turn: ${esc(st.rotation.labels.map((l, i) => `${l} ${st.rotation.each[i]} min`).join(', '))}.`
              : `Rotating ${esc(st.rotation.labels.join(', '))} every ${st.rotation.minutes} min.`}</p>` : ''}
          </div>
          <div class="panel"><h2>Turn on</h2>
            ${(() => {
              const chip = ([k, e]) => `<button data-on="${esc(k)}" class="${t.on && t.effect_key === k ? 'current' : ''}">${swatches(effectSwatches(e), 4)}${esc(e.label || k)}</button>`;
              const fav = favs();
              if (!fav.length) return `<div class="chips">${effects.map(chip).join('')}</div>`
                + (role() !== 'viewer' ? '<p class="note" style="margin-top:8px">Tip: tap the star on a pattern (Patterns tab) to pin it here as a big button.</p>' : '');
              return `<div class="favs">${fav.map(k => { const e = S.settings.effects[k]; return `<button data-on="${esc(k)}" class="fav ${t.on && t.effect_key === k ? 'current' : ''}">${strand(e.colors || effectSwatches(e), e.colors ? e.counts : undefined)}<b>${esc(e.label || k)}</b></button>`; }).join('')}</div>
                <details style="margin-top:12px"><summary class="small">All patterns (${effects.length})</summary><div class="chips" style="margin-top:10px">${effects.map(chip).join('')}</div></details>`;
            })()}
            <div class="row" style="margin-top:12px"><button data-act="off" class="ghost">Turn off</button>
              ${(st.override || lv.adjusted) ? '<button data-act="resume" class="ghost">Return to schedule</button>' : ''}
              ${st.flash.available || st.flash.active ? `<button data-act="${st.flash.active ? 'stop_flash' : 'flash'}" class="ghost danger">${st.flash.active ? 'Stop flash' : `Security flash (${st.flash.minutes} min)`}</button>` : ''}
              ${st.alert && st.alert.showing && role() !== 'viewer' ? '<button data-act="dismiss_alert" class="ghost">Dismiss weather alert</button>' : ''}</div>
          </div>
          <div class="panel"><h2>Brightness and speed</h2>
            <div class="levels" aria-disabled="${!canAdjust}" style="margin-top:12px">
              ${[['brightness', 'Brightness'], ['speed', 'Speed']].map(([k, l]) => `<label>${l}<input type="range" min="0" max="255" data-level="${k}" value="${lv[k] ?? 128}" ${!canAdjust || lv[k] == null ? 'disabled' : ''}><output>${lv[k] == null ? '—' : Math.round(lv[k] / 2.55) + '%'}</output></label>`).join('')}
            </div>
            <p class="note" style="margin-top:8px">${!t.on ? 'Turn the lights on to adjust them.' : t.reason === 'flash' ? `Locked during the ${esc((st.flash.label || 'security flash').toLowerCase())}.` : t.reason === 'alert' ? 'Locked while the weather alert shows.' : t.reason === 'music' ? 'Set in the Trimlight app during a music show.' : lv.brightness == null ? 'Levels appear once the controller reports this saved pattern.' : lv.adjusted ? 'Adjusted by hand until the next scheduled change.' : 'Changes last until the next scheduled change.'}</p>
          </div>
        </div>
        <div class="stack">
          <div class="panel"><div class="panel-head"><h2>This week</h2><button class="small ghost" data-tabjump="schedule">Edit schedule</button></div>
            <table class="week"><tbody>${st.days.map((d, i) => {
              const dst = prevAbbr && d.abbr !== prevAbbr ? ` <span class="dst">${esc(d.abbr)} starts</span>` : ''; prevAbbr = d.abbr;
              return `<tr class="${i === 0 ? 'today' : ''}"><td class="d">${i === 0 ? 'Today' : esc(d.dow)}<small>${esc(d.label)}</small></td>
                <td>${(d.windows || []).length ? d.windows.map(w => `<div class="win"><span class="num">${esc(w.on)} – ${esc(w.off)}</span><div class="r">${esc(w.rule)}${w.controllers ? ' \u00b7 ' + esc(w.controllers.join(', ')) : ''}</div></div>`).join('') : '<span class="r">Off</span>'}${dst}</td>
                <td class="sun num">☀ ${esc(d.sunrise ?? '—')}<br>☾ ${esc(d.sunset ?? '—')}</td></tr>`; }).join('')}</tbody></table></div>
          ${controllerCards(st)}
          <div class="panel"><details><summary>Activity</summary>
            <ul class="log">${st.events.map(e => `<li class="${esc(e.level)}"><time>${esc(e.label || e.t)}</time>${esc(e.msg)}</li>`).join('')}</ul>
          </details></div>
        </div>
      </div></div>`;
  };
  const act = async (body, btn) => busy(btn, async () => { S.status = await api('action', { body }); render(S.status); }).catch(() => {});
  m.onclick = e => {
    const b = e.target.closest('button'); if (!b) return;
    if (b.dataset.one) act({ action: 'one', device: b.dataset.dev, state: b.dataset.one }, b);
    else if (b.dataset.on) act({ action: 'on', effect: b.dataset.on }, b);
    else if (b.dataset.act) act({ action: b.dataset.act }, b);
    else if (b.dataset.tabjump) go(b.dataset.tabjump);
    else if (b.dataset.dismisswarn !== undefined) busy(b, () => api('warnings/dismiss', { body: {} })).then(async () => render(await refreshStatus())).catch(() => {});
  };
  m.oninput = e => { if (e.target.dataset.level) e.target.nextElementSibling.textContent = Math.round(e.target.value / 2.55) + '%'; };
  m.onchange = e => {
    if (e.target.dataset.level) act({ action: 'levels', [e.target.dataset.level]: Number(e.target.value) });
    else if (e.target.dataset.onepat && e.target.value) act({ action: 'one', device: e.target.dataset.onepat, state: 'on', effect: e.target.value });
  };
  render(await refreshStatus());
  S.timers.push(setInterval(async () => { if (!document.hidden && !$('#dlg').open && document.activeElement?.type !== 'range') render(await refreshStatus()); }, 30000));
};

/* Home › Tonight (3.15): the next 24 hours of the schedule, with a countdown
   to the next thing that happens. */
function inWords(min) {
  if (min < 1) return 'now';
  const h = Math.floor(min / 60), m = min % 60;
  return 'in ' + (h ? `${h} h${m ? ` ${m} min` : ''}` : `${m} min`);
}
function tonightPanel(st) {
  const ev = st.tonight || [];
  if (!ev.length) return '';
  const icons = { sunset: '\u263e', on: '\u25cf', switch: '\u21bb', off: '\u25cb' };
  const verb = { sunset: '', on: 'On: ', switch: 'Switches to ', off: 'Off: ' };
  const first = ev.find(e => e.kind !== 'sunset') || ev[0], t = st.target || {};
  // Something set by hand (or a flash or a music show) runs now: say that,
  // not "Lights on in 4 h" while they're already on (3.15.1).
  const nxt = st.next_change ? `${st.next_change}${st.next_change_day ? ' ' + st.next_change_day : ''}` : null;
  const lead = t.reason === 'manual' ? `${t.on ? 'On' : 'Off'} by hand${nxt ? ` \u00b7 the schedule takes over at ${nxt}` : ''}`
    : t.reason === 'flash' ? `${st.flash && st.flash.label || 'Security flash'}${st.flash && st.flash.until ? ` until ${st.flash.until}` : ''}`
    : t.reason === 'alert' ? `${t.source}${st.alert && st.alert.until ? ` until ${st.alert.until}` : ''}`
    : t.reason === 'music' && !(st.music && st.music.scheduled) ? 'Music show, until it\u2019s stopped'
    : first.kind === 'off' ? `Lights off ${inWords(first.in_min)}` : first.kind === 'sunset' ? `Sunset ${inWords(first.in_min)}`
    : first.kind === 'switch' ? `${first.text.split(':')[0]} ${inWords(first.in_min)}` : `Lights on ${inWords(first.in_min)}`;
  return `<div class="panel tonight" aria-label="Coming up in the next 24 hours"><div class="panel-head"><h2>${esc(lead)}</h2><span class="small muted">Next 24 hours</span></div>
    <ol class="tl">${ev.map(e => `<li class="tl-${e.kind}"><span class="tl-ic" aria-hidden="true">${icons[e.kind] || ''}</span><span class="num tl-t">${esc(e.at)}${e.day ? ' ' + esc(e.day) : ''}</span>
      <span class="grow">${esc(verb[e.kind] || '')}${esc(e.text)}</span><span class="small muted num">${esc(inWords(e.in_min))}</span></li>`).join('')}</ol></div>`;
}

/* ---------------------------------------------------------------- shared pattern helpers */
// Favorites (3.15): patterns pinned to Home, in the order they were pinned.
const MAX_FAVS = 6;
function favs() { const e = S.settings.effects || {}; return (S.settings.favorites || []).filter(k => e[k]).slice(0, MAX_FAVS); }
function usedBy(key) {
  const s = S.settings, out = [];
  (s.rules || []).forEach(r => { const e = Array.isArray(r.effect) ? r.effect : [r.effect]; if (e.includes(key)) out.push(`schedule rule “${r.name}”`); });
  (s.weather_rules || []).forEach(r => { const e = Array.isArray(r.effect) ? r.effect : [r.effect]; if (e.includes(key)) out.push(`weather rule “${r.name}”`); });
  if (s.security?.effect === key) out.push('the security flash');
  (s.gameday?.teams || []).forEach(t => { if (t.effect === key) out.push(`game-day lights for ${t.name}`); });
  if (s.weather_alerts?.effect === key) out.push('severe weather alerts');
  Object.entries(s.mood || {}).forEach(([lv, k]) => { if (k === key) out.push(`mood follow (${lv} music)`); });
  (s.holidays?.list || []).forEach(h => { if ((h.effects || []).includes(key)) out.push(`the holiday lights for ${(HOLIDAY_NAMES[h.key] || h.key.replace(/_/g, ' '))}`); });   // 3.19.1
  if ((s.holidays?.country?.effects || []).includes(key)) out.push('public holiday lights');
  Object.entries(s.effects || {}).forEach(([k, e]) => { if (e.split && (Object.values(e.split).includes(key) || e.rest === key)) out.push(`the split pattern ${e.label || k}`); });
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
function devBulbs(d) {
  const ends = (d.ports || []).filter(p => p.end > 0 && !p.unused).map(p => p.end);     // not-connected ports don't count (3.18.1)
  return ends.length ? Math.max(...ends) : 100;
}
function totalBulbs() {
  // 4.9.1: the controller chosen in Create (Bulbs of), else the first this app runs
  const d = (S.devices || []).find(x => x.id === S.designDev && x.ports) || (S.devices || []).find(x => x.selected && x.ports)
    || (S.devices || []).find(x => x.ports);
  return d ? devBulbs(d) : 100;
}
/* Create's "Bulbs of" choice (4.9.1): with controllers of different
   lengths, which one the preview and Paint bulbs count. A pattern repeats
   along any controller's lights, so it works on each. */
function designDevPick() {
  const ds = (S.devices || []).filter(x => x.selected && x.ports);
  if (ds.length < 2 || new Set(ds.map(devBulbs)).size < 2) return '';
  const cur = ds.find(x => x.id === S.designDev) || ds[0];
  return `<label class="row small" style="gap:6px">Bulbs of<select id="designdev" style="width:auto">${ds.map(x =>
    `<option value="${esc(x.id)}" ${x.id === cur.id ? 'selected' : ''}>${esc(x.name || 'Controller')} (${devBulbs(x)} bulbs)</option>`).join('')}</select></label>`;
}
// Small per-browser conveniences (4.9.1): never needed, so failures are ignored.
function lsGet(k) { try { return localStorage.getItem('elx:' + k); } catch { return null; } }
function lsSet(k, v) { try { localStorage.setItem('elx:' + k, v); } catch { /* private mode */ } }
/* Patterns › Folder (4.9.1): one folder per pattern, typed or picked. */
function folderDialog(key) {
  const e = S.settings.effects[key];
  if (!e) return;
  const folders = [...new Set(Object.values(S.settings.effects || {}).map(x => (x.folder || '').trim()).filter(Boolean))].sort();
  dialog(`<h2>Folder for \u201c${esc(e.label || key)}\u201d</h2>
    <label class="field">Folder<input type="text" name="folder" maxlength="30" list="pfolderlist" value="${esc(e.folder || '')}" placeholder="e.g. Christmas"></label>
    <datalist id="pfolderlist">${folders.map(f => `<option value="${esc(f)}">`).join('')}</datalist>
    <p class="note">Leave it empty for no folder. Folders only sort your list; they change nothing else.</p>`, async f => {
    const n = clone(S.settings), v = f.folder.value.trim().slice(0, 30);
    if (v) n.effects[key].folder = v; else n.effects[key].folder = '';
    await saveSettings(n, v ? `In ${v}` : 'No folder');
    VIEWS.patterns('mine');
  });
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
  return (await addPatterns([def]))[0];
}
async function addPatterns(defs) {
  const n = clone(S.settings); n.effects = n.effects || {};
  const keys = defs.map(def => { const key = slug(def.label, n.effects); n.effects[key] = def; return key; });
  await saveSettings(n, defs.length === 1 ? `Added “${defs[0].label}” to your patterns` : `Added ${defs.length} patterns`);
  return keys;
}

/* Named colors (3.20): the web's color names, grouped like the RGB charts
   Trimlight owners share, with how each looks on LED lights. */
function namedColorsDialog(onPick) {
  const names = S.catalog.names, groups = S.catalog.name_groups;
  const draw = () => {
    const q = Colors.key($('#ncq').value || ''), good = $('#ncgood').checked;
    $('#nclist').innerHTML = groups.map(g => {
      const list = names.filter(c => c.group === g && (!q || Colors.key(c.name).includes(q)) && (!good || ['great', 'dim', 'shift'].includes(c.led.kind)));
      return list.length ? `<h3 style="margin:8px 0 4px">${esc(g)}</h3><div class="ncgrid">${list.map(c => `<button type="button" class="ncbtn" data-nc="${c.hex}" title="${esc(c.name)} ${c.hex}: ${esc(c.led.text)}">
        <i style="background:${c.hex}"></i><span><b>${esc(c.name)}</b><small class="${c.led.kind === 'great' ? 'ok' : 'muted'}">${esc(c.led.text)}</small></span></button>`).join('')}</div>` : '';
    }).join('') || '<p class="muted">No color by that name.</p>';
  };
  dialog(`<h2>Named colors</h2>
    <p class="note">The standard web color names (the RGB charts shared in Trimlight groups). LEDs aren't screens: pale colors and whites look white, browns look orange, grays are dim white. The preview shows each as it is on the chart.</p>
    <div class="row"><input type="search" id="ncq" class="grow" style="flex:1" placeholder="Search: crimson, sky, forest…" aria-label="Search named colors">
      <label class="check small"><input type="checkbox" id="ncgood"> Only colors that show well on lights</label></div>
    <div id="nclist" style="max-height:55vh;overflow:auto"></div>`, null);
  const f = $('#dlg form');
  f.addEventListener('input', draw);
  f.addEventListener('click', e => { const b = e.target.closest('[data-nc]'); if (b) { $('#dlg').close(); onPick(b.dataset.nc); } });
  draw();
  $('#ncq').focus();
}

/* ---------------------------------------------------------------- share codes (3.19)
   A pattern (or a few, as a playlist) as a short code "ELX1:…" and a QR
   code to send to someone. Codes from someone else are checked on the app
   computer (sharecode.py) before anything is shown or added. */
const shareable = e => !!(e && (e.colors || e.builtin !== undefined) && !e.scene && !e.split);
async function shareDialog(keys, rotate) {
  let r;
  try { r = await api('share', { body: { keys, rotate: keys.length > 1 ? (rotate || 15) : undefined } }); } catch (e) { return; }
  let qr = '';
  try { qr = r.code.length <= 1800 ? QR.svg(r.code, r.code.length > 900 ? 'L' : 'M', 4) : ''; } catch { qr = ''; }
  dialog(`<h2>Share ${keys.length > 1 ? keys.length + ' patterns' : '“' + esc(r.labels[0]) + '”'}</h2>
    <p class="note">Send this code in a message or post. In EaveLuxOS, the other person taps <b>Patterns › Open a share code</b> and pastes it. Only the colors and motion are in it, nothing about your home.</p>
    <textarea id="sharecode" readonly rows="4" style="width:100%;font-family:ui-monospace,monospace;font-size:12px">${esc(r.code)}</textarea>
    <div class="row"><button type="button" class="small" data-copy="sharecode">Copy the code</button>${navigator.share ? '<button type="button" class="small ghost" data-sharesys>Send…</button>' : ''}<span class="small muted">${r.length} characters</span></div>
    ${qr ? `<div class="qrbox" style="text-align:center;background:#fff;padding:8px;border-radius:8px">${qr}</div>
      <p class="note">Or let them scan it: a phone's camera shows the code as text to copy and paste. Some browsers scan it right in Open a share code.</p>`
      : '<p class="note">This one is too long for a QR code; send the code itself.</p>'}`, null);
  const f = $('#dlg form');
  f.addEventListener('click', e => {
    const b = e.target.closest('button'); if (!b) return;
    if (b.dataset.copy) { const el = $('#sharecode'); el.select(); (navigator.clipboard?.writeText ? navigator.clipboard.writeText(el.value) : Promise.reject()).then(() => toast('Copied'), () => toast('Selected. Copy it with Ctrl+C (\u2318C on a Mac).')); }
    if (b.dataset.sharesys !== undefined) navigator.share({ title: 'EaveLuxOS pattern', text: r.code }).catch(() => {});
  });
}
function sharePickDialog() {
  const effs = Object.entries(S.settings.effects || {}).filter(([, e]) => shareable(e));
  if (!effs.length) return toast('None of your patterns can be shared as a code (patterns drawn bulb by bulb or split by controller can be exported as a file).', true);
  dialog(`<h2>Share patterns</h2><p class="note">Pick up to 8. More than one can travel as a playlist, each showing a few minutes.</p>
    <div class="stack" style="max-height:45vh;overflow:auto">${effs.map(([k, e]) => `<label class="check"><input type="checkbox" name="sp" value="${esc(k)}"> ${esc(e.label || k)} ${e.colors ? strand(e.colors, e.counts) : ''}</label>`).join('')}</div>
    <label class="field">Each shows (minutes, for a playlist)<input type="number" name="rot" min="1" max="240" value="15"></label>`, async f => {
    const keys = $$('input[name=sp]:checked', f).map(x => x.value);
    if (!keys.length) throw new Error('Pick at least one pattern.');
    if (keys.length > 8) throw new Error('Up to 8 patterns in one code.');
    setTimeout(() => shareDialog(keys, Math.max(1, Math.min(240, +f.rot.value || 15))), 0);
  }, { ok: 'Make the code' });
}
function openShareDialog(prefill = '') {
  const canScan = 'BarcodeDetector' in window;
  const cam = canScan && window.isSecureContext && navigator.mediaDevices?.getUserMedia;
  dialog(`<h2>Open a share code</h2>
    <p class="note">Paste a code someone sent you (it starts with <b>ELX1:</b>; the rest of their message can come along). You'll see the patterns before anything is added.</p>
    <textarea name="code" rows="4" style="width:100%;font-family:ui-monospace,monospace;font-size:12px" placeholder="ELX1:…">${esc(prefill)}</textarea>
    ${canScan ? `<div class="row">${cam ? '<button type="button" class="small ghost" data-scan>Scan a QR code</button>' : ''}<label class="btn small ghost" tabindex="0">QR code from a picture<input type="file" accept="image/*" data-qrpic hidden></label></div>
      <video id="qrvid" playsinline muted hidden style="width:100%;max-height:40vh;background:#000;border-radius:8px"></video>`
      : '<p class="note">To use a QR code: scan it with your phone\u2019s camera, copy the text it shows, and paste it here.</p>'}
    <div id="sharepv"></div>`, async f => {
    const r = await api('share/open', { body: { code: f.code.value } });
    if (!f.dataset.shown) { f.dataset.shown = '1'; showShared(r); return false; }      // first the preview, then add
    await addPatterns(r.patterns);                         // one save for all of them (3.19.1)
    VIEWS.patterns('mine');
  }, { ok: 'Show the patterns' });
  const f = $('#dlg form'); let stream = null;
  const stop = () => { if (stream) stream.getTracks().forEach(t => t.stop()); stream = null; const v = $('#qrvid'); if (v) v.hidden = true; };
  $('#dlg').addEventListener('close', stop, { once: true });
  const found = text => { stop(); f.code.value = text; delete f.dataset.shown; $('button.primary', f).click(); };
  const showShared = r => {
    $('#sharepv').innerHTML = `<p><b>${r.patterns.length} pattern${r.patterns.length > 1 ? 's' : ''}</b>${r.rotate ? `, a playlist of ${r.rotate} minutes each` : ''}:</p>
      ${r.patterns.map((p, i) => `<div class="row" style="align-items:center"><span class="grow"><b>${esc(p.label)}</b> ${p.colors ? strand(p.colors, p.counts) : '<span class="small muted">built-in effect</span>'}</span><button type="button" class="small ghost" data-trysh="${i}">Try</button></div>`).join('')}
      <p class="note">Try shows it on the house for 15 minutes.${r.rotate ? ' To use them as a playlist, pick them together in a rule.' : ''}</p>`;
    $('button.primary', f).textContent = r.patterns.length > 1 ? 'Add all to my patterns' : 'Add to my patterns';
    f._shared = r;
  };
  f.code.addEventListener('input', () => { delete f.dataset.shown; $('#sharepv').innerHTML = ''; $('button.primary', f).textContent = 'Show the patterns'; });
  f.addEventListener('click', async e => {
    const b = e.target.closest('button'); if (!b) return;
    if (b.dataset.trysh !== undefined) { const p = f._shared.patterns[+b.dataset.trysh]; return busy(b, () => api('action', { body: { action: 'try', effect: p } })).then(() => toast(`Showing “${p.label}” for 15 minutes`)).catch(() => {}); }
    if (b.dataset.scan !== undefined) {
      try {
        const det = new BarcodeDetector({ formats: ['qr_code'] }), v = $('#qrvid');
        stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } });
        v.srcObject = stream; v.hidden = false; await v.play();
        const look = async () => { if (!stream) return; try { const c = await det.detect(v); const hit = c.find(x => /ELX1:/.test(x.rawValue)); if (hit) return found(hit.rawValue); } catch { /* next frame */ } requestAnimationFrame(look); };
        look();
      } catch (err) { stop(); toast(err.name === 'NotAllowedError' ? 'The camera wasn\u2019t allowed.' : 'The camera couldn\u2019t start: ' + err.message, true); }
    }
  });
  f.addEventListener('change', async e => {
    const inp = e.target.closest('[data-qrpic]'); if (!inp || !inp.files[0]) return;
    try {
      const codes = await new BarcodeDetector({ formats: ['qr_code'] }).detect(await createImageBitmap(inp.files[0]));
      const hit = codes.find(x => /ELX1:/.test(x.rawValue));
      if (hit) found(hit.rawValue); else toast('No EaveLuxOS QR code found in that picture.', true);
    } catch (err) { toast('That picture couldn\u2019t be read: ' + err.message, true); }
    inp.value = '';
  });
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
    // 4.9.1: A to Z (or newest first), and folders such as Christmas or
    // Fourth of July. The order and the folder shown are remembered here.
    const all = Object.entries(S.settings.effects || {});
    const folders = [...new Set(all.map(([, e]) => (e.folder || '').trim()).filter(Boolean))].sort((a, b) => a.localeCompare(b));
    const sort = S.psort || lsGet('psort') || 'az';
    let fold = S.pfolder ?? lsGet('pfolder') ?? '';
    if (fold && fold !== ' ' && !folders.includes(fold)) fold = '';   // ' ' is No folder (names are trimmed)
    const name = e => String(e.label || '').toLowerCase();
    let effs = all.filter(([, e]) => !fold || (fold === ' ' ? !(e.folder || '').trim() : (e.folder || '').trim() === fold));
    if (sort === 'az') effs = effs.sort(([, a], [, b]) => name(a).localeCompare(name(b), undefined, { numeric: true }));
    else if (sort === 'new') effs = effs.reverse();
    const chip = (v, label, n) => `<button class="small ${fold === v ? '' : 'ghost'}" data-pfolder="${esc(v)}" aria-pressed="${fold === v}">${esc(label)} <span class="muted">${n}</span></button>`;
    body.innerHTML = `<div class="row" style="margin-bottom:12px"><button class="small ghost" data-splitnew>Split by controller</button>
      <span class="note">With more than one controller: a different pattern on each, at the same time.</span>
      <span class="grow"></span>${role() !== 'viewer' ? '<button class="small ghost" data-shareopen>Open a share code</button>' : ''}<button class="small ghost" data-sharepick>Share patterns</button></div>
      <div class="row pfolders" style="margin-bottom:12px;gap:6px">
        <label class="row small" style="gap:6px">Order<select id="psort" style="width:auto"><option value="az" ${sort === 'az' ? 'selected' : ''}>A to Z</option><option value="new" ${sort === 'new' ? 'selected' : ''}>Newest first</option><option value="old" ${sort === 'old' ? 'selected' : ''}>Oldest first</option></select></label>
        ${folders.length ? chip('', 'All', all.length) + folders.map(f => chip(f, f, all.filter(([, e]) => (e.folder || '').trim() === f).length)).join('')
          + chip(' ', 'No folder', all.filter(([, e]) => !(e.folder || '').trim()).length) : '<span class="note">Put patterns in folders (Christmas, Fourth of July\u2026) with Folder on each one.</span>'}</div>
      <div class="cards">${effs.map(([k, e]) => `<div class="card">
      <div class="title"><b>${esc(e.label || k)}</b><button class="small ghost favbtn" data-fav="${esc(k)}" aria-pressed="${favs().includes(k)}" title="${favs().includes(k) ? 'Remove from Home' : 'Pin to Home (up to ' + MAX_FAVS + ')'}" aria-label="${favs().includes(k) ? 'Remove from Home' : 'Pin to Home'}">${icon('star')}</button></div>
      ${e.colors ? strand(e.colors, e.counts) : strand(effectSwatches(e))}
      <p class="small muted">${esc(effectKind(e))}${usedBy(k).length ? ` · used by ${usedBy(k).length}` : ''}</p>
      ${e.scene && HouseFX.sceneTotal(e) !== addressSpace() && !houseDevs().some(x => devBulbs(x) === HouseFX.sceneTotal(e)) ? `<p class="small warn">Made for ${HouseFX.sceneTotal(e)} bulbs; your lights now have ${addressSpace()}. Edit it and save it again.</p>` : ''}
      <div class="actions"><button class="small" data-on="${esc(k)}">Turn on</button><button class="small ghost" data-edit="${esc(k)}">Edit</button>${role() !== 'viewer' ? `<button class="small ghost" data-pfold="${esc(k)}">Folder${e.folder ? ': ' + esc(e.folder) : ''}</button>` : ''}${shareable(e) ? `<button class="small ghost" data-share="${esc(k)}">Share</button>` : ''}<button class="small ghost danger" data-del="${esc(k)}">Delete</button></div>
    </div>`).join('') || '<p class="muted small">No patterns in this folder.</p>'}</div>`;
    const ps = $('#psort', body);
    if (ps) ps.onchange = () => { S.psort = ps.value; lsSet('psort', ps.value); VIEWS.patterns('mine'); };
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
    // 4.7.1: every controller on the account, chosen here; read over the home
    // network when the controller has an address (what it holds now), else
    // from what Trimlight's cloud last heard from it.
    let devs;
    try { devs = await loadDevices(); } catch (e) { body.innerHTML = `<p class="callout warn">${esc(e.message)}</p>`; return; }
    if (!devs.length) { body.innerHTML = '<p class="callout">No controller reported its pattern library.</p>'; return; }
    const d = devs.find(x => x.id === S.ptabDev) || devs.find(x => x.selected && x.effects) || devs.find(x => x.effects) || devs[0];
    S.ptabDev = d.id;
    const pick = devs.length > 1 ? `<label class="field" style="max-width:340px;margin-bottom:12px">Controller<select id="ptdev">${devs.map(x =>
      `<option value="${esc(x.id)}" ${x.id === d.id ? 'selected' : ''}>${esc(x.name || 'Controller')}${x.selected ? '' : ' (not run by this app)'}</option>`).join('')}</select></label>` : '';
    const bindPick = () => { const sel = $('#ptdev', body); if (sel) sel.onchange = () => { S.ptabDev = sel.value; VIEWS.patterns('controller'); }; };
    let effects = d.effects, from = 'cloud', why = '';
    if (role() === 'admin' && lanFor(d.id)) {
      body.innerHTML = `${pick}<p class="muted">Reading ${esc(d.name || 'the controller')} over your home network…</p>`;
      bindPick();         // another can be chosen while this one is read
      try {
        const r = await api('local' + (devs.length > 1 ? `?device=${encodeURIComponent(d.id)}` : ''));
        effects = r.patterns.map(p => ({ id: p.id, ...p.effect })); from = 'lan';
      } catch (e) { why = e.message; }
      if (S.ptab !== 'controller' || S.ptabDev !== d.id || !document.body.contains(body)) return;    // moved on meanwhile
    }
    S.ctrlEffects = effects || []; S.ctrlDev = d;
    const src = from === 'lan' ? `read just now from <b>${esc(d.name)}</b> over your home network`
      : `on <b>${esc(d.name)}</b>, as Trimlight’s cloud last heard${why ? ` (the home network didn’t answer: ${esc(why)})` : ''}`;
    const ours = (S.status && S.status.controlled) || devs.filter(x => x.selected).map(x => x.id);
    const tryNote = devs.length > 1 ? ` Try shows a pattern on ${ours.length === 1 && ours[0] === d.id ? 'this controller' : 'the controllers this app runs'}${ours.includes(d.id) ? '' : `, not on ${esc(d.name)}`}.` : '';
    body.innerHTML = `${pick}<p class="note" style="margin-bottom:12px">Patterns saved in the Trimlight app, ${src}. Add them to your patterns to use them in schedules.${tryNote}</p>
      ${effects && effects.length ? `<div class="cards">${effects.map((e, i) => { const def = fromController(e); return `<div class="card">
        <div class="title"><b>${esc(e.name)}</b></div>${def.colors ? strand(def.colors, def.counts) : strand(effectSwatches(def))}
        <p class="small muted">${esc(effectKind(def))}</p>
        <div class="actions"><button class="small" data-ctry="${i}">Try</button><button class="small ghost" data-cadd="${i}">Add to my patterns</button></div></div>`; }).join('')}</div>`
        : `<p class="callout">${effects ? `No patterns are saved on ${esc(d.name)}.` : `${esc(d.name)} didn’t report its pattern library${d.error ? `: ${esc(d.error)}` : ''}.`}</p>`}`;
    bindPick();
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
    if (d.new !== undefined) return go('create', {});      // 4.0.1: the attribute has no value, so test that it's there
    if (d.bgroup) { S.bgroup = d.bgroup; return VIEWS.patterns('builtin'); }
    if (d.on) return busy(b, () => api('action', { body: { action: 'on', effect: d.on } })).then(() => toast('Turned on until the next scheduled change')).catch(() => {});
    if (d.splitnew !== undefined) return splitDialog(null);
    if (d.pfolder !== undefined) { S.pfolder = d.pfolder; lsSet('pfolder', d.pfolder); return VIEWS.patterns('mine'); }
    if (d.pfold) return folderDialog(d.pfold);
    if (d.edit) {
      const def = S.settings.effects[d.edit];
      if (def.split) return splitDialog(d.edit);
      if (def.scene) { Object.assign(HV, { mode: 'scene', key: d.edit, name: def.label || '', cur: 0, groups: clone(def.scene.groups) }); return go('map'); }
      if (def.colors) return go('create', { key: d.edit });
      return builtinDialog(def, async out => { const n = clone(S.settings); n.effects[d.edit] = out; await saveSettings(n); VIEWS.patterns(); }, 'Edit pattern');
    }
    if (d.del) {
      const users = usedBy(d.del);
      if (users.length) return confirmBox("Can't delete yet", `This pattern is used by ${esc(users.join(', '))}. Change those first.`, 'OK');
      if (!await confirmBox('Delete pattern?', `“${esc(S.settings.effects[d.del].label || d.del)}” will be removed from your patterns. Patterns in the Trimlight app aren't affected.`, 'Delete', true)) return;
      const n = clone(S.settings); delete n.effects[d.del];
      if (Array.isArray(n.favorites)) n.favorites = n.favorites.filter(k => k !== d.del);
      return busy(b, () => saveSettings(n, 'Deleted')).then(() => VIEWS.patterns()).catch(() => {});
    }
    if (d.share) return shareDialog([d.share]);
    if (d.sharepick !== undefined) return sharePickDialog();
    if (d.shareopen !== undefined) return openShareDialog();
    if (d.fav) {
      const n = clone(S.settings), cur = favs();
      if (cur.includes(d.fav)) n.favorites = cur.filter(k => k !== d.fav);
      else if (cur.length >= MAX_FAVS) return toast(`Home holds ${MAX_FAVS} favorites. Unpin one first.`, true);
      else n.favorites = [...cur, d.fav];
      return busy(b, () => saveSettings(n, cur.includes(d.fav) ? 'Removed from Home' : 'Pinned to Home')).then(() => VIEWS.patterns()).catch(() => {});
    }
    if (d.comref !== undefined) { S.comRefresh = true; return VIEWS.patterns('community'); }
    if (d.comtry) return busy(b, async () => (await api('community/pattern?id=' + encodeURIComponent(d.comtry))).pattern)
      .then(def => tryDef(def, null)).catch(() => {});
    if (d.comadd) return busy(b, async () => addPattern((await api('community/pattern?id=' + encodeURIComponent(d.comadd))).pattern)).catch(() => {});
    if (d.ctry) {
      const def = fromController(S.ctrlEffects[+d.ctry]);
      // Review #2 (4.7.1): a pattern known only by its name is shown by name,
      // which only works on a controller that has it.
      const ours = (S.status && S.status.controlled) || [];
      if (def.saved && S.ctrlDev && ours.length && !(ours.length === 1 && ours[0] === S.ctrlDev.id)) {
        return toast(`“${def.label}” is shown by its name, so only ${S.ctrlDev.name} can show it, and this app runs ${ours.includes(S.ctrlDev.id) ? 'other controllers too' : 'other controllers'}.`, true);
      }
      return tryDef(def, b);
    }
    if (d.cadd) {
      const def = fromController(S.ctrlEffects[+d.cadd]);
      // 4.7.1: two controllers can each have a "Christmas"; the second is
      // added as "Christmas (Front)" so both stay easy to tell apart.
      const taken = new Set(Object.values(S.settings.effects || {}).map(e => String(e.label || '').trim().toLowerCase()));
      if (taken.has(def.label.trim().toLowerCase()) && S.ctrlDev) {
        const base = `${def.label} (${S.ctrlDev.name || 'controller'})`;
        let label = base, n = 2;
        while (taken.has(label.toLowerCase())) label = `${base} ${n++}`;      // review #3: added twice
        def.label = label;
      }
      return busy(b, () => addPattern(def)).catch(() => {});
    }
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
  if (S.aiOn === undefined) api('ai').then(r => { S.aiOn = r.configured; if (S.view === 'create') VIEWS.createRender && VIEWS.createRender(); }).catch(() => { S.aiOn = false; });
  const D = S.design, m = $('#main');
  const def = () => ({ label: D.label.trim() || 'Untitled', colors: D.segs.map(s => s.c), counts: D.segs.map(s => s.n), custom_mode: D.mode, speed: D.speed, brightness: D.brightness,
    ...(D.exact ? { exact_colors: true } : {}) });
  const gOn = () => !!(S.settings.color && S.settings.color.enabled);
  const render = () => {
    const s = D.segs[D.sel];
    m.innerHTML = `<div class="view"><div class="panel-head"><button class="ghost small" data-backpat aria-label="Back to Patterns">\u2039 Patterns</button><h2>${D.key ? 'Edit pattern' : 'Create a pattern'}</h2>
        ${D.key ? '<button class="ghost" data-newd>Start a new one</button>' : ''}</div>
      ${D.from && !D.key ? `<p class="callout">Started from the built-in effect <b>${esc(D.from)}</b>: same colors, closest animation (${esc(S.catalog.custom_modes[D.mode] || '')}). Built-in effects can't be recolored on the controller, so this is a new pattern that moves a little differently. Change the colors, try it, then save it.</p>` : ''}
      <div class="cols wide-left">
        <div class="stack">
          <div class="panel stack describe">
            <div class="row"><input type="text" id="tdesc" maxlength="200" class="grow" style="flex:1" value="${esc(D.desc || '')}"
                placeholder="Describe it: cyberpunk rainy night, slow candy cane twinkle…" aria-label="Describe a pattern">
              <button class="small primary" data-tmake>Make it</button>${D.desc ? '<button class="small ghost" data-tagain>Try another</button>' : ''}</div>
            <div class="row small">${S.aiOn ? `<label class="check"><input type="checkbox" id="tai" ${D.useAi ? 'checked' : ''}> Use AI (Claude, with your API key)</label>` : '<span class="muted">Built in, free and on this computer. For AI ideas, add an Anthropic API key in Setup › App › AI pattern ideas.</span>'}
              ${D.why ? `<span class="muted">${esc(D.why)}</span>` : ''}</div>
          </div>
          <div class="panel stack">
            <label class="field">Name<input type="text" id="dname" maxlength="40" placeholder="e.g. Candy cane" value="${esc(D.label)}"></label>
            ${D.paint ? `</div>${painterHtml(D)}<div hidden>` : ''}
            <div class="row" style="justify-content:space-between"><h3>Colors in order</h3>
              <span class="small ${D.segs.length > 30 ? 'callout warn' : 'muted'}">${D.segs.length} of 30 color slots</span></div>
            <div class="row"><button class="small ghost" data-onhouse>Preview on house</button><button class="small ghost" data-paintbulbs>Paint bulbs</button><button class="small ghost" data-paintzones>Paint by zone</button><button class="small ghost" data-combinezones>Combine patterns by zone</button><span class="note">Paint single bulbs, ranges or every Nth bulb, or color named sections of the house (zones from the House tab).</span></div>
            <div><p class="note">Each circle is one color; the number is how many bulbs it covers (up to 90). The sequence repeats along your roofline. Black is a dark color that moves with the pattern; ✕ zones bulbs off so they stay dark and are skipped by any movement, for example over a bedroom window.</p></div>
            <div class="segs">${D.segs.map((g, i) => `<button class="segbtn ${g.c === 'off' ? 'off' : ''}" data-seg="${i}" aria-pressed="${i === D.sel}" aria-label="${g.c === 'off' ? 'Zoned off' : 'Color ' + (i + 1)}, ${g.n} bulbs"
               style="${g.c === 'off' ? '' : `background:${g.c};`}color:${lum(g.c) > .55 ? '#111' : '#fff'}">${g.n}</button>`).join('')}
              ${D.segs.length < 30 ? '<button class="segbtn add" data-addseg aria-label="Add a color">+</button>' : ''}</div>
            ${s ? `<div class="stack" style="gap:10px"><h3>Selected color ${D.sel + 1} <span class="small muted" style="font-weight:normal">${esc(colorName(s.c))}</span></h3>
              <div class="palette">${S.catalog.palette.map(p => `<button data-color="${p.hex}" title="${esc(p.name)}" aria-label="${esc(p.name)}" style="background:${p.hex}"></button>`).join('')}
                <button data-color="off" class="off" title="Zone off (✕): these bulbs stay dark and don't move" aria-label="Zone off"></button>
                <label class="custom" title="Any color"><input type="color" id="cpick" value="${s.c === 'off' ? '#000000' : s.c.toLowerCase()}" aria-label="Pick any color"></label></div>
              <div class="row"><input type="text" id="cname" class="grow" style="flex:1;min-width:180px" list="cnamelist" autocomplete="off" spellcheck="false"
                  placeholder="Name or code: crimson, FF1493, 255 20 147" aria-label="Color by name or code">
                <button class="small" data-cname>Set</button><button class="small ghost" data-cnames>Named colors…</button></div>
              <datalist id="cnamelist">${S.catalog.names.map(c => `<option value="${esc(c.name)}">`).join('')}</datalist>
              ${(() => { const n = s.c !== 'off' && Colors.nearest(s.c, S.catalog.names); return n && n.exact && n.led.kind !== 'great' ? `<p class="small ${['white', 'pale', 'dimwhite'].includes(n.led.kind) ? 'warn' : 'muted'}">${esc(n.name)}: ${esc(n.led.text)}.</p>` : ''; })()}
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
          <div class="panel stack"><div class="panel-head"><h3>Preview</h3>${designDevPick()}</div><canvas class="preview" id="cv" height="160" aria-label="Animated preview of the pattern"></canvas>
            <p class="note" id="cvnote"></p>
            ${gOn() && !D.exact ? `<p class="note">Color correction is on (gamma ${Number(S.settings.color.gamma || GAMMA.def).toFixed(1)}): the lights get adjusted colors so they look like this preview. Change it in <a href="#color">Setup › Color correction</a>.</p>` : ''}</div>
          <div class="panel stack">
            <button data-try>Try on my lights</button>
            <label class="check"><input type="checkbox" id="alsoapp" ${lanAny() ? '' : 'disabled'}> Also save it on the controller${(S.status && (S.status.devices || []).length > 1) ? 's this app runs' : ''} (the Trimlight app's list), over the home network${lanAny() ? '' : ' <span class="small muted">(set its address in Setup \u203a Lights & controller \u203a Local mode)</span>'}</label>
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
    const cn = $('#cname'); if (cn) cn.onkeydown = e => { if (e.key === 'Enter') { e.preventDefault(); $('[data-cname]').click(); } };
    const ck = $('#ckelvin'); if (ck) ck.oninput = e => {
      S.kelvin = +e.target.value; D.segs[D.sel].c = Whites.kelvinHex(S.kelvin);
      const v = $('[data-kval]', ck.closest('.whites')); if (v) v.textContent = `${S.kelvin} K`;
      repaintSegs(); };
    const sn = $('#segn'); if (sn) sn.onchange = e => { D.segs[D.sel].n = Math.max(1, Math.min(90, +e.target.value || 1)); render(); };
    // While painting, the preview shows the painted pattern (if it fits).
    const painted = D.paint && PT.compress(D.paint.canvas);
    startPreview($('#cv'), painted && painted.length <= PT.MAX_SLOTS ? { ...D, segs: painted } : D, $('#cvnote'));
    const dd = $('#designdev');
    if (dd) dd.onchange = () => { S.designDev = dd.value; render(); };
    if (D.paint) painterDraw(D);
  };
  VIEWS.createRender = render;
  m.onkeydown = e => { if (e.key === 'Enter' && e.target.id === 'tdesc') { e.preventDefault(); const b = $('[data-tmake]'); if (b) b.click(); } };
  // "crimson", "FF1493", "255 20 147", or a pasted list of colors (3.20).
  const setFromText = text => {
    if (!text) { $('#cname').focus(); return toast('Type a color name or code, or paste a list of them.', true); }
    const r = Colors.parse(text, S.catalog.names);
    if (!r.colors.length) return toast(`“${r.unknown.slice(0, 3).join(' ')}” isn't a color name or code this app knows. Try Named colors…, or a code like FF1493.`, true);
    if (r.unknown.length) toast(`Skipped what wasn't a color: ${r.unknown.slice(0, 4).join(', ')}`, true);
    if (r.colors.length === 1) { D.segs[D.sel].c = r.colors[0]; return render(); }
    const room = 30 - D.segs.length;
    dialog(`<h2>${r.colors.length} colors</h2>
      <div class="stack" style="max-height:40vh;overflow:auto">${r.colors.map(c => `<div class="row" style="align-items:center"><i style="display:inline-block;width:22px;height:22px;border-radius:50%;background:${esc(c)};border:1px solid var(--line)"></i><span>${esc(colorName(c))}</span></div>`).join('')}</div>
      <p class="note">Each gets 3 bulbs to start; change them after. A pattern holds up to 30 colors.</p>`, async () => {
      D.segs = r.colors.slice(0, 30).map(c => ({ c, n: 3 })); D.sel = 0; render();
    }, { ok: 'Use them as the pattern', extraFoot: room > 0 ? `<button type="button" class="ghost" data-addafter>Add after color ${D.sel + 1}</button>` : '' });
    const ab = $('#dlg [data-addafter]');
    if (ab) ab.onclick = () => { D.segs.splice(D.sel + 1, 0, ...r.colors.slice(0, room).map(c => ({ c, n: 3 }))); $('#dlg').close(); render(); };
  };
  const repaintSegs = () => { const b = $(`[data-seg="${D.sel}"]`); if (b) { const g = D.segs[D.sel]; b.classList.toggle('off', g.c === 'off'); b.style.background = g.c === 'off' ? '' : g.c; b.style.color = lum(g.c) > .55 ? '#111' : '#fff'; } };
  m.onclick = async e => {
    const b = e.target.closest('button'); if (!b) return;
    const d = b.dataset;
    if (painterClick(D, d)) return;
    if (d.tmake !== undefined || d.tagain !== undefined) {
      const desc = ($('#tdesc').value || '').trim(); if (!desc) { $('#tdesc').focus(); return toast('Describe the pattern first.', true); }
      D.variant = d.tagain !== undefined && desc === D.desc ? (D.variant || 0) + 1 : 0;
      D.desc = desc; D.useAi = !!($('#tai') && $('#tai').checked);
      return busy(b, () => api('textpattern', { body: { prompt: desc, variant: D.variant, ai: D.useAi } })).then(p => {
        Object.assign(D, { label: p.label, segs: p.colors.map((c, i) => ({ c, n: p.counts[i] || 3 })), mode: p.custom_mode, speed: p.speed,
          brightness: p.brightness, sel: 0, why: (p.source === 'AI' ? 'AI: ' : '') + (p.why || ''), exact: false, paint: null });
        render(); toast('Here it is. Adjust it, preview it, then save.');
      }).catch(() => {});
    }
    if (d.paintbulbs !== undefined) { painterOpen(D); render(); }
    else if (d.onhouse !== undefined) {
      const x = def(); S.housePreview = { label: D.label || 'your design', def: effectDef(x) }; HV.mode = 'preview'; HV.effect = '_design';
      location.hash = '#map';
    }
    else if (d.seg) { D.sel = +d.seg; render(); }
    else if (d.addseg !== undefined) { D.segs.push({ c: D.segs[D.sel]?.c || '#FFFFFF', n: 3 }); D.sel = D.segs.length - 1; render(); }
    else if (d.color) { D.segs[D.sel].c = d.color; render(); }
    else if (d.cname !== undefined) setFromText(($('#cname').value || '').trim());
    else if (d.cnames !== undefined) namedColorsDialog(hex => { D.segs[D.sel].c = hex; render(); });
    else if (d.n) { const g = D.segs[D.sel]; g.n = Math.max(1, Math.min(90, g.n + +d.n)); render(); }
    else if (d.mv) { const j = D.sel + +d.mv; [D.segs[D.sel], D.segs[j]] = [D.segs[j], D.segs[D.sel]]; D.sel = j; render(); }
    else if (d.rm !== undefined) { D.segs.splice(D.sel, 1); D.sel = Math.max(0, D.sel - 1); render(); }
    else if (d.newd !== undefined) { VIEWS.create({ fresh: true }); }
    else if (d.backpat !== undefined) go('patterns');
    else if (d.paintzones !== undefined) zonePainter(D, render);
    else if (d.combinezones !== undefined) zoneCombiner(D, render);
    else if (d.try !== undefined) busy(b, () => api('action', { body: { action: 'try', effect: def() } })).then(() => toast('Showing on your lights for 15 minutes, then back to the schedule')).catch(() => {});
    else if (d.save !== undefined) busy(b, async () => {
      const label = D.label.trim(); if (!label) { $('#dname').focus(); throw new Error('Give the pattern a name first.'); }
      const n = clone(S.settings); n.effects = n.effects || {};
      const key = D.key || slug(label, n.effects);
      n.effects[key] = { ...def(), label };
      await saveSettings(n, D.key ? 'Changes saved' : `Saved “${label}”`);
      D.key = key;
      if ($('#alsoapp').checked) {
        const r = await api('device/save_effect', { body: { name: label.slice(0, 30), effect: def() } });
        const n = (r.saved || []).length, miss = r.missing || [];
        toast(`Saved “${label}” here and on ${n > 1 ? n + ' controllers' : 'the controller'}${miss.length ? `; not on ${miss.join(' and ')} (no home-network address yet)` : ''}`, !!miss.length);
      }
      render();
    }).catch(() => {});
  };
  m.onchange = e => { painterChange(D, e.target); };
  render();
};

/* Animated approximation of the controller's custom modes (the motion
   itself is HouseFX.colorsAt, shared with the house photo preview). */
function startPreview(cv, D, note) {
  const ctx = cv.getContext('2d'); const t0 = performance.now(); const view = S.view;
  const frame = now => {
    if (S.view !== view || !cv.isConnected) return;
    const dpr = window.devicePixelRatio || 1, W = cv.clientWidth * dpr, H = 160 * dpr;
    if (cv.width !== W) { cv.width = W; cv.height = H; }
    const N = Math.min(totalBulbs(), 300), gap = 15 * dpr, perRow = Math.max(10, Math.floor((W - gap) / gap)), rows = Math.ceil(N / perRow);
    const rowH = Math.min(26 * dpr, (H - 8 * dpr) / rows);
    note.textContent = `${totalBulbs()} bulbs${totalBulbs() > 300 ? ' (first 300 shown)' : ''}. The preview approximates how the controller animates; outlined bulbs are zoned off.`;
    const cols = HouseFX.colorsAt({ segs: D.segs, mode: D.mode, speed: D.speed, brightness: D.brightness }, N, (now - t0) / 1000);
    ctx.clearRect(0, 0, W, H);
    for (let i = 0; i < N; i++) {
      const { c, a, off } = cols[i];
      const x = gap / 2 + (i % perRow) * gap + gap / 2, y = 4 * dpr + Math.floor(i / perRow) * rowH + rowH / 2;
      const r = Math.min(5 * dpr, rowH / 3);
      if (off) { ctx.strokeStyle = 'rgba(160,160,190,.35)'; ctx.lineWidth = dpr; ctx.beginPath(); ctx.arc(x, y, r, 0, 7); ctx.stroke(); continue; }
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
  if (!pats.length || !pats[0]) throw new Error('Create a pattern first (Patterns › New pattern).');
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

/* 4.8: the controllers this app runs (for Controllers on a rule, the
   month's controller choice and Home's cards), and how a rule names them. */
function ctlList() { return ((S.status && S.status.devices) || []).filter(d => d.id).map(d => ({ id: d.id, name: d.name || 'Controller' })); }
function ctlNames(ids) {
  const all = ctlList();
  return (ids || []).map(id => (all.find(d => d.id === id) || {}).name).filter(Boolean);
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
    <label class="check"><input type="checkbox" name="usecurve" ${r.curve ? 'checked' : ''}> Night curve: change the whites and brightness through the night</label>
    <div class="stack" data-curve style="gap:6px" ${r.curve ? '' : 'hidden'}>${curveRows(r.curve || CURVE_PRESET)}</div>
    ${ctlList().length > 1 ? `<div class="stack" style="gap:8px"><span class="small" style="font-weight:650">Controllers</span>
      <div class="chips">${ctlList().map(d => `<label class="check" style="gap:6px"><input type="checkbox" name="ctl" value="${esc(d.id)}" ${!r.controllers || r.controllers.includes(d.id) ? 'checked' : ''}>${esc(d.name)}</label>`).join('')}</div>
      <p class="hint">A rule for some controllers only runs those; the others follow their own rules at the same time. Where rules overlap on a controller, the higher priority wins there.</p></div>` : ''}
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
    if (f.usecurve.checked) out.curve = readCurve(f);
    if (f.prio.value === 'custom') out.priority = +f.prio_n.value || 0; else if (f.prio.value !== '') out.priority = +f.prio.value;
    if (ctlList().length > 1) {
      // 4.8: all ticked is "all" (left out, so a controller added later runs it too);
      // controllers named before that this app doesn't run now are kept.
      const ticked = $$('input[name=ctl]:checked', f).map(x => x.value), here = ctlList().map(d => d.id);
      if (!ticked.length) throw new Error('Pick at least one controller.');
      const kept = (r.controllers || []).filter(id => !here.includes(id));
      if (ticked.length < here.length || kept.length) out.controllers = [...ticked, ...kept];
    } else if (r.controllers) out.controllers = r.controllers;
    const n = clone(S.settings); n.rules = n.rules || [];
    if (idx === undefined) n.rules.push(out); else n.rules[idx] = out;
    await saveSettings(n, 'Schedule saved'); VIEWS.schedule();
  }, { onOpen: f => {
    f.dataset.nightly = '1';
    wirePicker(f);
    f.addEventListener('click', e => {
      const b = e.target.closest('[data-cvadd],[data-cvdel],[data-cvpreset]'); if (!b) return;
      e.preventDefault();
      let pts = readCurve(f, true);
      if (b.dataset.cvadd !== undefined && pts.length < 6) pts.push({ at: '23:00', kelvin: null, level: 50 });
      if (b.dataset.cvdel !== undefined && pts.length > 2) pts.splice(+b.dataset.cvdel, 1);
      if (b.dataset.cvpreset !== undefined) pts = clone(CURVE_PRESET);
      $('[data-curve]', f).innerHTML = curveRows(pts);
    });
    f.addEventListener('change', e => {
      if (e.target.name === 'season') $$('[data-range]', f).forEach(x => x.hidden = e.target.value !== 'range');
      if (e.target.name === 'usebright') f.brightness.hidden = !e.target.checked;
      if (e.target.name === 'usecurve') $('[data-curve]', f).hidden = !e.target.checked;
      if (e.target.name === 'prio') f.prio_n.hidden = e.target.value !== 'custom';
    });
  } });
  return form;
}

/* Night curve rows (3.18): a time, a white (or the pattern's own) and a
   brightness for each point; the app moves between them in 10-minute steps. */
const CURVE_PRESET = [{ at: 'sunset', kelvin: 5000, level: 100 }, { at: '21:00', kelvin: 2700, level: 100 }, { at: '00:00', kelvin: 2700, level: 15 }];
const CURVE_K = [[null, 'Pattern’s own colors'], [6500, 'Daylight 6500 K'], [5000, 'Cool white 5000 K'], [4000, 'Neutral 4000 K'],
  [3000, 'Soft white 3000 K'], [2700, 'Warm white 2700 K'], [2200, 'Candlelight 2200 K']];
function curveRows(pts) {
  return `${pts.map((p, i) => `<div class="row" data-cvrow>
      <input type="text" name="cv_at" value="${esc(p.at)}" style="width:8.5em" aria-label="Time of point ${i + 1}" placeholder="21:00 or sunset">
      <select name="cv_k" style="width:auto" aria-label="White at point ${i + 1}">${CURVE_K.map(([k, l]) => `<option value="${k ?? ''}" ${(p.kelvin ?? null) === k ? 'selected' : ''}>${l}</option>`).join('')}</select>
      <select name="cv_l" style="width:auto" aria-label="Brightness at point ${i + 1}">${[100, 85, 70, 50, 35, 25, 15, 10, 5].map(n => `<option value="${n}" ${p.level === n ? 'selected' : ''}>${n}%</option>`).join('')}</select>
      ${pts.length > 2 ? `<button type="button" class="small ghost" data-cvdel="${i}" aria-label="Remove point ${i + 1}">✕</button>` : ''}</div>`).join('')}
    <div class="row"><button type="button" class="small ghost" data-cvadd ${pts.length >= 6 ? 'disabled' : ''}>Add a point</button>
      <button type="button" class="small ghost" data-cvpreset>Dusk to midnight glow</button></div>
    <p class="hint">Times like 21:00, 00:00, sunset or sunset + 30. Times before the rule starts count as the next morning. The lights change a little every 10 minutes between points. Whites follow the white you choose; other colors keep their color and only dim. The backup timer copies the opening look.</p>`;
}
function readCurve(f, loose) {
  const pts = $$('[data-cvrow]', f).map(row => ({ at: $('[name=cv_at]', row).value.trim(), kelvin: $('[name=cv_k]', row).value ? +$('[name=cv_k]', row).value : null,
    level: +$('[name=cv_l]', row).value }));
  if (!loose && pts.some(p => !p.at)) throw new Error('Give every night-curve point a time.');
  return pts;
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
    await saveSettings(n, 'Weather rule saved'); VIEWS.alerts();
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

// What the lights are doing, in words (Home's headline and the Schedule tab).
function stateLine(st) {
  const t = st.target, nextTxt = st.next_change ? `${st.next_change}${st.next_change_day ? ' ' + st.next_change_day : ''}` : null;
  let head = t.on ? 'The lights are on' : 'The lights are off', sub;
  if (t.reason === 'flash') { head = st.flash.label || 'Security flash'; sub = `${t.effect} until ${st.flash.until}, then back to normal.`; }
  else if (t.reason === 'alert') { head = 'Severe weather alert'; sub = `${t.source}: ${t.effect}${st.alert && st.alert.until ? ' until ' + st.alert.until : ''}, then back to normal. Dismissing it, or turning the lights on or off by hand, puts them back now.`; }
  else if (t.reason === 'music') { head = 'Music show'; sub = `${st.music.scheduled ? t.source + ': t' : 'T'}he controller\u2019s music mode runs the lights${st.music.until ? ' until ' + st.music.until : ' until the show is stopped'}. Stop it on the Music tab.`; }
  else if (t.parts) {
    // 4.8: the controllers show different things; one line for each
    const ctl = ctlList(), all = Object.entries(t.parts);
    if (t.on && all.some(([, p]) => !p.on)) head = 'Some lights are on';
    sub = all.map(([id, p]) => `${(ctl.find(d => d.id === id) || {}).name || 'Controller'}: ${p.on ? p.effect : 'off'}${p.manual ? ' (by hand)' : p.rule ? ` (${p.rule})` : ''}`).join(' \u00b7 ') + '.';
  }
  else if (t.reason === 'manual') sub = (t.on ? `${t.effect}, set by hand` : 'Turned off by hand') + (nextTxt ? `. The schedule takes over at ${nextTxt}.` : '.');
  else if (t.on && t.reason === 'weather') sub = `${t.source}: ${t.effect} until ${st.window.end}, instead of ${st.window.rule}.`;
  else if (t.on && st.window) sub = `${st.window.rule}: ${t.effect} until ${st.window.end}.` + (t.delegated ? ' The controller is running tonight from its own timer, so the lights go off on time even if this computer stops.' : '');
  else sub = nextTxt ? `Next on at ${nextTxt}.` : 'Nothing scheduled this week.';
  if (st.holiday && !t.on && !['flash', 'alert', 'music', 'manual'].includes(t.reason)) sub = `Today is ${st.holiday.name}: ${st.holiday.playlist} from ${st.holiday.on}. ` + sub;
  if (t.on && t.curve) sub += ` Night curve: ${t.curve.kelvin ? t.curve.kelvin + ' K, ' : ''}${t.curve.level}% brightness.`;
  if (!t.applied && !st.error) sub += ' Sending…';
  return { head, sub };
}

/* Schedule › Away mode (3.15): while you're away, each night's on and off
   times move by a different amount (the same night always by the same), so
   the house looks lived in rather than on a timer. */
const localIso = (d = new Date()) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
function awayActive() {
  const a = S.settings.away || {};
  return a.enabled && a.until && a.until >= localIso() ? a : null;
}
function awayPanel(box) {
  if (!box) return;
  const a = S.settings.away || {}, on = awayActive(), ro = role() === 'viewer';
  const d = new Date(); d.setDate(d.getDate() + 7);
  const def = localIso(d);
  box.innerHTML = `<h2>Away mode</h2>
    <p class="note">Going away? Each night the lights come on and go off a little earlier or later than usual, so the house looks lived in, not on a timer.</p>
    ${on ? `<p class="callout ok">On until <b>${esc(new Date(on.until + 'T12:00').toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' }))}</b>: times move by up to ${on.minutes} minutes. The calendar under Coming up shows the real times.</p>`
      : a.enabled ? '<p class="note">It ended on the date you came back.</p>' : ''}
    <div class="row">
      <label class="field" style="flex:1;min-width:140px">Back on<input type="date" id="awuntil" value="${esc(on ? on.until : def)}" ${ro ? 'disabled' : ''}></label>
      <label class="field" style="flex:1;min-width:140px">Move times by up to<select id="awmin" ${ro ? 'disabled' : ''}>${[10, 20, 30, 45, 60].map(n => `<option value="${n}" ${(a.minutes || 20) === n ? 'selected' : ''}>${n} minutes</option>`).join('')}</select></label></div>
    ${ro ? '' : `<div class="row"><button class="${on ? 'small' : 'primary small'}" data-awsave>${on ? 'Update' : 'Turn on away mode'}</button>${on ? '<button class="small ghost" data-awoff>Turn off (I\u2019m back)</button>' : ''}</div>`}`;
  box.onclick = e => {
    const b = e.target.closest('button'); if (!b) return;
    e.stopPropagation();
    const n = clone(S.settings);
    if (b.dataset.awoff !== undefined) n.away = { ...(n.away || {}), enabled: false };
    else if (b.dataset.awsave !== undefined) {
      const until = $('#awuntil').value;
      if (!until || until < localIso()) return toast('Pick the day you\u2019re back.', true);
      const seed = (n.away && n.away.seed) || Array.from(crypto.getRandomValues(new Uint8Array(8)), x => x.toString(16).padStart(2, '0')).join('');
      n.away = { enabled: true, until, minutes: +$('#awmin').value, seed };
    } else return;
    busy(b, () => saveSettings(n, n.away.enabled ? 'Away mode on' : 'Away mode off')).then(() => { awayPanel(box); upcomingPanel($('#upcbox')); }).catch(() => {});
  };
}

/* Schedule › Game-day lights (3.15): team colors on the nights your team
   plays. Game dates come from ESPN's public schedule (gameday.py). */
/* Schedule › Holidays (3.19): holidays found by the app every year, each
   with a playlist, instead of dated rules entered again each year. */
const COUNTRIES = [['CA', 'Canada'], ['GB', 'United Kingdom'], ['IE', 'Ireland'], ['AU', 'Australia'], ['NZ', 'New Zealand'],
  ['DE', 'Germany'], ['FR', 'France'], ['NL', 'Netherlands'], ['IT', 'Italy'], ['ES', 'Spain'], ['MX', 'Mexico'], ['BR', 'Brazil'],
  ['IN', 'India'], ['PH', 'Philippines'], ['JP', 'Japan'], ['ZA', 'South Africa'], ['US', 'United States (federal)']];
const HOLIDAY_NAMES = {};          // key -> name, filled by the Holidays panel (for "used by")
async function holidayPanel(box) {
  if (!box) return;
  let h; try { h = await api('holidays'); } catch (e) { box.innerHTML = `<h2>Holidays</h2><p class="muted small">${esc(e.message)}</p>`; return; }
  h.holidays.forEach(x => { HOLIDAY_NAMES[x.key] = x.name; });
  const s = S.settings, hc = s.holidays || { enabled: false, list: [] }, ro = role() === 'viewer';
  const effs = Object.entries(s.effects || {}), info = k => h.holidays.find(x => x.key === k) || {};
  const day = d => new Date(d + 'T12:00').toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' });
  const effSel = (attr, v, none) => `<select ${attr} ${ro ? 'disabled' : ''}>${none ? '<option value="">—</option>' : ''}${effs.map(([k, e]) => `<option value="${esc(k)}" ${v === k ? 'selected' : ''}>${esc(e.label || k)}</option>`).join('')}</select>`;
  const list = hc.list || [], picked = new Set(list.map(e => e.key)), year = new Date().getFullYear();
  const cc = hc.country || null;
  box.innerHTML = `<h2>Holidays</h2>
    <p class="note">Pick holidays and give each a playlist. The app works out the date every year, including the ones that move (Easter, Thanksgiving, Hanukkah, Diwali), loads the playlist that morning and runs it from the time you choose. Holidays outrank seasons (a Christmas season rule) and the everyday schedule; game days outrank holidays.</p>
    <label class="check"><input type="checkbox" id="holon" ${hc.enabled ? 'checked' : ''} ${ro ? 'disabled' : ''}> <b>Use holiday lights</b></label>
    ${h.today ? `<p class="callout ok small">Today is <b>${esc(h.today.name)}</b>: ${esc(h.today.playlist)} from ${esc(h.today.on)}.</p>` : ''}
    ${list.map((e, i) => { const inf = info(e.key), nx = inf.next || [], my = nx[0] ? nx[0].slice(0, 4) : String(year);
      const mv = (e.moved || {})[my]; return `<div class="panel stack" style="background:var(--surface2);padding:12px">
      <div class="panel-head"><b>${esc(inf.name || e.key)}</b><span class="small muted">${esc(inf.group || '')}${inf.nights > 1 ? ` · ${inf.nights} nights` : ''}</span>${ro ? '' : `<button class="small ghost danger" data-holdel="${i}">Remove</button>`}</div>
      <div class="row">${[0, 1, 2].map(j => `<label class="field" style="flex:1;min-width:130px">${j ? 'Then' : 'Pattern'}${effSel(`data-holeff="${i}" data-j="${j}"`, e.effects[j], j > 0)}</label>`).join('')}</div>
      <div class="row">${e.effects.length > 1 ? `<label class="field" style="width:9em">Each shows (min)<input type="number" min="1" max="240" data-holrot="${i}" value="${e.rotate || 15}" ${ro ? 'disabled' : ''}></label>` : ''}
        <label class="field" style="width:7em">On<input type="text" data-holon="${i}" value="${esc(e.on || 'sunset')}" ${ro ? 'disabled' : ''}></label>
        <label class="field" style="width:7em">Off<input type="text" data-holoff="${i}" value="${esc(e.off || '23:00')}" ${ro ? 'disabled' : ''}></label>
        <label class="field" style="width:7em">Days before<input type="number" min="0" max="45" data-holbef="${i}" value="${e.before || 0}" ${ro ? 'disabled' : ''}></label>
        <label class="field" style="width:7em">Days after<input type="number" min="0" max="45" data-holaft="${i}" value="${e.after || 0}" ${ro ? 'disabled' : ''}></label></div>
      <p class="small ${inf.missing ? 'warn' : 'muted'}">${nx.length ? (inf.eve ? 'First night: ' : 'Next: ') + nx.map((x, k) => esc(day(x)) + (e.before && inf.starts && inf.starts[k] !== x ? ` (lights from ${esc(day(inf.starts[k]))})` : '')).join(', ') : inf.known_until ? `Dates are known through ${inf.known_until}; a newer EaveLuxOS has more.` : ''}
        ${inf.approximate ? ' The date depends on the new moon being seen, so it can be a day off where you live.' : ''}${inf.eve ? ' It begins at sundown, so the lights start the evening before.' : ''}</p>
      ${ro ? '' : `<label class="row small">Move ${my}\u2019s ${inf.eve ? 'first night' : 'date'} to <input type="date" data-holmove="${i}" data-year="${my}" value="${esc(mv || nx[0] || '')}" style="width:auto">${mv ? ` <button class="small ghost" data-holunmove="${i}" data-year="${my}">Back to ${esc(day(nx[0] || mv))}</button>` : ''}</label>`}
    </div>`; }).join('')}
    ${ro ? '' : `<div class="row"><select id="holpick"><option value="">Add a holiday\u2026</option>${h.groups.map(g => `<optgroup label="${esc(g)}">${h.holidays.filter(x => x.group === g && !picked.has(x.key)).map(x => `<option value="${esc(x.key)}">${esc(x.name)}${x.next[0] ? ' (' + esc(day(x.next[0])) + ')' : ''}</option>`).join('')}</optgroup>`).join('')}</select>
      <button class="small" data-holadd>Add</button></div>
      <p class="note">A new holiday comes with ready-made themed patterns (added to your patterns, yours to change). Times work like rules: sunset, sunset + 30, 18:00.</p>`}
    <h3>Another country's public holidays</h3>
    <p class="note">Official public holidays from the free Nager.Date service, checked weekly from the app computer (only the country code is sent). All of them share one playlist, below the holidays above.</p>
    <div class="row"><label class="field" style="flex:1;min-width:160px">Country<select id="holcc" ${ro ? 'disabled' : ''}><option value="">None</option>${COUNTRIES.map(([c, n]) => `<option value="${c}" ${cc && cc.code === c ? 'selected' : ''}>${n}</option>`).join('')}${cc && !COUNTRIES.some(([c]) => c === cc.code) ? `<option value="${esc(cc.code)}" selected>${esc(cc.code)}</option>` : ''}<option value="other">Other (2-letter code)\u2026</option></select></label>
      ${cc ? `<label class="field" style="flex:1;min-width:150px">Pattern${effSel('id="holcceff"', (cc.effects || [])[0])}</label>` : ''}
      ${cc && !ro ? '<button class="small ghost" data-holfetch style="align-self:flex-end">Check now</button>' : ''}</div>
    ${cc && h.country ? `<p class="small ${h.country.error ? 'warn' : 'muted'}">${h.country.error ? esc(h.country.error) : h.country.next.length ? 'Next: ' + h.country.next.map(x => `${esc(x.name)} (${esc(day(x.date))})`).join(', ') : h.country.fetched ? 'No more public holidays this year.' : 'Not checked yet.'}</p>` : ''}`;
  const save = (n, msg) => saveSettings(n, msg).then(() => holidayPanel(box));
  const edit = fn => {
    const n = clone(S.settings); n.holidays = clone(n.holidays || { enabled: true, list: [] }); n.holidays.list = n.holidays.list || []; fn(n);
    // Dates moved for years gone by are dropped, so they never pile up (3.19.1).
    n.holidays.list.forEach(x => { if (x.moved) { x.moved = Object.fromEntries(Object.entries(x.moved).filter(([y]) => +y >= year - 1)); if (!Object.keys(x.moved).length) delete x.moved; } });
    return n;
  };
  box.onchange = e => {
    const t = e.target, ds = t.dataset;
    if (t.id === 'holon') return busy(null, () => save(edit(n => { n.holidays.enabled = t.checked; }), t.checked ? 'Holiday lights on' : 'Holiday lights off')).catch(() => holidayPanel(box));
    if (t.id === 'holcc') {
      let code = t.value;
      if (code === 'other') { code = (prompt('Two-letter country code (ISO 3166), like CA or GB:') || '').trim().toUpperCase(); if (!/^[A-Z]{2}$/.test(code)) return holidayPanel(box); }
      return busy(null, async () => {
        await save(edit(n => { n.holidays.enabled = true; n.holidays.country = code ? { ...(n.holidays.country || {}), code, effects: (n.holidays.country || {}).effects || [Object.keys(n.effects)[0]] } : null; }), code ? 'Saved' : 'Removed');
        if (code) await api('holidays/refresh', { body: { code } }).catch(() => {});
        holidayPanel(box);
      }).catch(() => holidayPanel(box));
    }
    if (t.id === 'holcceff') return busy(null, () => save(edit(n => { n.holidays.country.effects = [t.value]; }), 'Saved')).catch(() => holidayPanel(box));
    const i = +(ds.holeff ?? ds.holrot ?? ds.holon ?? ds.holoff ?? ds.holbef ?? ds.holaft ?? ds.holmove ?? -1);
    if (i < 0) return;
    const n = edit(n => {
      const x = n.holidays.list[i];
      if (ds.holeff !== undefined) { const ef = [...x.effects]; ef[+ds.j] = t.value; x.effects = ef.filter(Boolean); if (!x.effects.length) x.effects = [t.value || Object.keys(n.effects)[0]]; }
      if (ds.holrot !== undefined) x.rotate = Math.max(1, Math.min(240, +t.value || 15));
      if (ds.holon !== undefined) x.on = t.value.trim() || 'sunset';
      if (ds.holoff !== undefined) x.off = t.value.trim() || '23:00';
      if (ds.holbef !== undefined) x.before = Math.max(0, Math.min(45, +t.value || 0));
      if (ds.holaft !== undefined) x.after = Math.max(0, Math.min(45, +t.value || 0));
      if (ds.holmove !== undefined) { x.moved = { ...(x.moved || {}) }; if (t.value) x.moved[ds.year] = t.value; else delete x.moved[ds.year]; }
    });
    busy(null, () => save(n, 'Saved')).catch(() => holidayPanel(box));
  };
  box.onclick = e => {
    const b = e.target.closest('button'); if (!b) return; e.stopPropagation();
    if (b.dataset.holdel !== undefined) return busy(b, () => save(edit(n => { n.holidays.list.splice(+b.dataset.holdel, 1); }), 'Removed')).catch(() => {});
    if (b.dataset.holunmove !== undefined) return busy(b, () => save(edit(n => { const x = n.holidays.list[+b.dataset.holunmove]; x.moved = { ...(x.moved || {}) }; delete x.moved[b.dataset.year]; }), 'Saved')).catch(() => {});
    if (b.dataset.holfetch !== undefined) return busy(b, () => api('holidays/refresh', { body: { code: cc.code } })).then(() => { toast('Public holidays checked'); holidayPanel(box); }).catch(() => holidayPanel(box));
    if (b.dataset.holadd === undefined) return;
    const key = $('#holpick').value; if (!key) return toast('Choose a holiday.', true);
    const inf = info(key);
    const n = edit(n => {
      n.holidays.enabled = true;
      // Its themed patterns, added to the user's own (theirs to change).
      const keys = (inf.theme || []).map((p, j) => { const k = `hol_${key}${j ? '_' + (j + 1) : ''}`; if (!n.effects[k]) n.effects[k] = clone(p); return k; });
      n.holidays.list.push({ key, effects: keys.length ? keys : [Object.keys(n.effects)[0]], rotate: 15, before: 0, after: 0,
                             on: 'sunset', off: key === 'new_years_eve' ? '00:30' : '23:00' });
    });
    busy(b, () => save(n, `${inf.name} added`)).catch(() => {});
  };
}

/* Schedule › Game-day lights (4.9): a sound when this team scores, played
   through the speakers of the computer EaveLuxOS runs on. */
function soundRow(t, i, ro) {
  const snd = t.sound;
  if (!snd) return ro ? '' : `<div class="stack soundrow" style="gap:6px"><label class="field small">Sound when they score (optional)
      <input type="file" accept=".mp3,.wav,audio/mpeg,audio/wav" data-gdsndfile="${i}"></label>
    <p class="small muted" style="margin:0">An MP3 or WAV file you have, up to 15 MB, such as a goal horn or a fight song. You choose the part that plays (up to 30 seconds) on the computer EaveLuxOS runs on.</p></div>`;
  const len = snd.length ? ` (${Math.round(snd.length)} s long)` : '';
  return `<div class="stack soundrow" style="gap:6px;border-top:1px solid var(--line);padding-top:8px">
    <label class="check small"><input type="checkbox" data-gdsndon="${i}" ${snd.on !== false ? 'checked' : ''} ${ro ? 'disabled' : ''}> <span>Play the sound: <b>${esc(snd.name || 'sound file')}</b>${esc(len)}</span></label>
    <div class="row" style="gap:8px">
      <label class="row small" style="gap:6px">Start at<input type="number" min="0" max="3600" step="0.5" value="${esc(snd.start ?? 0)}" data-gdsndstart="${i}" style="width:6em" ${ro ? 'disabled' : ''}> s</label>
      <label class="row small" style="gap:6px">Play for<input type="number" min="1" max="30" step="1" value="${esc(snd.seconds ?? 20)}" data-gdsndsecs="${i}" style="width:5em" ${ro ? 'disabled' : ''}> s</label></div>
    <div class="row" style="gap:6px"><button class="small" data-gdsndhere="${i}">Listen here</button>
      ${ro ? '' : `<button class="small ghost" data-gdsndpc="${i}">Play on the app computer</button><button class="small ghost danger" data-gdsnddel="${i}">Remove sound</button>`}</div>
    <p class="small muted" style="margin:0">Plays with the celebration, through the speakers of the computer EaveLuxOS runs on; turn its volume up.</p></div>`;
}
async function gamePanel(box) {
  if (!box) return;
  let g; try { g = await api('gameday'); } catch (e) { box.innerHTML = `<h2>Game-day lights</h2><p class="muted small">${esc(e.message)}</p>`; return; }
  const s = S.settings, gd = s.gameday || { enabled: false, teams: [] }, ro = role() === 'viewer';
  const effs = Object.entries(s.effects || {});
  const info = k => g.teams.find(t => t.key === k) || {};
  const day = d => new Date(d + 'T12:00').toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' });
  // 4.3.5: two separate switches. Settings from before had one for both.
  const party = gd.celebrate_enabled ?? !!gd.enabled;
  box.innerHTML = `<h2>Game-day lights</h2>
    <p class="note">Two separate things, each with its own switch. Game dates and scores come from ESPN\u2019s public schedule; if it can\u2019t be reached, your normal schedule runs.</p>
    <label class="check"><input type="checkbox" id="gdon" ${gd.enabled ? 'checked' : ''} ${ro ? 'disabled' : ''}> <span><b>Use game-day lights</b><br><span class="small muted">Your team\u2019s colors on the nights they play, instead of the usual pattern (even during a holiday season).</span></span></label>
    <label class="check"><input type="checkbox" id="gdparty" ${party ? 'checked' : ''} ${ro ? 'disabled' : ''}> <span><b>Celebrate scores</b><br><span class="small muted">Flash the team\u2019s colors for a few seconds when they score, then back to what was on. Works whether or not game-day lights are on; tick each team below.</span></span></label>
    ${(gd.teams || []).map((t, i) => { const inf = info(`${t.league}-${t.team}`); return `<div class="panel stack" style="background:var(--surface2);padding:12px">
      <div class="panel-head"><b>${esc(t.name || t.team.toUpperCase())}</b><span class="small muted">${esc((g.leagues[t.league] || t.league))}</span>${ro ? '' : `${t.celebrate ? `<button class="small ghost" data-gdauto="${i}">Make it an automation</button>` : ''}<button class="small ghost danger" data-gddel="${i}">Remove</button>`}</div>
      <div class="row"><label class="field" style="flex:2;min-width:150px">Team colors (pattern)<select data-gdeff="${i}" ${ro ? 'disabled' : ''}>${effs.map(([k, e]) => `<option value="${esc(k)}" ${t.effect === k ? 'selected' : ''}>${esc(e.label || k)}</option>`).join('')}</select></label>
        <label class="field" style="flex:1;min-width:110px">On<input type="text" data-gdon="${i}" value="${esc(t.on || 'sunset')}" ${ro ? 'disabled' : ''}></label>
        <label class="field" style="flex:1;min-width:110px">Off<input type="text" data-gdoff="${i}" value="${esc(t.off || '23:00')}" ${ro ? 'disabled' : ''}></label></div>
      <p class="small muted" style="margin:0">On and Off are for game-day lights. ${gd.enabled ? '' : '<b>Game-day lights are off.</b>'}</p>
      <label class="check small"><input type="checkbox" data-gdcel="${i}" ${t.celebrate ? 'checked' : ''} ${ro ? 'disabled' : ''}> Celebrate this team\u2019s scores${party ? '' : ' <span class="muted">(Celebrate scores is off above)</span>'}${t.league === 'nfl' ? ' (field goals and touchdowns)' : t.league === 'nba' ? ' (3-pointers; baskets are too frequent)' : ''}</label>
      ${t.celebrate ? soundRow(t, i, ro) : ''}
      ${inf.live && inf.live.state === 'missing' ? `<p class="small warn">Not on ESPN’s scoreboard today under “${esc(inf.live.code)}”, so scores can’t be followed. Check the team code (the letters in the team’s address on espn.com).</p>`
        : inf.live ? `<p class="small"><b>${inf.live.state === 'in' ? 'Live' : inf.live.state === 'post' ? 'Final' : 'Today'}</b>: ${esc(t.name || t.team.toUpperCase())} ${inf.live.score}${inf.live.vs ? ` – ${esc(inf.live.vs)} ${inf.live.them ?? ''}` : ''} ${inf.live.detail ? '· ' + esc(inf.live.detail) : ''}</p>` : ''}
      <p class="small ${inf.error && !inf.known ? 'warn' : 'muted'}">${inf.next && inf.next.length ? 'Next games: ' + inf.next.map(day).map(esc).join(', ') : inf.error ? 'Schedule not available yet: ' + esc(inf.error) : inf.known ? 'No more games this season.' : !gd.enabled && !(party && t.celebrate) ? 'Not checked while this team has neither game-day lights nor celebrations on.' : 'Schedule not checked yet (within a minute of turning it on).'}</p></div>`; }).join('')}
    ${party && (gd.teams || []).some(t => t.celebrate) ? `<div class="row"><label class="row small">Celebrate for<select id="gdsec" style="width:auto" ${ro ? 'disabled' : ''}>${[10, 15, 20, 30, 45, 60].map(n => `<option value="${n}" ${(gd.celebrate_seconds || 15) === n ? 'selected' : ''}>${n} seconds</option>`).join('')}</select></label>
      <label class="check small"><input type="checkbox" id="gdonly" ${gd.celebrate_only_when_on !== false ? 'checked' : ''} ${ro ? 'disabled' : ''}> Only while the lights are on</label></div>
      <p class="note">Live scores come from ESPN’s free scoreboard, checked every 20 seconds during the game. It runs a little behind live TV, so the lights celebrate shortly after you see the score.</p>` : ''}
    ${ro ? '' : `<div class="row"><select id="gdpick"><option value="">Add a team\u2026</option>${g.presets.map(p => `<option value="${esc(p.id)}">${esc(p.name)} (${esc(g.leagues[p.league])})</option>`).join('')}<option value="other">Another team\u2026</option></select>
      <span id="gdother" hidden><select id="gdleague">${Object.entries(g.leagues).map(([k, l]) => `<option value="${k}">${l}</option>`).join('')}</select>
        <input type="text" id="gdteam" placeholder="ESPN team code, e.g. nyg" maxlength="5" style="width:12em"></span>
      <button class="small" data-gdadd>Add</button>
      ${(gd.teams || []).length && isAdmin() ? '<button class="small ghost" data-gdrefresh>Check schedules now</button>' : ''}</div>`}
    ${(gd.teams || []).length ? '<p class="note">Times work like rules: sunset, sunset + 30, 18:00. The Month view under Coming up shows game nights.</p>' : ''}`;
  const save = (n, msg) => saveSettings(n, msg).then(() => gamePanel(box));
  box.onchange = e => {
    const t = e.target, ds = t.dataset, n = clone(S.settings);
    n.gameday = n.gameday || { enabled: false, teams: [] };
    if (ds.gdsndfile !== undefined) {
      // 4.9: keep the file on the app computer, then say which part plays
      const team = n.gameday.teams[+ds.gdsndfile], f = t.files && t.files[0];
      if (!f) return;
      return busy(null, async () => {
        const r = await fetch(`api/sound/upload?team=${encodeURIComponent(team.league + '-' + team.team)}&name=${encodeURIComponent(f.name)}`,
          { method: 'POST', cache: 'no-store', body: f, headers: { 'X-Requested-With': 'eaveluxos', 'Content-Type': 'application/octet-stream', ...authHeaders() } });
        const j = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(j.error || `Upload failed (${r.status}).`);
        team.sound = { name: j.name, kind: j.kind, length: j.length, start: 0, seconds: Math.min(20, Math.max(1, Math.floor(j.length))), on: true };
        await save(n, `Sound saved for ${team.name}`);
      }).catch(err => { toast(err.message, true); t.value = ''; });
    }
    if (ds.gdsndstart !== undefined || ds.gdsndsecs !== undefined || ds.gdsndon !== undefined) {
      const team = n.gameday.teams[+(ds.gdsndstart ?? ds.gdsndsecs ?? ds.gdsndon)];
      if (!team || !team.sound) return;
      if (ds.gdsndon !== undefined) team.sound.on = t.checked;
      if (ds.gdsndstart !== undefined) team.sound.start = Math.max(0, Math.min(3600, +t.value || 0));
      if (ds.gdsndsecs !== undefined) team.sound.seconds = Math.max(1, Math.min(30, Math.round(+t.value) || 20));
      return busy(null, () => save(n)).catch(() => {});
    }
    if (t.id === 'gdon') {
      if (n.gameday.celebrate_enabled === undefined) n.gameday.celebrate_enabled = !!n.gameday.enabled;   // keep celebrations as they were
      n.gameday.enabled = t.checked; return busy(null, () => save(n, t.checked ? 'Game-day lights on' : 'Game-day lights off')).catch(() => { t.checked = !t.checked; });
    }
    if (t.id === 'gdparty') { n.gameday.celebrate_enabled = t.checked; return busy(null, () => save(n, t.checked ? 'Score celebrations on' : 'Score celebrations off')).catch(() => { t.checked = !t.checked; }); }
    if (t.id === 'gdpick') { $('#gdother').hidden = t.value !== 'other'; return; }
    if (t.id === 'gdsec') { n.gameday.celebrate_seconds = +t.value; return busy(null, () => save(n)).catch(() => {}); }
    if (t.id === 'gdonly') { n.gameday.celebrate_only_when_on = t.checked; return busy(null, () => save(n)).catch(() => {}); }
    if (ds.gdcel !== undefined) { n.gameday.teams[+ds.gdcel].celebrate = t.checked;
      if (t.checked && n.gameday.celebrate_enabled === undefined) n.gameday.celebrate_enabled = true;
      return busy(null, () => save(n, t.checked ? `Celebrations on for ${n.gameday.teams[+ds.gdcel].name}` : 'Celebrations off for that team')).catch(() => { t.checked = !t.checked; }); }
    const i = ds.gdeff ?? ds.gdon ?? ds.gdoff; if (i === undefined) return;
    const team = n.gameday.teams[+i];
    if (ds.gdeff !== undefined) team.effect = t.value;
    if (ds.gdon !== undefined) team.on = t.value.trim() || 'sunset';
    if (ds.gdoff !== undefined) team.off = t.value.trim() || '23:00';
    busy(null, () => save(n)).catch(() => {});
  };
  box.onclick = e => {
    const b = e.target.closest('button'); if (!b) return;
    e.stopPropagation();
    const n = clone(S.settings);
    n.gameday = n.gameday || { enabled: false, teams: [] };
    if (b.dataset.gdauto !== undefined) {
      // 4.11: this team's score celebration as an automation, to add conditions
      const tm = n.gameday.teams[+b.dataset.gdauto], key = `${tm.league}-${String(tm.team).toLowerCase()}`;
      const then = [{ type: 'flash', effect: tm.effect, seconds: n.gameday.celebrate_seconds || 15 }];
      if (tm.sound && tm.sound.on !== false) then.push({ type: 'sound', team: key });
      n.automations = n.automations || [];
      n.automations.push({ id: 'a' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6), name: `${tm.name || tm.team.toUpperCase()} score`,
        enabled: true, priority: 100, cooldown: 30, beats_manual: false, when: { type: 'score', team: key },
        if: n.gameday.celebrate_only_when_on === false ? [] : [{ type: 'lights', on: true }], then });
      tm.celebrate = false;
      return busy(b, () => save(n, `${tm.name || 'The team'}: now an automation under Alerts \u203a Automations`)).catch(() => {});
    }
    if (b.dataset.gddel !== undefined) { n.gameday.teams.splice(+b.dataset.gddel, 1); return busy(b, () => save(n, 'Removed')).catch(() => {}); }
    const sk = x => { const tm = n.gameday.teams[+x]; return tm ? `${tm.league}-${tm.team}` : ''; };
    if (b.dataset.gdsndhere !== undefined) return busy(b, async () => {
      // Listen in this browser: the part that plays, as the app computer cuts it.
      const r = await fetch('api/sound/clip?team=' + encodeURIComponent(sk(b.dataset.gdsndhere)), { cache: 'no-store', headers: { 'X-Requested-With': 'eaveluxos', ...authHeaders() } });
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || `Couldn't get the sound (${r.status}).`);
      if (S.soundUrl) URL.revokeObjectURL(S.soundUrl);
      S.soundUrl = URL.createObjectURL(await r.blob());
      if (S.soundEl) S.soundEl.pause();
      S.soundEl = new Audio(S.soundUrl);
      await S.soundEl.play();
    }).catch(err => toast(err.message, true));
    if (b.dataset.gdsndpc !== undefined) return busy(b, () => api('sound/test', { body: { team: sk(b.dataset.gdsndpc) } }))
      .then(r => toast(r.played ? 'Playing on the app computer\u2019s speakers' : 'It couldn\u2019t be played there; see Activity.', !r.played)).catch(() => {});
    if (b.dataset.gdsnddel !== undefined) {
      const tm = n.gameday.teams[+b.dataset.gdsnddel];
      return busy(b, async () => { await api('sound/delete', { body: { team: sk(b.dataset.gdsnddel) } }); delete tm.sound; await save(n, 'Sound removed'); }).catch(() => {});
    }
    if (b.dataset.gdrefresh !== undefined) return busy(b, () => api('gameday/refresh', { body: {} })).then(() => {
      toast('Checking the schedules\u2026');
      setTimeout(() => { if (S.view === 'schedule') gamePanel(box); }, 8000);
    }).catch(() => {});
    if (b.dataset.gdadd === undefined) return;
    const pick = $('#gdpick').value; if (!pick) return toast('Choose a team.', true);
    let team;
    if (pick === 'other') {
      const code = $('#gdteam').value.trim().toLowerCase();
      if (!/^[a-z]{2,5}$/.test(code)) return toast('Enter ESPN\u2019s short team code, like nyg.', true);
      team = { league: $('#gdleague').value, team: code, name: `${code.toUpperCase()} (${g.leagues[$('#gdleague').value]})` };
    } else {
      const p = g.presets.find(x => x.id === pick);
      team = { league: p.league, team: p.team, name: p.name };
      const key = `team_${p.id.replace('-', '_')}`;
      if (!n.effects[key]) n.effects[key] = { label: `${p.name} colors`, colors: p.colors, counts: p.colors.map(() => 4), custom_mode: 0, brightness: 220 };
      team.effect = key;
    }
    if ((n.gameday.teams || []).some(t => t.league === team.league && t.team === team.team)) return toast('That team is already on the list.', true);
    if ((n.gameday.teams || []).length >= 6) return toast('Up to 6 teams.', true);
    team.effect = team.effect || Object.keys(n.effects)[0];
    team.on = 'sunset'; team.off = '23:00';
    n.gameday.teams = [...(n.gameday.teams || []), team];
    if (!n.gameday.enabled && !(n.gameday.celebrate_enabled ?? false)) n.gameday.enabled = true;   // a first team: game-day lights on
    busy(b, () => save(n, `${team.name} added`)).catch(() => {});
  };
}

/* Music › Mood follow (3.18, beta): this browser listens through the app
   computer's microphone and switches between three patterns as the music
   gets calmer or livelier. Browsers only allow a microphone on a secure page
   or on the computer itself (localhost), so it runs on the app computer. */
const MOOD = { on: false, level: null, stream: null, ctx: null, timer: null, node: null, win: null, rep: null, prevSpec: null, meter: 0, err: '', tab: '' };
function moodAvailable() { return !!(window.isSecureContext && navigator.mediaDevices && navigator.mediaDevices.getUserMedia); }
async function moodStart() {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false } });
  const ctx = new (window.AudioContext || window.webkitAudioContext)(), an = ctx.createAnalyser(), src = ctx.createMediaStreamSource(stream);
  an.fftSize = 2048; src.connect(an);
  if (ctx.state === 'suspended') await ctx.resume().catch(() => {});     // some browsers start it paused
  const td = new Float32Array(an.fftSize), fd = new Float32Array(an.frequencyBinCount);
  Object.assign(MOOD, { on: true, stream, ctx, win: new Mood.Window(), rep: new Mood.Reporter(), prevSpec: null, level: null, err: '',
                        tab: MOOD.tab || Math.random().toString(36).slice(2, 12) });
  let last = performance.now();
  const sample = () => {
    if (!MOOD.on) return;
    const now = performance.now(), dt = Math.min(250, Math.max(1, now - last)); last = now;
    an.getFloatTimeDomainData(td); an.getFloatFrequencyData(fd);
    let sum = 0; for (const v of td) sum += v * v;
    const rms = Math.sqrt(sum / td.length);
    let flux = 0; const mag = Array.from(fd, db => Math.pow(10, db / 20));
    if (MOOD.prevSpec) for (let i = 0; i < mag.length; i++) flux += Math.max(0, mag[i] - MOOD.prevSpec[i]);
    MOOD.prevSpec = mag; MOOD.win.add(rms, flux / mag.length, dt); MOOD.meter = rms;
    const mt = $('#moodmeter'); if (mt) mt.style.width = Math.min(100, rms / 0.2 * 100) + '%';
    const lv = MOOD.rep.step(now, MOOD.win);             // every 10 seconds by the clock (3.18.2)
    if (!lv) return;
    MOOD.level = lv;
    api('mood', { body: { level: lv, tab: MOOD.tab } }).then(r => { MOOD.err = ''; MOOD.pattern = r.pattern || ''; MOOD.waiting = !!r.waiting; moodPanel($('#moodbox')); })
      .catch(e => { MOOD.err = e.message; moodPanel($('#moodbox')); });
  };
  // The audio thread keeps calling a processor node in a background tab,
  // where timers are slowed (3.18.2); it outputs silence. The timer stays
  // as a backup for browsers without one.
  if (ctx.createScriptProcessor) {
    let acc = 0;
    const node = ctx.createScriptProcessor(4096, 1, 1), mute = ctx.createGain();
    mute.gain.value = 0; src.connect(node); node.connect(mute); mute.connect(ctx.destination);
    node.onaudioprocess = ev => { acc += ev.inputBuffer.duration * 1000; if (acc >= 100) { acc = 0; sample(); } };
    MOOD.node = node;
  }
  MOOD.timer = setInterval(() => { if (!MOOD.node || performance.now() - last > 1000) sample(); }, 100);
}
function moodStop(tell = true) {
  clearInterval(MOOD.timer);
  if (MOOD.node) MOOD.node.onaudioprocess = null;
  if (MOOD.stream) MOOD.stream.getTracks().forEach(t => t.stop());
  if (MOOD.ctx) MOOD.ctx.close().catch(() => {});
  Object.assign(MOOD, { on: false, stream: null, ctx: null, timer: null, node: null, level: null, waiting: false });
  if (tell) api('mood', { body: { level: 'stop', tab: MOOD.tab } }).catch(() => {});
}
// Closing the listening page hands mood follow (and the lights) back right
// away, instead of after 3 minutes (3.18.2).
window.addEventListener('pagehide', () => { if (MOOD.on) { moodStop(false); api('mood', { body: { level: 'stop', tab: MOOD.tab }, keepalive: true }).catch(() => {}); } });
function moodPanel(box) {
  if (!box) return;
  const md = S.settings.mood || {}, ro = role() === 'viewer';
  const effs = Object.entries(S.settings.effects || {});
  const sel = lv => `<select data-mood="${lv}" ${ro || MOOD.on ? 'disabled' : ''}><option value="">Choose…</option>${effs.map(([k, e]) => `<option value="${esc(k)}" ${md[lv] === k ? 'selected' : ''}>${esc(e.label || k)}</option>`).join('')}</select>`;
  const ready = MOOD_LEVELS_UI.every(([lv]) => md[lv]);
  box.innerHTML = `<div class="panel-head"><h2>Mood follow <span class="pill">Beta</span></h2>
      ${MOOD.on ? '<button class="small danger" data-moodstop>Stop</button>' : `<button class="small primary" data-moodgo ${!ready || ro || !moodAvailable() || LINK.on ? 'disabled' : ''}>Start listening</button>`}</div>
    <p class="note">The app computer's microphone listens to the music and switches between three of your patterns as it gets calmer or livelier, every 10 seconds or so. It follows the <b>mood</b>, not the beat: Trimlight's cloud is far too slow for the beat (that's what the controller's own music mode is for).</p>
    <div class="cols" style="gap:10px">${MOOD_LEVELS_UI.map(([lv, l]) => `<label class="field">${l}${sel(lv)}</label>`).join('')}</div>
    ${!moodAvailable() ? `<p class="callout small">A browser only lets a page use the microphone on the computer itself. Open EaveLuxOS on the app computer (<b>${location.protocol}//localhost:${location.port || 8787}</b>) and start it there, with the music playing near that computer.</p>` : ''}
    ${MOOD.on ? `<div class="meter"><i id="moodmeter"></i></div><p class="small">${MOOD.level ? `Hearing <b>${MOOD.level}</b> music${MOOD.pattern ? (MOOD.waiting ? ' (' : ': ') + esc(MOOD.pattern) + (MOOD.waiting ? ')' : '') : ''}.` : 'Listening… the first change comes in about 10 seconds.'} Keep this page open (a background tab is fine). After 30 seconds of quiet, or when this page closes, the lights go back to the schedule. A weather alert or a pattern you choose by hand comes first.</p>` : ''}
    ${MOOD.err ? `<p class="callout warn small">${esc(MOOD.err)}</p>` : ''}`;
  box.onchange = e => {
    const t = e.target.closest('[data-mood]'); if (!t) return;
    const n = clone(S.settings); n.mood = { ...(n.mood || {}), [t.dataset.mood]: t.value || null };
    busy(null, () => saveSettings(n, 'Saved')).then(() => moodPanel(box)).catch(() => moodPanel(box));
  };
  box.onclick = e => {
    const b = e.target.closest('button'); if (!b) return; e.stopPropagation();
    if (b.dataset.moodstop !== undefined) { moodStop(); toast('Mood follow stopped; back on the schedule'); linkPanel($('#linkbox')); return moodPanel(box); }
    if (b.dataset.moodgo !== undefined) busy(b, moodStart).then(() => { moodPanel(box); linkPanel($('#linkbox')); })
      .catch(err => { MOOD.err = err.name === 'NotAllowedError' ? 'The microphone wasn’t allowed. Allow it for this page in the browser, then try again.' : err.message; moodPanel(box); });
  };
}
const MOOD_LEVELS_UI = [['calm', 'Calm music'], ['lively', 'Lively music'], ['party', 'Party music']];

/* Setup › App › AI pattern ideas (3.18): the owner's own Anthropic API key, for
   Create's "Describe it". Kept with the other secrets; never exported. */
async function aiPanel(box) {
  if (!box) return;
  let st; try { st = await api('ai'); } catch (e) { box.innerHTML = `<h2>AI pattern ideas</h2><p class="muted small">${esc(e.message)}</p>`; return; }
  S.aiOn = st.configured; foldSums();
  box.innerHTML = `<h2>AI pattern ideas</h2>
    <p class="note">Create's <b>Describe it</b> works without this, built in and free. With an Anthropic API key, it can also ask Claude for ideas. Each idea costs a fraction of a cent on your Anthropic account, and the description you type is sent to Anthropic. Nothing else about your home is sent.</p>
    ${st.configured ? '<p class="callout ok small">A key is saved. Create shows <b>Use AI</b>.</p>' : ''}
    <div class="row"><input type="password" id="aikey" class="grow" style="flex:1" autocomplete="off" placeholder="${st.configured ? 'Saved (paste a new key to replace it)' : 'sk-ant-…'}" aria-label="Anthropic API key">
      <button class="small" data-aisave>Save key</button>${st.configured ? '<button class="small ghost danger" data-aidel>Remove</button>' : ''}</div>
    <p class="note">Get a key at console.anthropic.com › API keys. It's stored encrypted with your other credentials and never included in exported files. Up to 6 ideas a minute and 100 a day, to keep the cost in check.</p>
    ${st.configured ? `<div class="row"><label class="field" style="flex:1">Model<input id="aimodel" value="${esc(st.model)}" placeholder="${esc(st.default_model)}" autocomplete="off" spellcheck="false"></label>
      <button class="small" data-aimodel style="align-self:flex-end">Save model</button></div>
    <p class="note">Only change this if Use AI says the model wasn't found (Anthropic retires older models). Leave it empty for the default, ${esc(st.default_model)}.</p>` : ''}`;
  box.onclick = e => {
    const b = e.target.closest('button'); if (!b) return; e.stopPropagation();
    if (b.dataset.aimodel !== undefined) {
      const model = ($('#aimodel').value || '').trim();
      return busy(b, () => api('ai/settings', { body: { model } }).then(loadSettings)).then(() => { toast(model ? 'Model saved' : 'Back to the default model'); aiPanel(box); }).catch(() => {});
    }
    const key = b.dataset.aidel !== undefined ? '' : ($('#aikey').value || '').trim();
    if (b.dataset.aisave !== undefined && !key) return toast('Paste the key first.', true);
    busy(b, () => api('ai/settings', { body: { key } })).then(() => { toast(key ? 'Key saved' : 'Key removed'); aiPanel(box); }).catch(() => {});
  };
}

/* Settings › Webhooks: try an alert flash from here (3.16). */
async function tryAlertPanel(box) {
  if (!box) return;
  let tr; try { tr = await api('triggers'); } catch (e) { return; }
  const effs = Object.entries(S.settings.effects || {});
  box.innerHTML = `<details><summary class="small">Try an alert</summary><div class="stack" style="margin-top:10px">
    <div class="row"><label class="field" style="flex:2;min-width:160px">Pattern<select id="tapat">${tr.presets.map(p => `<option value="${esc(p.key)}">${esc(p.label)}</option>`).join('')}
        <optgroup label="Your patterns">${effs.map(([k, e]) => `<option value="${esc(k)}">${esc(e.label || k)}</option>`).join('')}</optgroup></select></label>
      <label class="field" style="flex:2;min-width:140px">Zone<select id="tazone"><option value="">Whole house</option>${tr.zones.map(z => `<option>${esc(z.name)}</option>`).join('')}</select></label>
      <label class="field" style="flex:1;min-width:90px">Seconds<input type="number" id="tasec" min="5" max="600" value="15"></label></div>
    ${tr.zones.length ? '' : '<p class="note">Zones come from the House tab: select a range with the bulb finder and save it as a zone.</p>'}
    <div class="row"><button class="small" data-tatry>Flash it</button><button class="small ghost" data-tastop>Stop</button></div></div></details>`;
  box.onclick = e => {
    const b = e.target.closest('button'); if (!b) return; e.stopPropagation();
    const body = b.dataset.tastop !== undefined ? { action: 'stop_flash' }
      : { action: 'flash', effect: $('#tapat').value, zone: $('#tazone').value || undefined, seconds: +$('#tasec').value || 15 };
    busy(b, () => api('action', { body })).then(st => {
      S.status = st;
      if (body.action !== 'flash') return toast('Stopped');
      toast(st.flash_started === false ? `Not shown: ${st.target.source || 'something more important'} is showing (see Activity on Home).` : 'Flashing', st.flash_started === false);
    }).catch(() => {});
  };
}

/* Schedule › Severe weather alerts (3.16): NWS warnings for your location
   change the lights until the warning ends (or it's dismissed). */
async function wxAlertPanel(box) {
  if (!box) return;
  let tr; try { tr = await api('triggers'); } catch (e) { box.innerHTML = `<h2>Severe weather alerts</h2><p class="muted small">${esc(e.message)}</p>`; return; }
  const s = S.settings, wa = s.weather_alerts || {}, ro = role() === 'viewer';
  const groups = wa.groups || ['tornado', 'storm'], cur = wa.effect || 'severe';
  const al = tr.alert;
  box.innerHTML = `<div class="panel-head"><h2>Severe weather alerts</h2><label class="check"><input type="checkbox" id="waon" ${wa.enabled ? 'checked' : ''} ${ro ? 'disabled' : ''}> On</label></div>
    <p class="note">When the National Weather Service issues a warning for your location, the lights change to an alert pattern until it ends. US only; checked every 5 minutes.</p>
    ${al && al.event ? `<p class="callout warn small"><b>${esc(al.event)}</b>${al.until ? ' until ' + esc(al.until) : ''}. ${esc(al.headline || '')}</p>` : wa.enabled && al && al.error ? `<p class="callout warn small">${esc(al.error)}</p>` : wa.enabled && al && al.checked ? '<p class="small muted">No warnings for your location right now.</p>' : ''}
    <div class="chips">${tr.alert_groups.map(g => `<label class="check small" title="${esc(g.events.join(', '))}"><input type="checkbox" data-wag="${esc(g.key)}" ${groups.includes(g.key) ? 'checked' : ''} ${ro ? 'disabled' : ''}> ${esc(g.label)}</label>`).join('')}</div>
    <div class="row"><label class="field grow">Pattern<select id="waeff" ${ro ? 'disabled' : ''}>${tr.presets.map(p => `<option value="${esc(p.key)}" ${cur === p.key ? 'selected' : ''}>${esc(p.label)}</option>`).join('')}
      <optgroup label="Your patterns">${Object.entries(s.effects || {}).map(([k, e]) => `<option value="${esc(k)}" ${cur === k ? 'selected' : ''}>${esc(e.label || k)}</option>`).join('')}</optgroup></select></label></div>
    <label class="check"><input type="checkbox" id="waturn" ${wa.turn_on ? 'checked' : ''} ${ro ? 'disabled' : ''}> Turn the lights on for a warning, even in daytime or when the schedule has them off</label>
    <p class="note">Warnings only (not watches). The alert never interrupts a music show, and Home has a button to dismiss it.</p>`;
  if (ro) return;
  box.onchange = () => {
    const n = clone(S.settings);
    n.weather_alerts = { enabled: $('#waon').checked, groups: $$('[data-wag]', box).filter(x => x.checked).map(x => x.dataset.wag),
      effect: $('#waeff').value, turn_on: $('#waturn').checked };
    if (n.weather_alerts.enabled && !n.weather_alerts.groups.length) { toast('Choose at least one kind of warning.', true); return wxAlertPanel(box); }
    busy(null, () => saveSettings(n, 'Weather alerts saved')).then(() => wxAlertPanel(box)).catch(() => wxAlertPanel(box));
  };
}

/* Schedule › Coming up: the next 3 weeks as a list, or a month as a calendar
   (3.15). Each rule keeps one color everywhere, so a season stands out. */
const RULE_COLORS = ['#E8833A', '#3A86E8', '#2FA36B', '#C04BD1', '#D6455D', '#1FA5A5', '#B08A1E', '#6C63FF'];
function ruleColor(name) {
  const i = (S.settings.rules || []).findIndex(r => r.name === name);
  if (i >= 0) return RULE_COLORS[i % RULE_COLORS.length];
  let h = 0; for (const c of String(name)) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return RULE_COLORS[h % RULE_COLORS.length];
}
function upcomingPanel(box) {
  if (!box) return;
  const view = S.upcView || 'month';          // 4.6.1: the month first
  const now = new Date(), ym = S.calMonth || `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
  const [y, mo] = ym.split('-').map(Number);
  const title = new Date(y, mo - 1, 1).toLocaleDateString([], { month: 'long', year: 'numeric' });
  const ctls = ctlList(), cdev = ctls.some(d => d.id === S.upcDev) ? S.upcDev : '';
  box.innerHTML = `<div class="panel-head"><h2>Coming up</h2>${ctls.length > 1 ? `<select id="upcdev" aria-label="Controller" style="width:auto">
      <option value="">All controllers</option>${ctls.map(d => `<option value="${esc(d.id)}" ${d.id === cdev ? 'selected' : ''}>${esc(d.name)}</option>`).join('')}</select>` : ''}<div class="seg" role="group" aria-label="Show as">
      <button data-upv="month" aria-pressed="${view === 'month'}">Month</button><button data-upv="list" aria-pressed="${view === 'list'}">List</button></div></div>
    ${view === 'month' ? `<div class="calnav"><button class="small ghost" data-calm="-1" aria-label="Previous month">‹</button><b>${esc(title)}</b><button class="small ghost" data-calm="1" aria-label="Next month">›</button></div>` : ''}
    <div id="upc" style="margin-top:8px"><p class="muted">Loading…</p></div>`;
  const day = d => new Date(d.date + 'T12:00');
  const times = d => (d.windows || []).length ? d.windows.map(w => `<div class="win"><span class="dot" style="background:${ruleColor(w.rule)}"></span><span class="num">${esc(hm12(w.on_label))} – ${esc(hm12(w.off_label))}</span> <span class="sub">${esc(w.rule)}${w.effect && w.effect !== w.rule ? ' · ' + esc(w.effect) : ''}${w.controllers ? ' · ' + esc(w.controllers.join(', ')) : ''}</span></div>`).join('') : '<span class="sub">Off</span>';
  const q = (view === 'month' ? `upcoming?month=${ym}` : 'upcoming?days=21') + (cdev ? `&device=${encodeURIComponent(cdev)}` : '');
  const sel = $('#upcdev', box);
  if (sel) sel.onchange = () => { S.upcDev = sel.value; upcomingPanel(box); };
  api(q).then(list => {
    const out = $('#upc'); if (!out) return;
    if (!list.length) { out.innerHTML = '<p class="muted">Finish setup to see upcoming times.</p>'; return; }
    if (view === 'list') {
      out.innerHTML = `<div class="list">${list.map(d => `<div class="item"><div style="width:5.5em" class="small"><b>${esc(day(d).toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' }))}</b></div>
        <div class="grow">${times(d)}${d.dst_change ? `<div class="dst">${esc(d.abbr)} starts today</div>` : ''}</div><div class="sub num">☾ ${esc(hm12(d.sunset))}</div></div>`).join('')}</div>`;
      return;
    }
    const lead = day(list[0]).getDay(), today = new Date().toDateString();
    const rules = [...new Set(list.flatMap(d => (d.windows || []).map(w => w.rule)))];
    out.innerHTML = `<div class="cal" role="grid" aria-label="${esc(title)}">
        ${['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map(w => `<div class="calh">${w}</div>`).join('')}
        ${'<div></div>'.repeat(lead)}
        ${list.map((d, i) => `<button class="calday${day(d).toDateString() === today ? ' today' : ''}${(d.windows || []).length ? '' : ' off'}" data-calday="${i}" aria-label="${esc(day(d).toLocaleDateString([], { weekday: 'long', month: 'long', day: 'numeric' }))}: ${esc((d.windows || []).map(w => w.rule).join(', ') || 'off')}">
          <span class="n">${day(d).getDate()}</span>${(d.windows || []).map(w => `<span class="bar" style="background:${ruleColor(w.rule)}" title="${esc(w.rule)}"><span>${esc(w.rule)}</span></span>`).join('')}</button>`).join('')}
      </div>
      ${rules.length ? `<div class="legend" style="margin-top:10px">${rules.map(r => `<span><span class="dot" style="background:${ruleColor(r)}"></span>${esc(r)}</span>`).join('')}</div>` : '<p class="muted small" style="margin-top:8px">Nothing scheduled this month.</p>'}
      <div id="caldetail" class="note" style="margin-top:10px">Tap a day for its times.</div>`;
    out.onclick = e => {
      const b = e.target.closest('[data-calday]'); if (!b) return;
      const d = list[+b.dataset.calday];
      $('#caldetail').innerHTML = `<b>${esc(day(d).toLocaleDateString([], { weekday: 'long', month: 'long', day: 'numeric' }))}</b> · sunset ${esc(hm12(d.sunset))}${d.dst_change ? ` · ${esc(d.abbr)} starts` : ''}<div style="margin-top:4px">${times(d)}</div>`;
    };
  }).catch(e => { const out = $('#upc'); if (out) out.innerHTML = `<p class="muted">${esc(e.message)}</p>`; });
  box.onclick = e => {
    const b = e.target.closest('button'); if (!b) return;
    if (b.dataset.upv) { e.stopPropagation(); S.upcView = b.dataset.upv; upcomingPanel(box); }
    else if (b.dataset.calm) {
      e.stopPropagation();
      const d = new Date(y, mo - 1 + +b.dataset.calm, 1);
      S.calMonth = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`; upcomingPanel(box);
    }
  };
}

// The Schedule tab's "Right now" panel with "Run the schedule".
function schedNowPanel(box, st) {
  if (!box || !st || st.setup_only || !st.target) { if (box) box.hidden = true; return; }
  const t = st.target, { head, sub } = stateLine(st);
  const following = t.reason !== 'manual' && t.reason !== 'flash' && !(t.reason === 'music' && !st.music.scheduled) && !st.levels?.adjusted;
  box.hidden = false;
  const aw = awayActive();
  box.innerHTML = `${aw ? `<p class="callout ok small" style="margin:0 0 8px">Away mode: times move by up to ${aw.minutes} minutes each night until ${esc(new Date(aw.until + 'T12:00').toLocaleDateString([], { month: 'short', day: 'numeric' }))}.</p>` : ''}<div class="panel-head"><h2>Right now</h2><button class="primary" data-runsched ${role() === 'viewer' ? 'disabled' : ''}>Run the schedule</button></div>
    <p><b>${esc(following ? 'Following the schedule' : head)}</b>. ${esc(sub)}</p>
    ${st.error ? `<p class="callout warn small">Can't reach the lights right now: ${esc(st.error)}</p>` : ''}
    <p class="note">${following ? 'Changed the lights in the Trimlight Edge app? ' : ''}<b>Run the schedule</b> ends anything set by hand (a pattern, Off, a music show from the Music button, a security flash) and sends what the schedule says right now to the controller again. Show nights from the Music tab are part of the schedule and keep running.</p>`;
}

VIEWS.schedule = async () => {
  const m = $('#main'), s = S.settings;
  const rules = (s.rules || []).map((r, i) => ({ r, i })).sort((a, b) => prio(b.r) - prio(a.r) || a.i - b.i);
  const effs = s.effects || {};
  // 4.0: only what runs when. Weather, severe weather alerts and the
  // security flash are on the Alerts tab; the backup timer is in Setup.
  m.innerHTML = `<div class="view">
    <div class="panel-head"><h2>Schedule</h2><button class="ghost" data-import>Import from Trimlight app</button><button class="primary" data-addrule>Add a rule</button></div>
    <div class="panel stack" id="schednow" hidden></div>
    <h3 class="secthead">Every night</h3>
    <div class="cols wide-left">
      <div class="stack">
        <div class="panel"><h2>Rules</h2><p class="note" style="margin-top:4px">A day can have several rules that don't overlap, for example a morning one (6:00 AM to sunrise) and an evening one (sunset to 11:00 PM); each runs in its own time. Only where rules overlap does the higher priority win (or, with equal priority, the one higher in this list).</p>
          <div class="row" style="margin-top:6px"><button class="small ghost" data-addmorning>Add a morning schedule</button></div>
          <div class="list" style="margin-top:8px">${rules.length ? rules.map(({ r, i }) => { const pats = Array.isArray(r.effect) ? r.effect : [r.effect];
            return `<div class="item"><div class="grow" data-rulename="${esc(r.name)}"><div class="row" style="gap:8px"><span class="name">${esc(r.name)}</span><span class="badge ${prio(r) >= 200 ? 'hi' : ''}">${prioLabel(prio(r))} · ${prio(r)}</span>${r.controllers ? `<span class="badge">${esc(ctlNames(r.controllers).join(', ') || 'a controller not run now')} only</span>` : ''}</div>
              <div class="sub">${esc(humanDates(r))} · ${esc(humanDays(r.days))} · ${esc(humanT(r.on))} → ${esc(humanT(r.off))}</div>
              <div class="sub">${swatches(effectSwatches(effs[pats[0]]), 4)} ${pats.length > 1 && Array.isArray(r.rotate_each) ? esc(pats.map((p, i) => `${effLabel(p)} ${r.rotate_each[i]} min`).join(' / ')) + ', in turn'
                : esc(pats.map(effLabel).join(' / ')) + (pats.length > 1 ? (r.rotate === 'nightly' ? ', a different one each night' : `, every ${r.rotate_minutes} min`) : '')}${r.brightness !== undefined ? `, brightness ${Math.round(r.brightness / 2.55)}%` : ''}</div></div>
              <button class="small ghost" data-editrule="${i}">Edit</button><button class="small ghost danger" data-delrule="${i}" aria-label="Delete ${esc(r.name)}">Delete</button></div>`; }).join('')
            : '<p class="muted">No rules yet. Add one to turn the lights on automatically.</p>'}</div></div>
      </div>
      ${fold('upcoming', 'Coming up', '<div class="panel" id="upcbox"><p class="muted small">Loading…</p></div>', wide())}
      ${fold('whowins', 'Who wins tonight', '<div class="panel stack" id="winbox"><p class="muted small">Loading…</p></div>')}
    </div>
    <h3 class="secthead">Special days</h3>
    <div class="stack">
      ${fold('holidays', 'Holidays', '<div class="panel stack" id="holbox"><p class="muted small">Loading…</p></div>')}
      ${fold('game', 'Game-day lights', '<div class="panel stack" id="gamebox"><p class="muted small">Loading…</p></div>')}
      ${fold('away', 'Away mode', '<div class="panel stack" id="awaybox"><p class="muted small">Loading…</p></div>')}
    </div></div>`;
  whenOpen('away', () => awayPanel($('#awaybox')));
  whenOpen('game', () => gamePanel($('#gamebox')));
  whenOpen('holidays', () => holidayPanel($('#holbox')));
  schedNowPanel($('#schednow'), S.status);
  api('status').then(st => { S.status = st; foldSums(); if (S.view === 'schedule') schedNowPanel($('#schednow'), st); }).catch(() => {});
  api('rulecheck').then(rc => { for (const [name, info] of Object.entries(rc)) {
    if (!info.blocked_by) continue;
    const el = $$('[data-rulename]', m).find(x => x.dataset.rulename === name);
    if (el) el.insertAdjacentHTML('beforeend', `<div class="callout warn small" style="margin-top:6px">Never runs in the next year: \u201c${esc(info.blocked_by)}\u201d wins on all its nights. ${esc(info.hint)}</div>`);
  } }).catch(() => {});
  whenOpen('upcoming', () => upcomingPanel($('#upcbox')));
  whenOpen('whowins', () => winPanel($('#winbox')));
  m.onclick = async e => {
    const b = e.target.closest('button'); if (!b) return; const d = b.dataset;
    if (d.runsched !== undefined) {
      return busy(b, async () => { S.status = await api('action', { body: { action: 'resume', force: true } }); schedNowPanel($('#schednow'), S.status); })
        .then(() => toast('Running the schedule')).catch(() => {});
    }
    if (d.addrule !== undefined) { if (!Object.keys(effs).length) return toast('Create a pattern first.', true); ruleDialog(); }
    else if (d.addmorning !== undefined) { if (!Object.keys(effs).length) return toast('Create a pattern first.', true);
      ruleDialog(undefined, { name: 'Morning', on: '06:00', off: 'sunrise', effect: (rules.find(x => !x.r.dates) || {}).r?.effect || Object.keys(effs)[0] }); }
    else if (d.editrule) ruleDialog(+d.editrule);
    else if (d.delrule) { if (await confirmBox('Delete rule?', `“${esc(s.rules[+d.delrule].name)}” will be removed.`, 'Delete', true)) { const n = clone(s); n.rules.splice(+d.delrule, 1); await busy(null, () => saveSettings(n, 'Deleted')).catch(() => {}); VIEWS.schedule(); } }
    else if (d.import !== undefined) busy(b, importFromApp).catch(() => {});
  };
};

/* ---------------------------------------------------------------- ALERTS (4.0)
   Everything that changes the lights when something happens: the weather,
   severe weather warnings, the security flash, webhooks (Home Assistant,
   cameras) and phone alerts. Moved here from Schedule and Settings. */
/* ---------------------------------------------------------------- 4.11: AUTOMATIONS
   When something happens, if conditions hold, then do something. The
   engine is automations.py; this is the list and the builder. */
const AUTO_WHEN = [['score', 'A team scores'], ['game_start', 'A game starts'], ['game_end', 'A game ends'],
  ['weather', 'A severe weather warning starts'], ['webhook', 'A webhook event comes'], ['time', 'It’s a time of day'],
  ['lights', 'The schedule turns the lights on or off']];
const AUTO_IF = [['dark', 'It’s dark (sunset to sunrise)'], ['between', 'Between two times'], ['before', 'Before a time'],
  ['after', 'After a time'], ['days', 'On these days'], ['dates', 'Between two dates'], ['lights', 'The lights are on or off'],
  ['rule', 'A rule is running'], ['pattern', 'A pattern is showing'], ['home', 'The team is at home'], ['away', 'The team is away'],
  ['winning', 'The team is winning'], ['losing', 'The team is losing']];
const AUTO_THEN = [['flash', 'Flash, then go back'], ['show', 'Show a pattern'], ['off', 'Turn off for a while'], ['sound', 'Play a team’s sound']];
const AUTO_DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const GAME_ONLY = ['home', 'away', 'winning', 'losing'];
const autoPrio = p => p >= 300 ? 'Highest' : p >= 200 ? 'High' : p >= 100 ? 'Normal' : 'Low';
function autoTeams() {
  return ((S.settings.gameday || {}).teams || []).filter(t => t && t.league && t.team)
    .map(t => ({ key: `${t.league}-${String(t.team).toLowerCase()}`, name: t.name || String(t.team).toUpperCase(), sound: t.sound }));
}
function autoDescribe(a) {
  const w = a.when || {}, eff = k => ((S.settings.effects || {})[k] || {}).label || k;
  const team = k => k === 'any' || !k ? 'a team' : (autoTeams().find(t => t.key === k) || {}).name || k;
  const dev = id => ctlNames([id])[0] || 'a controller';
  const when = { score: () => `${team(w.team)} scores`, game_start: () => `${team(w.team)}’s game starts`,
    game_end: () => `${team(w.team)}’s game ends${w.result === 'win' ? ' in a win' : w.result === 'loss' ? ' in a loss' : ''}`,
    weather: () => w.event ? `a ${w.event} starts` : 'a weather warning starts', webhook: () => `the webhook event “${w.name || ''}” comes`,
    time: () => `it’s ${w.at || ''}`, lights: () => `the schedule turns the lights ${w.on === false ? 'off' : 'on'}` }[w.type];
  const cs = (a.if || []).map(c => ({ dark: () => 'it’s dark', between: () => `between ${c.from} and ${c.to}`, before: () => `before ${c.at}`,
    after: () => `after ${c.at}`, days: () => 'on ' + (c.days || []).map(d => AUTO_DAYS[d]).join(', '), dates: () => `from ${c.from} to ${c.to}`,
    lights: () => `the lights are ${c.on === false ? 'off' : 'on'}`, rule: () => `${c.name} is running`, pattern: () => `${eff(c.effect)} is showing`,
    home: () => 'they’re home', away: () => 'they’re away', winning: () => 'they’re winning', losing: () => 'they’re losing' }[c.type] || (() => ''))());
  const acts = (a.then || []).map(x => { const on = x.device ? ` on ${dev(x.device)}` : '';
    return ({ flash: () => `flash ${x.effect ? eff(x.effect) : x.color}${x.zone ? ' in ' + x.zone : ''} for ${x.seconds} s${on}`,
      show: () => `show ${eff(x.effect)}${on} ${x.minutes ? `for ${x.minutes} min` : 'until the schedule changes'}`,
      off: () => `turn off${on} for ${x.minutes} min`, sound: () => `play ${team(x.team)}’s sound` }[x.type] || (() => ''))(); });
  return `When ${when ? when() : '…'}${cs.length ? ', if ' + cs.join(' and ') : ''}, then ${acts.join(', then ') || '…'}.`;
}
async function autoPanel(box) {
  const autos = S.settings.automations || [], ro = role() === 'viewer';
  let hist = [];
  try { hist = await api('automations/history'); } catch { /* shown empty */ }
  box.innerHTML = `<div class="panel-head"><h2>Automations</h2>${ro ? '' : '<button class="small" data-autoadd>Add an automation</button>'}</div>
    <p class="note">When something happens, if everything you list is true, then the lights do what you say, and go back afterward. For example: when the Flyers score, if it’s dark, flash orange and black for 20 seconds. A higher priority goes first when two start at once.</p>
    <div class="list">${autos.map((a, i) => `<div class="item"><div class="grow">
        <div class="row" style="gap:8px"><label class="check"><input type="checkbox" data-autoon="${i}" ${a.enabled === false ? '' : 'checked'} ${ro ? 'disabled' : ''}><span class="name">${esc(a.name)}</span></label>
          <span class="badge ${(a.priority ?? 100) >= 200 ? 'hi' : ''}">${autoPrio(a.priority ?? 100)} · ${a.priority ?? 100}</span>${a.beats_manual ? '<span class="badge">beats a manual choice</span>' : ''}</div>
        <div class="sub">${esc(autoDescribe(a))}</div><div class="small" data-autoout="${i}"></div></div>
        <div class="row" style="gap:6px">${ro ? '' : `<button class="small ghost" data-autotry="${i}">Try it now</button>`}<button class="small ghost" data-autochk="${i}">Check it now</button>
          ${ro ? '' : `<button class="small ghost" data-autoedit="${i}">Edit</button><button class="small ghost danger" data-autodel="${i}">Delete</button>`}</div></div>`).join('')
      || '<p class="muted">No automations yet.</p>'}</div>
    ${hist.length ? `<h3 style="margin:10px 0 4px">Lately</h3><div class="small">${hist.slice(0, 8).map(h => `<div><span class="muted">${esc(h.at)}</span> ${esc(h.text)}</div>`).join('')}</div>` : ''}
    <p class="note">Webhooks can start one by name: <code>POST /api/hook/event</code> with <code>{"name": "doorbell"}</code> (Alerts › Webhooks has the address and token). A team’s score celebration under Schedule › Game-day lights can become an automation with <b>Make it an automation</b>.</p>`;
  const save = (n, msg) => busy(null, () => saveSettings(n, msg)).then(() => autoPanel(box)).catch(() => {});
  box.onchange = e => {
    const t = e.target;
    if (t.dataset.autoon !== undefined) { const n = clone(S.settings); n.automations[+t.dataset.autoon].enabled = t.checked; save(n, t.checked ? 'On' : 'Off'); }
  };
  box.onclick = async e => {
    const b = e.target.closest('button'); if (!b) return; const d = b.dataset;
    if (d.autoadd !== undefined) return autoDialog(null, () => autoPanel(box));
    if (d.autoedit) return autoDialog(+d.autoedit, () => autoPanel(box));
    if (d.autodel) {
      if (!await confirmBox('Delete this automation?', esc(autos[+d.autodel].name), 'Delete')) return;
      const n = clone(S.settings); n.automations.splice(+d.autodel, 1); return save(n, 'Deleted');
    }
    const out = $(`[data-autoout="${d.autotry || d.autochk}"]`, box);
    if (d.autotry) return busy(b, () => api('automation/try', { body: { id: autos[+d.autotry].id } }))
      .then(r => { out.textContent = r.result; }).catch(() => {});
    if (d.autochk) return busy(b, () => api('automation/check', { body: { id: autos[+d.autochk].id } }))
      .then(r => { out.innerHTML = r.conditions.length ? r.conditions.map(c => `<div>${c.ok ? '✓' : '✗'} ${esc(c.text)}</div>`).join('')
        + (r.game_only ? '<div class="muted">Home, away, winning and losing are checked when the game event comes.</div>' : '')
        : 'No conditions: it runs whenever the event comes.'; }).catch(() => {});
  };
}
function autoDialog(idx, done) {
  const src = idx === null ? null : (S.settings.automations || [])[idx];
  const A = src ? clone(src) : { id: 'a' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6), name: '', enabled: true,
    priority: 100, cooldown: 30, beats_manual: false, when: { type: 'score', team: 'any' }, if: [{ type: 'dark' }], then: [{ type: 'flash', seconds: 20 }] };
  const effs = Object.entries(S.settings.effects || {}), teams = autoTeams(), ctls = ctlList(), zones = mapData().zones || [];
  const rules = (S.settings.rules || []).map(r => r.name).filter(Boolean);
  const opt = (v, cur, label) => `<option value="${esc(v)}" ${String(v) === String(cur ?? '') ? 'selected' : ''}>${esc(label)}</option>`;
  const teamSel = (k, cur, any = true) => `<select data-k="${k}" style="width:auto;max-width:100%">${any ? opt('any', cur, 'Any team') : ''}${teams.map(t => opt(t.key, cur, t.name)).join('')}</select>`;
  const effSel = (k, cur, none) => `<select data-k="${k}" style="width:auto;max-width:100%">${none ? opt('', cur, none) : ''}${effs.map(([key, e]) => opt(key, cur, e.label || key)).join('')}</select>`;
  const timeIn = (k, cur, ph) => `<input type="text" data-k="${k}" value="${esc(cur ?? '')}" placeholder="${ph}" style="width:9em">`;
  const devSel = (k, cur) => ctls.length > 1 ? `<select data-k="${k}" style="width:auto">${opt('', cur, 'All controllers')}${ctls.map(c => opt(c.id, cur, c.name)).join('')}</select>` : '';
  const whenHtml = () => { const w = A.when; return `<select data-k="when.type" style="width:auto;max-width:100%">${AUTO_WHEN.map(([v, l]) => opt(v, w.type, l)).join('')}</select>
    ${['score', 'game_start', 'game_end'].includes(w.type) ? (teams.length ? teamSel('when.team', w.team) : '<span class="note">Add a team under Schedule › Game-day lights first.</span>') : ''}
    ${w.type === 'game_end' ? `<select data-k="when.result" style="width:auto">${opt('any', w.result, 'win or loss')}${opt('win', w.result, 'in a win')}${opt('loss', w.result, 'in a loss')}</select>` : ''}
    ${w.type === 'weather' ? `<input type="text" data-k="when.event" value="${esc(w.event || '')}" placeholder="any warning, or e.g. Tornado Warning">` : ''}
    ${w.type === 'webhook' ? `<input type="text" data-k="when.name" value="${esc(w.name || '')}" placeholder="e.g. doorbell" maxlength="40">` : ''}
    ${w.type === 'time' ? timeIn('when.at', w.at, 'sunset + 15, 6:30 pm') : ''}
    ${w.type === 'lights' ? `<select data-k="when.on" style="width:auto">${opt('true', String(w.on !== false), 'on')}${opt('false', String(w.on !== false), 'off')}</select>` : ''}`; };
  const condHtml = (c, i) => `<div class="row autorow" style="gap:6px"><select data-k="if.${i}.type" style="width:auto;max-width:100%">${AUTO_IF.filter(([v]) => !GAME_ONLY.includes(v) || ['score', 'game_start', 'game_end'].includes(A.when.type)).map(([v, l]) => opt(v, c.type, l)).join('')}</select>
    ${c.type === 'between' ? timeIn(`if.${i}.from`, c.from, 'from, e.g. 6:00 pm') + timeIn(`if.${i}.to`, c.to, 'to, e.g. 11:00 pm') : ''}
    ${c.type === 'before' || c.type === 'after' ? timeIn(`if.${i}.at`, c.at, 'e.g. 10:00 pm, sunset') : ''}
    ${c.type === 'days' ? AUTO_DAYS.map((d, j) => `<label class="check small"><input type="checkbox" data-k="if.${i}.day.${j}" ${(c.days || []).includes(j) ? 'checked' : ''}>${d}</label>`).join('') : ''}
    ${c.type === 'dates' ? `<input type="text" data-k="if.${i}.from" value="${esc(c.from || '')}" placeholder="from 12-01" style="width:7em"><input type="text" data-k="if.${i}.to" value="${esc(c.to || '')}" placeholder="to 12-31" style="width:7em">` : ''}
    ${c.type === 'lights' ? `<select data-k="if.${i}.on" style="width:auto">${opt('true', String(c.on !== false), 'on')}${opt('false', String(c.on !== false), 'off')}</select>` : ''}
    ${c.type === 'rule' ? `<select data-k="if.${i}.name" style="width:auto;max-width:100%">${rules.map(r => opt(r, c.name, r)).join('')}</select>` : ''}
    ${c.type === 'pattern' ? effSel(`if.${i}.effect`, c.effect) : ''}
    <button type="button" class="small ghost danger" data-rmif="${i}" aria-label="Remove this condition">✕</button></div>`;
  const actHtml = (x, i) => `<div class="row autorow" style="gap:6px"><select data-k="then.${i}.type" style="width:auto;max-width:100%">${AUTO_THEN.map(([v, l]) => opt(v, x.type, l)).join('')}</select>
    ${x.type === 'flash' ? `${effSel(`then.${i}.effect`, x.effect, 'a color:')}${x.effect ? '' : `<input type="color" data-k="then.${i}.color" value="${esc(x.color || '#FF6600')}">`}
      ${zones.length ? `<select data-k="then.${i}.zone" style="width:auto">${opt('', x.zone, 'whole house')}${[...new Set(zones.map(z => z.name))].map(z => opt(z, x.zone, 'zone: ' + z)).join('')}</select>` : ''}
      <label class="row small" style="gap:4px">for<input type="number" data-k="then.${i}.seconds" min="5" max="600" value="${x.seconds ?? 20}" style="width:5em">s</label>` : ''}
    ${x.type === 'show' ? `${effSel(`then.${i}.effect`, x.effect)}<label class="row small" style="gap:4px">for<input type="number" data-k="then.${i}.minutes" min="1" max="720" value="${x.minutes ?? ''}" placeholder="until next" style="width:6em">min</label>` : ''}
    ${x.type === 'off' ? `<label class="row small" style="gap:4px">for<input type="number" data-k="then.${i}.minutes" min="1" max="720" value="${x.minutes ?? 30}" style="width:5em">min</label>` : ''}
    ${x.type === 'sound' ? (teams.length ? teamSel(`then.${i}.team`, x.team, false) : '<span class="note">Teams and their sounds are under Schedule › Game-day lights.</span>') : ''}
    ${x.type !== 'sound' ? devSel(`then.${i}.device`, x.device) : ''}
    <button type="button" class="small ghost danger" data-rmthen="${i}" aria-label="Remove this action">✕</button></div>`;
  const body = () => `<label class="field">Name<input type="text" data-k="name" value="${esc(A.name)}" maxlength="60" placeholder="e.g. Flyers goal"></label>
    <div class="stack" style="gap:6px"><b>When</b><div class="row" style="gap:6px">${whenHtml()}</div></div>
    <div class="stack" style="gap:6px"><b>If</b> <span class="note">All of these must be true. None: always.</span>${(A.if || []).map(condHtml).join('')}
      ${(A.if || []).length < 8 ? '<button type="button" class="small ghost" data-addif>Add a condition</button>' : ''}</div>
    <div class="stack" style="gap:6px"><b>Then</b> <span class="note">In this order. A flash goes back to what was showing.</span>${(A.then || []).map(actHtml).join('')}
      ${(A.then || []).length < 4 ? '<button type="button" class="small ghost" data-addthen>Add an action</button>' : ''}</div>
    <div class="row" style="gap:10px"><label class="field">Priority<select data-k="priority" style="width:auto">${[[100, 'Normal'], [200, 'High'], [300, 'Highest'], [50, 'Low']].map(([v, l]) => opt(v, A.priority, `${l} (${v})`)).join('')}${[50, 100, 200, 300].includes(A.priority) ? '' : opt(A.priority, A.priority, `Custom (${A.priority})`)}</select></label>
      <label class="field">Cooldown (seconds)<input type="number" data-k="cooldown" min="0" max="86400" value="${A.cooldown ?? 30}" style="width:7em"></label></div>
    <label class="check"><input type="checkbox" data-k="beats_manual" ${A.beats_manual ? 'checked' : ''}> Beats a manual choice (runs even when the lights were set by hand)</label>
    <p class="note" data-autosum>${esc(autoDescribe(A))}</p>`;
  const setPath = (k, el) => {
    const parts = k.split('.');
    if (parts[0] === 'if' && parts[2] === 'day') {
      const c = A.if[+parts[1]], j = +parts[3], set = new Set(c.days || []);
      if (el.checked) set.add(j); else set.delete(j);
      c.days = [...set].sort(); return;
    }
    let v = el.type === 'checkbox' ? el.checked : el.value;
    if (['seconds', 'minutes', 'priority', 'cooldown'].includes(parts[parts.length - 1])) v = v === '' ? undefined : Math.round(+v);
    if (k === 'when.on' || /^if\.\d+\.on$/.test(k)) v = v === 'true';
    let o = A;
    for (let i = 0; i < parts.length - 1; i++) o = o[/^\d+$/.test(parts[i]) ? +parts[i] : parts[i]];
    const last = parts[parts.length - 1];
    if (v === undefined || v === '') delete o[last]; else o[last] = v;
    if (last === 'type') {               // a new kind: start it clean
      const fresh = { flash: { seconds: 20 }, off: { minutes: 30 }, dark: { from: 'sunset', to: 'sunrise' }, days: { days: [4, 5, 6] },
        lights: { on: true }, score: { team: 'any' }, game_start: { team: 'any' }, game_end: { team: 'any', result: 'any' }, time: { at: 'sunset' } }[v] || {};
      const keep = parts[0] === 'then' ? { device: o.device } : {};
      Object.keys(o).forEach(x => delete o[x]); Object.assign(o, { type: v, ...fresh, ...keep });
      if (!['score', 'game_start', 'game_end'].includes(A.when.type)) A.if = A.if.filter(c => !GAME_ONLY.includes(c.type));
      return true;
    }
    if (/^then\.\d+\.effect$/.test(k) && v) delete o.color;
  };
  dialog(`<h2>${src ? 'Edit automation' : 'Add an automation'}</h2><div data-autoform class="stack" style="gap:12px">${body()}</div>`, async () => {
    const out = clone(A);
    out.name = (out.name || '').trim() || autoDescribe(out).slice(5, 50);
    (out.if || []).forEach(c => { if (c.type === 'dark') { c.from = c.from || 'sunset'; c.to = c.to || 'sunrise'; } });
    (out.then || []).forEach(x => { if (x.type === 'flash' && !x.effect && !x.color) x.color = '#FF6600'; });
    const n = clone(S.settings); n.automations = n.automations || [];
    if (src) n.automations[idx] = out; else n.automations.push(out);
    await saveSettings(n, src ? 'Automation saved' : 'Automation added');
    if (done) done();
  }, { ok: 'Save', onOpen: f => {
    const form = $('[data-autoform]', f);
    const redraw = () => { form.innerHTML = body(); };
    form.addEventListener('change', e => { const k = e.target.dataset.k; if (!k) return; if (setPath(k, e.target)) return redraw(); if (e.target.tagName === 'SELECT' && /effect$/.test(k)) return redraw(); $('[data-autosum]', form).textContent = autoDescribe(A); });
    form.addEventListener('input', e => { const k = e.target.dataset.k; if (k && e.target.type !== 'checkbox' && e.target.tagName === 'INPUT') { setPath(k, e.target); $('[data-autosum]', form).textContent = autoDescribe(A); } });
    form.addEventListener('click', e => {
      const b = e.target.closest('button'); if (!b) return; const d = b.dataset;
      if (d.addif !== undefined) A.if.push({ type: 'dark', from: 'sunset', to: 'sunrise' });
      else if (d.addthen !== undefined) A.then.push({ type: 'flash', seconds: 20 });
      else if (d.rmif !== undefined) A.if.splice(+d.rmif, 1);
      else if (d.rmthen !== undefined) A.then.splice(+d.rmthen, 1);
      else return;
      redraw();
    });
  } });
}

VIEWS.alerts = async () => {
  const m = $('#main'), s = S.settings, effs = s.effects || {}, admin = isAdmin();
  const ro = role() === 'viewer' ? 'disabled' : '';     // Viewers look but don't change (4.0.1)
  const weather = `<div class="panel stack"><div class="panel-head"><h2>Weather</h2><label class="check"><input type="checkbox" id="wxon" ${s.weather?.enabled ? 'checked' : ''} ${ro}> On</label></div>
          <p class="note">Uses the US National Weather Service. Weather only changes the pattern while a rule has the lights on.</p>
          <div class="list">${(s.weather_rules || []).map((r, i) => { const pats = Array.isArray(r.effect) ? r.effect : [r.effect]; const w = Array.isArray(r.when) ? r.when : r.when ? [r.when] : [];
            return `<div class="item"><div class="grow"><div class="row" style="gap:8px"><span class="name">${esc(r.name)}</span><span class="badge">${r.priority ?? 150}</span></div>
              <div class="sub">${esc([...w.map(x => (WX.find(y => y[0] === x) || [0, x])[1]), r.below_f !== undefined ? `below ${r.below_f}°F` : '', r.above_f !== undefined ? `above ${r.above_f}°F` : ''].filter(Boolean).join(', '))} → ${esc(pats.map(effLabel).join(' / '))}</div></div>
              ${ro ? '' : `<button class="small ghost" data-editwx="${i}">Edit</button><button class="small ghost danger" data-delwx="${i}">Delete</button>`}</div>`; }).join('') || '<p class="muted">No weather rules.</p>'}</div>
          <div class="row">${ro ? '' : '<button class="small" data-addwx>Add a weather rule</button>'}
            <label class="row small">Check with<select id="wxuse" style="width:auto" ${ro}>${[['either', 'now or next hour'], ['observed', 'current conditions'], ['forecast', 'next-hour forecast']].map(([k, l]) => `<option value="${k}" ${(s.weather?.use || 'either') === k ? 'selected' : ''}>${l}</option>`).join('')}</select></label></div>
        </div>
`;
  const security = `<div class="panel stack"><h2>Security flash</h2><p class="note">Bright lights on demand from Home, a webhook or Home Assistant, then back to normal. Changes save as you make them.</p>
          <div class="row"><label class="field grow">Pattern<select id="secp" ${ro}><option value="">Off</option>${Object.keys(effs).map(k => `<option value="${esc(k)}" ${s.security?.effect === k ? 'selected' : ''}>${esc(effLabel(k))}</option>`).join('')}</select></label>
            <label class="field">Minutes<input type="number" id="secm" min="1" max="240" value="${s.security?.minutes ?? 5}" ${ro}></label></div></div>`;
  m.innerHTML = `<div class="view">
    <div class="panel-head"><h2>Alerts</h2><span class="muted small">What changes the lights when something happens: the weather, a warning, a camera or alarm, a button.</span></div>
    <div class="stack">
      ${fold('autos', 'Automations (When \u00b7 If \u00b7 Then)', '<div class="panel stack" id="autobox"><p class="muted small">Loading\u2026</p></div>', wide())}
      ${fold('weather', 'Weather', weather, wide())}
      ${fold('wxalerts', 'Severe weather alerts', '<div class="panel stack" id="wxalertbox"><p class="muted small">Loading…</p></div>')}
      ${fold('security', 'Security flash', security)}
      ${admin ? fold('webhooks', 'Webhooks (Home Assistant, cameras, alarms)', '<div class="panel stack" id="hookbox"><p class="muted small">Loading…</p></div>') : ''}
      ${admin ? fold('phone', 'Phone alerts', '<div class="panel stack" id="alertbox"><p class="muted small">Loading…</p></div>') : ''}
    </div>
    <p class="note" style="margin-top:14px">Flashing a team\u2019s colors when it scores is set per team under Schedule \u203a Game-day lights.</p></div>`;
  whenOpen('wxalerts', () => wxAlertPanel($('#wxalertbox')));
  whenOpen('autos', () => autoPanel($('#autobox')));
  if (admin) { whenOpen('webhooks', () => webhookPanel($('#hookbox'))); whenOpen('phone', () => alertPanel($('#alertbox'))); }
  m.onclick = async e => {
    const b = e.target.closest('button'); if (!b) return; const d = b.dataset;
    if (d.addwx !== undefined) weatherDialog();
    else if (d.editwx) weatherDialog(+d.editwx);
    else if (d.delwx) { const n = clone(S.settings); n.weather_rules.splice(+d.delwx, 1); await busy(b, () => saveSettings(n, 'Deleted')).catch(() => {}); VIEWS.alerts(); }
  };
  m.onchange = e => {
    if (ro) return;
    if (e.target.id === 'wxon' || e.target.id === 'wxuse') {
      const n = clone(S.settings); n.weather = { ...(n.weather || {}), enabled: $('#wxon').checked, use: $('#wxuse').value };
      busy(null, () => saveSettings(n, n.weather.enabled ? 'Weather rules on' : 'Weather rules off')).catch(() => {});
    }
    // 4.0: the security flash saves as you change it, like everything else.
    if (e.target.id === 'secp' || e.target.id === 'secm') {
      const n = clone(S.settings); n.security = { effect: $('#secp').value || null, minutes: Math.max(1, Math.min(240, +$('#secm').value || 5)) };
      busy(null, () => saveSettings(n, n.security.effect ? 'Security flash saved' : 'Security flash off')).catch(() => {});
    }
  };
};

/* Alerts › Webhooks: the token, examples, and a test alert (from Settings, 4.0). */
async function webhookPanel(box) {
  if (!box) return;
  let a; try { a = S.account = await api('account'); } catch (e) { box.innerHTML = `<p class="muted small">${esc(e.message)}</p>`; return; }
  foldSums();
  box.innerHTML = `<h2>Webhooks</h2>
    <p class="note">Let Home Assistant, IFTTT, a camera (Frigate, Blue Iris) or a motion sensor trigger the lights, for example a security flash at night or a green flash on the porch for a package.</p>
    <label class="check"><input type="checkbox" id="hook" ${a.webhook_token ? 'checked' : ''}> Allow webhooks</label>
    ${a.webhook_token ? `<label class="field">Token <span class="hint">Treat it like a password.</span><input type="text" readonly value="${esc(a.webhook_token)}" id="htok"></label>
      <div class="row"><button class="small" data-copy="htok">Copy token</button><button class="small ghost" data-regen>Make a new token</button></div>
      <p class="small">Example:</p><pre class="code">curl -X POST -H "X-Token: ${esc(a.webhook_token)}" \\\n  http://${esc(a.addresses[0] || 'THIS-PC')}:${a.port}/api/hook/flash</pre>
      <p class="note">Actions: flash, stop_flash, on (with {"effect": "name"}), off, resume, levels, dismiss_alert. Send the token in the X-Token header, or as "token" in a JSON body for services that can't set headers. Tokens in the web address are refused.</p>
      <p class="small">An alert with its own pattern, length and zone (for example a package at the front door):</p><pre class="code">curl -X POST -H "X-Token: ${esc(a.webhook_token)}" \\\n  -H "Content-Type: application/json" \\\n  -d '{"effect": "package", "zone": "Front porch", "seconds": 30}' \\\n  http://${esc(a.addresses[0] || 'THIS-PC')}:${a.port}/api/hook/flash</pre>
      <p class="note"><b>effect</b>: one of your patterns, or an alert pattern: package, alarm, doorbell, delivery, severe, security. Or send <b>color</b> (like "#00FF00") instead. <b>zone</b>: a zone from the House tab (optional). <b>seconds</b>: 5 to 14400 (30 if left out).</p>
      <div id="trybox"></div>` : ''}`;
  tryAlertPanel($('#trybox', box));
  box.onchange = e => {
    if (e.target.id === 'hook') busy(null, () => api('webhook', { body: { enable: e.target.checked } })).then(() => webhookPanel(box)).catch(() => { e.target.checked = !e.target.checked; });
  };
  box.onclick = async e => {
    const b = e.target.closest('button'); if (!b) return;
    if (b.dataset.regen !== undefined) { e.stopPropagation();
      if (await confirmBox('Make a new token?', 'Anything using the old token stops working until you update it.', 'Make new token'))
        busy(b, () => api('webhook', { body: { enable: true } })).then(() => webhookPanel(box)).catch(() => {}); }
    if (b.dataset.copy) { e.stopPropagation(); const el = $('#' + b.dataset.copy); el.select();
      const manual = () => toast(/Mac|iPhone|iPad|iOS/i.test(navigator.userAgentData?.platform || navigator.userAgent) ? 'Selected. Press \u2318C to copy.' : 'Selected. Press Ctrl+C to copy.');
      if (navigator.clipboard?.writeText) navigator.clipboard.writeText(el.value).then(() => toast('Copied'), manual); else manual(); }
  };
}

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
  const search = () => {
    if ($('#lq', box).value.trim().length < 2) {          // 4.3.9: no request (and no error) for an empty box
      $('#lres', box).innerHTML = '<p class="muted small">Type a town or ZIP code first.</p>'; $('#lq', box).focus(); return;
    }
    return realSearch();
  };
  const realSearch = () => busy($('#lgo', box), async () => {
    const r = await api('geocode?q=' + encodeURIComponent($('#lq', box).value.trim()));
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
/* Home › Controllers (4.5): one card per controller, as the Trimlight app's
   first screen lists them, each with its own home-network address (Trimlight's
   cloud doesn't report it; the app checks every few minutes it answers there). */
/* 4.8: what one controller shows, and its own On, Off and pattern. The top
   buttons still mean all of them. */
function ownPart(st, id) {
  const t = st.target || {}, p = t.parts && t.parts[id];
  return p ? p : { on: t.on, effect: t.effect, rule: t.reason === 'schedule' || t.reason === 'weather' ? t.source : null,
    manual: t.reason === 'manual', until: t.until };
}
function ownLine(st, id) {
  const p = ownPart(st, id);
  const by = p.manual ? ' \u00b7 chosen by hand' : p.rule ? ` \u00b7 ${esc(p.rule)}` : '';
  return `<div class="sub ownline">${p.on ? `Showing <b>${esc(p.effect || 'a pattern')}</b>${by}${p.until ? ` until ${esc(p.until)}` : ''}` : `Off${by}`}</div>`;
}
function ownControls(st, id) {
  const p = ownPart(st, id), effs = st.effects || [];
  return `<div class="row owncontrols" style="margin-top:8px;gap:6px">
    <button class="small" data-one="on" data-dev="${esc(id)}">On</button><button class="small ghost" data-one="off" data-dev="${esc(id)}">Off</button>
    <select data-onepat="${esc(id)}" aria-label="Pattern for this controller" style="width:auto;max-width:100%"><option value="">Show a pattern\u2026</option>
      ${effs.map(e => `<option value="${esc(e.key)}">${esc(e.label)}</option>`).join('')}</select>
    ${(st.target && st.target.parts && p.manual) ? `<button class="small ghost" data-one="schedule" data-dev="${esc(id)}">Back to schedule</button>` : ''}</div>`;
}
function controllerCards(st) {
  const lan = st.lan || {}, homes = lan.devices || {}, admin = role() === 'admin';
  const live = st.devices || [], account = st.account || [], ours = st.controlled || live.map(d => d.id);
  const card = d => {
    const h = homes[d.id];
    const net = h ? `<b class="num">${esc(h.address)}</b> · ${h.ok === true ? '<span class="ok">answering</span>' : h.ok === false ? '<span class="bad">not answering</span>' : '<span class="muted">checking…</span>'}`
      : `<span class="muted">not set</span>${admin ? ' (<a href="#local">Setup › Local mode</a>)' : ''}`;
    // 4.7.1: with two or more, the ones this app runs are marked Active (green)
    // and the rest greyed out, like the Trimlight app's controller list.
    const state = many ? (d.idle ? 'idle' : 'active') : '';
    const tag = state === 'active' ? '<span class="pill ok">Active</span>'
      : state === 'idle' ? `<span class="badge">Not run by this app</span>` : '';
    return `<div class="item ${state}"><div class="grow"><div class="name">${esc(d.name || 'Controller')} ${tag}
        ${d.error || d.unknown || d.idle ? '' : `<span class="badge ${d.online ? 'hi' : ''}">${d.online ? 'Online' : 'Offline'}</span> <span class="small">${esc(d.switch || '')}</span>`}</div>
      ${d.error ? `<div class="sub warning">${esc(d.error)}</div>` : ''}
      ${d.idle ? `<div class="sub">This app leaves it alone${admin ? '; to run it too, turn it on in <a href="#lights">Setup › Lights &amp; controller › Controlled by this app</a>' : ''}.</div>` : ''}
      ${state === 'active' ? ownLine(st, d.id) : ''}
      <div class="sub">Home network: ${net}${d.firmware ? ` · firmware ${esc(d.firmware)}` : ''}</div>
      ${state === 'active' && role() !== 'viewer' ? ownControls(st, d.id) : ''}</div></div>`;
  };
  // Controllers the cloud hasn't reported on yet still show with their
  // address; the ones on the account that this app doesn't run come last.
  const shown = new Set(live.map(d => d.id));
  const devs = [...live];
  for (const [id, h] of Object.entries(homes)) {
    if (shown.has(id)) continue;
    shown.add(id);
    devs.push({ id, name: h.name, error: null, online: null, unknown: true, idle: account.some(a => a.id === id) && !ours.includes(id) });
  }
  for (const a of account) {
    if (shown.has(a.id)) continue;
    shown.add(a.id);
    devs.push({ id: a.id, name: a.name, error: null, online: null, unknown: true, idle: !ours.includes(a.id) });
  }
  devs.sort((a, b) => !!a.idle - !!b.idle);
  const many = devs.length > 1;
  return `<div class="panel ctlcards"><h2>${many ? `Controllers (${devs.length})` : 'Controller'}</h2>
    ${lan.unassigned && admin ? `<p class="callout small">The home-network address saved before, <b class="num">${esc(lan.unassigned)}</b>, isn’t known to be any one controller’s yet. Choose which in <a href="#local">Setup › Local mode</a>.</p>` : ''}
    <div class="list">${devs.map(card).join('') || '<p class="muted small">No controller reported yet.</p>'}</div></div>`;
}

/* Music › Music from this computer (4.1, experimental). This browser
   listens (a microphone or line-in, or the computer's own sound), turns it
   into 16 sound levels (bands.js) and sends them about 9 times a second; the
   app passes them to the controller over the home network, the way the
   Trimlight app does from a phone, so the lights move to the beat. Like
   mood follow it needs the page on the app computer (a browser only allows
   listening on the computer itself or a secure page). */
const LINK = { on: false, stream: null, ctx: null, node: null, timer: null, edges: null, lv: null, busy: false,
               tab: '', err: '', st: null, sent: 0, devices: [], since: 0, out: '', gain: 0 };
function linkOpts() {
  let o = {};
  try { o = JSON.parse(localStorage.getItem('linkopts') || '{}') || {}; } catch { o = {}; }
  return { input: typeof o.input === 'string' ? o.input : 'default', pattern: Number.isInteger(o.pattern) ? o.pattern : 0,
           sensitivity: Number.isInteger(o.sensitivity) ? o.sensitivity : 8, gain: Number.isFinite(o.gain) ? o.gain : 0,
           color: typeof o.color === 'string' && /^#[0-9a-f]{6}$/i.test(o.color) ? o.color : '#ff0000',
           minutes: Number.isInteger(o.minutes) ? o.minutes : 60,
           // 4.13: what the lights follow (the controller's music patterns, or zones), the sound's delay, the zones' controllers
           engine: o.engine === 'zones' ? 'zones' : 'patterns', delay: Number.isInteger(o.delay) ? Math.max(0, Math.min(1000, o.delay)) : 0,
           zdevs: Array.isArray(o.zdevs) ? o.zdevs.filter(x => typeof x === 'string') : [] };
}
function linkSave(o) { try { localStorage.setItem('linkopts', JSON.stringify(o)); } catch { /* private window */ } }
// Firefox and browsers built on it (LibreWolf, Waterfox) can share a screen
// but never its sound (4.1.3).
const SHARES_SOUND = !/Firefox\//.test(navigator.userAgent);
async function linkListen(input, holdBack) {
  if (input === 'file') return null;                  // 4.13: played here (linkStart)
  if (input === 'screen') {
    if (!SHARES_SOUND) throw new Error('This browser (Firefox or one built on it, like LibreWolf) can\u2019t share a tab\u2019s sound. Choose Stereo Mix under Listen to (see the note below), or open the app in Microsoft Edge or Chrome for tab sharing.');
    if (!navigator.mediaDevices.getDisplayMedia) throw new Error('This browser can\u2019t share the computer\u2019s sound. Use Chrome or Edge, or choose a microphone or line-in.');
    // 4.1.3: open on the list of tabs. A tab playing music shares its sound
    // with "Also share tab audio", which is on by default; "Also share system
    // audio" only appears for Entire screen, and not on every computer.
    const s = await navigator.mediaDevices.getDisplayMedia({
      video: { displaySurface: 'browser' },
      // 4.13: with a sound delay, the tab goes quiet and this page plays its sound, held back to match the lights
      audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false, suppressLocalAudioPlayback: !!holdBack },
      systemAudio: 'include', windowAudio: 'system', selfBrowserSurface: 'exclude', surfaceSwitching: 'include', preferCurrentTab: false });
    s.getVideoTracks().forEach(t => t.stop());
    if (!s.getAudioTracks().length) {
      s.getTracks().forEach(t => t.stop());
      throw new Error('No sound was shared. Start again and pick the browser tab that\u2019s playing the music (keep \u201cAlso share tab audio\u201d on). Or, for everything this computer plays, use Stereo Mix (see the note below).');
    }
    return s;
  }
  const audio = { echoCancellation: false, noiseSuppression: false, autoGainControl: false };
  if (input && input !== 'default') audio.deviceId = { exact: input };
  return navigator.mediaDevices.getUserMedia({ audio });
}
/* 4.13: zones that follow the music, for each controller chosen: the
   House tab's zones for it and what each follows (Music › My zones). */
const zName = d => (((LINK.zs || {}).devices || {})[d] || {}).name || devName(d);
function zoneSetup(dev) {
  const md = mapData(), mz = S.settings.music_zones || {};
  const zones = md.zones.filter(z => forDev(z, dev));
  const maps = (mz.maps || []).map(m => ({ ...m, zone: zones.findIndex(z => z.name === m.zone && (z.device || null) === (m.device || null)) }))
    .filter(m => m.zone >= 0);
  return { zones, maps, base: mz.base || '#000000', total: addressSpace(dev), perSlot: (S.status && S.status.slot_limit) || PER_SLOT };
}
async function linkStart() {
  const o = linkOpts(), zones = o.engine === 'zones';
  LINK.tab = LINK.tab || Math.random().toString(36).slice(2, 12);
  LINK.err = ''; LINK.out = ''; LINK.zst = null; LINK.engine = o.engine;
  const fromFile = o.input === 'file', tabSound = o.input === 'screen';
  if (fromFile && !(LINK.files || []).length) throw new Error('Choose a music file first (Music file).');
  const devs = zones ? o.zdevs.filter(d => ((LINK.zs || {}).devices || {})[d]) : [];
  if (zones && !devs.length) throw new Error('Tick the controller (or controllers) whose zones follow the music.');
  // Each controller's own number of bulbs: a frame for fewer would repeat along the rest of its lights
  if (zones) { await loadDevices().catch(() => {}); for (const d of devs) if (!(S.devices || []).some(x => x.id === d && x.ports))
    throw new Error(`${zName(d)}\u2019s number of bulbs isn\u2019t known yet. Open Setup \u203a Lights & controller once.`); }
  if (zones) for (const d of devs) {
    const z = zoneSetup(d), need = MusicZones.worst(z);
    if (!z.maps.some(m => m.follows !== 'off')) throw new Error(`Choose what ${zName(d)}’s zones follow first.`);
    if (need > MAX_SLOTS) throw new Error(`${zName(d)}: these choices can need ${need} color blocks; a controller takes ${MAX_SLOTS}. Use fewer meters or zones.`);
  }
  const stream = await linkListen(o.input, o.delay > 0);
  try {
    if (zones) LINK.zst = await api('musiczones', { body: { op: 'start', tab: LINK.tab, devices: devs, minutes: o.minutes } });
    else LINK.st = await api('musiclink', { body: { op: 'start', tab: LINK.tab, pattern: o.pattern, sensitivity: o.sensitivity, minutes: o.minutes, color: o.color } });
  } catch (e) { if (stream) stream.getTracks().forEach(t => t.stop()); throw e; }
  const ctx = new (window.AudioContext || window.webkitAudioContext)(), an = ctx.createAnalyser();
  let src, audio = null, held = false;
  if (fromFile) {
    audio = new Audio(); audio.preload = 'auto'; LINK.fileAt = LINK.fileAt || 0;
    const play = i => { LINK.fileAt = (i + LINK.files.length) % LINK.files.length; if (audio.src) URL.revokeObjectURL(audio.src);
      audio.src = URL.createObjectURL(LINK.files[LINK.fileAt]); audio.play().catch(() => {}); const n = $('#lknow'); if (n) n.textContent = LINK.files[LINK.fileAt].name; };
    audio.onended = () => play(LINK.fileAt + 1);
    src = ctx.createMediaElementSource(audio); LINK.play = play; held = true;
  } else {
    src = ctx.createMediaStreamSource(stream);
    // The tab's own sound went quiet only if the browser could do that; otherwise playing it here would double it.
    held = tabSound && o.delay > 0 && stream.getAudioTracks().some(t => (t.getSettings && t.getSettings().suppressLocalAudioPlayback) === true);
    if (tabSound && o.delay > 0 && !held) LINK.err = 'This browser can’t hold the tab’s sound back, so the sound delay isn’t used. Microsoft Edge and Chrome can.';
  }
  an.fftSize = 2048; an.smoothingTimeConstant = 0.5; src.connect(an);
  if (held) {                                  // what you hear, held back by the sound delay (4.13)
    const delay = ctx.createDelay(2); delay.delayTime.value = o.delay / 1000;
    src.connect(delay); delay.connect(ctx.destination); LINK.delayNode = delay;
  }
  if (ctx.state === 'suspended') await ctx.resume().catch(() => {});
  const fd = new Float32Array(an.frequencyBinCount);
  Object.assign(LINK, { on: true, stream, ctx, audio, held, edges: Bands.edges(ctx.sampleRate, an.fftSize), sent: 0, since: Date.now(), gain: o.gain,
    beat: Beat.create(ctx.sampleRate, an.fftSize), music: null, devs, zfps: 4, rtt: [] });
  if (stream) stream.getTracks().forEach(t => t.addEventListener('ended', () => { if (LINK.on) { LINK.err = 'The sound stopped being shared.'; linkStop(); } }));
  if (fromFile) LINK.play(LINK.fileAt);
  let last = 0, lastFrame = 0, lastAn = 0;
  const tick = () => {
    if (!LINK.on) return;
    const now = performance.now();
    // 4.13: the analysis runs with every bit of sound (beats need it often); levels and frames go out at their own pace
    if (now - lastAn >= 15) {
      lastAn = now;
      an.getFloatFrequencyData(fd);
      LINK.music = Beat.step(LINK.beat, fd, ctx.currentTime);
      if (LINK.sync && ctx.currentTime >= LINK.sync.next) syncTick(ctx);
      linkMeters();
    }
    if (zones) {
      if (now - lastFrame < 1000 / Math.max(2, LINK.zfps) || LINK.busy) return;
      lastFrame = now;
      const music = LINK.sync && ctx.currentTime < LINK.sync.flashUntil ? { bass: 1, mid: 1, treble: 1, pulse: 1 } : LINK.music;
      const frames = {};
      try {
        for (const d of LINK.devs) {
          const z = zoneSetup(d), maps = LINK.sync && ctx.currentTime < LINK.sync.flashUntil ? z.maps.map(m => ({ ...m, color: '#FFFFFF', follows: m.follows === 'off' ? 'off' : 'beat' })) : z.maps;
          const f = MusicZones.frame({ ...z, maps, music, maxSlots: MAX_SLOTS });
          frames[d] = { colors: f.colors, counts: f.counts };
        }
      } catch (e) { LINK.err = e.message; return linkStop(); }
      LINK.busy = true;
      const t0 = performance.now();
      api('musiczones', { body: { op: 'frame', tab: LINK.tab, frames } })
        .then(r => {
          LINK.sent++; LINK.rtt = [...LINK.rtt.slice(-19), performance.now() - t0];
          const ds = Object.values(r.devices || {}).filter(x => x.running);
          if (ds.length) { LINK.zfps = Math.min(...ds.map(x => x.fps)); LINK.ctlms = Math.max(...ds.map(x => x.ms || 0)); }
          if (r.running === false && LINK.on) { LINK.err = 'The show ended in the app.'; linkStop(false); }
        })
        .catch(e => { if (LINK.on) { LINK.err = e.message; linkStop(false); } })
        .finally(() => { LINK.busy = false; });
      return;
    }
    if (now - last < 100) return;
    last = now;
    LINK.lv = Bands.levels(fd, LINK.edges, LINK.gain);     // 4.1.4: kept in memory, not read from storage 10 times a second
    const bars = $('#linkbars');
    if (bars) [...bars.children].forEach((b, i) => { b.style.height = Math.max(2, LINK.lv[i] / 255 * 100) + '%'; });
    if (LINK.busy) return;                  // never let requests pile up
    LINK.busy = true;
    const t0 = performance.now();
    api('musiclink', { body: { op: 'levels', tab: LINK.tab, levels: LINK.lv } })
      .then(r => { LINK.sent++; LINK.rtt = [...LINK.rtt.slice(-19), performance.now() - t0];
        if (r && r.running === false && LINK.on) { LINK.err = 'The show ended in the app.'; linkStop(false); } })
      .catch(e => { if (LINK.on) { LINK.err = e.message; linkStop(false); } })
      .finally(() => { LINK.busy = false; });
  };
  // As with mood follow: the audio thread keeps going in a background tab,
  // where timers slow down; the timer is the backup.
  if (ctx.createScriptProcessor) {
    const node = ctx.createScriptProcessor(1024, 1, 1), mute = ctx.createGain();
    mute.gain.value = 0; src.connect(node); node.connect(mute); mute.connect(ctx.destination);
    node.onaudioprocess = tick;
    LINK.node = node;
  }
  LINK.timer = setInterval(tick, 20);
}
/* 4.13: Sync test. A click every second, through the same sound delay as the
   music, and every zone flashes white with it. Move Sound delay until the
   flashes land on the clicks. */
function syncTick(ctx) {
  const t = LINK.sync.next, osc = ctx.createOscillator(), g = ctx.createGain();
  osc.frequency.value = 1800; g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(0.6, t + 0.004); g.gain.exponentialRampToValueAtTime(0.0001, t + 0.06);
  osc.connect(g); g.connect(LINK.delayNode || ctx.destination); osc.start(t); osc.stop(t + 0.08);
  LINK.sync.flashUntil = t + 0.18; LINK.sync.next = t + 1;
}
/* The suggested sound delay: half the page's round trip, the controller's
   own answer time and a little for it to change the lights. */
function linkSuggest() {
  const r = LINK.rtt || []; if (r.length < 5) return null;
  const med = [...r].sort((a, b) => a - b)[Math.floor(r.length / 2)];
  return Math.round((med / 2 + (LINK.ctlms || 0) / 2 + 60) / 10) * 10;
}
function linkMeters() {
  const box = $('#lkmeters'); if (!box || !LINK.music) return;
  const M = LINK.music;
  for (const k of ['bass', 'mid', 'treble']) { const el = $(`[data-m="${k}"] i`, box); if (el) el.style.width = Math.round(M[k] * 100) + '%'; }
  const dot = $('[data-m="beat"]', box); if (dot) dot.style.opacity = String(0.15 + 0.85 * M.pulse);
  const bpm = $('[data-m="bpm"]', box); if (bpm) bpm.textContent = M.bpm ? `${Math.round(M.bpm)} BPM${M.conf < 0.35 ? ' (unsure)' : ''}` : 'Finding the tempo…';
  const fr = $('[data-m="fps"]', box);
  if (fr && LINK.engine === 'zones') fr.textContent = `${LINK.zfps} frames a second${LINK.ctlms ? ` · the controller answers in ${LINK.ctlms} ms` : ''}`;
  const sg = $('[data-m="suggest"]', box); const v = linkSuggest(); if (sg && v !== null) sg.textContent = `Suggested from this show: about ${v} ms.`;
}
function linkStop(tell = true) {
  clearInterval(LINK.timer);
  if (LINK.node) LINK.node.onaudioprocess = null;
  if (LINK.stream) LINK.stream.getTracks().forEach(t => t.stop());
  if (LINK.audio) { LINK.audio.pause(); if (LINK.audio.src) URL.revokeObjectURL(LINK.audio.src); }
  if (LINK.ctx) LINK.ctx.close().catch(() => {});
  const was = LINK.on, engine = LINK.engine;
  Object.assign(LINK, { on: false, stream: null, ctx: null, node: null, timer: null, lv: null, audio: null, delayNode: null, sync: null, music: null });
  if (tell && was) api(engine === 'zones' ? 'musiczones' : 'musiclink', { body: { op: 'stop', tab: LINK.tab } }).catch(() => {});
  linkPanel($('#linkbox'));
  moodPanel($('#moodbox'));
}
window.addEventListener('pagehide', () => { if (LINK.on) { const e = LINK.engine; linkStop(false); api(e === 'zones' ? 'musiczones' : 'musiclink', { body: { op: 'stop', tab: LINK.tab }, keepalive: true }).catch(() => {}); } });
async function linkPanel(box, fresh = true) {
  if (!box) return;
  // 4.1.3: draw at once from the last answer, so the page doesn't jump while
  // it asks again (the Music tab redraws only when the show changes now).
  if (fresh) {
    if (LINK.st && !box.innerHTML.trim()) linkPanel(box, false);
    try { [LINK.st, LINK.zs] = await Promise.all([api('musiclink'), api('musiczones')]); }
    catch (e) { if (!LINK.st) box.innerHTML = `<h2>Music from this computer</h2><p class="callout warn small">${esc(e.message)}</p>`; return; }
    if (!document.body.contains(box)) return;
  }
  const st = LINK.st;
  if (!st) return;
  const o = linkOpts(), admin = role() === 'admin', ro = role() === 'viewer';
  const pats = [], sens = [];
  for (let i = st.patterns[0]; i <= st.patterns[1]; i++) pats.push(i);
  for (let i = st.sensitivity[0]; i <= st.sensitivity[1]; i++) sens.push(i);
  if (moodAvailable() && navigator.mediaDevices.enumerateDevices && !LINK.devices.length) {
    navigator.mediaDevices.enumerateDevices().then(ds => {
      LINK.devices = ds.filter(d => d.kind === 'audioinput' && d.deviceId && d.deviceId !== 'default');
      if (LINK.devices.length && !LINK.on && !box.contains(document.activeElement)) linkPanel(box, false);
    }).catch(() => {});
  }
  const running = LINK.on || (st.running && st.host);
  const addr = admin ? `<div class="row">
      <label class="field" style="flex:1;min-width:180px">Controller\u2019s address on your home network<input type="text" id="lkaddr" value="${esc(st.address)}" placeholder="e.g. 192.168.1.50" inputmode="decimal" ${running ? 'disabled' : ''}></label>
      <button class="small" data-lksave ${running ? 'disabled' : ''}>Save</button>
      <button class="small ghost" data-lkfind ${running ? 'disabled' : ''}>Find</button>
      <button class="small ghost" data-lktest ${running || !st.address ? 'disabled' : ''}>Test connection</button>
      <button class="small ghost" data-lkread ${running || !st.address ? 'disabled' : ''}>Read the controller</button></div>
      <p class="hint">The Trimlight app shows it when it opens (for example 192.168.1.50); your router\u2019s device list shows it too. Reserve it in the router so it doesn\u2019t change. <b>Test connection</b> only says hello. <b>Read the controller</b> also sets the controller\u2019s clock and lists what it holds, as the Trimlight app does each time it opens.</p>
      <div id="lkout">${LINK.out || ''}</div>`
    : `<p class="note">Controller\u2019s address: <b>${st.address ? esc(st.address) : 'not set yet'}</b>${st.address ? '' : ' (an Administrator enters it here)'}.</p>`;
  const inputs = [['default', 'Default microphone or line-in'], ...LINK.devices.map(d => [d.deviceId, d.label || 'Microphone']),
                  ['screen', `Music playing in a browser tab (share the tab)${SHARES_SOUND ? '' : ' \u2013 Edge or Chrome only'}`],
                  ['file', 'A music file on this computer (played here)']];
  const zs = LINK.zs || { devices: {} }, zones = o.engine === 'zones';
  if (zones && !S.devices && !LINK.loadingDevs) { LINK.loadingDevs = true; loadDevices().catch(() => {}).finally(() => { LINK.loadingDevs = false; if (S.devices) linkPanel(box, false); }); }
  const zdevs = Object.entries(zs.devices), canDelay = o.input === 'file' || o.input === 'screen';
  const zonesOk = zdevs.some(([d, v]) => o.zdevs.includes(d) && v.address && (v.tested || {}).fps);
  const startOff = ro || !moodAvailable() || MOOD.on || st.show || (zones ? !zonesOk : !st.address);
  box.innerHTML = `<div class="panel-head"><h2>Music from this computer</h2>
      ${LINK.on ? '<button class="small danger" data-lkstop>Stop</button>'
        : `<button class="small primary" data-lkgo ${startOff ? 'disabled' : ''}>Start the show</button>`}</div>
    <p class="note">The lights dance to music this computer hears or plays, beat by beat, with no phone: this app talks to the controller directly on your home network, the way the Trimlight app does in music mode. Choose the music pattern and sensitivity here instead of in the Trimlight app.</p>
    ${addr}
    <div class="row" role="group" aria-label="What the lights follow"><span class="small">The lights follow</span>
      <button class="small ${!zones ? 'current' : 'ghost'}" data-lkeng="patterns" ${LINK.on ? 'disabled' : ''}>The controller\u2019s music patterns</button>
      <button class="small ${zones ? 'current' : 'ghost'}" data-lkeng="zones" ${LINK.on ? 'disabled' : ''}>My zones (bass, mids, treble, beat)</button></div>
    <div class="grid3">
      <label class="field">Listen to<select id="lkin" ${LINK.on || ro ? 'disabled' : ''}>${inputs.map(([v, l]) => `<option value="${esc(v)}" ${o.input === v ? 'selected' : ''}>${esc(l)}</option>`).join('')}</select></label>
      ${o.input === 'file' ? `<label class="field">Music file${(LINK.files || []).length > 1 ? 's' : ''}<input type="file" id="lkfile" accept="audio/*" multiple ${ro ? 'disabled' : ''}>
        <span class="hint" id="lknow">${(LINK.files || []).length ? esc(LINK.files[LINK.fileAt || 0].name) + ((LINK.files || []).length > 1 ? ` (1 of ${LINK.files.length})` : '') : 'Your own MP3, WAV or M4A; nothing is uploaded.'}</span></label>` : ''}
      ${zones ? '' : `<label class="field">Music pattern<select id="lkpat" ${ro ? 'disabled' : ''}>${pats.map(i => `<option value="${i}" ${o.pattern === i ? 'selected' : ''}>${i + 1}. ${esc((st.names || [])[i] || '')}</option>`).join('')}</select></label>
      ${(st.single || []).includes(o.pattern) ? `<label class="field">Color<input type="color" id="lkcolor" value="${esc(o.color)}" ${ro ? 'disabled' : ''}></label>` : ''}`}
      <label class="field">How long<select id="lklen" ${LINK.on || ro ? 'disabled' : ''}>${SHOW_LENGTHS.map(([v, l]) => `<option value="${v}" ${o.minutes === v ? 'selected' : ''}>${esc(l)}</option>`).join('')}</select></label></div>
    ${zones ? zonesHtml(zs, o, ro) : ''}
    <div class="grid3">
      ${zones ? '' : `<label class="field">Sensitivity <span class="muted small" id="lksensv">${o.sensitivity}</span><input type="range" id="lksens" min="${sens[0]}" max="${sens[sens.length - 1]}" value="${o.sensitivity}" ${ro ? 'disabled' : ''}></label>`}
      <label class="field">Sound delay <span class="muted small" id="lkdelayv">${o.delay} ms</span><input type="range" id="lkdelay" min="0" max="1000" step="10" value="${o.delay}" ${ro || (LINK.on && !LINK.held) ? 'disabled' : ''}></label>
      <label class="field">Input level <span class="muted small" id="lkgainv">${o.gain > 0 ? '+' : ''}${o.gain} dB</span><input type="range" id="lkgain" min="-18" max="18" step="3" value="${o.gain}" ${ro ? 'disabled' : ''}></label></div>
    <p class="hint">${canDelay ? '<b>Sound delay</b> holds back what you hear so it lands with the lights, which trail the music by the time it takes to reach the controller. ' + (zones ? 'Start the show, tap <b>Sync test</b> and move it until the flashes land on the clicks.' : 'Start at the suggestion shown during the show and adjust by ear.') : 'A microphone, line-in or Stereo Mix is heard in the room as it plays, so its sound can\u2019t be held back; Sound delay is for a browser tab\u2019s sound and music files.'}</p>
    ${LINK.on ? `<div class="meters" id="lkmeters" aria-live="off">
        ${['bass', 'mid', 'treble'].map(k => `<div class="mband" data-m="${k}"><span>${{ bass: 'Bass', mid: 'Mids', treble: 'Treble' }[k]}</span><b><i></i></b></div>`).join('')}
        <div class="row small"><span class="beatdot" data-m="beat" aria-hidden="true"></span><b data-m="bpm">Finding the tempo\u2026</b><span class="muted" data-m="fps"></span></div>
        <p class="small muted" data-m="suggest"></p>
        <div class="row">${zones && LINK.held ? `<button class="small" data-lksync>${LINK.sync ? 'Stop the sync test' : 'Sync test'}</button>` : ''}
          ${LINK.audio ? '<button class="small ghost" data-lkpause>Pause / play</button><button class="small ghost" data-lknext>Next file</button>' : ''}</div></div>` : ''}
    ${LINK.on && !zones ? `<div class="bars" id="linkbars" aria-hidden="true">${Array.from({ length: 16 }, () => '<i></i>').join('')}</div>
      <p class="small">Sending to <b>${esc(st.host || st.address)}</b>. Keep this page open (a background tab is fine). Stop here, or choose a pattern, and the schedule comes back; if this page closes or goes quiet for 20 seconds, the show ends by itself.</p>` : ''}
    ${!moodAvailable() ? `<p class="callout small">A browser only lets a page listen on the computer itself. Open EaveLuxOS on the app computer (<b>${location.protocol}//localhost:${location.port || 8787}</b>) and start it there.</p>` : ''}
    ${MOOD.on ? '<p class="callout small">Mood follow is listening. Stop it first: both can\u2019t run the lights at once.</p>' : ''}
    ${st.show && !LINK.on ? '<p class="callout small">A music show is already on. Stop it above first.</p>' : ''}
    ${LINK.err || st.error ? `<p class="callout warn small">${esc(LINK.err || st.error)}</p>` : ''}
    <p class="hint"><b>Music in a browser tab</b> (YouTube, Spotify\u2019s web player): play it in another tab, start the show and pick that tab; keep \u201cAlso share tab audio\u201d on. <b>Everything this computer plays</b> (the Spotify app, a playlist): in Windows, open Sound settings \u203a More sound settings \u203a Recording, right-click \u203a Show disabled devices, and enable <b>Stereo Mix</b> (if your sound card has it); then choose it under Listen to. A microphone works too, a moment late.</p>
    <p class="hint">Experimental: built from captures of the Trimlight app (firmware 1.17.77). The computer and the controller must be on the same home network.</p>`;
  // Kept, so the answer stays when the panel redraws (every 15 seconds).
  const show = html => { LINK.out = html; const o2 = $('#lkout'); if (o2) o2.innerHTML = html; };
  box.onclick = async e => {
    const b = e.target.closest('button'); if (!b) return; const d = b.dataset;
    if (d.lksave !== undefined) {
      busy(b, async () => { await api('musiclink/address', { body: { address: $('#lkaddr').value.trim() } }); S.settings = await api('settings'); toast('Saved'); linkPanel(box); }).catch(() => {});
    } else if (d.lkfind !== undefined) {
      busy(b, async () => {
        const r = await api('musiclink/find', { body: {} });
        if (r.found.length === 1) $('#lkaddr').value = r.found[0];
        show(r.found.length ? `<p class="small">Answered: <b>${r.found.map(esc).join(', ')}</b>${r.found.length === 1 ? ' (filled in; press Save)' : ''}.</p>`
          : '<p class="small muted">Nothing answered. Enter the address the Trimlight app shows instead.</p>');
      }).catch(() => {});
    } else if (d.lktest !== undefined || d.lkread !== undefined) {
      busy(b, async () => {
        const r = await api('musiclink/test', { body: { read: d.lkread !== undefined } });
        show(`<p class="callout small" style="border-color:var(--ok)"><b>The controller answered</b> in ${r.ms} ms.${r.names ? ` It holds ${r.bytes} bytes${r.names.length ? `, including: ${r.names.slice(0, 15).map(esc).join(', ')}` : ''}.` : ''}</p>`);
      }).catch(err => show(`<p class="callout warn small">${esc(err.message)}</p>`));
    } else if (d.lkgo !== undefined) {
      busy(b, () => linkStart()).then(() => { linkPanel(box); moodPanel($('#moodbox')); })
        .catch(err => { LINK.err = err.name === 'NotAllowedError' ? 'Listening wasn\u2019t allowed. Allow the microphone (or the sharing) for this page in the browser, then try again.' : err.message; linkPanel(box); });
    } else if (d.lkstop !== undefined) linkStop();
    else if (d.lkeng) { linkSave({ ...linkOpts(), engine: d.lkeng }); linkPanel(box, false); }
    else if (d.lksync !== undefined && LINK.ctx) { LINK.sync = LINK.sync ? null : { next: LINK.ctx.currentTime + 0.3, flashUntil: 0 }; b.textContent = LINK.sync ? 'Stop the sync test' : 'Sync test'; }
    else if (d.lkpause !== undefined && LINK.audio) { if (LINK.audio.paused) LINK.audio.play().catch(() => {}); else LINK.audio.pause(); }
    else if (d.lknext !== undefined && LINK.play) LINK.play(LINK.fileAt + 1);
    else if (d.lkztest) {
      const dev = d.lkztest;
      if (!await confirmBox(`Speed test: ${zName(dev)}`, 'For about ten seconds the lights shimmer between two dim warm whites while the app sends frames faster and faster, and checks the controller keeps up. Then the schedule\u2019s pattern comes back.', 'Run the test')) return;
      busy(b, async () => { const r = await api('musiczones', { body: { op: 'test', device: dev } }); S.settings = await api('settings');
        toast(r.fps ? `${zName(dev)} takes ${r.fps} frames a second` : `${zName(dev)} didn\u2019t keep up even at 2 frames a second`, !r.fps); linkPanel(box); }).catch(() => {});
    }
  };
  box.oninput = e => {
    const t = e.target;
    if (t.id === 'lksens') $('#lksensv').textContent = t.value;
    if (t.id === 'lkgain') { const v = +t.value; LINK.gain = v; $('#lkgainv').textContent = `${v > 0 ? '+' : ''}${v} dB`; linkSave({ ...linkOpts(), gain: v }); }
    if (t.id === 'lkdelay') { const v = +t.value; $('#lkdelayv').textContent = `${v} ms`; linkSave({ ...linkOpts(), delay: v });
      if (LINK.delayNode && LINK.ctx) LINK.delayNode.delayTime.setTargetAtTime(v / 1000, LINK.ctx.currentTime, 0.05); }
  };
  box.onchange = e => {
    const t = e.target, o2 = linkOpts();
    if (t.id === 'lkin') { linkSave({ ...o2, input: t.value }); linkPanel(box, false); }
    else if (t.id === 'lkfile') { LINK.files = [...t.files]; LINK.fileAt = 0; linkPanel(box, false); }
    else if (t.dataset.lkzdev !== undefined) { const set = new Set(o2.zdevs); if (t.checked) set.add(t.dataset.lkzdev); else set.delete(t.dataset.lkzdev); linkSave({ ...o2, zdevs: [...set] }); linkPanel(box, false); }
    else if (t.dataset.lkz !== undefined || t.id === 'lkzbase') zonesSave(t, box);
    else if (t.id === 'lklen') linkSave({ ...o2, minutes: +t.value });
    else if (t.id === 'lkpat' || t.id === 'lksens') {
      const k = t.id === 'lkpat' ? 'pattern' : 'sensitivity';
      linkSave({ ...o2, [k]: +t.value });
      if (LINK.on) api('musiclink', { body: { op: 'set', tab: LINK.tab, [k]: +t.value } }).catch(err => toast(err.message, true));
      if (k === 'pattern') linkPanel(box, false);          // the Color choice comes and goes (4.2)
    } else if (t.id === 'lkcolor') {
      linkSave({ ...o2, color: t.value });
      if (LINK.on) api('musiclink', { body: { op: 'set', tab: LINK.tab, color: t.value } }).catch(err => toast(err.message, true));
    }
  };
}

/* 4.13: Music › My zones: each controller's speed test, and what each of
   its zones follows. Saved with the household's settings. */
const FOLLOW_NAMES = { bass: 'Bass', mid: 'Mids', treble: 'Treble', beat: 'The beat', off: 'Nothing (dark)' };
function zonesHtml(zs, o, ro) {
  const md = mapData(), mz = S.settings.music_zones || {}, maps = mz.maps || [];
  const devs = Object.entries(zs.devices || {});
  if (!devs.length) return '<p class="callout small">The controllers aren\u2019t listed yet. Open Setup \u203a Lights & controller once.</p>';
  const chosen = devs.filter(([d]) => o.zdevs.includes(d));
  const ctl = devs.map(([d, v]) => `<div class="item"><label class="check grow"><input type="checkbox" data-lkzdev="${esc(d)}" ${o.zdevs.includes(d) ? 'checked' : ''} ${LINK.on || ro || !v.address ? 'disabled' : ''}> ${esc(v.name)}</label>
      <span class="small ${v.tested && v.tested.fps ? '' : 'warn'}">${!v.address ? 'No home-network address (Setup \u203a Local mode)' : v.tested ? (v.tested.fps ? `Speed test: ${v.tested.fps} frames a second` : 'Speed test: didn\u2019t keep up') : 'Not tested yet'}</span>
      ${v.address ? `<button class="small ghost" data-lkztest="${esc(d)}" ${LINK.on || ro || zs.link ? 'disabled' : ''}>Speed test</button>` : ''}</div>`).join('');
  const rows = chosen.map(([d, v]) => {
    const zones = md.zones.filter(z => forDev(z, d));
    if (!zones.length) return `<p class="small"><b>${esc(v.name)}</b>: no zones yet. Save zones on the House tab (Zones).</p>`;
    const zsu = zoneSetup(d), need = MusicZones.worst(zsu);
    return `<div class="stack" style="gap:6px"><b>${esc(v.name)}</b>${zones.map(z => {
      const m = maps.find(x => x.zone === z.name && (x.device || null) === (z.device || null)) || { follows: 'off', shows: 'glow', color: '#FF6600' };
      const k = esc(JSON.stringify([z.name, z.device || null]));
      return `<div class="row zrow"><span class="grow" style="min-width:8em">${esc(z.name)} <span class="muted small">${z.start}\u2013${z.end}</span></span>
        <select data-lkz="${k}" data-f="follows" aria-label="${esc(z.name)} follows" ${ro ? 'disabled' : ''}>${MusicZones.FOLLOWS.map(f => `<option value="${f}" ${m.follows === f ? 'selected' : ''}>${FOLLOW_NAMES[f]}</option>`).join('')}</select>
        <select data-lkz="${k}" data-f="shows" aria-label="${esc(z.name)} shows as" ${ro ? 'disabled' : ''}><option value="glow" ${m.shows !== 'meter' ? 'selected' : ''}>Glow</option><option value="meter" ${m.shows === 'meter' ? 'selected' : ''}>Meter</option></select>
        <input type="color" data-lkz="${k}" data-f="color" value="${esc(String(m.color).toLowerCase())}" aria-label="${esc(z.name)} color" ${ro ? 'disabled' : ''}></div>`; }).join('')}
      ${need > MAX_SLOTS ? `<p class="callout warn small">These choices can need ${need} color blocks; a controller takes ${MAX_SLOTS}. Use fewer meters or zones.</p>` : ''}</div>`;
  }).join('');
  return `<div class="stack zonesbox"><p class="small">Which controllers\u2019 zones follow the music. Each must pass its <b>speed test</b> once: it shows how many frames a second the controller takes, the most a show will use.</p>
    <div class="list">${ctl}</div>${rows}
    ${chosen.length ? `<label class="row small">Everything else <input type="color" id="lkzbase" value="${esc(String(mz.base || '#000000').toLowerCase())}" ${ro ? 'disabled' : ''}> <span class="muted">(black: dark)</span></label>` : ''}
    <p class="note"><b>Glow</b>: the whole zone brightens with what it follows. <b>Meter</b>: it fills along the zone, from its first bulb (or its last, if it runs the other way). <b>The beat</b> flashes on each beat and fades. Zones come from the House tab.</p></div>`;
}
let zonesTimer = null;
function zonesSave(t, box) {
  const n = clone(S.settings), mz = n.music_zones = n.music_zones || {};
  if (t.id === 'lkzbase') mz.base = t.value.toUpperCase();
  else {
    const [zone, device] = JSON.parse(t.dataset.lkz), maps = mz.maps = mz.maps || [];
    let m = maps.find(x => x.zone === zone && (x.device || null) === device);
    if (!m) { m = { zone, ...(device ? { device } : {}), follows: 'off', shows: 'glow', color: '#FF6600' }; maps.push(m); }
    m[t.dataset.f] = t.dataset.f === 'color' ? t.value.toUpperCase() : t.value;
  }
  S.settings = n;                      // the show uses it at once; saved a moment later
  clearTimeout(zonesTimer);
  zonesTimer = setTimeout(() => saveSettings(clone(S.settings), 'Saved').then(() => { if (!LINK.on) linkPanel(box, false); }).catch(() => {}), 500);
}

const SHOW_LENGTHS = [[30, '30 minutes'], [60, '1 hour'], [90, '1½ hours'], [120, '2 hours'], [180, '3 hours'], [0, 'Until I stop it']];
const fmtMin = n => n % 60 === 0 ? `${n / 60} hour${n === 60 ? '' : 's'}` : n > 60 ? `${Math.floor(n / 60)} h ${n % 60} min` : `${n} minutes`;
VIEWS.music = async () => {
  const m = $('#main');
  m.innerHTML = `<div class="view"><p class="muted">Loading…</p></div>`;
  const viewer = role() === 'viewer';
  let render = st => {
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
      <div class="panel-head"><h2>Music</h2><span class="muted small">Two different ways to light the house to music.</span></div>
      <h3 class="secthead">Music show: the controller's own music mode</h3>
      <div class="cols wide-left">
        <div class="stack">
          <div class="panel stack"><h2>Music show</h2>${state}
            ${mu.active
              ? `<div class="row"><button class="primary" data-mstop ${viewer ? 'disabled' : ''}>Stop the show</button></div>`
              : `<div class="row"><label class="field">How long<select id="mlen">${lens.map(([v, l]) => `<option value="${v}" ${v === def ? 'selected' : ''}>${esc(l)}</option>`).join('')}</select></label>
                 <button class="primary" data-mstart ${viewer ? 'disabled' : ''} ${st.flash?.active ? 'disabled title="A security flash is running"' : ''}>Start a music show</button></div>`}
            <p class="note">Starting a show doesn\u2019t make the lights dance by itself: it keeps this app from changing them while the controller\u2019s music mode runs. Choosing a pattern, Return to schedule or a security flash interrupts the show.</p>
          </div>
          ${fold('howto', 'Then, on the controller', `<div class="panel stack"><h2>Then, on the controller</h2>
            <ol class="howto">
              <li>On a phone on your <b>home Wi-Fi</b> (music doesn\u2019t work away from home), open the <b>Trimlight Edge</b> app, choose your controller and tap <b>Music</b>.</li>
              <li>Choose <b>Auxiliary IN</b> if a player is plugged into the port on top of the controller (best: no delay, and the phone can be put away). Or choose <b>Microphone</b> and set the phone near the speaker.</li>
              <li>Pick a music pattern and set <b>Music Sensitivity</b>, then start the music.</li>
              <li>When you\u2019re done, press <b>Stop the show</b> here (or let it end on its own). The scheduled pattern comes back.</li>
            </ol>
            <p class="note">The Trimlight app can only switch music mode on over home Wi-Fi, and Trimlight\u2019s cloud (which this app uses) has no music controls. See \u201cMusic shows\u201d in the Manual for wiring a computer or speaker to the Aux port.</p>
          </div>`, wide())}
        </div>
        <div class="stack">
          ${fold('shownights', 'Show nights', `<div class="panel stack"><div class="panel-head"><h2>Show nights</h2><button class="small" data-maddshow ${viewer ? 'hidden' : ''}>Add a show night</button></div>
            <p class="note">On these nights this app steps aside by itself, so a show started in the Trimlight app isn\u2019t switched back to the schedule.</p>
            <div class="list">${shows.length ? shows.map((r, i) => `<div class="item"><div class="grow"><span class="name">${esc(r.name)}</span>
                <div class="sub">${esc(humanDates(r))} \u00b7 ${esc(humanDays(r.days))} \u00b7 ${esc(humanT(r.on))} \u2192 ${esc(humanT(r.off))}</div></div>
                ${viewer ? '' : `<button class="small ghost" data-meditshow="${i}">Edit</button><button class="small ghost danger" data-mdelshow="${i}" aria-label="Delete ${esc(r.name)}">Delete</button>`}</div>`).join('')
              : '<p class="muted">None yet. Add one for nights you plan a show, like Fridays and Saturdays in December.</p>'}</div>
          </div>`)}
          ${fold('showlen', 'Show length', `<div class="panel stack"><h2>Show length</h2>
            <div class="row"><label class="field">Usual length (minutes)<input type="number" id="mdef" min="5" max="360" value="${def}" ${viewer ? 'disabled' : ''}></label>
</div>
            <p class="note">The length chosen first above, and for a show started from a webhook or Home Assistant.</p>
          </div>`)}
        </div>
      </div>
      <h3 class="secthead">Music from this computer <span class="pill">Experimental</span></h3>
      <div class="panel stack" id="linkbox"></div>
      <h3 class="secthead">Mood follow: this app listens and changes patterns</h3>
      <div class="panel stack" id="moodbox"></div>
      </div>`;
  };
  const render0 = render;
  render = st => { render0(st); moodPanel($('#moodbox')); linkPanel($('#linkbox')); };
  try { render(await refreshStatus()); } catch (e) { m.innerHTML = `<div class="view"><p class="callout warn">${esc(e.message)}</p></div>`; return; }
  // 4.1.3: redraw only when the show's state changed, and never under the
  // user's hands (it rebuilt everything every 15 seconds, closing menus).
  const musicKey = st => JSON.stringify([st.music, st.flash?.active, st.target?.reason]);
  let shown = musicKey(S.status || {});
  S.timers.push(setInterval(async () => {
    if (document.hidden || $('#dlg').open) return;
    const st = await refreshStatus(), k = musicKey(st);
    if (k === shown || m.contains(document.activeElement) && document.activeElement !== document.body) return;
    shown = k; render(st);
  }, 15000));
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
    }
  };
  // 4.0: the usual show length saves as you change it.
  m.onchange = e => {
    if (e.target.id !== 'mdef') return;
    const v = Math.round(+e.target.value);
    if (!(v >= 5 && v <= 360)) return toast('Use 5 to 360 minutes.', true);
    const n = clone(S.settings); n.music = { ...(n.music || {}), minutes: v };
    busy(null, () => saveSettings(n, 'Show length saved')).catch(() => {});
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
  // 4.7.1: not-connected ports don't count, as in totalBulbs (a deck showed 1500)
  const bulbs = x => Math.max(0, ...(x.ports || []).filter(p => p.start > 0 && p.end > 0 && !p.unused).map(p => p.end));
  const doing = x => x.error ? 'Couldn\u2019t read it' : x.switch === 0 ? 'Off' : x.switch === 2 ? 'On its own timer' : x.switch === 1 ? 'On' : '';
  return `<div class="devcards" role="tablist" aria-label="Controllers">${devs.map(x => {
    const run = !chosen.length || chosen.includes(x.id), n = bulbs(x), what = doing(x);
    return `<button type="button" class="devcard" role="tab" aria-selected="${x.id === cur}" data-dev="${esc(x.id)}">
      <span class="dc-top"><b>${esc(x.name || 'Controller')}</b><span class="dot ${x.online ? 'on' : ''}">${x.online ? 'Online' : 'Offline'}</span></span>
      <span class="dc-sub">${[what, n ? `${n} bulbs` : ''].filter(Boolean).map(esc).join(' \u00b7 ')}</span>
      ${run ? '' : '<span class="dc-tag">Not run by this app</span>'}</button>`;
  }).join('')}</div>`;
}
/* Setup › Pattern backups (3.15; its own section since 4.9.2): put patterns back on the controller from
   one of the backups taken before every safety-net change. Only adds; a
   pattern whose name is already there is skipped. Administrators only. */
async function backupPanel(box, d) {
  if (!box) return;
  const tok = box.dataset.tok = String(Math.random());     // a newer draw wins (two can overlap while loading)
  const all = await api('backups').catch(e => { box.innerHTML = `<h2>Pattern backups</h2><p class="muted small">${esc(e.message)}</p>`; return null; });
  if (!all) return;
  const list = all.filter(b => b.device === d.id);
  // 4.3: put back over the home network only, checked against the controller
  // itself (not the cloud's copy, which can be out of step or unreadable).
  if (!lanFor(d.id)) {
    box.innerHTML = `<h2>Pattern backups</h2><p class="callout small">Since 4.3 patterns are put back over your home network, never through Trimlight\u2019s cloud. Enter ${(S.devices || []).length > 1 ? esc(d.name || 'this controller') + '\u2019s' : 'the controller\u2019s'} address in <a href="#local"><b>Setup › Local mode</b></a> first.</p>`;
    return;
  }
  // 4.3.6: if the controller can't be read just now, the backups are still
  // listed (and can be downloaded); putting back waits until it can be read.
  let live = null, liveErr = '';
  try { live = await api('local' + ((S.devices || []).length > 1 ? '?device=' + encodeURIComponent(d.id) : '')); } catch (e) { liveErr = e.message; }
  if (box.dataset.tok !== tok) return;
  const have = new Set((live ? live.patterns : []).map(e => String(e.name || '').trim().toLowerCase()));
  d = { ...d, error: live ? null : liveErr };
  if (!list.length) {
    box.innerHTML = '<h2>Pattern backups</h2><p class="muted small">No backups of this controller yet. One is taken before every change the backup timer makes (Setup › Lights & controller).</p>';
    return;
  }
  const pick = S.bkFile && list.some(b => b.file === S.bkFile) ? S.bkFile : list[0].file;
  box.innerHTML = `<h2>Pattern backups</h2>
    <p class="note">Put patterns back on the controller, for example after a factory reset or deleting one by mistake. It only adds: patterns already on the controller are left alone. It works over your home network, one pattern at a time, reading the controller back after each and stopping at the first difference. A pattern gets its old number when that\u2019s free, so timers made in the Trimlight app find it again.</p>
    ${liveErr ? `<p class="callout warn small">Couldn\u2019t read the controller just now (${esc(liveErr)}), so patterns can\u2019t be put back yet. The backups are listed below. Open Local mode and tap Read again, then come back.</p>` : ''}
    <label class="field">Backup<select id="bkfile">${list.map(b => `<option value="${esc(b.file)}" ${b.file === pick ? 'selected' : ''}>${esc(b.label)} (${b.patterns} patterns)</option>`).join('')}</select></label>
    <div id="bklist"><p class="muted small">Loading…</p></div>`;
  const load = async file => {
    S.bkFile = file;
    let r; try { r = await api('backups/patterns?file=' + encodeURIComponent(file)); }
    catch (e) { $('#bklist', box).innerHTML = `<p class="callout warn">${esc(e.message)}</p>`; return; }
    const builtin = p => p.category === 0;
    const missing = r.patterns.filter(p => !have.has(p.name.trim().toLowerCase()) && !builtin(p));
    $('#bklist', box).innerHTML = `${r.patterns.length ? `<div class="list">${r.patterns.map(p => { const there = have.has(p.name.trim().toLowerCase());
        return `<label class="check"><input type="checkbox" data-bk="${p.id}" ${there || d.error || builtin(p) ? 'disabled' : missing.length <= 10 ? 'checked' : ''}> <span class="grow">${esc(p.name)} <span class="small muted">${esc(p.kind)}${there ? ' · on the controller now' : builtin(p) ? ' · can\u2019t be put back over the home network yet' : ''}</span></span></label>`; }).join('')}</div>`
      : '<p class="muted small">This backup has no patterns.</p>'}
      ${missing.length ? `<div class="row" style="margin-top:10px"><button class="primary small" data-bkgo ${d.error ? 'disabled' : ''}>Put back selected</button><span class="small muted">${missing.length} not on the controller now</span></div>`
        : r.patterns.length ? '<p class="small muted" style="margin-top:8px">Every pattern in this backup is on the controller now.</p>' : ''}`;
  };
  $('#bkfile', box).onchange = e => load(e.target.value);
  box.onclick = async e => {
    const b = e.target.closest('[data-bkgo]'); if (!b) return;
    e.stopPropagation();
    const ids = [...box.querySelectorAll('[data-bk]:checked')].map(x => +x.dataset.bk);
    if (!ids.length) return toast('Tick the patterns to put back.', true);
    if (!await confirmBox('Put these patterns back?', `${ids.length} pattern${ids.length > 1 ? 's' : ''} will be added to ${esc(d.name || 'the controller')} over your home network. Nothing on it is changed or deleted. This takes a few seconds per pattern.`, 'Put back')) return;
    busy(b, () => api('backups/restore', { body: { file: S.bkFile, ids } })).then(r => {
      const dup = ((r.duplicates || []).length ? ` Skipped ${r.duplicates.length} more with the same name as one put back (${r.duplicates.join(', ')}).` : '')
        + ((r.builtin || []).length ? ` Not put back (built-in effects can\u2019t be written over the home network yet): ${r.builtin.join(', ')}.` : '');
      toast((r.restored.length ? `Put back: ${r.restored.join(', ')}.` : 'Nothing to put back: those patterns are already there.') + dup);
      S.devices = null; backupPanel(box, d);
    }).catch(() => {});
  };
  load(pick);
}

/* Local mode (4.3): the controller over the home network. Patterns are saved,
   put back and deleted only this way, never through Trimlight's cloud; ports
   too when the address is known. */
const lanAddr = () => ((S.settings || {}).lan || {}).address || '';
/* 4.5: each controller has its own address on the home network. An address
   saved before 4.5 counts only when the account has one controller. */
function lanFor(id) {
  const l = (S.settings || {}).lan || {}, m = l.devices || {};
  if (m[id]) return m[id];
  return l.address && !Object.values(m).includes(l.address) && (S.devices || []).length <= 1 ? l.address : '';
}
const lanAny = () => { const l = (S.settings || {}).lan || {}; return !!(l.address || Object.values(l.devices || {}).some(Boolean)); };
async function localPanel(box, fresh = false) {
  if (!box) return;
  const devs = (S.devices || []).filter(d => d.id);
  const many = devs.length > 1;
  const l = (S.settings || {}).lan || {};
  const unassigned = many && l.address && !Object.values(l.devices || {}).includes(l.address) ? l.address : '';
  const withAddr = many ? devs.filter(d => lanFor(d.id)) : [];
  if (many && !withAddr.some(d => d.id === S.lcDev)) S.lcDev = (withAddr[0] || {}).id;
  const addr = many ? lanFor(S.lcDev || '') : lanAddr();
  const intro = `<h2>Local mode (home network)</h2>
    <p class="note">This app saves, puts back and deletes the controller's patterns, and sets its ports, straight over your home network, as the Trimlight Edge app does when it shows <b>Local</b>. Nothing about patterns goes through Trimlight's cloud: saves and deletes there left its copy of the controller unreadable (code 12006) and lost patterns. Each change is checked by reading the controller back, and it stops at the first difference.</p>`;
  const head = many ? intro + `
    <p class="note">Each controller has its own address. <b>Find</b> lists every controller answering on your home network; <b>Which is this?</b> shows what one holds, so you can tell them apart.</p>
    ${unassigned ? `<p class="callout small">The address saved before, <b class="num">${esc(unassigned)}</b>, belongs to which controller? ${devs.map(d => `<button class="small ghost" data-lcassign="${esc(d.id)}" data-addr="${esc(unassigned)}">${esc(d.name || d.id)}</button>`).join(' ')}</p>` : ''}
    <div class="list">${devs.map(d => `<div class="item"><div class="grow"><b>${esc(d.name || d.id)}</b>
        <div class="row" style="align-items:flex-end;margin-top:4px"><label class="field" style="flex:1;min-width:160px">Address on your home network<input type="text" data-lcaddr="${esc(d.id)}" value="${esc(lanFor(d.id))}" placeholder="e.g. 192.168.1.50" inputmode="decimal" spellcheck="false"></label>
        <button class="small" data-lcsavedev="${esc(d.id)}">Save</button></div></div></div>`).join('')}</div>
    <div class="row"><button class="small" data-lcdisc>Find and match my controllers</button><button class="small ghost" data-lcfind>Find controllers</button></div><div id="lcfound"></div>`
    : intro + `
    <div class="row" style="align-items:flex-end">
      <label class="field" style="flex:1;min-width:180px">Controller’s address on your home network<input type="text" id="lcaddr" value="${esc(addr)}" placeholder="e.g. 192.168.1.50" inputmode="decimal" spellcheck="false"></label>
      <button class="small" data-lcsave>Save</button><button class="small ghost" data-lcfind>Find it</button><button class="small ghost" data-lcdisc>Find and match</button></div><div id="lcfound"></div>`;
  // The setting is reachable even when the controller can't be read just
  // now (4.4.1: it used to show only after a good read).
  const cmd = lanAny() ? `<label class="check" style="margin-top:8px"><input type="checkbox" id="lccmd" ${l.commands ? 'checked' : ''}>
          <span><b>Send on/off and saved patterns over the home network</b> <span class="pill">Try it</span><br><span class="small muted">The schedule turns the lights on and off, and shows patterns saved on the controller, straight over your home network instead of through Trimlight’s cloud${many ? ', each controller at its own address (one without an address uses the cloud)' : ''}. If that doesn’t work, it uses the cloud as before. This app’s own patterns and the built-in effects go this way too (shown live, as the Trimlight app does while you edit), and so do the brightness and speed sliders.</span></span></label>` : '';
  const pick = many && withAddr.length ? `<div class="row" style="margin-top:8px"><label class="field">Controller to read<select id="lcdev">${withAddr.map(d => `<option value="${esc(d.id)}" ${d.id === S.lcDev ? 'selected' : ''}>${esc(d.name || d.id)} (${esc(lanFor(d.id))})</option>`).join('')}</select></label></div>` : '';
  const q = many && S.lcDev ? 'device=' + encodeURIComponent(S.lcDev) : '';
  const dev = many ? S.lcDev : undefined;
  const keepFound = () => { const lf = $('#lcfound', box); if (lf && S.lcFound && !lf.innerHTML) lf.innerHTML = S.lcFound; };
  if (!addr) { box.innerHTML = head + cmd + (many ? '' : '<p class="callout small">Enter the address (the Trimlight Edge app shows it when you open the controller on your home Wi-Fi), or tap <b>Find it</b>.</p>'); keepFound(); }
  else {
    box.innerHTML = head + cmd + pick + '<div id="lcbody"><p class="muted small">Reading the controller…</p></div>';
    keepFound();
    // Review #4 (4.15): the buttons work while the controller is read (they were set up only after it)
    setTimeout(async () => { try {
      const st = await api('local' + ((fresh || q) ? '?' + [fresh ? 'fresh=1' : '', q].filter(Boolean).join('&') : ''));
      $('#lcbody', box).innerHTML = `<p class="small">Ports: ${st.ports.map(p => `${p.port}: ${p.start}–${p.end}`).join(' · ')}</p>
        <h3 style="margin:8px 0 4px">On ${many ? esc((devs.find(d => d.id === S.lcDev) || {}).name || 'the controller') : 'the controller'} now (${st.patterns.length})</h3>
        ${st.unreadable ? `<p class="note small">The controller also sent ${st.unreadable} slot${st.unreadable === 1 ? '' : 's'} that ${st.unreadable === 1 ? 'isn\u2019t a pattern' : 'aren\u2019t patterns'} (numbered 0 or past 60, usually without a name). They\u2019re left out here and never changed by this app.</p>` : ''}
        <div class="list">${st.patterns.map(p => `<div class="item"><div class="grow"><b>${esc(p.name)}</b> <span class="small muted">#${p.id}</span>
          <div>${swatches(p.colors.map(c => c[1]), 10)}</div></div><button class="small ghost danger" data-lcdel="${p.id}" data-name="${esc(p.name)}">Delete</button></div>`).join('') || '<p class="muted small">No saved patterns.</p>'}</div>
        ${st.daily ? `<h3 style="margin:12px 0 4px">Daily timers on the controller</h3>
          <p class="small muted">The controller\u2019s own two daily timers (the Trimlight app\u2019s), as it holds them now. Shown only; change them in the Trimlight app for now. This app\u2019s schedule doesn\u2019t use them.</p>
          <div class="list">${st.daily.map(t => `<div class="item"><div class="grow"><b>Timer ${t.id + 1}</b> <span class="small ${t.enable ? 'ok' : 'muted'}">${t.enable ? 'on' : 'off'}</span>
            <div class="small">${esc(hm12(t.start))} \u2013 ${esc(hm12(t.end))} \u00b7 ${esc(t.repeat || 'repeat ' + t.repetition)} \u00b7 ${esc(t.pattern || 'pattern #' + t.effectId)}</div></div></div>`).join('')}</div>` : ''}
        <div class="row" style="margin-top:8px"><button class="small ghost" data-lcread>Read again</button>
          <button class="small" data-lcbackup>Back up now</button><span class="small muted">Saves these patterns and ports on this computer (listed under Pattern backups).</span></div>`;
    } catch (e) { const lb = $('#lcbody', box); if (lb) lb.innerHTML = `<p class="callout warn small">${esc(e.message)}</p><div><button class="small ghost" data-lcread>Try again</button></div>`; } }, 0);
  }
  const assign = async (b, id, address, force = false) => {
    const r = await busy(b, () => api('local/address', { body: { device: id, address, force } }));
    if (r && r.confirm) {
      if (!await confirmBox('Is that the right controller?', r.confirm, 'Save anyway')) return;
      return assign(b, id, address, true);
    }
    S.settings = await api('settings'); toast('Saved'); S.lcDev = address ? id : S.lcDev; localPanel(box);
  };
  box.onchange = e => {
    if (e.target.id === 'lcdev') { S.lcDev = e.target.value; return localPanel(box); }
    if (e.target.id !== 'lccmd') return;
    const on = e.target.checked;
    api('local/commands', { body: { on } }).then(async () => { S.settings = await api('settings'); toast(on ? 'On/off and saved patterns go over the home network' : 'Everything goes through Trimlight’s cloud'); })
      .catch(() => { e.target.checked = !on; });
  };
  box.onclick = async e => {
    const b = e.target.closest('button'); if (!b) return; const ds = b.dataset;
    if (ds.lcsave !== undefined) return busy(b, async () => { await api('musiclink/address', { body: { address: $('#lcaddr', box).value.trim() } }); S.settings = await api('settings'); toast('Saved'); localPanel(box); }).catch(() => {});
    if (ds.lcsavedev) return assign(b, ds.lcsavedev, $(`[data-lcaddr="${CSS.escape(ds.lcsavedev)}"]`, box).value.trim()).catch(() => {});
    if (ds.lcassign) return assign(b, ds.lcassign, ds.addr).catch(() => {});
    if (ds.lcfind !== undefined) return busy(b, async () => { const r = await api('musiclink/find', { body: {} });
      if (!many) {
        if (r.found.length) { $('#lcaddr', box).value = r.found[0]; toast(r.found.length === 1 ? 'Found it. Tap Save.' : `Found ${r.found.length}: ${r.found.join(', ')}`); } else toast('No controller answered. Enter its address instead.', true);
        return;
      }
      const taken = Object.fromEntries(devs.map(d => [lanFor(d.id), d.name || d.id]));
      $('#lcfound', box).innerHTML = r.found.length ? `<div class="list">${r.found.map(a => `<div class="item"><div class="grow"><b class="num">${esc(a)}</b>${taken[a] ? ` <span class="small muted">${esc(taken[a])}’s</span>` : ''}<div class="small muted" data-lcinfo="${esc(a)}"></div>
          <div class="row" style="margin-top:4px">${taken[a] ? '' : `<select data-lcfor="${esc(a)}">${devs.filter(d => !lanFor(d.id)).concat(devs.filter(d => lanFor(d.id))).map(d => `<option value="${esc(d.id)}">${esc(d.name || d.id)}</option>`).join('')}</select><button class="small" data-lcuse="${esc(a)}">Use for this controller</button>`}
          <button class="small ghost" data-lcwhich="${esc(a)}">Which is this?</button></div></div></div>`).join('')}</div>`
        : '<p class="callout small">No controller answered. Enter each address instead (the Trimlight Edge app shows it when you open that controller on your home Wi-Fi).</p>';
    }).catch(() => {});
    if (ds.lcuse) return assign(b, $(`[data-lcfor="${CSS.escape(ds.lcuse)}"]`, box).value, ds.lcuse).catch(() => {});
    // 4.15: find every controller on the home network, read each, and match it to the account's by its ports
    if (ds.lcdisc !== undefined || ds.lcscan !== undefined) {
      const out = $('#lcfound', box);
      out.innerHTML = `<p class="muted small">${ds.lcscan !== undefined ? 'Knocking on each address of your home network (port 8586 only), then reading each controller found\u2026 this takes up to a minute.' : 'Looking for controllers and reading each one\u2026'}</p>`;
      return busy(b, () => api('local/discover', { body: { scan: ds.lcscan !== undefined } })).then(r => {
        const name = id => (r.devices.find(d => d.id === id) || {}).name || id;
        const matches = r.found.filter(f => f.match && f.saved_for !== f.match);
        out.innerHTML = (r.found.length ? `<div class="list">${r.found.map(f => `<div class="item"><div class="grow"><b class="num">${esc(f.address)}</b>
            <span class="small muted">${f.how === 'answered' ? 'answered the search' : 'its controller port is open'}</span>
            <div class="small">${f.error ? `<span class="warn">${esc(f.error)}</span>` : `Ports ${f.ports.filter(p => p.start || p.end).map(p => `${p.port}: ${p.start}\u2013${p.end}`).join(' \u00b7 ')}. ${f.count} pattern${f.count === 1 ? '' : 's'}${f.patterns.length ? ': ' + esc(f.patterns.join(', ')) + (f.count > f.patterns.length ? ` and ${f.count - f.patterns.length} more` : '') : ''}.`}</div>
            <div class="small">${f.saved_for ? `Saved as <b>${esc(name(f.saved_for))}</b>\u2019s address.${f.match && f.match !== f.saved_for ? ` <span class="warn">Its ports match ${esc(name(f.match))} instead.</span>` : ''}`
              : f.match ? `This is <b>${esc(name(f.match))}</b> (its ports match).` : esc(f.note || 'Not matched to a controller on your account.')}</div></div>
            ${f.match && f.saved_for !== f.match ? `<button class="small" data-lcmatch="${esc(f.address)}" data-dev="${esc(f.match)}">Use for ${esc(name(f.match))}</button>` : ''}</div>`).join('')}</div>`
          : '<p class="callout small">No controller answered.</p>')
          + `<div class="row">${matches.length > 1 ? `<button class="small primary" data-lcall='${esc(JSON.stringify(matches.map(f => [f.match, f.address])))}'>Use all ${matches.length} matches</button>` : ''}
              ${ds.lcscan === undefined ? '<button class="small ghost" data-lcscan>Look harder (check each address on this network)</button>' : ''}</div>`;
        S.lcFound = out.innerHTML;          // kept when the panel draws again (the controller read finishing, a save)
      }).catch(() => { out.innerHTML = ''; });
    }
    if (ds.lcmatch) return assign(b, ds.dev, ds.lcmatch).catch(() => {});
    if (ds.lcall) return busy(b, async () => { for (const [dev, a] of JSON.parse(ds.lcall)) await api('local/address', { body: { device: dev, address: a, force: true } });
      S.settings = await api('settings'); toast('Addresses saved'); localPanel(box); }).catch(() => {});
    if (ds.lcwhich) return busy(b, () => api('local/identify', { body: { address: ds.lcwhich } })).then(r => {
      const el = $(`[data-lcinfo="${CSS.escape(ds.lcwhich)}"]`, box);
      if (el) el.textContent = `Ports ${r.ports.map(p => `${p.port}: ${p.start}–${p.end}`).join(' · ')}. ${r.count} pattern${r.count === 1 ? '' : 's'}${r.patterns.length ? ': ' + r.patterns.join(', ') + (r.count > r.patterns.length ? ', …' : '') : ''}.`;
    }).catch(() => {});
    if (ds.lcread !== undefined) return localPanel(box, true);
    if (ds.lcbackup !== undefined) return busy(b, () => api('local/backup', { body: { device: dev } })).then(async r => {
      toast(`Backed up ${r.patterns} pattern${r.patterns === 1 ? '' : 's'}`);
      const data = await api('safety/backup?file=' + encodeURIComponent(r.file));
      const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }));
      const a = document.createElement('a'); a.href = url; a.download = r.file; a.click(); setTimeout(() => URL.revokeObjectURL(url), 5000);
      const bk = $('#bkbox'); if (bk && S.lightDevObj) backupPanel(bk, S.lightDevObj);
    }).catch(() => {});
    if (ds.lcdel !== undefined) {
      const who = many ? ((devs.find(d => d.id === dev) || {}).name || 'the controller') : 'the controller';
      if (!await confirmBox(`Delete “${ds.name}” from ${who}?`, `It is removed from the controller's own library (the Trimlight app's list) over your home network. Timers in the Trimlight app that use it stop showing it. A backup of the controller is taken first, so it can be put back from Pattern backups.`, 'Delete', true)) return;
      return busy(b, () => api('local/delete', { body: { id: +ds.lcdel, name: ds.name, device: dev } })).then(() => { toast(`Deleted “${ds.name}”`); S.devices = null; loadDevices().then(() => localPanel(box)).catch(() => localPanel(box)); }).catch(() => {});
    }
  };
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
  S.lightDevObj = d;
  const ports = [0, 1, 2, 3].map(i => { const p = (d.ports || []).find(x => x.id === i) || { id: i, start: 0, end: 0 }; return { ...p, off: !!p.unused || !(p.start > 0 && p.end > 0) }; });
  // Ports that read "bulbs 1-600" are how the controller reports a port that
  // was never set up; most homes have nothing plugged in there (3.18.1).
  // Not for a port given bulbs on this tab: that is a real run (3.18.2).
  const unset = ports.filter(p => !p.off && !p.set_here && p.start === 1 && p.end === 600 && ports.some(q => q !== p && !q.off && q.end < 600));
  const on = ports.filter(p => !p.off);
  const sequential = on.every((p, i) => p.start === (i === 0 ? 1 : on[i - 1].end + 1));
  S.portMode = S.portMode && S.portModeDev === d.id ? S.portMode : (sequential ? 'simple' : 'advanced'); S.portModeDev = d.id;
  const P = S.portDraft && S.portDraft.dev === d.id ? S.portDraft.P : ports.map(p => ({ ...p, count: p.off ? 0 : p.end - p.start + 1 }));
  S.portDraft = { dev: d.id, P };
  const chosen = S.settings.service?.devices || [];
  const draw = () => {
    if (!$('#pmap')) return;           // controller unreadable: no port editor
    if (S.portMode === 'simple') { let next = 1; P.forEach(p => { if (p.count > 0) { p.start = next; p.end = next + p.count - 1; p.off = false; next = p.end + 1; } else { p.off = true; p.start = p.end = 0; } }); }
    const max = Math.max(1, ...P.filter(p => !p.off).map(p => p.end));
    $('#pmap').innerHTML = P.map(p => `<div class="lane" title="Port ${p.id + 1}">${p.off ? '' : `<i style="left:${(p.start - 1) / max * 100}%;width:${(p.end - p.start + 1) / max * 100}%"></i>`}
      <span>Port ${p.id + 1}: ${p.off ? 'not connected' : `bulbs ${p.start}–${p.end}`}</span></div>`).join('');
    $('#ptotal').textContent = `${max === 1 && P.every(p => p.off) ? 0 : max} bulbs in the pattern${P.some((p, i) => !p.off && P.some((q, j) => j !== i && !q.off && p.start <= q.end && q.start <= p.end)) ? '. Overlapping ports show the same bulbs (mirrored).' : '.'}`;
  };
  m.innerHTML = `<div class="view"><div class="panel-head"><h2>${devs.length > 1 ? `Lights: ${esc(d.name || 'Controller')}` : 'Lights'}</h2>
      <span class="badge ${d.online ? 'hi' : ''}">${d.online ? 'Online' : 'Offline'}</span><span class="small muted">Firmware ${esc(d.firmware || '?')}</span></div>
    ${devs.length > 1 ? devCards(devs, d.id, chosen) : ''}
    ${d.error ? `<p class="callout warn">${esc(d.error)}</p><p class="callout">Your port layout and settings on the controller haven\u2019t changed. They just can\u2019t be shown, and saving is turned off until the controller can be read.</p>
      ${isAdmin() ? '<div class="row"><button class="primary small" data-resync>Resync with Trimlight\u2019s cloud</button><span class="small muted">Asks the controller to send the cloud a fresh copy. Changes nothing on it. Don\u2019t unplug the controller meanwhile.</span></div>' : ''}` : ''}
    <div class="cols wide-left">
      ${d.error ? `<div class="panel stack"><h2>Ports and bulbs</h2><p class="muted">Unknown until the controller can be read.</p><div><button class="ghost" data-reload>Try again</button></div></div>` : `<div class="panel stack"><div class="panel-head"><h2>Ports and bulbs</h2>
          <div class="seg"><button data-pm="simple" aria-pressed="${S.portMode === 'simple'}">Simple</button><button data-pm="advanced" aria-pressed="${S.portMode === 'advanced'}">Advanced</button></div></div>
        ${unset.length ? `<p class="callout small">${unset.map(p => 'Port ' + (p.id + 1)).join(' and ')} ${unset.length === 1 ? 'reads' : 'read'} bulbs 1–600, which is how the controller reports a port that was never set up. If nothing is plugged in there, mark ${unset.length === 1 ? 'it' : 'them'} <b>Not connected</b> and save, so this app counts ${Math.max(...ports.filter(q => !q.off && !unset.includes(q)).map(q => q.end))} bulbs instead of 600. <button class="small ghost" data-portreal="${unset.map(p => p.id).join(',')}">${unset.length === 1 ? 'It\u2019s' : 'They\u2019re'} really connected</button></p>` : ''}
        <p class="note">${lanFor(d.id) ? 'Saved over your home network (Local mode), where a port marked <b>Not connected</b> is really switched off on the controller and keeps its numbers.' : 'Trimlight\u2019s cloud has no setting that turns a port off. A port marked <b>Not connected</b> keeps its numbers on the controller.'} This app leaves it out of the bulb count, the bulb finder and the house tools.</p>
        <p class="note">${S.portMode === 'simple' ? 'Enter how many bulbs are on each port. Use 0 for a port with nothing plugged in. Ports are numbered in order along the roofline.' : 'Set the first and last bulb number for each port. Ports may overlap to mirror the same section of the pattern.'}</p>
        <div class="ports">${P.map(p => `<div class="port"><b>Port ${p.id + 1}</b><div class="vals">
          ${S.portMode === 'simple' ? `<input type="number" min="0" max="2048" data-pc="${p.id}" value="${p.count}" aria-label="Bulbs on port ${p.id + 1}"><span class="small muted">bulbs</span>`
          : `<label class="check" style="gap:6px"><input type="checkbox" data-poff="${p.id}" ${p.off ? 'checked' : ''}>Not connected</label>
             <input type="number" min="1" max="2048" data-ps="${p.id}" value="${p.off ? '' : p.start}" ${p.off ? 'disabled' : ''} aria-label="First bulb"><span class="muted">to</span>
             <input type="number" min="1" max="2048" data-pe="${p.id}" value="${p.off ? '' : p.end}" ${p.off ? 'disabled' : ''} aria-label="Last bulb">`}</div></div>`).join('')}</div>
        <div class="portmap" id="pmap"></div><p class="note" id="ptotal"></p>
        <div class="row"><button class="primary" data-saveports ${d.error && !lanFor(d.id) ? 'disabled' : ''}>Save to controller</button><button class="ghost" data-reload>Undo changes</button></div>
      </div>`}
      <div class="stack">
        <div class="panel stack"><h2>Controller</h2>
          <label class="field">Name<input type="text" id="lname" maxlength="30" value="${esc(d.name)}"></label>
          <label class="field">LED chip<select id="lic">${S.catalog.ic_types.map((n, i) => `<option value="${i}" ${d.ic === i ? 'selected' : ''}>${n}</option>`).join('')}</select></label>
          <label class="field">Color order <span class="hint">Trimlight systems are almost always RGB. Change it only if Test colors shows the wrong color.</span>
            <select id="lco">${S.catalog.color_orders.map((n, i) => `<option value="${i}" ${d.colorOrder === i ? 'selected' : ''}>${n}</option>`).join('')}</select></label>
          <div class="row"><button data-savedev ${d.error ? 'disabled' : ''}>Save controller settings</button>
            ${isAdmin() ? '<button class="ghost" data-resync title="Ask the controller to send Trimlight\u2019s cloud a fresh copy of its data">Resync with Trimlight\u2019s cloud</button>' : ''}</div>
          <div class="row"><span class="small">Test colors:</span>${[['Red', '#FF0000'], ['Green', '#00FF00'], ['Blue', '#0000FF'], ['White', '#FFFFFF']].map(([n, c]) => `<button class="small" data-test="${c}">${swatches([c], 1)}${n}</button>`).join('')}</div>
        </div>
        ${fold('safety', 'Backup timer', '<div class="panel stack" id="safetybox"><p class="muted">Loading…</p></div>', false)}
        <p class="note">${isAdmin() ? '<a href="#color">Color correction</a>, <a href="#local">Local mode</a> and <a href="#backups">Pattern backups</a> have their own sections' : '<a href="#color">Color correction</a> has its own section'} in Setup (4.9.2).</p>
        ${devs.length > 1 ? `<div class="panel stack"><h2>Controlled by this app</h2>${devs.map(x => `<label class="check"><input type="checkbox" data-ctl="${esc(x.id)}" ${!chosen.length || chosen.includes(x.id) ? 'checked' : ''}>${esc(x.name)}</label>`).join('')}
          <div><button class="small" data-savectl>Save</button></div></div>` : ''}
      </div>
    </div></div>`;
  draw();
  whenOpen('safety', () => safetyPanel($('#safetybox')));
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
    if (ds.portreal !== undefined) {           // a real run of bulbs 1-600: stop the hint (3.18.2)
      const n = clone(S.settings); n.service = n.service || {};
      const ps = { ...(n.service.ports_set || {}) };
      ps[d.id] = [...new Set([...(ps[d.id] || []), ...ds.portreal.split(',').map(Number)])].sort();
      n.service.ports_set = ps;
      return busy(b, () => saveSettings(n, 'Noted')).then(() => { S.devices = null; return VIEWS.lights({ keep: true }); }).catch(() => {});
    }
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
    if (ds.resync !== undefined) return busy(b, () => api('resync', { body: {} })).then(r => {
      toast(r.ok ? 'Trimlight\u2019s cloud reads the controller again' : 'Trimlight\u2019s cloud still can\u2019t read it. Try again in a few minutes; the lights keep running.', !r.ok);
      S.devices = null; VIEWS.lights({ keep: true });
    }).catch(() => {});
    if (ds.saveports !== undefined) {
      const bad = P.find(p => !p.off && !(p.start >= 1 && p.end >= p.start && p.end <= 2048));
      if (bad) return toast(`Port ${bad.id + 1}: the first bulb must be 1 or more and not after the last bulb (max 2048).`, true);
      if (!await confirmBox('Save ports to the controller?', 'The lights may flicker while the controller applies the new layout.', 'Save')) return;
      return busy(b, () => api('device/update', { body: { deviceId: d.id, ports: P.map(p => ({ id: p.id, start: p.off ? 0 : p.start, end: p.off ? 0 : p.end })) } }))
        .then(async r => { toast(r && r.note ? r.note : r && r.local ? 'Ports saved over the home network and read back' : 'Ports saved', !!(r && r.note)); S.portMode = null; await loadSettings().catch(() => {}); VIEWS.lights(); }).catch(() => {});
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

/* ---------------------------------------------------------------- 4.9.2: Setup sections of their own
   Color correction, Local mode and Pattern backups, which were folded panels
   under Lights & controller. Each panel is the same as before. */
VIEWS.color = async () => {
  $('#main').innerHTML = '<div class="view"><div class="panel stack" id="gbox" style="max-width:760px"></div></div>';
  colorPanel($('#gbox'));
};
VIEWS.local = async () => {
  if (!isAdmin()) return go('lights', null, true);
  const m = $('#main');
  m.innerHTML = '<div class="view"><div class="panel stack" id="lcbox" style="max-width:900px"><p class="muted">Loading…</p></div></div>';
  try { await loadDevices(); } catch (e) { $('#lcbox').innerHTML = `<h2>Local mode (home network)</h2><p class="callout warn">${esc(e.message)}</p>`; return; }
  localPanel($('#lcbox'));
};
VIEWS.backups = async () => {
  if (!isAdmin()) return go('lights', null, true);
  const m = $('#main');
  m.innerHTML = '<div class="view"><p class="muted">Loading…</p></div>';
  let devs;
  try { devs = await loadDevices(); } catch (e) { m.innerHTML = `<div class="view"><h2>Pattern backups</h2><p class="callout warn">${esc(e.message)}</p></div>`; return; }
  if (!devs.length) { m.innerHTML = '<div class="view"><h2>Pattern backups</h2><p class="callout">No controllers on this account.</p></div>'; return; }
  S.lightDev = devs.some(d => d.id === S.lightDev) ? S.lightDev : (devs.find(d => d.selected) || devs[0]).id;
  const d = devs.find(x => x.id === S.lightDev);
  S.lightDevObj = d;
  m.innerHTML = `<div class="view">${devs.length > 1 ? `<div class="row" style="margin-bottom:12px"><label class="row small" style="gap:6px">Controller<select id="bkdev" style="width:auto">${devs.map(x =>
      `<option value="${esc(x.id)}" ${x.id === d.id ? 'selected' : ''}>${esc(x.name || 'Controller')}</option>`).join('')}</select></label></div>` : ''}
    <div class="panel stack" id="bkbox" style="max-width:900px"></div></div>`;
  const sel = $('#bkdev');
  if (sel) sel.onchange = () => { S.lightDev = sel.value; VIEWS.backups(); };
  backupPanel($('#bkbox'), d);
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
VIEWS.settings = async (sec) => {
  sec = sec === 'app' || sec === 'access' ? sec : (S.setupSec === 'app' ? 'app' : 'access');
  const m = $('#main');
  const a = S.account = await api('account');
  const urls = a.addresses.map(ip => `${a.scheme || 'http'}://${ip}:${a.port}/`);
  const local = S.session.local, admin = isAdmin(), me = a.user || {}, signedIn = !me.local && !me.setup;
  const hours = h => h < 24 ? `${h} hour${h === 1 ? '' : 's'}` : `${h / 24} day${h === 24 ? '' : 's'}`;
  // 4.0: Setup › Accounts & access, and Setup › App (the old Settings tab).
  // Webhooks and phone alerts are on the Alerts tab now.
  const parts = {
    access: [`
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
`, `
        <div class="panel stack"><h2>Phones and other computers</h2>
          ${urls.length ? `<p>Open <code>${esc(urls[0])}</code> in the web browser on any phone or computer on your home Wi-Fi. It shows a sign-in page. In Safari, Share › Add to Home Screen makes it an app.</p>
            ${urls.length > 1 ? `<p class="note">If that address doesn't open, this computer has others: ${urls.slice(1).map(u => `<code>${esc(u)}</code>`).join(', ')}.</p>` : ''}` : ''}
          <p class="note">${a.password_set ? 'Each person signs in with their own account.' : 'Create an account (Setup › Accounts & access) so other devices can sign in.'}</p>
          <details class="lanhelp"><summary>A phone can\u2019t open it?</summary>
            <ol class="howto">
              <li>Type the address exactly, starting with <b>${esc(a.scheme || 'http')}://</b> and ending with <b>:${esc(a.port)}/</b>, in the phone\u2019s web browser.</li>
              <li>Use your <b>home Wi-Fi</b>, not mobile data, on the same network as this computer: not a guest or separate network on your router.</li>
              <li>This computer\u2019s firewall has to let phones in.${local ? ' Check it below.' : ' Open Settings on the computer running the app and use <b>Check this computer</b> there.'}</li>
            </ol>
            ${local ? '<div class="row"><button class="small" data-lancheck>Check this computer</button></div><div id="lanresult" class="stack" aria-live="polite"></div>' : ''}
          </details></div>
`],
    app: [`
        <div class="panel stack"><h2>Share and back up</h2>
          <p class="note">Export your patterns and schedule to a file you can keep or share with other Trimlight owners. It never includes your Trimlight credentials, passwords, location or away mode.</p>
          <div class="row"><button data-export>Export patterns and schedule</button>${role() !== 'viewer' ? '<label class="btn" tabindex="0">Import a file<input type="file" id="impf" accept=".json,application/json" hidden></label>' : ''}</div></div>
        <div class="panel stack" id="updbox"><h2>Updates</h2><p class="muted small">Loading…</p></div>
        ${fold('usage', 'Lights usage', '<div class="panel stack" id="usagebox"></div>')}
        <div class="panel stack" id="pwabox"></div>
        <div class="panel stack"><h2>Setup and about</h2>
          ${admin ? '<div><button class="ghost" data-wizard>Run the setup assistant again</button></div>' : ''}
          <p class="small muted">Version ${esc(a.version)}${a.python ? ` · Python ${esc(a.python)}<br>Data folder: <code>${esc(a.data_dir)}</code>` : ''}</p>
          <p class="small muted">EaveLuxOS, the intelligent lighting control platform. © 2026 Christopher A. Tankelewicz (ThinkTank4n6). Free software under the MIT License. Works with Trimlight Edge controllers; not affiliated with or endorsed by Trimlight. The house roofline tools and bulb painter are adapted from Trimlight Home Studio (© 2026 Thomas Kay and contributors, MIT License).</p>
          ${!local ? (signedIn ? '' : '<div><button class="ghost" data-logout>Sign out of this device</button></div>') : '<div><button class="ghost danger" data-quit>Quit the app</button></div><p class="note">Your lights only follow the schedule while the app is running.</p>'}</div>
`, `
        ${admin ? `<div class="panel stack"><h2>App address</h2>
          <p class="note">The app uses port <b>${a.port}</b>${urls.length ? ` (<code>${esc(urls[0])}</code>)` : ''}. Change it if another program on this computer needs that port.</p>
          <div class="row"><label class="field">Port<input type="number" id="pport" min="1024" max="65535" value="${a.port}" style="width:8em"></label>
            <button data-port style="align-self:end">Restart on new port</button></div>
          <p class="note">Phones and bookmarks need the new address afterward. The schedule pauses for a few seconds while the app restarts.</p></div>
        <div class="panel stack"><h2>Start automatically</h2>
          ${a.autostart.supported ? `<label class="check"><input type="checkbox" id="auto" ${a.autostart.enabled ? 'checked' : ''}> Start this app when the computer starts</label>
            ${a.autostart.note ? `<p class="note">${esc(a.autostart.note)}</p>` : ''}` : '<p class="muted">Not available on this system.</p>'}
          ${a.awake && a.awake.supported ? `<label class="check"><input type="checkbox" id="awake" ${a.awake.enabled ? 'checked' : ''}> Keep this computer awake while the app runs</label>
            <p class="note">A sleeping computer can't follow the schedule. With this on, the computer won't go to sleep on its own; the screen can still turn off, and the power button and Sleep still work. Quitting the app lets it sleep again.</p>` : ''}</div>` : ''}
        ${admin ? fold('ai', 'AI pattern ideas', '<div class="panel stack" id="aibox"></div>') : ''}
        ${admin ? fold('history', 'Version history', `<div class="panel stack"><h2>Version history</h2>
          <p class="note">Every save is kept (the last 100). Restoring brings back the patterns, schedule and house map from that moment; your account, phones and app address stay as they are.</p>
          <div class="list" id="hist"><p class="muted small">Loading…</p></div></div>`) : ''}
`],
  };
  m.innerHTML = `<div class="view"><h2>${sec === 'app' ? 'App' : 'Accounts & access'}</h2>
    <div class="cols"><div class="stack">${parts[sec][0]}</div><div class="stack">${parts[sec][1]}</div></div></div>`;
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
  const drawUpdates = (u) => {
    const box = $('#updbox'); if (!box || !u) return;
    const state = !u.enabled ? 'Checking is off.'
      : u.newer ? `<b>EaveLuxOS ${esc(u.latest)} is available</b> (you have ${esc(u.current)}).`
      : u.latest ? `You have the latest version (${esc(u.current)}).`
      : u.error ? `Couldn't check yet: ${esc(u.error)}` : 'Not checked yet. The first check runs a minute after the app starts.';
    box.innerHTML = `<h2>Updates</h2>
      <p>${state}${u.checked_label ? ` <span class="small muted">Last checked ${esc(u.checked_label)}.</span>` : ''}</p>
      ${u.newer ? `<div class="row">${u.download ? `<a class="btn small primary" href="${esc(u.download)}" target="_blank" rel="noopener noreferrer">Download ${esc(u.download_name)}</a>${local ? '' : ' <span class="small muted">for the app computer, not this device</span>'}` : ''}
        <a class="btn small ${u.download ? 'ghost' : 'primary'}" href="${esc(u.url)}" target="_blank" rel="noopener noreferrer">What's new</a></div>
        ${u.notes ? `<details><summary>Release notes</summary><div class="small" style="white-space:pre-wrap;margin-top:6px">${esc(u.notes)}</div></details>` : ''}
        <p class="note">${u.from_source ? 'This copy runs from the source code: download the new zip from that page (or <code>git pull</code>) and start it the same way.' : 'Quit the app, open the download and start the new version; your settings are kept.'} See Manual, section 23.</p>` : ''}
      ${admin ? `<label class="check"><input type="checkbox" id="updon" ${u.enabled ? 'checked' : ''}> Check GitHub for a new version once a day</label>
        <div><button class="small ghost" data-updnow ${u.enabled ? '' : 'disabled'}>Check now</button></div>` : ''}
      ${admin ? updInstallHtml(u) : ''}
      <p class="note">The app computer only asks GitHub which version is newest; nothing about your home is sent, and nothing is downloaded or installed by itself.</p>`;
    const on = $('#updon');
    if (on) on.onchange = () => busy(null, () => api('update/settings', { body: { enabled: on.checked } }))
      .then(r => { drawUpdates(r); updateBar(r); }).catch(() => { on.checked = !on.checked; });
    // 4.15: install, roll back, and installing by themselves
    const au = $('#updauto');
    if (au) au.onchange = () => busy(null, () => api('update/auto', { body: { auto: au.checked } })).then(drawUpdates).catch(() => { au.checked = !au.checked; });
    box.onclick = async e => {
      const b = e.target.closest('button'); if (!b) return;
      if (b.dataset.updinstall !== undefined) {
        if (!await confirmBox(`Install EaveLuxOS ${u.latest}?`, 'It downloads the new version, checks it against the release\u2019s SHA-256 list, and restarts as the new version (the lights pause for a moment). If the new version doesn\u2019t start properly, the app goes back to this one by itself.', 'Install')) return;
        busy(b, () => api('update/install', { body: {} })).then(r => updWait(box, r.installing)).catch(() => {});
      } else if (b.dataset.updback !== undefined) {
        if (!await confirmBox('Go back to the previous version?', `EaveLuxOS restarts as ${esc(u.install.previous || 'the version before')}. Your settings stay as they are.`, 'Go back', true)) return;
        busy(b, () => api('update/rollback', { body: {} })).then(() => updWait(box, null)).catch(() => {});
      }
    };
  };
  if (admin && $('#aibox')) whenOpen('ai', () => aiPanel($('#aibox')));
  if ($('#usagebox')) whenOpen('usage', () => usagePanel($('#usagebox')));
  if ($('#pwabox')) pwaPanel($('#pwabox'));
  if ($('#updbox')) api('update').then(drawUpdates).catch(e => { const box = $('#updbox'); if (box) box.innerHTML = `<h2>Updates</h2><p class="muted small">${esc(e.message)}</p>`; });
  if (admin && $('#hist')) api('history?limit=15').then(h => {
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
    if (d.wizard !== undefined) wizard(0);
    if (d.updnow !== undefined) return busy(b, () => api('update/check', { body: {} }))
      .then(r => { drawUpdates(r); updateBar(r); toast(r.error ? r.error : r.newer ? `EaveLuxOS ${r.latest} is available` : 'You have the latest version', !!r.error); }).catch(() => {});
    if (d.port !== undefined) {
      const np = +$('#pport').value;
      if (!np || np === a.port) return toast('Enter a different port number.', true);
      if (!await confirmBox(`Move the app to port ${np}?`, `The app restarts on <code>${esc(location.protocol + '//' + location.hostname + ':' + np + '/')}</code>. Update phone bookmarks and Home Screen icons to the new address.`, 'Restart')) return;
      busy(b, () => api('port', { body: { port: np } })).then(() => {
        $('#main').innerHTML = `<div class="gate"><div class="panel stack"><h2>Moving to port ${np}…</h2><p class="muted">This page reopens on the new address in a few seconds.</p></div></div>`;
        setTimeout(() => { location.href = `${location.protocol}//${location.hostname}:${np}/#app`; }, 5000);
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
    if (t.id === 'awake') busy(null, () => api('awake', { body: { enabled: t.checked } })).then(r => toast(r.enabled ? 'Keeping this computer awake' : 'This computer may sleep on its own')).catch(() => { t.checked = !t.checked; });
    if (t.id === 'auto') busy(null, () => api('autostart', { body: { enabled: t.checked } })).then(r => toast(r.enabled ? 'Will start automatically' : 'Won’t start automatically')).catch(() => { t.checked = !t.checked; });
    if (t.id === 'locallogin') busy(null, () => api('local_login', { body: { enabled: t.checked } })).then(r => toast(r.local_login ? 'This computer now asks you to sign in too' : 'This computer no longer asks you to sign in')).catch(() => { t.checked = !t.checked; });
    if (t.id === 'idle') busy(null, () => api('session_policy', { body: { idle_hours: +t.value } })).then(r => toast(`Sign-ins now end after ${hours(r.idle_hours)} without use`)).catch(() => { t.value = a.session_idle_hours; });
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
VIEWS.access = () => VIEWS.settings('access');
VIEWS.app = () => VIEWS.settings('app');

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

/* ---------------------------------------------------------------- CONTROLLER HEALTH (4.15)
   Each controller: online and firmware (from Trimlight's cloud), how its
   requests went today and over 14 days, the last error, and a check over
   the home network. */
const ago = sec => { const s = Math.max(0, Math.round(Date.now() / 1000 - sec));
  return s < 60 ? 'just now' : s < 3600 ? `${Math.round(s / 60)} min ago` : s < 86400 ? `${Math.round(s / 3600)} h ago` : `${Math.round(s / 86400)} days ago`; };
VIEWS.health = async (fresh) => {
  const m = $('#main');
  if (!fresh) m.innerHTML = '<div class="view"><h2>Controller health</h2><p class="muted">Loading\u2026</p></div>';
  let r;
  try { r = fresh || await api('health'); } catch (e) { m.innerHTML = `<div class="view"><h2>Controller health</h2><p class="callout warn">${esc(e.message)}</p></div>`; return; }
  if (S.view !== 'health') return;
  const ro = role() === 'viewer';
  const card = d => {
    const peak = Math.max(1, ...d.days.map(x => x.ok + x.fail));
    const dot = d.online === true ? 'ok' : d.online === false ? 'bad' : '';
    return `<div class="panel stack hcard"><div class="panel-head"><h2><span class="hdot ${dot}"></span>${esc(d.name)}</h2>
        <span class="small muted">${d.online === true ? 'Online' : d.online === false ? 'Offline' : 'Not known yet'}${d.firmware ? ` \u00b7 firmware ${esc(d.firmware)}` : ''}${d.run ? '' : ' \u00b7 not run by this app'}</span></div>
      <div class="hstats">
        <div><b>${d.today.ok + d.today.fail}</b><small>requests today</small></div>
        <div><b class="${d.success !== null && d.success < 90 ? 'warn' : ''}">${d.success === null ? '\u2014' : d.success + '%'}</b><small>worked today</small></div>
        <div><b>${d.today.avg === null ? '\u2014' : d.today.avg + ' ms'}</b><small>typical answer</small></div>
        <div><b>${d.week.success === null ? '\u2014' : d.week.success + '%'}</b><small>worked this week</small></div></div>
      <div class="hbars" role="img" aria-label="Requests per day for 14 days; failed ones in red">${d.days.map(x => `<div title="${esc(x.day)}: ${x.ok} worked, ${x.fail} failed${x.avg ? `, typically ${x.avg} ms` : ''}">
        <span class="hb ok" style="height:${x.ok / peak * 100}%"></span><span class="hb bad" style="height:${x.fail / peak * 100}%"></span></div>`).join('')}</div>
      <p class="small">${d.last ? `Last request ${ago(d.last.at)}: ${d.last.ok ? `answered in ${d.last.ms} ms` : 'failed'}.` : 'No requests counted yet.'}
        ${d.error ? `<br><span class="warn">Last problem ${ago(d.error.at)}: ${esc(d.error.error)}</span>` : ''}</p>
      <p class="small">Home network: ${d.address ? `<code>${esc(d.address)}</code>${d.lan ? (d.lan.ms !== null ? `, answered in ${d.lan.ms} ms (${ago(d.lan.at)})` : `, <span class="warn">didn\u2019t answer (${ago(d.lan.at)}): ${esc(d.lan.error || '')}</span>`) : ', not checked yet'}`
        : 'no address saved (Setup \u203a Local mode, or Find controllers there).'}</p></div>`;
  };
  m.innerHTML = `<div class="view"><div class="panel-head"><h2>Controller health</h2>${ro ? '' : '<button class="small" data-hcheck>Check now</button>'}</div>
    <p class="note">How each controller has been answering this app: every request to Trimlight\u2019s cloud is counted. <b>Check now</b> asks the cloud again (online, firmware), reads each controller and greets it on your home network.</p>
    <div class="cols">${r.devices.length ? r.devices.map(card).join('') : '<p class="muted">No controllers listed yet.</p>'}</div></div>`;
  m.onclick = e => { const b = e.target.closest('[data-hcheck]'); if (b) busy(b, () => api('health/check', { body: {} })).then(x => VIEWS.health(x)).catch(() => {}); };
};

/* ---------------------------------------------------------------- UPDATES THAT INSTALL (4.15) */
function updInstallHtml(u) {
  const i = u.install || {}, last = i.last || {};
  const lastLine = last.stage === 'rolled_back' ? `<p class="callout warn small">EaveLuxOS ${esc(last.to || '')} didn\u2019t start properly (${esc(last.why || '')}), so the app went back to ${esc(last.frm || 'the version before')} by itself.</p>`
    : last.stage === 'done' && last.to === u.current && last.frm ? `<p class="small muted">Updated from ${esc(last.frm)} to ${esc(u.current)}.</p>`
    : last.stage === 'interrupted' ? `<p class="small muted">The last install (to ${esc(last.to || '?')}) didn’t finish; this is ${esc(u.current)}.</p>` : '';
  if (!i.ok) return lastLine + (u.newer ? `<p class="note">${esc(i.why || '')}</p>` : '');
  return `${lastLine}
    ${u.newer && u.download_name ? `<div><button class="small primary" data-updinstall>Install ${esc(u.latest)} now</button></div>` : ''}
    <label class="check"><input type="checkbox" id="updauto" ${u.auto ? 'checked' : ''}> Install new versions by themselves, while the lights are off</label>
    ${i.can_roll_back ? `<div><button class="small ghost" data-updback>Go back to ${esc(i.previous || 'the previous version')}</button></div>` : ''}
    <p class="note">Each download is checked against the release\u2019s SHA-256 list before it\u2019s used. The version you have now is kept, and if the new one doesn\u2019t start and keep answering, the app goes back to it by itself.</p>`;
}
/* After Install or Go back: this page waits for the app to answer again. */
async function updWait(box, version) {
  box.innerHTML = `<h2>Updates</h2><p>${version ? `Installing EaveLuxOS ${esc(version)}` : 'Going back to the previous version'}\u2026 The app restarts; this page reloads when it answers again.</p>`;
  const end = Date.now() + 240000;
  await new Promise(r => setTimeout(r, 4000));
  while (Date.now() < end) {
    try { const s = await fetch('api/session', { cache: 'no-store' }).then(r => r.json()); if (s && s.version) { location.reload(); return; } } catch { /* restarting */ }
    await new Promise(r => setTimeout(r, 2000));
  }
  box.innerHTML += '<p class="callout warn small">The app hasn\u2019t answered yet. Check the app computer.</p>';
}

/* ---------------------------------------------------------------- WHO WINS TONIGHT (4.15)
   A night, noon to noon, for each controller: what shows when, what it
   beats and why, and what could still take over (weather, automations,
   alerts). Warnings for what's likely to surprise. */
async function winPanel(box, day) {
  if (!box) return;
  let r;
  try { r = await api('conflicts' + (day ? '?date=' + encodeURIComponent(day) : '')); }
  catch (e) { box.innerHTML = `<h2>Who wins tonight</h2><p class="callout warn small">${esc(e.message)}</p>`; return; }
  const t = x => new Date(x).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
  const a0 = Date.parse(r.start), a1 = Date.parse(r.end), pct = x => (Date.parse(x) - a0) / (a1 - a0) * 100;
  const kinds = { rule: 'Rule', holiday: 'Holiday', 'game day': 'Game day' };
  const dev = Object.entries(r.devices).map(([d, spans]) => {
    const on = spans.filter(x => x.on);
    return `<div class="stack" style="gap:6px">${d !== 'all' ? `<b>${esc(r.names[d] || d)}</b>` : ''}
      <div class="tlbar" style="height:14px" aria-hidden="true">${on.map(x => { const e = (S.settings.effects || {})[x.winner.effect_key];
        const c = e && e.colors ? '#' + String(e.colors.find(k => !/^(off|x)$/i.test(k)) || 'FFC062').replace('#', '') : '#FFC062';
        return `<i style="left:${pct(x.start)}%;width:${pct(x.end) - pct(x.start)}%;background:${esc(c)}" title="${esc(x.winner.name)}"></i>`; }).join('')}</div>
      <div class="list">${on.length ? on.map(x => `<div class="item"><div class="grow">
          <div class="name">${t(x.start)} \u2013 ${t(x.end)}: ${esc(x.winner.effect)}</div>
          <div class="sub">${kinds[x.winner.kind] || 'Rule'} \u201c${esc(x.winner.name)}\u201d, priority ${x.winner.priority}${x.beaten.length ? '. Beats ' + x.beaten.map(b => `\u201c${esc(b.name)}\u201d (${esc(b.why)})`).join(', ') : ''}.</div>
          ${x.weather.length ? `<div class="sub">If the weather turns: ${x.weather.map(w => `${esc(w.name)} (${esc(w.when.join(', '))}, priority ${w.priority}) shows ${esc(w.effect)}`).join('; ')}.</div>` : ''}</div></div>`).join('')
        : '<p class="muted small">The lights stay off this night.</p>'}</div></div>`;
  }).join('');
  const autos = r.automations.length ? `<p class="small"><b>Automations</b> come on top when they run: ${r.automations.map(a => `\u201c${esc(a.name)}\u201d ${a.at ? 'at ' + t(a.at) : esc(a.when)} (priority ${a.priority})`).join('; ')}.</p>` : '';
  box.innerHTML = `<div class="panel-head"><h2>Who wins tonight</h2><label class="row small">Night of <input type="date" id="windate" value="${esc(r.date)}" style="width:auto"></label></div>
    ${r.warnings.map(w => `<p class="callout ${w.level === 'weather' ? '' : 'warn'} small">${esc(w.text)}</p>`).join('')}
    ${dev}${autos}
    <p class="note">From noon to noon. The order, highest first: a security flash or celebration, a severe weather warning, a choice made by hand (until the next scheduled change), automations when they run, a weather rule with a higher priority than what's on, then rules, holidays and game days by priority (the same priority: the one listed first).</p>`;
  box.onchange = e => { if (e.target.id === 'windate' && e.target.value) winPanel(box, e.target.value); };
}

/* ---------------------------------------------------------------- ON A PHONE (4.14)
   EaveLuxOS as an app on the home screen: a service worker (sw.js) keeps
   the app's own files on the phone where the browser allows it (an https://
   address, or this computer); shortcuts on the icon (?do=on, off, resume,
   flash); an install button where the browser offers one; and Quick, a
   screen of big buttons for what you reach for most. */
const COARSE = matchMedia('(pointer: coarse)').matches;
const standalone = () => matchMedia('(display-mode: standalone)').matches || navigator.standalone === true;
const IOS = /iPhone|iPad|iPod/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
let INSTALL = null;
window.addEventListener('beforeinstallprompt', e => { e.preventDefault(); INSTALL = e; installBar(); const p = $('#pwabox'); if (p) pwaPanel(p); });
window.addEventListener('appinstalled', () => { INSTALL = null; const b = $('#installbar'); if (b) b.remove(); toast('EaveLuxOS is on your home screen'); });
function pwaStart() {
  if ('serviceWorker' in navigator && window.isSecureContext && !pwaStart.done) {
    pwaStart.done = true;
    navigator.serviceWorker.register('sw.js').catch(() => { /* the app works as before without it */ });
  }
  const p = new URLSearchParams(location.search), act = p.get('do');
  if (p.has('do') || p.has('app')) history.replaceState(null, '', location.pathname + location.hash);
  if (act && ['on', 'off', 'resume', 'flash'].includes(act)) {
    if (role() === 'viewer') toast('A viewer account can\u2019t change the lights.', true);
    // Review #1 (4.14): the installed app's own shortcuts act at once; the same
    // address opened as a link (an email, another web page) asks first.
    else if (standalone()) quickDo({ type: act }).catch(() => {});
    else confirmBox(`${quickInfo({ type: act }).label}?`, 'A link asked EaveLuxOS to do this.', 'Yes').then(ok => ok && quickDo({ type: act }).catch(() => {}));
  }
  installBar();
}
/* A bar on a phone's browser (not the installed app): put it on the home screen. */
function installBar() {
  if (!COARSE || standalone() || $('#installbar')) return;
  let hidden = null; try { hidden = localStorage.getItem('elx-install-hidden'); } catch { /* no storage */ }
  if (hidden) return;
  const bar = document.createElement('div');
  bar.id = 'installbar'; bar.className = 'callout ok viewonly updbar';
  bar.innerHTML = `<span class="grow"><b>Put EaveLuxOS on your home screen</b> for one-tap lights.</span>
    ${INSTALL ? '<button class="small primary" data-inst>Install</button>' : '<button class="small primary" data-insthow>How</button>'}
    <button class="small ghost" data-insthide>Not now</button>`;
  bar.onclick = e => {
    const b = e.target.closest('button'); if (!b) return;
    if (b.dataset.inst !== undefined) return pwaInstall();
    if (b.dataset.insthow !== undefined) return go('app');
    try { localStorage.setItem('elx-install-hidden', '1'); } catch { /* no storage */ }
    bar.remove();
  };
  const upd = $('#updbar'); upd.parentNode.insertBefore(bar, upd.nextSibling);
}
async function pwaInstall() {
  if (!INSTALL) return go('app');
  INSTALL.prompt();
  const r = await INSTALL.userChoice.catch(() => null);
  INSTALL = null;
  if (r && r.outcome === 'accepted') { const b = $('#installbar'); if (b) b.remove(); }
}
/* Setup › App: On your phone. */
function pwaPanel(box) {
  const secure = window.isSecureContext, sw = !!(navigator.serviceWorker && navigator.serviceWorker.controller);
  const how = IOS ? 'In <b>Safari</b>, tap <b>Share</b> (the square with an arrow), then <b>Add to Home Screen</b>.'
    : 'In <b>Chrome</b>, tap the <b>\u22ee</b> menu, then <b>Install app</b> (or <b>Add to Home screen</b>).';
  box.innerHTML = `<h2>On your phone</h2>
    <p>${standalone() ? '<b>You\u2019re using the installed app.</b>' : INSTALL ? '<b>This browser can install EaveLuxOS as an app.</b>' : 'Put EaveLuxOS on your phone\u2019s home screen: it opens full screen, like any app, with no app store.'}</p>
    ${INSTALL ? '<div><button class="primary" data-pwainstall>Install EaveLuxOS</button></div>' : standalone() ? '' : `<p class="small">${how}</p>`}
    <ul class="small" style="margin:0;padding-left:1.2em">
      <li>The icon opens <b>Quick</b>: big buttons for On, Off, the schedule, your favorites and scenes. Press and hold the icon (Android) for <b>Lights on</b>, <b>Lights off</b>, <b>Back to the schedule</b> and <b>Security flash</b>.</li>
      <li>${secure ? (sw ? 'This address is secure, so the app\u2019s files are kept on this device: it opens at once, and says so plainly when you\u2019re away from home.' : 'This address is secure, so the app\u2019s files are kept on this device after the next visit.')
        : 'This address is plain <code>http://</code>, so the app works but isn\u2019t kept on the phone, and Android adds a shortcut instead of an app. For the full app, use the app\u2019s <code>https://</code> address (Manual, section 8: HTTPS with mkcert, trusted on the phone).'}</li>
      <li>It works on your home Wi-Fi (or your home VPN), as the app always has.</li></ul>`;
  box.onclick = e => { if (e.target.closest('[data-pwainstall]')) pwaInstall(); };
}

/* Quick: big buttons for what you reach for most. The household chooses
   them (settings "quick", up to 12); until then: On, Off, the schedule,
   your favorites and your scenes. */
const QUICK_MAX = 12;
function quickTiles() {
  const effs = S.settings.effects || {}, autos = S.settings.automations || [];
  const ok = t => t && (['on', 'off', 'resume', 'flash'].includes(t.type) || (t.type === 'pattern' && effs[t.key]) || (t.type === 'auto' && autos.some(a => a.id === t.id)));
  const set = (S.settings.quick || []).filter(ok);
  if (set.length) return set.slice(0, QUICK_MAX);
  const scenes = Object.keys(effs).filter(k => effs[k].scene && !favs().includes(k)).slice(0, 3);
  return [{ type: 'on' }, { type: 'off' }, { type: 'resume' }, ...favs().map(key => ({ type: 'pattern', key })), ...scenes.map(key => ({ type: 'pattern', key }))].slice(0, QUICK_MAX);
}
function quickInfo(t) {
  const e = (S.settings.effects || {})[t.key], a = (S.settings.automations || []).find(x => x.id === t.id);
  return {
    on: { label: 'Lights on', sub: 'Tonight\u2019s pattern', icon: 'bulbon' }, off: { label: 'Lights off', sub: 'Until the next scheduled change', icon: 'power' },
    resume: { label: 'Back to the schedule', sub: 'Whatever the schedule says now', icon: 'time' },
    flash: { label: 'Security flash', sub: 'Bright lights for a few minutes', icon: 'bolt' },
    pattern: { label: e ? e.label || t.key : t.key, sub: e && e.scene ? 'Scene' : 'Pattern', colors: e ? effectSwatches(e).slice(0, 6) : [] },
    auto: { label: a ? a.name : 'Automation', sub: 'Automation: try it now', icon: 'bolt' },
  }[t.type] || { label: t.type };
}
async function quickDo(t, b) {
  if (navigator.vibrate) { try { navigator.vibrate(12); } catch { /* not allowed */ } }
  const run = {
    on: () => api('action', { body: { action: 'on' } }), off: () => api('action', { body: { action: 'off' } }),
    resume: () => api('action', { body: { action: 'resume' } }), flash: () => api('action', { body: { action: 'flash' } }),
    pattern: () => api('action', { body: { action: 'on', effect: t.key } }),
    auto: () => api('automation/try', { body: { id: t.id } }),
  }[t.type];
  if (!run) return;
  await busy(b, run);
  const info = quickInfo(t);
  toast({ on: 'Lights on', off: 'Lights off', resume: 'Back on the schedule', flash: 'Security flash on' }[t.type] || `${info.label}`);
  refreshStatus().catch(() => {});
  if (S.view === 'quick') VIEWS.quick(true);
}
VIEWS.quick = async (soft) => {
  const m = $('#main');
  if (!soft) m.innerHTML = '<div class="view"><p class="muted">Loading\u2026</p></div>';
  let st = S.status;
  try { st = await refreshStatus(); } catch (e) { if (!st) { m.innerHTML = `<div class="view"><p class="callout warn">${esc(e.message)}</p></div>`; return; } }
  if (S.view !== 'quick') return;
  const ro = role() === 'viewer', tiles = quickTiles(), lv = st.levels || {}, t = st.target || {};
  const { head, sub } = st.setup_only ? { head: 'Setup needed', sub: '' } : stateLine(st);
  m.innerHTML = `<div class="view quickview">
    <div class="qhead"><div class="grow"><h1>${esc(head)}</h1><p class="muted">${esc(sub)}</p></div>
      ${ro ? '' : '<button class="small ghost" data-qedit>Edit</button>'}</div>
    <div class="qtiles">${tiles.map((x, i) => { const info = quickInfo(x);
      const cur = (x.type === 'pattern' && t.on && t.effect_key === x.key) || (x.type === 'off' && !t.on);
      return `<button class="qtile${cur ? ' current' : ''}" data-qi="${i}" ${ro || st.setup_only ? 'disabled' : ''} aria-label="${esc(info.label)}">
        ${info.colors ? `<span class="qsw">${info.colors.map(c => `<i style="background:${esc(c)}"></i>`).join('') || '<i></i>'}</span>` : `<span class="qic">${icon(info.icon)}</span>`}
        <b>${esc(info.label)}</b><small>${esc(info.sub)}</small></button>`; }).join('')}</div>
    ${t.on && !ro && t.reason !== 'music' && t.reason !== 'flash' ? `<label class="field qbright">Brightness <span class="muted" id="qbv">${Math.round((lv.brightness ?? 200) / 255 * 100)}%</span>
      <input type="range" id="qbright" min="10" max="255" value="${lv.brightness ?? 200}" aria-label="Brightness"></label>` : ''}
    <div class="row"><button class="ghost" data-qhome>Everything else (Home)</button></div></div>`;
  m.onclick = e => {
    const b = e.target.closest('button'); if (!b) return;
    if (b.dataset.qi !== undefined) return quickDo(tiles[+b.dataset.qi], b).catch(() => {});
    if (b.dataset.qhome !== undefined) return go('home');
    if (b.dataset.qedit !== undefined) return quickEdit();
  };
  let bt = null;
  m.oninput = e => {
    if (e.target.id !== 'qbright') return;
    const v = +e.target.value; $('#qbv').textContent = Math.round(v / 255 * 100) + '%';
    clearTimeout(bt); bt = setTimeout(() => api('action', { body: { action: 'levels', brightness: v } }).catch(err => toast(err.message, true)), 250);
  };
};
function quickEdit() {
  const effs = Object.entries(S.settings.effects || {}), autos = S.settings.automations || [];
  let list = clone(quickTiles());
  const opts = () => [['on', 'Lights on'], ['off', 'Lights off'], ['resume', 'Back to the schedule'], ['flash', 'Security flash'],
    ...effs.map(([k, e]) => [`p:${k}`, `${e.scene ? 'Scene' : 'Pattern'}: ${e.label || k}`]), ...autos.map(a => [`a:${a.id}`, `Automation: ${a.name}`])];
  const parse = v => v.startsWith('p:') ? { type: 'pattern', key: v.slice(2) } : v.startsWith('a:') ? { type: 'auto', id: v.slice(2) } : { type: v };
  const draw = f => {
    $('[data-qlist]', f).innerHTML = list.map((x, i) => `<div class="item"><span class="grow">${esc(quickInfo(x).label)}</span>
      <button type="button" class="small ghost" data-qup="${i}" ${i ? '' : 'disabled'} aria-label="Move up">\u2191</button>
      <button type="button" class="small ghost" data-qdown="${i}" ${i < list.length - 1 ? '' : 'disabled'} aria-label="Move down">\u2193</button>
      <button type="button" class="small ghost danger" data-qdel="${i}" aria-label="Remove">\u2715</button></div>`).join('') || '<p class="muted small">No buttons: Quick shows the usual ones.</p>';
    $('[data-qadd]', f).disabled = list.length >= QUICK_MAX;
  };
  dialog(`<h2>Quick buttons</h2><p class="note">Up to ${QUICK_MAX}, in this order, for everyone in the household.</p>
    <div class="list" data-qlist></div>
    <div class="row"><select name="add" style="flex:1;min-width:0">${opts().map(([v, l]) => `<option value="${esc(v)}">${esc(l)}</option>`).join('')}</select>
      <button type="button" class="small" data-qadd>Add</button></div>`, async () => {
    const n = clone(S.settings); n.quick = list; await saveSettings(n, 'Quick buttons saved'); VIEWS.quick(true);
  }, { ok: 'Save', onOpen: f => {
    draw(f);
    f.addEventListener('click', e => {
      const b = e.target.closest('button'); if (!b) return; const d = b.dataset;
      if (d.qadd !== undefined) list.push(parse(f.add.value));
      else if (d.qup) { const i = +d.qup; [list[i - 1], list[i]] = [list[i], list[i - 1]]; }
      else if (d.qdown) { const i = +d.qdown; [list[i + 1], list[i]] = [list[i], list[i + 1]]; }
      else if (d.qdel) list.splice(+d.qdel, 1);
      else return;
      draw(f);
    });
  } });
}

/* ---------------------------------------------------------------- start */
window.addEventListener('hashchange', () => { const v = location.hash.slice(1); if (S.session?.authed && v !== S.view && (VIEWS[v] || v in VIEW_ALIAS)) go(v, undefined, true); });
boot().catch(e => {
  // 4.14: opened from the home screen away from home (or the app computer is off): say so plainly
  const away = e instanceof TypeError || !navigator.onLine;
  $('#main').innerHTML = away ? `<div class="gate"><div class="panel stack"><h2>Can\u2019t reach EaveLuxOS</h2>
      <p>This ${COARSE ? 'phone' : 'device'} can\u2019t reach the app computer right now. EaveLuxOS works on your home network: join your home Wi-Fi (or your home VPN), and check the app computer is on with EaveLuxOS running.</p>
      <div><button class="primary" data-retry>Try again</button></div></div></div>`
    : `<div class="gate"><p class="callout warn">Can't reach the app: ${esc(e.message)}</p></div>`;
  const r = $('#main [data-retry]'); if (r) r.onclick = () => location.reload();      // no inline handlers (the page's security policy)
});

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
    if (r.status < 500 && r.status !== 415) throw new Error(e.error || `Upload failed (${r.status}).`);   // 4.4.5: any trouble on the app computer: the browser shrinks it
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
/* One load per photo version, shared: the House map's photo and House view
   ask at the same moment, and a second load used to release the first one's
   copy while the photo was still using it (3.17.1). */
const photoLoads = {};
function loadPhoto(side) {
  const key = side + ':' + (S.photoV || 0);
  if (photoCache[key]) return Promise.resolve(photoCache[key]);
  if (photoLoads[key]) return photoLoads[key];
  return (photoLoads[key] = (async () => {
    try {
      const r = await fetch('api/photo/' + encodeURIComponent(side), { headers: authHeaders(), cache: 'no-store' });
      if (!r.ok) throw new Error('no photo');
      const url = URL.createObjectURL(await r.blob());
      for (const k of Object.keys(photoCache)) if (k.startsWith(side + ':') && k !== key) { URL.revokeObjectURL(photoCache[k]); delete photoCache[k]; }
      return (photoCache[key] = url);
    } finally { delete photoLoads[key]; }
  })());
}
/* Four elevations of the house plus a shed are always there; added ones
   follow. 4.12: a side can have versions (day and night photos, before and
   after), each a side of its own with "of" naming its elevation. */
function mapData() {
  const m = S.settings.map || {}, saved = m.sides || [], RLx = window.Roofline;
  const sides = [...RLx.DEFAULT_SIDES.map(d => { const x = saved.find(y => y.id === d.id);
      return x ? { ...d, ...x, name: x.name === RLx.OLD_NAMES[d.id] ? d.name : x.name } : { ...d }; }),
    ...saved.filter(x => !RLx.DEFAULT_SIDES.some(d => d.id === x.id))];
  return { total_bulbs: m.total_bulbs ?? null, sides, landmarks: m.landmarks || [], zones: m.zones || [], rooflines: clone(m.rooflines || {}) };
}
/* 4.12: elevations and their versions. A "key" is what a photo, its
   rooflines and its pins are saved under: an elevation's id (its first
   version) or one of its versions' ids. */
const Elev = {
  list: md => md.sides.filter(x => !x.of),
  of: (md, key) => { const x = md.sides.find(y => y.id === key); return x && x.of ? md.sides.find(y => y.id === x.of) || x : x; },
  versions: (md, id) => [md.sides.find(y => y.id === id), ...md.sides.filter(y => y.of === id)].filter(Boolean),
  use: (md, e) => (e.use && md.sides.some(y => y.id === e.use && (y.id === e.id || y.of === e.id))) ? e.use : e.id,
  vname: (md, key) => { const x = md.sides.find(y => y.id === key); return !x ? '' : x.of ? x.name : (x.vname || 'Main'); },
  label: (md, key) => { const e = Elev.of(md, key); if (!e) return key; const vs = Elev.versions(md, e.id);
    return vs.length > 1 ? `${e.name} \u00b7 ${Elev.vname(md, key)}` : e.name; },
  // A new id for a version or an imported elevation, unused so far
  slug: name => String(name).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 30) || 'side',
  newId: (md, base) => { const b = Elev.slug(base);
    for (let i = 0; ; i++) { const id = i ? `${b}-${i + 1}` : b;
      if (!md.sides.some(x => x.id === id) && !(md.rooflines || {})[id] && !(S.photos && S.photos.has(id))) return id; } },
  KINDS: [['front', 'Front elevation'], ['side', 'Side elevation'], ['rear', 'Rear elevation'], ['other', 'Other (garage, shed, deck)']],
};
function addressSpace(dev) {
  // 4.10: one controller's own count when asked for one; otherwise the house's
  const d = dev && (S.devices || []).find(x => x.id === dev && x.ports);
  return d ? devBulbs(d) : mapData().total_bulbs || totalBulbs();
}
/* 4.10: the House tab with two or more controllers. S.houseDev is the
   controller the finder, scenes and new zones are for ('' for all). */
function houseDevs() { return (S.devices || []).filter(x => x.selected && x.ports); }
function houseDev() { return houseDevs().length > 1 && houseDevs().some(x => x.id === S.houseDev) ? S.houseDev : ''; }
function houseSpace() { return addressSpace(houseDev()); }
function devName(id) { return ((S.devices || []).find(x => x.id === id) || {}).name || 'a controller not run now'; }
function housePreview(effect, minutes) {
  const device = houseDev();
  return api('action', { body: { action: 'try', effect, minutes, ...(device ? { device } : {}) } });
}
// A zone or landmark for a controller applies to it; one for all to every one.
const forDev = (x, dev) => !x.device || !dev || x.device === dev;
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
  m.innerHTML = '<div class="view"><h2>House</h2><p class="muted">Loading…</p></div>';
  await loadDevices().catch(() => {});
  S.photos = new Set(await api('photos').catch(() => []));
  S.finder = S.finder || { bulb: 1, end: 1, range: false, step: 1, color: '#FFC062', live: false, side: 'front', placing: false };
  const F = S.finder;
  const render = () => {
    const md = mapData(), T = houseSpace(), HD = houseDev(), many = houseDevs().length > 1;
    F.bulb = Math.max(1, Math.min(T, F.bulb)); F.end = Math.max(F.bulb, Math.min(T, F.end));
    if (!md.sides.some(x => x.id === F.side)) F.side = md.sides[0].id;
    const pins = md.landmarks.map((l, i) => ({ ...l, i })).filter(l => l.side === F.side && l.x != null && forDev(l, HD));
    const sideNow = Elev.of(md, F.side) || {}, vers = Elev.versions(md, sideNow.id), useKey = Elev.use(md, sideNow);
    const isDefault = window.Roofline.DEFAULT_SIDES.some(x => x.id === sideNow.id);
    const inSel = b => F.range ? b >= F.bulb && b <= F.end : b === F.bulb;
    const ports = ((S.devices || []).find(x => x.selected && x.ports) || {}).ports || [];
    if (R.tracing) F.placing = false;
    const RF = roofHtml(md, F.side);
    m.innerHTML = `<div class="view">
      <div class="panel-head"><h2>House</h2><span class="muted small">Find a bulb, pin it on a photo, trace the roofline, name the corners and sections.</span>
        ${many ? `<label class="row small" style="gap:6px">Controller<select id="hdev" style="width:auto"><option value="">All controllers</option>${houseDevs().map(x =>
          `<option value="${esc(x.id)}" ${x.id === HD ? 'selected' : ''}>${esc(x.name || 'Controller')} (${devBulbs(x)} bulbs)</option>`).join('')}</select></label>` : ''}</div>
      ${many && !HD ? '<p class="note">The finder lights a bulb number on every controller at once. Choose a <b>Controller</b> above to light only that one\u2019s; the others keep showing what they were.</p>' : ''}
      ${RF.flat}
      ${fold('whole', 'Whole house: every elevation at once', '<div class="panel stack" id="wholebox"><p class="muted small">Loading\u2026</p></div>')}
      <div class="cols wide-left">
        <div class="stack">
          <div class="panel stack">
            <div class="row" role="tablist" aria-label="Elevations of the house">${Elev.list(md).map(x => `<button class="small ${x.id === sideNow.id ? 'current' : ''}" data-side="${esc(x.id)}">${esc(x.name)}</button>`).join('')}
              <button class="small ghost" data-addside>Add an elevation</button></div>
            <div class="row small" aria-label="Versions of this elevation"><span class="muted">Versions</span>${vers.map(v => `<button class="small ${v.id === F.side ? 'current' : 'ghost'}" data-ver="${esc(v.id)}" ${v.id === useKey && vers.length > 1 ? 'title="Shown in the whole house"' : ''}>${esc(Elev.vname(md, v.id))}${v.id === useKey && vers.length > 1 ? ' \u2605' : ''}</button>`).join('')}
              <button class="small ghost" data-addver ${md.sides.length >= 80 ? 'disabled' : ''}>Add a version</button>
              ${vers.length > 1 && F.side !== useKey ? '<button class="small" data-usever>Show this version in the whole house</button>' : ''}</div>
            <div class="row small">${role() === 'viewer' ? '' : '<button class="small" data-calib>Calibrate with camera</button>'}<button class="small ghost" data-renelev>Rename</button><button class="small ghost" data-exportelev title="A file with this elevation's photos, rooflines, bulbs and pins">Export this elevation</button>
              <label class="btn small ghost">Import an elevation<input type="file" id="elevfile" accept=".json,application/json" hidden></label>
              ${F.side !== sideNow.id ? '<button class="small ghost danger" data-delver>Delete this version</button>' : ''}
              ${!isDefault ? '<button class="small ghost danger" data-delelev>Delete this elevation</button>' : ''}</div>
            ${many ? `<label class="row small" style="gap:6px">This elevation\u2019s lights<select id="sidedev" style="width:auto"><option value="">Any controller</option>${houseDevs().map(x =>
              `<option value="${esc(x.id)}" ${x.id === sideNow.device ? 'selected' : ''}>${esc(x.name || 'Controller')}</option>`).join('')}</select>
              <span class="note">Choosing this elevation then chooses its controller.</span></label>` : ''}
            <div class="photo" id="photo" data-placing="${F.placing}" data-tracing="${R.tracing}">
              ${S.photos.has(F.side) ? `<img id="pimg" alt="Photo of the ${esc(Elev.label(md, F.side))}">` : ''}
              ${RF.overlay}
              <div class="nophoto" ${S.photos.has(F.side) ? 'hidden' : ''}><p>No photo of this side yet.</p><p class="small muted">Take one at night with the lights on, from the street.</p></div>
              ${pins.map(l => `<button class="pin ${inSel(l.bulb) ? 'on' : ''}" style="left:${l.x * 100}%;top:${l.y * 100}%" data-pin="${l.i}" title="${esc(l.name)}: bulb ${l.bulb}"><span>${esc(l.name)}</span></button>`).join('')}
            </div>
            <div class="row"><label class="btn small">${'Upload photo'}<input type="file" id="pfile" accept="image/*" hidden></label>
              <button class="small ${F.placing ? 'current' : 'ghost'}" data-place>${F.placing ? 'Tap the photo where the bulb is…' : `Pin bulb ${F.bulb} on this photo`}</button>
              <button class="small ghost danger" data-delphoto>Remove photo</button></div>
            ${RF.tools}
            <p class="note">Photos stay on this computer and are never included in exported pattern files. <b>Export this elevation</b> makes a file that does include its photos, to move it to another EaveLuxOS. Roofline detection runs in this browser.</p>
          </div>
          <div class="panel stack" id="hvbox"></div>
          <div class="stack">
            ${fold('landmarks', 'Landmarks', `<div class="panel stack"><h2>Landmarks</h2>
              <div class="row"><input type="text" id="lmname" maxlength="60" placeholder="e.g. Front gable peak" class="grow" style="flex:1"><button class="small" data-savelm>Save bulb ${F.bulb}</button></div>
              <div class="list">${md.landmarks.length ? md.landmarks.map((l, i) => ({ ...l, i })).sort((a, b) => a.bulb - b.bulb).map(l => `<div class="item"><div class="grow"><div class="name">${esc(l.name)}</div>
                <div class="sub">Bulb ${l.bulb}${many && l.device ? ' on ' + esc(devName(l.device)) : ''}${l.side ? ' · ' + esc(Elev.label(md, l.side)) : ''}${l.x != null ? ' · pinned' : ''}</div></div>
                <button class="small" data-golm="${l.i}">Show</button><button class="small ghost danger" data-dellm="${l.i}" aria-label="Delete ${esc(l.name)}">✕</button></div>`).join('')
                : '<p class="muted small">Find a corner or peak with the finder, give it a name, and save it here.</p>'}</div></div>`)}
            ${fold('zones', 'Zones', `<div class="panel stack"><h2>Zones</h2>
              <div class="row"><input type="text" id="zname" maxlength="60" placeholder="e.g. Garage roof" class="grow" style="flex:1"><button class="small" data-savezone ${F.range ? '' : 'disabled'}>Save ${F.range ? `${F.bulb}–${F.end}` : 'range'}</button></div>
              ${F.range ? '' : '<p class="note">Turn on <b>Select a range</b> in the finder to save a section of roofline.</p>'}
              <div class="list">${md.zones.length ? md.zones.map((z, i) => `<div class="item"><div class="grow"><div class="name">${esc(z.name)}</div><div class="sub">Bulbs ${z.start}–${z.end} (${z.end - z.start + 1})${z.reverse ? ' · runs the other way' : ''}${many ? ' · ' + (z.device ? esc(devName(z.device)) : 'every controller') : ''}</div></div>
                <button class="small" data-gozone="${i}">Show</button><button class="small ghost" data-editzone="${i}" aria-label="Edit ${esc(z.name)}">Edit</button><button class="small ghost danger" data-delzone="${i}" aria-label="Delete ${esc(z.name)}">✕</button></div>`).join('')
                : '<p class="muted small">Zones are named sections, like "garage roof", that you can paint in Create.</p>'}</div></div>`)}
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
            <p class="note">Everything else ${HD ? `on ${esc(devName(HD))}` : ''} goes dark while the finder shows${HD ? '; the other controllers keep showing what they were' : ''}. The schedule comes back by itself 10 minutes after your last change. Bulb numbers are pattern addresses: if two ports overlap (a mirrored run), one number lights in both places.</p>
          </div>
          ${fold('numbering', 'Bulb numbering', `<div class="panel stack"><h2>Bulb numbering</h2>
            <p class="small">${ports.length ? 'From the controller: ' + ports.map(p => p.start && p.end && !p.unused ? `Port ${p.id + 1} ${p.start}–${p.end}` : `Port ${p.id + 1} not connected`).join(', ') + '.' : 'Port layout unknown until the controller answers.'}</p>
            <label class="field">Use a different total <span class="hint">Leave empty to use the controller's ports (${totalBulbs()}).</span>
              <input type="number" id="ftotal" min="1" max="10000" value="${md.total_bulbs ?? ''}" placeholder="${totalBulbs()}"></label>
            <div><button class="small" data-savetotal>Save</button></div></div>`)}
        </div>
      </div></div>`;
    const img = $('#pimg');
    if (img) {
      img.onload = () => roofWire(mapData(), F.side);
      loadPhoto(F.side).then(url => { img.src = url; }).catch(() => { img.hidden = true; $('.nophoto', m).hidden = false; });
    }
    roofWire(md, F.side);
    houseView($('#hvbox'), F.side);
    whenOpen('whole', () => wholePanel($('#wholebox')));
  };
  VIEWS.mapRender = render;
  let liveTimer = null;
  const show = async (btn) => {
    const T = houseSpace(); const def = highlightDef(F.bulb, F.range ? F.end : F.bulb, T, F.color);
    await housePreview(def, 10);
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
        <p class="note">Bulb ${F.bulb} on the ${esc(Elev.label(md, F.side).toLowerCase())} photo.</p>`, async f => {
        const nm = f.nm.value.trim(); if (!nm) throw new Error('Give it a name.');
        await saveMap(mp => { const lm = { name: nm, bulb: F.bulb, side: F.side, x: Math.round(x * 1000) / 1000, y: Math.round(y * 1000) / 1000 };
          if (existing >= 0) mp.landmarks[existing] = lm; else mp.landmarks.push(lm); }, 'Pinned');
        render();
      }, { ok: 'Save pin', onOpen: f => f.nm.focus() });
      return render();
    }
    if (!b) return; const d = b.dataset, md = mapData(), T = houseSpace();
    if (d.side) {
      if (R.tracing) return toast('Save or cancel the roofline section first.', true);
      const el = md.sides.find(x => x.id === d.side) || {};
      const last = (S.lastVer || {})[d.side];              // 4.12: the version last looked at, else the one in use
      F.side = last && Elev.versions(md, d.side).some(v => v.id === last) ? last : Elev.use(md, el); F.placing = false; R.hint = '';
      const sd = el.device;           // 4.10: its controller too
      if (sd && houseDevs().some(x => x.id === sd)) S.houseDev = sd;
      return render(); }
    if (d.step) { const k = +d.step * F.step, w = F.end - F.bulb; F.bulb = Math.max(1, Math.min(T - (F.range ? w : 0), F.bulb + k)); F.end = F.range ? F.bulb + w : F.bulb; return moved(); }
    if (d.by) { F.step = +d.by; return render(); }
    if (d.show !== undefined) return busy(b, show).then(() => toast(F.range ? `Showing bulbs ${F.bulb}–${F.end}` : `Showing bulb ${F.bulb}`)).catch(() => {});
    if (d.resume !== undefined) return busy(b, () => api('action', { body: { action: 'resume' } })).then(() => toast('Back on the schedule')).catch(() => {});
    if (d.place !== undefined) { if (R.tracing) return toast('Save or cancel the roofline section first.', true); F.placing = !F.placing; return render(); }
    if (d.pin) { const l = md.landmarks[+d.pin]; F.range = false; F.bulb = F.end = l.bulb; return moved(); }
    if (d.golm) { const l = md.landmarks[+d.golm]; F.range = false; F.bulb = F.end = l.bulb; if (l.side) F.side = l.side; if (l.device) S.houseDev = l.device; render(); return busy(b, show).catch(() => {}); }
    if (d.dellm) return busy(b, () => saveMap(mp => mp.landmarks.splice(+d.dellm, 1), 'Landmark deleted')).then(render).catch(() => {});
    if (d.savelm !== undefined) { const nm = $('#lmname').value.trim(); if (!nm) return toast('Type a name first.', true);
      return busy(b, () => saveMap(mp => mp.landmarks.push({ name: nm, bulb: F.bulb, side: F.side, ...(houseDev() ? { device: houseDev() } : {}) }), `Saved \u201c${nm}\u201d as bulb ${F.bulb}`)).then(render).catch(() => {}); }
    if (d.gozone) { const z = md.zones[+d.gozone]; if (z.device) S.houseDev = z.device; F.range = true; F.bulb = z.start; F.end = z.end; render(); return busy(b, show).catch(() => {}); }
    if (d.delzone) return busy(b, () => saveMap(mp => mp.zones.splice(+d.delzone, 1), 'Zone deleted')).then(render).catch(() => {});
    if (d.editzone) return zoneDialog(+d.editzone, F, render);
    if (d.savezone !== undefined) { const nm = $('#zname').value.trim(); if (!nm) return toast('Type a zone name first.', true);
      return busy(b, () => saveMap(mp => mp.zones.push({ name: nm, start: F.bulb, end: F.end, ...(houseDev() ? { device: houseDev() } : {}) }), `Saved zone \u201c${nm}\u201d${houseDev() ? ' for ' + devName(houseDev()) : ''}`)).then(render).catch(() => {}); }
    if (d.calib !== undefined) { if (R.tracing) return toast('Save or cancel the roofline section first.', true); return calibDialog(F, render); }
    if (d.ver) { if (R.tracing) return toast('Save or cancel the roofline section first.', true);
      F.side = d.ver; F.placing = false; R.hint = ''; S.lastVer = { ...(S.lastVer || {}), [Elev.of(md, d.ver).id]: d.ver }; return render(); }
    if (d.addside !== undefined || d.renelev !== undefined || d.addver !== undefined || d.usever !== undefined
        || d.delver !== undefined || d.delelev !== undefined || d.exportelev !== undefined) {
      if (R.tracing) return toast('Save or cancel the roofline section first.', true);
      return elevAction(d, b, md, Elev.of(md, F.side), F, render);
    }
    if (d.delphoto !== undefined) { if (!await confirmBox('Remove this photo?', 'Pins on it stay saved and come back if you upload a new photo.', 'Remove', true)) return;
      return busy(b, () => api('photo/delete', { body: { side: F.side } })).then(() => { S.photos.delete(F.side); render(); }).catch(() => {}); }
    if (d.savetotal !== undefined) { const v = $('#ftotal').value; return busy(b, () => saveMap(mp => mp.total_bulbs = v ? Math.max(1, Math.min(10000, +v)) : null, 'Saved')).then(render).catch(() => {}); }
  };
  m.onchange = async e => {
    const t = e.target, T = houseSpace();
    if (t.id === 'hdev') { S.houseDev = t.value; return render(); }
    if (t.id === 'sidedev') {
      const v = t.value, side = Elev.of(mapData(), F.side).id;      // 4.12: the elevation's, for all its versions
      return busy(null, () => saveMap(mp => {
        let x = mp.sides.find(y => y.id === side);
        if (!x) { x = { ...(mapData().sides.find(y => y.id === side) || { id: side }) }; mp.sides.push(x); }
        if (v) x.device = v; else delete x.device;
      }, v ? `This side is ${devName(v)}\u2019s` : 'This side is any controller\u2019s')).then(() => { if (v) S.houseDev = v; render(); }).catch(() => {});
    }
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
    if (t.id === 'elevfile' && t.files[0]) { const file = t.files[0]; t.value = ''; return elevImport(file, F, render); }
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


/* 4.12: each elevation once, as the version shown in the whole house. */
function flatSides(md) { return Elev.list(md).map(e => ({ id: Elev.use(md, e), name: Elev.label(md, Elev.use(md, e)) })); }

/* ---------------------------------------------------------------- HOUSE MAP: whole house (4.12)
   Every elevation at once, each in the version shown in the whole house,
   animating: one pattern everywhere; tonight's schedule, scrubbed or played
   through, each controller with its own; or a pattern for each zone. */
const WH = { src: 'one', effect: null, picks: {}, tl: null, at: null, playing: false, night: true, token: 0 };
const fmtClock = ms => new Date(ms).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
function whEffect(key, dev) {
  const all = S.settings.effects || {}, e = all[key];
  if (!e) return null;
  if (e.split) { const k = e.split[dev] ?? e.rest; return k && k !== 'off' ? all[k] || null : null; }
  return e;
}
function whSpan(dev) {
  const tl = WH.tl; if (!tl) return null;
  const spans = tl.devices[dev] || tl.devices.all || Object.values(tl.devices)[0] || [];
  return spans.find(x => Date.parse(x.start) <= WH.at && WH.at < Date.parse(x.end)) || null;
}
async function wholePanel(box) {
  if (!box) return;
  const md = mapData(), devs = houseDevs(), effs = Object.entries(S.settings.effects || {}).filter(([, e]) => e.colors || e.split);
  if (!WH.effect || !(S.settings.effects || {})[WH.effect]) WH.effect = (effs[0] || [])[0] || null;
  const els = Elev.list(md).map(e => { const key = Elev.use(md, e);
    return { e, key, dev: e.device || (devs[0] || {}).id || '', bulbs: HouseFX.sideBulbs(md.rooflines[key] || []) }; }).filter(x => x.bulbs.length);
  if (WH.src === 'tonight' && !WH.tl) {
    try { WH.tl = await api('house/tonight'); WH.at = Date.parse(WH.tl.now); }
    catch (e) { WH.src = 'one'; toast(e.message, true); }
  }
  const zones = md.zones;
  const tl = WH.tl, a0 = tl ? Date.parse(tl.start) : 0, a1 = tl ? Date.parse(tl.end) : 0;
  const bars = tl ? Object.entries(tl.devices).map(([dv, spans]) => `<div class="small">${esc(dv === 'all' ? 'Every controller' : devName(dv))}</div><div class="tlbar" aria-hidden="true">${spans.map(x => {
      const e = whEffect(x.effect, dv), c = e && e.colors ? '#' + String(e.colors.find(k => !/^(off|x)$/i.test(k)) || 'FFC062').replace('#', '') : '#FFC062';
      return `<i style="left:${(Date.parse(x.start) - a0) / (a1 - a0) * 100}%;width:${(Date.parse(x.end) - Date.parse(x.start)) / (a1 - a0) * 100}%;background:${esc(c)}" title="${esc(x.label)}"></i>`; }).join('')}</div>`).join('') : '';
  box.innerHTML = `<div class="row"><button class="small ${WH.src === 'one' ? 'current' : 'ghost'}" data-whsrc="one">One pattern</button>
      <button class="small ${WH.src === 'tonight' ? 'current' : 'ghost'}" data-whsrc="tonight">Tonight\u2019s schedule</button>
      <button class="small ${WH.src === 'zones' ? 'current' : 'ghost'}" data-whsrc="zones" ${zones.length ? '' : 'disabled title="Save zones first"'}>A pattern for each zone</button>
      <label class="check small"><input type="checkbox" id="whnight" ${WH.night ? 'checked' : ''}> Night</label></div>
    ${WH.src === 'one' ? `<label class="field">Pattern<select id="wheff">${effs.map(([k, e]) => `<option value="${esc(k)}" ${k === WH.effect ? 'selected' : ''}>${esc(e.label || k)}</option>`).join('')}</select></label>
      <p class="note">A Split by controller pattern shows each controller\u2019s own part on its elevations.</p>`
    : WH.src === 'tonight' && tl ? `<div class="timeline"><input type="range" id="what" min="${a0}" max="${a1}" step="60000" value="${WH.at}" aria-label="Time tonight">
        <b id="whclock">${fmtClock(WH.at)}</b><button class="small ghost" data-whnow>Now</button><button class="small" data-whplay>${WH.playing ? 'Pause' : 'Play'}</button></div>
      <div class="stack" style="gap:4px">${bars}</div><p class="small" id="whwhat"></p>
      <p class="note">From noon to noon, as the schedule plans it (rules and holidays), each controller with its own. Weather, scores, alerts, automations and choices by hand can\u2019t be known ahead.</p>`
    : WH.src === 'zones' ? `<div class="stack">${zones.map((z, i) => `<div class="row"><div class="grow" style="min-width:9em"><b>${esc(z.name)}</b><div class="small muted">Bulbs ${z.start}\u2013${z.end}${z.reverse ? ' \u00b7 runs the other way' : ''}${devs.length > 1 ? ' \u00b7 ' + (z.device ? esc(devName(z.device)) : 'every controller') : ''}</div></div>
        <select data-whpick="${i}" style="flex:1 1 11em;min-width:0;max-width:100%" aria-label="Pattern for ${esc(z.name)}"><option value="">Dark</option>${effs.filter(([, e]) => combinable(e)).map(([k, e]) => `<option value="${esc(k)}" ${WH.picks[i] === k ? 'selected' : ''}>${esc(e.label || k)}</option>`).join('')}</select></div>`).join('')}</div>
      <div class="row"><button class="small" data-whcombine ${Object.values(WH.picks).some(Boolean) ? '' : 'disabled'}>Make it a pattern (Combine patterns by zone)</button></div>
      <p class="note">Here each zone moves its own pattern, to see them together. A controller moves one pattern with one motion, so the saved pattern (Combine patterns by zone) moves as one.</p>` : ''}
    ${els.length ? `<div class="whole">${els.map((x, i) => `<figure><canvas data-wh="${i}" aria-label="${esc(Elev.label(md, x.key))}"></canvas>
      <figcaption>${esc(Elev.label(md, x.key))}${devs.length > 1 ? ' \u00b7 ' + esc(devName(x.dev)) : ''}</figcaption></figure>`).join('')}</div>`
      : '<p class="callout small">No elevation has its bulbs placed yet. On an elevation\u2019s photo, trace the roofline and give each line its bulb numbers (Bulbs).</p>'}
    ${devs.length > 1 && els.some(x => !x.e.device) ? '<p class="note">Elevations without a controller (This elevation\u2019s lights) show the first controller\u2019s.</p>' : ''}`;
  box.onclick = e => {
    const b = e.target.closest('button'); if (!b) return; const d = b.dataset;
    if (d.whsrc) { WH.src = d.whsrc; WH.playing = false; if (d.whsrc === 'tonight') WH.tl = null; return wholePanel(box); }
    if (d.whnow !== undefined && WH.tl) { WH.at = Math.min(Date.parse(WH.tl.end), Math.max(Date.parse(WH.tl.start), Date.now())); return wholePanel(box); }
    if (d.whplay !== undefined) { WH.playing = !WH.playing; b.textContent = WH.playing ? 'Pause' : 'Play'; return; }
    if (d.whcombine !== undefined) {
      S.combinePrefill = { ...WH.picks }; go('create');
      // Review #5: if Create doesn't open, the choices don't linger for the next Combine
      let n = 0; const t = setInterval(() => { const c = $('[data-combinezones]'); if (c || ++n > 40) { clearInterval(t); if (c) c.click(); else S.combinePrefill = null; } }, 100);
    }
  };
  box.onchange = box.oninput = e => {
    const t = e.target;
    if (t.id === 'wheff') WH.effect = t.value;
    else if (t.id === 'whnight') WH.night = t.checked;
    else if (t.dataset.whpick !== undefined) { WH.picks[t.dataset.whpick] = t.value; const c = $('[data-whcombine]', box); if (c) c.disabled = !Object.values(WH.picks).some(Boolean); }
    else if (t.id === 'what') { WH.at = +t.value; WH.playing = false; const p = $('[data-whplay]', box); if (p) p.textContent = 'Play'; }
  };
  wholeDraw(box, els);
}
function wholeDraw(box, els) {
  const token = ++WH.token, view = S.view, t0 = performance.now(), md = mapData(), all = S.settings.effects || {};
  const imgs = els.map(() => null);
  els.forEach((x, i) => { if (S.photos.has(x.key)) loadPhoto(x.key).then(url => { const im = new Image(); im.onload = () => { imgs[i] = im; }; im.src = url; }).catch(() => {}); });
  let last = performance.now();
  const frame = now => {
    if (WH.token !== token || S.view !== view || !box.isConnected) return;
    const t = (now - t0) / 1000;
    if (WH.src === 'tonight' && WH.tl && WH.playing) {
      WH.at += (now - last) * 600;                         // ten minutes a second
      if (WH.at >= Date.parse(WH.tl.end)) { WH.at = Date.parse(WH.tl.end); WH.playing = false; const p = $('[data-whplay]', box); if (p) p.textContent = 'Play'; }
      const r = $('#what', box); if (r) r.value = WH.at;
    }
    last = now;
    if (WH.src === 'tonight' && WH.tl) {
      const c = $('#whclock', box); if (c) c.textContent = fmtClock(WH.at);
      const w = $('#whwhat', box); if (w) w.textContent = Object.keys(WH.tl.devices).map(dv => { const sp = whSpan(dv);
        return `${dv === 'all' ? '' : devName(dv) + ': '}${sp ? `${sp.label} (${sp.rule})` : 'off'}`; }).join(' \u00b7 ');
    }
    const cache = {};
    let moving = WH.playing;
    const cols = (k, def, n) => { if (hvMoving(def)) moving = true; return cache[k] || (cache[k] = def ? HouseFX.colorsAt(def, n, t) : null); };
    els.forEach((x, i) => {
      const cv = $(`[data-wh="${i}"]`, box); if (!cv) return;
      const ctx = cv.getContext('2d'), img = imgs[i], dpr = window.devicePixelRatio || 1, W = Math.round(cv.clientWidth * dpr) || 300;
      const H = img ? Math.round(W * img.naturalHeight / img.naturalWidth) : Math.round(W * .62);
      if (cv.width !== W || cv.height !== H) { cv.width = W; cv.height = H; }
      ctx.clearRect(0, 0, W, H);
      if (img) { ctx.drawImage(img, 0, 0, W, H); if (WH.night) { ctx.fillStyle = 'rgba(5,7,18,.62)'; ctx.fillRect(0, 0, W, H); } }
      const T = addressSpace(x.dev), r = Math.max(1.8, W / 240);
      let whole = null;
      if (WH.src === 'one' || WH.src === 'tonight') {
        const key = WH.src === 'one' ? WH.effect : (whSpan(x.dev) || {}).effect;
        const e = key ? whEffect(key, x.dev) : null;
        whole = cols(`${key}|${x.dev}|${T}`, effectDef(e), T);
      }
      const zs = WH.src === 'zones' ? md.zones.map((z, j) => ({ z, j, k: WH.picks[j] })).filter(o => o.k && all[o.k] && forDev(o.z, x.dev)) : [];
      for (const p of x.bulbs) {
        if (p.b > T) continue;
        let c = null;
        if (whole) { const k = whole[(p.b - 1) % whole.length]; if (k && !k.off) c = k; }
        else for (let q = zs.length - 1; q >= 0 && !c; q--) {
          const { z, j, k } = zs[q]; if (p.b < z.start || p.b > z.end) continue;
          const n = z.end - z.start + 1, cc = cols(`z${j}|${k}`, effectDef(all[k]), n), v = cc && cc[z.reverse ? z.end - p.b : p.b - z.start];
          if (v && !v.off) c = v;
        }
        const px = p.x / 100 * W, py = p.y / 100 * H;
        if (!c) { ctx.strokeStyle = 'rgba(170,175,205,.3)'; ctx.lineWidth = dpr; ctx.beginPath(); ctx.arc(px, py, r, 0, 7); ctx.stroke(); continue; }
        const [R0, G0, B0] = c.c, a = c.a;
        ctx.fillStyle = `rgba(${R0 | 0},${G0 | 0},${B0 | 0},${a * .28})`; ctx.beginPath(); ctx.arc(px, py, r * 3, 0, 7); ctx.fill();
        ctx.fillStyle = `rgba(${R0 | 0},${G0 | 0},${B0 | 0},${Math.max(a, .08)})`; ctx.beginPath(); ctx.arc(px, py, r, 0, 7); ctx.fill();
      }
    });
    // Still patterns are drawn twice a second (a resized window, a scrubbed time), sparing a phone's battery
    if (moving) requestAnimationFrame(frame); else setTimeout(() => requestAnimationFrame(frame), 250);
  };
  requestAnimationFrame(frame);
}

/* ---------------------------------------------------------------- HOUSE MAP: camera calibration (4.16)
   The phone watches the house while the controller shows a few coded
   frames (calib.js); every bulb it sees is placed and pinned, as a new
   version of this elevation with the camera's own photo. */
const CAL = { wait: 'auto' };
async function calibDialog(F, render) {
  const md = mapData(), el = Elev.of(md, F.side) || md.sides[0];
  const devs = houseDevs(), dev = houseDev() || (el.device && devs.some(x => x.id === el.device) ? el.device : '') || (devs.length === 1 ? devs[0].id : '');
  const can = !!(window.isSecureContext && navigator.mediaDevices && navigator.mediaDevices.getUserMedia);
  const many = devs.length > 1;
  const T = addressSpace(dev), perSlot = (S.status && S.status.slot_limit) || PER_SLOT, frames = Calib.frames(T, perSlot);
  const f = dialog(`<h2>Calibrate the ${esc(el.name.toLowerCase())} with the camera</h2>
    ${!can ? `<p class="callout warn small">The camera works only on a secure page: open EaveLuxOS at its <b>https://</b> address on this phone (Manual, section 8: HTTPS with mkcert), or on the app computer itself (http://localhost) with a webcam.</p>`
      : many && !dev ? '<p class="callout warn small">Choose a <b>Controller</b> at the top of the House tab first: each controller numbers its own bulbs.</p>' : ''}
    <ol class="small" style="margin:0 0 8px;padding-left:1.2em"><li>At night, stand where you can see the whole ${esc(el.name.toLowerCase())}, and prop the phone up (a tripod, a car roof, a fence post): it must not move for about a minute.</li>
      <li>Tap <b>Start</b>. ${many ? `<b>${esc(devName(dev))}</b> shows` : 'The lights show'} ${frames.length} black-and-white frames (${T} bulbs), a second or two each; the camera reads every bulb\u2019s number from them.</li>
      <li>Check the result, then <b>Save</b>: it becomes a new version of this elevation, with this photo and every bulb found pinned.</li></ol>
    <div class="calview"><video data-cv playsinline muted autoplay></video><canvas data-cc hidden></canvas></div>
    <div class="row small"><label class="row small">Wait for each frame <select data-cw style="width:auto">${[['auto', 'until the lights change'], ['2', '2 seconds'], ['4', '4 seconds']].map(([v, l]) => `<option value="${v}" ${CAL.wait === v ? 'selected' : ''}>${l}</option>`).join('')}</select></label></div>
    <p class="small" data-cs role="status">${can && (dev || !many) ? 'Point the camera at the house.' : ''}</p>
    <div class="row"><button type="button" class="primary" data-cstart ${can && (dev || !many) ? '' : 'disabled'}>Start</button>
      <button type="button" class="primary" data-csave hidden>Save as a new version</button><button type="button" class="ghost" data-cagain hidden>Try again</button></div>
    <label class="check small" data-cuse hidden><input type="checkbox" data-cusebox checked> Show it in the whole house (\u2605)</label>`, null);
  const dlg = $('#dlg'), video = $('[data-cv]', f), status = $('[data-cs]', f), canvas = $('[data-cc]', f);
  let stream = null, lock = null, running = false, result = null, stop = false;
  const say = t => { status.textContent = t; };
  const cleanup = () => { stop = true; if (stream) stream.getTracks().forEach(t => t.stop()); if (lock) lock.release().catch(() => {}); };
  dlg.addEventListener('close', () => { cleanup(); if (running || result) calibRestore(dev); }, { once: true });
  if (can && (dev || !many)) {
    try {
      stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' }, width: { ideal: 1920 }, height: { ideal: 1080 } }, audio: false });
      video.srcObject = stream; await video.play().catch(() => {});
    } catch (e) { say(e.name === 'NotAllowedError' ? 'The camera wasn\u2019t allowed. Allow it for this page in the browser, then try again.' : `The camera couldn\u2019t start: ${e.message}`); $('[data-cstart]', f).disabled = true; }
  }
  f.addEventListener('change', e => { if (e.target.dataset.cw !== undefined) CAL.wait = e.target.value; });
  f.addEventListener('click', async e => {
    const b = e.target.closest('button'); if (!b) return;
    if (b.dataset.cstart !== undefined || b.dataset.cagain !== undefined) {
      if (running) return;
      running = true; result = null;
      ['cstart', 'csave', 'cagain'].forEach(k => { $(`[data-${k}]`, f).hidden = k !== 'cstart'; });
      $('[data-cstart]', f).disabled = true; $('[data-cuse]', f).hidden = true;
      video.hidden = false; canvas.hidden = true;
      try { lock = navigator.wakeLock ? await navigator.wakeLock.request('screen') : null; } catch { lock = null; }
      try {
        result = await calibCapture(video, frames, dev, T, say, () => stop);
        if (stop) return;
        calibShow(canvas, video, result);
        const found = new Set(result.bulbs.map(x => x.bulb)).size;
        say(found ? `Found ${found} of ${T} bulbs${result.sections.sections.length ? `, in ${result.sections.sections.length} line${result.sections.sections.length === 1 ? '' : 's'}` : ''}${result.sections.cut ? ` (${result.sections.cut} more line${result.sections.cut === 1 ? '' : 's'} didn\u2019t fit: an elevation holds 40)` : ''}. ${found < T * 0.5 ? (result.repeats ? 'Many weren\u2019t seen: check the whole elevation is in view and the phone didn\u2019t move, or wait longer for each frame.' : 'The controller may not repeat a short pattern along its lights; this way of finding bulbs needs that.') : 'Bulbs not seen are spread out between the ones found.'}`
          : 'No bulbs were found. Check the lights are in view and it\u2019s dark, and that the phone stays still; or wait longer for each frame.');
        $('[data-csave]', f).hidden = !result.sections.sections.length; $('[data-cagain]', f).hidden = false; $('[data-cuse]', f).hidden = !result.sections.sections.length;
      } catch (err) { say(err.message); $('[data-cagain]', f).hidden = false; }
      finally { running = false; $('[data-cstart]', f).hidden = true; calibRestore(dev); }
    }
    if (b.dataset.csave !== undefined && result) {
      busy(b, async () => {
        const md2 = mapData(), el2 = Elev.of(md2, F.side) || el;
        const key = Elev.newId(md2, `${el2.id}-calibrated`);
        const blob = await new Promise(r => result.photo.toBlob(r, 'image/jpeg', 0.9));
        await uploadPhoto(key, new File([blob], key + '.jpg', { type: 'image/jpeg' }));
        S.photos.add(key); S.photoV = Date.now();
        const vn = (() => { const names = Elev.versions(md2, el2.id).map(v => Elev.vname(md2, v.id).toLowerCase()); for (let i = 1; ; i++) { const n = i === 1 ? 'Calibrated' : `Calibrated ${i}`; if (!names.includes(n.toLowerCase())) return n; } })();
        const use = $('[data-cusebox]', f).checked;
        await saveMap(mp => {
          mp.sides.push({ id: key, name: vn, of: el2.id });
          mp.rooflines[key] = result.sections.sections;
          const e2 = mp.sides.find(x => x.id === el2.id);
          if (use) e2.use = key;
          if (dev && many && e2.device !== dev) e2.device = dev;            // these are that controller's bulb numbers
        }, `Saved \u201c${vn}\u201d`);
        F.side = key; S.lastVer = { ...(S.lastVer || {}), [el2.id]: key };
        result = null; dlg.close(); render();
      }).catch(() => {});
    }
  });
}
/* Show each frame, wait for the lights to change, and capture it (three
   pictures averaged). Returns the decoded bulbs, the lines, and the photo. */
async function calibCapture(video, frames, dev, T, say, stopped) {
  if (!video.videoWidth) await new Promise(r => { video.onloadedmetadata = r; setTimeout(r, 4000); });
  const vw = video.videoWidth, vh = video.videoHeight;
  if (!vw) throw new Error('The camera isn\u2019t sending a picture.');
  const k = Math.min(1, 960 / vw), w = Math.round(vw * k), h = Math.round(vh * k);
  const c = document.createElement('canvas'); c.width = w; c.height = h;
  const ctx = c.getContext('2d', { willReadFrequently: true });
  const grab = () => { ctx.drawImage(video, 0, 0, w, h); return Calib.gray(ctx.getImageData(0, 0, w, h).data); };
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const avg = async () => { const a = grab(); await sleep(70); const b = grab(); await sleep(70); const d = grab();
    const o = new Uint8Array(a.length); for (let i = 0; i < a.length; i++) o[i] = (a[i] + b[i] + d[i]) / 3; return o; };
  const changed = (a, b) => { let n = 0; for (let i = 0; i < a.length; i++) if (Math.abs(a[i] - b[i]) > 24) n++; return n; };
  const shots = { bits: [] };
  let photo = null, prev = grab();
  for (let i = 0; i < frames.length; i++) {
    if (stopped()) throw new Error('Stopped.');
    const fr = frames[i];
    say(`Frame ${i + 1} of ${frames.length}\u2026 keep the phone still.`);
    await api('action', { body: { action: 'try', effect: fr.effect, minutes: 10, ...(dev ? { device: dev } : {}) } });
    if (CAL.wait !== 'auto') await sleep(+CAL.wait * 1000);
    else {
      // Until the picture has changed and then held still (the lights took the frame), at most 6 s
      const end = performance.now() + 6000, small = Math.max(4, w * h * 0.0002);
      await sleep(i ? 400 : 1500);
      let last = grab(), moved = !i || changed(prev, last) > small, calm = 0;
      while (performance.now() < end && calm < 2) {
        await sleep(180);
        const g = grab(), d = changed(last, g);
        if (changed(prev, g) > small) moved = true;
        calm = moved && d <= small ? calm + 1 : 0;
        last = g;
      }
    }
    const shot = await avg();
    prev = shot;
    if (fr.kind === 'dark') shots.dark = shot;
    else if (fr.kind === 'full') {
      shots.full = shot;
      const pc = document.createElement('canvas'); pc.width = vw; pc.height = vh;   // the photo, in color at the camera's size
      pc.getContext('2d').drawImage(video, 0, 0, vw, vh); photo = pc;
    } else (shots.bits[fr.bit] = shots.bits[fr.bit] || [])[fr.kind === 'bit' ? 0 : 1] = shot;
  }
  say('Reading the bulbs\u2026');
  await sleep(20);
  const r = Calib.decode(shots, w, h, T);
  return { ...r, sections: Calib.toSections(r.bulbs, h / w), photo, w, h };
}
/* The photo with every bulb found: a dot and, every few, its number. */
function calibShow(canvas, video, r) {
  canvas.width = r.photo.width; canvas.height = r.photo.height;
  const ctx = canvas.getContext('2d'), W = canvas.width, H = canvas.height;
  ctx.drawImage(r.photo, 0, 0); ctx.fillStyle = 'rgba(5,7,18,.45)'; ctx.fillRect(0, 0, W, H);
  ctx.font = `${Math.round(W / 70)}px system-ui, sans-serif`;
  for (const s of r.sections.sections) {
    ctx.strokeStyle = '#62D682'; ctx.lineWidth = Math.max(1, W / 600); ctx.beginPath();
    s.points.forEach(([x, y], i) => (i ? ctx.lineTo : ctx.moveTo).call(ctx, x / 100 * W, y / 100 * H)); ctx.stroke();
  }
  r.bulbs.forEach((b, i) => {
    const x = b.x / 100 * W, y = b.y / 100 * H;
    ctx.fillStyle = '#FFC062'; ctx.beginPath(); ctx.arc(x, y, Math.max(2, W / 300), 0, 7); ctx.fill();
    if (b.bulb % 10 === 0 || b.bulb === 1) { ctx.fillStyle = '#FFE2B0'; ctx.fillText(String(b.bulb), x + 4, y - 4); }
  });
  video.hidden = true; canvas.hidden = false;
}
function calibRestore(dev) {
  // Review #1 (4.16): back to what showed before (a choice made by hand stays), not simply the schedule
  api('action', { body: { action: 'end_preview', ...(dev ? { device: dev } : {}) } }).catch(() => {});
}

/* ---------------------------------------------------------------- HOUSE MAP: elevations (4.12)
   Add, rename and delete elevations and their versions; export one as a
   file (its photos, rooflines, bulbs and pins) and import it again. */
const ELEV_FILE = 'eaveluxos-elevation';
function elevAction(d, b, md, el, F, render) {
  const kindSel = cur => `<label class="field">Kind<select name="kind">${Elev.KINDS.map(([k, l]) => `<option value="${k}" ${k === (cur || 'other') ? 'selected' : ''}>${esc(l)}</option>`).join('')}</select></label>`;
  if (d.addside !== undefined) return dialog(`<h2>Add an elevation</h2><label class="field">Name<input type="text" name="nm" maxlength="30" required placeholder="e.g. Garage side elevation"></label>
      ${kindSel('side')}<p class="note">A house can have several side elevations (an L-shaped house, a garage, a deck).</p>`, async f => {
    const nm = f.nm.value.trim(); if (!nm) throw new Error('Give it a name.');
    if (Elev.list(md).some(x => x.name.toLowerCase() === nm.toLowerCase())) throw new Error(`There's already an elevation named \u201c${nm}\u201d.`);
    const id = Elev.newId(md, nm);
    await saveMap(mp => { mp.sides.push({ id, name: nm, kind: f.kind.value }); }, 'Elevation added'); F.side = id; render(); }, { ok: 'Add', onOpen: f => f.nm.focus() });
  if (d.renelev !== undefined) {
    const v = md.sides.find(x => x.id === F.side);
    return dialog(`<h2>Rename</h2><label class="field">Elevation<input type="text" name="nm" maxlength="30" required value="${esc(el.name)}"></label>${kindSel(el.kind)}
      <label class="field">This version<input type="text" name="vn" maxlength="30" required value="${esc(Elev.vname(md, F.side))}" placeholder="e.g. Day, Night, Before"></label>`, async f => {
      const nm = f.nm.value.trim(), vn = f.vn.value.trim(); if (!nm || !vn) throw new Error('Give both a name.');
      if (Elev.list(md).some(x => x.id !== el.id && x.name.toLowerCase() === nm.toLowerCase())) throw new Error(`There's already an elevation named \u201c${nm}\u201d.`);
      await saveMap(mp => { const e = mp.sides.find(x => x.id === el.id); e.name = nm; e.kind = f.kind.value;
        if (v.of) mp.sides.find(x => x.id === v.id).name = vn; else e.vname = vn; }, 'Renamed'); render(); }, { ok: 'Save' });
  }
  if (d.addver !== undefined) return dialog(`<h2>Add a version of the ${esc(el.name.toLowerCase())}</h2>
      <label class="field">Name<input type="text" name="nm" maxlength="30" required placeholder="e.g. Night, Before, After"></label>
      <label class="check"><input type="checkbox" name="copy" checked> Start from this version\u2019s rooflines, bulbs and pins (for a photo taken from the same spot)</label>
      <p class="note">Each version has its own photo, rooflines and pins. The \u2605 one is shown in the whole house and the flat diagram.</p>`, async f => {
    const nm = f.nm.value.trim(); if (!nm) throw new Error('Give it a name.');
    if (Elev.versions(md, el.id).some(x => Elev.vname(md, x.id).toLowerCase() === nm.toLowerCase())) throw new Error(`There's already a version named \u201c${nm}\u201d.`);
    const id = Elev.newId(md, `${el.id}-${nm}`), copy = f.copy.checked, from = F.side;
    await saveMap(mp => {
      mp.sides.push({ id, name: nm, of: el.id });
      if (copy && mp.rooflines[from]) mp.rooflines[id] = clone(mp.rooflines[from]);
      if (copy) mp.landmarks.push(...mp.landmarks.filter(l => l.side === from && l.x != null).map(l => ({ ...l, side: id })));
    }, 'Version added');
    F.side = id; S.lastVer = { ...(S.lastVer || {}), [el.id]: id }; render(); }, { ok: 'Add', onOpen: f => f.nm.focus() });
  if (d.usever !== undefined) return busy(b, () => saveMap(mp => { mp.sides.find(x => x.id === el.id).use = F.side; },
    `The whole house shows \u201c${Elev.vname(md, F.side)}\u201d`)).then(render).catch(() => {});
  if (d.delver !== undefined || d.delelev !== undefined) {
    const keys = d.delelev !== undefined ? Elev.versions(md, el.id).map(x => x.id) : [F.side];
    const what = d.delelev !== undefined ? `the ${el.name}` : `the \u201c${Elev.vname(md, F.side)}\u201d version`;
    return confirmBox(`Delete ${what}?`, 'Its photo, rooflines and pins go. Landmarks stay, without their pins.', 'Delete', true).then(ok => {
      if (!ok) return;
      return busy(b, async () => {
        // Review #1 (4.12): every one, even a photo this page didn't know of (one from the phone since)
        for (const k of keys) { await api('photo/delete', { body: { side: k } }); S.photos.delete(k); }
        await saveMap(mp => {
          mp.sides = mp.sides.filter(x => !keys.includes(x.id));
          const e = mp.sides.find(x => x.id === el.id); if (e && keys.includes(e.use)) delete e.use;
          for (const k of keys) delete mp.rooflines[k];
          mp.landmarks = mp.landmarks.map(l => keys.includes(l.side) ? (({ side, x, y, ...rest }) => rest)(l) : l);
        }, 'Deleted');
        F.side = d.delelev !== undefined ? 'front' : el.id; render();
      }).catch(() => {});
    });
  }
  if (d.exportelev !== undefined) return busy(b, async () => {
    const vs = Elev.versions(md, el.id), use = Elev.use(md, el);
    const toData = blob => new Promise((ok, no) => { const r = new FileReader(); r.onload = () => ok(r.result); r.onerror = no; r.readAsDataURL(blob); });
    const versions = [];
    for (const v of vs) {
      let photo = null;
      if (S.photos.has(v.id)) {       // from the app itself: the page may not fetch its own blob: links (CSP)
        const r = await fetch('api/photo/' + encodeURIComponent(v.id), { headers: authHeaders(), cache: 'no-store' });
        if (!r.ok) throw new Error(`The ${Elev.label(md, v.id)} photo couldn\u2019t be read.`);
        photo = await toData(await r.blob());
      }
      versions.push({ name: Elev.vname(md, v.id), photo, rooflines: md.rooflines[v.id] || [],
        pins: md.landmarks.filter(l => l.side === v.id && l.x != null).map(({ name, bulb, x, y, device }) => ({ name, bulb, x, y, ...(device ? { device } : {}) })) });
    }
    const file = { format: ELEV_FILE, version: 1, name: el.name, kind: el.kind || 'other', ...(el.device ? { device: el.device } : {}),
      use: vs.findIndex(v => v.id === use), versions };
    const url = URL.createObjectURL(new Blob([JSON.stringify(file)], { type: 'application/json' }));
    const a = document.createElement('a'); a.href = url; a.download = `${Elev.slug(el.name)}.elevation.json`; a.click();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
  }).then(() => toast('Exported')).catch(() => {});
}
/* Check an exported elevation file and turn it into what saveMap needs. Pure,
   so the tests can use it: md is the house as it is; returns {sides,
   rooflines, landmarks, photos: [[key, dataURL]]}. */
function elevParse(raw, md, knownDevs) {
  let f; try { f = typeof raw === 'string' ? JSON.parse(raw) : raw; } catch { throw new Error('That isn\u2019t an elevation file.'); }
  if (!f || f.format !== ELEV_FILE || f.version !== 1 || !Array.isArray(f.versions) || !f.versions.length || f.versions.length > 12)
    throw new Error('That isn\u2019t an EaveLuxOS elevation file (made with Export this elevation).');
  if (md.sides.length + f.versions.length > 80) throw new Error('The house has too many elevations and versions to add this one.');
  let name = String(f.name || 'Imported elevation').trim().slice(0, 30) || 'Imported elevation';
  const names = new Set(Elev.list(md).map(x => x.name.toLowerCase()));
  for (let i = 2; names.has(name.toLowerCase()); i++) name = `${String(f.name).slice(0, 24)} (${i})`;
  const kind = Elev.KINDS.some(([k]) => k === f.kind) ? f.kind : 'other';
  const work = { sides: [...md.sides], rooflines: { ...md.rooflines } }, sides = [], rooflines = {}, landmarks = [], photos = [];
  const okDev = x => typeof x === 'string' && knownDevs.includes(x);
  f.versions.forEach((v, i) => {
    const vn = String(v.name || `Version ${i + 1}`).trim().slice(0, 30) || `Version ${i + 1}`;
    const id = Elev.newId(work, i ? `${sides[0].id}-${vn}` : name);
    const side = i ? { id, name: vn, of: sides[0].id } : { id, name, kind, vname: vn, ...(okDev(f.device) ? { device: f.device } : {}) };
    work.sides.push(side); sides.push(side);
    const lines = (Array.isArray(v.rooflines) ? v.rooflines : []).slice(0, RL.LIMITS.sections).filter(l => RL.validSection(l))
      .map(l => ({ id: l.id, kind: l.kind, points: l.points, ...(Array.isArray(l.wire) ? { wire: l.wire.filter(Number.isInteger) } : {}),
        ...(l.bulbs && Number.isInteger(l.bulbs.from) && Number.isInteger(l.bulbs.to) ? { bulbs: { from: l.bulbs.from, to: l.bulbs.to } } : {}),
        ...(Array.isArray(l.pins) ? { pins: l.pins.filter(p => Array.isArray(p) && p.length === 3 && Number.isInteger(p[0]) && p[0] >= 1 && p.slice(1).every(n => Number.isFinite(n) && n >= 0 && n <= 100)).slice(0, HouseFX.MAX_PINS) } : {}) }));
    if (lines.length) { rooflines[id] = lines; work.rooflines[id] = lines; }
    for (const p of Array.isArray(v.pins) ? v.pins.slice(0, 200) : []) {
      if (!p || !Number.isInteger(p.bulb) || p.bulb < 1 || p.bulb > 10000 || !(p.x >= 0 && p.x <= 1 && p.y >= 0 && p.y <= 1)) continue;
      const nm = String(p.name || '').trim().slice(0, 60); if (!nm) continue;
      landmarks.push({ name: nm, bulb: p.bulb, side: id, x: p.x, y: p.y, ...(okDev(p.device) ? { device: p.device } : {}) });
    }
    if (typeof v.photo === 'string' && /^data:image\/(jpeg|png|webp);base64,/.test(v.photo)) photos.push([id, v.photo]);
  });
  if (Number.isInteger(f.use) && f.use > 0 && f.use < sides.length) sides[0].use = sides[f.use].id;
  return { sides, rooflines, landmarks, photos };
}
async function elevImport(file, F, render) {
  try {
    await busy(null, async () => {
      if (file.size > 60_000_000) throw new Error('That file is too big to be an elevation.');
      const md = mapData(), got = elevParse(await file.text(), md, (S.devices || []).map(x => x.id));
      for (const [key, url] of got.photos) {
        const [head, b64] = url.split(','), bin = atob(b64), bytes = new Uint8Array(bin.length);   // no fetch of data: links (CSP)
        for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
        const blob = new Blob([bytes], { type: head.slice(5, head.indexOf(';')) });
        await uploadPhoto(key, new File([blob], key + '.jpg', { type: blob.type }));
        S.photos.add(key);
      }
      await saveMap(mp => { mp.sides.push(...got.sides); Object.assign(mp.rooflines, got.rooflines); mp.landmarks.push(...got.landmarks); },
        `Imported \u201c${got.sides[0].name}\u201d`);
      S.photoV = Date.now(); F.side = got.sides[0].use || got.sides[0].id; roofReset(); render();
    });
  } catch { /* busy() has shown the error */ }
}

/* ---------------------------------------------------------------- HOUSE MAP: house view (3.17)
   The photo with each bulb where it sits (from the bulb numbers given to the
   traced lines): preview a pattern animating on the house, or build an
   architectural scene by tapping bulbs. */
const HV = { mode: 'preview', effect: null, night: true, groups: [{ color: '#FFC58A', level: 100, bulbs: [] }], cur: 0, width: 3,
  name: '', key: null, lm: '' };
function effectDef(e) {
  if (!e || !e.colors) return null;
  return { segs: e.colors.map((c, i) => ({ c: String(c).toLowerCase() === 'off' || String(c).toLowerCase() === 'x' ? 'off' : '#' + String(c).replace('#', '').toUpperCase(),
    n: (e.counts || [])[i] || 3 })), mode: e.custom_mode || 0, speed: e.speed ?? 100, brightness: e.brightness ?? 200 };
}
function sceneSegs(T) { return Painter.compress(HouseFX.sceneCanvas(T, HV.groups)); }
/* Slots the scene needs on this controller: 60-bulb controllers split long
   dark gaps into more slots than the 90-bulb count suggests (3.17.1). */
function sceneSlots(T) { return Painter.slotsAt(HouseFX.sceneCanvas(T, HV.groups), (S.status && S.status.slot_limit) || Painter.PER_SLOT); }
async function houseView(box, side) {
  if (!box) return;
  const md = mapData(), T = houseSpace(), lines = md.rooflines[side] || [];
  const bulbs = HouseFX.sideBulbs(lines), sideName = Elev.label(md, side);
  const effs = Object.entries(S.settings.effects || {}).filter(([, e]) => e.colors);
  const designed = S.housePreview;
  if (!HV.effect) HV.effect = designed ? '_design' : (effs[0] || [])[0] || null;
  const ro = role() === 'viewer';
  const g = HV.groups[HV.cur] || HV.groups[0];
  const slots = sceneSlots(T);
  const owned = HouseFX.sceneOwners(T, HV.groups), sceneCount = owned.reduce((n, x) => n + x, 0);
  const past = bulbs.filter(p => p.b > T).length;
  box.innerHTML = `<div class="panel-head"><h2>House view</h2>
      <div class="row"><button class="small ${HV.mode === 'preview' ? 'current' : 'ghost'}" data-hvmode="preview">Preview a pattern</button>
      <button class="small ${HV.mode === 'scene' ? 'current' : 'ghost'}" data-hvmode="scene" ${ro ? 'disabled' : ''}>Build a scene</button>
      <button class="small ${HV.mode === 'bulbs' ? 'current' : 'ghost'}" data-hvmode="bulbs" ${ro ? 'disabled' : ''}>Place bulbs</button></div></div>
    ${!S.photos.has(side) ? `<p class="muted small">Upload a photo of the ${esc(sideName.toLowerCase())} first.</p>`
      : !bulbs.length ? `<p class="callout small">Give this side's traced lines their bulb numbers first: under the photo, tap <b>Bulbs</b> next to each roof edge and enter the first and last bulb on it. ${lines.length ? '' : 'Trace the roofline first (Auto-detect or Trace by hand).'}</p>` : ''}
    ${past ? `<p class="callout warn small">${past} bulb${past === 1 ? '' : 's'} on this side ${past === 1 ? 'is' : 'are'} numbered past bulb ${T}, the last one your lights have now. Check the <b>Bulbs</b> numbers under the photo; ${past === 1 ? 'it isn’t' : 'they aren’t'} shown.</p>` : ''}
    ${HV.mode === 'scene' && HV.key && HouseFX.sceneTotal((S.settings.effects || {})[HV.key]) && HouseFX.sceneTotal(S.settings.effects[HV.key]) !== T ? `<p class="callout warn small">This scene was made for ${HouseFX.sceneTotal(S.settings.effects[HV.key])} bulbs; your lights now have ${T}. Save it again to fit.</p>` : ''}
    <div class="hview" ${bulbs.length && S.photos.has(side) ? '' : 'hidden'}><canvas id="hvcv" aria-label="The ${esc(sideName.toLowerCase())} with its bulbs"></canvas></div>
    ${HV.mode === 'bulbs' ? hvBulbsHtml(md, side, bulbs) : HV.mode === 'preview' ? `<div class="row">
        <label class="field grow">Pattern<select id="hveff">${designed ? `<option value="_design" ${HV.effect === '_design' ? 'selected' : ''}>From Create: ${esc(designed.label || 'your design')}</option>` : ''}
          ${effs.map(([k, e]) => `<option value="${esc(k)}" ${HV.effect === k ? 'selected' : ''}>${esc(e.label || k)}</option>`).join('')}</select></label>
        <label class="check small"><input type="checkbox" id="hvnight" ${HV.night ? 'checked' : ''}> Night</label></div>
      <p class="note">An approximation of how the controller animates the pattern, on your photo. Only patterns made of colors can be previewed (not built-in effects or patterns saved only in the Trimlight app).</p>`
    : `<div class="chips">${HV.groups.map((x, i) => `<button class="small ${i === HV.cur ? 'current' : 'ghost'}" data-hvg="${i}"><i class="dot" style="background:${esc(HouseFX.dim(x.color, x.level))}"></i> Group ${i + 1} (${owned[i]})</button>`).join('')}
        <button class="small ghost" data-hvadd ${HV.groups.length >= 14 ? 'disabled' : ''}>Add a group</button></div>
      <div class="row"><label class="row small">Color <label class="custom-swatch" style="background:${esc(g.color)}"><input type="color" id="hvcol" value="${esc(g.color.toLowerCase())}" aria-label="Group color"></label></label>
        ${['#FFC58A', '#FFE2B8', '#FFFFFF', '#FF0000', '#00FF00', '#0040FF'].map(c => `<button class="swatch" style="background:${c}" data-hvc="${c}" aria-label="${c}"></button>`).join('')}
        <label class="row small">Brightness <select id="hvlvl" style="width:auto">${[100, 75, 50, 35, 20, 10].map(n => `<option value="${n}" ${g.level === n ? 'selected' : ''}>${n}%</option>`).join('')}</select></label>
        <label class="row small">Tap lights <select id="hvw" style="width:auto">${[1, 3, 5, 7, 9].map(n => `<option value="${n}" ${HV.width === n ? 'selected' : ''}>${n} bulb${n > 1 ? 's' : ''}</option>`).join('')}</select></label></div>
      <div class="row"><input type="text" id="hvnums" placeholder="Bulb numbers, e.g. 10-12, 40" class="grow" style="flex:1" aria-label="Bulb numbers to light">
        <button class="small ghost" data-hvnums>Light these</button></div>
      <div class="row"><input type="text" id="hvlm" placeholder="Landmarks named… (e.g. window)" value="${esc(HV.lm)}" class="grow" style="flex:1">
        <button class="small ghost" data-hvlm>Light them all</button><button class="small ghost" data-hvclr>Clear group</button>${HV.groups.length > 1 ? '<button class="small ghost danger" data-hvdel>Delete group</button>' : ''}</div>
      <p class="small ${slots > Painter.MAX_SLOTS ? 'warn' : 'muted'}">${sceneCount} bulb${sceneCount === 1 ? '' : 's'} lit · uses ${slots} of ${Painter.MAX_SLOTS} color slots${slots > Painter.MAX_SLOTS ? ': too many. Merge groups or light fewer separate spots.' : ''}. Every other bulb stays dark.</p>
      <div class="row"><input type="text" id="hvname" maxlength="40" placeholder="Scene name, e.g. Window accents" value="${esc(HV.name)}" class="grow" style="flex:1">
        <button class="small" data-hvtry ${sceneCount && slots <= Painter.MAX_SLOTS ? '' : 'disabled'}>Show on lights</button>
        <button class="small primary" data-hvsave ${sceneCount && slots <= Painter.MAX_SLOTS ? '' : 'disabled'}>Save as a pattern</button>
        ${HV.key ? '<button class="small ghost" data-hvnew>New scene</button>' : ''}</div>
      <p class="note">Tap a bulb on the photo to light it (with the bulbs around it, as set by <b>Tap lights</b>); tap again to turn it back off. A scene is an ordinary pattern: schedule it like any other.</p>
      ${Object.entries(S.settings.effects || {}).filter(([, e]) => e.scene).length ? `<p class="small">Edit a saved scene: ${Object.entries(S.settings.effects).filter(([, e]) => e.scene).map(([k, e]) => `<a href="#" data-hvedit="${esc(k)}">${esc(e.label || k)}</a>`).join(', ')}</p>` : ''}`}`;
  const B = { list: bulbs };
  hvDraw(box, side, B, T);
  if (HV.mode === 'bulbs') hvBulbsWire(box, side, B, T);
  box.onclick = e => hvClick(e, box, side, bulbs, T);
  box.onchange = e => {
    const t = e.target;
    if (t.id === 'hveff') HV.effect = t.value;
    else if (t.id === 'hvnight') HV.night = t.checked;
    else if (t.id === 'hvcol') g.color = t.value.toUpperCase();
    else if (t.id === 'hvlvl') g.level = +t.value;
    else if (t.id === 'hvw') HV.width = +t.value;
    else if (t.id === 'hvlm') { HV.lm = t.value; return; }
    else if (t.id === 'hvname') { HV.name = t.value; return; }
    else return;
    houseView(box, side);
  };
}
function hvDraw(box, side, B, T) {
  const cv = $('#hvcv', box); if (!cv || !B.list.length) return;
  const ctx = cv.getContext('2d'), view = S.view, token = (HV.token = (HV.token || 0) + 1), t0 = performance.now();
  let img = null;
  loadPhoto(side).then(url => { const im = new Image(); im.onload = () => { img = im; }; im.src = url; }).catch(() => {});
  const canvasScene = HV.mode === 'scene' ? HouseFX.sceneCanvas(T, HV.groups) : null;
  const def = HV.mode === 'preview' ? (HV.effect === '_design' ? S.housePreview && S.housePreview.def : effectDef((S.settings.effects || {})[HV.effect])) : null;
  const rgb = h => { const n = parseInt(h.slice(1), 16); return [n >> 16, n >> 8 & 255, n & 255]; };
  const frame = now => {
    if (S.view !== view || !cv.isConnected || HV.token !== token) return;
    const dpr = window.devicePixelRatio || 1, W = Math.round(cv.clientWidth * dpr);
    const H = img ? Math.round(W * img.naturalHeight / img.naturalWidth) : Math.round(W * .66);
    if (cv.width !== W || cv.height !== H) { cv.width = W; cv.height = H; }
    ctx.clearRect(0, 0, W, H);
    if (img) { ctx.drawImage(img, 0, 0, W, H); if (HV.mode === 'scene' || HV.night) { ctx.fillStyle = 'rgba(5,7,18,.62)'; ctx.fillRect(0, 0, W, H); } }
    if (HV.mode === 'bulbs') { hvBulbsFrame(ctx, B.list, W, H, dpr, T); return setTimeout(() => requestAnimationFrame(frame), 120); }
    const cols = def ? HouseFX.colorsAt(def, T, (now - t0) / 1000) : null;
    const r = Math.max(2, W / 260);
    for (const p of B.list) {
      if (p.b > T) continue;                // numbered past the last bulb: not on the lights (3.17.1)
      const x = p.x / 100 * W, y = p.y / 100 * H;
      let c = null, a = 1;
      if (cols) { const k = cols[(p.b - 1) % cols.length]; if (k && !k.off) { c = k.c; a = k.a; } }
      else if (canvasScene) { const v = canvasScene[p.b - 1]; if (v && v !== 'off') c = rgb(v); }
      if (!c) { ctx.strokeStyle = 'rgba(170,175,205,.35)'; ctx.lineWidth = dpr; ctx.beginPath(); ctx.arc(x, y, r, 0, 7); ctx.stroke(); continue; }
      ctx.fillStyle = `rgba(${c[0]|0},${c[1]|0},${c[2]|0},${a * .28})`; ctx.beginPath(); ctx.arc(x, y, r * 3, 0, 7); ctx.fill();
      ctx.fillStyle = `rgba(${c[0]|0},${c[1]|0},${c[2]|0},${Math.max(a, .08)})`; ctx.beginPath(); ctx.arc(x, y, r, 0, 7); ctx.fill();
    }
    // Only a moving pattern needs 60 frames a second; a still scene or still
    // pattern is redrawn twice a second (for a resized window), which spares
    // a phone's battery while the House map is open (3.17.1).
    if (hvMoving(def)) requestAnimationFrame(frame); else setTimeout(() => requestAnimationFrame(frame), 500);
  };
  requestAnimationFrame(frame);
}
const hvMoving = def => !!(def && def.mode);       // custom motion 0 is static
function hvSceneEffect(T, label) {
  const segs = sceneSegs(T), need = sceneSlots(T);
  if (need > Painter.MAX_SLOTS) throw new Error(`That scene needs ${need} color slots; the controller allows ${Painter.MAX_SLOTS}.`);
  return { label, colors: segs.map(x => x.c), counts: segs.map(x => x.n), custom_mode: 0, speed: 0, brightness: 255,
    scene: { groups: HV.groups.map(x => ({ color: x.color, level: x.level, bulbs: [...x.bulbs].sort((a, b) => a - b) })) } };
}
/* ---- 4.12: Place bulbs. Drag a bulb to where it really sits on the photo;
   it's pinned there, and the bulbs between pins spread out again along the
   line. Tap one to select it; arrow keys nudge it; Light it shows it on the
   house. */
function hvBulbsHtml(md, side, bulbs) {
  const sel = HV.sel && bulbs.find(p => p.line === HV.sel.line && p.b === HV.sel.b);
  const pinned = (md.rooflines[side] || []).reduce((n, l) => n + (l.pins || []).length, 0);
  return `<p class="small">${sel ? `<b>Bulb ${sel.b}</b> ${sel.pinned ? '(pinned)' : '(spread evenly)'}` : 'Tap a bulb to select it, or drag it to where it really is.'}
      ${pinned ? ` \u00b7 ${pinned} pinned on this ${md.sides.find(x => x.id === side)?.of ? 'version' : 'elevation'}` : ''}</p>
    <div class="row">${sel ? `<button class="small" data-hvlight>Light bulb ${sel.b} on the house</button>${sel.pinned ? '<button class="small ghost" data-hvunpin>Unpin it</button>' : ''}` : ''}
      ${pinned ? '<button class="small ghost danger" data-hvunpinall>Unpin all on this photo</button>' : ''}</div>
    <p class="note">Drag a bulb dot to where that bulb sits on the photo; it turns green (pinned) and the bulbs between it and the next pin, or the end of the line, spread out evenly again. Light it on the house to check. With a bulb selected, the arrow keys nudge it (Shift: farther).</p>`;
}
function hvBulbsFrame(ctx, list, W, H, dpr, T) {
  const r = Math.max(2.5, W / 220);
  for (const p of list) {
    if (p.b > T) continue;
    const x = p.x / 100 * W, y = p.y / 100 * H, sel = HV.sel && HV.sel.line === p.line && HV.sel.b === p.b;
    ctx.fillStyle = sel ? '#FFC062' : p.pinned ? '#62D682' : 'rgba(255,226,184,.9)';
    ctx.beginPath(); ctx.arc(x, y, sel ? r * 1.8 : r, 0, 7); ctx.fill();
    if (p.pinned || sel) { ctx.strokeStyle = '#171C33'; ctx.lineWidth = dpr; ctx.stroke(); }
    if (sel) { ctx.fillStyle = '#FFE2B0'; ctx.font = `${Math.round(12 * dpr)}px system-ui, sans-serif`; ctx.fillText(String(p.b), x + r * 2.4, y - r * 2); }
  }
}
function hvBulbsWire(box, side, B, T) {
  const cv = $('#hvcv', box); if (!cv) return;
  cv.tabIndex = 0;
  const pos = e => { const r = cv.getBoundingClientRect(); return [Math.max(0, Math.min(100, (e.clientX - r.left) / r.width * 100)), Math.max(0, Math.min(100, (e.clientY - r.top) / r.height * 100))]; };
  const lines = () => clone(mapData().rooflines[side] || []);
  // Positions with bulb b of a line held at (x, y), for the live redraw
  const withPin = (lineId, b, x, y) => HouseFX.sideBulbs(lines().map(l => l.id === lineId ? { ...l, pins: HouseFX.setPin(l, b, x, y) } : l));
  const save = (lineId, b, x, y, msg) => busy(null, () => saveMap(mp => {
    const l = (mp.rooflines[side] || []).find(z => z.id === lineId); if (!l) throw new Error('That line was deleted.');
    l.pins = HouseFX.setPin(l, b, x, y); if (!l.pins.length) delete l.pins;
  }, msg)).then(() => houseView(box, side)).catch(() => houseView(box, side));
  let drag = null;
  cv.onpointerdown = e => {
    const [x, y] = pos(e), p = HouseFX.nearest(B.list.filter(q => q.b <= T), x, y, 4); if (!p) return;
    e.preventDefault(); cv.setPointerCapture(e.pointerId); cv.focus();
    drag = { line: p.line, b: p.b, x0: x, y0: y, moved: false };
    HV.sel = { line: p.line, b: p.b };
  };
  cv.onpointermove = e => {
    if (!drag) return;
    const [x, y] = pos(e);
    if (!drag.moved && Math.hypot(x - drag.x0, y - drag.y0) < 0.6) return;
    drag.moved = true; drag.x = x; drag.y = y;
    try { B.list = withPin(drag.line, drag.b, x, y); } catch (err) { toast(err.message, true); drag = null; }
  };
  cv.onpointerup = cv.onpointercancel = e => {
    if (!drag) return;
    if (cv.hasPointerCapture(e.pointerId)) cv.releasePointerCapture(e.pointerId);
    const d = drag; drag = null;
    if (d.moved) save(d.line, d.b, d.x, d.y, `Bulb ${d.b} pinned`); else houseView(box, side);
  };
  let nudge = null;
  cv.onkeydown = e => {
    const k = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }[e.key];
    if (!k || !HV.sel) return;
    const p = B.list.find(q => q.line === HV.sel.line && q.b === HV.sel.b); if (!p) return;
    e.preventDefault();
    const st = e.shiftKey ? 1.5 : 0.3, x = Math.max(0, Math.min(100, p.x + k[0] * st)), y = Math.max(0, Math.min(100, p.y + k[1] * st));
    B.list = withPin(p.line, p.b, x, y);
    clearTimeout(nudge); nudge = setTimeout(() => save(p.line, p.b, x, y, `Bulb ${p.b} pinned`).then(() => $('#hvcv', box)?.focus()), 600);
  };
  box._hvPin = (lineId, b) => save(lineId, b, null, null, `Bulb ${b} unpinned`);
}
function hvClick(e, box, side, bulbs, T) {
  const b = e.target.closest('button, a'), again = () => houseView(box, side);
  const g = HV.groups[HV.cur];
  if (!b) {
    const cv = e.target.closest('#hvcv'); if (!cv || HV.mode !== 'scene') return;
    const r = cv.getBoundingClientRect(), x = (e.clientX - r.left) / r.width * 100, y = (e.clientY - r.top) / r.height * 100;
    const p = HouseFX.nearest(bulbs, x, y, 4); if (!p) return toast('Tap closer to a bulb on the roofline.', true);
    const set = new Set(g.bulbs), add = HouseFX.around(p.b, HV.width, T), on = !set.has(p.b);
    add.forEach(n => on ? set.add(n) : set.delete(n)); g.bulbs = [...set];
    return again();
  }
  const d = b.dataset;
  if (d.hvmode) { HV.mode = d.hvmode; return again(); }
  if (d.hvlight !== undefined && HV.sel) return busy(b, () => housePreview(highlightDef(HV.sel.b, HV.sel.b, T, '#FFC062'), 10))
    .then(() => toast(`Showing bulb ${HV.sel.b}`)).catch(() => {});
  if (d.hvunpin !== undefined && HV.sel) return box._hvPin(HV.sel.line, HV.sel.b);
  if (d.hvunpinall !== undefined) return confirmBox('Unpin every bulb on this photo?', 'They spread out evenly along their lines again.', 'Unpin all', true).then(ok => ok &&
    busy(b, () => saveMap(mp => { for (const l of mp.rooflines[side] || []) delete l.pins; }, 'Unpinned')).then(again).catch(() => {}));
  if (d.hvg) { HV.cur = +d.hvg; return again(); }
  if (d.hvc) { g.color = d.hvc; return again(); }
  if (d.hvadd !== undefined) { HV.groups.push({ color: '#FFFFFF', level: 100, bulbs: [] }); HV.cur = HV.groups.length - 1; return again(); }
  if (d.hvdel !== undefined) { HV.groups.splice(HV.cur, 1); HV.cur = 0; return again(); }
  if (d.hvclr !== undefined) { g.bulbs = []; return again(); }
  if (d.hvnew !== undefined) { Object.assign(HV, { groups: [{ color: '#FFC58A', level: 100, bulbs: [] }], cur: 0, name: '', key: null }); return again(); }
  if (d.hvedit) { e.preventDefault(); const sc = S.settings.effects[d.hvedit];
    Object.assign(HV, { mode: 'scene', key: d.hvedit, name: sc.label || '', cur: 0, groups: clone(sc.scene.groups).map(x => ({ ...x, bulbs: x.bulbs || [] })) }); return again(); }
  if (d.hvnums !== undefined) {
    try {
      const nums = HouseFX.parseBulbs($('#hvnums', box).value, T);
      if (!nums.length) return toast('Type bulb numbers, like 10-12, 40.', true);
      const set = new Set(g.bulbs); nums.forEach(n => set.add(n)); g.bulbs = [...set];
      toast(`Lit ${nums.length} bulb${nums.length === 1 ? '' : 's'}`); return again();
    } catch (err) { return toast(err.message, true); }
  }
  if (d.hvlm !== undefined) {
    const want = ($('#hvlm', box).value || '').trim().toLowerCase(); HV.lm = want;
    const hits = mapData().landmarks.filter(l => want && l.name.toLowerCase().includes(want));
    if (!hits.length) return toast(want ? `No landmarks named “${want}”.` : 'Type part of a landmark name, like “window”.', true);
    const set = new Set(g.bulbs); hits.forEach(l => HouseFX.around(l.bulb, HV.width, T).forEach(n => set.add(n))); g.bulbs = [...set];
    toast(`Lit ${hits.length} landmark${hits.length === 1 ? '' : 's'}`); return again();
  }
  if (d.hvtry !== undefined) return busy(b, () => housePreview(hvSceneEffect(T, HV.name || 'Scene'), 15))
    .then(() => toast('Showing on your lights for 15 minutes, then back to the schedule')).catch(() => {});
  if (d.hvsave !== undefined) return busy(b, async () => {
    const label = ($('#hvname', box).value || '').trim(); if (!label) { $('#hvname', box).focus(); throw new Error('Give the scene a name first.'); }
    const n = clone(S.settings); n.effects = n.effects || {};
    const key = HV.key || slug(label, n.effects);
    n.effects[key] = hvSceneEffect(T, label);
    await saveSettings(n, HV.key ? 'Scene updated' : `Saved “${label}”`); HV.key = key; HV.name = label;
  }).then(again).catch(() => {});
}

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
  const sideName = Elev.label(md, side);
  const flat = R.flat ? `<div class="panel stack"><div class="row"><h2 class="grow">Flat diagram</h2>
      <button class="small" data-flatsvg>Download SVG</button><button class="small ghost" data-flat>Close</button></div>
      <div class="flatmap">${RL.flatHouseSvg(flatSides(md), md.rooflines, md.landmarks, 'Flat diagram of every elevation')}</div>
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
      <div class="sub ${l.bulbs && Math.max(l.bulbs.from, l.bulbs.to) > houseSpace() ? 'warn' : ''}">${l.bulbs ? `Bulbs ${l.bulbs.from}–${l.bulbs.to}${Math.max(l.bulbs.from, l.bulbs.to) > houseSpace() ? ` (past bulb ${houseSpace()})` : ''}` : 'No bulbs assigned'} · ${l.points.length} points${(l.wire || []).length ? ` · ${l.wire.length} wire-only stretch${l.wire.length === 1 ? '' : 'es'}` : ''}</div></div>
      <button class="small ghost" data-rbulbs="${esc(l.id)}">Bulbs</button><button class="small ghost" data-redit="${esc(l.id)}">Adjust</button><button class="small ghost danger" data-rdel="${esc(l.id)}" aria-label="Delete this section">✕</button></div>`).join('')}</div>` : '';
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
    const url = URL.createObjectURL(new Blob([RL.flatHouseSvg(flatSides(md), md.rooflines, md.landmarks)], { type: 'image/svg+xml' }));
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
    const before = R.editing && (md.rooflines[side] || []).find(l => l.id === R.editing);
    if (before && before.bulbs) line.bulbs = { ...before.bulbs };          // its bulb numbers stay (3.17)
    if (before && before.pins) line.pins = before.pins.map(p => [...p]);   // and its pinned bulbs (4.12)
    if (!RL.validSection(line)) { toast('That section needs 2 to 100 points on the photo.', true); return true; }
    await busy(b, () => saveMap(mp => {
      const list = (mp.rooflines[side] || []).slice(), i = list.findIndex(l => l.id === line.id);
      if (i >= 0) list[i] = line; else { if (list.length >= RL.LIMITS.sections) throw new Error(`At most ${RL.LIMITS.sections} sections per side.`); list.push(line); }
      mp.rooflines[side] = list;
    }, 'Roofline saved')).then(() => { roofReset(); VIEWS.mapRender(); }).catch(() => {});
    return true;
  }
  if (d.redit) { const l = (md.rooflines[side] || []).find(x => x.id === d.redit); if (l) { roofBegin(l); VIEWS.mapRender(); } return true; }
  if (d.rbulbs) {
    const l = (md.rooflines[side] || []).find(x => x.id === d.rbulbs); if (!l) return true;
    const T = houseSpace();
    dialog(`<h2>Bulbs on this line</h2>
      <p class="small">Which bulb numbers run along this line, from its first point to its last? Use the bulb finder to check the two ends. If they count down (for example 84 to 40), enter them that way.</p>
      <div class="row"><label class="field">First point<input type="number" name="a" min="1" max="${T}" value="${l.bulbs ? l.bulbs.from : ''}" required></label>
        <label class="field">Last point<input type="number" name="z" min="1" max="${T}" value="${l.bulbs ? l.bulbs.to : ''}" required></label></div>
      <p class="note">The bulbs are spread evenly along the line, skipping wire-only stretches. That's what the house preview and scene builder use. To move single bulbs to where they really are, use <b>House view \u203a Place bulbs</b>.</p>`, async f => {
      const a = Math.round(+f.a.value), z = Math.round(+f.z.value);
      if (!(a >= 1 && z >= 1 && a <= T && z <= T)) throw new Error(`Bulb numbers go from 1 to ${T}.`);
      await saveMap(mp => { const x = (mp.rooflines[side] || []).find(q => q.id === l.id); if (!x) return;
        x.bulbs = { from: a, to: z };
        if (x.pins) { x.pins = x.pins.filter(p => p[0] >= Math.min(a, z) && p[0] <= Math.max(a, z)); if (!x.pins.length) delete x.pins; }   // 4.12
      }, 'Bulbs saved');
      VIEWS.mapRender();
    }, { ok: 'Save', extraFoot: l.bulbs ? '<button type="button" class="ghost danger" data-rbclear>Clear</button>' : '',
      onOpen: f => { const c = f.querySelector('[data-rbclear]'); if (c) c.onclick = () => busy(c, () => saveMap(mp => {
        const x = (mp.rooflines[side] || []).find(q => q.id === l.id); if (x) { delete x.bulbs; delete x.pins; } }, 'Bulbs cleared')).then(() => { $('#dlg').close(); VIEWS.mapRender(); }).catch(() => {}); } });
    return true;
  }
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
  const P = D.paint, T = addressSpace(S.designDev), slots = PT.slotsNeeded(P.canvas), over = slots > PT.MAX_SLOTS;
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
    if (t.value === 'house' && P.scope !== 'house') { painterSet(P, PT.expand(PT.compress(P.canvas), addressSpace(S.designDev))); P.scope = 'house'; }
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
/* 4.12: a zone lit for checking: its first bulb green and its last red
   (the other way round when it runs backward), the rest in the finder color,
   so it's plain on the house where it starts, where it ends, and which way. */
function zoneCheckDef(start, end, total, color, reverse) {
  if (end === start) return highlightDef(start, end, total, color);
  const [first, last] = reverse ? ['#FF0000', '#00FF00'] : ['#00FF00', '#FF0000'];
  // Review #4: never a middle the same as an end marker
  const mid = /^#(FF0000|00FF00)$/i.test(color) ? '#FFC062' : color;
  const runs = [];
  if (start > 1) runs.push(['#000000', start - 1]);
  runs.push([first, 1]);
  if (end - start > 1) runs.push([mid, end - start - 1]);
  runs.push([last, 1]);
  if (end < total) runs.push(['#000000', total - end]);
  const segs = runsToSegs(runs);
  if (segs.length > MAX_SLOTS) throw new Error(`That needs ${segs.length} color slots; the controller allows ${MAX_SLOTS}.`);
  return { label: `Zone ${start}–${end}`, colors: segs.map(x => x.c), counts: segs.map(x => x.n), custom_mode: 0, brightness: 255, speed: 0 };
}
/* The elevations (as shown in the whole house) with some of bulbs a..z. */
function zoneElevs(md, a, z, dev) {
  return Elev.list(md).filter(e => forDev(e, dev)).map(e => Elev.use(md, e))
    .filter(k => HouseFX.sideBulbs(md.rooflines[k] || []).some(p => p.b >= a && p.b <= z));
}
/* A still picture of one photo with a zone's bulbs marked: green where it
   starts, red where it ends, amber between, the rest dim. */
function zonePicture(cv, side, a, z, reverse) {
  const md = mapData(), bulbs = HouseFX.sideBulbs(md.rooflines[side] || []);
  const ctx = cv.getContext('2d'), tok = (cv._tok = (cv._tok || 0) + 1);
  const draw = img => {
    if (cv._tok !== tok) return;
    const dpr = window.devicePixelRatio || 1, W = Math.round((cv.clientWidth || 320) * dpr), H = img ? Math.round(W * img.naturalHeight / img.naturalWidth) : Math.round(W * .6);
    cv.width = W; cv.height = H; ctx.clearRect(0, 0, W, H);
    if (img) { ctx.drawImage(img, 0, 0, W, H); ctx.fillStyle = 'rgba(5,7,18,.6)'; ctx.fillRect(0, 0, W, H); }
    const r = Math.max(2, W / 200), [s, e] = reverse ? [z, a] : [a, z];
    for (const p of bulbs) {
      const x = p.x / 100 * W, y = p.y / 100 * H, inz = p.b >= a && p.b <= z;
      ctx.fillStyle = !inz ? 'rgba(170,175,205,.35)' : p.b === s ? '#00FF00' : p.b === e ? '#FF3030' : '#FFC062';
      ctx.beginPath(); ctx.arc(x, y, inz ? r * (p.b === s || p.b === e ? 1.9 : 1.2) : r * .7, 0, 7); ctx.fill();
    }
  };
  draw(null);
  if (S.photos.has(side)) loadPhoto(side).then(url => { const im = new Image(); im.onload = () => draw(im); im.src = url; }).catch(() => {});
}
function zoneDialog(i, F, rerender) {
  const md = mapData(), z = md.zones[i];
  if (!z) return;
  if (z.device && houseDevs().some(x => x.id === z.device)) S.houseDev = z.device;     // 4.10: its controller's bulbs
  const T = houseSpace();
  const read = f => {
    const name = f.zn.value.trim(), start = Number(f.zs.value), end = Number(f.ze.value);
    if (!name) throw new Error('Give the zone a name.');
    if (md.zones.some((o, j) => j !== i && o.name.trim().toLowerCase() === name.toLowerCase() && (o.device || null) === (z.device || null))) throw new Error(`There's already a zone named “${name}”.`);
    if (!Number.isInteger(start) || !Number.isInteger(end)) throw new Error('Bulb numbers must be whole numbers.');
    if (start < 1 || end > T) throw new Error(`Bulbs go from 1 to ${T}.`);
    if (end < start) throw new Error('The last bulb can\u2019t be before the first.');
    return { name, start, end, reverse: f.zrev.checked };
  };
  const nudge = (k, by) => `<button type="button" class="small ghost" data-znudge="${k}" data-by="${by}" aria-label="${{ s: 'First bulb', e: 'Last bulb', b: 'The whole zone' }[k]} ${by > 0 ? 'one later' : 'one earlier'}">${by > 0 ? '+1' : '−1'}</button>`;
  dialog(`<h2>Edit zone</h2>
    <label class="field">Name<input type="text" name="zn" maxlength="60" required value="${esc(z.name)}"></label>
    <div class="row"><label class="field">First bulb<input type="number" name="zs" min="1" max="${T}" value="${z.start}"></label>
      <label class="field">Last bulb<input type="number" name="ze" min="1" max="${T}" value="${z.end}"></label></div>
    <p class="note" data-zcount>${z.end - z.start + 1} bulbs, out of ${T}.</p>
    <div class="row small zcal" aria-label="Line it up"><span>First ${nudge('s', -1)}${nudge('s', 1)}</span><span>Last ${nudge('e', -1)}${nudge('e', 1)}</span><span>Whole zone ${nudge('b', -1)}${nudge('b', 1)}</span></div>
    <label class="check"><input type="checkbox" name="zrev" ${z.reverse ? 'checked' : ''}> Runs the other way (from its last bulb to its first)</label>
    <div class="row"><button type="button" class="small" data-zlight>Light these bulbs</button>
      ${F.range ? `<button type="button" class="small ghost" data-zfinder>Use the finder's range (${F.bulb}–${F.end})</button>` : ''}</div>
    <div class="zpic"><div class="row small" data-zsides></div><canvas data-zcv aria-label="This zone on the photo"></canvas></div>
    <p class="note">Light the zone: its first bulb is <b style="color:#1DB954">green</b> and its last <b style="color:#E5484D">red</b>. If they're not where the zone starts and ends on the house, nudge them; while it's lit, the house follows each change. <b>Runs the other way</b> makes a zone's patterns (Combine patterns by zone) start from its last bulb. The schedule comes back by itself 10 minutes after the last change.</p>`,
    async f => {
      const v = read(f);
      await saveMap(mp => { mp.zones[i] = { ...mp.zones[i], ...v }; if (!v.reverse) delete mp.zones[i].reverse; }, `Zone “${v.name}” saved`);
      rerender();
    }, { ok: 'Save zone', onOpen: f => {
      let lit = false, timer = null, side = null;
      const light = btn => { let v; try { v = read(f); } catch (err) { return toast(err.message, true); }
        return busy(btn, () => housePreview(zoneCheckDef(v.start, v.end, T, F.color, v.reverse), 10))
          .then(() => { lit = true; toast(`Showing bulbs ${v.start}–${v.end}`); }).catch(() => {}); };
      const picture = () => {
        const a = Number(f.zs.value), b = Number(f.ze.value), md2 = mapData();
        const ks = Number.isInteger(a) && Number.isInteger(b) && b >= a ? zoneElevs(md2, a, b, z.device) : [];
        if (!ks.includes(side)) side = ks.includes(Elev.use(md2, Elev.of(md2, F.side) || {})) ? Elev.use(md2, Elev.of(md2, F.side)) : ks[0] || null;
        $('[data-zsides]', f).innerHTML = ks.length ? 'On ' + ks.map(k => `<button type="button" class="small ${k === side ? 'current' : 'ghost'}" data-zside="${esc(k)}">${esc(Elev.label(md2, k))}</button>`).join('')
          : '<span class="muted">None of these bulbs is on a traced photo yet (House view › Bulbs on each line).</span>';
        const cv = $('[data-zcv]', f); cv.hidden = !side; if (side) zonePicture(cv, side, a, b, f.zrev.checked);
      };
      const changed = () => {
        const a = Number(f.zs.value), b = Number(f.ze.value);
        $('[data-zcount]', f).textContent = Number.isInteger(a) && Number.isInteger(b) && b >= a ? `${b - a + 1} bulbs, out of ${T}.` : 'Check the bulb numbers.';
        picture();
        if (lit) { clearTimeout(timer); timer = setTimeout(() => light(null), 450); }
      };
      f.zs.oninput = f.ze.oninput = changed; f.zrev.onchange = changed;
      f.addEventListener('click', e => {
        const b = e.target.closest('button'); if (!b) return;
        if (b.dataset.zfinder !== undefined) { f.zs.value = F.bulb; f.ze.value = F.end; changed(); }
        if (b.dataset.zside) { side = b.dataset.zside; picture(); }
        if (b.dataset.znudge) {
          const by = +b.dataset.by, k = b.dataset.znudge; let a = Number(f.zs.value), c = Number(f.ze.value);
          if (k === 's') a += by; else if (k === 'e') c += by; else { if (a + by < 1 || c + by > T) return toast(`Bulbs go from 1 to ${T}.`, true); a += by; c += by; }
          if (a < 1 || c > T || c < a) return toast(a < 1 || c > T ? `Bulbs go from 1 to ${T}.` : 'The last bulb can\u2019t be before the first.', true);
          f.zs.value = a; f.ze.value = c; changed();
        }
        if (b.dataset.zlight !== undefined) light(b);
      });
      picture();
    } });
}

/* Paint-by-zone dialog for the designer. */
/* A zone's color in Paint by zone, dimmed to its brightness (3.17). */
function zoneColor(f, i) {
  const v = f['z' + i].value, c = v === 'custom' ? f['c' + i].value.toUpperCase() : v;
  if (!c || c === 'off') return c;
  return HouseFX.dim(c, +f['l' + i].value || 100);
}
function zonePainter(D, rerender) {
  const md0 = mapData();
  // 4.10: zones for one controller are painted on that controller's bulbs.
  // Paint by zone makes one pattern, so it offers the zones for the
  // controller Create counts (Bulbs of) and the zones for every controller.
  const devs = houseDevs(), owned = md0.zones.some(z => z.device);
  const dd = owned && devs.length > 1 ? ((devs.find(x => x.id === S.designDev) || devs[0]).id) : '';
  const left = md0.zones.filter(z => !forDev(z, dd));
  const md = { ...md0, zones: md0.zones.filter(z => forDev(z, dd)) }, T = dd ? addressSpace(dd) : addressSpace();
  if (dd && !md.zones.length) return confirmBox('No zones for this controller', `Every zone is for another controller. Choose <b>Bulbs of</b> above the preview to paint ${esc(devName(left[0].device))}\u2019s zones.`, 'OK');
  if (!md.zones.length) return confirmBox('No zones yet', 'Open the <b>House</b> tab, select a range with the bulb finder and save it as a zone (for example \u201cGarage roof\u201d). Then come back here to paint it.', 'OK');
  const opts = sel => `<option value="">Leave as the rest</option>${S.catalog.palette.map(p => `<option value="${p.hex}" ${sel === p.hex ? 'selected' : ''}>${esc(p.name)}</option>`).join('')}<option value="off">\u2715 Zone off</option><option value="custom">Other color\u2026</option>`;
  dialog(`<h2>Paint by zone</h2><p class="note">${T} bulbs${dd ? ` (${esc(devName(dd))})` : ''}. Later zones in the list win where zones overlap.${left.length ? ` Zones for ${esc([...new Set(left.map(z => devName(z.device)))].join(', '))} aren\u2019t listed: choose <b>Bulbs of</b> to paint those, or use <b>Combine patterns by zone</b>, which makes one pattern for each controller.` : ''}</p>
    <div class="stack">${md.zones.map((z, i) => `<div class="row"><div class="grow" style="min-width:9em"><b>${esc(z.name)}</b><div class="small muted">Bulbs ${z.start}\u2013${z.end}</div></div>
      <select name="z${i}" style="width:auto">${opts('')}</select><input type="color" name="c${i}" value="#ffffff" hidden aria-label="Color for ${esc(z.name)}">
      <select name="l${i}" style="width:auto" aria-label="Brightness for ${esc(z.name)}">${[100, 75, 50, 35, 20, 10].map(n => `<option value="${n}">${n}%</option>`).join('')}</select></div>`).join('')}</div>
    <p class="note">The percentage dims a zone against the others (the controller has one brightness for the whole pattern, so it's done by darkening that zone's color). Mixed brightness works best for still patterns.</p>
    <label class="field">Everything else<select name="base"><option value="off">\u2715 Zone off (dark, never moves)</option><option value="#000000">Black</option>${S.catalog.palette.filter(p => p.hex !== '#000000').map(p => `<option value="${p.hex}">${esc(p.name)}</option>`).join('')}</select></label>
    <p class="note" data-slots></p>`,
  async f => {
    const assign = md.zones.map((z, i) => ({ start: z.start, end: z.end, color: zoneColor(f, i) })).filter(a => a.color);
    if (!assign.length) throw new Error('Choose a color for at least one zone.');
    const segs = paintZones(assign, f.base.value, T);
    if (segs.length > MAX_SLOTS) throw new Error(`That needs ${segs.length} color slots, but the controller allows ${MAX_SLOTS}. Use fewer zones or larger ones.`);
    D.segs = segs; D.sel = 0; D.mode = 0;
    if (!D.label) D.label = 'Zones';
    toast('Zones painted. Preview it, then save.'); rerender();
  }, { ok: 'Paint', onOpen: f => {
    const upd = () => {
      md.zones.forEach((_, i) => { f['c' + i].hidden = f['z' + i].value !== 'custom'; });
      const assign = md.zones.map((z, i) => ({ start: z.start, end: z.end, color: zoneColor(f, i) })).filter(a => a.color);
      const n = assign.length ? paintZones(assign, f.base.value, T).length : 0;
      $('[data-slots]', f).textContent = n ? `Uses ${n} of ${MAX_SLOTS} color slots.${n > MAX_SLOTS ? ' Too many.' : ''}` : '';
    };
    f.addEventListener('change', upd); f.addEventListener('input', upd); upd();
  } });
}

/* Combine patterns by zone (4.7): a different one of your patterns along each
   zone (Christmas on the garage, the flag on the porch), as one pattern with
   one motion. The fitting is in zonemix.js; this fills the designer, where
   Preview on house, Try and Save work as for any pattern. */
const combinable = e => !!(e && Array.isArray(e.colors) && e.colors.length && !e.split && !e.saved && e.builtin === undefined);
function zoneCombiner(D, rerender) {
  const md = mapData(), T = addressSpace();
  if (!md.zones.length) return confirmBox('No zones yet', 'Open the <b>House</b> tab, select a range with the bulb finder and save it as a zone (for example “Garage roof”). Then come back here to give each zone a pattern.', 'OK');
  const pats = Object.entries(S.settings.effects || {}).filter(([, e]) => combinable(e));
  if (!pats.length) return confirmBox('No patterns to combine', 'Combine uses patterns of your own colors (made in Create). Built-in effects and patterns saved only on the controller can’t be laid along a zone.', 'OK');
  const pre = S.combinePrefill || {}; S.combinePrefill = null;          // 4.12: from the whole-house view
  const optsFor = i => `<option value="">Leave as the rest</option>${pats.map(([k, e]) => `<option value="${esc(k)}" ${pre[i] === k ? 'selected' : ''}>${esc(e.label || k)}</option>`).join('')}`;
  const modes = S.catalog.custom_modes;
  // 4.10: zones for one controller (House tab). When a chosen zone is one
  // controller's, each controller gets its own combined pattern, along its
  // own bulbs, saved together as a Split by controller pattern.
  const devs = houseDevs();
  const owned = devs.length > 1 && md.zones.some(z => z.device && devs.some(x => x.id === z.device));
  const read = f => {
    const picks = md.zones.map((z, i) => { const e = (S.settings.effects || {})[f['p' + i].value]; return combinable(e) ? e : null; });
    // Review #1 (4.7): the controller's own limit per block, as scenes use
    // (60 on some), so what fits here also fits there.
    const perSlot = (S.status && S.status.slot_limit) || PER_SLOT;
    const mix = (pk, total) => ZoneMix.combine({ zones: md.zones, picks: pk, base: f.base.value, total, maxSlots: MAX_SLOTS, perSlot });
    if (!owned || !md.zones.some((z, i) => picks[i] && z.device)) return { picks, r: mix(picks, T) };
    const parts = devs.map(dv => {
      const pk = picks.map((p, i) => forDev(md.zones[i], dv.id) ? p : null);
      if (!pk.some(Boolean)) return { dev: dv, r: null };
      try { return { dev: dv, r: mix(pk, devBulbs(dv)) }; } catch (e) { throw new Error(`${dv.name || 'Controller'}: ${e.message}`); }
    });
    return { picks, parts };
  };
  dialog(`<h2>Combine patterns by zone</h2>
    <p class="note">${owned ? 'Each zone shows the pattern you choose, along its own controller’s bulbs (a zone for every controller shows on each). With a zone for one controller chosen, this saves one pattern for each controller, together as a <b>Split by controller</b> pattern.' : `${T} bulbs. Each zone shows the pattern you choose, repeated along that zone only.`} Later zones in the list win where zones overlap.</p>
    ${owned ? '<label class="field">Name<input type="text" name="nm" maxlength="40" placeholder="e.g. Holidays by zone"></label>' : ''}
    <div class="stack">${md.zones.map((z, i) => `<div class="row"><div class="grow" style="min-width:9em"><b>${esc(z.name)}</b><div class="small muted">Bulbs ${z.start}–${z.end}${owned ? ' · ' + (z.device ? esc(devName(z.device)) : 'every controller') : ''}</div></div>
      <select name="p${i}" style="flex:1 1 11em;min-width:0;max-width:100%" aria-label="Pattern for ${esc(z.name)}">${optsFor(i)}</select></div>`).join('')}</div>
    <label class="field">Everything else<select name="base"><option value="off">✕ Off (dark, never moves)</option><option value="#000000">Black</option>${S.catalog.palette.filter(p => p.hex !== '#000000').map(p => `<option value="${p.hex}">${esc(p.name)}</option>`).join('')}</select></label>
    <fieldset class="stack" style="border:0;padding:0;margin:0"><legend class="small" style="font-weight:650">Motion</legend>
      <label class="check"><input type="radio" name="mv" value="still" checked> Still: each zone stays in place (looks best)</label>
      <label class="check"><input type="radio" name="mv" value="move"> Moving: <select name="mode" style="width:auto">${modes.map((m, i) => i ? `<option value="${i}">${esc(m)}</option>` : '').join('')}</select></label>
      <p class="note">A controller has one motion for all its bulbs, so a moving pattern carries each zone’s colors into the next zone.</p></fieldset>
    <div data-cmprev></div><p class="note" data-cmnote></p>`,
  async f => {
    const got = read(f), { picks } = got;
    const first = picks.find(Boolean);
    if (got.parts) {
      const name = (f.nm.value || '').trim() || [...new Set(picks.filter(Boolean).map(e => e.label))].join(' + ').slice(0, 40);
      const n = clone(S.settings); n.effects = n.effects || {};
      const split = {}, mode = f.mv.value === 'move' ? +f.mode.value : 0;
      for (const { dev, r } of got.parts) {
        if (!r) { split[dev.id] = 'off'; continue; }
        const label = `${name} (${dev.name || 'Controller'})`.slice(0, 60), key = slug(label, n.effects);
        n.effects[key] = { label, colors: r.segs.map(x => x.c), counts: r.segs.map(x => x.n), custom_mode: mode,
          speed: first.speed ?? 100, brightness: r.brightness, folder: 'Zone parts' };
        split[dev.id] = key;
      }
      const key = slug(name, n.effects);
      n.effects[key] = { label: name, split };
      await saveSettings(n, `Saved “${name}”, one part for each controller`);
      return go('patterns');
    }
    const { r } = got;
    D.segs = r.segs; D.sel = 0;
    D.mode = f.mv.value === 'move' ? +f.mode.value : 0;
    D.speed = first.speed ?? 100;
    D.brightness = r.brightness;
    D.exact = picks.filter(Boolean).every(e => e.exact_colors);
    const names = [...new Set(picks.filter(Boolean).map(e => e.label))];
    if (!D.key) D.label = names.join(' + ').slice(0, 40);
    toast('Combined. Preview it on the house, then save it.'); rerender();
  }, { ok: 'Combine', onOpen: f => {
    const upd = () => {
      f.mode.disabled = f.mv.value !== 'move';
      let got;
      try { got = read(f); } catch (e) {
        $('[data-cmprev]', f).innerHTML = ''; $('[data-cmnote]', f).textContent = e.message; return;
      }
      const chosen = got.picks.filter(Boolean), exact = chosen.filter(e => e.exact_colors).length;
      if (got.parts) {
        $('[data-cmprev]', f).innerHTML = got.parts.map(({ dev, r }) => `<div class="small" style="margin-top:6px"><b>${esc(dev.name || 'Controller')}</b> (${devBulbs(dev)} bulbs)${r ? '' : ': off, no zone chosen for it'}</div>${r ? strand(r.segs.map(x => x.c), r.segs.map(x => x.n)) : ''}`).join('');
        $('[data-cmnote]', f).textContent = 'Saves a part for each controller (in the Zone parts folder) and a split pattern that shows them together.';
        return;
      }
      const out = got.r;
      $('[data-cmprev]', f).innerHTML = strand(out.segs.map(s => s.c), out.segs.map(s => s.n));
      const st = Object.entries(out.stretched).map(([i, k]) => `${md.zones[i].name} (colors ${k}× as long)`);
      $('[data-cmnote]', f).textContent = `Uses ${out.segs.length} of ${MAX_SLOTS} color blocks.` +
        (st.length ? ` To fit, these zones' colors were made longer: ${st.join(', ')}.` : ' Every zone keeps its pattern exactly.') +
        (exact && exact < chosen.length ? ' One of these patterns is set to use its colors exactly; the combined one follows Color correction like the others.' : '');
    };
    f.addEventListener('change', upd); upd();
  } });
}

/* Patterns › Split by controller (3.17): each controller runs its own
   pattern, speed and brightness at the same time. One controller can only
   run one pattern, so this is how parts of the house move independently. */
async function splitDialog(key) {
  let devs;
  try { devs = await loadDevices(); } catch (e) { return toast(e.message, true); }
  const sel = devs.filter(d => d.selected);
  if (sel.length < 2) return confirmBox('One controller', `This needs two or more controllers. A controller runs one pattern at a time (one motion, speed and brightness for all of its bulbs), so parts of the house can only move independently when they're on different controllers. ${devs.length > 1 ? 'Choose the controllers this app uses in Setup › Lights &amp; controller.' : ''}`, 'OK');
  const cur = key ? S.settings.effects[key] : { label: '', split: {}, rest: 'off' };
  const pats = Object.entries(S.settings.effects || {}).filter(([k, e]) => !e.split && k !== key);
  const opts = v => `<option value="off" ${v === 'off' ? 'selected' : ''}>✕ Off</option>${pats.map(([k, e]) => `<option value="${esc(k)}" ${v === k ? 'selected' : ''}>${esc(e.label || k)}</option>`).join('')}`;
  dialog(`<h2>${key ? 'Edit' : 'New'} pattern split by controller</h2>
    <label class="field">Name<input type="text" name="nm" maxlength="40" value="${esc(cur.label || '')}" placeholder="e.g. Twinkle upstairs, white garage" required></label>
    ${sel.map((d, i) => `<label class="field">${esc(d.name)}<select name="d${i}">${opts(cur.split[d.id] || (key ? 'off' : (pats[0] || [])[0]))}</select></label>`).join('')}
    ${Object.keys(cur.split || {}).filter(id => !sel.some(d => d.id === id)).length ? `<p class="note">Also kept: the part for ${Object.keys(cur.split).filter(id => !sel.some(d => d.id === id)).map(id => esc((devs.find(d => d.id === id) || {}).name || id)).join(', ')}, a controller this app doesn't run right now.</p>` : ''}
    <p class="note">Each controller shows its own pattern, with its own motion, speed and brightness. A split pattern works anywhere a pattern does: Turn on, rules, rotations and the backup timer.</p>`, async f => {
    const label = f.nm.value.trim(); if (!label) throw new Error('Give it a name.');
    // Keep the parts of controllers not shown here (not ticked on the Lights
    // tab right now), so editing doesn't lose them (3.17.1).
    const split = { ...(cur.split || {}) }; sel.forEach((d, i) => { split[d.id] = f['d' + i].value; });
    if (Object.values(split).every(v => v === 'off')) throw new Error('Choose a pattern for at least one controller.');
    const n = clone(S.settings); const k = key || slug(label, n.effects);
    n.effects[k] = { label, split, rest: 'off' };
    await saveSettings(n, key ? 'Changes saved' : `Saved “${label}”`); VIEWS.patterns('mine');
  }, { ok: 'Save' });
}

/* Backup timer panel (the safety net; Setup › Lights & controller since 4.0). */
async function safetyPanel(box) {
  let st;
  try { st = await api('safety'); } catch (e) { box.innerHTML = `<p class="muted">${esc(e.message)}</p>`; return; }
  const devs = Object.values(st.devices || {});
  const conflicts = devs.flatMap(d => d.conflicts || []);
  if (st.paused) {
    // 4.3.9: paused for everyone; see safety.py PAUSED.
    box.innerHTML = `<div class="panel-head"><h2>Backup timer</h2><span class="pill">Paused</span></div>
      <p class="callout warn small"><b>Paused in this version.</b> Every time Trimlight\u2019s cloud stopped being able to read a controller (code 12006) so far, it came within minutes of the backup timer writing its calendar timers through the cloud. Until that is understood, it writes nothing to your controller.</p>
      <p class="note">Your lights keep running from this app as usual. Without this computer or the internet they stay as they were last set.${st.enabled ? ' Your choice to use it is kept for when it returns.' : ''}</p>`;
    return;
  }
  box.innerHTML = `<div class="panel-head"><h2>Backup timer</h2><label class="check"><input type="checkbox" id="sfon" ${st.enabled ? 'checked' : ''}> On</label></div>
    <p class="note">Copies the next nights into the controller's own timers, so the lights still come on and go off if this computer or the internet is down.
      The app keeps running the lights as usual. It never saves patterns: each night uses a pattern already saved on the controller under the same name, and a night whose pattern isn't there is skipped.
      It writes only its own calendar timers, only when the controller has been settled for two minutes and no music show is near, backs up the controller first, and checks every write.</p>
    ${st.halted ? `<p class="callout warn small"><b>Stopped itself</b> (${esc(st.halted.at.replace('T', ' '))}): ${esc(st.halted.why)}
      It won't write to the controller again until you turn it off and on again.</p>` : ''}
    ${st.enabled && st.held && !st.halted ? '<p class="note">Waiting: no writes during a music show, local-link use, or the 15 minutes after.</p>' : ''}
    ${st.enabled ? `
      <label class="row small">Copy the next <select id="sfdays" style="width:auto">${[3, 5, 7, 10, 14].map(n => `<option ${n === st.days ? 'selected' : ''}>${n}</option>`).join('')}</select> nights</label>
      ${devs.length ? devs.map(d => `<p class="callout small ${d.ok ? 'ok' : 'warn'}">${d.ok ? 'Armed' : 'Not armed'}: ${esc(d.message || '')}${d.last_sync_label ? ` <span class="muted">(last copied ${esc(d.last_sync_label)})</span>` : ''}
        ${d.backup ? `<br><a href="#" data-backup="${esc(d.backup)}">Download the controller backup taken before this change</a>` : ''}</p>`).join('') : '<p class="note">Waiting for the first copy (a few seconds after the app talks to the controller).</p>'}
      ${conflicts.includes('daily') ? `<p class="callout warn small">The Trimlight app's daily timers are on. They would run too whenever the controller is left in Timer mode, so the backup timer waits until they're off. <button class="small" data-dailyoff>Turn them off</button></p>` : ''}
      ${conflicts.some(c => c.startsWith('calendar:')) ? '<p class="callout warn small">The controller has calendar events made in the Trimlight app on the coming nights. They would run too whenever the controller is left in Timer mode, so the backup timer waits until they\u2019re removed in the Trimlight app (then choose Update now). Events on other dates are fine.</p>' : ''}
      ${st.plan.length ? `<details><summary>What the controller will do on its own</summary><div class="list">${st.plan.map(p => `<div class="item"><div class="grow"><b>${esc(p.date.replace(/^(\d\d)-(\d\d)$/, (_, mo, dy) => MONTHS[+mo - 1] + ' ' + (+dy)))}</b> <span class="sub">${esc(p.rule)}</span></div>
        <span class="num small">${esc(hm12(p.on))} \u2013 ${esc(hm12(p.off))}</span><span class="small">${esc(p.pattern)}</span></div>`).join('')}</div></details>` : ''}
      <div><button class="small" data-sfsync>Update now</button></div>
      <p class="note">On a normal night the controller now runs the lights itself from its copy, so they also go off on time if this computer stops. After a manual change, weather or the security flash, the app keeps control for the rest of that night; if it stops then, the lights stay on until it returns. Weather, minute-by-minute rotation, sliders and anything after midnight need the app.</p>` : ''}`;
  box.onchange = async e => {
    if (e.target.id === 'sfon' && e.target.checked) {
      e.target.checked = false;                       // until confirmed (4.2.1)
      const yes = await confirmBox('Turn on the backup timer?',
        'It writes calendar timers to your controller through Trimlight\u2019s cloud. It never saves patterns: each night uses a '
        + 'pattern already saved on the controller with the same name, and other nights are skipped.<br><br>'
        + 'If anything looks wrong (the controller doesn\u2019t read back as written, or Trimlight can\u2019t read it), it removes '
        + 'its timers and stops itself.<br><br>Leave it off if you also set timers in the Trimlight app.', 'Turn it on');
      if (!yes) return;
      e.target.checked = true;
    }
    if (e.target.id === 'sfon' || e.target.id === 'sfdays') {
      const n = clone(S.settings); n.safety = { enabled: $('#sfon', box).checked, days: +($('#sfdays', box)?.value || st.days || 7) };
      await busy(null, () => saveSettings(n, n.safety.enabled ? 'Backup timer on' : 'Backup timer off. Removing its timers from the controller.')).catch(() => {});
      setTimeout(() => safetyPanel(box), 2500);
    }
  };
  box.onclick = async e => {
    const a = e.target.closest('[data-backup]');
    if (a) { e.preventDefault(); const data = await api('safety/backup?file=' + encodeURIComponent(a.dataset.backup));
      const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }));
      const link = Object.assign(document.createElement('a'), { href: url, download: a.dataset.backup }); document.body.append(link); link.click(); link.remove(); return; }
    const b = e.target.closest('button'); if (!b) return;
    if (b.dataset.sfsync !== undefined) busy(b, () => api('safety/sync', { body: {} })).then(() => { toast('Backup timer updated'); safetyPanel(box); }).catch(() => {});
    if (b.dataset.dailyoff !== undefined && await confirmBox('Turn off the Trimlight app\u2019s daily timers?', 'The controller is backed up first. You can turn them back on in the Trimlight app.', 'Turn off'))
      busy(b, () => api('safety/daily_off', { body: {} })).then(r => { toast(`Turned off ${r.turned_off} daily timer${r.turned_off === 1 ? '' : 's'}`); api('safety/sync', { body: {} }).then(() => safetyPanel(box)); }).catch(() => {});
  };
}
