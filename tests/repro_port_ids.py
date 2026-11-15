# 4.0.3: "Invalid parameter [port -> id]" saving ports on a controller that shows them as 1-4.
class Cloud:                                     # reports ports 1-4, but saving takes them numbered 0-3
    def __init__(s): s.ports = {1: (1, 83), 2: (84, 138), 3: (1, 600), 4: (1, 600)}
    def read(s): return [{"id": k, "start": a, "end": b} for k, (a, b) in s.ports.items()]
    def update(s, ports):
        if any(p["id"] not in range(4) for p in ports): raise ValueError("code 12000 (Invalid parameter [port -> id].)")
        for p in ports: s.ports[p["id"] + 1] = (p["start"], p["end"])
def base(ports): ids = {p["id"] for p in ports}; return 1 if ids and 0 not in ids and ids <= {1, 2, 3, 4} else 0
def old_save(c, screen):                         # writes back in the numbers the controller shows
    b = base(c.read()); c.update([{**p, "id": p["id"] + b} for p in screen])
def new_save(c, screen):                         # FIX: refused over the id -> nothing changed, try the other numbering
    b = base(c.read())
    try: c.update([{**p, "id": p["id"] + b} for p in screen])
    except ValueError as e:
        if "port -> id" not in str(e): raise
        c.update([{**p, "id": p["id"] + 1 - b} for p in screen])
screen = [{"id": 0, "start": 1, "end": 90}, {"id": 1, "start": 91, "end": 138}, {"id": 2, "start": 1, "end": 600}, {"id": 3, "start": 1, "end": 600}]
for f in (old_save, new_save):
    c = Cloud()
    try: f(c, screen); print(f.__name__, "ok ->", c.read())
    except ValueError as e: print(f.__name__, "failed:", e)
