/* SPDX-License-Identifier: MIT
   Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)

   A small, safe Markdown renderer for the built-in manual: headings (with
   GitHub-style ids for the table of contents), paragraphs, nested lists,
   tables, block quotes, code blocks, rules, **bold**, *italic*, `code` and
   links. All text is HTML-escaped first; links may only point to #anchors,
   relative files or http(s) addresses. Works as a plain <script>
   (window.Markdown) and as a Node module (tests). */
(function (root) {
  'use strict';

  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  /* GitHub's anchor ids: lowercase, punctuation dropped, spaces to hyphens. */
  function slug(text) {
    return text.toLowerCase().replace(/<[^>]*>/g, '').replace(/[`*_]/g, '').trim()
      .replace(/[^\p{L}\p{N}\s-]/gu, '').replace(/\s/g, '-');
  }

  function safeUrl(u) {
    const url = u.trim();
    if (/^#[\w-]*$/.test(url)) return url;
    if (/^https?:\/\/[^\s"'<>]+$/i.test(url)) return url;
    if (/^[\w./-]+(#[\w-]*)?$/.test(url) && !url.includes('..') && !/^[a-z]+:/i.test(url)) return url;
    return null;
  }

  function inline(text) {
    const codes = [];
    let s = String(text).replace(/`([^`]+)`/g, (_, c) => { codes.push(`<code>${esc(c)}</code>`); return `\u0000${codes.length - 1}\u0000`; });
    const links = [];
    s = s.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (m, label, url) => {
      const href = safeUrl(url);
      const ext = href && /^https?:/i.test(href);
      links.push(href ? `<a href="${esc(href)}"${ext ? ' target="_blank" rel="noopener noreferrer"' : ''}>${emph(esc(label))}</a>` : esc(label));
      return `\u0001${links.length - 1}\u0001`;
    });
    s = esc(s);
    s = s.replace(/https?:\/\/[^\s<>"')]+[^\s<>"').,;:]/g, u => `<a href="${u}" target="_blank" rel="noopener noreferrer">${u}</a>`);
    s = emph(s);
    s = s.replace(/\u0001(\d+)\u0001/g, (_, i) => links[+i]).replace(/\u0000(\d+)\u0000/g, (_, i) => codes[+i]);
    return s;
  }
  function emph(s) {
    return s.replace(/\*\*([^*]+?)\*\*/g, '<b>$1</b>').replace(/(^|[^\w*])\*([^*\s][^*]*?)\*(?=[^\w*]|$)/g, '$1<i>$2</i>');
  }

  const isList = l => /^(\s*)([-*+]|\d+[.)])\s+/.exec(l);
  const indentOf = l => l.match(/^\s*/)[0].replace(/\t/g, '    ').length;
  const cells = l => l.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map(c => c.trim());

  function list(lines, i, base) {
    const first = isList(lines[i]);
    const ordered = /\d/.test(first[2]);
    const start = ordered ? parseInt(first[2], 10) : 1;
    let html = ordered ? `<ol${start !== 1 ? ` start="${start}"` : ''}>` : '<ul>';
    while (i < lines.length) {
      const m = isList(lines[i]);
      if (!m || indentOf(lines[i]) !== base) break;
      let text = lines[i].slice(m[0].length);
      let inner = '';
      i++;
      while (i < lines.length) {
        const l = lines[i];
        if (!l.trim()) {
          let j = i + 1;
          while (j < lines.length && !lines[j].trim()) j++;
          if (j < lines.length && indentOf(lines[j]) > base) { i = j; continue; }
          break;
        }
        const sub = isList(l);
        if (sub && indentOf(l) > base) { const r = list(lines, i, indentOf(l)); inner += r.html; i = r.i; continue; }
        if (sub || indentOf(l) <= base) break;
        if (inner) inner += `<p>${inline(l.trim())}</p>`; else text += ' ' + l.trim();
        i++;
      }
      html += `<li>${inline(text)}${inner}</li>`;
      while (i < lines.length && !lines[i].trim()) {
        let j = i; while (j < lines.length && !lines[j].trim()) j++;
        const nm = j < lines.length && isList(lines[j]);
        if (nm && indentOf(lines[j]) === base) i = j; else break;
      }
    }
    return { html: html + (ordered ? '</ol>' : '</ul>'), i };
  }

  function render(md) {
    const lines = String(md).replace(/\r\n?/g, '\n').split('\n');
    let out = '', i = 0;
    while (i < lines.length) {
      const l = lines[i];
      if (!l.trim()) { i++; continue; }
      if (/^```/.test(l)) {
        const body = []; i++;
        while (i < lines.length && !/^```/.test(lines[i])) body.push(lines[i++]);
        i++; out += `<pre class="code"><code>${esc(body.join('\n'))}</code></pre>`; continue;
      }
      const h = /^(#{1,6})\s+(.*?)\s*#*\s*$/.exec(l);
      if (h) { const n = h[1].length; out += `<h${n} id="${esc(slug(h[2]))}">${inline(h[2])}</h${n}>`; i++; continue; }
      if (/^\s*(-{3,}|\*{3,}|_{3,})\s*$/.test(l)) { out += '<hr>'; i++; continue; }
      if (/^\s*\|/.test(l) && i + 1 < lines.length && /^\s*\|?\s*:?-{2,}/.test(lines[i + 1])) {
        const head = cells(l); i += 2;
        let rows = '';
        while (i < lines.length && /^\s*\|/.test(lines[i])) rows += `<tr>${cells(lines[i++]).map(c => `<td>${inline(c)}</td>`).join('')}</tr>`;
        out += `<div class="tablewrap"><table><thead><tr>${head.map(c => `<th>${inline(c)}</th>`).join('')}</tr></thead><tbody>${rows}</tbody></table></div>`;
        continue;
      }
      if (/^\s*>/.test(l)) {
        const body = [];
        while (i < lines.length && /^\s*>/.test(lines[i])) body.push(lines[i++].replace(/^\s*>\s?/, ''));
        out += `<blockquote>${render(body.join('\n'))}</blockquote>`; continue;
      }
      if (isList(l)) { const r = list(lines, i, indentOf(l)); out += r.html; i = r.i; continue; }
      const para = [];
      while (i < lines.length && lines[i].trim() && !/^(#{1,6}\s|```|\s*>|\s*\|)/.test(lines[i]) && !isList(lines[i])) para.push(lines[i++].trim());
      out += `<p>${inline(para.join(' '))}</p>`;
    }
    return out;
  }

  const api = { render, slug, inline, safeUrl };
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.Markdown = api;
})(typeof window !== 'undefined' ? window : globalThis);
