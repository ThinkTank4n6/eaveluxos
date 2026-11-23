/* SPDX-License-Identifier: MIT
   Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)

   Studio (4.20): the advanced effect editor. A show is keyframes in order
   (a timeline), each a look built from layers (a base color or gradient,
   accents and bands) or described in words; play it on the lights, then
   approve it into your patterns and the schedule. The work is studio.py;
   this is the screen. Loaded after app.js and uses its helpers. */
'use strict';

const STUDIO_KEY = 'elx-studio';
const ST = { show: null };
const stMotions = () => (S.catalog && S.catalog.custom_modes) || ['Static'];
const stLoad = () => { try { return JSON.parse(localStorage.getItem(STUDIO_KEY) || 'null'); } catch { return null; } };
const stSave = () => { try { localStorage.setItem(STUDIO_KEY, JSON.stringify(ST.show)); } catch { /* fine */ } };
const stBlank = () => ({ name: '', fade: 3, keyframes: [] });
const stMinutes = s => s.keyframes.reduce((a, k) => a + (k.minutes || 0), 0);

VIEWS.studio = async () => {
  const m = $('#main');
  if (!S.catalog) { try { S.catalog = await api('catalog'); } catch { /* motions fall back */ } }
  ST.show = ST.show || stLoad() || stBlank();
  const ro = role() === 'viewer';
  const s = ST.show;
  const kf = (k, i) => `<div class="item studiokf" data-kf="${i}"><div class="grow">
      <div class="row" style="gap:8px"><b>${i + 1}.</b><span class="name">${esc(k.pattern.label)}</span>
        <span class="badge">${esc(stMotions()[k.pattern.custom_mode] || '')}</span></div>
      ${strand(k.pattern.colors, k.pattern.counts)}
      <label class="row small" style="gap:6px;margin-top:4px">for<input type="number" min="1" max="240" value="${k.minutes}" data-kfmin="${i}" style="width:5em" aria-label="Minutes for keyframe ${i + 1}">minutes</label></div>
    ${ro ? '' : `<div class="row" style="gap:4px;flex-wrap:wrap">${i ? `<button class="small ghost" data-kfup="${i}" aria-label="Earlier">↑</button>` : ''}
      <button class="small ghost" data-kfedit="${i}">Layers</button>${s.keyframes.length < 12 ? `<button class="small ghost" data-kfdup="${i}" aria-label="Copy keyframe ${i + 1}">Copy</button>` : ''}<button class="small ghost danger" data-kfdel="${i}" aria-label="Remove keyframe ${i + 1}">✕</button></div>`}</div>`;
  m.innerHTML = `<div class="view stack">
    <div class="panel-head"><h2>Studio</h2><div class="row" style="gap:6px">${ro ? '' : '<button class="ghost small" data-stopen>Open a share code</button>'}<button class="ghost small" data-tabjump="patterns">Back to Patterns</button></div></div>
    <p class="note">Build a show: looks in order, each for some minutes, fading from one to the next. Build each look from layers (a color or a gradient, then accents and bands on top), or describe the whole show in words. Play it on the lights, then approve it: the looks become your patterns, and the show can go on tonight’s schedule.</p>
    ${ro ? '' : `<div class="panel stack"><h3 style="margin:0">Describe it</h3>
      <div class="row"><input type="text" id="stwords" maxlength="400" class="grow" style="flex:1;min-width:200px" placeholder="e.g. warm white for 30 minutes, then fade to candy cane twinkle, then deep blue"><button data-stwords>Lay it out</button></div>
      <p class="note small" id="stwhy"></p></div>`}
    <div class="panel stack"><div class="panel-head"><h3 style="margin:0">Timeline</h3><span class="muted small">${s.keyframes.length ? `${plural(s.keyframes.length, 'keyframe')} · ${stMinutes(s)} minutes` : ''}</span></div>
      ${s.keyframes.length ? `<div class="stline" aria-hidden="true">${s.keyframes.map(k => `<span style="flex-grow:${k.minutes};background:linear-gradient(90deg,${k.pattern.colors.slice(0, 8).map(esc).join(',')}${k.pattern.colors.length === 1 ? ',' + esc(k.pattern.colors[0]) : ''})" title="${esc(k.pattern.label)}"></span>`).join('')}</div>` : ''}
      <div class="list">${s.keyframes.map(kf).join('') || '<p class="muted small">No keyframes yet: describe a show above, or add a look.</p>'}</div>
      ${ro ? '' : `<div class="row" style="flex-wrap:wrap">${s.keyframes.length < 12 ? `<button class="small" data-kfnew>Add a look (layers)</button>
        <select id="stfrom" style="width:auto;max-width:100%"><option value="">Add one of your patterns…</option>${Object.entries(S.settings.effects || {}).filter(([, e]) => Array.isArray(e.colors)).map(([k, e]) => `<option value="${esc(k)}">${esc(e.label || k)}</option>`).join('')}</select>` : ''}
        <label class="row small" style="gap:6px">Fade between<select id="stfade" style="width:auto">${[0, 2, 3, 5, 8].map(v => `<option value="${v}" ${v === s.fade ? 'selected' : ''}>${v ? v + ' s' : 'none'}</option>`).join('')}</select></label></div>`}
    </div>
    ${ro || !s.keyframes.length ? '' : `<div class="panel stack"><h3 style="margin:0">Play and approve</h3>
      <div class="row" style="flex-wrap:wrap"><label class="row small" style="gap:6px">Each look for<select id="sthold" style="width:auto">${[3, 5, 10, 20].map(v => `<option value="${v}" ${v === 5 ? 'selected' : ''}>${v} seconds</option>`).join('')}</select></label>
        <button data-stplay>Play on the lights</button><button class="ghost" data-ststop>Stop</button><span class="small" id="stplaying" aria-live="polite"></span></div>
      <p class="note small">Plays the show once, quickly (the real minutes are for the schedule), then the last look stays for 10 minutes. Any button ends it. Fades need Local mode.</p>
      <label class="field">Name<input type="text" id="stname" maxlength="40" value="${esc(s.name)}" placeholder="e.g. Christmas Eve"></label>
      <label class="check stsched"><input type="checkbox" id="stsched" checked> Put it on the schedule: every night from <input type="text" id="ston" value="sunset" style="width:7em" aria-label="From"> to <input type="text" id="stoff" value="23:00" style="width:6em" aria-label="Until">, the looks in turn</label>
      <div class="row"><button class="primary" data-stsave>Approve and save</button><button class="ghost" data-stshare>Share</button><button class="ghost danger" data-stclear>Start over</button></div></div>`}
  </div>`;
  const redraw = () => { stSave(); VIEWS.studio(); };
  m.onchange = e => {
    const t = e.target;
    if (t.dataset.kfmin !== undefined) { s.keyframes[+t.dataset.kfmin].minutes = Math.max(1, Math.min(240, Math.round(+t.value || 1))); return redraw(); }
    if (t.id === 'stfade') { s.fade = +t.value; return stSave(); }
    if (t.id === 'stname') { s.name = t.value.trim(); return stSave(); }
    if (t.id === 'stfrom' && t.value) {
      const e2 = S.settings.effects[t.value];
      s.keyframes.push({ minutes: 10, pattern: { label: e2.label || t.value, colors: e2.colors.filter(c => c !== 'off'), counts: (e2.counts || []).filter((n, i) => e2.colors[i] !== 'off'),
        custom_mode: e2.custom_mode || 0, speed: e2.speed ?? 100, brightness: e2.brightness ?? 200 } });
      return redraw();
    }
  };
  m.onclick = async e => {
    const b = e.target.closest('button'); if (!b) return; const d = b.dataset;
    if (d.tabjump) return go(d.tabjump);
    if (d.stopen !== undefined) return openShareDialog();
    if (d.stwords !== undefined) {
      return busy(b, () => api('studio/describe', { body: { text: $('#stwords').value } })).then(r => {
        ST.show = { name: r.name, fade: r.fade, keyframes: r.keyframes }; stSave(); VIEWS.studio().then(() => { const w = $('#stwhy'); if (w) w.textContent = r.why; });
      }).catch(() => {});
    }
    if (d.kfnew !== undefined) return layerDialog(null);
    if (d.kfedit !== undefined) return layerDialog(+d.kfedit);
    if (d.kfdel !== undefined) { s.keyframes.splice(+d.kfdel, 1); return redraw(); }
    if (d.kfdup !== undefined) { const i = +d.kfdup; s.keyframes.splice(i + 1, 0, clone(s.keyframes[i])); return redraw(); }
    if (d.kfup !== undefined) { const i = +d.kfup; [s.keyframes[i - 1], s.keyframes[i]] = [s.keyframes[i], s.keyframes[i - 1]]; return redraw(); }
    if (d.stplay !== undefined) return busy(b, () => api('studio/play', { body: { show: s, hold: +$('#sthold').value } })).then(r => { toast(`Playing ${plural(r.steps, 'look')} on the lights`); stWatch(); }).catch(() => {});
    if (d.ststop !== undefined) return busy(b, () => api('studio/stop', { body: {} })).then(() => toast('Stopped: back to the schedule')).catch(() => {});
    if (d.stshare !== undefined) { s.name = ($('#stname') || {}).value?.trim() || s.name;      // 4.21
      return busy(b, () => api('share/show', { body: { show: s } })).then(r => codeDialog(`Share “${r.labels[0]}”`, r, 'The other person taps <b>Open a share code</b> (Patterns or Studio) and pastes it; the show opens in their Studio to play and approve. Only the looks and their minutes are in it.')).catch(() => {}); }
    if (d.stclear !== undefined) { if (!await confirmBox('Start over?', 'The timeline is cleared (nothing saved is touched).', 'Start over', true)) return; ST.show = stBlank(); return redraw(); }
    if (d.stsave !== undefined) {
      s.name = $('#stname').value.trim();
      return busy(b, () => api('studio/save', { body: { show: s, schedule: $('#stsched').checked, on: $('#ston').value.trim(), off: $('#stoff').value.trim() } })).then(async r => {
        S.settings = await api('settings');
        toast(`Saved ${plural(r.patterns.length, 'pattern')}${r.rule ? `, and “${r.rule}” on the schedule` : ''}${r.fade ? `; fades of ${r.fade} s turned on` : ''}`);
      }).catch(() => {});
    }
  };
};

/* While a show plays: "Look 2 of 3" next to Play (4.20 review). */
function stWatch() {
  clearInterval(ST.watch);
  const tick = () => api('studio/state').then(r => {
    const el = $('#stplaying');
    if (!el || S.view !== 'studio') return clearInterval(ST.watch);
    const p = r.playing;
    el.textContent = p ? `Look ${p.step} of ${p.steps}` : 'Done: the last look stays for 10 minutes.';
    if (!p) clearInterval(ST.watch);
  }).catch(() => clearInterval(ST.watch));
  ST.watch = setInterval(tick, 1000); tick();
}

/* A look from layers: a base (one color or a gradient), then accents and bands. */
function layerDialog(idx) {
  const s = ST.show;
  const src = idx === null ? null : s.keyframes[idx];
  const L = clone((src && src.spec) || { label: src ? src.pattern.label : 'New look', length: 30, base: { type: 'gradient', stops: (src ? src.pattern.colors.slice(0, 3) : ['#FF0000', '#FFFFFF']) },
    layers: [], motion: stMotions()[src ? src.pattern.custom_mode : 0] || 'Static', speed: src ? src.pattern.speed : 100, brightness: src ? src.pattern.brightness : 200 });
  const stops = () => L.base.type === 'gradient' ? L.base.stops : [L.base.color];
  const body = () => `<label class="field">Name<input type="text" data-l="label" maxlength="40" value="${esc(L.label)}"></label>
    <div class="row" style="flex-wrap:wrap"><label class="field">Base<select data-l="base.type" style="width:auto"><option value="solid" ${L.base.type === 'solid' ? 'selected' : ''}>One color</option><option value="gradient" ${L.base.type === 'gradient' ? 'selected' : ''}>Gradient</option></select></label>
      <label class="field">Bulbs in one repeat<input type="number" data-l="length" min="2" max="300" value="${L.length}" style="width:6em"></label></div>
    <div class="row" style="gap:6px;flex-wrap:wrap">${stops().map((c, i) => `<input type="color" data-stop="${i}" value="${esc(c)}" aria-label="Color ${i + 1}">`).join('')}
      ${L.base.type === 'gradient' && L.base.stops.length < 6 ? '<button type="button" class="small ghost" data-addstop>+ color</button>' : ''}
      ${L.base.type === 'gradient' && L.base.stops.length > 1 ? '<button type="button" class="small ghost" data-rmstop>− color</button>' : ''}
      ${L.base.type === 'gradient' ? `<label class="check small"><input type="checkbox" data-l="base.mirror" ${L.base.mirror ? 'checked' : ''}> there and back</label>` : ''}</div>
    <div class="stack" style="gap:6px"><b>Layers on top</b>${L.layers.map((ly, i) => `<div class="row small" style="gap:6px;flex-wrap:wrap">
        <select data-ly="${i}.type" style="width:auto"><option value="accent" ${ly.type === 'accent' ? 'selected' : ''}>Accent</option><option value="band" ${ly.type === 'band' ? 'selected' : ''}>Band</option></select>
        <input type="color" data-ly="${i}.color" value="${esc(ly.color)}" aria-label="Layer color">
        ${ly.type === 'accent' ? `every<input type="number" data-ly="${i}.every" min="2" max="300" value="${ly.every}" style="width:4.5em">bulbs, <input type="number" data-ly="${i}.width" min="1" max="299" value="${ly.width}" style="width:4em"> lit`
          : `from bulb<input type="number" data-ly="${i}.start" min="1" max="300" value="${ly.start + 1}" style="width:4.5em">, <input type="number" data-ly="${i}.width" min="1" max="300" value="${ly.width}" style="width:4em"> wide`}
        <button type="button" class="small ghost danger" data-rmly="${i}" aria-label="Remove layer">✕</button></div>`).join('')}
      ${L.layers.length < 4 ? '<div><button type="button" class="small ghost" data-addly>Add a layer</button></div>' : ''}</div>
    <div class="row" style="flex-wrap:wrap"><label class="field">Motion<select data-l="motion" style="width:auto">${stMotions().map(x => `<option ${x === L.motion ? 'selected' : ''}>${esc(x)}</option>`).join('')}</select></label>
      <label class="field">Speed<input type="range" data-l="speed" min="0" max="255" value="${L.speed}"></label>
      <label class="field">Brightness<input type="range" data-l="brightness" min="1" max="255" value="${L.brightness}"></label></div>
    <div data-lprev><p class="muted small">…</p></div>`;
  let last = null, timer = null;
  const preview = f => { clearTimeout(timer); timer = setTimeout(() => api('studio/compose', { body: { spec: L } }).then(p => {
    last = p; const el = $('[data-lprev]', f); if (el) el.innerHTML = `${strand(p.bulbs)}<p class="note small">${p.colors.length} of the controller’s 30 colors${p.colors.length === 30 ? ' (in-between shades of a long gradient are merged)' : ''}.</p>`;
  }).catch(err => { last = null; const el = $('[data-lprev]', f); if (el) el.innerHTML = `<p class="callout warn small">${esc(err.message)}</p>`; }), 150); };
  dialog(`<h2>${src ? 'Layers' : 'Add a look'}</h2><div data-lform class="stack">${body()}</div>`, async () => {
    const p = last || await api('studio/compose', { body: { spec: L } });
    const pattern = { label: p.label, colors: p.colors, counts: p.counts, custom_mode: p.custom_mode, speed: p.speed, brightness: p.brightness };
    if (idx === null) s.keyframes.push({ minutes: 10, pattern, spec: clone(L) }); else s.keyframes[idx] = { ...s.keyframes[idx], pattern, spec: clone(L) };
    stSave(); VIEWS.studio();
  }, { ok: 'Use it', onOpen: f => {
    const form = $('[data-lform]', f);
    const redraw = () => { form.innerHTML = body(); preview(f); };
    form.addEventListener('input', e => {
      const t = e.target, k = t.dataset.l, ly = t.dataset.ly, st = t.dataset.stop;
      if (k === 'base.type') { L.base = t.value === 'solid' ? { type: 'solid', color: stops()[0] } : { type: 'gradient', stops: [stops()[0], '#FFFFFF'] }; return redraw(); }
      if (k === 'base.mirror') L.base.mirror = t.checked;
      else if (k) L[k] = ['length', 'speed', 'brightness'].includes(k) ? Math.round(+t.value) : t.value;
      if (st !== undefined) { if (L.base.type === 'gradient') L.base.stops[+st] = t.value.toUpperCase(); else L.base.color = t.value.toUpperCase(); }
      if (ly) { const [i, f2] = ly.split('.'); const v = f2 === 'color' || f2 === 'type' ? t.value : Math.round(+t.value); L.layers[+i][f2] = f2 === 'start' ? v - 1 : f2 === 'color' ? v.toUpperCase() : v; if (f2 === 'type') return redraw(); }
      preview(f);
    });
    form.addEventListener('click', e => {
      const b = e.target.closest('button'); if (!b) return; const d = b.dataset;
      if (d.addstop !== undefined) L.base.stops.push('#FFFFFF');
      else if (d.rmstop !== undefined) L.base.stops.pop();
      else if (d.addly !== undefined) L.layers.push({ type: 'accent', color: '#FFFFFF', every: 6, width: 1 });
      else if (d.rmly !== undefined) L.layers.splice(+d.rmly, 1);
      else return;
      redraw();
    });
    preview(f);
  } });
}
