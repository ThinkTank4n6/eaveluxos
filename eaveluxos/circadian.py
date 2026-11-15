# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Night curves (3.18): a rule's brightness and white color temperature
change through the night, for example crisp 5000 K at dusk, 2700 K from
9 PM, a 15% glow after midnight.

A curve is 2 to 6 points: {"at": a time like "sunset", "21:00" or "00:00",
"kelvin": 1800-6500 or null (keep the pattern's whites), "level": 5-100 (%
of the rule's brightness)}. Between points the values change gradually, in
10-minute steps (each step is one command to the controller). Points before
the rule's start time count as the next morning, so "00:00" after a sunset
start means midnight.

Brightness is set through the pattern's brightness, so it works for every
kind of pattern. Color temperature changes the whites (colors with little
saturation) of patterns made of colors; other colors keep their hue.
"""
import colorsys
import math
from datetime import timedelta

from .schedule import ConfigError, Effect, TimeExpr, _hex_to_int, gamma_correct

STEP_MIN = 10
STEP_MOVING = 30         # a moving pattern restarts its motion when sent, so it steps less often (3.18.2)
K_MIN, K_MAX = 1800, 6500


def kelvin_rgb(k: float) -> tuple[int, int, int]:
    """The RGB mix for a white of k kelvin (the fit whites.js uses)."""
    t = max(K_MIN, min(K_MAX, float(k))) / 100
    r = 255 if t <= 66 else 329.698727446 * math.pow(t - 60, -0.1332047592)
    g = 99.4708025861 * math.log(t) - 161.1195681661 if t <= 66 else 288.1221695283 * math.pow(t - 60, -0.0755148492)
    b = 255 if t >= 66 else 0 if t <= 19 else 138.5177312231 * math.log(t - 10) - 305.0447927307
    return tuple(max(0, min(255, round(v))) for v in (r, g, b))


def parse_curve(c, where: str):
    """The rule's "curve" setting -> [(TimeExpr, kelvin|None, level)], or None."""
    raw = c.get("curve")
    if raw is None:
        return None
    if not isinstance(raw, list) or not 2 <= len(raw) <= 6:
        raise ConfigError(f"{where}: a night curve needs 2 to 6 points")
    out = []
    for p in raw:
        if not isinstance(p, dict) or set(p) - {"at", "kelvin", "level"}:
            raise ConfigError(f"{where}: each night-curve point needs a time, a brightness and (optionally) a white")
        k, lv = p.get("kelvin"), p.get("level", 100)
        if k is not None and (not isinstance(k, int) or isinstance(k, bool) or not K_MIN <= k <= K_MAX):
            raise ConfigError(f"{where}: night-curve whites are {K_MIN}-{K_MAX} K")
        if not isinstance(lv, int) or isinstance(lv, bool) or not 5 <= lv <= 100:
            raise ConfigError(f"{where}: night-curve brightness is 5-100%")
        try:
            at = TimeExpr.parse(str(p.get("at") or ""))
        except ConfigError as e:
            raise ConfigError(f"{where}: night curve: {e}") from None
        out.append((at, k, lv))
    return out


def points_for(curve, window, loc):
    """The curve's points as real times for this night: [(datetime, k, level)]."""
    out = []
    start = window.start
    for at, k, lv in curve:
        t = at.resolve(start.date(), loc)
        if t is None:                        # no sunset that day (far north): fall back to the start
            t = start
        if t < start:
            # A little before the start ("sunset" for a rule that starts at
            # sunset + 15) means the start; long before ("00:00" on the start
            # date) means the next morning.
            if start - t <= timedelta(hours=6):
                t = start
            else:
                t = at.resolve(start.date() + timedelta(days=1), loc) or t + timedelta(days=1)
        out.append((t, k, lv))
    out.sort(key=lambda x: x[0])
    return out


def moves(eff) -> bool:
    """Whether the pattern moves (sending it again restarts the motion).
    Patterns made of colors with the Static mode don't; saved and built-in
    ones are taken to move."""
    if eff is None:
        return False
    if eff.kind == "split":
        return any(moves(p) for p in list(eff.parts.values()) + [eff.rest])
    return not (eff.kind == "custom" and eff.payload.get("mode", 0) == 0)


def curve_at(curve, window, now, loc, step: int = STEP_MIN):
    """(kelvin or None, level %) for now, in `step`-minute steps."""
    pts = points_for(curve, window, loc)
    # Steps on the clock's marks (9:00, 9:10, ...), so a point at 9:00 PM is
    # reached at 9:00 PM, not at the step nearest the start.
    t = max(window.start, now.replace(minute=now.minute - now.minute % step, second=0, microsecond=0))
    if t <= pts[0][0]:
        return pts[0][1], pts[0][2]
    if t >= pts[-1][0]:
        return pts[-1][1], pts[-1][2]
    for (t1, k1, l1), (t2, k2, l2) in zip(pts, pts[1:]):
        if t1 <= t <= t2:
            f = (t - t1).total_seconds() / max(1.0, (t2 - t1).total_seconds())
            lv = round(l1 + (l2 - l1) * f)
            if k1 is None or k2 is None:
                k = k1 if f < 0.5 else k2
            else:
                k = round((k1 + (k2 - k1) * f) / 50) * 50       # 50 K steps
            return k, lv
    return pts[-1][1], pts[-1][2]


def _is_white(hex_color: str) -> bool:
    r, g, b = (_hex_to_int(hex_color) >> s & 255 for s in (16, 8, 0))
    h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    return v > 0.25 and s < 0.35


def with_white(eff: Effect, kelvin, gamma) -> Effect:
    """The pattern with its whites at `kelvin` (patterns made of colors only).
    A white's own lightness is kept, so a dim white stays dim."""
    if kelvin is None or eff.kind != "custom" or not eff.colors:
        return eff
    kr = kelvin_rgb(kelvin)
    pixels, changed = [], False
    for p, designed in zip(eff.payload["pixels"], eff.colors):
        if p.get("disable") or designed == "off" or not _is_white(designed):
            pixels.append(p)
            continue
        n = _hex_to_int(designed)
        v = max(n >> 16 & 255, n >> 8 & 255, n & 255) / 255
        hexv = "#" + "".join(f"{round(c * v):02X}" for c in kr)
        pixels.append({**p, "color": gamma_correct(_hex_to_int(hexv), gamma)})
        changed = True
    if not changed:
        return eff
    return Effect(eff.key, eff.label, "custom", payload={**eff.payload, "pixels": pixels}, colors=list(eff.colors))


def curve_levels(base_brightness: int | None, rule_levels: dict, level: int) -> dict:
    """The rule's levels with its brightness at `level` percent."""
    b = rule_levels.get("brightness", base_brightness if base_brightness is not None else 200)
    return {**rule_levels, "brightness": max(1, min(255, round(b * level / 100)))}
