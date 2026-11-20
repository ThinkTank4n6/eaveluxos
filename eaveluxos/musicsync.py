# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Music sync 2.0 (4.13): zones that follow the music, shown live on the
controller over the home network.

The listening page works out each frame (the zones lit by the bass, mids,
treble or beat; musiczones.js) and sends it here. This app shows it with the
same live-preview message the Trimlight app sends while you edit a pattern
(lanlink.preview_message; it saves nothing on the controller).

How fast a controller can take frames isn't known, so this is careful:

* A controller is used only after its **speed test** (speed_test below):
  short bursts of frames at 2, 4, 6 and 8 a second, each followed by a
  keep-alive whose answer time shows whether the controller kept up. The
  fastest pace with prompt answers is the most a show may use.
* During a show only the latest frame is sent (frames never queue), never
  faster than that pace, and only when it changed.
* A keep-alive goes every second. If the answers slow down (over
  SLOW_MS), the pace drops a step; when they're quick again for a while, it
  rises back toward the tested pace. With no answer for LOST_AFTER seconds,
  or failures over and over, the show stops and the schedule's pattern is
  sent again, as when any music show ends.
"""
from __future__ import annotations

import logging
import statistics
import threading
import time

from . import lanlink as L

log = logging.getLogger("eaveluxos.musicsync")

RATES = (2, 4, 6, 8)          # frames a second the speed test tries, in order
TEST_SECONDS = 2.5            # each rate's burst
SLOW_MS = 400                 # a keep-alive answer slower than this: slow down
OK_MS = 150                   # answers this quick for RISE_AFTER seconds: speed up again
RISE_AFTER = 10.0
CEILING_BACK = 60.0           # quick this long after slowing down: the pace that lagged may be tried again
SLOW_IN_A_ROW = 2             # Review #1 (4.13): one late answer is Wi-Fi; two in a row is the controller
LOST_AFTER = 6.0              # no answer at all for this long: the controller is gone
PING_EVERY = 1.0
IDLE = 20.0                   # no frames from the page for this long: the show ends
TEST_SLOW_MS = 300            # a test rate passes when every answer came within this


def preview_data(colors, counts) -> tuple[int, bytes]:
    """(sub, data) for one frame: colors '#RRGGBB', counts 1-255 each, at
    most 30; shown still (mode 0) at full brightness. Raises ValueError."""
    if not (isinstance(colors, list) and isinstance(counts, list) and 1 <= len(colors) == len(counts) <= L.SLOTS):
        raise ValueError(f"a frame is 1 to {L.SLOTS} colors, each with its number of bulbs")
    slots = []
    for c, n in zip(colors, counts):
        if not (isinstance(c, str) and len(c) == 7 and c[0] == "#"):
            raise ValueError("colors are like #FF6600")
        try:
            v = int(c[1:], 16)
        except ValueError:
            raise ValueError("colors are like #FF6600") from None
        if isinstance(n, bool) or not isinstance(n, int) or not 1 <= n <= 255:
            raise ValueError("each color covers 1 to 255 bulbs")
        slots.append((n, ((v >> 16) & 255, (v >> 8) & 255, v & 255), True))
    rec = L.pattern_record(1, "music", 0, 0, 255, slots)
    return L.SUB_PREVIEW, rec[27:30] + rec[32:]


class _Pinger:
    """Keep-alives sent without waiting, answers counted as they come, so
    the time each one took is known without holding up the frames."""

    def __init__(self, link):
        self.link, self.sent, self.times, self.heard = link, [], [], time.monotonic()

    def ping(self):
        self.link.send_ping()
        self.sent.append(time.monotonic())

    def collect(self):
        for m in self.link.drain() or []:
            if m[1] == L.CMD_PING and self.sent:
                now = time.monotonic()
                self.times.append((now - self.sent.pop(0)) * 1000)
                self.heard = now

    def waiting_ms(self) -> float:
        """How long the oldest unanswered keep-alive has been waiting."""
        return (time.monotonic() - self.sent[0]) * 1000 if self.sent else 0.0


def speed_test(host: str, link_factory=L.Link, clock=None, rates=None, seconds=None,
               sleep=time.sleep) -> dict:
    """Frames at each rate in turn (two dim warm whites, so the lights only
    shimmer), each burst followed by keep-alives. Returns {"fps": the fastest
    rate that kept up (0: none), "rates": [{"fps", "ok", "ms" (slowest
    answer), "median"}]}. Stops at the first rate that doesn't keep up."""
    rates, seconds = rates or RATES, seconds or TEST_SECONDS
    a = preview_data(["#3C2A14"], [255])
    b = preview_data(["#1E150A"], [255])
    link = link_factory(host)
    link.open()
    out, best = [], 0
    try:
        if clock is not None:
            link.read_all(clock())
        link.ping()
        for fps in rates:
            p = _Pinger(link)
            n = max(2, int(fps * seconds))
            for i in range(n):
                link._send(L.frame(L.CMD_REQUEST, L.request(*(a if i % 2 else b))))
                if i % max(1, fps // 2) == 0:
                    p.ping()
                # Listen while waiting, so each answer is timed when it comes, not at the next frame
                until = time.monotonic() + 1 / fps
                while time.monotonic() < until:
                    p.collect()
                    sleep(0.01)
            end = time.monotonic() + 1.5
            while p.sent and time.monotonic() < end:
                sleep(0.02)
                p.collect()
            # Review #2: every keep-alive answered, and all but one quickly (one late answer is Wi-Fi, not the controller)
            ok = not p.sent and bool(p.times) and sorted(p.times)[-2 if len(p.times) > 2 else -1] <= TEST_SLOW_MS
            out.append({"fps": fps, "ok": ok, "ms": round(max(p.times or [0])) if not p.sent else None,
                        "median": round(statistics.median(p.times)) if p.times else None})
            if not ok:
                break
            best = fps
    finally:
        link.close()
    return {"fps": best, "rates": out}


class ZoneStreamer:
    """One controller's zone show: the latest frame, at a careful pace.
    on_end(why, sid) is told why it ended: "stopped", "idle", "app" or
    "lost" (with the reason in .last_error)."""

    def __init__(self, on_end=None, link_factory=L.Link, idle: float = IDLE):
        self.on_end = on_end or (lambda why, sid: None)
        self.link_factory = link_factory
        self.idle = idle
        self.lock = threading.Lock()
        self.state = None
        self.frame = None            # (sub, data) waiting to be sent
        self.fed = 0.0
        self.sent = 0
        self.thread = None
        self.stop_evt = threading.Event()
        self.last_error = None

    def running(self) -> bool:
        return self.state is not None

    def status(self) -> dict:
        st = self.state
        if not st:
            return {"running": False, "error": self.last_error}
        return {"running": True, "host": st["host"], "fps": st["fps"], "max_fps": st["max_fps"], "ms": st.get("ms"),
                "frames": self.sent, "since": st["since"], "slowed": st.get("slowed", 0), "error": None}

    def start(self, host: str, tab: str, max_fps: int, sid: str, wanted=lambda: True, clock=None):
        if not 1 <= int(max_fps) <= max(RATES):
            raise ValueError("Run the speed test first.")
        with self.lock:
            if self.state is not None:
                if self.state["tab"] != tab:
                    raise L.LinkError("A music show from this computer is already running on another page. Stop it there first.")
                return
        link = self.link_factory(host)
        link.open()
        try:
            if clock is not None:
                link.read_all(clock())
            link.ping()
        except L.LinkError:
            link.close()
            raise
        with self.lock:
            self.stop_evt = threading.Event()
            fps = min(4, int(max_fps))
            # ceiling: the most it may rise to again; a pace that lagged is never tried again this show
            self.state = {"host": host, "tab": tab, "sid": sid, "fps": fps, "max_fps": int(max_fps), "ceiling": int(max_fps),
                          "since": time.time()}
            self.frame, self.fed, self.sent, self.last_error = None, time.monotonic(), 0, None
            self.thread = threading.Thread(target=self._run, args=(link, self.stop_evt, wanted), daemon=True,
                                           name="music-zones")
            self.thread.start()

    def feed(self, colors, counts, tab: str) -> bool:
        msg = preview_data(colors, counts)            # ValueError for a bad frame
        with self.lock:
            st = self.state
            if not st or st["tab"] != tab:
                return False
            self.fed = time.monotonic()
            if msg != st.get("last"):
                self.frame = msg
            return True

    def stop(self, tab: str | None = None, why: str = "stopped") -> bool:
        with self.lock:
            st = self.state
            if not st or (tab is not None and st["tab"] != tab):
                return False
            st["why"] = why
            self.stop_evt.set()
            t = self.thread
        if t is not None and t is not threading.current_thread():
            t.join(3)
        return True

    def _run(self, link, stop_evt, wanted):
        why, err = "stopped", None
        sid = (self.state or {}).get("sid")
        p = _Pinger(link)
        next_ping, next_send, quick_since, failures = 0.0, 0.0, time.monotonic(), []
        slow_run, last_ms, waited_for, slowed_at, sent_pings = 0, None, -1, time.monotonic(), 0
        try:
            while not stop_evt.is_set():
                now = time.monotonic()
                with self.lock:
                    st = self.state
                    if not st:
                        break
                    fps, fed = st["fps"], self.fed
                    msg = self.frame if now >= next_send else None
                    if msg is not None:
                        self.frame = None
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
                    if msg is not None:
                        link._send(L.frame(L.CMD_REQUEST, L.request(*msg)))
                        self.sent += 1
                        with self.lock:
                            if self.state:
                                self.state["last"] = msg
                        next_send = now + 1 / fps
                    if now >= next_ping:
                        p.ping()
                        sent_pings += 1
                        next_ping = now + PING_EVERY
                    p.collect()
                    answers, p.times = p.times, []
                    for ms in answers:
                        slow_run = slow_run + 1 if ms > SLOW_MS else 0
                        if ms > OK_MS:
                            quick_since = now
                        last_ms = ms
                    wait = p.waiting_ms()
                    oldest = sent_pings - len(p.sent)               # which keep-alive is still waiting
                    if wait > 3 * SLOW_MS and waited_for != oldest:
                        waited_for = oldest                         # one long wait counts once
                        slow_run += 1
                    with self.lock:
                        if self.state:
                            self.state["ms"] = round(max(last_ms or 0, wait))
                    if now - p.heard > LOST_AFTER:
                        raise L.LinkError(f"The controller stopped answering (nothing for {LOST_AFTER:.0f} seconds).")
                    if slow_run >= SLOW_IN_A_ROW:
                        slow_run, quick_since, slowed_at = 0, now, now
                        with self.lock:
                            if self.state and self.state["fps"] > min(RATES):
                                self.state["ceiling"] = self.state["fps"] - 1
                                self.state["fps"] -= 1
                                self.state["slowed"] = self.state.get("slowed", 0) + 1
                                log.info("Music zones: answers came late; %d frames a second now.", self.state["fps"])
                    elif now - quick_since > RISE_AFTER:
                        quick_since = now
                        with self.lock:
                            st2 = self.state
                            if st2 and now - slowed_at > CEILING_BACK and st2["ceiling"] < st2["max_fps"]:
                                st2["ceiling"] += 1
                                slowed_at = now
                            if st2 and st2["fps"] < st2["ceiling"]:
                                st2["fps"] += 1
                except L.LinkError as e:
                    failures = [t for t in failures if now - t < 60] + [now]
                    link.close()
                    if len(failures) >= 2:
                        why, err = "lost", str(e)
                        break
                    try:
                        link = self.link_factory(self.state["host"]).open()
                        link.ping()          # the controller takes requests on a connection after a keep-alive
                        p = _Pinger(link)
                    except (L.LinkError, TypeError) as e2:
                        why, err = "lost", str(e2)
                        break
                stop_evt.wait(0.02)
        finally:
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
