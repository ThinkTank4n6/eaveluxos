# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""3.7: on Windows, data lives in one fixed place (%LOCALAPPDATA%\\EaveLuxOS)
for every version, and the first start brings over an earlier version's
./data folder. Runs on any system by pretending to be Windows."""
import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from eaveluxos import secretbox, store as store_mod
from eaveluxos.store import Store, previous_data_dir, resolve_data_dir


def make_version(downloads: Path, name: str, effect: str | None = None, secret: str | None = None) -> Path:
    """An unzipped version: Downloads/<name>/eaveluxos/main.py, optionally with
    data saved by that version (made in portable mode, as older versions did)."""
    base = downloads / name / "eaveluxos"
    base.mkdir(parents=True)
    (base / "main.py").write_text("# app\n", encoding="utf-8")
    if effect:
        with mock.patch.dict(os.environ, {"EAVELUXOS_PORTABLE": "1"}):
            st = Store(base)
            s = st.settings
            s["effects"][effect] = {"label": effect, "colors": ["#FF0000"], "counts": [1]}
            st.save_settings(s)
            if secret:
                st.save_secrets(client_secret=secret)
            st.close()
    return base


class FixedWindowsHome(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.downloads = self.tmp / "Downloads"
        self.local = self.tmp / "AppData" / "Local"
        self.env = mock.patch.dict(os.environ, {"LOCALAPPDATA": str(self.local)})
        self.env.start()
        os.environ.pop("EAVELUXOS_PORTABLE", None)
        os.environ.pop("EAVELUXOS_DATA_DIR", None)
        self.win = mock.patch.object(store_mod, "_system", return_value="Windows")
        self.win.start()

    def tearDown(self):
        self.win.stop()
        self.env.stop()
        os.environ["EAVELUXOS_PORTABLE"] = "1"
        shutil.rmtree(self.tmp, ignore_errors=True)

    def open(self, base):
        st = Store(base)
        self.addCleanup(st.close)
        return st

    def test_every_version_uses_the_same_folder(self):
        a = make_version(self.downloads, "eaveluxos-3.6.1")
        b = make_version(self.downloads, "eaveluxos-3.7.0")
        self.assertEqual(resolve_data_dir(a), self.local / "EaveLuxOS")
        self.assertEqual(resolve_data_dir(b), self.local / "EaveLuxOS")

    @unittest.skipUnless(secretbox.available(), "needs the cryptography package")
    def test_first_start_brings_over_the_newest_earlier_version(self):
        make_version(self.downloads, "eaveluxos-3.5.1", effect="older")
        time.sleep(0.05)
        old = make_version(self.downloads, "eaveluxos-3.6.0", effect="mine", secret="s3cr3t")
        files = lambda: sorted(p.name for p in (old / "data").iterdir() if not p.name.endswith(("-wal", "-shm")))
        before = files()
        new = make_version(self.downloads, "eaveluxos-3.7.0")
        st = self.open(new)
        self.assertEqual(st.dir, self.local / "EaveLuxOS")
        self.assertIn("mine", st.settings["effects"])          # the newest copy, not 3.5.1
        self.assertNotIn("older", st.settings["effects"])
        self.assertEqual(st.secrets["client_secret"], "s3cr3t")  # secret.key came too
        self.assertTrue(any("brought over" in w for w in st.warnings))
        self.assertEqual(files(), before)                       # source left in place
        with mock.patch.dict(os.environ, {"EAVELUXOS_PORTABLE": "1"}):
            again = Store(old)
            self.assertIn("mine", again.settings["effects"])     # and still works for that version
            again.close()
        self.assertFalse((new / "data").exists())

    def test_brings_over_its_own_data_folder_first(self):
        make_version(self.downloads, "eaveluxos-3.6.0", effect="sibling")
        time.sleep(0.05)
        here = make_version(self.downloads, "eaveluxos-3.6.1", effect="own")
        self.assertIn("own", self.open(here).settings["effects"])

    def test_only_once_and_never_over_existing_data(self):
        old = make_version(self.downloads, "eaveluxos-3.6.0", effect="first")
        new = make_version(self.downloads, "eaveluxos-3.7.0")
        st = self.open(new)
        s = st.settings
        s["effects"]["changed_later"] = {"label": "x", "colors": ["#00FF00"], "counts": [1]}
        st.save_settings(s)
        st.close()
        make_version(self.downloads, "eaveluxos-3.6.9", effect="newer_old_copy")
        st2 = self.open(new)
        self.assertIn("changed_later", st2.settings["effects"])
        self.assertNotIn("newer_old_copy", st2.settings["effects"])
        self.assertFalse(st2.warnings)
        self.assertTrue((old / "data").exists())

    def test_ignores_folders_that_are_not_eaveluxos(self):
        stranger = self.downloads / "some-other-app" / "thing" / "data"
        stranger.mkdir(parents=True)
        (stranger / "eaveluxos.db").write_bytes(b"x")          # no main.py / EaveLuxOS.exe next to it
        new = make_version(self.downloads, "eaveluxos-3.7.0")
        self.assertIsNone(previous_data_dir(new))
        self.assertFalse(self.open(new).warnings)

    def test_portable_mode_keeps_data_next_to_the_app(self):
        new = make_version(self.downloads, "eaveluxos-3.7.0")
        (new / "portable.txt").write_text("", encoding="utf-8")
        self.assertEqual(resolve_data_dir(new), new / "data")

    def test_unzipped_straight_into_downloads_finds_a_version_folder(self):
        make_version(self.downloads, "eaveluxos-3.6.0", effect="mine")
        new = self.downloads / "eaveluxos"                    # tar -xf eaveluxos-3.7.0.zip in Downloads
        new.mkdir()
        (new / "main.py").write_text("# app\n", encoding="utf-8")
        self.assertIn("mine", self.open(new).settings["effects"])

    def test_bundled_exe_layout_is_found(self):
        exe_dir = self.downloads / "EaveLuxOS-Windows" / "EaveLuxOS"
        exe_dir.mkdir(parents=True)
        (exe_dir / "EaveLuxOS.exe").write_bytes(b"MZ")
        with mock.patch.dict(os.environ, {"EAVELUXOS_PORTABLE": "1"}):
            st = Store(exe_dir)
            s = st.settings
            s["effects"]["from_exe"] = {"label": "x", "colors": ["#0000FF"], "counts": [1]}
            st.save_settings(s)
            st.close()
        new = make_version(self.downloads, "eaveluxos-3.7.0")
        self.assertIn("from_exe", self.open(new).settings["effects"])


class Elsewhere(unittest.TestCase):
    def test_mac_and_linux_unchanged(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            os.environ.pop("EAVELUXOS_PORTABLE", None)
            with mock.patch.object(store_mod, "_system", return_value="Linux"):
                self.assertEqual(resolve_data_dir(tmp), tmp / "data")
        finally:
            os.environ["EAVELUXOS_PORTABLE"] = "1"
            shutil.rmtree(tmp, ignore_errors=True)



class StartAutomatically(unittest.TestCase):
    """3.7: "Start automatically" follows the copy of the app that's running,
    so an update doesn't keep starting the old version at login."""
    def test_repoints_to_the_running_copy(self):
        from eaveluxos import autostart
        tmp = Path(tempfile.mkdtemp())
        try:
            with mock.patch.dict(os.environ, {"APPDATA": str(tmp)}), \
                 mock.patch.object(autostart.platform, "system", return_value="Windows"):
                old, new = tmp / "eaveluxos-3.6.0" / "eaveluxos", tmp / "eaveluxos-3.7.0" / "eaveluxos"
                self.assertFalse(autostart.repoint(new))                 # off: nothing to do
                autostart.set_enabled(old, True)
                vbs = next(tmp.rglob("EaveLuxOS.vbs"))
                self.assertIn(str(old / "main.py"), vbs.read_text(encoding="locale"))
                self.assertTrue(autostart.repoint(new))
                self.assertIn(str(new / "main.py"), vbs.read_text(encoding="locale"))
                self.assertNotIn(str(old / "main.py"), vbs.read_text(encoding="locale"))
                self.assertFalse(autostart.repoint(new))                 # already right
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
