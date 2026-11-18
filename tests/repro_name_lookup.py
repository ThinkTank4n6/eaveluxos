# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Review #1 (4.7.4): with this computer's own-name lookup slow (as on the
test Mac), each visit to Setup started another lookup, and an address found
by one that finished late was thrown away, so it never showed. The lookup
is mocked. Run: python3 tests/repro_name_lookup.py"""
import socket, sys, time; from pathlib import Path; sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from unittest import mock
from eaveluxos import server
calls = []
def slow(*a, **k):
    calls.append(1); time.sleep(1.5)
    return [(socket.AF_INET, 0, 0, "", ("192.168.77.9", 0))]
server.NAME_WAIT = 0.2
with mock.patch.object(server.socket, "getaddrinfo", slow), mock.patch.object(server.socket.socket, "connect", side_effect=OSError):
    server._lan_addresses(); server._lan_addresses()
    time.sleep(1.8)
    later = server._lan_addresses()
bad = len(calls) > 2 or "192.168.77.9" not in later
print(f"BUG: {len(calls)} lookups; the late address {'was' if '192.168.77.9' in later else 'was never'} used" if bad
      else f"OK: {len(calls)} lookup(s) at a time, and the late answer is used")
