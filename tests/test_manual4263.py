# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""4.26.3: the manual viewer renders bold addresses, tables and paragraphs
inside list items, and code blocks under a list item."""
import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "eaveluxos" / "static" / "markdown.js"


def render(md):
    code = (f"let s='';process.stdin.setEncoding('utf8');process.stdin.on('data',d=>s+=d);"
            f"process.stdin.on('end',()=>process.stdout.write(require({json.dumps(str(JS))}).render(s)))")
    r = subprocess.run(["node", "-e", code], input=md, capture_output=True, text=True, encoding="utf-8", timeout=60)
    return r.stdout


@unittest.skipUnless(shutil.which("node"), "node not installed")
class Manual4263(unittest.TestCase):
    def test_bold_address(self):
        h = render("Open **http://localhost:8787**. Then **Next**.\n\nAn **https://** address.")
        self.assertIn('<b><a href="http://localhost:8787"', h)
        self.assertIn("<b>Next</b>", h)
        self.assertIn("<b>https://</b>", h)
        self.assertNotIn("**", h)

    def test_table_and_paragraph_inside_a_list_item(self):
        h = render("- **Accounts**: roles:\n\n  | Role | Can |\n  |---|---|\n  | **Admin** | All |\n\n  First line\n  second line.\n- Next")
        self.assertIn("<table>", h)
        self.assertNotIn("| Role", h)
        self.assertIn("<p>First line second line.</p>", h)
        self.assertIn("<li>Next</li>", h)

    def test_code_block_under_an_item(self):
        h = render("- Windows:\n  ```\n  certutil -hashfile x SHA256\n  ```\n- Mac")
        self.assertIn('<li>Windows:<pre class="code"><code>certutil -hashfile x SHA256</code></pre></li>', h)

    def test_whole_manual_has_no_raw_markup(self):
        h = render((ROOT / "MANUAL.md").read_text(encoding="utf-8"))
        import re
        text = re.sub(r"<pre.*?</pre>|<code>.*?</code>", "", h, flags=re.S)
        text = re.sub(r"<[^>]+>", "", text)
        self.assertNotIn("**", text)
        self.assertNotIn("|---", text)
        self.assertNotRegex(h, r'href="[^"]*[*<]')

    def test_both_download_pages_listed(self):
        md = (ROOT / "MANUAL.md").read_text(encoding="utf-8")
        sec = md.split("## 4. Download and start the app", 1)[1].split("## 5.", 1)[0]
        self.assertIn("https://github.com/ThinkTank4n6/eaveluxos/releases/latest", sec)
        self.assertIn("https://thinktankforensics.com/home.html", sec)


if __name__ == "__main__":
    unittest.main()
