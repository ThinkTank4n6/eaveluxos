# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Energy estimates (4.21): what the lights draw, from the patterns.

An LED bulb draws about in proportion to how bright each of its red, green
and blue parts is lit: full white is all three at full, warm white a little
less, one deep color about a third, and a dark bulb almost nothing. So a
pattern's draw is its bulbs × the watts of one bulb at full white × the
pattern's brightness × how much of white its colors average (each color
weighted by how many bulbs it covers). The controller itself adds a few
watts while it's on.

These are estimates: the watts of one bulb at full white is from the
lights' specifications (EaveLuxOS starts at 0.3 W, change it under Setup ›
App › Lights usage), and a built-in effect's colors are only known to the
controller (counted as half of white)."""
from __future__ import annotations

from datetime import date, timedelta

WATTS_PER_BULB = 0.3        # at full white; change it under Lights usage
CONTROLLER_WATTS = 3.0      # the controller and its power supply, while on
BUILTIN_SHARE = 0.5         # a built-in effect's colors aren't known here


def white_share(payload: dict) -> float:
    """How much of full white a pattern's colors average, 0 to 1."""
    if not isinstance(payload, dict):
        return BUILTIN_SHARE
    if payload.get("category") != 1 or not payload.get("pixels"):
        return BUILTIN_SHARE
    total = lit = 0.0
    for p in payload["pixels"]:
        n = max(1, int(p.get("count", 1)))
        c = 0 if p.get("disable") else int(p.get("color", 0))
        lit += n * (((c >> 16) & 255) + ((c >> 8) & 255) + (c & 255)) / 765
        total += n
    return lit / total if total else 0.0


def pattern_watts(effect, bulbs: int, per_bulb: float = WATTS_PER_BULB, brightness: int | None = None) -> float:
    """Watts while this pattern (an Effect) shows on `bulbs` bulbs."""
    if effect is None or bulbs <= 0:
        return 0.0
    if effect.kind == "split":
        parts = [p for p in list(effect.parts.values()) + [effect.rest] if p is not None]
        return max((pattern_watts(p, bulbs, per_bulb, brightness) for p in parts), default=0.0)
    pl = effect.payload if isinstance(effect.payload, dict) else {}
    b = brightness if brightness is not None else int(pl.get("brightness", 200) or 200)
    return bulbs * per_bulb * (max(0, min(255, b)) / 255) * white_share(pl) + CONTROLLER_WATTS


def month_estimate(schedule, start: date, days: int, bulbs: int, per_bulb: float = WATTS_PER_BULB,
                   rate: float | None = None) -> dict:
    """The schedule's coming `days` nights: hours on, kWh and (with a price
    per kWh) cost, each night's pattern at its own draw. Weather, flashes and
    choices made by hand aren't known ahead, so they aren't in it."""
    hours = kwh = 0.0
    nights = []
    for i in range(days):
        d = start + timedelta(days=i)
        night_kwh = night_h = 0.0
        for p in schedule.day_plans(d):
            h = max(0.0, (p.end - p.start).total_seconds() / 3600)
            eff = p.rule.pick(p.window.start, p.start)[0]
            w = pattern_watts(eff, bulbs, per_bulb, (p.rule.levels or {}).get("brightness"))
            night_h += h
            night_kwh += w * h / 1000
        hours += night_h
        kwh += night_kwh
        nights.append({"date": d.isoformat(), "hours": round(night_h, 2), "kwh": round(night_kwh, 3)})
    return {"days": days, "hours": round(hours, 1), "kwh": round(kwh, 2),
            "cost": round(kwh * rate, 2) if rate is not None else None, "nights": nights}
