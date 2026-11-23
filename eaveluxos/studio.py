# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Studio (4.20): the advanced effect editor.

  Layers     a look is built from a base (one color, or a gradient through up
             to 6 colors) and up to 4 layers on top: an accent color every N
             bulbs, or a band of bulbs. compose() turns it into what the
             controller plays: up to 30 colors, each over 1 to 90 bulbs,
             repeating along the lights, with one of its motions.
  Keyframes  a show is looks in order, each for some minutes, with a fade
             between them (4.19 fades). Saved, the looks become your patterns
             and the show a schedule rule that plays them in turn.
  Words      describe a show ("deep blue for 10 minutes, then fade to purple,
             then white sparkle") and it's laid out as keyframes to change,
             play on the lights and approve (from_words).

Everything here is plain data in and out: the controller only ever gets an
ordinary pattern of this app's, shown live over the home network or sent as
the schedule sends any pattern."""
from __future__ import annotations

import re

from .catalog import CUSTOM_MODES

MAX_SLOTS = 30
MAX_PER_SLOT = 90
MAX_LENGTH = 300            # bulbs in one repeat of a look
MAX_LAYERS = 4
MAX_STOPS = 6
MAX_KEYFRAMES = 12
_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _rgb(h: str) -> tuple:
    return int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)


def _hex(c) -> str:
    return "#" + "".join(f"{max(0, min(255, round(v))):02X}" for v in c)


def _color(v, where: str) -> str:
    if not isinstance(v, str) or not _HEX.match(v):
        raise ValueError(f"{where}: a color is like #FF6600.")
    return v.upper()


def _int(v, lo, hi, where) -> int:
    if isinstance(v, bool) or not isinstance(v, int) or not lo <= v <= hi:
        raise ValueError(f"{where}: a whole number from {lo} to {hi}.")
    return v


def gradient(stops: list, n: int) -> list[str]:
    """n colors through the stops ([{"color", "at": 0..1}], or plain colors
    spread evenly)."""
    if not stops:
        raise ValueError("A gradient needs at least one color.")
    pts = []
    for i, s in enumerate(stops[:MAX_STOPS]):
        if isinstance(s, str):
            s = {"color": s, "at": i / max(1, min(len(stops), MAX_STOPS) - 1)}
        if not isinstance(s, dict):
            raise ValueError("A gradient stop is a color and where it is.")
        at = s.get("at", i / max(1, len(stops) - 1))
        if isinstance(at, bool) or not isinstance(at, (int, float)) or not 0 <= at <= 1:
            raise ValueError("A gradient stop is from 0 (start) to 1 (end).")
        pts.append((float(at), _rgb(_color(s.get("color"), "Gradient"))))
    pts.sort()
    out = []
    for k in range(n):
        t = k / max(1, n - 1)
        if t <= pts[0][0]:
            out.append(_hex(pts[0][1]))
            continue
        for (a, ca), (b, cb) in zip(pts, pts[1:]):
            if a <= t <= b:
                f = 0 if b == a else (t - a) / (b - a)
                out.append(_hex([x + (y - x) * f for x, y in zip(ca, cb)]))
                break
        else:
            out.append(_hex(pts[-1][1]))
    return out


def _runs(bulbs: list[str]) -> list[list]:
    runs = []
    for c in bulbs:
        if runs and runs[-1][0] == c and runs[-1][1] < MAX_PER_SLOT:
            runs[-1][1] += 1
        else:
            runs.append([c, 1])
    return runs


def _dist(a: str, b: str) -> int:
    return sum((x - y) ** 2 for x, y in zip(_rgb(a), _rgb(b)))


def _fit(runs: list[list]) -> list[list]:
    """At most 30 slots: merge the two neighboring runs whose colors are
    closest (a gradient loses a few in-between shades, layers keep theirs),
    the merged run taking the longer one's color."""
    runs = [list(r) for r in runs]
    while len(runs) > MAX_SLOTS:
        i = min(range(len(runs) - 1), key=lambda k: (_dist(runs[k][0], runs[k + 1][0]), runs[k][1] + runs[k + 1][1]))
        a, b = runs[i], runs[i + 1]
        if a[1] + b[1] > MAX_PER_SLOT:
            # too long to merge: shorten the longer one's share instead
            keep = a if a[1] >= b[1] else b
            runs[i:i + 2] = [[keep[0], MAX_PER_SLOT]]
        else:
            runs[i:i + 2] = [[a[0] if a[1] >= b[1] else b[0], a[1] + b[1]]]
    return runs


def compose(spec: dict) -> dict:
    """A look -> a pattern of this app's: {"label", "colors", "counts",
    "custom_mode", "speed", "brightness", "bulbs" (what one repeat looks
    like, for the screen)}. Raises ValueError with what's wrong."""
    if not isinstance(spec, dict):
        raise ValueError("A look is a base and its layers.")
    n = _int(spec.get("length", 30), 2, MAX_LENGTH, "Bulbs in one repeat")
    base = spec.get("base") or {"type": "solid", "color": "#FFFFFF"}
    kind = base.get("type") if isinstance(base, dict) else None
    if kind == "solid":
        bulbs = [_color(base.get("color"), "Base")] * n
    elif kind == "gradient":
        stops = base.get("stops")
        if not isinstance(stops, list) or not 1 <= len(stops) <= MAX_STOPS:
            raise ValueError(f"A gradient has 1 to {MAX_STOPS} colors.")
        bulbs = gradient(stops, n)
        if base.get("mirror"):
            half = gradient(stops, (n + 1) // 2)
            bulbs = (half + half[::-1])[:n]
    else:
        raise ValueError("The base is one color or a gradient.")
    layers = spec.get("layers") or []
    if not isinstance(layers, list) or len(layers) > MAX_LAYERS:
        raise ValueError(f"Up to {MAX_LAYERS} layers.")
    for k, ly in enumerate(layers, 1):
        if not isinstance(ly, dict):
            raise ValueError(f"Layer {k} isn't readable.")
        col = _color(ly.get("color"), f"Layer {k}")
        if ly.get("type") == "accent":
            every = _int(ly.get("every", 5), 2, n, f"Layer {k}: every")
            width = _int(ly.get("width", 1), 1, every - 1, f"Layer {k}: bulbs lit")
            off = _int(ly.get("offset", 0), 0, every - 1, f"Layer {k}: offset")
            for i in range(n):
                if (i - off) % every < width:
                    bulbs[i] = col
        elif ly.get("type") == "band":
            start = _int(ly.get("start", 0), 0, n - 1, f"Layer {k}: start")
            width = _int(ly.get("width", 3), 1, n, f"Layer {k}: width")
            for i in range(start, min(n, start + width)):
                bulbs[i] = col
        else:
            raise ValueError(f"Layer {k} is an accent or a band.")
    motion = spec.get("motion", "Static")
    if motion not in CUSTOM_MODES:
        raise ValueError("Choose one of the controller's motions.")
    speed = _int(spec.get("speed", 100), 0, 255, "Speed")
    bright = _int(spec.get("brightness", 200), 1, 255, "Brightness")
    runs = _fit(_runs(bulbs))
    label = str(spec.get("label") or "Studio look").strip()[:40] or "Studio look"
    return {"label": label, "colors": [r[0] for r in runs], "counts": [r[1] for r in runs],
            "custom_mode": CUSTOM_MODES.index(motion), "speed": speed, "brightness": bright,
            "bulbs": [c for r in runs for c in [r[0]] * r[1]]}


def check_pattern(p, where="Keyframe") -> dict:
    """A keyframe's pattern (from compose, the words, or one of yours copied
    in): the fields a pattern of this app's has, checked."""
    if not isinstance(p, dict):
        raise ValueError(f"{where}: no pattern.")
    cols, counts = p.get("colors"), p.get("counts")
    if not isinstance(cols, list) or not 1 <= len(cols) <= MAX_SLOTS:
        raise ValueError(f"{where}: 1 to {MAX_SLOTS} colors.")
    counts = counts if isinstance(counts, list) and len(counts) == len(cols) else [3] * len(cols)
    out = {"label": str(p.get("label") or "Studio look").strip()[:40] or "Studio look",
           "colors": [_color(c, where) for c in cols],
           "counts": [_int(n, 1, MAX_PER_SLOT, f"{where}: bulbs per color") for n in counts],
           "custom_mode": _int(p.get("custom_mode", 0), 0, len(CUSTOM_MODES) - 1, f"{where}: motion"),
           "speed": _int(p.get("speed", 100), 0, 255, f"{where}: speed"),
           "brightness": _int(p.get("brightness", 200), 1, 255, f"{where}: brightness")}
    return out


def check_show(raw) -> dict:
    """{"name", "keyframes": [{"pattern", "minutes"}], "fade": seconds}."""
    from .transitions import CHOICES
    if not isinstance(raw, dict):
        raise ValueError("A show is its keyframes.")
    kfs = raw.get("keyframes")
    if not isinstance(kfs, list) or not 1 <= len(kfs) <= MAX_KEYFRAMES:
        raise ValueError(f"A show has 1 to {MAX_KEYFRAMES} keyframes.")
    out = []
    for i, k in enumerate(kfs, 1):
        if not isinstance(k, dict):
            raise ValueError(f"Keyframe {i} isn't readable.")
        out.append({"pattern": check_pattern(k.get("pattern"), f"Keyframe {i}"),
                    "minutes": _int(k.get("minutes", 10), 1, 240, f"Keyframe {i}: minutes")})
    fade = raw.get("fade", 3)
    if isinstance(fade, bool) or fade not in CHOICES:
        raise ValueError("A fade is 0, 2, 3, 5 or 8 seconds.")
    name = " ".join(str(raw.get("name") or "").split())[:40]
    return {"name": name or "Studio show", "keyframes": out, "fade": fade}


# ---------------------------------------------------------------- words
_SPLIT = re.compile(r"\s*(?:,?\s*\bthen\b|;|->|→|\band after that\b|\bfollowed by\b)\s*", re.I)
_MIN = re.compile(r"\b(?:for|over)?\s*(\d{1,3})\s*(?:min|mins|minute|minutes)\b", re.I)
_HOUR = re.compile(r"\b(?:for|over)?\s*(\d{1,2})\s*(?:h|hr|hrs|hour|hours)\b", re.I)
_SEC = re.compile(r"\b(?:over|in)\s*(\d{1,2})\s*(?:s|sec|secs|second|seconds)\b", re.I)
_FADE = re.compile(r"\b(fade|fades|fading|blend|melt|morph|dissolve)s?\b", re.I)


def from_words(text: str, gen=None) -> dict:
    """A show from a description: each part (split at "then", ";", "->")
    becomes a keyframe with the built-in designer (textpattern.generate, or
    `gen`), "for 10 minutes" its length, and "fade" / "over 5 seconds" the
    fade between them. Returns a show (check_show's shape) and "why"."""
    from . import textpattern
    from .transitions import CHOICES
    gen = gen or textpattern.generate
    text = str(text or "").strip()[:400]
    if not text:
        raise ValueError("Describe the show, for example “deep blue for 10 minutes, then fade to purple”.")
    parts = [p for p in _SPLIT.split(text) if p and p.strip(" ,.")][:MAX_KEYFRAMES]
    kfs, why, fade = [], [], 0
    for p in parts:
        minutes = 10
        m, h = _MIN.search(p), _HOUR.search(p)
        if m:
            minutes = max(1, min(240, int(m.group(1))))
        elif h:
            minutes = max(1, min(240, int(h.group(1)) * 60))
        s = _SEC.search(p)
        if s:
            fade = int(s.group(1))
        elif _FADE.search(p) and not fade:
            fade = 3
        words = _FADE.sub(" ", _SEC.sub(" ", _HOUR.sub(" ", _MIN.sub(" ", p))))
        words = re.sub(r"\b(to|into|then|start with|begin with|start|end with)\b", " ", words, flags=re.I).strip(" ,.")
        if not words:
            continue
        pat = gen(words)
        kfs.append({"pattern": check_pattern({k: pat.get(k) for k in ("label", "colors", "counts", "custom_mode",
                                                                         "speed", "brightness")}),
                    "minutes": minutes})
        why.append(f"{pat.get('label')}: {minutes} min" + (f" ({pat.get('why')})" if pat.get("why") else ""))
    if not kfs:
        raise ValueError("No colors or themes found in that. Try “warm white, then fade to candy cane”.")
    fade = min(CHOICES, key=lambda c: abs(c - fade)) if fade else (3 if len(kfs) > 1 else 0)
    return {"name": " → ".join(k["pattern"]["label"] for k in kfs)[:40], "keyframes": kfs, "fade": fade,
            "why": "; ".join(why) + (f"; fade {fade} s" if fade else "")}


def save_plan(show: dict, effects: dict, slug_taken=None) -> tuple[dict, list[str]]:
    """The patterns a show adds ({key: pattern}) and their keys in order. A
    key never replaces one of yours."""
    base = re.sub(r"[^a-z0-9]+", "_", show["name"].lower()).strip("_")[:24] or "show"
    taken = set(effects) | set(slug_taken or ())
    add, keys = {}, []
    for i, k in enumerate(show["keyframes"], 1):
        key, n = f"studio_{base}_{i}", 2
        while key in taken:
            key, n = f"studio_{base}_{i}_{n}", n + 1
        taken.add(key)
        add[key] = dict(k["pattern"])
        keys.append(key)
    return add, keys
