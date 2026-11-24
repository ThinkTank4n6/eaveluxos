"""4.23 review #1: a pattern saved with one of the newer Trimlight Edge
animations (A8 Juggle: 22 on the controller, Nov 24 backup) was copied into
My patterns as animation 16 (Solid fade): the app knew 0-16 and clamped
anything higher. Standalone; prints BUG, or OK with --fixed."""
import sys

FIXED = "--fixed" in sys.argv
MODES = ["Static", "Chase forward", "Chase backward", "Chase middle to out", "Chase out to middle",
         "Stars", "Breath", "Comet forward", "Comet backward", "Comet middle to out", "Comet out to middle",
         "Wave forward", "Wave backward", "Wave middle to out", "Wave out to middle", "Strobe", "Solid fade"]
if FIXED:
    MODES = MODES[:5] + ["Twinkle fade", "Fade"] + MODES[7:] + ["Full strobe", "Twinkle", "Firework",
                                                                "Inside out", "Dissolve", "Juggle"]
saved = {"id": 29, "name": "A8 Juggle", "mode": 22}


def add_to_my_patterns(e):
    return {"label": e["name"], "custom_mode": min(len(MODES) - 1, e["mode"])}


copy = add_to_my_patterns(saved)
got = MODES[copy["custom_mode"]]
print(f"OK: the copy runs {got}" if got == "Juggle" else f"BUG: the copy runs {got}, not Juggle")
