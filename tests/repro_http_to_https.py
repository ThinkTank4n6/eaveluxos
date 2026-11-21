# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Review #1 (4.16.5), Chris on Nov 20: with HTTPS on (an mkcert
certificate), starting EaveLuxOS while it was already running opened
http://localhost:8787, and the browser said "localhost didn't send any
data": a plain http:// request to the HTTPS port got no answer at all. Now
the app opens https:// when HTTPS is on, and a plain request is sent on to
https://. Needs the cryptography package (prints SKIP without it).
Run: python3 tests/repro_http_to_https.py"""
import sys; from pathlib import Path; sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import shutil, socket, tempfile, threading
try:
    from eaveluxos.tlscert import make_cert
except ImportError:
    print("SKIP: no cryptography"); sys.exit(0)
from eaveluxos.server import App, make_server

d = Path(tempfile.mkdtemp())
try:
    (d / "data" / "tls").mkdir(parents=True)
    try:
        make_cert(d / "data" / "tls")
    except RuntimeError:
        print("SKIP: no cryptography"); sys.exit(0)
    app = App(d)
    srv = make_server(app, "127.0.0.1", 0)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    s = socket.create_connection(("127.0.0.1", port), timeout=10)
    s.sendall(b"GET /#home HTTP/1.1\r\nHost: localhost:%d\r\n\r\n" % port)
    got = b""
    try:
        while chunk := s.recv(4096):
            got += chunk
    except OSError:
        pass
    s.close(); srv.shutdown(); srv.server_close(); app.store.close()
    want = f"Location: https://localhost:{port}/".encode()
    print("OK: http:// is sent on to https://" if got.startswith(b"HTTP/1.1 307") and want in got
          else f"BUG: a plain http:// request got {got[:60]!r} (the browser: \"didn't send any data\")")
finally:
    shutil.rmtree(d, ignore_errors=True)
