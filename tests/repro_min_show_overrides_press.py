"""4.20 review #1, standalone: a button pressed during a fade between two Studio looks
was overridden by the next look. Run: python3 tests/repro_min_show_overrides_press.py [--fixed]"""
import sys
FIXED, gen, shown = "--fixed" in sys.argv, [0], []      # gen: bumped by every choice (a button, or the show's own)
def choose(what):                                     # the controller's manual(): shows it, bumps gen
    gen[0] += 1; shown.append(what)
def fade(press_during):                               # the frames between two looks; a press ends it early
    if press_during: choose("Lights off (pressed)")
mine = None
for i, look in enumerate(["Warm white", "Candy cane"]):
    if i: fade(press_during=True)                     # the person presses Lights off mid-fade
    if FIXED and mine is not None and gen[0] != mine: break   # the fix: their choice wins
    choose(look); mine = gen[0]
last = shown[-1]
print(f"BUG: the lights ended on {last!r}, over the button pressed" if last != "Lights off (pressed)"
      else "OK: the button pressed during the fade wins")
sys.exit(0 if last == "Lights off (pressed)" else 1)
