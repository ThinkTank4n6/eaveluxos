# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Review #1 (4.18.2): the installed app's service worker kept the answer to
any page opened in the browser as "the app's page" for when the app
computer can't be reached. Opening the new certificate download (/ca.crt),
or the manual (/docs/MANUAL.md), in the installed app replaced the kept
page with that file: away from home, the app then opened as a certificate
or a text file instead of "Can't reach EaveLuxOS".
Run: python3 tests/repro_sw_keeps_download.py"""
import sys; from pathlib import Path; sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import shutil, subprocess

SW = Path(__file__).resolve().parent.parent / "eaveluxos" / "static" / "sw.js"
HARNESS = r"""
const kept = []; const handlers = {};
global.self = { location: { origin: 'http://pc:8787' }, addEventListener: (k, f) => { handlers[k] = f; }, skipWaiting() {}, clients: { claim() {} } };
global.caches = { open: async () => ({ put: async (k) => { kept.push(k); }, match: async () => null, addAll: async () => {} }), keys: async () => [], match: async () => null };
global.fetch = async (req) => ({ ok: true, type: 'basic', headers: { get: () => 'application/x-x509-ca-cert' }, clone() { return this; } });
eval(require('fs').readFileSync(process.argv[1], 'utf8'));
let done;
handlers.fetch({ request: { method: 'GET', url: 'http://pc:8787/ca.crt', mode: 'navigate' }, respondWith: p => { done = Promise.resolve(p); } });
(done || Promise.resolve()).then(() => setTimeout(() => console.log(JSON.stringify(kept)), 50));
"""
if not shutil.which("node"):
    print("SKIP: Node.js isn't installed")
    sys.exit(0)
out = subprocess.run(["node", "-e", HARNESS, str(SW)], capture_output=True, text=True, timeout=30).stdout.strip()
print("BUG: the certificate download was kept as the app's page" if "index.html" in out
      else "OK: a download opened in the app is never kept as its page")
