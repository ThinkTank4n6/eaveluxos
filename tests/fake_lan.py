# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""A pretend Trimlight Edge controller on the home network (4.1), answering
the way the real one did in the November 2026 capture: a greeting for a
greeting, the short keep-alive answer, and everything it holds for the clock
request. It checks every frame's MD5, as the real one presumably does, and
keeps what it got for the tests to look at."""
import socket
import threading
import time

from eaveluxos import lanlink as L

DUMP = (b"\x01\x00\x00\x00\x01\x00S\x00T\x00\x8a" + b"VALENTINE'S DAY" + b"\x00" * 8 + b"CHRISTMAS" + b"\x00" * 6
        + b"American Flag" + b"\x00\x02\x7f\xff")


class FakeController:
    # Something a newer firmware might send that this app doesn't know: an
    # unknown short reply, a damaged frame and stray bytes (4.1.4 tests).
    NOISE = (L.MAGIC + b"\x04\x00\x00\x01\x07" + b"\x00junk!"
             + L.MAGIC + b"\x04\x00\x00\x02" + b"\x11" * 16 + b"\x05\x01\x02")

    def __init__(self, greet=True, answer_pings=True, close_after=None, greet_delay=0.0, noise=False):
        self.noise = noise
        self.greet, self.answer_pings, self.close_after = greet, answer_pings, close_after
        self.greet_delay = greet_delay
        self.srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.srv.bind(("127.0.0.1", 0))
        self.srv.listen(4)
        self.port = self.srv.getsockname()[1]
        self.got = []            # (kind, cmd, payload) in order
        self.connections = 0
        self.errors = []
        self.lock = threading.Lock()
        self.stopping = False
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self):
        while not self.stopping:
            try:
                c, _ = self.srv.accept()
            except OSError:
                return
            with self.lock:
                self.connections += 1
            threading.Thread(target=self._serve, args=(c,), daemon=True).start()

    def _serve(self, c):
        buf, frames = b"", 0
        c.settimeout(5)
        try:
            while not self.stopping:
                try:
                    chunk = c.recv(65536)
                except socket.timeout:
                    continue
                except OSError:              # the app hung up (a reset is normal at the end of a test)
                    return
                if not chunk:
                    return
                buf += chunk
                try:
                    msgs, buf = L.parse(buf, short=False)
                except L.LinkError as e:
                    self.errors.append(str(e))
                    return
                for kind, cmd, body in msgs:
                    with self.lock:
                        self.got.append((kind, cmd, body))
                    try:
                        self._answer(c, kind, cmd, body)
                    except OSError:
                        return
                    if kind == "frame":
                        frames += 1
                        if self.close_after and frames >= self.close_after:
                            return
        finally:
            c.close()

    def _answer(self, c, kind, cmd, body):
        if kind == "hello" and self.greet:
            time.sleep(self.greet_delay)
            tok = b"cG0od8uKe9tE9EuiJG9udr1r0000KME000YLD0000RKw0E0cY00="
            c.sendall(b"S\x01\x00\x00" + bytes([len(tok), len(tok)]) + tok)
        elif kind == "frame" and cmd == L.CMD_PING and self.answer_pings:
            if self.answer_pings is not True:     # a number: answer that many, then go quiet
                self.answer_pings -= 1
            c.sendall((self.NOISE if self.noise else b"") + L.MAGIC + b"\x0b\x00\x00\x01\x00")
        elif kind == "frame" and cmd == L.CMD_REQUEST and body[:1] == bytes([L.SUB_TIME]):
            c.sendall(L.frame(L.CMD_REQUEST, L.request(L.SUB_TIME, DUMP)))

    def frames(self, cmd=None):
        with self.lock:
            return [(k, c, b) for k, c, b in self.got if k == "frame" and (cmd is None or c == cmd)]

    def close(self):
        self.stopping = True
        self.srv.close()
