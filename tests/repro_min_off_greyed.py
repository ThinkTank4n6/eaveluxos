"""Off-button review #1, standalone: lights turned on outside EaveLuxOS (the Trimlight app,
the controller's own timer, power coming back) while the schedule says off: the header's
Off button was greyed out, so it couldn't turn them off. Run with --fixed for the fix."""
import sys
FIXED = "--fixed" in sys.argv
def off_button_enabled(target_on, music=False):          # app.js statusPill(), as it was
    return True if FIXED else (target_on or music)       # the fix: Off always works
def press_off(target_on):                                 # what a click does, if it can be clicked
    if not off_button_enabled(target_on):
        return "nothing: the button is greyed out"
    return "Lights off sent to every controller"          # manual(False) -> a new target -> sent
app_target_on = False      # 8 PM, after the schedule's off time: the app says "Lights off"
lights_really_on = True    # ...but the controller's own timer turned them on (Nov 21, 4:53 PM)
result = press_off(app_target_on)
if lights_really_on and result.startswith("nothing"):
    print(f"BUG: pressing Off did {result}; the lights stay on")
    sys.exit(1)
print(f"OK: pressing Off: {result}")
