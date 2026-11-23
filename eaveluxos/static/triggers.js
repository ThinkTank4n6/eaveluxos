/* SPDX-License-Identifier: MIT
   Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)

   Triggers and calendar (4.18): birthdays and anniversaries (Schedule ›
   Special days), who's home (Alerts), automation templates, and the Siri,
   Alexa, Google and motion recipes under Alerts › Webhooks. Loaded after
   app.js and uses its helpers (api, esc, busy, toast, confirmBox, $, clone,
   saveSettings, effLabel, role, isAdmin, autoPanel). */
'use strict';

const DT_MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const ordinal = n => n + (n % 100 >= 11 && n % 100 <= 13 ? 'th' : ['th', 'st', 'nd', 'rd'][n % 10] || 'th');
const leapYear = y => y % 4 === 0 && (y % 100 !== 0 || y % 400 === 0);

/* The next time a month-day comes (today counts), and how many years it makes. */
function nextOccurrence(mmdd, year, today = new Date()) {
  const [m, d] = mmdd.split('-').map(Number);
  const t0 = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  for (let y = today.getFullYear(); y <= today.getFullYear() + 1; y++) {
    const day = m === 2 && d === 29 && !leapYear(y) ? 28 : d;
    const when = new Date(y, m - 1, day);
    if (when >= t0) return { when, years: year ? y - year : null, days: Math.round((when - t0) / 864e5) };
  }
  return null;
}
/* Days from the date itself if its lights run tonight (-2: two days before; 0: the day), else null. */
function dtTonight(e, today = new Date()) {
  if (e.enabled === false || !e.date) return null;
  const [m, d] = e.date.split('-').map(Number), t0 = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  for (let y = today.getFullYear() - 1; y <= today.getFullYear() + 1; y++) {
    if (e.year && y < e.year) continue;
    const day = new Date(y, m - 1, m === 2 && d === 29 && !leapYear(y) ? 28 : d), k = Math.round((t0 - day) / 864e5);
    if (k >= -(e.before || 0) && k <= (e.after || 0)) return k;
  }
  return null;
}
function personalLabel(e) {
  const k = e.kind || 'birthday', n = e.name || '';
  if (k === 'other' || n.toLowerCase().includes(k)) return n;
  return k === 'birthday' ? `${n}'s birthday` : `${n} anniversary`;
}
function personalNext(e) {
  const nx = nextOccurrence(e.date, e.year); if (!nx) return '';
  const when = nx.days === 0 ? 'today' : nx.days === 1 ? 'tomorrow' : nx.when.toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' });
  const age = nx.years > 0 ? ((e.kind || 'birthday') === 'birthday' ? `turns ${nx.years}` : (e.kind === 'anniversary' ? `${ordinal(nx.years)} anniversary` : `${nx.years} years`)) : '';
  return [age, when].filter(Boolean).join(', ');
}

SUMS.dates = () => { const l = ((S.settings.dates || {}).list || []).filter(e => e.enabled !== false);
  if (!l.length) return 'None';
  const soon = l.map(e => ({ e, nx: nextOccurrence(e.date, e.year) })).filter(x => x.nx).sort((a, b) => a.nx.days - b.nx.days)[0];
  return `${plural(l.length, 'date')}${soon ? ` · next: ${personalLabel(soon.e)}, ${personalNext(soon.e)}` : ''}`; };
SUMS.people = () => { const p = (S.settings.presence || {}).people || []; return p.length ? plural(p.length, 'person').replace('persons', 'people') : 'Nobody added'; };

/* ---------------------------------------------------------------- birthdays and anniversaries */
function datesPanel(box) {
  const pc = S.settings.dates || { list: [] }, list = pc.list || [], ro = role() === 'viewer';
  const effs = Object.entries(S.settings.effects || {});
  const effSel = (id, cur) => `<select id="${id}">${effs.map(([k, e]) => `<option value="${esc(k)}" ${k === cur ? 'selected' : ''}>${esc(e.label || k)}</option>`).join('')}</select>`;
  const order = list.map((e, i) => ({ e, i, nx: nextOccurrence(e.date, e.year) })).sort((a, b) => (a.nx ? a.nx.days : 999) - (b.nx ? b.nx.days : 999));
  box.innerHTML = `<h2>Birthdays &amp; anniversaries</h2>
    <p class="note">Your own dates, every year without setting them up again: the lights show their patterns that night (and the days around it, if you like). They outrank holidays, so a Christmas birthday gets its own lights; game days still win. Kept on this computer only: never in a shared or exported file.</p>
    <div class="list">${order.length ? order.map(({ e, i }) => `<div class="item"><div class="grow">
        <div class="row" style="gap:8px">${ro ? '' : `<label class="check"><input type="checkbox" data-dton="${i}" ${e.enabled === false ? '' : 'checked'} aria-label="Show the lights for ${esc(personalLabel(e))}"></label>`}<span class="name">${esc(personalLabel(e))}</span>
          ${(k => k === null ? '' : `<span class="badge hi">${k === 0 ? 'Today' : 'Lights tonight'}</span>`)(dtTonight(e))}
          <span class="badge">${esc(DT_MONTHS[+e.date.slice(0, 2) - 1] + ' ' + +e.date.slice(3))}${e.year ? ', ' + e.year : ''}</span></div>
        <div class="sub">${esc(personalNext(e))} · ${esc((e.effects || []).map(effLabel).join(' / '))} · ${esc(humanT(e.on || 'sunset'))} → ${esc(humanT(e.off || '23:00'))}${e.before || e.after ? ` · ${e.before ? e.before + ' day(s) before' : ''}${e.before && e.after ? ', ' : ''}${e.after ? e.after + ' day(s) after' : ''}` : ''}</div></div>
        ${ro ? '' : `<button class="small ghost" data-dtedit="${i}">Edit</button><button class="small ghost danger" data-dtdel="${i}" aria-label="Delete ${esc(personalLabel(e))}">Delete</button>`}</div>`).join('')
      : '<p class="muted small">No dates yet.</p>'}</div>
    ${ro ? '' : '<div><button class="small" data-dtadd>Add a date</button></div>'}`;
  const save = (fn, msg) => { const n = clone(S.settings); n.dates = clone(n.dates || { list: [] }); n.dates.list = n.dates.list || []; fn(n.dates.list);
    return busy(null, () => saveSettings(n, msg)).then(() => { datesPanel(box); foldSums(); }).catch(() => datesPanel(box)); };
  const edit = idx => {
    const e = idx === null ? { name: '', kind: 'birthday', date: '', effects: [effs[0] ? effs[0][0] : ''], on: 'sunset', off: '23:00', before: 0, after: 0 } : clone(list[idx]);
    const [m, d] = (e.date || '-').split('-');
    const pats = (e.effects || []).filter(k => (S.settings.effects || {})[k]);
    dialog(`<h2>${idx === null ? 'Add a date' : 'Edit ' + esc(personalLabel(e))}</h2><div class="stack">
      <div class="row"><label class="field grow">Name<input type="text" id="dtname" maxlength="40" value="${esc(e.name)}" placeholder="e.g. Chris, or Our wedding"></label>
        <label class="field">It's a<select id="dtkind">${[['birthday', 'birthday'], ['anniversary', 'anniversary'], ['other', 'another date']].map(([v, l]) => `<option value="${v}" ${e.kind === v ? 'selected' : ''}>${l}</option>`).join('')}</select></label></div>
      <div class="row"><label class="field">Month<select id="dtm">${DT_MONTHS.map((x, k) => `<option value="${k + 1}" ${+m === k + 1 ? 'selected' : ''}>${x}</option>`).join('')}</select></label>
        <label class="field">Day<input type="number" id="dtd" min="1" max="31" value="${+d || ''}" style="width:5em"></label>
        <label class="field">Year <span class="hint">optional: for “turns 40”</span><input type="number" id="dty" min="1900" max="${new Date().getFullYear() + 1}" value="${e.year || ''}" style="width:7em"></label></div>
      <div class="stack" style="gap:6px"><b>Patterns</b> <span class="note">Up to 6, shown in turn.</span><div id="dtpats" class="stack" style="gap:6px"></div></div>
      <div class="row"><label class="field">From<input type="text" id="dton" value="${esc(e.on || 'sunset')}" style="width:9em"></label>
        <label class="field">Until<input type="text" id="dtoff" value="${esc(e.off || '23:00')}" style="width:9em"></label>
        <label class="field">Days before<input type="number" id="dtbefore" min="0" max="7" value="${e.before || 0}" style="width:5em"></label>
        <label class="field">Days after<input type="number" id="dtafter" min="0" max="7" value="${e.after || 0}" style="width:5em"></label></div>
      <p class="note">Times work like rules: sunset, sunset + 30, 18:00. February 29 shows on February 28 in other years.</p></div>`, async f => {
      const name = $('#dtname', f).value.trim(), day = +$('#dtd', f).value, mon = +$('#dtm', f).value, yr = $('#dty', f).value;
      if (!name) { toast('Give it a name.', true); return false; }
      if (!pats.length) { toast('Choose a pattern.', true); return false; }
      if (!(day >= 1 && day <= new Date(2024, mon, 0).getDate())) { toast('That month doesn’t have that day.', true); return false; }
      const out = { ...e, name, kind: $('#dtkind', f).value, date: `${String(mon).padStart(2, '0')}-${String(day).padStart(2, '0')}`,
        effects: pats.slice(), rotate: Math.max(1, Math.min(240, Math.round(+($('#dtrot', f) || {}).value || e.rotate || 15))),
        on: $('#dton', f).value.trim() || 'sunset', off: $('#dtoff', f).value.trim() || '23:00',
        before: Math.max(0, Math.min(7, +$('#dtbefore', f).value || 0)), after: Math.max(0, Math.min(7, +$('#dtafter', f).value || 0)) };
      if (yr) out.year = +yr; else delete out.year;
      await save(l => { if (idx === null) l.push(out); else l[idx] = out; }, idx === null ? 'Date added' : 'Saved');
    }, { ok: 'Save', onOpen: f => {
      // 4.18.2: several patterns in turn, and a preview on the lights
      const box2 = $('#dtpats', f);
      const draw = () => {
        box2.innerHTML = `${pats.map((k, i) => `<div class="row" style="gap:6px"><span class="grow">${i + 1}. ${esc(effLabel(k))}</span>
            <button type="button" class="small ghost" data-dtprev="${i}">Preview</button>
            ${i ? `<button type="button" class="small ghost" data-dtup="${i}" aria-label="Show ${esc(effLabel(k))} earlier">↑</button>` : ''}
            <button type="button" class="small ghost danger" data-dtrm="${i}" aria-label="Remove ${esc(effLabel(k))}">✕</button></div>`).join('')}
          ${pats.length < 6 ? `<select id="dtadd" style="width:auto;max-width:100%"><option value="">Add a pattern…</option>${effs.filter(([k]) => !pats.includes(k)).map(([k, x]) => `<option value="${esc(k)}">${esc(x.label || k)}</option>`).join('')}</select>` : ''}
          ${pats.length > 1 ? `<label class="row small" style="gap:6px">Each shows for<input type="number" id="dtrot" min="1" max="240" value="${e.rotate || 15}" style="width:5em">minutes</label>` : ''}`;
      };
      box2.addEventListener('change', ev => { if (ev.target.id === 'dtadd' && ev.target.value) { pats.push(ev.target.value); draw(); } });
      box2.addEventListener('change', ev => { if (ev.target.id === 'dtrot') e.rotate = +ev.target.value; });
      box2.addEventListener('click', ev => {
        const b = ev.target.closest('button'); if (!b) return; const ds = b.dataset;
        if (ds.dtrm !== undefined) { pats.splice(+ds.dtrm, 1); draw(); }
        if (ds.dtup !== undefined) { const i = +ds.dtup; [pats[i - 1], pats[i]] = [pats[i], pats[i - 1]]; draw(); }
        if (ds.dtprev !== undefined) { const k = pats[+ds.dtprev], def = { ...(S.settings.effects || {})[k] };
          busy(b, () => api('action', { body: { action: 'try', effect: def } })).then(() => toast(`Showing “${effLabel(k)}” for 15 minutes, then back to the schedule`)).catch(() => {}); }
      });
      draw();
    } });
  };
  box.onchange = e => { const t = e.target; if (t.dataset.dton !== undefined) save(l => { l[+t.dataset.dton].enabled = t.checked; }, t.checked ? 'On' : 'Off'); };
  box.onclick = async e => {
    const b = e.target.closest('button'); if (!b) return; const d = b.dataset;
    if (d.dtadd !== undefined) { if (!effs.length) return toast('Create a pattern first.', true); return edit(null); }
    if (d.dtedit !== undefined) return edit(+d.dtedit);
    if (d.dtdel !== undefined) {
      if (!await confirmBox('Delete this date?', esc(personalLabel(list[+d.dtdel])), 'Delete')) return;
      return save(l => l.splice(+d.dtdel, 1), 'Deleted');
    }
  };
}

/* ---------------------------------------------------------------- who's home */
function hookBase(a) { return `${a.scheme || 'http'}://${a.addresses && a.addresses[0] || 'THIS-PC'}:${a.port}`; }

async function presencePanel(box, admin) {
  let st; try { st = await api('presence'); } catch (e) { box.innerHTML = `<h2>Who’s home</h2><p class="muted small">${esc(e.message)}</p>`; return; }
  let a = null; if (admin) { try { a = S.account = await api('account'); } catch { /* recipes need the webhook */ } }
  const people = (S.settings.presence || {}).people || [], ro = role() === 'viewer';
  const since = t => t ? new Date(t * 1000).toLocaleString([], { weekday: 'short', hour: 'numeric', minute: '2-digit' }) : '';
  const who = people[0] || 'Chris';
  box.innerHTML = `<h2>Who’s home</h2>
    <p class="note">The people who live here, so automations can start when someone arrives or leaves (<b>Someone arrives home</b>, <b>Someone leaves home</b>) or check <b>Someone is home</b> / <b>Nobody is home</b>. Each phone tells this app itself, with a webhook from Shortcuts or Home Assistant; no location is sent or kept, only home or away.</p>
    <div class="list">${st.people.length ? st.people.map(p => `<div class="item"><div class="grow"><span class="name">${esc(p.name)}</span>
        <span class="pill ${p.state === 'home' ? 'ok' : ''}">${p.state === 'home' ? 'Home' : p.state === 'away' ? 'Away' : 'Not known yet'}</span>
        ${p.at ? `<div class="sub">since ${esc(since(p.at))}</div>` : ''}</div>
        ${ro ? '' : `<button class="small ghost" data-pset="${esc(p.name)}" data-state="${p.state === 'home' ? 'away' : 'home'}">Mark ${p.state === 'home' ? 'away' : 'home'}</button>
        <button class="small ghost danger" data-pdel="${esc(p.name)}" aria-label="Remove ${esc(p.name)}">Remove</button>`}</div>`).join('')
      : '<p class="muted small">Nobody added yet.</p>'}</div>
    <p class="small"><a href="#phone">Set up a phone</a>: one page that also does its certificate and home-screen icon.</p>
    ${ro ? '' : `<div class="row"><input type="text" id="pname" maxlength="30" placeholder="A name, e.g. Chris" style="max-width:16em"><button class="small" data-padd>Add</button></div>
      <label class="row small" style="gap:6px">A phone at the edge of the Wi-Fi can go home, away, home: after a change, ignore the next one for
        <input type="number" id="psettle" min="0" max="30" value="${(S.settings.presence || {}).settle_minutes ?? 2}" style="width:4.5em"> minutes</label>
      <p class="note">Ignored changes are still noted (Home › Activity) and Who’s home stays right; they just don’t start automations. 0: never ignore. Marking by hand is never ignored.</p>`}
    ${a ? (a.webhook_token ? `<details><summary>Set up an iPhone (Shortcuts)</summary><div class="stack" style="margin-top:8px">
      <ol class="small">
        <li>Open <b>Shortcuts</b> › <b>Automation</b> › <b>New Automation</b> › <b>Wi-Fi</b>. Choose your home network, <b>When Joining</b>, and <b>Run Immediately</b>. (Not <b>Arrive</b>: it runs down the street, before the phone is back on your Wi-Fi, so it can’t reach this app.)</li>
        <li>Add the action <b>Get Contents of URL</b>, with the address below. Tap <b>Show More</b>: Method <b>POST</b>; Headers: <b>X-Token</b> = the token below; Request Body <b>JSON</b>: <b>person</b> = ${esc(who)}, <b>state</b> = home.</li>
        <li>Make a second one with <b>Leave</b> (your home, <b>Run Immediately</b>) and <b>state</b> = away.</li></ol>
      <pre class="code">${esc(hookBase(a))}/api/hook/presence</pre>
      <div class="row"><input type="text" readonly id="prtok" value="${esc(a.webhook_token)}" style="max-width:22em" aria-label="Webhook token"><button type="button" class="small" data-prcopy>Copy token</button></div>
      <p class="note">When you leave, the phone is no longer on your home Wi-Fi, so it can only reach this app over a VPN (your router’s, or Tailscale; see Setup › Accounts & access › Away from home). Without a VPN, use Home Assistant’s companion app for leaving: its zones run at home, where this app is.</p></div></details>
      <details><summary>Set up with Home Assistant (iPhone or Android)</summary><pre class="code">rest_command:
  eaveluxos_presence:
    url: "${esc(hookBase(a))}/api/hook/presence"
    method: POST
    headers:
      X-Token: !secret eaveluxos_token
    content_type: "application/json"
    payload: '{"person": "{{ person }}", "state": "{{ state }}"}'

automation:
  - alias: ${esc(who)} home or away
    trigger:
      - platform: state
        entity_id: person.${esc(who.toLowerCase().replace(/[^a-z0-9]+/g, '_'))}
    action:
      - service: rest_command.eaveluxos_presence
        data:
          person: ${esc(who)}
          state: "{{ 'home' if trigger.to_state.state == 'home' else 'away' }}"</pre>
      <p class="note">Put the webhook token in Home Assistant’s <code>secrets.yaml</code> as <code>eaveluxos_token</code>.</p></details>`
      : '<p class="note">Turn on webhooks under Alerts › Webhooks to let phones say when someone arrives or leaves.</p>') : ''}`;
  box.onchange = e => {
    if (e.target.id !== 'psettle') return;
    const v = Math.max(0, Math.min(30, Math.round(+e.target.value || 0)));
    const n = clone(S.settings); n.presence = { ...(n.presence || { people: [] }), settle_minutes: v };
    busy(null, () => saveSettings(n, v ? `Changes within ${v} min are ignored` : 'No changes are ignored')).catch(() => presencePanel(box, admin));
  };
  const savePeople = (list, msg) => { const n = clone(S.settings); n.presence = { ...(n.presence || {}), people: list };
    return busy(null, () => saveSettings(n, msg)).then(() => { presencePanel(box, admin); foldSums();
      const ab = $('#autobox'); if (ab && ab.querySelector('[data-autotpl]')) autoPanel(ab); }).catch(() => {}); };   // the templates that need people
  box.onclick = async e => {
    const b = e.target.closest('button'); if (!b) return; const d = b.dataset;
    if (d.prcopy !== undefined) { const el = $('#prtok', box); el.select();
      return navigator.clipboard?.writeText ? navigator.clipboard.writeText(el.value).then(() => toast('Copied'), () => toast('Selected: copy it with Ctrl+C or ⌘C.')) : toast('Selected: copy it with Ctrl+C or ⌘C.'); }
    if (d.padd !== undefined) {
      const name = $('#pname', box).value.trim().replace(/\s+/g, ' ');
      if (!name) return toast('Type a name.', true);
      if (people.some(p => p.toLowerCase() === name.toLowerCase())) return toast(`${name} is already on the list.`, true);
      return savePeople([...people, name], `${name} added`);
    }
    if (d.pdel !== undefined) {
      const used = (S.settings.automations || []).filter(x => (x.when || {}).person === d.pdel).map(x => x.name);
      if (used.length) return toast(`First change the automation${used.length > 1 ? 's' : ''} for ${d.pdel}: ${used.join(', ')}.`, true);
      if (!await confirmBox(`Remove ${d.pdel}?`, 'Their phone’s arrivals and departures are then refused.', 'Remove')) return;
      return savePeople(people.filter(p => p !== d.pdel), 'Removed');
    }
    if (d.pset !== undefined) return busy(b, () => api('presence', { body: { person: d.pset, state: d.state } }))
      .then(r => { S.presenceSeen = null; toast(`${r.person}: ${r.state === 'home' ? 'home' : 'away'}${(r.automations || []).length ? ' · ' + r.automations.join(' ') : ''}`); presencePanel(box, admin); }).catch(() => {});
  };
}

/* ---------------------------------------------------------------- voice, buttons and motion (Alerts › Webhooks) */
function voicePanel(box, a) {
  const base = hookBase(a), first = Object.keys(S.settings.effects || {})[0] || 'warm_white';
  box.innerHTML = `<details><summary>Siri, Alexa and Google</summary><div class="stack" style="margin-top:8px">
      <p class="note"><b>Siri</b>: make a shortcut in the Shortcuts app with one action, <b>Get Contents of URL</b> (Method POST, header <b>X-Token</b> = the token, Request Body JSON). Name it what you’ll say, for example “Holiday lights on”, then say “Hey Siri, holiday lights on”. One shortcut each:</p>
      <table class="small"><tbody>
        <tr><td>Lights on with a pattern</td><td><code>${esc(base)}/api/hook/on</code> · <code>{"effect": "${esc(first)}"}</code></td></tr>
        <tr><td>Lights off</td><td><code>${esc(base)}/api/hook/off</code></td></tr>
        <tr><td>Back to the schedule</td><td><code>${esc(base)}/api/hook/resume</code></td></tr>
        <tr><td>Security flash</td><td><code>${esc(base)}/api/hook/flash</code> · <code>{"effect": "security"}</code></td></tr>
        <tr><td>Start an automation by name</td><td><code>${esc(base)}/api/hook/event</code> · <code>{"name": "movie night"}</code></td></tr>
      </tbody></table>
      <p class="note">The pattern names are the keys under Patterns (a webhook’s <code>status</code> reply lists them). Siri shortcuts work from the Lock Screen, CarPlay and an Apple Watch too, on the home network or over a VPN.</p>
      <p class="note"><b>Alexa and Google Assistant</b> go through Home Assistant: add the <code>rest_command</code> below, make a script for each phrase (for example <i>Holiday lights on</i> calling it with <code>action: on</code>), and expose the scripts under Settings › Voice assistants (Home Assistant Cloud, or the Alexa and Google integrations).</p>
      <pre class="code">rest_command:
  eaveluxos:
    url: "${esc(base)}/api/hook/{{ action }}"
    method: POST
    headers:
      X-Token: !secret eaveluxos_token
    content_type: "application/json"
    payload: "{{ body | default({}) | to_json }}"</pre></div></details>
    <details><summary>Motion: cameras and sensors</summary><div class="stack" style="margin-top:8px">
      <p class="note">A camera (Frigate, Blue Iris, UniFi Protect through Home Assistant) or a motion sensor sends a named event when it sees something, and an automation decides what the lights do: for example light up the driveway zone for a minute after dark, or flash red when nobody’s home. Under Alerts › Automations choose <b>Start from a template</b> › <b>Motion lights</b>, then point the camera at:</p>
      <pre class="code">curl -X POST -H "X-Token: …" -H "Content-Type: application/json" \\
  -d '{"name": "motion"}' ${esc(base)}/api/hook/event</pre>
      <p class="note">Use a different name for each camera (motion-driveway, motion-porch) to light a different zone for each. A cooldown keeps a busy camera from flashing again and again.</p></div></details>`;
}

/* ---------------------------------------------------------------- automation templates */
const firstZone = () => { const z = (typeof mapData === 'function' ? mapData().zones : []) || []; return z.length ? z[0].name : undefined; };
const AUTO_TEMPLATES = {
  motion: { label: 'Motion lights (a camera or sensor)', make: () => ({ name: 'Motion lights', priority: 200, cooldown: 90,
    when: { type: 'webhook', name: 'motion' }, if: [{ type: 'dark', from: 'sunset', to: 'sunrise' }],
    then: [{ type: 'flash', color: '#FFFFFF', seconds: 60, ...(firstZone() ? { zone: firstZone() } : {}) }] }) },
  welcome: { label: 'Welcome home', people: true, make: () => ({ name: 'Welcome home', cooldown: 300,
    when: { type: 'arrive', person: 'any', first: true }, if: [{ type: 'dark', from: 'sunset', to: 'sunrise' }],
    then: [{ type: 'flash', color: '#FFB347', seconds: 120 }] }) },
  intruder: { label: 'Motion while nobody’s home', people: true, make: () => ({ name: 'Motion while away', priority: 300, cooldown: 60, beats_manual: true,
    when: { type: 'webhook', name: 'motion' }, if: [{ type: 'nobody_home' }, { type: 'dark', from: 'sunset', to: 'sunrise' }],
    then: [{ type: 'flash', color: '#FF0000', seconds: 30 }] }) },
  doorbell: { label: 'Doorbell', make: () => ({ name: 'Doorbell', priority: 200, cooldown: 30,
    when: { type: 'webhook', name: 'doorbell' }, if: [], then: [{ type: 'flash', color: '#00A0FF', seconds: 20 }] }) },
  goodnight: { label: 'Everyone left: lights off for the night', people: true, make: () => ({ name: 'Everyone left', cooldown: 600,
    when: { type: 'leave', person: 'any', last: true }, if: [{ type: 'between', from: '23:00', to: 'sunrise' }],
    then: [{ type: 'off', minutes: 480 }] }) },
};

/* ---------------------------------------------------------------- Home: who's home (4.18.2) */
async function homeWho(el) {
  const people = (S.settings.presence || {}).people || [];
  if (!el || !people.length || role() === 'viewer') return;
  // Home redraws every few seconds: ask at most every 20 seconds (Review #2, 4.18.2)
  let st = S.presenceSeen && Date.now() - S.presenceSeen.at < 20000 ? S.presenceSeen.st : null;
  if (!st) { try { st = await api('presence'); } catch { return; } S.presenceSeen = { at: Date.now(), st }; }
  if (!document.body.contains(el)) return;
  const home = st.people.filter(p => p.state === 'home').map(p => p.name), away = st.people.filter(p => p.state === 'away').map(p => p.name);
  const unknown = st.people.filter(p => !p.state).map(p => p.name);
  el.innerHTML = `<span class="muted">Who’s home:</span> ${home.length ? `<b>${esc(home.join(' · '))}</b>` : 'nobody'}`
    + (away.length ? ` <span class="muted">· away: ${esc(away.join(', '))}</span>` : '')
    + (unknown.length ? ` <span class="muted">· not known yet: ${esc(unknown.join(', '))}</span>` : '')
    + ` <a href="#alerts" data-whojump class="small">Change</a>`;
  el.hidden = false;
  const a = $('[data-whojump]', el);
  if (a) a.onclick = e => { e.preventDefault(); try { localStorage.setItem('fold:people', '1'); } catch { /* fine */ } location.hash = '#alerts'; };
}

/* ---------------------------------------------------------------- Set up this phone (4.18.2)
   One page, in order: trust the certificate, put the icon on the home
   screen, and (if you like) tell the app when you come and go. On the app
   computer it shows a code to scan with the phone instead. */
VIEWS.phone = async () => {
  const m = $('#main');
  m.innerHTML = '<div class="view"><p class="muted">Loading…</p></div>';
  let p; try { p = await api('phone'); } catch (e) { m.innerHTML = `<div class="view"><p class="callout warn">${esc(e.message)}</p></div>`; return; }
  if (S.view !== 'phone') return;
  const host = location.hostname;
  const ip = p.addresses[0] || host, secure = location.protocol === 'https:' && window.isSecureContext;
  const android = /Android/i.test(navigator.userAgent), mobile = IOS || android;
  const step = (n, done, title, body) => `<div class="panel stack"><h2>${done ? '<span class="pill ok">Done</span> ' : `${n}. `}${title}</h2>${body}</div>`;
  if (!mobile) {                       // a computer: the code for the phone to scan
    const target = p.https && p.ca ? `http://${ip}:${p.port}/trust` : `${p.https ? 'https' : 'http'}://${ip}:${p.port}/#phone`;
    let qr = ''; try { qr = QR.svg(target, 'M', 6); } catch { /* the address below still works */ }
    m.innerHTML = `<div class="view stack"><div class="panel-head"><h2>Set up a phone or tablet</h2></div>
      <div class="panel stack"><p>On the phone or tablet, connect to your home Wi-Fi and point its camera at this code (or type the address). It walks through everything in order: trusting the app’s certificate, the home-screen icon, and who’s home.</p>
        <div class="qrbox" style="max-width:260px">${qr}</div><p><code>${esc(target)}</code></p>
        ${p.https ? (p.ca ? `<p class="note">The phone checks this fingerprint for the certificate it installs:<br><code style="word-break:break-all">${esc(p.ca_sha256)}</code></p>`
          : '<p class="callout warn small">HTTPS is on, but no mkcert root certificate was found to give phones. Run <code>mkcert -CAROOT</code> and copy <b>rootCA.pem</b> (never rootCA-key.pem) into EaveLuxOS’s <code>tls</code> folder.</p>')
          : '<p class="note">HTTPS isn’t on, so phones skip the certificate. It’s worth turning on: Manual, section 8, step 2 (mkcert).</p>'}</div></div>`;
    return;
  }
  const how = IOS ? 'Tap <b>Share</b> (on an iPad at the top right; in newer iOS the <b>⋯</b> button first), then <b>Add to Home Screen</b>, and <b>Add</b>.'
    : 'Tap the <b>⋮</b> menu, then <b>Install app</b> (or <b>Add to Home screen</b>, then <b>Install</b>).';
  const certBody = secure ? '<p>This connection is secure: the certificate is trusted.</p>'
    : !p.https ? '<p>HTTPS isn’t on for this app, so there’s nothing to trust; go on to step 2. (An Administrator can turn it on: Manual, section 8.)</p>'
    : !p.ca ? '<p class="callout warn small">The app computer has no certificate to give phones yet. Ask an Administrator to copy mkcert’s <b>rootCA.pem</b> into EaveLuxOS’s <code>tls</code> folder.</p>'
    : `<p><a class="btn primary" href="/ca.crt" download="EaveLuxOS-root.crt">Download the certificate</a></p>
       ${IOS ? `<ol class="small"><li>Tap <b>Allow</b>: it says <b>Profile Downloaded</b>.</li><li>Open the <b>Settings</b> app: <b>General</b>, <b>VPN &amp; Device Management</b>, the <b>mkcert</b> profile, <b>Install</b>.</li><li>Then <b>General</b>, <b>About</b>, <b>Certificate Trust Settings</b>: turn on <b>mkcert</b>.</li></ol>`
         : `<ol class="small"><li>Open the <b>Settings</b> app and search for <b>CA certificate</b>.</li><li>Tap it, <b>Install anyway</b>, and choose <b>EaveLuxOS-root.crt</b> from Downloads.</li></ol>`}
       <p class="note">Fingerprint (SHA-256), as on the app computer: <code style="word-break:break-all">${esc(p.ca_sha256)}</code></p>
       <p><a class="btn" href="https://${esc(host)}:${p.port}/#phone">Then open the secure address</a></p>`;
  const installBody = standalone() ? '<p>You’re using the installed app.</p>'
    : `${typeof INSTALL !== 'undefined' && INSTALL ? '<p><button class="primary" data-pwainstall>Install EaveLuxOS</button></p>' : `<p>${how}</p>`}
       ${!secure && android ? '<p class="note">Without the secure address, Android adds a plain shortcut instead of the app. Step 1 fixes that.</p>' : ''}`;
  const me = (() => { try { return localStorage.getItem('elx-me') || ''; } catch { return ''; } })();
  const canSet = role() !== 'viewer';
  const whoBody = !p.people.length ? '<p class="note">Optional: under <b>Alerts › Who’s home</b>, add the people who live here, and the lights can welcome you home.</p>'
    : `<label class="field">This phone is<select id="phme" style="width:auto"><option value="">Choose…</option>${p.people.map(n => `<option ${n === me ? 'selected' : ''}>${esc(n)}</option>`).join('')}</select></label>
       ${canSet ? '<div class="row"><button class="small" data-phset="home">I’m home</button><button class="small ghost" data-phset="away">I’m away</button></div>' : ''}
       <details><summary>Tell the app automatically when you come and go</summary><div class="stack" style="margin-top:8px">
       ${IOS ? `<ol class="small"><li>Open <b>Shortcuts</b> › <b>Automation</b> › <b>New Automation</b> › <b>Wi-Fi</b>: your home network, <b>When Joining</b>, <b>Run Immediately</b>.</li>
           <li>Action <b>Get Contents of URL</b>: <code>https://${esc(ip)}:${p.port}/api/hook/presence</code>; <b>Show More</b>: Method <b>POST</b>, header <b>X-Token</b> = the webhook token, Request Body <b>JSON</b>: <b>person</b> = <span data-phname>${esc(me || 'your name')}</span>, <b>state</b> = home.</li>
           <li>A second automation with <b>Leave</b> (your home) and <b>state</b> = away. Leaving reaches the app only over your home VPN.</li></ol>`
         : '<p class="small">Android has no built-in way; use the Home Assistant companion app (Alerts › Who’s home has the setup to copy), or Tasker.</p>'}
       <div id="phtok"></div></div></details>`;
  m.innerHTML = `<div class="view stack"><div class="panel-head"><h2>Set up this ${/iPad|Tablet/i.test(navigator.userAgent) || (IOS && navigator.maxTouchPoints > 1 && !/iPhone/.test(navigator.userAgent)) ? 'tablet' : 'phone'}</h2></div>
    ${step(1, secure, 'Trust the app’s certificate', certBody)}
    ${step(2, standalone(), 'Put EaveLuxOS on the home screen', installBody)}
    ${step(3, false, 'Who’s home (optional)', whoBody)}</div>`;
  if (isAdmin()) api('account').then(a => { const t = $('#phtok'); if (t && a.webhook_token) t.innerHTML = `<div class="row"><input type="text" readonly id="phtokv" value="${esc(a.webhook_token)}" aria-label="Webhook token"><button type="button" class="small" data-phcopy>Copy token</button></div>`;
    else if (t) t.innerHTML = '<p class="note">Turn on webhooks first: Alerts › Webhooks.</p>'; }).catch(() => {});
  else { const t = $('#phtok'); if (t) t.innerHTML = '<p class="note">The webhook token is under Alerts › Webhooks; ask an Administrator for it.</p>'; }
  m.onchange = e => { if (e.target.id === 'phme') { try { localStorage.setItem('elx-me', e.target.value); } catch { /* fine */ } $$('[data-phname]', m).forEach(x => { x.textContent = e.target.value || 'your name'; }); } };
  m.onclick = e => {
    const b = e.target.closest('button'); if (!b) return;
    if (b.dataset.pwainstall !== undefined && typeof pwaInstall === 'function') return pwaInstall();
    if (b.dataset.phcopy !== undefined) { const el = $('#phtokv'); el.select(); return navigator.clipboard?.writeText ? navigator.clipboard.writeText(el.value).then(() => toast('Copied'), () => toast('Selected: copy it.')) : toast('Selected: copy it.'); }
    if (b.dataset.phset) { const who = $('#phme').value; if (!who) return toast('Choose who this phone is.', true);
      return busy(b, () => api('presence', { body: { person: who, state: b.dataset.phset } })).then(r => { S.presenceSeen = null; return r; }).then(r => toast(`${r.person}: ${r.state}`)).catch(() => {}); }
  };
};

/* ---------------------------------------------------------------- Schedule › Fades between patterns (4.19) */
SUMS.fades = () => { const v = (S.settings.transitions || {}).fade_seconds || 0; return v ? `${v} seconds` : 'Off'; };
function fadePanel(box) {
  if (!box) return;
  const v = (S.settings.transitions || {}).fade_seconds || 0, ro = role() === 'viewer';
  const lan = !!(S.settings.lan || {}).commands;
  box.innerHTML = `<h2>Fades between patterns</h2>
    <p class="note">When the schedule changes the pattern, the lights blend from the old colors to the new ones instead of jumping, and fade in and out when the schedule turns them on and off. A pattern you choose, a flash or a restore after a power cut still changes at once.</p>
    <label class="field">Fade<select id="fadesec" style="width:auto" ${ro ? 'disabled' : ''}>${[[0, 'Off'], [2, '2 seconds'], [3, '3 seconds'], [5, '5 seconds'], [8, '8 seconds']].map(([s, l]) => `<option value="${s}" ${s === v ? 'selected' : ''}>${l}</option>`).join('')}</select></label>
    ${ro ? '' : `<div class="row"><select id="fadetry" style="width:auto;max-width:100%" aria-label="Pattern to fade to">${Object.entries(S.settings.effects || {}).filter(([, e]) => Array.isArray(e.colors)).map(([k, e]) => `<option value="${esc(k)}">${esc(e.label || k)}</option>`).join('')}</select>
      <button class="small" data-fadetry>Try it</button></div><p class="note small">Fades from what’s showing to that pattern, which then shows for 15 minutes.</p>`}
    <p class="note">Fades go over the home network (Setup › Local mode, with commands on), and only your own patterns fade: a built-in effect or a pattern saved on the controller has colors only the controller knows, so it changes at once. The cloud never gets a fade.${lan ? '' : ' <b>Local mode commands look off on this app.</b>'}</p>`;
  box.onclick = e => {
    const b = e.target.closest('[data-fadetry]'); if (!b) return;
    const k = $('#fadetry', box).value; if (!k) return toast('Choose a pattern.', true);
    busy(b, () => api('fade/try', { body: { effect: k, seconds: +$('#fadesec', box).value || 3 } }))
      .then(() => toast(`Faded to “${effLabel(k)}” (15 minutes, then back to the schedule)`)).catch(() => {});
  };
  box.onchange = e => {
    if (e.target.id !== 'fadesec') return;
    const n = clone(S.settings), s = +e.target.value;
    n.transitions = { ...(n.transitions || {}), fade_seconds: s };
    busy(null, () => saveSettings(n, s ? `Fades of ${s} seconds` : 'Fades off')).then(foldSums).catch(() => fadePanel(box));
  };
}

/* ---------------------------------------------------------------- energy estimates (4.21), in Lights usage */
async function energyPanel(box) {
  if (!box) return;
  let r; try { r = await api('energy'); } catch (e) { box.innerHTML = `<p class="muted small">${esc(e.message)}</p>`; return; }
  const u = S.settings.usage || {}, ro = role() === 'viewer';
  const money = v => v == null ? '' : `, about <b>$${v.toFixed(2)}</b>`;
  box.innerHTML = `<h3 style="margin:8px 0 0">Estimated from your patterns</h3>
    ${r.bulbs ? `<p>${r.on ? `Now: about <b>${r.now_watts} W</b>. ` : ''}The next 30 nights on the schedule: <b>${r.month.hours} hours</b>, about <b>${r.month.kwh} kWh</b>${money(r.month.cost)}.</p>
      ${r.hungriest.length ? `<p class="small muted">Your brightest patterns: ${r.hungriest.map(h => `${esc(h.label)} ${h.watts} W`).join(' · ')}</p>` : ''}`
      : '<p class="small">Enter how many bulbs you have to see estimates.</p>'}
    <details><summary class="small">How it’s estimated</summary><div class="stack" style="margin-top:8px">
      <p class="note">Each bulb draws about in proportion to how brightly its red, green and blue are lit: full white the most, one deep color about a third, a dark bulb almost nothing. So: bulbs × watts of one bulb at full white × the pattern’s brightness × its colors, plus about 3 W for the controller. Weather, flashes and choices made by hand aren’t known ahead. A built-in effect counts as half of white.</p>
      <div class="row"><label class="field">Bulbs<input type="number" id="enbulbs" min="0" max="10000" value="${u.bulbs ?? (r.bulbs || '')}" ${ro ? 'disabled' : ''} style="width:7em"></label>
        <label class="field">Watts for one bulb at full white<input type="number" id="enwpb" min="0" max="5" step="0.01" value="${u.watts_per_bulb ?? r.watts_per_bulb}" ${ro ? 'disabled' : ''} style="width:7em"></label></div>
      ${ro ? '' : '<div><button class="small ghost" data-ensave>Save</button></div>'}</div></details>`;
  box.onclick = e => {
    const b = e.target.closest('[data-ensave]'); if (!b) return;
    e.stopPropagation();
    const n = clone(S.settings), v = id => { const x = $(id, box).value.trim(); return x === '' ? null : Number(x); };
    n.usage = { ...(n.usage || {}), bulbs: v('#enbulbs'), watts_per_bulb: v('#enwpb') };
    Object.keys(n.usage).forEach(k => { if (n.usage[k] === null) delete n.usage[k]; });
    busy(b, () => saveSettings(n, 'Saved')).then(() => energyPanel(box)).catch(() => {});
  };
}

/* ---------------------------------------------------------------- sharing shows and automations (4.21) */
function codeDialog(title, r, how) {
  let qr = '';
  try { qr = r.code.length <= 1800 ? QR.svg(r.code, r.code.length > 900 ? 'L' : 'M', 4) : ''; } catch { qr = ''; }
  dialog(`<h2>${esc(title)}</h2><p class="note">${how}</p>
    <textarea id="sharecode" readonly rows="4" style="width:100%;font-family:ui-monospace,monospace;font-size:12px">${esc(r.code)}</textarea>
    <div class="row"><button type="button" class="small" data-sccopy>Copy the code</button>${navigator.share ? '<button type="button" class="small ghost" data-scsend>Send…</button>' : ''}<span class="small muted">${r.length} characters</span></div>
    ${qr ? `<div class="qrbox" style="text-align:center;background:#fff;padding:8px;border-radius:8px">${qr}</div>` : '<p class="note">Too long for a QR code; send the code itself.</p>'}`, null);
  $('#dlg form').addEventListener('click', e => {
    const b = e.target.closest('button'); if (!b) return;
    if (b.dataset.sccopy !== undefined) { const el = $('#sharecode'); el.select(); (navigator.clipboard?.writeText ? navigator.clipboard.writeText(el.value) : Promise.reject()).then(() => toast('Copied'), () => toast('Selected: copy it with Ctrl+C or ⌘C.')); }
    if (b.dataset.scsend !== undefined) navigator.share({ title, text: r.code }).catch(() => {});
  });
}
/* What a shared show or automation holds, before anything is added. */
function sharedPreview(r) {
  if (r.kind === 'show') {
    const s = r.show;
    return `<p><b>A Studio show: “${esc(s.name)}”</b>, ${plural(s.keyframes.length, 'look')}${s.fade ? `, fading ${s.fade} s` : ''}:</p>
      ${s.keyframes.map(k => `<div class="small"><b>${esc(k.pattern.label)}</b>, ${k.minutes} min ${strand(k.pattern.colors, k.pattern.counts)}</div>`).join('')}
      <p class="note">It opens in Studio, to play on your lights and approve. Nothing is added until you do.</p>`;
  }
  const a = r.automation, lbl = k => /^@\d$/.test(k || '') ? (r.patterns[+k.slice(1)] || {}).label || k : k;
  const shown = { ...a, then: (a.then || []).map(x => x.effect ? { ...x, effect: lbl(x.effect) } : x), if: (a.if || []).map(c => c.effect ? { ...c, effect: lbl(c.effect) } : c) };
  return `<p><b>An automation: “${esc(a.name)}”</b></p><p class="small">${esc(autoDescribe(shown))}</p>
    ${r.patterns.length ? `<p class="small">With ${plural(r.patterns.length, 'pattern')}: ${r.patterns.map(p => `<b>${esc(p.label)}</b> ${p.colors ? strand(p.colors, p.counts) : ''}`).join(' ')}</p>` : ''}
    <p class="note">The patterns become yours, and the automation is added <b>turned off</b>, to check (and point at your own teams, people or zones) before you turn it on.</p>`;
}
