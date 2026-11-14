# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Light / Dark / Auto switch (3.15)."""
import re
import shutil
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "eaveluxos" / "static"


class ThemeTests(unittest.TestCase):
    css = (STATIC / "app.css").read_text(encoding="utf-8")
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    html = (STATIC / "index.html").read_text(encoding="utf-8")

    def test_forced_dark_uses_the_same_colors_as_system_dark(self):
        system = re.search(r':root:not\(\[data-theme="light"\]\)\{([^}]*)\}', self.css).group(1)
        forced = re.search(r':root\[data-theme="dark"\]\{([^}]*)\}', self.css).group(1)
        self.assertEqual(system.split(), forced.split())
        self.assertIn("color-scheme:dark", forced)

    def test_every_dark_rule_respects_a_chosen_light_theme(self):
        # A bare "@media (prefers-color-scheme: dark){ selector" would ignore Light.
        for m in re.finditer(r"@media \(prefers-color-scheme: dark\)\{\s*([^{]+)\{", self.css):
            self.assertIn(':not([data-theme="light"])', m.group(1), m.group(0))

    def test_choice_applies_before_the_page_is_drawn(self):
        head = self.html.split("</head>")[0]
        self.assertIn('<script src="theme.js"></script>', head)
        t = (STATIC / "theme.js").read_text(encoding="utf-8")
        self.assertIn("localStorage.getItem('elx-theme')", t)
        self.assertIn("try", t)                       # private windows: no storage, no crash

    def test_header_button_cycles_and_remembers(self):
        self.assertIn("{ auto: 'light', light: 'dark', dark: 'auto' }", self.js)
        self.assertIn("localStorage.setItem('elx-theme', t)", self.js)
        self.assertIn("btn('theme'", self.js)

    def test_server_serves_theme_js(self):
        from eaveluxos.server import App, make_server
        d = Path(tempfile.mkdtemp())
        app = App(d, start=False)
        srv = make_server(app, "127.0.0.1", 0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{srv.server_address[1]}/theme.js", timeout=10) as r:
                self.assertEqual(r.status, 200)
                self.assertIn("javascript", r.headers.get("Content-Type", ""))
        finally:
            srv.shutdown(); srv.server_close(); app.store.close(); shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
