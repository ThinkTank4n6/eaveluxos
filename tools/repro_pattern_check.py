"""Repro: the 5-minute check only compares switchState, so a pattern changed in the Trimlight app is never restored."""
class FakeCloud:  # device/get as documented: switchState plus currentEffect ("Device current running effect")
    def __init__(s): s.dev = {"switchState": 1, "currentEffect": None}; s.sent = 0
    def preview(s, payload): s.sent += 1; s.dev["currentEffect"] = {"id": -1, **payload}  # -1: a preview
    def get(s): return dict(s.dev)
WARM = {"category": 1, "mode": 0, "speed": 100, "brightness": 180, "pixels": [{"index": 0, "count": 1, "color": 0xFFB46B}]}
class Ctrl:  # same check as Controller._maintenance: two readings in a row must disagree before restoring
    def __init__(s, cloud): s.cloud, s.mismatches = cloud, 0
    def apply(s): s.cloud.preview(dict(WARM))
    def maintenance(s):
        d = s.cloud.get()
        wrong = d["switchState"] != 1                       # BUG: currentEffect is never looked at
        s.mismatches = s.mismatches + 1 if wrong else 0
        if s.mismatches >= 2: s.mismatches = 0; s.apply()
cloud = FakeCloud(); c = Ctrl(cloud); c.apply()
cloud.dev["currentEffect"] = {"id": 4, "category": 0, "mode": 12, "speed": 140, "brightness": 255}  # Trimlight app: Rainbow
for _ in range(4): c.maintenance()                          # 20 minutes of checks
showing = cloud.get()["currentEffect"]
print("controller shows:", "Rainbow (id 4)" if showing.get("id") == 4 else "Warm white", "| restores sent:", cloud.sent - 1,
      "-> BUG: never restored" if showing.get("id") == 4 else "-> OK")
