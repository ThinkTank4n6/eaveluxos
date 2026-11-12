# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""3.4.1: the Manual tab, and the version, copyright and MIT License link at
the bottom of every screen."""
import json
import shutil
import subprocess
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from eaveluxos.server import VERSION, App, make_server
from eaveluxos.store import hash_password

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "eaveluxos" / "static"
NOTICE = "Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)"


class Docs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = Path(tempfile.mkdtemp())
        cls.app = App(cls.dir, start=False)
        cls.app.store.save_user(None, "owner", "admin", password="porchlights1")
        cls.app.store.save_secrets(local_login=True)        # nobody is signed in
        cls.srv = make_server(cls.app, "127.0.0.1", 0)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.app.store.close()
        shutil.rmtree(cls.dir, ignore_errors=True)

    def get(self, path):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{self.srv.server_address[1]}{path}", timeout=10) as r:
                return r.status, r.headers.get("Content-Type"), r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers.get("Content-Type"), e.read()

    def test_manual_and_license_readable_before_sign_in(self):
        st, ctype, body = self.get("/docs/MANUAL.md")
        self.assertEqual((st, ctype), (200, "text/markdown; charset=utf-8"))
        self.assertEqual(body, (ROOT / "MANUAL.md").read_bytes())
        st, ctype, body = self.get("/docs/LICENSE.txt")
        self.assertEqual((st, ctype), (200, "text/plain; charset=utf-8"))
        self.assertIn(b"MIT License", body)
        self.assertEqual(self.get("/api/settings")[0], 401)               # everything else still needs sign-in
        for other in ("/docs/README.md", "/docs/../main.py", "/docs/eaveluxos.db"):
            self.assertNotEqual(self.get(other)[0], 200, other)

    def test_version_reported_before_sign_in(self):
        st, _, body = self.get("/api/session")
        self.assertEqual(json.loads(body)["version"], VERSION)

    def test_footer_on_every_screen(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        footer = html[html.index('<footer class="legal"'):html.index("</footer>")]
        self.assertIn(NOTICE, footer)
        self.assertIn('href="docs/LICENSE.txt"', footer)
        self.assertIn("MIT License", footer)
        self.assertIn('id="legalver"', footer)
        self.assertLess(html.index("<main"), html.index('<footer class="legal"'))   # outside the views, so always shown
        js = (STATIC / "app.js").read_text(encoding="utf-8")
        self.assertIn("$('#legalver').textContent = `EaveLuxOS ${s.version}`", js)
        self.assertIn("['manual','Manual']", js)

    def test_credentials_page_linked(self):
        url = "https://trimlight.ledhue.com/trimlight/v1/api-credentials/apply"
        manual = (ROOT / "MANUAL.md").read_text(encoding="utf-8")
        sec2 = manual[manual.index("## 2. Get your Trimlight API credentials"):manual.index("## 3. Install Python")]
        self.assertIn("### How to obtain API credentials", sec2)
        self.assertIn(url, sec2)
        self.assertIn("Get API credentials", sec2)
        self.assertEqual((STATIC / "app.js").read_text(encoding="utf-8").count(f'href="{url}" target="_blank" rel="noopener noreferrer"'), 3)
        self.assertIn(url, (ROOT / "README.md").read_text(encoding="utf-8"))

    def test_docs_ship_with_every_build(self):
        build = (ROOT / "packaging" / "build.py").read_text(encoding="utf-8")
        self.assertIn("ROOT / 'MANUAL.md'", build)
        self.assertIn("ROOT / 'LICENSE'", build)
        self.assertIn("MANUAL.md", (ROOT / "Dockerfile").read_text(encoding="utf-8"))

    @unittest.skipUnless(shutil.which("node"), "Node.js isn't installed")
    def test_markdown_renderer(self):
        r = subprocess.run(["node", str(Path(__file__).parent / "markdown_check.js")], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main()
