# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""A stand-in for Trimlight's cloud API, for tests. It checks the HMAC signature
on every request exactly as the real service is documented to."""
import json, hmac, hashlib, base64, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
CID, SECRET = "community-test", "s3cr3t-value-1234"
STATE = {"dev": {"deviceId": "TL-EDGE-01", "name": "Trimlight", "connectivity": 1, "switchState": 1, "state": 0,
  "colorOrder": 0, "ic": 0, "fwVersionName": "1.17.77",
  "ports": [{"id": 0, "start": 1, "end": 83}, {"id": 1, "start": 84, "end": 138}, {"id": 2, "start": 100, "end": 138}, {"id": 3, "start": 0, "end": 0}],
  "effects": [
    {"id": 0, "name": "0-Security", "category": 1, "mode": 0, "speed": 120, "brightness": 110,
     "pixels": [{"index": i, "count": n, "color": c, "disable": False} for i, (n, c) in enumerate([(7, 0xE0D4A6), (10, 0), (6, 0xE0D4A6), (10, 0), (11, 0xE0D4A6), (6, 0)])]},
    {"id": 1, "name": "9-11", "category": 1, "mode": 0, "speed": 100, "brightness": 200, "pixels": [{"index": 0, "count": 5, "color": 0xFF0000, "disable": False}, {"index": 1, "count": 5, "color": 0xFFFFFF, "disable": False}, {"index": 2, "count": 5, "color": 0x0000FF, "disable": False}]},
    {"id": 2, "name": "American Flag", "category": 1, "mode": 1, "speed": 60, "brightness": 220, "pixels": [{"index": 0, "count": 4, "color": 0xFF0000, "disable": False}, {"index": 1, "count": 4, "color": 0xFFFFFF, "disable": False}, {"index": 2, "count": 4, "color": 0x0033FF, "disable": False}]},
    {"id": 3, "name": "CHRISTMAS", "category": 1, "mode": 0, "speed": 100, "brightness": 220, "pixels": [{"index": 0, "count": 3, "color": 0xFF0000, "disable": False}, {"index": 1, "count": 3, "color": 0x00FF00, "disable": False}]},
    {"id": 4, "name": "Rainbow Gradual Chase", "category": 0, "mode": 0, "speed": 140, "brightness": 255, "pixelLen": 30, "reverse": False}],
  "daily": [{"id": 0, "enable": True, "effectId": 0, "repetition": 1, "startTime": {"hours": 17, "minutes": 30}, "endTime": {"hours": 23, "minutes": 0}},
            {"id": 1, "enable": False, "effectId": 1, "repetition": 1, "startTime": {"hours": 1, "minutes": 0}, "endTime": {"hours": 2, "minutes": 0}}],
  "calendar": [{"id": 0, "effectId": 3, "startDate": {"month": 12, "day": 1}, "endDate": {"month": 12, "day": 31}, "startTime": {"hours": 17, "minutes": 0}, "endTime": {"hours": 24, "minutes": 0}}]},
  "log": [], "more": []}   # "more": extra controllers on the same account (same shape as "dev")
LIST_KEYS = ("deviceId", "name", "switchState", "connectivity", "state", "fwVersionName")
def _dev(body):
    """The controller a request names; requests without one (or an unknown id) use the first."""
    did = body.get("deviceId") if isinstance(body, dict) else None
    return next((x for x in STATE.get("more", []) if x["deviceId"] == did), STATE["dev"])
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _ok(self, payload=None):
        b = json.dumps({"code": 0, "desc": "success", **({"payload": payload} if payload is not None else {})}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def _err(self, code, desc):
        b = json.dumps({"code": code, "desc": desc}).encode()
        self.send_response(200); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def handle_any(self):
        n = int(self.headers.get("Content-Length", 0) or 0); body = json.loads(self.rfile.read(n) or b"{}")
        cid, ts, tok = self.headers.get("S-ClientId"), self.headers.get("S-Timestamp"), self.headers.get("authorization")
        exp = base64.b64encode(hmac.new(SECRET.encode(), f"Trimlight|{cid}|{ts}".encode(), hashlib.sha256).digest()).decode()
        if cid != CID or tok != exp: return self._err(10002, "auth failed")
        p = self.path.replace("/trimlight/v1/oauth/resources", ""); d = _dev(body)
        lim = STATE.get("max_count")
        if lim and any(px.get("count", 0) > lim for px in (body.get("payload") or {}).get("pixels") or []):
            return self._err(12000, "Invalid parameter [pixels]")
        STATE["log"].append((p, body))
        if p == "/devices":
            devs = [STATE["dev"], *STATE.get("more", [])]
            return self._ok({"total": len(devs), "current": 1, "data": [{k: x[k] for k in LIST_KEYS} for x in devs]})
        if p == "/device/get":
            if d["deviceId"] in STATE.get("fail_get", ()): return self._err(10003, "device not responding")
            if STATE.get("fail_12006", 0) > 0:      # a passing out-of-step copy
                STATE["fail_12006"] -= 1
                return self._err(12006, "Device data could not be parsed. Please synchronize the device and retry.")
            ids = [x["id"] for x in d["effects"]]
            if len(set(ids)) != len(ids):   # what the real cloud does with two patterns numbered alike
                return self._err(12006, "Device data could not be parsed. Please synchronize the device and retry. "
                                        f"(unable to identify effect boundary, declared {len(ids)} and scanned {len(set(ids))} effect records)")
            return self._ok({k: v for k, v in d.items() if k != "deviceId"})
        if p == "/device/update":
            pl = body["payload"]
            if "ports" in pl:
                for q in pl["ports"]: d["ports"][q["id"]] = q
            for k in ("name", "ic", "colorOrder", "switchState"):
                if k in pl: d[k] = pl[k]
            return self._ok()
        if p == "/device/effect/save":
            e = dict(body["payload"])
            if e.get("id") is not None and e["id"] >= 0 and any(x["id"] == e["id"] for x in d["effects"]):
                d["effects"] = [x for x in d["effects"] if x["id"] != e["id"]] + [e]
                return self._ok({"id": e["id"]})
            if len(d["effects"]) >= 60: return self._err(10001, "library full")
            # "stale_shadow": like the real cloud, number new patterns from its
            # last copy of the controller, refreshed only by notify-update-shadow.
            used = STATE["shadow"] if STATE.get("stale_shadow") and STATE.get("shadow") is not None else {x["id"] for x in d["effects"]}
            e["id"] = min(i for i in range(60) if i not in used); d["effects"].append(e); return self._ok({"id": e["id"]})
        if p == "/device/effect/delete":
            i = next((n for n, e in enumerate(d["effects"]) if e["id"] == body["payload"]["id"]), None)
            if i is not None: d["effects"].pop(i)     # one record per delete
            return self._ok()
        if p == "/device/calendar/save":
            c = dict(body["payload"])
            if STATE.get("corrupt_calendar"):
                c["startTime"] = {"hours": 1, "minutes": 1}  # simulate a controller that stores something else
            used = {x["id"] for x in d["calendar"]}
            if c.get("id") is None or c["id"] < 0:
                c["id"] = min(i for i in range(60) if i not in used)
            d["calendar"] = [x for x in d["calendar"] if x["id"] != c["id"]] + [c]
            return self._ok({"id": c["id"]})
        if p == "/device/calendar/delete":
            d["calendar"] = [x for x in d["calendar"] if x["id"] != body["payload"]["id"]]; return self._ok()
        if p == "/device/daily/save":
            q = body["payload"]; d["daily"] = [x for x in d["daily"] if x["id"] != q["id"]] + [{k: v for k, v in q.items() if k != "currentDate"}]
            return self._ok()
        # currentEffect as Trimlight documents it: the running effect, id -1 for an unsaved preview.
        if p == "/device/effect/preview":
            d["currentEffect"] = {**body["payload"], "id": -1}; return self._ok()
        if p == "/device/effect/view":
            e = next((x for x in d["effects"] if x["id"] == body["payload"]["id"]), None)
            if e is not None: d["currentEffect"] = dict(e)
            return self._ok()
        if p == "/device/notify-update-shadow":
            STATE["shadow"] = {x["id"] for x in d["effects"]}; return self._ok()
        return self._err(10001, "unknown " + p)
    do_GET = do_POST = handle_any
def start(port=0):
    s = ThreadingHTTPServer(("127.0.0.1", port), H); threading.Thread(target=s.serve_forever, daemon=True).start()
    return s
if __name__ == "__main__":
    start(); import time; time.sleep(10**6)
