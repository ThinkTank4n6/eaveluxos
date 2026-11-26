"""4.26.2 repro: a score celebration held back by a weather alert also logged
"no celebration because the lights are off", though the lights were on.
Prints BUG, or OK with --fixed (when only the real reason is logged)."""
import sys
from pathlib import Path
from types import SimpleNamespace as NS
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from eaveluxos.server import App

notes = []
def start_flash(**kw):
    notes.append("Flyers scored! skipped: the High Wind Warning alert is showing.")
    return False
cfg = NS(celebrate={"nhl-phi": {}}, effects={"team": NS(kind="static", colors=[])})
fake = NS(ctrl=NS(cfg=cfg, start_flash=start_flash, note=notes.append))
App.celebrate(fake, {"key": "nhl-phi", "effect": "team", "seconds": 20, "name": "Flyers"}, 1, {})
wrong = any("lights are off" in n for n in notes)
if "--fixed" in sys.argv:
    print("OK: only the real reason is logged" if not wrong else "BUG: still says the lights are off")
else:
    print("BUG: it also says the lights are off" if wrong else "OK: (already fixed)")
