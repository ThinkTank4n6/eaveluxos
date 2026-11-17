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
  - sub 0x04, 1 byte N: show saved pattern number N. (Read before 4.2.1
    as "back to normal": the app sent 0x0e because pattern 14 was showing.
    This app doesn't send it; the schedule's next pattern ends the show.)
  - sub 0x05, 1 byte N: delete saved pattern N.
  - sub 0x0a, 6 bytes: a port's pixels: port (0-3), start (2), end (2),
    on (1) or off (0).
  - sub 0x0f / 0x0e, 182 bytes: a pattern record (create / save): number,
    name (25 bytes), category, mode, speed, brightness, 2 bytes, then 30
    color slots of count, red, green, blue, on.
  - sub 0x0d, 153 bytes: live preview while editing (mode, speed,
    brightness, then the 30 slots).
  - sub 0x0c, 23 bytes: music mode: input (1 = levels sent by the app,
    2 = the controller's own input), music pattern (0 = the app's first),
    the color for the "Single Color" patterns (red, green, blue: a fourth
    capture showed them follow the app's color bar), 0x3c,
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
import logging
import os
import re
import socket
import threading
import time
from datetime import datetime
from pathlib import Path

log = logging.getLogger("eaveluxos.lanlink")

MAGIC = b"SPTECH"
TCP_PORT = 8586
FIND_PORT = 8589          # the controller listens here for the finding broadcast
FIND_FROM = 8588          # the app sends it from here (and hears answers here)
CMD_REQUEST, CMD_FIND, CMD_LEVELS, CMD_PING = 0x04, 0x06, 0x0A, 0x0B
SUB_TIME, SUB_MUSIC, SUB_POWER = 0x15, 0x0C, 0x02
SUB_SHOW, SUB_DELETE, SUB_PORT = 0x04, 0x05, 0x0A      # show / delete saved pattern N; port pixels
SUB_PATTERN_NEW, SUB_PATTERN_SAVE, SUB_PREVIEW = 0x0F, 0x0E, 0x0D
GREETING_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
BANDS = 16
SOURCE_LEVELS, SOURCE_CONTROLLER = 1, 2   # who listens: this app (sends levels) or the controller
SENSITIVITY = (1, 14)                     # the range the Trimlight app's slider sent
PATTERNS = (0, 17)                        # the controller's 18 built-in music patterns, from 0
# Their names as the Trimlight Edge app shows them (November 2026). The
# "Single Color" ones take a color; the others have their own (4.2).
PATTERN_NAMES = ("Full Color Rhythm Spectrum", "Single Color Rhythm Spectrum", "Full Color Rhythm Twinkle",
                 "Single Color Rhythm Twinkle", "Gradient Energy", "Single Color Energy", "Gradient Pulse",
                 "Single Color Pulse", "Full Color Ejection Forward", "Single Color Ejection Forward",
                 "Full Color Ejection Backward", "Single Color Ejection Backward", "Full Color VuMeter",
                 "Single Color VuMeter", "Independence Day", "Christmas", "HeatBeat", "Party")
SINGLE_COLOR = tuple(i for i, n in enumerate(PATTERN_NAMES) if n.startswith("Single Color"))
DEFAULT_COLOR = (0xFF, 0x00, 0x00)         # red, as the app starts
SEND_EVERY = 0.11                         # seconds between level frames (the app's pace)
PING_EVERY = 5.0
ANSWER_WITHIN = 15.0                      # no keep-alive answer for this long: the connection is gone (4.1.4)
MAX_FRAME = 64 * 1024
# 4.3.10: messages the app couldn't read are saved here (the data folder) so
# they can be looked at; the server sets it. Nov 16: the controller answered a
# read with 1,940 bytes whose check didn't match, while Trimlight's cloud
# couldn't parse its data either (12006).
DUMP_DIR = None
GREET_PAUSE = 0.5          # seconds after the greeting (4.4); tests set 0
ASK_AGAIN = 3.0            # no answer at all to a read this long: ask again on the same connection (4.4.3)
DUMPS_KEPT = 5


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


def parse(buf: bytes, final: bool = False, short: bool = True, resync: bool = False):
    """Complete messages at the start of buf: ([(kind, cmd, payload)], rest).
    kind is "frame" (scrambled, MD5 checked), "short" (the unscrambled reply
    form) or "hello". With final=False an incomplete message waits for more
    bytes. short: whether short keep-alive answers can come (reading the
    controller); reading what the app sends (the test controller, the
    capture tool), a frame that has only partly arrived is never mistaken
    for one.

    Anything that doesn't fit raises LinkError, unless resync (the live
    connection, 4.1.4): then it's skipped up to the next "SPTECH" and
    reported as ("junk", None, bytes), so a message from a newer firmware or
    one damaged frame doesn't end a show."""
    out, i, n = [], 0, len(buf)

    def skip(at, why):
        if not resync:
            raise LinkError(why)
        j = buf.find(MAGIC, at + 1)
        if j < 0:                                  # keep a tail that may be the start of the next one
            j = n
            for k in range(min(5, n - at - 1), 0, -1):
                if MAGIC.startswith(buf[n - k:]):
                    j = n - k
                    break
        out.append(("junk", None, buf[at:j]))
        return j

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
                i = skip(i, "The controller sent something unexpected.")
                continue
            break
        if buf[i:i + 6] != MAGIC:
            i = skip(i, "The controller sent something unexpected.")
            continue
        cmd, ln = buf[i + 6], int.from_bytes(buf[i + 8:i + 10], "big")
        if ln > MAX_FRAME:
            i = skip(i, "The controller sent a message that's too long.")
            continue
        if n - i >= 27 + ln:
            k = buf[i + 26]
            body = bytes(b ^ k for b in buf[i + 27:i + 27 + ln])
            if hashlib.md5(body).digest() == buf[i + 10:i + 26]:
                out.append(("frame", cmd, body))
                i += 27 + ln
                continue
        short_ok = n - i >= 10 + ln and ((short and cmd == CMD_PING) or final)
        if short_ok and (resync or n - i == 10 + ln or buf[i + 10 + ln:i + 12 + ln] in (b"SP", b"S\x01")
                         or n - i - 10 - ln < 2):
            out.append(("short", cmd, buf[i + 10:i + 10 + ln]))
            i += 10 + ln
            continue
        if n - i >= 27 + ln and resync:
            # 4.3.10: a length that doesn't match the bytes (as on Nov 16) —
            # find the length the controller's own check fits, if any.
            k, digest = buf[i + 26], buf[i + 10:i + 26]
            nxt = buf.find(MAGIC, i + 27)
            if nxt < 0 and not final and n - i < 27 + ln + 512:
                break                     # more of it may still be on the way
            end = n if nxt < 0 else nxt
            for alt in range(end - i - 27, max(-1, ln - 512), -1):
                body = bytes(b ^ k for b in buf[i + 27:i + 27 + alt])
                if alt != ln and hashlib.md5(body).digest() == digest:
                    log.warning("A message from the controller said %d bytes but held %d; read as %d.", ln, alt, alt)
                    out.append(("frame", cmd, body))
                    i += 27 + alt
                    break
            else:
                i = skip(i, "A message from the controller didn't check out (damaged or not understood).")
            continue
        if final or n - i >= 27 + ln:
            i = skip(i, "A message from the controller didn't check out (damaged or not understood).")
            continue
        break
    return out, buf[i:]


def salvage(buf: bytes, sub: int):
    """A frame in buf whose MD5 fits some length it actually holds (shorter
    or longer than its length field says), with a body starting with sub."""
    at = buf.find(MAGIC)
    while at >= 0:
        if len(buf) - at > 27:
            k, digest = buf[at + 26], buf[at + 10:at + 26]
            nxt = buf.find(MAGIC, at + 27)
            end = len(buf) if nxt < 0 else nxt
            for alt in range(end - at - 27, 2, -1):
                body = bytes(b ^ k for b in buf[at + 27:at + 27 + alt])
                if body[:1] == bytes([sub]) and hashlib.md5(body).digest() == digest:
                    return body
        at = buf.find(MAGIC, at + 1)
    return None


def save_unread(host: str, raw: bytes):
    """Keep a copy of a message the app couldn't read (4.3.10), for a look
    later: data/lan-unread-<time>.bin, the last few only. It holds what the
    controller sent (its patterns and timers), nothing else."""
    if DUMP_DIR is None:
        return
    try:
        d = Path(DUMP_DIR)
        d.mkdir(parents=True, exist_ok=True)
        # A unique name: Windows' clock can give two saves the same
        # microsecond (4.3.11; GitHub's Windows test overwrote one).
        stamp = f"{datetime.now():%Y%m%d-%H%M%S}"
        n = len(list(d.glob(f"lan-unread-{stamp}-*.bin")))
        name = d / f"lan-unread-{stamp}-{n:03d}.bin"
        while name.exists():
            n += 1
            name = d / f"lan-unread-{stamp}-{n:03d}.bin"
        name.write_bytes(raw)
        old = sorted(d.glob("lan-unread-*.bin"))[:-DUMPS_KEPT]
        for f in old:
            f.unlink(missing_ok=True)
        log.warning("Saved the message the controller at %s sent that couldn't be read: %s", host, name.name)
    except OSError:
        pass


def greeting() -> bytes:
    """The app's greeting: 4 random characters (captured: "+D56", "ufPC")."""
    word = "".join(GREETING_CHARS[b % len(GREETING_CHARS)] for b in os.urandom(4)).encode()
    return b"S\x01\x00\x00" + bytes([len(word), len(word)]) + word


def request(sub: int, data: bytes) -> bytes:
    return bytes([sub]) + len(data).to_bytes(2, "big") + data


def time_payload(now: datetime) -> bytes:
    return request(SUB_TIME, bytes([now.year - 2000, now.month, now.day, now.isoweekday(),
                                    now.hour, now.minute, now.second]))


def check_color(color) -> tuple:
    """(r, g, b) from "#RRGGBB" or a 3-tuple of 0-255."""
    if isinstance(color, str) and re.fullmatch(r"#?[0-9A-Fa-f]{6}", color.strip()):
        h = color.strip().lstrip("#")
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    if isinstance(color, (tuple, list)) and len(color) == 3 and all(
            isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 255 for v in color):
        return tuple(color)
    raise ValueError("A color looks like #FF0000.")


def music_payload(source: int, pattern: int, sensitivity: int, levels=None, color=DEFAULT_COLOR) -> bytes:
    lv = list(levels) if levels is not None else [0] * BANDS
    if len(lv) != BANDS or not all(isinstance(v, int) and 0 <= v <= 255 for v in lv):
        raise ValueError(f"{BANDS} sound levels from 0 to 255")
    if source not in (SOURCE_LEVELS, SOURCE_CONTROLLER):
        raise ValueError("unknown input")
    if not (PATTERNS[0] <= pattern <= PATTERNS[1]) or not (SENSITIVITY[0] <= sensitivity <= SENSITIVITY[1]):
        raise ValueError("music pattern or sensitivity out of range")
    return request(SUB_MUSIC, bytes([source, pattern, *check_color(color), 0x3C, sensitivity]) + bytes(lv))


def read_music(payload: bytes) -> dict | None:
    """The settings in a music payload (for the capture tool and tests)."""
    if len(payload) < 3 or payload[0] != SUB_MUSIC:
        return None
    d = payload[3:3 + int.from_bytes(payload[1:3], "big")]
    if len(d) < 7:
        return None
    return {"source": d[0], "pattern": d[1], "color": "#%02X%02X%02X" % tuple(d[2:5]), "sensitivity": d[6],
            "levels": list(d[7:7 + BANDS])}


def names_in(dump: bytes) -> list[str]:
    """Pattern and timer names in the controller's answer to the clock
    request (best effort: the layout isn't known, the names are plain text)."""
    seen = []
    for m in re.finditer(rb"[A-Za-z0-9][ -~]{2,31}", dump):
        s = m.group().decode("ascii").strip()
        if sum(c.isalpha() for c in s) >= 3 and s not in seen:
            seen.append(s)
    return seen[:200]


# ------------------------------------------------------------------ what the controller holds (4.3)
# Decoded from four captures (Nov 15, 2026) against the cloud's copy of the
# same controller. The answer to the clock request, after "15 LL LL":
#   3 bytes (01 00 00 seen; not known), then ports 1-4 as start (2) and end (2),
#   then 3 bytes (10 4d, then the pattern count less one), the pattern count,
#   then one 182-byte record per saved pattern, then timers and the time.
# A pattern record (also what sub 0x0f / 0x0e send):
#   number | name (25 bytes, NUL-padded) | 02 | mode | speed | brightness
#   | 00 00 | 30 color slots of count, red, green, blue, on (1) / off (0)
NAME_LEN, SLOTS, RECORD, HEAD = 25, 30, 182, 23
MAX_PATTERN_ID = 60                     # the Trimlight Edge library's size
WRITE_GAP = 0.6                         # between the two halves of a pattern save, as the app spaced them


def pattern_record(pid: int, name: str, mode: int, speed: int, brightness: int, slots) -> bytes:
    """slots: up to 30 of (count, (red, green, blue), on). Raises ValueError."""
    if not 1 <= pid <= 255:
        raise ValueError("pattern number out of range")
    raw = str(name).strip().encode("ascii", "replace")[:NAME_LEN]
    if not raw:
        raise ValueError("a pattern needs a name")
    for v in (mode, speed, brightness):
        if not (isinstance(v, int) and 0 <= v <= 255):
            raise ValueError("mode, speed and brightness are 0-255")
    slots = list(slots)
    if len(slots) > SLOTS:
        raise ValueError(f"at most {SLOTS} color slots")
    out = bytearray([pid]) + raw.ljust(NAME_LEN, b"\0") + bytes([2, mode, speed, brightness, 0, 0])
    for count, (r, g, b), on in slots + [(0, (0, 0, 0), True)] * (SLOTS - len(slots)):
        if not 0 <= count <= 255:
            raise ValueError("at most 255 bulbs in one color slot")
        out += bytes([count, r, g, b, 1 if on else 0])
    return bytes(out)


def record_from_effect(pid: int, e: dict) -> bytes:
    """A custom-colors pattern as Trimlight's cloud describes it (a backup's
    "effects" entry, or this app's own pattern) as a local record."""
    if e.get("category") not in (1, None):
        raise ValueError("only custom-color patterns can be written over the home network")
    px = sorted([p for p in e.get("pixels") or [] if isinstance(p, dict)], key=lambda p: p.get("index", 0))
    slots = []
    for p in px:
        c = int(p.get("color") or 0)
        slots.append((int(p.get("count") or 0), ((c >> 16) & 255, (c >> 8) & 255, c & 255), not p.get("disable")))
    while slots and slots[-1] == (0, (0, 0, 0), True) and len(slots) > SLOTS:
        slots.pop()
    return pattern_record(pid, str(e.get("name") or ""), int(e.get("mode") or 0), int(e.get("speed", 128)),
                          int(e.get("brightness", 255)), slots)


def read_record(r: bytes) -> dict:
    slots = [[r[32 + 5 * i], "#%02X%02X%02X" % tuple(r[33 + 5 * i:36 + 5 * i]), r[36 + 5 * i]] for i in range(SLOTS)]
    return {"id": r[0], "name": r[1:1 + NAME_LEN].split(b"\0")[0].decode("ascii", "replace"),
            "mode": r[27], "speed": r[28], "brightness": r[29], "slots": slots}


def read_state(body: bytes) -> dict:
    """The controller's answer to the clock request, decoded. Raises
    LinkError if it isn't laid out as expected (then nothing may be written)."""
    if body[:1] != bytes([SUB_TIME]) or len(body) < 3 + HEAD:
        raise LinkError("The controller's answer wasn't in the expected layout.")
    d = body[3:3 + int.from_bytes(body[1:3], "big")]
    if len(d) < HEAD:                   # review #6 (4.3.1): a short declared length
        raise LinkError("The controller's answer was shorter than expected.")
    n = d[22]
    if len(d) < HEAD + RECORD * n:
        raise LinkError("The controller's answer was shorter than its pattern count says.")
    ports = [{"port": i + 1, "start": int.from_bytes(d[3 + 4 * i:5 + 4 * i], "big"),
              "end": int.from_bytes(d[5 + 4 * i:7 + 4 * i], "big")} for i in range(4)]
    pats = [read_record(d[HEAD + RECORD * k:HEAD + RECORD * (k + 1)]) for k in range(n)]
    # raw: everything it sent, kept with backups (4.3.10) so the parts not
    # decoded yet (its timers) can be looked at.
    # switch: the first byte, 1 with the lights on and 0 off (seen Nov 15-16, 2026).
    return {"head": d[:3].hex(" "), "switch": d[0], "ports": ports, "patterns": pats, "raw": body.hex()}


def state_payload(ports, patterns, head=b"\x01\x00\x00", tail=b"\x00" * 37) -> bytes:
    """The other way round (tests, and to check read_state against itself)."""
    d = bytearray(head)
    for p in ports:
        d += int(p[0]).to_bytes(2, "big") + int(p[1]).to_bytes(2, "big")
    d += bytes([0x10, 0x4D, max(len(patterns) - 1, 0), len(patterns)])
    for r in patterns:
        d += r
    return request(SUB_TIME, bytes(d + tail))


def same_record(p: dict, rec: bytes) -> bool:
    """Does a pattern read back from the controller hold exactly this record?"""
    return read_record(rec) == p


def check_address(addr) -> str:
    """A controller address: an IPv4 address on a home network."""
    import ipaddress
    try:
        ip = ipaddress.IPv4Address(str(addr).strip())
    except ValueError:
        raise LinkError("Enter the controller's IP address, like 192.168.1.50.") from None
    # 4.1.4: only the home-network ranges. "Private" in Python also covers
    # 0.0.0.0 (which reaches this computer itself), 240.x and 169.254.x.
    home = any(ip in ipaddress.IPv4Network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))
    test = ip.is_loopback and os.environ.get("EAVELUXOS_LAN_TEST") == "1"
    if not (home or test) or (home and str(ip).endswith(".255")):
        raise LinkError("That isn't a device address on a home network (they start with 10., 172.16-31. or 192.168.).")
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
        self.skipped, self.warned = 0, False     # bytes not understood (4.1.4)

    def open(self) -> "Link":
        self.buf = b""                    # also when opening again (4.3.12)
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
        # 4.4: the Trimlight app waits about half a second after the greeting
        # before asking anything; asked at once, the controller often ignored
        # the first read ("0 bytes came", Nov 16).
        if GREET_PAUSE:
            time.sleep(GREET_PAUSE)
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
            msgs, self.buf = parse(self.buf, resync=True)
            self._junk(msgs)
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
        msgs, self.buf = parse(self.buf, resync=True)
        self._junk(msgs)
        return msgs

    def _junk(self, msgs):
        for m in msgs:
            if m[0] == "junk":
                self.skipped += len(m[2])
                if len(m[2]) >= 100:
                    save_unread(self.host, m[2])
                if not self.warned:
                    self.warned = True
                    log.warning("The controller at %s sent %d bytes this app doesn't understand (skipped): %s",
                                self.host, len(m[2]), m[2][:32].hex(" "))

    def send_ping(self):
        """A keep-alive without waiting for the answer (4.1.4): the stream
        collects answers with drain(), so a slow one never holds up the
        sound levels."""
        self._send(frame(CMD_PING, b"\x01"))

    def ping(self) -> float:
        """Keep-alive, waiting for the answer; returns the round trip in
        milliseconds (Test connection, and before a show starts)."""
        t = time.monotonic()
        self._send(frame(CMD_PING, b"\x01"))
        self._wait(lambda m: m[1] == CMD_PING)
        return (time.monotonic() - t) * 1000

    def read_all(self, now: datetime) -> bytes:
        """Set the clock (as the Trimlight app does on opening) and get back
        what the controller holds."""
        req = frame(CMD_REQUEST, time_payload(now))
        self._send(req)
        want = lambda m: m[0] == "frame" and m[2][:1] == bytes([SUB_TIME])
        try:
            try:
                return self._wait(want, timeout=ASK_AGAIN)[2]
            except LinkError:
                if not self.buf and self.sock is not None:
                    # Nothing at all came: the controller often ignores the
                    # first request (Nov 16-17: "0 bytes came", then the next
                    # one answered). Ask again here before giving up (4.4.3).
                    self._send(req)
                return self._wait(want, timeout=max(self.timeout, 6))[2]
        except LinkError as e:
            # 4.3.13: Nov 16, 4:43 PM, Pattern backups: "didn't answer", and
            # nothing saved. An answer whose length field says more than it
            # holds waits for bytes that never come. Look for one whose own
            # check fits a length it does hold, and keep what came either way.
            body = salvage(self.buf, SUB_TIME)
            if body is not None:
                log.warning("The controller's answer said more bytes than it sent; read as %d.", len(body))
                self.buf = b""
                return body
            # Nothing at all is common and the caller says what it means
            # (4.4.3: 74 of these lines on the night of Nov 17); some bytes
            # that don't fit are worth a warning.
            (log.warning if self.buf else log.info)(
                "No usable answer to a read from %s: %d bytes came%s", self.host, len(self.buf),
                f" ({self.buf[:40].hex(' ')})" if self.buf else "")
            if len(self.buf) >= 100:
                save_unread(self.host, self.buf)
            raise e

    def state(self, now: datetime) -> dict:
        return read_state(self.read_all(now))

    def _write(self, sub: int, data: bytes):
        """One change, sent the way the Trimlight app sends it: a keep-alive
        answered first, then the request. The controller doesn't answer
        changes: read it back to check (4.3)."""
        self.ping()
        self._send(frame(CMD_REQUEST, request(sub, data)))

    def save_pattern(self, record: bytes):
        """Create, then save, as the Trimlight app does (0x0f, then 0x0e)."""
        self._write(SUB_PATTERN_NEW, record)
        time.sleep(WRITE_GAP)
        self._write(SUB_PATTERN_SAVE, record)

    def delete_pattern(self, pid: int):
        self._write(SUB_DELETE, bytes([pid]))

    def set_port(self, port: int, start: int, end: int, on: bool):
        """port 0-3; start and end 1-2048. A port can really be off here."""
        if port not in range(4) or not 1 <= start <= end <= 2048:
            raise ValueError("port 1-4, bulbs 1-2048")
        self._write(SUB_PORT, bytes([port]) + start.to_bytes(2, "big") + end.to_bytes(2, "big") + bytes([1 if on else 0]))

    def power(self, on: bool):
        self._send(frame(CMD_REQUEST, request(SUB_POWER, b"\x01" if on else b"\x00")))

    def show_saved(self, pid: int):
        """Show saved pattern number pid (sub 0x04, as the Trimlight app does)."""
        if not 1 <= pid <= 255:
            raise ValueError("pattern number out of range")
        self._write(SUB_SHOW, bytes([pid]))

    def music(self, source: int, pattern: int, sensitivity: int, color=DEFAULT_COLOR):
        self._send(frame(CMD_REQUEST, music_payload(source, pattern, sensitivity, color=color)))

    def levels(self, pattern: int, sensitivity: int, levels, color=DEFAULT_COLOR):
        self._send(frame(CMD_LEVELS, music_payload(SOURCE_LEVELS, pattern, sensitivity, levels, color)))


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
    on_end(why, sid) is told why ("stopped", "idle", "app" or "lost") and
    which show it was."""

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
        self.starting = None         # the page whose start is connecting right now (4.1.4)

    def running(self) -> bool:
        return self.state is not None or self.starting is not None

    def status(self) -> dict:
        st = self.state
        if not st:
            return {"running": False, "error": self.last_error}
        return {"running": True, "host": st["host"], "pattern": st["pattern"], "sensitivity": st["sensitivity"],
                "color": "#%02X%02X%02X" % tuple(st.get("color", DEFAULT_COLOR)),
                "since": st["since"], "frames": self.sent, "hearing": time.monotonic() - self.fed < 2,
                "error": None}

    def start(self, host: str, pattern: int, sensitivity: int, tab: str, wanted=lambda: True, clock=None,
              sid: str | None = None, color=DEFAULT_COLOR):
        """clock: a function giving the local time. If given, the show opens
        the way the Trimlight app does (greeting, clock, read) before the
        music settings. sid: this show's own name, handed back to on_end
        (4.1.4), so the end of one show can never stop a newer one."""
        color = check_color(color)
        music_payload(SOURCE_LEVELS, pattern, sensitivity, color=color)        # checks the numbers
        with self.lock:
            if self.state is not None:
                if self.state["tab"] != tab:
                    raise LinkError("A music show from this computer is already running on another page. Stop it there first.")
                if self.state["host"] == host:          # already running here: just new settings
                    self.state.update(pattern=pattern, sensitivity=sensitivity, color=color, changed=True)
                    self.fed = time.monotonic()
                    return
                raise LinkError("Stop the running show before changing the controller's address.")
            # 4.1.4: claimed before connecting (which can take seconds), so a
            # second start can't connect too and leave two streams running.
            if self.starting is not None:
                raise LinkError("A music show from this computer is already starting"
                                + (" on another page." if self.starting != tab else "."))
            self.starting = tab
        try:
            self._connect_and_run(host, pattern, sensitivity, tab, wanted, clock, sid, color)
        finally:
            with self.lock:
                self.starting = None

    def _connect_and_run(self, host, pattern, sensitivity, tab, wanted, clock, sid, color):
        link = self.link_factory(host)
        link.open()
        try:
            if clock is not None:
                link.read_all(clock())
            link.ping()
            link.music(SOURCE_LEVELS, pattern, sensitivity, color)
        except LinkError:
            link.close()
            raise
        with self.lock:
            self.stop_evt = threading.Event()
            self.state = {"host": host, "pattern": pattern, "sensitivity": sensitivity, "tab": tab, "sid": sid,
                          "color": color,
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

    def adjust(self, tab: str, pattern=None, sensitivity=None, color=None):
        with self.lock:
            st = self.state
            if not st or st["tab"] != tab:
                return False
            p = st["pattern"] if pattern is None else pattern
            s = st["sensitivity"] if sensitivity is None else sensitivity
            c = st.get("color", DEFAULT_COLOR) if color is None else check_color(color)
            music_payload(SOURCE_LEVELS, p, s, color=c)
            st["pattern"], st["sensitivity"], st["color"], st["changed"] = p, s, c, True
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
        sid = (self.state or {}).get("sid")
        next_ping = time.monotonic() + PING_EVERY
        heard = time.monotonic()          # the controller's last keep-alive answer
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
                        link.music(SOURCE_LEVELS, st["pattern"], st["sensitivity"], st.get("color", DEFAULT_COLOR))
                    link.levels(st["pattern"], st["sensitivity"], lv if now - fed < 1.5 else [0] * BANDS,
                                st.get("color", DEFAULT_COLOR))
                    self.sent += 1
                    # 4.1.4: the keep-alive used to wait for its answer (up to
                    # 3 s), and no levels went out meanwhile: the lights froze
                    # on busy Wi-Fi. Answers are now counted as they arrive.
                    if any(m[1] == CMD_PING for m in link.drain()):
                        heard = now
                    if now - heard > ANSWER_WITHIN:
                        raise LinkError(f"The controller stopped answering (nothing for {ANSWER_WITHIN:.0f} seconds).")
                    if now >= next_ping:
                        link.send_ping()
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
                        link.music(SOURCE_LEVELS, st["pattern"], st["sensitivity"], st.get("color", DEFAULT_COLOR))
                        heard = time.monotonic()
                    except LinkError as e2:
                        why, err = "lost", str(e2)
                        break
                stop_evt.wait(SEND_EVERY)
        finally:
            # Nothing is sent to end the show (4.2.1: what earlier versions sent,
            # 04 0e, means "show saved pattern 14"). The app's schedule sends
            # the next pattern when the show ends, which ends music mode.
            link.close()
            with self.lock:
                st = self.state
                if stop_evt.is_set() and st:
                    why = st.get("why", why)
                if self.thread is threading.current_thread() or self.thread is None:
                    self.state = None
                    self.last_error = err
            try:
                self.on_end(why, sid)
            except Exception:
                pass
