# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""4.16.3: an update installed from Setup › App on Windows left the new
version without its web pages (it used the older copy's unpacked files,
which were deleted when that copy closed)."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from eaveluxos import autostart
from eaveluxos.version import VERSION
from tests.test_local43 import ServerBase

ROOT = Path(__file__).resolve().parent.parent
PYI = {"_PYI_APPLICATION_HOME_DIR": "T/_MEI1", "_PYI_ARCHIVE_FILE": "x.exe", "_PYI_PARENT_PROCESS_LEVEL": "1",
       "_MEIPASS2": "T/_MEI1", "PATH": "/bin"}


class ChildEnv(unittest.TestCase):
    def test_drops_the_unpacked_folder_and_asks_for_a_fresh_start(self):
        env = autostart.child_env(PYI)
        self.assertEqual(env, {"PATH": "/bin", "PYINSTALLER_RESET_ENVIRONMENT": "1"})
        self.assertNotIn("_PYI_ARCHIVE_FILE", autostart.child_env({"_pyi_archive_file": "y"}) | {})

    def test_leaves_this_process_alone(self):
        before = dict(os.environ)
        autostart.child_env()
        self.assertEqual(dict(os.environ), before)


class BorrowedFiles(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.d, True)

    def test_cases(self):
        self.assertFalse(autostart.borrowed_files(None, VERSION, {}), "from the source code: nothing unpacked")
        self.assertTrue(autostart.borrowed_files(self.d, VERSION, {}), "no marker: 4.16.2 or older's files")
        (self.d / "bundle-version.txt").write_text("0.0.1", encoding="utf-8")
        self.assertTrue(autostart.borrowed_files(self.d, VERSION, {}), "another version's files")
        (self.d / "bundle-version.txt").write_text(VERSION + "\n", encoding="utf-8")
        self.assertFalse(autostart.borrowed_files(self.d, VERSION, {}), "its own")
        self.assertFalse(autostart.borrowed_files(self.d / "nope", VERSION, {autostart.RELAUNCHED: "1"}),
                         "started again once already: never a loop")

    def test_restart_starts_fresh_and_stays_for_the_handover(self):
        popen, slept = mock.Mock(), []
        with mock.patch.dict(os.environ, PYI):
            autostart.restart_on_own_files(self.d, popen=popen, sleep=slept.append)
        env = popen.call_args.kwargs["env"]
        self.assertEqual(env[autostart.RELAUNCHED], "1")
        self.assertEqual(env["PYINSTALLER_RESET_ENVIRONMENT"], "1")
        self.assertFalse([k for k in env if k.startswith(("_PYI_", "_MEIPASS"))])
        self.assertEqual(popen.call_args.args[0][-1], "run")
        self.assertEqual(slept, [autostart.HANDOVER_WAIT])
        self.assertGreater(autostart.HANDOVER_WAIT, 90 + 20, "outlasts an older copy's start and steady checks")


class MainStart(unittest.TestCase):
    def test_a_copy_on_borrowed_files_starts_again_before_anything_else(self):
        sys.path.insert(0, str(ROOT))
        self.addCleanup(sys.path.remove, str(ROOT))
        import main
        with mock.patch.object(main, "FROZEN", True), mock.patch.object(sys, "_MEIPASS", "/nowhere", create=True), \
                mock.patch.object(autostart, "restart_on_own_files") as again, \
                mock.patch.object(main, "already_running", side_effect=AssertionError("checked the port first")):
            self.assertEqual(main.cmd_run(False), 0)
        again.assert_called_once()

    def test_its_own_files_start_normally(self):
        import main
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d, True)
        (d / "bundle-version.txt").write_text(VERSION, encoding="utf-8")
        with mock.patch.object(main, "FROZEN", True), mock.patch.object(sys, "_MEIPASS", str(d), create=True), \
                mock.patch.object(autostart, "restart_on_own_files") as again, \
                mock.patch.object(main, "already_running", return_value=True):
            self.assertEqual(main.cmd_run(False), 0)
        again.assert_not_called()


class Build(unittest.TestCase):
    def test_every_build_carries_its_version(self):
        sys.path.insert(0, str(ROOT / "packaging"))
        self.addCleanup(sys.path.remove, str(ROOT / "packaging"))
        import build
        with mock.patch.object(subprocess, "run") as run:
            build.pyinstaller("EaveLuxOS", "--onefile")
        args = run.call_args.args[0]
        marker = ROOT / "build" / "bundle-version.txt"
        self.assertIn(f"{marker}{build.SEP}.", args)
        self.assertEqual(marker.read_text(encoding="utf-8"), VERSION)


class Spawns(ServerBase):
    def test_update_and_port_move_start_fresh(self):
        with mock.patch.dict(os.environ, PYI), mock.patch.object(subprocess, "Popen") as popen:
            self.app._update_spawn()
        env = popen.call_args.kwargs["env"]
        self.assertEqual(env["PYINSTALLER_RESET_ENVIRONMENT"], "1")
        self.assertFalse([k for k in env if k.startswith(("_PYI_", "_MEIPASS"))])
        src = (ROOT / "eaveluxos" / "server.py").read_text(encoding="utf-8")
        self.assertEqual(src.count('"env": autostart.child_env()'), 2, "the move to another port too")

    def test_a_new_copy_without_its_page_doesnt_count(self):
        from eaveluxos import server as S
        from eaveluxos.server import make_server
        srv = make_server(self.app, "127.0.0.1", 0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        s = json.loads(json.dumps(self.app.store.settings))
        s.setdefault("service", {})["web_port"] = srv.server_address[1]
        self.app.store.save_settings(s)
        self.assertEqual(self.app._update_answers(), VERSION)
        empty = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, empty, True)
        with mock.patch.object(S, "STATIC", empty):
            self.assertIsNone(self.app._update_answers(), "answers, but its page is gone")


class Interrupted(unittest.TestCase):
    def test_an_attempt_closed_by_hand_is_tidied_up(self):
        import time
        from eaveluxos import selfupdate
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d, True)
        plan = {"ok": True, "why": "", "files": ["EaveLuxOS.exe"], "dir": str(d), "kind": "windows"}
        (d / ".eaveluxos-update").mkdir()
        up = selfupdate.Updater(d, plan_=plan)
        up._write(stage="trying", frm="4.16.2", to="4.15.0")
        up.cleanup()
        self.assertEqual(up.state()["stage"], "trying", "a fresh attempt is left alone")
        st = up.state(); st["at"] = time.time() - 600
        up.path.write_text(json.dumps(st), encoding="utf-8")
        up.cleanup()
        self.assertEqual(up.state()["stage"], "interrupted")
        self.assertFalse((d / ".eaveluxos-update").exists())


class Review(unittest.TestCase):
    def test_1_the_new_version_unpacks_its_own_files(self):
        from tests import reprorun
        reprorun.run(self, "repro_update_borrows_files.py", 60)

    def test_2_a_restart_doesnt_resend_a_pattern_sent_over_the_home_network(self):
        from tests import reprorun
        reprorun.run(self, "repro_restart_resends.py", 120)


class RestartKeepsTheWay(ServerBase):
    def test_odd_saved_values_are_left_out(self):
        from eaveluxos.controller import Controller
        c = self.app.ctrl
        c.next_try = 0
        c.tick()
        c._save_state()
        st = json.loads(Path(c.state_path).read_text(encoding="utf-8"))
        st["lan_sent"] = {"A": ["pattern", "nonsense"], "B": "switch", "C": []}
        st["lan_state"] = {"A": 1, "B": 7}
        Path(c.state_path).write_text(json.dumps(st), encoding="utf-8")
        n = Controller(c.cfg, c.api, data_dir=self.app.store.dir)
        self.assertEqual(n.lan_sent, {"A": {"pattern"}})
        self.assertEqual(n.lan_state, {"A": 1})

    def test_an_old_saved_state_keeps_nothing(self):
        import time
        from eaveluxos.controller import Controller
        c = self.app.ctrl
        c.lan_sent, c.lan_state = {"A": {"pattern"}}, {"A": 1}
        c._save_state()
        st = json.loads(Path(c.state_path).read_text(encoding="utf-8"))
        st["saved_at"] = time.time() - 7200
        Path(c.state_path).write_text(json.dumps(st), encoding="utf-8")
        n = Controller(c.cfg, c.api, data_dir=self.app.store.dir)
        self.assertEqual((n.lan_sent, n.lan_state), ({}, {}), "it sends again, so it learns the way again")



class FindAndMatchOne(ServerBase):
    """4.16.4 (Chris, Nov 20): Find and match offered "Use for Trimlight" for
    the address already saved, because it was saved the original way (one
    address for all)."""

    def test_the_address_already_saved_says_so(self):
        from eaveluxos import lanlink
        with mock.patch.object(lanlink, "find", lambda *a, **k: ["127.0.0.1"]):
            r = self.app.local_discover()
        f = r["found"][0]
        self.assertEqual(len(self.app._account()), 1)
        self.assertEqual(f["saved_for"], self.app._account()[0]["id"])


if __name__ == "__main__":
    unittest.main()
