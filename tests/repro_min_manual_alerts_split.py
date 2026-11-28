"""4.28.1 repro: the manual had three separate "Alerts" sections (14, 15 and
21) and Phone alerts sat under Setup, though all of them are on the Alerts tab.
Prints BUG, or OK with --fixed (when there is one Alerts section)."""
import re, sys
from pathlib import Path
md = (Path(__file__).resolve().parents[1] / "MANUAL.md").read_text(encoding="utf-8")
alerts = re.findall(r"(?m)^## \d+\. Alerts.*$", md)
good = len(alerts) == 1 and all(f"\n### {h}\n" in md for h in ("Security flash", "Phone alerts", "Webhooks and Home Assistant"))
if "--fixed" in sys.argv:
    print("OK: one Alerts section" if good else f"BUG: {len(alerts)} Alerts sections")
else:
    print(f"BUG: {len(alerts)} Alerts sections" if not good else "OK: (already fixed)")
