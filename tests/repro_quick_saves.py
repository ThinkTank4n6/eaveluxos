# 4.0.0 review #1: quick saves in a row lost all but the first ("changed on another device").
import copy, json
class Server:                                    # the app's settings store: refuses a save made from an old version
    def __init__(s): s.rev, s.data = 1, {"security": {"minutes": 5}, "weather": {"enabled": False}}
    def save(s, doc):
        if doc["_rev"] != s.rev: raise ValueError("changed on another device")
        s.rev += 1; s.data = {k: v for k, v in doc.items() if k != "_rev"}; return s.rev
def old_client(srv, edits):                      # each change starts at once, from the version it saw (all in flight together)
    seen = {**copy.deepcopy(srv.data), "_rev": srv.rev}; out = []
    for key, val in edits:
        try: srv.save({**copy.deepcopy(seen), key: val}); out.append("ok")
        except ValueError as e: out.append(str(e))
    return out
def new_client(srv, edits):                      # FIX: queue, merge what changed onto the latest, one save for a burst
    seen = copy.deepcopy(srv.data); pending = {k: v for k, v in edits if json.dumps(v) != json.dumps(seen.get(k))}
    srv.save({**copy.deepcopy(srv.data), **pending, "_rev": srv.rev}); return ["ok"]
burst = [("security", {"minutes": 6}), ("security", {"minutes": 7}), ("weather", {"enabled": True}), ("security", {"minutes": 8})]
for f in (old_client, new_client):
    srv = Server(); r = f(srv, burst); print(f.__name__, r, "->", srv.data)
