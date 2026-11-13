# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Names Trimlight uses for its built-in effects and animation modes
(from Trimlight's API documentation), grouped the way the app groups them."""

BUILTIN = [
    "Rainbow Gradual Chase", "Rainbow Comet", "Rainbow Segment", "Rainbow Wave", "Rainbow Meteor",
    "Rainbow Gradual", "Rainbow Jump", "Rainbow Stars", "Rainbow Fade In Out", "Rainbow Spin",
    "Red Stacking", "Green Stacking", "Blue Stacking", "Yellow Stacking", "Cyan Stacking", "Purple Stacking",
    "White Stacking", "Full Color Stack", "Red to Green Stack", "Green to Blue Stack", "Blue to Yellow Stack",
    "Yellow to Cyan Stack", "Cyan to Purple Stack", "Purple to White Stack",
    "Red Comet", "Green Comet", "Blue Comet", "Yellow Comet", "Cyan Comet", "Purple Comet", "White Comet",
    "Red Meteor", "Green Meteor", "Blue Meteor", "Yellow Meteor", "Cyan Meteor", "Purple Meteor", "White Meteor",
    "Red Wave", "Green Wave", "Blue Wave", "Yellow Wave", "Cyan Wave", "Purple Wave", "White Wave",
    "Red Green Wave", "Red Blue Wave", "Red Yellow Wave", "Red Cyan Wave", "Red Purple Wave", "Red White Wave",
    "Green Blue Wave", "Green Yellow Wave", "Green Cyan Wave", "Green Purple Wave", "Green White Wave",
    "Blue Yellow Wave", "Blue Cyan Wave", "Blue Purple Wave", "Blue White Wave", "Yellow Cyan Wave",
    "Yellow Purple Wave", "Yellow White Wave", "Cyan Purple Wave", "Cyan White Wave", "Purple White Wave",
    "Red Dot Pulse", "Green Dot Pulse", "Blue Dot Pulse", "Yellow Dot Pulse", "Cyan Dot Pulse",
    "Purple Dot Pulse", "White Dot Pulse", "Red Green Blank Pulse", "Green Blue Blank Pulse",
    "Blue Yellow Blank Pulse", "Yellow Cyan Blank Pulse", "Cyan Purple Blank Pulse", "Purple White Blank Pulse",
    "Red with Purple Pulse", "Green with Cyan Pulse", "Blue with Yellow Pulse", "Yellow with Blue Pulse",
    "Cyan with Green Pulse", "Purple with Purple Pulse",
    "Red Comet Spin", "Green Comet Spin", "Blue Comet Spin", "Yellow Comet Spin", "Cyan Comet Spin",
    "Purple Comet Spin", "White Comet Spin", "Red Dot Spin", "Green Dot Spin", "Blue Dot Spin", "Yellow Dot Spin",
    "Cyan Dot Spin", "Purple Dot Spin", "White Dot Spin", "Red Segment Spin", "Green Segment Spin",
    "Blue Segment Spin", "Yellow Segment Spin", "Cyan Segment Spin", "Purple Segment Spin", "White Segment Spin",
    "Red Green Gradual Snake", "Red Blue Gradual Snake", "Red Yellow Gradual Snake", "Red Cyan Gradual Snake",
    "Red Purple Gradual Snake", "Red White Gradual Snake", "Green Blue Gradual Snake", "Green Yellow Gradual Snake",
    "Green Cyan Gradual Snake", "Green Purple Gradual Snake", "Green White Gradual Snake",
    "Blue Yellow Gradual Snake", "Blue Cyan Gradual Snake", "Blue Purple Gradual Snake", "Blue White Gradual Snake",
    "Yellow Cyan Gradual Snake", "Yellow Purple Gradual Snake", "Yellow White Gradual Snake",
    "Cyan Purple Gradual Snake", "Cyan White Gradual Snake", "Purple White Gradual Snake",
    "Red White Blank Snake", "Green White Blank Snake", "Blue White Blank Snake", "Yellow White Blank Snake",
    "Cyan White Blank Snake", "Purple White Blank Snake", "Green Yellow White Snake", "Red Green White Snake",
    "Red Yellow Snake", "Red White Snake", "Green White Snake",
    "Red Stars", "Green Stars", "Blue Stars", "Yellow Stars", "Cyan Stars", "Purple Stars", "White Stars",
    "Red Background Stars", "Green Background Stars", "Blue Background Stars", "Yellow Background Stars",
    "Cyan Background Stars", "Purple Background Stars", "Red White Background Stars",
    "Green White Background Stars", "Blue White Background Stars", "Yellow White Background Stars",
    "Cyan White Background Stars", "Purple White Background Stars", "White White Background Stars",
    "Red Breath", "Green Breath", "Blue Breath", "Yellow Breath", "Cyan Breath", "Purple Breath", "White Breath",
    "Red Yellow Fire", "Red Purple Fire", "Green Yellow Fire", "Green Cyan Fire", "Blue Purple Fire",
    "Blue Cyan Fire", "Red Strobe", "Green Strobe", "Blue Strobe", "Yellow Strobe", "Cyan Strobe",
    "Purple Strobe", "White Strobe", "Red Blue White Strobe", "Full Color Strobe",
]
assert len(BUILTIN) == 180

GROUPS = [("Rainbow", 0, 9), ("Stacking", 10, 23), ("Comet", 24, 30), ("Meteor", 31, 37), ("Wave", 38, 65),
          ("Pulse", 66, 84), ("Spin", 85, 105), ("Snake", 106, 137), ("Stars", 138, 157),
          ("Breath", 158, 164), ("Fire", 165, 170), ("Strobe", 171, 179)]

CUSTOM_MODES = ["Static", "Chase forward", "Chase backward", "Chase middle to out", "Chase out to middle",
                "Stars", "Breath", "Comet forward", "Comet backward", "Comet middle to out",
                "Comet out to middle", "Wave forward", "Wave backward", "Wave middle to out",
                "Wave out to middle", "Strobe", "Solid fade"]

# The Trimlight app's quick palette (R, G, B, Y, PU, O, W, WW, PI, C, BK)
PALETTE = [("Red", "#FF0000"), ("Green", "#00FF00"), ("Blue", "#0000FF"), ("Yellow", "#FFFF00"),
           ("Purple", "#8000FF"), ("Orange", "#FF3000"), ("White", "#FFFFFF"), ("Warm white", "#E0A060"),
           ("Pink", "#FF0080"), ("Cyan", "#00FFFF"), ("Off (black)", "#000000")]

IC_TYPES = ["UCS1903", "DMX512"]
COLOR_ORDERS = ["RGB", "RBG", "GRB", "GBR", "BRG", "BGR"]

_HUES = {"red": "#FF2020", "green": "#20D040", "blue": "#2050FF", "yellow": "#FFE020", "cyan": "#20E0E0",
         "purple": "#9030FF", "white": "#FFFFFF"}


# "Recreate with my colors": built-in effects' colors are fixed in the
# controller's firmware, so a built-in is recreated as a custom pattern with the
# same colors (full-strength LED values) and the closest custom motion. Close
# to the original, not identical.
_LED = {"red": "#FF0000", "green": "#00FF00", "blue": "#0000FF", "yellow": "#FFFF00", "cyan": "#00FFFF",
        "purple": "#8000FF", "white": "#FFFFFF"}
_RAINBOW = ["#FF0000", "#FFFF00", "#00FF00", "#0000FF", "#8000FF"]
_MODE = {name: i for i, name in enumerate(CUSTOM_MODES)}
_GROUP_MOTION = {"Stacking": "Chase forward", "Comet": "Comet forward", "Meteor": "Comet forward",
                 "Wave": "Wave forward", "Pulse": "Breath", "Spin": "Chase forward", "Snake": "Chase forward",
                 "Stars": "Stars", "Breath": "Breath", "Fire": "Stars", "Strobe": "Strobe"}
_RAINBOW_MOTION = [("fade", "Breath"), ("gradual chase", "Chase forward"), ("comet", "Comet forward"),
                   ("meteor", "Comet forward"), ("wave", "Wave forward"), ("stars", "Stars"),
                   ("gradual", "Solid fade"), ("jump", "Solid fade"), ("segment", "Chase forward"),
                   ("spin", "Chase forward")]
_COUNTS = {"Comet forward": 4, "Stars": 3, "Breath": 6, "Strobe": 6, "Solid fade": 6, "Wave forward": 5}


def recreate(mode: int) -> dict:
    """A custom pattern (colors, counts, custom_mode) close to built-in `mode`."""
    name, group = BUILTIN[mode], next(g for g, a, b in GROUPS if a <= mode <= b)
    words = name.lower().split()
    if group == "Rainbow":
        motion = next(m for k, m in _RAINBOW_MOTION if k in name.lower())
    else:
        motion = _GROUP_MOTION[group]
    if "rainbow" in words or "full" in words:
        colors = list(_RAINBOW)
    else:
        colors = list(dict.fromkeys(_LED[w] for w in words if w in _LED)) or ["#FFFFFF"]
    if "blank" in words:                     # dark gaps between the colors
        colors = [c for col in colors for c in (col, "#000000")]
    n = _COUNTS.get(motion, 4)
    return {"label": f"{name} (my colors)", "colors": colors, "counts": [n] * len(colors),
            "custom_mode": _MODE[motion], "speed": 100, "brightness": 200}


def builtin_list() -> list[dict]:
    out = []
    for gname, a, b in GROUPS:
        for i in range(a, b + 1):
            name = BUILTIN[i]
            words = name.lower().split()
            if "rainbow" in words or "full" in words:
                sw = ["#FF2020", "#FFE020", "#20D040", "#2050FF", "#9030FF"]
            else:
                sw = list(dict.fromkeys(_HUES[w] for w in words if w in _HUES))
            out.append({"mode": i, "name": name, "group": gname, "swatches": sw, "recreate": recreate(i)})
    return out


def catalog() -> dict:
    return {"builtin": builtin_list(), "groups": [g[0] for g in GROUPS], "custom_modes": CUSTOM_MODES,
            "palette": [{"name": n, "hex": h} for n, h in PALETTE], "ic_types": IC_TYPES,
            "color_orders": COLOR_ORDERS}
