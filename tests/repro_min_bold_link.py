"""4.26.3 repro: in the manual viewer, a bold address such as
**http://localhost:8787** took the closing ** into the link, which broke the
bold and left the rest of the line (or list) bold.
Prints BUG, or OK with --fixed (when the link stops before the **)."""
import json, shutil, subprocess, sys
from pathlib import Path
js = Path(__file__).resolve().parents[1] / "eaveluxos" / "static" / "markdown.js"
if not shutil.which("node"):
    print("OK: (node not installed; skipped)"); sys.exit()
src = "Open **http://localhost:8787**. Then **Next**."
out = subprocess.run(["node", "-e", f"process.stdout.write(require({json.dumps(str(js))}).inline({json.dumps(src)}))"],
                     capture_output=True, text=True).stdout
good = 'href="http://localhost:8787"' in out and "<b>Next</b>" in out and "**" not in out
if "--fixed" in sys.argv:
    print("OK: the bold link renders cleanly" if good else "BUG: still broken: " + out.encode("ascii", "replace").decode())
else:
    print("BUG: the ** went into the link" if not good else "OK: (already fixed)")
