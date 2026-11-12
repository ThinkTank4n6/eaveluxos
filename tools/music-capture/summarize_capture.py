#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Summarize a packet capture of the Trimlight Edge app talking to a
controller on the home network, to learn how music mode is switched on.

    python3 summarize_capture.py capture.pcapng --controller 192.168.1.50 \\
        --marks marks.txt --out report.md

Reads classic pcap and pcapng (Ethernet, raw IP, Linux cooked, BSD loopback,
Apple PKTAP). Standard library only. TCP segments are listed as captured, not
reassembled. Nothing is sent anywhere; the report is a local file.

marks.txt: one line per thing you did, the time as shown on the capture
computer's clock, then a label:
    20:15:05 opened Music page
    20:15:30 chose Auxiliary IN
"""
import argparse
import ipaddress
import re
import struct
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime

# ------------------------------------------------------------------ reading


@dataclass
class Packet:
    ts: float
    src: str
    dst: str
    proto: str          # "TCP" | "UDP"
    sport: int
    dport: int
    payload: bytes
    flags: str = ""     # TCP flags, e.g. "S", "SA", "PA"


def _ip(data: bytes):
    """(src, dst, l4proto, l4data) for an IPv4/IPv6 packet, or None."""
    if not data:
        return None
    v = data[0] >> 4
    if v == 4 and len(data) >= 20:
        ihl = (data[0] & 15) * 4
        total = struct.unpack("!H", data[2:4])[0] or len(data)
        frag = struct.unpack("!H", data[6:8])[0] & 0x1FFF
        if frag:
            return None   # later fragments carry no port header
        return (str(ipaddress.IPv4Address(data[12:16])), str(ipaddress.IPv4Address(data[16:20])),
                data[9], data[ihl:total])
    if v == 6 and len(data) >= 40:
        nxt, off = data[6], 40
        plen = struct.unpack("!H", data[4:6])[0]
        end = 40 + plen if plen else len(data)
        while nxt in (0, 43, 60) and off + 8 <= len(data):   # hop-by-hop, routing, dest options
            nxt, off = data[off], off + (data[off + 1] + 1) * 8
        return (str(ipaddress.IPv6Address(data[8:24])), str(ipaddress.IPv6Address(data[24:40])), nxt, data[off:end])
    return None


def _l4(ts, ipinfo):
    if ipinfo is None:
        return None
    src, dst, proto, d = ipinfo
    if proto == 17 and len(d) >= 8:
        sp, dp, ln = struct.unpack("!HHH", d[:6])
        return Packet(ts, src, dst, "UDP", sp, dp, d[8:ln] if ln >= 8 else d[8:])
    if proto == 6 and len(d) >= 20:
        sp, dp = struct.unpack("!HH", d[:4])
        off = (d[12] >> 4) * 4
        fl = d[13]
        flags = "".join(c for c, bit in (("F", 1), ("S", 2), ("R", 4), ("P", 8), ("A", 16)) if fl & bit)
        return Packet(ts, src, dst, "TCP", sp, dp, d[off:], flags)
    return None


def _from_link(link: int, data: bytes, ts: float):
    if link == 1:                                        # Ethernet (with VLAN tags)
        if len(data) < 14:
            return None
        et, off = struct.unpack("!H", data[12:14])[0], 14
        while et in (0x8100, 0x88A8) and len(data) >= off + 4:
            et, off = struct.unpack("!H", data[off + 2:off + 4])[0], off + 4
        return _l4(ts, _ip(data[off:])) if et in (0x0800, 0x86DD) else None
    if link in (101, 12, 14, 228, 229):                  # raw IP
        return _l4(ts, _ip(data))
    if link in (0, 108):                                 # BSD null / loopback
        return _l4(ts, _ip(data[4:]))
    if link == 113:                                      # Linux cooked v1
        return _l4(ts, _ip(data[16:]))
    if link == 276:                                      # Linux cooked v2
        return _l4(ts, _ip(data[20:]))
    if link == 258 and len(data) >= 8:                   # Apple PKTAP (rvictl)
        hlen, inner = struct.unpack("<II", data[:8])
        return _from_link(inner, data[hlen:], ts)
    return None


def read_packets(path: str):
    """(packets, link types seen)."""
    raw = open(path, "rb").read()
    if raw[:4] == b"\x0a\x0d\x0d\x0a":
        return _read_pcapng(raw)
    return _read_pcap(raw)


def _read_pcap(raw: bytes):
    magic = raw[:4]
    table = {b"\xd4\xc3\xb2\xa1": ("<", 1e-6), b"\xa1\xb2\xc3\xd4": (">", 1e-6),
             b"\x4d\x3c\xb2\xa1": ("<", 1e-9), b"\xa1\xb2\x3c\x4d": (">", 1e-9)}
    if magic not in table:
        raise ValueError("Not a pcap or pcapng file.")
    e, res = table[magic]
    link = struct.unpack(e + "I", raw[20:24])[0] & 0x0FFFFFFF
    out, off = [], 24
    while off + 16 <= len(raw):
        sec, frac, incl, _orig = struct.unpack(e + "IIII", raw[off:off + 16])
        data = raw[off + 16:off + 16 + incl]
        off += 16 + incl
        p = _from_link(link, data, sec + frac * res)
        if p:
            out.append(p)
    return out, {link}


def _read_pcapng(raw: bytes):
    out, links, ifaces, e, off = [], set(), [], "<", 0
    while off + 12 <= len(raw):
        btype = struct.unpack(e + "I", raw[off:off + 4])[0]
        if btype == 0x0A0D0D0A:                          # section header: byte order
            e = "<" if raw[off + 8:off + 12] == b"\x4d\x3c\x2b\x1a" else ">"
            ifaces = []
        blen = struct.unpack(e + "I", raw[off + 4:off + 8])[0]
        if blen < 12 or off + blen > len(raw):
            break
        body = raw[off + 8:off + blen - 4]
        if btype == 1:                                   # interface description
            link = struct.unpack(e + "H", body[:2])[0]
            res, o = 1e-6, 8
            while o + 4 <= len(body):
                code, ln = struct.unpack(e + "HH", body[o:o + 4])
                if code == 0:
                    break
                if code == 9 and ln >= 1:                # if_tsresol
                    v = body[o + 4]
                    res = 2.0 ** -(v & 0x7F) if v & 0x80 else 10.0 ** -v
                o += 4 + ((ln + 3) & ~3)
            ifaces.append((link, res))
            links.add(link)
        elif btype in (6, 2):                            # enhanced / obsolete packet
            iid = struct.unpack(e + "I", body[:4])[0] if btype == 6 else struct.unpack(e + "H", body[:2])[0]
            hi, lo, cap = struct.unpack(e + "III", body[4:16] if btype == 6 else body[4:16])
            if iid < len(ifaces):
                link, res = ifaces[iid]
                p = _from_link(link, body[20:20 + cap], ((hi << 32) | lo) * res)
                if p:
                    out.append(p)
        elif btype == 3 and ifaces:                      # simple packet (no time)
            link, _ = ifaces[0]
            p = _from_link(link, body[4:], 0.0)
            if p:
                out.append(p)
        off += blen
    return out, links


# ------------------------------------------------------------------ analysis


def is_group(a: str) -> bool:
    """Broadcast or multicast: how apps usually find devices on the network."""
    ip = ipaddress.ip_address(a)
    return ip.is_multicast or a == "255.255.255.255" or (ip.version == 4 and a.endswith(".255"))


def is_lan(a: str) -> bool:
    ip = ipaddress.ip_address(a)
    return ip.is_private or ip.is_link_local or ip.is_multicast or a == "255.255.255.255"


def read_marks(path: str | None, day_of: float | None):
    if not path:
        return []
    marks = []
    base = datetime.fromtimestamp(day_of) if day_of else datetime.now()
    for line in open(path, encoding="utf-8"):
        m = re.match(r"\s*(\d{1,2}):(\d{2})(?::(\d{2}))?\s+(.+?)\s*$", line)
        if m:
            t = base.replace(hour=int(m[1]), minute=int(m[2]), second=int(m[3] or 0), microsecond=0)
            marks.append((t.timestamp(), m[4]))
    return sorted(marks)


def hexdump(b: bytes, n: int = 48) -> str:
    h = b[:n].hex(" ")
    return h + (" …" if len(b) > n else "")


def printable(b: bytes, n: int = 48) -> str:
    return "".join(chr(c) if 32 <= c < 127 else "." for c in b[:n])


def varying_bytes(msgs: list[bytes]) -> list[int]:
    """Byte positions that differ across messages of the same shape."""
    if len(msgs) < 2:
        return []
    n = min(len(m) for m in msgs)
    return [i for i in range(n) if len({m[i] for m in msgs}) > 1]


@dataclass
class Flow:
    proto: str
    a: tuple
    b: tuple
    packets: int = 0
    payload_packets: int = 0
    bytes: int = 0
    first: float = 0.0
    last: float = 0.0
    items: list = field(default_factory=list)


def analyze(packets, controller: str | None, marks):
    flows: dict[tuple, Flow] = {}
    for p in packets:
        ends = sorted([(p.src, p.sport), (p.dst, p.dport)])
        k = (p.proto, *ends)
        f = flows.get(k)
        if f is None:
            f = flows[k] = Flow(p.proto, ends[0], ends[1], first=p.ts)
        f.packets += 1
        f.bytes += len(p.payload)
        f.last = p.ts
        if p.payload:
            f.payload_packets += 1
            f.items.append(p)
    lan = [f for f in flows.values() if is_lan(f.a[0]) and is_lan(f.b[0])]
    if controller:
        # The controller's own traffic, plus broadcasts: discovery is sent to
        # everyone, not to the controller's address.
        focus = [f for f in lan if controller in (f.a[0], f.b[0]) or is_group(f.a[0]) or is_group(f.b[0])]
    else:
        focus = lan
    return flows, lan, focus


def is_stream(f) -> bool:
    """Many small messages a second for a while: live data, not commands."""
    dur = f.last - f.first
    return dur >= 5 and f.payload_packets / dur >= 10


def mark_for(ts: float, marks):
    label = None
    for t, l in marks:
        if t <= ts:
            label = l
    return label


def report(path: str, packets, links, controller, marks) -> str:
    flows, lan, focus = analyze(packets, controller, marks)
    L = []
    w = L.append
    ts = [p.ts for p in packets if p.ts]
    w("# Trimlight capture summary\n")
    w(f"- File: `{path}`")
    w(f"- Packets with a TCP/UDP payload header: {len(packets)}; link types: {sorted(links)}")
    if ts:
        w(f"- Time span: {datetime.fromtimestamp(min(ts)):%Y-%m-%d %H:%M:%S} to "
          f"{datetime.fromtimestamp(max(ts)):%H:%M:%S} (this computer's clock)")
    w(f"- Controller address: {controller or 'not given (showing all home-network traffic)'}")
    w(f"- Internet flows left out: {len(flows) - len(lan)} (only home-network traffic is reported)\n")
    if controller and not any(controller in (f.a[0], f.b[0]) for f in focus):
        peers = Counter()
        for f in lan:
            for end in (f.a, f.b):
                peers[end[0]] += f.packets
        w("**No traffic to or from that address.** Busiest home-network addresses in the capture:\n")
        for a, n in peers.most_common(10):
            w(f"- {a}: {n} packets")
        return "\n".join(L) + "\n"

    w("## Marks\n")
    w("\n".join(f"- {datetime.fromtimestamp(t):%H:%M:%S} {l}" for t, l in marks) or "_None given._")
    w("\n## Conversations\n")
    w("| Proto | Endpoint A | Endpoint B | Packets | With data | Data bytes | Seconds | Note |")
    w("|---|---|---|---|---|---|---|---|")
    for f in sorted(focus, key=lambda f: -f.packets):
        dur = max(0.0, f.last - f.first)
        rate = f.payload_packets / dur if dur > 0 else 0
        note = []
        if is_group(f.a[0]) or is_group(f.b[0]):
            note.append("broadcast/multicast (discovery?)")
        if is_stream(f):
            note.append(f"steady {rate:.0f}/s stream (live data?)")
        w(f"| {f.proto} | {f.a[0]}:{f.a[1]} | {f.b[0]}:{f.b[1]} | {f.packets} | {f.payload_packets} | {f.bytes} | "
          f"{dur:.1f} | {'; '.join(note)} |")

    for f in sorted(focus, key=lambda f: f.first):
        if not f.items:
            continue
        w(f"\n## {f.proto} {f.a[0]}:{f.a[1]} ↔ {f.b[0]}:{f.b[1]}\n")
        shapes = defaultdict(list)
        for p in f.items:
            shapes[(len(p.payload), p.payload[:2])].append(p.payload)
        w("### Message shapes\n")
        w("Same length and same first 2 bytes. Byte positions count from 0; the ones that change are "
          "where settings or live values are likely to be.\n")
        w("| Count | Length | First bytes | Bytes that change | Example |")
        w("|---|---|---|---|---|")
        for (ln, _), msgs in sorted(shapes.items(), key=lambda kv: -len(kv[1]))[:25]:
            vb = varying_bytes(msgs)
            vbs = ", ".join(map(str, vb[:16])) + (" …" if len(vb) > 16 else "") if vb else "none"
            w(f"| {len(msgs)} | {ln} | `{msgs[0][:4].hex(' ')}` | {vbs} | `{hexdump(msgs[0], 24)}` |")
        w("\n### Timeline\n")
        w("| Time | Mark | Direction | Len | Hex | Text |")
        w("|---|---|---|---|---|---|")
        shown, last_key, repeats = 0, None, 0
        limit = 20 if is_stream(f) else 400
        for p in f.items:
            arrow = f"{p.src} → {p.dst}"
            key = (p.src, p.payload)
            if key == last_key:              # collapse identical repeats (keep-alives, streams)
                repeats += 1
                continue
            if repeats:
                w(f"|  |  | (same message repeated {repeats} more times) |  |  |  |")
                repeats = 0
            last_key = key
            if shown >= limit:
                left = len(f.items) - f.items.index(p)
                w(f"|  |  | ({left} more messages not listed{'; a live stream, see Message shapes' if limit == 20 else ''}) "
                  "|  |  |  |")
                repeats = 0
                break
            shown += 1
            w(f"| {datetime.fromtimestamp(p.ts):%H:%M:%S.%f}"[:-3] + f" | {mark_for(p.ts, marks) or ''} | {arrow} | "
              f"{len(p.payload)} | `{hexdump(p.payload)}` | `{printable(p.payload).replace('|', '¦')}` |")
        if repeats:
            w(f"|  |  | (same message repeated {repeats} more times) |  |  |  |")
    w("\n---\nCheck this report before sharing it: it can contain your controller's ID or name. "
      "Don't share captures made while pairing the controller to Wi-Fi, which can include your Wi-Fi password.")
    return "\n".join(L) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("capture", help="a .pcap or .pcapng file")
    ap.add_argument("--controller", help="the controller's IP address on your network")
    ap.add_argument("--marks", help="text file of 'HH:MM:SS what you did' lines")
    ap.add_argument("--out", help="write the report here (default: print it)")
    a = ap.parse_args(argv)
    try:
        packets, links = read_packets(a.capture)
    except (OSError, ValueError, struct.error) as e:
        print(f"Couldn't read {a.capture}: {e}", file=sys.stderr)
        return 1
    if a.controller:
        try:
            ipaddress.ip_address(a.controller)
        except ValueError:
            print("--controller must be an IP address, like 192.168.1.50", file=sys.stderr)
            return 1
    first = next((p.ts for p in packets if p.ts), None)
    text = report(a.capture, packets, links, a.controller, read_marks(a.marks, first))
    if a.out:
        open(a.out, "w", encoding="utf-8").write(text)
        print(f"Report written to {a.out}")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
