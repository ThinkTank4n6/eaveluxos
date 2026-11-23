# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Weather visualization (4.19): the lights show the weather.

Ready-made looks for rain, snow, a thunderstorm (lightning flashes), wind
and fog, each a pattern of this app's own with its weather rule, added in
one step from Alerts › Weather (add_looks). And temperature colors: a
weather rule that, instead of a pattern, shows the temperature as a color,
from deep blue when it's freezing to red when it's hot, worked out each
time the weather is read (temperature_effect).

The controller's own Lightning and Snowflake effects (in the Trimlight
app's Pattern Library) aren't used: how they're set is still being
captured. These are this app's own patterns, so they work today."""
from __future__ import annotations

import copy

# (key, label, colors, counts, custom mode, speed, brightness, rule name, condition)
LOOKS = [
    ("wx_rain", "Rain", ["#0A3CFF", "#3C8CFF", "#000000", "#000000"], [2, 1, 3, 2], 8, 170, 200, "Rain", "rain"),
    ("wx_snow", "Snow", ["#FFFFFF", "#BFDFFF", "#101830"], [1, 1, 4], 5, 80, 210, "Snow", "snow"),
    ("wx_storm", "Thunderstorm", ["#FFFFFF", "#0A0A40", "#14145A", "#0A0A40"], [1, 6, 6, 6], 15, 210, 230, "Thunderstorm", "storm"),
    ("wx_wind", "Windy", ["#20C0C0", "#E0FFFF", "#106070"], [4, 2, 4], 11, 230, 200, "Windy", "wind"),
    ("wx_fog", "Fog", ["#8090A0", "#506070", "#9AA8B4"], [5, 5, 5], 6, 40, 120, "Fog", "fog"),
]
LOOK_PRIORITY = 150          # beats the everyday schedule (100), not holidays (200 and up)
TEMP_PRIORITY = 140          # below the conditions: rain shows rain, whatever the temperature
TEMP_RULE = "Temperature colors"

# temperature (°F) -> color, in between mixed
_SCALE = [(10, (0x20, 0x30, 0xFF)), (32, (0x30, 0xB0, 0xFF)), (50, (0x30, 0xE0, 0x70)),
          (65, (0xFF, 0xD0, 0x30)), (80, (0xFF, 0x80, 0x20)), (95, (0xFF, 0x20, 0x20))]
STEP_F = 5                   # a new color every 5 °F, so the lights don't change with every reading


def temp_color(temp_f: float | None) -> str:
    if temp_f is None:
        return "#FFFFFF"
    t = max(_SCALE[0][0], min(_SCALE[-1][0], float(temp_f)))
    for (a, ca), (b, cb) in zip(_SCALE, _SCALE[1:]):
        if a <= t <= b:
            k = (t - a) / (b - a)
            return "#" + "".join(f"{round(x + (y - x) * k):02X}" for x, y in zip(ca, cb))
    return "#FFFFFF"


def _lighter(hexc: str, by: float) -> str:
    v = [int(hexc[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (255 - x) * by):02X}" for x in v)


def temperature_config(temp_f: float | None) -> tuple[str, dict]:
    """(pattern key, pattern settings) for this temperature, rounded to 5 °F."""
    if temp_f is None:
        return "wx_temp_unknown", {"label": "Temperature colors", "colors": ["#FFFFFF"], "counts": [1],
                                   "custom_mode": 0, "brightness": 180}
    t = int(round(float(temp_f) / STEP_F) * STEP_F)
    c = temp_color(t)
    return f"wx_temp_{t}", {"label": f"Temperature colors ({t}°F)", "colors": [c, _lighter(c, 0.35), c],
                            "counts": [4, 2, 4], "custom_mode": 6, "speed": 60, "brightness": 200}


def temperature_effect(temp_f, gamma=None):
    from .schedule import Effect
    key, cfg = temperature_config(temp_f)
    return Effect.from_config(key, cfg, gamma)


def add_looks(settings: dict, temperature: bool = True) -> tuple[dict, list[str]]:
    """The weather looks added to settings (patterns and rules missing so
    far; nothing of yours is changed). Returns (new settings, what was
    added), and turns weather rules on."""
    s = copy.deepcopy(settings)
    effects = s.setdefault("effects", {})
    rules = s.setdefault("weather_rules", [])
    names = {str(r.get("name", "")).lower() for r in rules if isinstance(r, dict)}
    added = []
    for key, label, colors, counts, mode, speed, bright, rname, cond in LOOKS:
        if key not in effects:
            effects[key] = {"label": label, "colors": colors, "counts": counts, "custom_mode": mode,
                            "speed": speed, "brightness": bright}
            added.append(f"pattern {label}")
        if rname.lower() not in names:
            rules.append({"name": rname, "when": [cond], "effect": key, "priority": LOOK_PRIORITY})
            names.add(rname.lower())
            added.append(f"weather rule {rname}")
    if temperature and TEMP_RULE.lower() not in names:
        rules.append({"name": TEMP_RULE, "temperature_colors": True, "priority": TEMP_PRIORITY})
        added.append(f"weather rule {TEMP_RULE}")
    s["weather"] = {**(s.get("weather") or {}), "enabled": True}
    return s, added
