// SPDX-License-Identifier: MIT
// Checks for eaveluxos/static/markdown.js, run by tests/test_manual.py with Node.
'use strict';
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const M = require('../eaveluxos/static/markdown.js');

// Nothing in the text can become markup or a script.
const evil = M.render('# Hi <script>alert(1)</script>\n\n<img src=x onerror=alert(1)> **b** [x](javascript:alert(1)) [y](data:text/html,1) `<b>`');
assert(!/<script|<img|javascript:|data:text/.test(evil), evil);
assert(evil.includes('&lt;script&gt;') && evil.includes('<b>b</b>') && evil.includes('<code>&lt;b&gt;</code>'));
assert.strictEqual(M.safeUrl('#5-the-setup-assistant'), '#5-the-setup-assistant');
assert.strictEqual(M.safeUrl('docs/LICENSE.txt'), 'docs/LICENSE.txt');
assert.strictEqual(M.safeUrl('../secret'), null);
assert.strictEqual(M.safeUrl('vbscript:x'), null);
assert(M.render('see https://www.python.org/downloads/.').includes('href="https://www.python.org/downloads/" target="_blank" rel="noopener noreferrer"'));

// Structure: nested lists, ordered start, tables, quotes, code.
const html = M.render('1. One\n   - inner\n2. Two\n\nText\n\n5. Five\n\n| A | B |\n|---|---|\n| 1 | **2** |\n\n> **Tip:** x\n\n```\na < b\n```');
assert(html.includes('<ol><li>One<ul><li>inner</li></ul></li><li>Two</li></ol>'), html);
assert(html.includes('<ol start="5">') && html.includes('<td><b>2</b></td>') && html.includes('<blockquote><p><b>Tip:</b> x</p></blockquote>'));
assert(html.includes('<pre class="code"><code>a &lt; b</code></pre>'));

// The real manual: every table-of-contents link has a matching heading.
const manual = M.render(fs.readFileSync(path.join(__dirname, '..', 'MANUAL.md'), 'utf8'));
const ids = new Set([...manual.matchAll(/id="([^"]+)"/g)].map(m => m[1]));
const links = [...manual.matchAll(/href="#([^"]+)"/g)].map(m => m[1]);
assert(links.length >= 20, 'contents links');
assert.deepStrictEqual(links.filter(l => !ids.has(l)), []);
console.log('markdown ok');
