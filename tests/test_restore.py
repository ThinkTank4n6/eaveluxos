# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Put patterns back from a controller backup (3.15)."""
import copy
import json
import shutil
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from tests import fake_trimlight as F
from tests.test_safety import BASE
from eaveluxos import restore
from eaveluxos.api import TrimlightAPI

NOW = datetime(2026, 11, 14, 9, 0, tzinfo=ZoneInfo("America/New_York"))
DEV = "TL-EDGE-01"


class RestoreTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.saved = copy.deepcopy(F.STATE["dev"])
        self.api = TrimlightAPI(F.CID, F.SECRET, base_url=BASE)
        self.backup = copy.deepcopy(F.STATE["dev"])                    # the controller as backed up
        (self.dir / f"{DEV}-original.json").write_text(json.dumps(self.backup), encoding="utf-8")
        (self.dir / f"{DEV}-20261113-172240-460361.json").write_text(json.dumps(self.backup), encoding="utf-8")
        self.lost = [e for e in self.backup["effects"] if e["category"] == 1][:2]     # deleted since
        F.STATE["dev"]["effects"] = [e for e in F.STATE["dev"]["effects"] if e not in self.lost]
        self.backups_made = []

    def tearDown(self):
        F.STATE["dev"] = self.saved
        for k in ("stale_shadow", "shadow"):
            F.STATE.pop(k, None)
        shutil.rmtree(self.dir, ignore_errors=True)

    def run_restore(self, ids):
        return restore.restore(self.api, DEV, NOW, self.backup, ids, backup=self.backups_made.append)

    def names(self):
        return [e["name"] for e in F.STATE["dev"]["effects"]]

    def test_list_newest_first_original_last(self):
        (self.dir / f"{DEV}-20261114-080000-000001.json").write_text(json.dumps(self.backup), encoding="utf-8")
        (self.dir / "notes.json").write_text("{}", encoding="utf-8")                     # not a backup
        (self.dir / f"{DEV}-20261114-090000-000001.json").write_text("{cut", encoding="utf-8")   # damaged: left out
        files = [b["file"] for b in restore.list_backups(self.dir)]
        self.assertEqual(files, [f"{DEV}-20261114-080000-000001.json", f"{DEV}-20261113-172240-460361.json", f"{DEV}-original.json"])
        self.assertEqual(restore.list_backups(self.dir)[-1]["label"], "Before EaveLuxOS first changed the controller")

    def test_puts_back_missing_patterns_as_new(self):
        before = copy.deepcopy(F.STATE["dev"]["effects"])
        r = self.run_restore([e["id"] for e in self.backup["effects"]])
        self.assertEqual(sorted(r["restored"]), sorted(e["name"] for e in self.lost))
        self.assertEqual(sorted(r["skipped"]), sorted(e["name"] for e in before))      # already there: left alone
        for e in before:
            self.assertIn(e, F.STATE["dev"]["effects"])                                # nothing changed
        ids = [e["id"] for e in F.STATE["dev"]["effects"]]
        self.assertEqual(len(ids), len(set(ids)))
        back = {e["name"]: e for e in F.STATE["dev"]["effects"]}
        for e in self.lost:
            self.assertEqual(back[e["name"]]["pixels"], e["pixels"])                   # same colors
        self.assertEqual(len(self.backups_made), 1)                                    # backed up first

    def test_same_name_twice_in_a_backup(self):
        """Review #7 (3.15.1): the owner's real backup has "0-Security" twice;
        the second was reported as already on the controller."""
        twin = {**copy.deepcopy(self.lost[0]), "id": 77}
        self.backup["effects"].append(twin)
        r = self.run_restore([self.lost[0]["id"], 77])
        self.assertEqual(r["restored"], [self.lost[0]["name"]])
        self.assertEqual(r["duplicates"], [self.lost[0]["name"]])
        self.assertEqual(r["skipped"], [])

    def test_waits_for_the_cloud_between_saves(self):
        F.STATE["stale_shadow"] = True                    # numbering from a stale copy, as on Nov 13
        F.STATE["shadow"] = {e["id"] for e in F.STATE["dev"]["effects"]}
        self.run_restore([e["id"] for e in self.lost])
        ids = [e["id"] for e in F.STATE["dev"]["effects"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.api.get_device(DEV, NOW)                     # still readable

    def test_stops_if_a_number_is_reused(self):
        F.STATE["stale_shadow"] = True
        F.STATE["shadow"] = {e["id"] for e in F.STATE["dev"]["effects"]} - {0}    # forgot pattern #0
        with self.assertRaises(restore.RestoreError) as cm:
            restore.restore(type("NoResync", (TrimlightAPI,), {"resync": None})(F.CID, F.SECRET, base_url=BASE),
                            DEV, NOW, self.backup, [e["id"] for e in self.lost])
        self.assertIn("delete “", str(cm.exception))
        self.assertNotIn("/device/effect/delete", [p for p, _ in F.STATE["log"][-5:]])

    def test_nothing_chosen_or_unreadable_changes_nothing(self):
        with self.assertRaises(restore.RestoreError):
            self.run_restore([])
        F.STATE["fail_get"] = (DEV,)
        try:
            with self.assertRaises(restore.RestoreError):
                self.run_restore([self.lost[0]["id"]])
        finally:
            F.STATE.pop("fail_get")
        self.assertNotIn(self.lost[0]["name"], self.names())

    def test_bad_backup_names_are_refused(self):
        for bad in ("../secret.key", "x.json", f"{DEV}-original.json/../../a"):
            with self.assertRaises(restore.RestoreError):
                restore.read_backup(self.dir, bad)


class Endpoints(unittest.TestCase):
    def test_admin_only_and_lights_tab(self):
        import eaveluxos.server as srv
        self.assertIn("/api/backups", srv.ADMIN_GETS)
        self.assertIn("/api/backups/patterns", srv.ADMIN_GETS)
        self.assertNotIn("/api/backups/restore", srv.EDITOR_POSTS)          # so Administrators only
        js = (Path(__file__).resolve().parent.parent / "eaveluxos" / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn("async function backupPanel", js)
        self.assertIn("backups/restore", js)


if __name__ == "__main__":
    unittest.main()
