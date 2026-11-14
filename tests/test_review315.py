# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Fixes from the code review of 3.15.0 (shipped in 3.15.1)."""
import copy
import json
import shutil
import tempfile
import threading
import time
import unittest
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from eaveluxos.server import App, ApiError, make_server

NY = ZoneInfo("America/New_York")


def make_app():
    d = Path(tempfile.mkdtemp())
    a = App(d, start=False)
    s = copy.deepcopy(a.store.settings)
    s["location"].update(latitude=39.95, longitude=-75.16)
    s["setup_done"] = True
    a.store.save_settings(s)
    a.store.save_secrets(client_id="x", client_secret="y")
    a.rebuild()
    return a, d


class PrivateSettings(unittest.TestCase):
    """Review #1: away mode (with the return date) and usage went into
    exported files, and "Replace mine" took someone else's away mode."""

    def setUp(self):
        self.a, self.d = make_app()
        s = copy.deepcopy(self.a.store.settings)
        s["away"] = {"enabled": True, "until": "2026-12-28", "minutes": 20, "seed": "abc"}
        s["usage"] = {"watts": 150, "rate": 0.19}
        self.a.save_settings(s, s.get("_rev"))
        self.srv = make_server(self.a, "127.0.0.1", 0)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown(); self.srv.server_close()
        self.a.store.close()
        shutil.rmtree(self.d, ignore_errors=True)

    def test_export_leaves_them_out(self):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.srv.server_address[1]}/api/export", timeout=10) as r:
            out = json.loads(r.read())
        self.assertNotIn("away", out["settings"])
        self.assertNotIn("usage", out["settings"])
        self.assertIn("effects", out["settings"])

    def test_import_never_takes_them(self):
        theirs = copy.deepcopy(self.a.store.settings)
        theirs["away"] = {"enabled": True, "until": "2027-01-15", "minutes": 60, "seed": "zzz"}
        theirs["usage"] = {"watts": 9, "rate": 2}
        for mode in ("replace", "merge"):
            try:
                self.a.import_settings({"settings": copy.deepcopy(theirs), "mode": mode})
            except ApiError:          # merge: "Everything in that file is already here"
                pass
            self.assertEqual(self.a.store.settings["away"]["until"], "2026-12-28", mode)
            self.assertEqual(self.a.store.settings["usage"]["watts"], 150, mode)



class Learning(unittest.TestCase):
    """Review #2: choosing a pattern in the Trimlight app twice within about
    10 minutes made it "learned" as how the controller reports ours, so it
    was never undone again, even after a restart."""

    def test_a_real_change_is_never_learned(self):
        from tests.test_review5 import PatternCheck, make_cfg
        from eaveluxos.controller import Controller
        pc = PatternCheck()
        for chosen in ({"id": 4, "category": 0, "mode": 12, "speed": 140, "brightness": 255},      # a saved pattern
                       {"id": -1, "category": 0, "mode": 12, "speed": 140, "brightness": 255}):   # a built-in, previewed
            d = tempfile.mkdtemp()
            try:
                api = PatternCheck.Cloud()
                c = Controller(make_cfg(), api, data_dir=d)
                c.tick()
                pc.run_checks(c, 2)
                for _ in range(3):                         # chosen again and again in the app
                    api.current = dict(chosen)
                    pc.run_checks(c, 2)
                    c.tick()
                self.assertFalse(c.reported, chosen)       # nothing learned, nothing saved
                self.assertGreaterEqual(len(pc.previews(api)), 2, chosen)   # undone at least once
                # After a restart it's undone again: only the old, in-memory
                # pause until the next change applied, never a saved one.
                api2 = PatternCheck.Cloud()
                c2 = Controller(make_cfg(), api2, data_dir=d)
                c2.tick()
                api2.current = dict(chosen)
                pc.run_checks(c2, 2)
                c2.tick()
                self.assertEqual(len(pc.previews(api2)), 2, chosen)
            finally:
                shutil.rmtree(d, ignore_errors=True)

    def test_a_slightly_different_report_is_still_learned(self):
        from eaveluxos.controller import Controller
        sent = {"category": 1, "mode": 0, "brightness": 200, "pixels": [{"index": 0, "count": 4, "color": 5}]}
        self.assertTrue(Controller._learnable(sent, {**sent, "id": -1, "brightness": 199}))
        self.assertTrue(Controller._learnable({**sent, "id": 7}, {**sent, "id": -1}))     # a saved pattern run as a preview
        self.assertFalse(Controller._learnable({**sent, "id": 7}, {**sent, "id": 9}))
        self.assertFalse(Controller._learnable(sent, {**sent, "mode": 3}))
        self.assertFalse(Controller._learnable(sent, {**sent, "category": 0}))


    def test_learned_file_written_outside_the_lock(self):
        """Review #9: the file was written while holding the status lock."""
        import inspect
        from eaveluxos.controller import Controller
        self.assertNotIn("open(", inspect.getsource(Controller._learn_reported))
        src = inspect.getsource(Controller._maintenance)
        self.assertLess(src.index("with self.lock:"), src.index("self._save_reported()"))
        self.assertGreater(src.index("self._save_reported()"), src.index("restored = self._check_pattern(t, snap)"))



class RestoreLock(unittest.TestCase):
    """Review #3: putting patterns back held the command lock throughout
    (3 s per pattern: ~3 minutes for 60), so on/off could run late."""

    def test_a_scheduled_change_waits_for_one_pattern_at_most(self):
        from tests import fake_trimlight as F
        from tests.test_safety import BASE
        from eaveluxos import restore
        from eaveluxos.api import TrimlightAPI
        saved = copy.deepcopy(F.STATE["dev"])
        api = TrimlightAPI(F.CID, F.SECRET, base_url=BASE)
        api.resync_wait = 0.3
        det = copy.deepcopy(F.STATE["dev"])
        det["effects"] += [{"id": 40 + i, "name": f"Lost {i}", "category": 1, "mode": 0,
                            "pixels": [{"index": 0, "count": 1, "color": 255, "disable": False}]} for i in range(8)]
        lock, waited, holds = threading.RLock(), [], []

        class Watch:                         # records how long each hold lasts
            def __enter__(self):
                lock.acquire(); self.t = time.time()

            def __exit__(self, *a):
                holds.append(time.time() - self.t); lock.release()

        def scheduler():
            time.sleep(0.5)
            t = time.time()
            with lock:
                waited.append(time.time() - t)
        th = threading.Thread(target=scheduler)
        th.start()
        try:
            r = restore.restore(api, "TL-EDGE-01", datetime.now(NY), det, [40 + i for i in range(8)], lock=Watch())
        finally:
            th.join()
            F.STATE["dev"] = saved
        self.assertEqual(len(r["restored"]), 8)
        self.assertLess(waited[0], 0.6)                      # one pattern's save and wait, not all eight (~2.4 s)
        self.assertLess(max(holds), 0.6)

    def test_save_and_its_wait_stay_together(self):
        import inspect
        from eaveluxos import restore
        src = inspect.getsource(restore.restore)
        unit = src[src.index("with lock:                                  # one save"):src.index("if rid is None or rid in taken")]
        self.assertIn("save_effect", unit)
        self.assertIn("resync(dev, now)", unit)



class RestoreLock(unittest.TestCase):
    """Review #3: putting patterns back held the command lock throughout
    (3 s per pattern: ~3 minutes for 60), so on/off could run late."""

    def test_a_scheduled_change_waits_for_one_pattern_at_most(self):
        from tests import fake_trimlight as F
        from tests.test_safety import BASE
        from eaveluxos import restore
        from eaveluxos.api import TrimlightAPI
        saved = copy.deepcopy(F.STATE["dev"])
        api = TrimlightAPI(F.CID, F.SECRET, base_url=BASE)
        api.resync_wait = 0.3
        det = copy.deepcopy(F.STATE["dev"])
        det["effects"] += [{"id": 40 + i, "name": f"Lost {i}", "category": 1, "mode": 0,
                            "pixels": [{"index": 0, "count": 1, "color": 255, "disable": False}]} for i in range(8)]
        lock, waited, holds = threading.RLock(), [], []

        class Watch:                         # records how long each hold lasts
            def __enter__(self):
                lock.acquire(); self.t = time.time()

            def __exit__(self, *a):
                holds.append(time.time() - self.t); lock.release()

        def scheduler():
            time.sleep(0.5)
            t = time.time()
            with lock:
                waited.append(time.time() - t)
        th = threading.Thread(target=scheduler)
        th.start()
        try:
            r = restore.restore(api, "TL-EDGE-01", datetime.now(NY), det, [40 + i for i in range(8)], lock=Watch())
        finally:
            th.join()
            F.STATE["dev"] = saved
        self.assertEqual(len(r["restored"]), 8)
        self.assertLess(waited[0], 0.6)                      # one pattern's save and wait, not all eight (~2.4 s)
        self.assertLess(max(holds), 0.6)

    def test_save_and_its_wait_stay_together(self):
        import inspect
        from eaveluxos import restore
        src = inspect.getsource(restore.restore)
        unit = src[src.index("with lock:                                  # one save"):src.index("if rid is None or rid in taken")]
        self.assertIn("save_effect", unit)
        self.assertIn("resync(dev, now)", unit)



class GameDayFetching(unittest.TestCase):
    """Review #5: every settings save (starring a pattern, editing a rule)
    made the app fetch every team's schedule from ESPN again."""

    def test_only_a_new_team_triggers_a_fetch(self):
        a, d = make_app()
        try:
            def save(**kw):
                s = copy.deepcopy(a.store.settings)
                s.update(kw)
                a.save_settings(s, s.get("_rev"))
            later = time.time() + 9999
            a.gameday.next_at = later
            save(favorites=["christmas"])
            self.assertEqual(a.gameday.next_at, later)                       # an ordinary save: no fetch
            team = {"league": "nfl", "team": "phi", "name": "Eagles", "effect": "christmas"}
            save(gameday={"enabled": True, "teams": [team]})
            self.assertEqual(a.gameday.next_at, 0)                            # a new team: fetch soon
            a.gameday.next_at = later
            save(gameday={"enabled": True, "teams": [{**team, "off": "22:00"}]})
            self.assertEqual(a.gameday.next_at, later)                       # same team, new time: no fetch
        finally:
            a.store.close()
            shutil.rmtree(d, ignore_errors=True)



class TonightHeading(unittest.TestCase):
    """Review #6: lights on by hand at noon, yet Tonight said "Lights on in
    4 h 45 min". Runs the page's own functions in Node."""

    def heading(self, st):
        import re
        import subprocess
        js = (Path(__file__).resolve().parent.parent / "eaveluxos" / "static" / "app.js").read_text(encoding="utf-8")
        fns = [re.search(r"^function %s\(.*?^}" % n, js, re.S | re.M).group(0) for n in ("inWords", "tonightPanel")]
        prog = ("const esc = s => String(s);\n" + "\n".join(fns) +
                "\nconst h = tonightPanel(%s); console.log(h.match(/<h2>(.*?)<\\/h2>/)[1]);" % json.dumps(st))
        return subprocess.run(["node", "-e", prog], capture_output=True, text=True, check=True).stdout.strip()

    EV = [{"kind": "sunset", "at": "4:45 PM", "in_min": 285, "text": "Sunset"},
          {"kind": "on", "at": "5:00 PM", "in_min": 300, "text": "Every night: Warm white"}]

    def test_by_hand(self):
        st = {"tonight": self.EV, "target": {"on": True, "reason": "manual"}, "next_change": "5:00 PM"}
        self.assertEqual(self.heading(st), "On by hand \u00b7 the schedule takes over at 5:00 PM")
        st["target"] = {"on": False, "reason": "manual"}
        self.assertTrue(self.heading(st).startswith("Off by hand"))

    def test_flash_and_music(self):
        self.assertEqual(self.heading({"tonight": self.EV, "target": {"reason": "flash"}, "flash": {"until": "9:05 PM"}}),
                         "Security flash until 9:05 PM")
        self.assertTrue(self.heading({"tonight": self.EV, "target": {"reason": "music"}, "music": {"scheduled": False}}).startswith("Music show"))

    def test_following_the_schedule(self):
        self.assertEqual(self.heading({"tonight": self.EV, "target": {"on": False, "reason": "schedule"}}), "Lights on in 5 h")



class BackgroundSwitches(unittest.TestCase):
    """Review #10: alerts and game days only started when the update check's
    switch was on."""

    def run_start(self, env):
        import os
        from unittest import mock
        a, d = make_app()
        started = []
        try:
            a.updates.start = lambda: started.append("updates")
            a.alerts.start = lambda: started.append("alerts")
            a.gameday.start = lambda *x: started.append("gameday")
            with mock.patch.dict(os.environ, env):
                a.start()
            return started
        finally:
            a.ctrl and a.ctrl.stop_event.set()
            a.store.close()
            shutil.rmtree(d, ignore_errors=True)

    def test_switches(self):
        self.assertEqual(self.run_start({"EAVELUXOS_BACKGROUND": "1", "EAVELUXOS_UPDATE_CHECK": "0"}), ["alerts", "gameday"])
        self.assertEqual(self.run_start({"EAVELUXOS_BACKGROUND": "1", "EAVELUXOS_UPDATE_CHECK": "1"}), ["updates", "alerts", "gameday"])
        self.assertEqual(self.run_start({"EAVELUXOS_BACKGROUND": "0", "EAVELUXOS_UPDATE_CHECK": "1"}), [])



class CheckSchedulesNow(unittest.TestCase):
    """Review #11: "Check schedules now" waited on ESPN inside the web
    request (up to 20 s per team, twice)."""

    def test_answers_at_once_and_checks_in_the_background(self):
        a, d = make_app()
        try:
            s = copy.deepcopy(a.store.settings)
            s["gameday"] = {"enabled": True, "teams": [{"league": "nfl", "team": "phi", "name": "Eagles", "effect": "christmas"}]}
            a.save_settings(s, s.get("_rev"))
            gate = threading.Event()

            def slow(url):
                gate.wait(5)
                return b'{"events": [{"date": "2026-12-06T18:00Z"}]}'
            a.gameday.fetch = slow
            t = time.time()
            r = a.gameday_refresh_soon()
            self.assertLess(time.time() - t, 0.5)                          # didn't wait for ESPN
            self.assertTrue(r["checking"])
            self.assertTrue(a.gameday_refresh_soon()["checking"])          # a second tap doesn't start another
            gate.set()
            a._gd_thread.join(5)
            self.assertIn("nfl-phi", a.gameday.dates())
            from datetime import date
            self.assertEqual(a.cfg.schedule.day_plan(date(2026, 12, 6)).rule.name, "Eagles game day")   # rebuilt
        finally:
            a.store.close()
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
