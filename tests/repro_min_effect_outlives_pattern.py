"""4.22 review #1: deleting a saved pattern left its Lightning in the
controller's effects list, so the next pattern saved under that number
flashed. Standalone; prints BUG, or OK with --fixed."""
import sys

FIXED = "--fixed" in sys.argv
ctl = {"patterns": {20: "Test Lightning", 21: "Test Snowflake"}, "effects": [(0, 20), (1, 21)]}


def delete(pid):
    ctl["patterns"].pop(pid)                       # sub 0x05: the controller keeps the effects list as is
    if FIXED and any(n == pid for _, n in ctl["effects"]):
        ctl["effects"] = [x for x in ctl["effects"] if x[1] != pid]    # sub 0x1b without it, read back


def save_new(name):
    pid = min(set(range(1, 61)) - set(ctl["patterns"]) - set(range(1, 20)))
    ctl["patterns"][pid] = name
    return pid


delete(20)
pid = save_new("Porch white")
inherited = [k for k, n in ctl["effects"] if n == pid]
print(f"BUG: new pattern #{pid} 'Porch white' plays Lightning" if inherited else f"OK: new pattern #{pid} has no effect")
