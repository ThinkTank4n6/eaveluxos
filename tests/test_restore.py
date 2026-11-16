# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Controller backups to put patterns back from (3.15). Putting them back is
over the home network since 4.3: tests/test_local43.py."""
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

    def test_list_newest_first_original_last(self):
        (self.dir / f"{DEV}-20261114-080000-000001.json").write_text(json.dumps(self.backup), encoding="utf-8")
        (self.dir / "notes.json").write_text("{}", encoding="utf-8")                     # not a backup
        (self.dir / f"{DEV}-20261114-090000-000001.json").write_text("{cut", encoding="utf-8")   # damaged: left out
        files = [b["file"] for b in restore.list_backups(self.dir)]
        self.assertEqual(files, [f"{DEV}-20261114-080000-000001.json", f"{DEV}-20261113-172240-460361.json", f"{DEV}-original.json"])
        self.assertEqual(restore.list_backups(self.dir)[-1]["label"], "Before EaveLuxOS first changed the controller")

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
        self.assertFalse(hasattr(restore, "restore"), "4.3: no putting back through the cloud")


if __name__ == "__main__":
    unittest.main()
