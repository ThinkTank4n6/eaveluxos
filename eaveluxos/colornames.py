# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Named colors (3.20): the web's standard color names (CSS / HTML, the
chart Trimlight owners pass around), grouped like that chart, each with a
note on how it looks on LED lights, which isn't always how it looks on a
screen: pale colors and whites look white, browns look orange, grays are
dim white, dark colors are dim versions of their hue.

The one list the app uses: Create's "Color by name" and Named colors, the
names shown on swatches, and Describe it's color words (textpattern.py).
"""
import colorsys
import re

GROUPS = ["Pink", "Red", "Orange", "Yellow", "Brown", "Green", "Cyan", "Blue", "Purple", "White", "Gray"]

_RAW = {
    "Pink": "Pink FFC0CB LightPink FFB6C1 HotPink FF69B4 DeepPink FF1493 PaleVioletRed DB7093 MediumVioletRed C71585",
    "Red": "LightSalmon FFA07A Salmon FA8072 DarkSalmon E9967A LightCoral F08080 IndianRed CD5C5C Crimson DC143C "
           "FireBrick B22222 DarkRed 8B0000 Red FF0000",
    "Orange": "OrangeRed FF4500 Tomato FF6347 Coral FF7F50 DarkOrange FF8C00 Orange FFA500",
    "Yellow": "Yellow FFFF00 LightYellow FFFFE0 LemonChiffon FFFACD LightGoldenrodYellow FAFAD2 PapayaWhip FFEFD5 "
              "Moccasin FFE4B5 PeachPuff FFDAB9 PaleGoldenrod EEE8AA Khaki F0E68C DarkKhaki BDB76B Gold FFD700",
    "Brown": "Cornsilk FFF8DC BlanchedAlmond FFEBCD Bisque FFE4C4 NavajoWhite FFDEAD Wheat F5DEB3 BurlyWood DEB887 "
             "Tan D2B48C RosyBrown BC8F8F SandyBrown F4A460 Goldenrod DAA520 DarkGoldenrod B8860B Peru CD853F "
             "Chocolate D2691E SaddleBrown 8B4513 Sienna A0522D Brown A52A2A Maroon 800000",
    "Green": "DarkOliveGreen 556B2F Olive 808000 OliveDrab 6B8E23 YellowGreen 9ACD32 LimeGreen 32CD32 Lime 00FF00 "
             "LawnGreen 7CFC00 Chartreuse 7FFF00 GreenYellow ADFF2F SpringGreen 00FF7F MediumSpringGreen 00FA9A "
             "LightGreen 90EE90 PaleGreen 98FB98 DarkSeaGreen 8FBC8F MediumSeaGreen 3CB371 SeaGreen 2E8B57 "
             "ForestGreen 228B22 Green 008000 DarkGreen 006400",
    "Cyan": "MediumAquamarine 66CDAA Aqua 00FFFF Cyan 00FFFF LightCyan E0FFFF PaleTurquoise AFEEEE Aquamarine 7FFFD4 "
            "Turquoise 40E0D0 MediumTurquoise 48D1CC DarkTurquoise 00CED1 LightSeaGreen 20B2AA CadetBlue 5F9EA0 "
            "DarkCyan 008B8B Teal 008080",
    "Blue": "LightSteelBlue B0C4DE PowderBlue B0E0E6 LightBlue ADD8E6 SkyBlue 87CEEB LightSkyBlue 87CEFA "
            "DeepSkyBlue 00BFFF DodgerBlue 1E90FF CornflowerBlue 6495ED SteelBlue 4682B4 RoyalBlue 4169E1 Blue 0000FF "
            "MediumBlue 0000CD DarkBlue 00008B Navy 000080 MidnightBlue 191970",
    "Purple": "Lavender E6E6FA Thistle D8BFD8 Plum DDA0DD Violet EE82EE Orchid DA70D6 Fuchsia FF00FF Magenta FF00FF "
              "MediumOrchid BA55D3 MediumPurple 9370DB BlueViolet 8A2BE2 DarkViolet 9400D3 DarkOrchid 9932CC "
              "DarkMagenta 8B008B Purple 800080 Indigo 4B0082 DarkSlateBlue 483D8B RebeccaPurple 663399 "
              "SlateBlue 6A5ACD MediumSlateBlue 7B68EE",
    "White": "White FFFFFF Snow FFFAFA Honeydew F0FFF0 MintCream F5FFFA Azure F0FFFF AliceBlue F0F8FF "
             "GhostWhite F8F8FF WhiteSmoke F5F5F5 Seashell FFF5EE Beige F5F5DC OldLace FDF5E6 FloralWhite FFFAF0 "
             "Ivory FFFFF0 AntiqueWhite FAEBD7 Linen FAF0E6 LavenderBlush FFF0F5 MistyRose FFE4E1",
    "Gray": "Gainsboro DCDCDC LightGrey D3D3D3 Silver C0C0C0 DarkGray A9A9A9 Gray 808080 DimGray 696969 "
            "LightSlateGray 778899 SlateGray 708090 DarkSlateGray 2F4F4F Black 000000",
}


def spaced(name: str) -> str:
    """"ForestGreen" -> "Forest Green" (how the app shows a name)."""
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name)


def key(text: str) -> str:
    """What's compared when someone types a name: "forest green",
    "Forest-Green" and "forestgreen" are all "forestgreen"; grey = gray."""
    return re.sub(r"[^a-z]", "", str(text).lower()).replace("grey", "gray")


def _hue_word(h: float) -> str:
    deg = h * 360
    for limit, word in ((12, "red"), (40, "orange"), (68, "yellow"), (160, "green"), (195, "cyan"),
                        (255, "blue"), (290, "purple"), (335, "pink"), (361, "red")):
        if deg < limit:
            return word
    return "red"


def led_note(hex_color: str, group: str) -> dict:
    """How a color looks on LED lights: {"kind", "text"}. kind is one of
    great, white, dimwhite, pale, washed, dim, shift, off."""
    n = int(hex_color.lstrip("#"), 16)
    r, g, b = (n >> 16 & 255) / 255, (n >> 8 & 255) / 255, (n & 255) / 255
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    if v == 0:
        return {"kind": "off", "text": "No light (a dark space that moves with the pattern)"}
    if group == "Gray":                    # the chart's grays: a dimmer white on lights
        return {"kind": "dimwhite", "text": "Looks like dim white on lights"}
    if group == "White" or (s < 0.12 and v >= 0.75):
        return {"kind": "white", "text": "Looks white on lights"}
    if s < 0.12:
        return {"kind": "dimwhite", "text": "Looks like dim white on lights"}
    if s < 0.4 and v > 0.8:
        return {"kind": "pale", "text": "Pale: looks almost white on lights"}
    if s < 0.55:
        return {"kind": "washed", "text": f"Softer on lights: a light, whitish {_hue_word(h)}"}
    if v < 0.6:
        return {"kind": "dim", "text": f"Looks like dim {_hue_word(h)} on lights"}
    if group == "Brown":
        return {"kind": "shift", "text": f"Looks {_hue_word(h)} on lights (lights can't show brown)"}
    return {"kind": "great", "text": "Great on lights"}


NAMES = []
for _group in GROUPS:
    _w = _RAW[_group].split()
    for _name, _hex in zip(_w[::2], _w[1::2]):
        NAMES.append({"name": spaced(_name), "hex": "#" + _hex, "group": _group, **{"led": led_note(_hex, _group)}})

BY_KEY = {key(c["name"]): c for c in NAMES}


def lookup(text: str):
    """A typed name -> its entry, or None."""
    return BY_KEY.get(key(text))


def describe_words() -> dict:
    """Lowercase spaced names (and "grey" spellings) -> hex, for Describe it."""
    out = {}
    for c in NAMES:
        w = c["name"].lower()
        out[w] = c["hex"]
        if "gray" in w:
            out[w.replace("gray", "grey")] = c["hex"]
    return out
