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
    // 4.26.3: a bare address stops before * (so **http://localhost:8787** stays
    // bold around the link) and is held aside while bold and italic are
    // marked, so they can never land inside the link's markup.
    s = s.replace(/https?:\/\/[^\s<>"')*]*[^\s<>"').,;:*]/g, u => {
      links.push(`<a href="${u}" target="_blank" rel="noopener noreferrer">${u}</a>`);
      return `\u0001${links.length - 1}\u0001`;
    });
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
          if (j < lines.length && indentOf(lines[j]) > base) {
            // 4.26.3: an indented block after a blank line (paragraphs, a
            // table, a code block, a list) belongs to this item and is
            // rendered like any other Markdown; a table there used to show
            // as raw "| Role | Can |" text, and each line as its own paragraph.
            let k = j;
            const block = [];
            while (k < lines.length) {
              if (lines[k].trim() && indentOf(lines[k]) <= base) break;
              block.push(lines[k]); k++;
            }
            while (block.length && !block[block.length - 1].trim()) block.pop();
            const cut = Math.min(...block.filter(b => b.trim()).map(indentOf));
            inner += render(block.map(b => b.replace(/\t/g, '    ').slice(cut)).join('\n'));
            i = k;
            continue;
          }
          break;
        }
        const sub = isList(l);
        if (sub && indentOf(l) > base) { const r = list(lines, i, indentOf(l)); inner += r.html; i = r.i; continue; }
        if (sub || indentOf(l) <= base) break;
        if (/^\s*```/.test(l)) {                    // 4.26.3: a code block right under the item's text
          const cut = indentOf(l), block = [l];
          i++;
          while (i < lines.length && !/^\s*```/.test(lines[i])) block.push(lines[i++]);
          if (i < lines.length) block.push(lines[i++]);
          inner += render(block.map(b => b.replace(/\t/g, '    ').slice(Math.min(cut, indentOf(b)))).join('\n'));
          continue;
        }
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

  const ALERTS = { note: 'Note', tip: 'Tip', important: 'Important', warning: 'Warning', caution: 'Caution' };

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
      if (h) {
        const n = h[1].length;
        // 4.22.3: "(4.18)" at the end of a section heading shows as a small version tag
        let t = inline(h[2]);
        if (n >= 2) t = t.replace(/\s*\((\d+\.\d+(?:\.\d+)?)\)$/, (m, v) => ` <span class="ver" title="Added in version ${v}">${v}</span>`);
        out += `<h${n} id="${esc(slug(h[2]))}">${t}</h${n}>`; i++; continue;
      }
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
        // 4.22.3: GitHub's alert boxes (> [!TIP] and the like), shown the same here
        const al = /^\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s*$/i.exec(body[0] || '');
        if (al) {
          const k = al[1].toLowerCase();
          out += `<blockquote class="alert alert-${k}"><p class="alert-title">${ALERTS[k]}</p>${render(body.slice(1).join('\n'))}</blockquote>`;
          continue;
        }
        out += `<blockquote>${render(body.join('\n'))}</blockquote>`; continue;
      }
      if (isList(l)) { const r = list(lines, i, indentOf(l)); out += r.html; i = r.i; continue; }
      const para = [];
      // 4.22.1: a line no block takes (a "|" row with no table header above
      // it) is text; before, nothing moved past it and the page froze.
      if (/^\s*\|/.test(l)) para.push(lines[i++].trim());
      while (i < lines.length && lines[i].trim() && !/^(#{1,6}\s|```|\s*>|\s*\|)/.test(lines[i]) && !isList(lines[i])) para.push(lines[i++].trim());
      out += `<p>${inline(para.join(' '))}</p>`;
    }
    return out;
  }

  const api = { render, slug, inline, safeUrl };
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.Markdown = api;
})(typeof window !== 'undefined' ? window : globalThis);
