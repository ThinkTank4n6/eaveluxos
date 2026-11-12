# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Guided hardware test: python3 main.py hwtest

Answers the questions only a real controller can: does the cloud accept 90
bulbs per color, does "Port off" (0/0) work, can patterns be saved to the
Trimlight library, does the controller's own timer turn the lights on and off
(the safety net), is the clock set, and how fast can commands be sent.

Safe by design: the controller's state is saved first, every check that
changes something asks before it runs, and everything is put back even if
you stop with Ctrl+C. Results go to data/hardware-test-<time>.txt.
"""
import json
import time
from datetime import datetime, timedelta
from pathlib import Path

from .api import TrimlightAPI, TrimlightError

GREEN, RED, BLACK = 0x00FF00, 0xFF0000, 0x000000


class Report:
    def __init__(self):
        self.rows, self.info = [], []

    def add(self, name, result, detail=""):
        self.rows.append((name, result, detail))

    def text(self):
        out = ["EaveLuxOS hardware test", time.strftime("%Y-%m-%d %H:%M"), ""] + self.info + [""]
        for name, result, detail in self.rows:
            out.append(f"[{result:4}] {name}" + (f": {detail}" if detail else ""))
        return "\n".join(out) + "\n"


def _custom(runs, mode=0, brightness=200):
    return {"category": 1, "mode": mode, "speed": 100, "brightness": brightness,
            "pixels": [{"index": i, "count": n, "color": c, "disable": False} for i, (c, n) in enumerate(runs)]}


def _solid(color, total):
    """One color over the whole roofline, in runs of 60 (safe on any firmware)."""
    runs, left = [], total
    while left > 0 and len(runs) < 30:
        runs.append((color, min(60, left)))
        left -= 60
    return runs


def _dark_after(total, runs):
    """Pad with black so the pattern covers the whole roofline (no repeats)."""
    used = sum(n for _, n in runs)
    rest = max(0, total - used)
    while rest > 0 and len(runs) < 30:
        runs.append((BLACK, min(60, rest)))
        rest -= 60
    return runs


def run(store, data_dir: Path, ask=input, say=print, sleep=time.sleep, now=lambda: datetime.now().astimezone()):
    rep = Report()
    sec = store.secrets
    if not (sec.get("client_id") and sec.get("client_secret")):
        say("Set up your Trimlight account in the app first (Settings).")
        return 2
    api = TrimlightAPI(sec["client_id"], sec["client_secret"])

    def raw_preview(payload):  # bypasses the client's automatic 60-bulb splitting
        return api._request("POST", "/v1/oauth/resources/device/effect/preview", {"deviceId": dev_id, "payload": payload})

    def yes(q):
        while True:
            a = (ask(q + " [y/n] ") or "").strip().lower()
            if a in ("y", "yes", "n", "no"):
                return a.startswith("y")

    say("\nTrimlight hardware test. Watch the house while it runs; it takes about 10 minutes.")
    say("Everything it changes is put back at the end (even if you press Ctrl+C).\n")

    # 1. connect -------------------------------------------------------------
    try:
        devices = api.list_devices()
    except TrimlightError as e:
        rep.add("Connect to Trimlight", "FAIL", str(e))
        return _finish(rep, data_dir, say)
    if not devices:
        rep.add("Connect to Trimlight", "FAIL", "no controllers on this account")
        return _finish(rep, data_dir, say)
    rep.add("Connect to Trimlight", "PASS", ", ".join(f"{d.get('name')} ({d.get('deviceId')})" for d in devices))
    dev = devices[0]
    if len(devices) > 1:
        for i, d in enumerate(devices, 1):
            say(f"  {i}. {d.get('name')}")
        pick = ask("Which controller should be tested? Number: ").strip()
        dev = devices[int(pick) - 1] if pick.isdigit() and 1 <= int(pick) <= len(devices) else devices[0]
    dev_id = dev["deviceId"]

    # 2. read and back up ----------------------------------------------------
    det = api.get_device(dev_id, now())   # this also sends the current time (step 3 checks it)
    backup = data_dir / f"hwtest-backup-{dev_id}-{time.strftime('%Y%m%d-%H%M%S')}.json"
    backup.write_text(json.dumps(det, indent=2))
    ports = det.get("ports", [])
    total = max([p.get("end", 0) for p in ports] + [1])
    rep.info += [f"Controller: {det.get('name')}  firmware {det.get('fwVersionName')}  chip {det.get('ic')}  order {det.get('colorOrder')}",
                 "Ports: " + ", ".join(f"{p['id'] + 1}=[{p.get('start')},{p.get('end')}]" for p in ports),
                 f"Saved patterns: {len(det.get('effects', []))}/60  calendar entries: {len(det.get('calendar', []))}  "
                 f"daily timers on: {sum(1 for x in det.get('daily', []) if x.get('enable'))}",
                 f"Backup of the controller before testing: {backup.name}"]
    rep.add("Read controller", "PASS", f"{total} bulb addresses")
    original_switch = det.get("switchState", 1)
    cleanup = []   # (description, function) run in reverse at the end; bind values as defaults (late binding!)

    try:
        # 3. clock -------------------------------------------------------------
        t = now()
        ok = yes(f"In the Trimlight Edge app, open the controller's Settings. Does Date Time show "
                 f"{t:%Y-%m-%d %H:%M} (give or take a minute)?")
        rep.add("Controller clock set by the app", "PASS" if ok else "FAIL",
                "" if ok else "the time sent with each status request may not set the clock")

        # 4. first bulbs ---------------------------------------------------------
        api.set_switch(dev_id, 1)
        cleanup.append(("put the controller's mode back", lambda: api.set_switch(dev_id, original_switch)))
        api.preview_effect(dev_id, _custom(_dark_after(total, [(RED, 10)])))
        ok = yes("Are the FIRST 10 bulbs red and everything else dark?")
        rep.add("Preview and bulb numbering", "PASS" if ok else "FAIL")

        # 5. 90 per slot ---------------------------------------------------------
        try:
            raw_preview(_custom(_dark_after(total, [(RED, 90)])))
            ok = yes("Are the first 90 bulbs red (count about 90) and the rest dark?")
            rep.add("90 bulbs per color slot", "PASS" if ok else "FAIL",
                    "accepted by the cloud" + ("" if ok else ", but the lights didn't show 90"))
        except TrimlightError as e:
            rep.add("90 bulbs per color slot", "NO", f"cloud refuses runs over 60 ({e}); the app splits them automatically")

        # 6. save to library -----------------------------------------------------
        if yes("Test saving a pattern into the Trimlight app's library? (it's deleted again afterward)"):
            r = api.save_effect(dev_id, {"id": -1, "name": "HW TEST delete me", **_custom([(GREEN, 3), (RED, 3)])}) or {}
            eid = r.get("id")
            if eid is None:
                rep.add("Save pattern to library", "FAIL", "no id returned")
            else:
                cleanup.append(("delete the test pattern", lambda eid=eid: api.effect_delete(dev_id, eid)))
                listed = any(e.get("id") == eid for e in api.get_device(dev_id, now()).get("effects", []))
                seen = yes("Pull down to refresh the Trimlight app's pattern library. Is \u201cHW TEST delete me\u201d there?")
                rep.add("Save pattern to library", "PASS" if listed and seen else "FAIL",
                        f"read back: {'yes' if listed else 'no'}, visible in the app: {'yes' if seen else 'no'}")
        else:
            rep.add("Save pattern to library", "SKIP")

        # 7. port off ------------------------------------------------------------
        if ports and yes("Test turning a port OFF and back on? That section goes dark for a few seconds."):
            unused = [p for p in ports if not (p.get("start") and p.get("end"))]
            p = unused[0] if unused else ports[-1]
            orig = {"id": p["id"], "start": p.get("start", 0), "end": p.get("end", 0)}
            cleanup.append((f"restore port {p['id'] + 1}", lambda orig=orig: api.update_device(dev_id, {"ports": [orig]})))
            api.preview_effect(dev_id, _custom([(GREEN, 1)]))
            try:
                api.update_device(dev_id, {"ports": [{"id": p["id"], "start": 0, "end": 0}]})
                back = next((x for x in api.get_device(dev_id, now()).get("ports", []) if x["id"] == p["id"]), {})
                ok = back.get("start") == 0 and back.get("end") == 0
                dark = True if unused else yes(f"Did the section on port {p['id'] + 1} go dark (the rest stays green)?")
                rep.add("Port off as 0/0", "PASS" if ok and dark else "FAIL", f"read back {back}")
            except TrimlightError as e:
                rep.add("Port off as 0/0", "FAIL", f"refused: {e}")
            api.update_device(dev_id, {"ports": [orig]})
        else:
            rep.add("Port off as 0/0", "SKIP")

        # 8. controller's own timer (safety net) ---------------------------------
        if yes("Test the controller's own timer (the safety net)? Takes about 5 minutes."):
            if any(x.get("enable") for x in det.get("daily", [])):
                say("Note: the Trimlight app's daily timers are on; they may also run during this test.")
            r = api.save_effect(dev_id, {"id": -1, "name": "HW TIMER delete me", **_custom(_solid(GREEN, total))}) or {}
            eid = r.get("id")
            cleanup.append(("delete the timer test pattern", lambda eid=eid: api.effect_delete(dev_id, eid)))
            used = {c.get("id") for c in api.get_device(dev_id, now()).get("calendar", [])}
            cid = min(i for i in range(60) if i not in used)
            start = (now() + timedelta(minutes=2)).replace(second=0, microsecond=0)
            end = start + timedelta(minutes=2)
            entry = {"id": cid, "effectId": eid, "startDate": {"month": start.month, "day": start.day},
                     "endDate": {"month": start.month, "day": start.day},
                     "startTime": {"hours": start.hour, "minutes": start.minute},
                     "endTime": {"hours": end.hour, "minutes": end.minute}}
            api.calendar_save(dev_id, entry)
            cleanup.append(("delete the timer test entry", lambda cid=cid: api.calendar_delete(dev_id, cid)))
            back = next((c for c in api.get_device(dev_id, now()).get("calendar", []) if c.get("id") == cid), None)
            readback = bool(back) and all(back.get(k) == entry[k] for k in ("effectId", "startDate", "endDate", "startTime", "endTime"))
            api.set_switch(dev_id, 0)
            sleep(2)
            api.set_switch(dev_id, 2)   # Timer mode, lights off until the entry starts
            say(f"The lights are off now. They should turn GREEN by themselves at {start:%H:%M} "
                f"and turn OFF at {end:%H:%M}. Don't touch anything.")
            sleep(max(0, (start - now()).total_seconds()) + 30)
            on = yes(f"Did the lights turn green by themselves at {start:%H:%M}?")
            sleep(max(0, (end - now()).total_seconds()) + 30)
            off = yes(f"Did they turn off by themselves at {end:%H:%M}?")
            rep.add("Controller timer turns lights on", "PASS" if on else "FAIL")
            rep.add("Controller timer turns lights off", "PASS" if off else "FAIL")
            rep.add("Timer entry reads back as written", "PASS" if readback else "FAIL", "" if readback else str(back))
        else:
            rep.add("Controller timer (safety net)", "SKIP")

        # 9. command rate --------------------------------------------------------
        if yes("Test how fast commands can be sent? (10 quick color changes)"):
            api.set_switch(dev_id, 1)
            errors, t0 = 0, time.time()
            for i in range(10):
                try:
                    api.preview_effect(dev_id, _custom([(RED if i % 2 else GREEN, 1)]))
                except TrimlightError:
                    errors += 1
                sleep(0.5)
            rep.add("10 commands at 2 per second", "PASS" if not errors else "WARN",
                    f"{errors} refused, {time.time() - t0:.1f}s total")
        else:
            rep.add("Command rate", "SKIP")
    except KeyboardInterrupt:
        rep.add("Stopped early", "SKIP", "Ctrl+C")
    except TrimlightError as e:
        rep.add("Unexpected error", "FAIL", str(e))
    finally:
        for desc, fn in reversed(cleanup):
            try:
                fn()
            except Exception as e:  # keep cleaning up the rest
                rep.add(f"Cleanup: {desc}", "FAIL", str(e))
    return _finish(rep, data_dir, say)


def _finish(rep: Report, data_dir: Path, say) -> int:
    path = data_dir / f"hardware-test-{time.strftime('%Y%m%d-%H%M%S')}.txt"
    path.write_text(rep.text())
    say("\n" + rep.text())
    say(f"Saved to {path}. Start the app again; it puts your schedule back on the lights.")
    return 0 if not any(r[1] == "FAIL" for r in rep.rows) else 1
