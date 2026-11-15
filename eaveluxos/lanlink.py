# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Talking to a Trimlight Edge controller directly on the home network (4.1,
experimental). Trimlight's cloud API has no music controls; the Trimlight app
runs music mode over the local network instead. This is what a capture of the
app showed (tools/music-capture, November 2026, firmware 1.17.77):

* The app finds controllers with a UDP broadcast to port 8589
  (``SPTECH 06 00 00 00``), then opens TCP port 8586 on the controller.
* It starts with a short greeting: ``S 01 00 00 L L <L bytes>`` with 4
  random characters (a new set each time), and the controller answers the
  same way.
* Every other message is a frame::

      "SPTECH" | command | 0x00 | length (2 bytes, big-endian)
               | MD5 of the payload (16) | key (1) | payload XOR key

  The controller's reply to a keep-alive is the short form without the MD5
  and key: ``SPTECH 0b 00 00 01 00``.
* Command 0x0b, payload 01: keep-alive, every 5 seconds.
* Command 0x04: a request. Its payload is ``sub | length (2) | data``.
  - sub 0x15, 7 bytes: set the clock (year-2000, month, day, ISO weekday,
    hour, minute, second). The controller answers with everything it holds
    (patterns, timers) under the same sub.
  - sub 0x02, 1 byte: lights off (0) or on (1).
  - sub 0x04, 1 byte: 0x0e when the app opens and when it leaves Music:
    back to normal (out of music mode). (0x09 was seen once; unknown.)
  - sub 0x0c, 23 bytes: music mode: input (1 = levels sent by the app,
    2 = the controller's own input), music pattern (0 = the app's first),
    0xff, 0, 0, 0x3c,
    sensitivity (1-14 seen), then 16 sound levels (zero here).
  A second capture (the same day) showed the lights on/off and leaving
  Music.
* Command 0x0a: the same music payload with live sound levels, 16 frequency
  bands from low to high (0-255), about 9 times a second, while the app
  listens with its microphone.

The scrambling is a single random byte; there's no account, password or key.
Nothing here reaches the internet."""
from __future__ import annotations

import hashlib
import os
import re
import socket
import threading
import time
from datetime import datetime

MAGIC = b"SPTECH"
TCP_PORT = 8586
FIND_PORT = 8589          # the controller listens here for the finding broadcast
FIND_FROM = 8588          # the app sends it from here (and hears answers here)
CMD_REQUEST, CMD_FIND, CMD_LEVELS, CMD_PING = 0x04, 0x06, 0x0A, 0x0B
SUB_TIME, SUB_MUSIC, SUB_POWER, SUB_MODE = 0x15, 0x0C, 0x02, 0x04
MODE_NORMAL = 0x0E                        # what the app sends on opening and on leaving Music
GREETING_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
BANDS = 16
SOURCE_LEVELS, SOURCE_CONTROLLER = 1, 2   # who listens: this app (sends levels) or the controller
SENSITIVITY = (1, 14)                     # the range the Trimlight app's slider sent
PATTERNS = (0, 19)                        # music patterns from 0 (the app's first); the count isn't known yet
SEND_EVERY = 0.11                         # seconds between level frames (the app's pace)
PING_EVERY = 5.0
MAX_FRAME = 64 * 1024


class LinkError(Exception):
    pass


# ------------------------------------------------------------------ frames
def frame(cmd: int, payload: bytes, key: int | None = None) -> bytes:
    """A scrambled frame, as the app sends them."""
    if not 0 <= cmd <= 255 or len(payload) > 0xFFFF:
        raise ValueError("bad frame")
    k = os.urandom(1)[0] if key is None else key & 0xFF
    return (MAGIC + bytes([cmd, 0]) + len(payload).to_bytes(2, "big") + hashlib.md5(payload).digest()
            + bytes([k]) + bytes(b ^ k for b in payload))


def parse(buf: bytes, final: bool = False, short: bool = True):
    """Complete messages at the start of buf: ([(kind, cmd, payload)], rest).
    kind is "frame" (scrambled, MD5 checked), "short" (the unscrambled reply
    form) or "hello". A damaged stream raises LinkError. With final=False an
    incomplete message waits for more bytes. short: whether short keep-alive
    answers can come (reading the controller); reading what the app sends
    (the test controller, the capture tool), a frame that has only partly
    arrived is never mistaken for one."""
    out, i, n = [], 0, len(buf)
    while i < n:
        if buf[i:i + 2] == b"S\x01":
            if n - i < 6:
                break
            ln = buf[i + 4]
            if n - i < 6 + ln:
                break
            out.append(("hello", None, buf[i + 6:i + 6 + ln]))
            i += 6 + ln
            continue
        if n - i < 10:
            if buf[i:i + min(6, n - i)] != MAGIC[:min(6, n - i)]:
                raise LinkError("The controller sent something unexpected.")
            break
        if buf[i:i + 6] != MAGIC:
            raise LinkError("The controller sent something unexpected.")
        cmd, ln = buf[i + 6], int.from_bytes(buf[i + 8:i + 10], "big")
        if ln > MAX_FRAME:
            raise LinkError("The controller sent a message that's too long.")
        if n - i >= 27 + ln:
            k = buf[i + 26]
            body = bytes(b ^ k for b in buf[i + 27:i + 27 + ln])
            if hashlib.md5(body).digest() == buf[i + 10:i + 26]:
                out.append(("frame", cmd, body))
                i += 27 + ln
                continue
        short_ok = n - i >= 10 + ln and ((short and cmd == CMD_PING) or final)
        if short_ok and (n - i == 10 + ln or buf[i + 10 + ln:i + 12 + ln] in (b"SP", b"S\x01")
                         or n - i - 10 - ln < 2):
            out.append(("short", cmd, buf[i + 10:i + 10 + ln]))
            i += 10 + ln
            continue
        if final or n - i >= 27 + ln:
            raise LinkError("A message from the controller didn't check out (damaged or not understood).")
        break
    return out, buf[i:]


def greeting() -> bytes:
    """The app's greeting: 4 random characters (captured: "+D56", "ufPC")."""
    word = "".join(GREETING_CHARS[b % len(GREETING_CHARS)] for b in os.urandom(4)).encode()
    return b"S\x01\x00\x00" + bytes([len(word), len(word)]) + word


def request(sub: int, data: bytes) -> bytes:
    return bytes([sub]) + len(data).to_bytes(2, "big") + data


def time_payload(now: datetime) -> bytes:
    return request(SUB_TIME, bytes([now.year - 2000, now.month, now.day, now.isoweekday(),
                                    now.hour, now.minute, now.second]))


def music_payload(source: int, pattern: int, sensitivity: int, levels=None) -> bytes:
    lv = list(levels) if levels is not None else [0] * BANDS
    if len(lv) != BANDS or not all(isinstance(v, int) and 0 <= v <= 255 for v in lv):
        raise ValueError(f"{BANDS} sound levels from 0 to 255")
    if source not in (SOURCE_LEVELS, SOURCE_CONTROLLER):
        raise ValueError("unknown input")
    if not (PATTERNS[0] <= pattern <= PATTERNS[1]) or not (SENSITIVITY[0] <= sensitivity <= SENSITIVITY[1]):
        raise ValueError("music pattern or sensitivity out of range")
    return request(SUB_MUSIC, bytes([source, pattern, 0xFF, 0, 0, 0x3C, sensitivity]) + bytes(lv))


def read_music(payload: bytes) -> dict | None:
    """The settings in a music payload (for the capture tool and tests)."""
    if len(payload) < 3 or payload[0] != SUB_MUSIC:
        return None
    d = payload[3:3 + int.from_bytes(payload[1:3], "big")]
    if len(d) < 7:
        return None
    return {"source": d[0], "pattern": d[1], "sensitivity": d[6], "levels": list(d[7:7 + BANDS])}


def names_in(dump: bytes) -> list[str]:
    """Pattern and timer names in the controller's answer to the clock
    request (best effort: the layout isn't known, the names are plain text)."""
    seen = []
    for m in re.finditer(rb"[A-Za-z0-9][ -~]{2,31}", dump):
        s = m.group().decode("ascii").strip()
        if sum(c.isalpha() for c in s) >= 3 and s not in seen:
            seen.append(s)
    return seen[:200]


def check_address(addr) -> str:
    """A controller address: an IPv4 address on a home network."""
    import ipaddress
    try:
        ip = ipaddress.IPv4Address(str(addr).strip())
    except ValueError:
        raise LinkError("Enter the controller's IP address, like 192.168.1.50.") from None
    if not ip.is_private or (ip.is_loopback and os.environ.get("EAVELUXOS_LAN_TEST") != "1"):
        raise LinkError("That isn't an address on a home network (they start with 10., 172.16-31. or 192.168.).")
    return str(ip)


# ------------------------------------------------------------------ link
class Link:
    """One TCP connection to a controller."""

    def __init__(self, host: str, port: int | None = None, timeout: float = 3.0):
        self.host, self.port, self.timeout = host, port or TCP_PORT, timeout
        self.sock = None
        self.buf = b""
        self.greeting = None
        self.lock = threading.Lock()

    def open(self) -> "Link":
        try:
            self.sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        except OSError as e:
            raise LinkError(f"Couldn't reach the controller at {self.host} (port {self.port}): {e}") from None
        self.sock.settimeout(self.timeout)
        try:
            self._send(greeting())
            self.greeting = self._wait(lambda m: m[0] == "hello")[2]
        except LinkError:
            self.close()
            raise
        return self

    def close(self):
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None

    def __enter__(self):
        return self.open()

    def __exit__(self, *a):
        self.close()

    def _send(self, data: bytes):
        if self.sock is None:
            raise LinkError("Not connected.")
        try:
            with self.lock:
                self.sock.sendall(data)
        except OSError as e:
            raise LinkError(f"The connection to the controller was lost: {e}") from None

    def _wait(self, want, timeout: float | None = None):
        """Read until a message for which want(msg) is true."""
        end = time.monotonic() + (timeout or self.timeout)
        while True:
            msgs, self.buf = parse(self.buf)
            for m in msgs:
                if want(m):
                    return m
            left = end - time.monotonic()
            if left <= 0:
                raise LinkError("The controller didn't answer.")
            try:
                self.sock.settimeout(left)
                chunk = self.sock.recv(65536)
            except socket.timeout:
                raise LinkError("The controller didn't answer.") from None
            except OSError as e:
                raise LinkError(f"The connection to the controller was lost: {e}") from None
            if not chunk:
                raise LinkError("The controller closed the connection.")
            self.buf += chunk
            if len(self.buf) > 4 * MAX_FRAME:
                raise LinkError("The controller sent too much.")

    def drain(self):
        """Take whatever has arrived without waiting (acks to the stream)."""
        if self.sock is None:
            return
        try:
            self.sock.settimeout(0)
            while True:
                chunk = self.sock.recv(65536)
                if not chunk:
                    raise LinkError("The controller closed the connection.")
                self.buf += chunk
        except (BlockingIOError, socket.timeout):
            pass
        except OSError as e:
            raise LinkError(f"The connection to the controller was lost: {e}") from None
        finally:
            if self.sock is not None:
                self.sock.settimeout(self.timeout)
        _, self.buf = parse(self.buf)

    def ping(self) -> float:
        """Keep-alive; returns the round trip in milliseconds."""
        t = time.monotonic()
        self._send(frame(CMD_PING, b"\x01"))
        self._wait(lambda m: m[1] == CMD_PING)
        return (time.monotonic() - t) * 1000

    def read_all(self, now: datetime) -> bytes:
        """Set the clock (as the Trimlight app does on opening) and get back
        what the controller holds."""
        self._send(frame(CMD_REQUEST, time_payload(now)))
        m = self._wait(lambda m: m[0] == "frame" and m[2][:1] == bytes([SUB_TIME]), timeout=max(self.timeout, 6))
        return m[2]

    def leave_music(self):
        """Out of music mode, as the Trimlight app does on leaving Music."""
        self._send(frame(CMD_REQUEST, request(SUB_MODE, bytes([MODE_NORMAL]))))

    def power(self, on: bool):
        self._send(frame(CMD_REQUEST, request(SUB_POWER, b"\x01" if on else b"\x00")))

    def music(self, source: int, pattern: int, sensitivity: int):
        self._send(frame(CMD_REQUEST, music_payload(source, pattern, sensitivity)))

    def levels(self, pattern: int, sensitivity: int, levels):
        self._send(frame(CMD_LEVELS, music_payload(SOURCE_LEVELS, pattern, sensitivity, levels)))


def find(timeout: float = 2.0, send_to: str = "255.255.255.255") -> list[str]:
    """Addresses that answer the finding broadcast (best effort: whether and
    how controllers answer wasn't in the capture)."""
    hello = MAGIC + bytes([CMD_FIND, 0, 0, 0])
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    found = []
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        try:
            s.bind(("", FIND_FROM))
        except OSError:
            s.bind(("", 0))
        end = time.monotonic() + timeout
        nxt = 0.0
        while time.monotonic() < end:
            if time.monotonic() >= nxt:
                try:
                    s.sendto(hello, (send_to, FIND_PORT))
                except OSError:
                    pass
                nxt = time.monotonic() + 0.5
            s.settimeout(max(0.05, min(0.5, end - time.monotonic())))
            try:
                data, (ip, _) = s.recvfrom(2048)
            except (socket.timeout, OSError):
                continue
            if data.startswith(MAGIC) and data != hello and ip not in found:
                found.append(ip)
    finally:
        s.close()
    return found


# ------------------------------------------------------------------ stream
class Streamer:
    """A music show from this computer: holds the connection, sends the
    settings, then the latest sound levels about 9 times a second and a
    keep-alive every 5 seconds. Ends by itself when the listening page goes
    quiet (no levels for `idle` seconds), when `wanted()` turns false (the
    show was stopped in the app), or when the connection fails twice in a
    row or more than three times in a minute.
    on_end(why) is told why: "stopped", "idle", "app" or "lost"."""

    def __init__(self, on_end=None, idle: float = 20.0, link_factory=Link):
        self.on_end = on_end or (lambda why: None)
        self.idle = idle
        self.link_factory = link_factory
        self.lock = threading.Lock()
        self.state = None            # {"host", "pattern", "sensitivity", "tab", ...} while running
        self.levels = [0] * BANDS
        self.fed = 0.0
        self.thread = None
        self.stop_evt = threading.Event()
        self.last_error = None
        self.sent = 0

    def running(self) -> bool:
        return self.state is not None

    def status(self) -> dict:
        st = self.state
        if not st:
            return {"running": False, "error": self.last_error}
        return {"running": True, "host": st["host"], "pattern": st["pattern"], "sensitivity": st["sensitivity"],
                "since": st["since"], "frames": self.sent, "hearing": time.monotonic() - self.fed < 2,
                "error": None}

    def start(self, host: str, pattern: int, sensitivity: int, tab: str, wanted=lambda: True, clock=None):
        """clock: a function giving the local time. If given, the show opens
        the way the Trimlight app does (greeting, clock, read) before the
        music settings."""
        music_payload(SOURCE_LEVELS, pattern, sensitivity)        # checks the numbers
        with self.lock:
            if self.state is not None:
                if self.state["tab"] != tab:
                    raise LinkError("A music show from this computer is already running on another page. Stop it there first.")
                if self.state["host"] == host:          # already running here: just new settings
                    self.state.update(pattern=pattern, sensitivity=sensitivity, changed=True)
                    self.fed = time.monotonic()
                    return
                raise LinkError("Stop the running show before changing the controller's address.")
        link = self.link_factory(host)
        link.open()
        try:
            if clock is not None:
                link.read_all(clock())
            link.ping()
            link.music(SOURCE_LEVELS, pattern, sensitivity)
        except LinkError:
            link.close()
            raise
        with self.lock:
            self.stop_evt = threading.Event()
            self.state = {"host": host, "pattern": pattern, "sensitivity": sensitivity, "tab": tab,
                          "since": time.time()}
            self.levels, self.fed, self.sent, self.last_error = [0] * BANDS, time.monotonic(), 0, None
            self.thread = threading.Thread(target=self._run, args=(link, self.stop_evt, wanted), daemon=True,
                                           name="music-link")
            self.thread.start()

    def feed(self, levels, tab: str) -> bool:
        if not (isinstance(levels, list) and len(levels) == BANDS
                and all(isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 255 for v in levels)):
            raise ValueError(f"{BANDS} sound levels from 0 to 255")
        with self.lock:
            st = self.state
            if not st or st["tab"] != tab:
                return False
            self.levels, self.fed = list(levels), time.monotonic()
            return True

    def adjust(self, tab: str, pattern=None, sensitivity=None):
        with self.lock:
            st = self.state
            if not st or st["tab"] != tab:
                return False
            p = st["pattern"] if pattern is None else pattern
            s = st["sensitivity"] if sensitivity is None else sensitivity
            music_payload(SOURCE_LEVELS, p, s)
            st["pattern"], st["sensitivity"], st["changed"] = p, s, True
            return True

    def stop(self, tab: str | None = None, why: str = "stopped") -> bool:
        with self.lock:
            st = self.state
            if not st or (tab is not None and st["tab"] != tab):
                return False
            st["why"] = why if why in ("stopped", "app") else "stopped"
            self.stop_evt.set()
            t = self.thread
        if t is not None and t is not threading.current_thread():
            t.join(3)
        return True

    def _run(self, link, stop_evt, wanted):
        why, err, failures, again = "stopped", None, 0, []
        next_ping = time.monotonic() + PING_EVERY
        try:
            while not stop_evt.is_set():
                now = time.monotonic()
                with self.lock:
                    st = dict(self.state or {})
                    lv, fed = list(self.levels), self.fed
                    if self.state and self.state.pop("changed", False):
                        st["changed"] = True
                if not st:
                    break
                if now - fed > self.idle:
                    why = "idle"
                    break
                try:
                    if not wanted():
                        why = "app"
                        break
                except Exception:
                    pass
                try:
                    if st.get("changed"):
                        link.music(SOURCE_LEVELS, st["pattern"], st["sensitivity"])
                    link.levels(st["pattern"], st["sensitivity"], lv if now - fed < 1.5 else [0] * BANDS)
                    self.sent += 1
                    link.drain()
                    if now >= next_ping:
                        link.ping()
                        next_ping = now + PING_EVERY
                    failures = 0
                except LinkError as e:
                    failures += 1
                    link.close()
                    again = [t for t in again if now - t < 60] + [now]
                    if failures >= 2 or len(again) > 3:          # twice in a row, or over and over
                        why, err = "lost", str(e)
                        break
                    try:
                        link = self.link_factory(st["host"])
                        link.open()
                        link.music(SOURCE_LEVELS, st["pattern"], st["sensitivity"])
                    except LinkError as e2:
                        why, err = "lost", str(e2)
                        break
                stop_evt.wait(SEND_EVERY)
        finally:
            if why != "lost":
                try:                     # leave music mode, as the Trimlight app does
                    link.leave_music()
                except LinkError:
                    pass
            link.close()
            with self.lock:
                st = self.state
                if stop_evt.is_set() and st:
                    why = st.get("why", why)
                if self.thread is threading.current_thread() or self.thread is None:
                    self.state = None
                    self.last_error = err
            try:
                self.on_end(why)
            except Exception:
                pass
