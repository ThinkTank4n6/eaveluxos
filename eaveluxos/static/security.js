/* SPDX-License-Identifier: MIT
   Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)

   Local-first and security (4.17): API tokens, the audit log, encrypted
   backups and the away-from-home check, on Setup › Accounts & access and
   Setup › App. Loaded after app.js and uses its helpers (api, esc, busy,
   toast, confirmBox, $). */
'use strict';

const SEC_ROLE = { viewer: 'Viewer (look only)', editor: 'Editor (control the lights and change designs)', admin: 'Administrator' };
const secWhen = t => t ? new Date(t * 1000).toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }) : '';
const secSave = (name, text, type) => {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement('a'); a.href = url; a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(url), 5000);
};

/* ---------------------------------------------------------------- API tokens */
async function tokenPanel(box) {
  const list = await api('tokens').catch(e => { box.innerHTML = `<p class="callout warn small">${esc(e.message)}</p>`; return null; });
  if (!list) return;
  box.innerHTML = `<h2>API tokens</h2>
    <p class="note">For programs that control the lights, such as Home Assistant or a script: each gets its own token instead of a person’s password. Send it as <code>Authorization: Bearer elx_…</code>. A token never manages accounts, tokens or updates, and you can revoke it any time. Every use is in the audit log.</p>
    <div class="list">${list.length ? list.map(t => `<div class="item"><div class="grow"><div class="name">${esc(t.name)} <span class="small muted">…${esc(t.hint || '')}</span></div>
      <div class="sub">${esc(SEC_ROLE[t.role] || t.role)} · made ${esc(secWhen(t.created))}${t.expires ? ` · ${t.expired ? '<b>expired</b>' : 'until ' + esc(secWhen(t.expires))}` : ''}${t.last_used ? ` · last used ${esc(secWhen(t.last_used))}${t.last_from ? ' from ' + esc(t.last_from) : ''}` : ' · not used yet'}</div></div>
      <button class="small ghost danger" data-tokrevoke="${esc(t.id)}">Revoke</button></div>`).join('') : '<p class="muted small">No tokens yet.</p>'}</div>
    <details><summary>Make a token</summary><div class="stack" style="margin-top:10px">
      <label class="field">Who uses it<input type="text" id="tokname" maxlength="60" placeholder="e.g. Home Assistant"></label>
      <label class="field">What it can do<select id="tokrole"><option value="viewer">${SEC_ROLE.viewer}</option><option value="editor" selected>${SEC_ROLE.editor}</option><option value="admin">${SEC_ROLE.admin}</option></select></label>
      <label class="field">Lasts<select id="tokdays"><option value="30">30 days</option><option value="365" selected>1 year</option><option value="">Until revoked</option></select></label>
      <div><button data-tokmake>Make token</button></div><div id="toknew"></div></div></details>`;
  box.onclick = async e => {
    const b = e.target.closest('button'); if (!b) return;
    if (b.dataset.tokmake !== undefined) {
      const days = $('#tokdays', box).value;
      return busy(b, () => api('tokens', { body: { name: $('#tokname', box).value.trim(), role: $('#tokrole', box).value, days: days ? +days : null } }))
        .then(r => {
          tokenPanel(box).then(() => {
            const n = $('#toknew', box); const d = $('details', box); if (d) d.open = true;
            if (n) n.innerHTML = `<p class="callout ok small">Copy it now: it isn’t shown again.<br><code style="word-break:break-all">${esc(r.token)}</code></p>`;
          });
        }).catch(() => {});
    }
    if (b.dataset.tokrevoke) {
      if (!await confirmBox('Revoke this token?', 'Whatever uses it stops working at once.', 'Revoke', true)) return;
      return busy(b, () => api('tokens/revoke', { body: { id: b.dataset.tokrevoke } })).then(() => { toast('Revoked'); tokenPanel(box); }).catch(() => {});
    }
  };
}

/* ---------------------------------------------------------------- audit log */
async function auditPanel(box, q = '') {
  const r = await api('audit?limit=300' + (q ? '&q=' + encodeURIComponent(q) : '')).catch(e => { box.innerHTML = `<p class="callout warn small">${esc(e.message)}</p>`; return null; });
  if (!r) return;
  const rows = r.rows;
  box.innerHTML = `<h2>Audit log</h2>
    <p class="note">Who changed what, from where: people (by account), API tokens, webhooks and automations. Kept for a year. Looking around isn’t listed, only changes.</p>
    <div class="row"><label class="field grow">Search<input type="search" id="audq" value="${esc(q)}" placeholder="e.g. settings, Christmas, token"></label>
      <button class="small ghost" data-audcsv style="align-self:end">Download (CSV)</button></div>
    <div class="list">${rows.length ? rows.map(x => `<div class="item"><div class="grow"><div class="name">${esc(x.what)}${x.ok ? '' : ' <span class="pill bad">refused</span>'}</div>
      <div class="sub">${esc(secWhen(x.at))} · ${esc(x.who)}${x.via ? ' · ' + esc(x.via) : ''}${x.detail ? ' · ' + esc(x.detail) : ''}</div></div></div>`).join('')
      : '<p class="muted small">Nothing yet.</p>'}</div>`;
  const s = $('#audq', box);
  s.onchange = () => auditPanel(box, s.value.trim());
  box.onclick = e => {
    if (!e.target.closest('[data-audcsv]')) return;
    const cell = v => `"${String(v ?? '').replace(/"/g, '""')}"`;
    const csv = ['when,who,role,from,what,detail,ok', ...rows.map(x => [new Date(x.at * 1000).toISOString(), x.who, x.role, x.via, x.what, x.detail, x.ok ? 'yes' : 'refused'].map(cell).join(','))].join('\r\n');
    secSave('eaveluxos-audit.csv', '﻿' + csv, 'text/csv');
  };
}

/* ---------------------------------------------------------------- encrypted backups */
function vaultPanel(box) {
  box.innerHTML = `<h2>Encrypted backup</h2>
    <p class="note">Everything needed to set EaveLuxOS up again on another computer: settings, the Trimlight account details, accounts and (if you like) the house photos, locked with a passphrase. Keep the passphrase somewhere safe: without it the backup can’t be opened, by you or anyone else.</p>
    <label class="field">Passphrase<input type="password" id="vpw" autocomplete="new-password" placeholder="At least 10 characters"></label>
    <label class="field">Passphrase again<input type="password" id="vpw2" autocomplete="new-password"></label>
    <label class="check"><input type="checkbox" id="vphotos"> Include the house photos (a bigger file)</label>
    <div class="row"><button data-vmake>Download encrypted backup</button></div>
    <details><summary>Put a backup back</summary><div class="stack" style="margin-top:10px">
      <p class="note">Replaces the settings on this computer with the backup’s (the app’s own address and port stay). With accounts, everyone signs in again.</p>
      <label class="field">Backup file<input type="file" id="vfile" accept=".elxbackup,.json,application/json"></label>
      <label class="field">Its passphrase<input type="password" id="vopen" autocomplete="off"></label>
      <label class="check"><input type="checkbox" id="vaccts" checked> Also put back the accounts</label>
      <div><button class="danger" data-vrestore>Put it back</button></div></div></details>`;
  box.onclick = async e => {
    const b = e.target.closest('button'); if (!b) return;
    if (b.dataset.vmake !== undefined) {
      const pw = $('#vpw', box).value;
      if (pw.length < 10) return toast('Use a passphrase of at least 10 characters.', true);
      if (pw !== $('#vpw2', box).value) return toast('The two passphrases are different.', true);
      return busy(b, () => api('backup/encrypted', { body: { passphrase: pw, photos: $('#vphotos', box).checked } })).then(r => {
        const day = new Date().toISOString().slice(0, 10);
        secSave(`eaveluxos-${day}.elxbackup`, JSON.stringify(r), 'application/json');
        $('#vpw', box).value = $('#vpw2', box).value = '';
        toast('Encrypted backup downloaded');
      }).catch(() => {});
    }
    if (b.dataset.vrestore !== undefined) {
      const f = $('#vfile', box).files[0];
      if (!f) return toast('Choose the backup file.', true);
      let blob;
      try { blob = JSON.parse(await f.text()); } catch { return toast('That isn’t an EaveLuxOS encrypted backup.', true); }
      if (!await confirmBox('Put this backup back?', 'The settings on this computer are replaced with the backup’s. The current ones stay in Version history.', 'Put it back', true)) return;
      return busy(b, () => api('backup/restore', { body: { backup: blob, passphrase: $('#vopen', box).value, accounts: $('#vaccts', box).checked } })).then(r => {
        toast(`Put back the backup from ${r.created ? new Date(r.created).toLocaleDateString() : 'earlier'}${r.photos ? `, ${r.photos} photos` : ''}.`);
        setTimeout(() => location.reload(), 1200);
      }).catch(() => {});
    }
  };
}

/* ---------------------------------------------------------------- away from home */
function remotePanel(box, a) {
  const yes = (ok, text, fix) => `<li class="${ok ? 'ok' : 'warn'}"><b>${ok ? '✓' : '!'}</b> ${text}${!ok && fix ? ` <span class="small muted">${fix}</span>` : ''}</li>`;
  const https = (a.scheme || 'http') === 'https';
  box.innerHTML = `<h2>Away from home</h2>
    <p class="note">EaveLuxOS is meant for your home network. To use it away from home, connect to your home network first with a <b>VPN</b>: your router’s own (for example WireGuard on a Firewalla, UniFi or ASUS router) or <b>Tailscale</b> on this computer and your phone. Then the usual address works as if you were home. Don’t forward a port on your router to this app: that puts it on the open internet.</p>
    <ul class="checklist">
      ${yes(a.password_set, 'Every person has an account with a password', 'Setup › Accounts & access › Accounts.')}
      ${yes(https, 'HTTPS is on (the address starts with https://)', 'See the manual: “HTTPS on your home network” (mkcert).')}
      ${'local_login' in a ? yes(!!a.local_login || !a.password_set, 'Programs on this computer sign in too', 'Optional: “Require signing in on this computer too” above.') : ''}
    </ul>
    <p class="note">Programs (Home Assistant, scripts) use an <b>API token</b> instead of a password; webhooks keep their own link. Changes made away from home ask for your password again, and every change is in the audit log.</p>`;
}
