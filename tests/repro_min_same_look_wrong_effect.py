"""4.22.3 review #1: two saved patterns that look exactly alike but differ by
Lightning: this app's copy of "Test w/o lightning" showed #20 (with
Lightning), the first number with that look. Standalone; BUG, or OK --fixed."""
import sys

FIXED = "--fixed" in sys.argv
saved = [{"id": 20, "name": "Test Lightning", "look": "orange"},
         {"id": 22, "name": "Test w/o lightning", "look": "orange"}]
effects = [(0, 20)]                                 # Lightning on #20


def show_like(look, name):
    same = [p for p in saved if p["look"] == look]
    if not FIXED:
        return same[0]["id"]                        # the first by number, whichever was meant
    for p in same:
        if p["name"].lower() == name.lower():
            return p["id"]
    plain = [p for p in same if p["id"] not in {n for _, n in effects}]
    return min(p["id"] for p in (plain or same))


pid = show_like("orange", "Test w/o lightning")
print("OK: showed #22, no Lightning" if pid == 22 else f"BUG: showed #{pid}, which has Lightning")
