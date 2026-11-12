# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""tools/music-capture/summarize_capture.py on synthetic captures."""
import importlib.util
import shutil
import struct
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("summarize_capture", ROOT / "tools" / "music-capture" / "summarize_capture.py")
SC = importlib.util.module_from_spec(spec)
spec.loader.exec_module(SC)

PHONE, CTRL, NET = "192.168.1.20", "192.168.1.50", "52.10.0.1"
T0 = datetime(2026, 12, 4, 20, 15, 0).timestamp()


def ipv4(src, dst, proto, l4):
    hdr = struct.pack("!BBHHHBBH4s4s", 0x45, 0, 20 + len(l4), 1, 0, 64, proto, 0,
                      bytes(map(int, src.split("."))), bytes(map(int, dst.split("."))))
    return hdr + l4


def udp(src, dst, sp, dp, data):
    return ipv4(src, dst, 17, struct.pack("!HHHH", sp, dp, 8 + len(data), 0) + data)


def tcp(src, dst, sp, dp, data, flags=0x18):
    return ipv4(src, dst, 6, struct.pack("!HHIIBBHHH", sp, dp, 1, 1, 5 << 4, flags, 65535, 0, 0) + data)


def ether(ip):
    return b"\x11" * 6 + b"\x22" * 6 + b"\x08\x00" + ip


def scenario():
    """(ts, raw IP packet): discovery, a command exchange, a stream, internet noise."""
    out = [(T0, udp(PHONE, "255.255.255.255", 50000, 8189, b"TLDISCOVER"))]
    out.append((T0 + 0.1, udp(CTRL, PHONE, 8189, 50000, b"TLHERE edge-01")))
    # "open music page", then "choose aux": same shape, byte 5 differs (the mode)
    out.append((T0 + 30, tcp(PHONE, CTRL, 51000, 8189, bytes([0xAA, 0x55, 0x10, 0x03, 0x01, 0x00, 0x7F]))))
    out.append((T0 + 30.05, tcp(CTRL, PHONE, 8189, 51000, b"\xAA\x55\x90\x00")))
    out.append((T0 + 45, tcp(PHONE, CTRL, 51000, 8189, bytes([0xAA, 0x55, 0x10, 0x03, 0x01, 0x02, 0x7F]))))
    # microphone mode: 20 levels a second for 8 s, values changing
    for i in range(160):
        out.append((T0 + 60 + i / 20, udp(PHONE, CTRL, 52000, 8190, bytes([0xBB, 0x01, i % 256, (i * 7) % 256]))))
    out.append((T0 + 61, tcp(PHONE, NET, 52344, 443, b"\x16\x03\x01 cloud")))   # internet: left out
    return sorted(out)


def write_pcap(path, items, link=1):
    with open(path, "wb") as f:
        f.write(struct.pack("<IHHiIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, link))
        for ts, ip in items:
            data = ether(ip) if link == 1 else ip
            sec = int(ts)
            f.write(struct.pack("<IIII", sec, int((ts - sec) * 1e6), len(data), len(data)) + data)


def write_pcapng(path, items, link=101):
    def block(btype, body):
        body += b"\x00" * ((4 - len(body) % 4) % 4)
        n = 12 + len(body)
        return struct.pack("<II", btype, n) + body + struct.pack("<I", n)
    with open(path, "wb") as f:
        f.write(block(0x0A0D0D0A, struct.pack("<IHHq", 0x1A2B3C4D, 1, 0, -1)))
        opts = struct.pack("<HHB3x", 9, 1, 9) + struct.pack("<HH", 0, 0)        # nanosecond timestamps
        f.write(block(1, struct.pack("<HHI", link, 0, 65535) + opts))
        for ts, ip in items:
            t = int(round(ts * 1e9))
            f.write(block(6, struct.pack("<IIIII", 0, t >> 32, t & 0xFFFFFFFF, len(ip), len(ip)) + ip))


class CaptureToolTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def check_report(self, cap):
        marks = self.dir / "marks.txt"
        marks.write_text("20:15:29 opened Music page\n20:15:44 chose Auxiliary IN\n20:16:00 microphone mode\n")
        out = self.dir / "report.md"
        self.assertEqual(SC.main([str(cap), "--controller", CTRL, "--marks", str(marks), "--out", str(out)]), 0)
        r = out.read_text(encoding="utf-8")
        self.assertNotIn(NET, r)                                   # internet traffic left out
        self.assertIn("broadcast/multicast (discovery?)", r)
        self.assertIn("steady 20/s stream", r)
        self.assertIn("| 2 | 7 | `aa 55 10 03` | 5 |", r)         # the command, and the byte that changed
        self.assertIn("chose Auxiliary IN", r)
        self.assertIn("TLHERE edge-01", r)
        self.assertIn("TLDISCOVER", r)                            # the broadcast itself is kept
        self.assertIn("| 160 | 4 | `bb 01 00 00` | 2, 3 |", r)     # the stream is one shape
        self.assertIn("140 more messages not listed; a live stream", r)
        self.assertLess(r.count("| microphone mode |"), 25)
        return r

    def test_classic_pcap_ethernet(self):
        cap = self.dir / "c.pcap"
        write_pcap(cap, scenario())
        self.check_report(cap)

    def test_pcapng_raw_ip_nanoseconds(self):
        cap = self.dir / "c.pcapng"
        write_pcapng(cap, scenario())
        pk, links = SC.read_packets(str(cap))
        self.assertEqual(links, {101})
        self.assertAlmostEqual(pk[0].ts, T0, places=3)
        self.check_report(cap)

    def test_wrong_controller_lists_busy_addresses(self):
        cap = self.dir / "c.pcap"
        write_pcap(cap, scenario())
        out = self.dir / "r.md"
        SC.main([str(cap), "--controller", "192.168.1.99", "--out", str(out)])
        r = out.read_text(encoding="utf-8")
        self.assertIn("No traffic to or from that address", r)
        self.assertNotIn("TLDISCOVER", r)
        self.assertIn(CTRL, r)

    def test_other_link_types(self):
        ip = udp(PHONE, CTRL, 1, 2, b"x")
        self.assertEqual(SC._from_link(113, b"\x00" * 16 + ip, 0).payload, b"x")              # Linux cooked
        self.assertEqual(SC._from_link(0, b"\x02\x00\x00\x00" + ip, 0).payload, b"x")         # BSD loopback
        pktap = struct.pack("<II", 12, 101) + b"\x00" * 4 + ip                               # Apple rvictl
        self.assertEqual(SC._from_link(258, pktap, 0).dst, CTRL)

    def test_not_a_capture(self):
        bad = self.dir / "x.pcap"
        bad.write_bytes(b"hello world, not a capture")
        self.assertEqual(SC.main([str(bad)]), 1)


if __name__ == "__main__":
    unittest.main()
