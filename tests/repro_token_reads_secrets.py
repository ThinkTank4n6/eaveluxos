# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Review #1 (4.17): an API token is meant for an integration and never
manages accounts, tokens or the Trimlight connection. But an Administrator
token could read Setup › Accounts & access's data (GET /api/account), which
for an Administrator includes the webhook link's token and the Trimlight
Client ID: a token for Home Assistant could then call the webhooks as
someone else and learn the account's ID.
Run: python3 tests/repro_token_reads_secrets.py"""
import sys; from pathlib import Path; sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import json, shutil, tempfile, threading, urllib.request
from eaveluxos.server import App, make_server

d = Path(tempfile.mkdtemp())
try:
    app = App(d, start=False)
    app.store.save_secrets(client_id="the-client-id", webhook_token="the-webhook-token")
    tok = app.store.new_token("Home Assistant", "admin")["token"]
    srv = make_server(app, "127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    r = urllib.request.Request(f"http://127.0.0.1:{srv.server_address[1]}/api/account",
                               headers={"Authorization": f"Bearer {tok}", "X-Forwarded-For": "203.0.113.9"})
    with urllib.request.urlopen(r, timeout=10) as x:
        body = x.read().decode()
    srv.shutdown(); srv.server_close(); app.store.close()
    leaked = [s for s in ("the-client-id", "the-webhook-token") if s in body]
    print(f"BUG: an API token read {', '.join(leaked)}" if leaked else "OK: an API token doesn't see the account's secrets")
finally:
    shutil.rmtree(d, ignore_errors=True)
