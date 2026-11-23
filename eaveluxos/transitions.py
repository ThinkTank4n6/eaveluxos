# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Smart transitions (4.19): a fade between the schedule's patterns, and in
and out when the schedule turns the lights on and off.

The controller has no fade of its own between two patterns. Over the home
network this app can show a still frame live (the preview the Trimlight
app uses while editing), so a fade is a few still frames, each a step from
the old colors to the new ones, then the new pattern itself, which starts
its motion. Only this app's own patterns (custom colors) fade: a built-in
effect or a pattern saved on the controller has colors only the controller
knows. Nothing is saved on the controller and the cloud is never used for
a fade: without the home network the change is simply sent at once.

Frames keep the new pattern's slots (how many bulbs each color covers), so
a frame is never more than the controller's 30 slots; each slot starts from
the color the old pattern had on that slot's first bulb (patterns repeat
along the lights)."""
from __future__ import annotations

FPS = 4                 # still frames a second: what a controller keeps up with (4.13 speed test)
MAX_SECONDS = 10
CHOICES = (0, 2, 3, 5, 8)
BLACK = 0


def fadeable(p) -> bool:
    """A payload whose colors are known: one of this app's own patterns."""
    return (isinstance(p, dict) and p.get("category") == 1 and isinstance(p.get("pixels"), list)
            and 0 < len(p["pixels"]) <= 30)


def _color_at(pixels: list, bulb: int) -> int:
    """The color on this bulb when the pattern repeats along the lights
    (a slot switched off, "X", is dark)."""
    total = sum(max(1, int(p.get("count", 1))) for p in pixels) or 1
    b = bulb % total
    for p in pixels:
        n = max(1, int(p.get("count", 1)))
        if b < n:
            return BLACK if p.get("disable") else int(p.get("color", 0))
        b -= n
    return BLACK


def _mix(a: int, b: int, t: float) -> int:
    out = 0
    for shift in (16, 8, 0):
        ca, cb = (a >> shift) & 255, (b >> shift) & 255
        out |= max(0, min(255, round(ca + (cb - ca) * t))) << shift
    return out


def frames(old, new, seconds: float, fps: int = FPS) -> list[dict]:
    """The still frames from old to new (either may be None: off, which
    fades from or to dark). The last frame is the new colors themselves;
    the caller then sends the real pattern. [] when there's nothing to
    fade (no time, or colors this app doesn't know)."""
    seconds = max(0.0, min(MAX_SECONDS, float(seconds or 0)))
    if seconds <= 0 or (old is None and new is None):
        return []
    if (old is not None and not fadeable(old)) or (new is not None and not fadeable(new)):
        return []
    shape = new if new is not None else old
    slots, start = [], 0
    for p in shape["pixels"]:
        n = max(1, int(p.get("count", 1)))
        to = BLACK if new is None or p.get("disable") else int(p.get("color", 0))
        frm = _color_at(old["pixels"], start) if old is not None else BLACK
        slots.append((n, frm, to, bool(p.get("disable")) and new is not None))
        start += n
    b_old = int(old.get("brightness", 255)) if old is not None else 0
    b_new = int(new.get("brightness", 255)) if new is not None else 0
    if all(frm == to for _, frm, to, _ in slots) and abs(b_old - b_new) < 8:
        # Review #3 (4.19): the same colors sent again (a night-curve step, a
        # rotation to a pattern with these colors): nothing to blend, and
        # still frames would only stop the motion for the fade's length
        return []
    steps = max(2, round(seconds * fps))
    out = []
    for k in range(1, steps + 1):
        t = k / steps
        out.append({"category": 1, "mode": 0, "speed": int(shape.get("speed", 100)),
                    "brightness": max(1, round(b_old + (b_new - b_old) * t)),
                    "pixels": [{"index": i, "count": n, "color": _mix(frm, to, t), "disable": off}
                               for i, (n, frm, to, off) in enumerate(slots)]})
    return out


def check(raw) -> int:
    """settings "transitions": {"fade_seconds": 0 | 2 | 3 | 5 | 8}."""
    from .schedule import ConfigError
    if raw is None:
        return 0
    if not isinstance(raw, dict):
        raise ConfigError("Fades must be {\"fade_seconds\": seconds}.")
    v = raw.get("fade_seconds", 0)
    if isinstance(v, bool) or v not in CHOICES:
        raise ConfigError(f"A fade is {', '.join(map(str, CHOICES[1:]))} seconds, or 0 for none.")
    return v
