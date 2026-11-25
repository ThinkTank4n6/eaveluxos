"""4.26.1 repro: Share to the community wrote each tag and color on its own line,
unlike the library's files (tags and pattern each on one line).
Prints BUG, or OK with --fixed (when the layout matches)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from eaveluxos.community import share_file

name, text = share_file({"colors": ["#ff0000", "#ffffff"], "counts": [4, 4], "custom_mode": 1, "speed": 60, "brightness": 200},
                        "Candy cane", "ThinkTank4n6", "Red and white stripes.", ["christmas", "red"])
lines = text.splitlines()
same = len(lines) == 7 and lines[4].startswith(' "tags": [') and lines[5].startswith(' "pattern": {"label"')
if "--fixed" in sys.argv:
    print("OK: the layout matches the library" if same else "BUG: still a different layout")
else:
    print("BUG: tags and colors are spread over %d lines" % len(lines) if not same else "OK: (already fixed)")
