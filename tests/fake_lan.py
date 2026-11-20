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

    def __init__(self, greet=True, answer_pings=True, close_after=None, greet_delay=0.0, noise=False, holds=None,
                 host="127.0.0.1", port=0):
        """holds: {"ports": [(start, end, on)] * 4, "patterns": {id: record}}: a
        controller that keeps patterns and ports, applies changes and
        answers the clock request with them, as the real one does (4.3).
        ignore: set of request subs it receives but doesn't apply (trouble)."""
        self.noise = noise
        self.holds = holds
        self.ignore = set()
        self.needs_ping = False
        self.silent_reads = 0            # don't answer this many clock requests
        self.overstate = 0               # say this many bytes more than the state answer holds
        self.quiet_after_save = 0        # this many times: apply a save, then go quiet on that connection
        self.late_reads = 0              # after each change, this many reads still show the old state
        self.drop_saves = 0              # lose this many pattern saves (both halves)
        self._shown = None               # what late reads show
        self._late_left = 0          # 4.3.6: no answer to a request before a keep-alive
        self.active = self.most_active = 0
        self.off_reads_zero = False      # report a port that is off as 0-0
        self.tidies_slots = False        # store unused color slots as 00 00 00 00 01
        self.greet, self.answer_pings, self.close_after = greet, answer_pings, close_after
        self.greet_delay = greet_delay
        self.max_fps = None              # 4.13: more live previews a second than this and keep-alive answers lag
        self.previews = []               # when each live preview came (4.13)
        self.slow_pings = 0              # 4.13: answer this many keep-alives half a second late (a Wi-Fi hiccup)
        self.srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.srv.bind((host, port))       # 4.5: several controllers, each at its own 127.0.0.x, same port
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
        pinged = mute = False
        with self.lock:
            self.active += 1
            self.most_active = max(self.most_active, self.active)
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
                    if kind == "frame" and cmd == L.CMD_PING:
                        pinged = True
                    if self.needs_ping and not pinged and kind == "frame" and cmd == L.CMD_REQUEST:
                        continue
                    if mute:
                        continue                 # this connection has gone quiet
                    if (self.quiet_after_save and kind == "frame" and cmd == L.CMD_REQUEST
                            and body[:1] == bytes([L.SUB_PATTERN_SAVE])):
                        self.quiet_after_save -= 1
                        mute = True              # 4.3.12: takes the save, then answers nothing more here
                    try:
                        self._answer(c, kind, cmd, body)
                    except OSError:
                        return
                    if kind == "frame":
                        frames += 1
                        if self.close_after and frames >= self.close_after:
                            return
        finally:
            with self.lock:
                self.active -= 1
            c.close()

    def _answer(self, c, kind, cmd, body):
        if kind == "hello" and self.greet:
            time.sleep(self.greet_delay)
            tok = b"cG0od8uKe9tE9EuiJG9udr1r0000KME000YLD0000RKw0E0cY00="
            c.sendall(b"S\x01\x00\x00" + bytes([len(tok), len(tok)]) + tok)
        elif kind == "frame" and cmd == L.CMD_REQUEST and body[:1] == bytes([L.SUB_PREVIEW]):
            with self.lock:
                self.previews.append(time.monotonic())
        elif kind == "frame" and cmd == L.CMD_PING and self.answer_pings:
            if self.slow_pings:
                self.slow_pings -= 1
                time.sleep(0.5)
            if self.max_fps:
                now = time.monotonic()
                with self.lock:
                    recent = sum(1 for t in self.previews if now - t < 1.0)
                if recent > self.max_fps + 0.5:
                    time.sleep(0.5)               # behind: the answer comes late
            if self.answer_pings is not True:     # a number: answer that many, then go quiet
                self.answer_pings -= 1
            c.sendall((self.NOISE if self.noise else b"") + L.MAGIC + b"\x0b\x00\x00\x01\x00")
        elif kind == "frame" and cmd == L.CMD_REQUEST and body[:1] == bytes([L.SUB_TIME]) and self.silent_reads:
            self.silent_reads -= 1
        elif kind == "frame" and cmd == L.CMD_REQUEST and body[:1] == bytes([L.SUB_TIME]):
            if self.holds is None:
                c.sendall(L.frame(L.CMD_REQUEST, L.request(L.SUB_TIME, DUMP)))
            else:
                with self.lock:
                    h = self.holds
                    pats = [h["patterns"][k] for k in sorted(h["patterns"])]
                    payload = L.state_payload([(0, 0) if self.off_reads_zero and not on else (a, b)
                                               for a, b, on in h["ports"]], pats,
                                              **({"tail": h["tail"]} if h.get("tail") else {}))   # its timers (4.6)
                    if self._late_left and self._shown is not None:
                        self._late_left -= 1
                        payload = self._shown
                    else:
                        self._shown = payload
                f = bytearray(L.frame(L.CMD_REQUEST, payload))
                if self.overstate:            # a length field saying more than it holds (4.3.13)
                    f[8:10] = (len(payload) + self.overstate).to_bytes(2, "big")
                c.sendall(bytes(f))
        elif kind == "frame" and cmd == L.CMD_REQUEST and self.holds is not None and body[0] not in self.ignore:
            sub, d = body[0], body[3:]
            with self.lock:
                if sub in (L.SUB_PATTERN_NEW, L.SUB_PATTERN_SAVE, L.SUB_DELETE, L.SUB_PORT):
                    self._late_left = self.late_reads
                if sub == L.SUB_PATTERN_SAVE and self.drop_saves:
                    self.drop_saves -= 1
                    self.holds["patterns"].pop(d[0], None)    # neither half took
                    return
                if sub in (L.SUB_PATTERN_NEW, L.SUB_PATTERN_SAVE) and len(d) == L.RECORD:
                    rec = bytearray(d)
                    if self.tidies_slots:
                        for i in range(L.SLOTS):
                            if rec[32 + 5 * i] == 0:
                                rec[32 + 5 * i:37 + 5 * i] = b"\0\0\0\0\x01"
                    self.holds["patterns"][d[0]] = bytes(rec)
                elif sub == L.SUB_DELETE and len(d) == 1:
                    self.holds["patterns"].pop(d[0], None)
                elif sub == L.SUB_PORT and len(d) == 6:
                    self.holds["ports"][d[0]] = (int.from_bytes(d[1:3], "big"), int.from_bytes(d[3:5], "big"), d[5])

    def frames(self, cmd=None):
        with self.lock:
            return [(k, c, b) for k, c, b in self.got if k == "frame" and (cmd is None or c == cmd)]

    def close(self):
        self.stopping = True
        self.srv.close()
