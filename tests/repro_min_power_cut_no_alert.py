"""4.27 repro: after a power cut (the app off 100 minutes, never quit), no
phone alert and no note ever said so; Chris's outages on Nov 26 went unseen.
Prints BUG, or OK with --fixed (when one alert goes out after the restart)."""
import shutil, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from eaveluxos.alerts import Alerts

d, t, sent = Path(tempfile.mkdtemp()), [1_000_000.0], []
def run():
    a = Alerts(d, now=lambda: t[0], send=lambda *m: sent.append(m[1]))
    a.update({"enabled": True}); a.start(); a.stop.set(); return a
a = run(); t[0] += 60; a.step()
t[0] += 6000                                   # the power is out
b = run(); t[0] += 60; b.step()
shutil.rmtree(d, ignore_errors=True)
ok = any("was off" in s for s in sent)
if "--fixed" in sys.argv:
    print("OK: an alert says the app was off" if ok else "BUG: still no alert")
else:
    print("BUG: nothing said the app was off" if not ok else "OK: (already fixed)")
