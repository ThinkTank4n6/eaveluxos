"""3.18.1 review #1: mood follow went through manual(), which treats any
choice during a weather warning as "not now" and dismisses the warning."""
import time
class Ctrl:                                         # just the layering logic, nothing external
    def __init__(s): s.alert, s.dismissed, s.override = "Winter Storm Warning", {}, None
    def target(s):
        if s.alert and s.alert.lower() not in s.dismissed: return "alert"
        return "manual" if s.override else "schedule"
    def manual(s, key, mood=False):                 # FIX: mood=True never dismisses
        if s.target() == "alert" and not mood: s.dismissed[s.alert.lower()] = time.time()
        s.override = {"effect": key, "mood": mood}
def mood_report(c, key, fixed):                    # what app.mood() did per 10-second report
    c.manual(key, mood=fixed)
for fixed in (False, True):
    c = Ctrl(); mood_report(c, "christmas", fixed)
    print("fixed" if fixed else "before", "->", c.target(), "| dismissed:", list(c.dismissed))
    assert c.target() == ("alert" if fixed else "manual")
print("OK: with the fix the storm warning stays on while music plays")
