# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""4.1.3: Microsoft Defender flagged EaveLuxOS.exe ("executes commands from an
attacker", a behavior guess). The Windows build now compiles PyInstaller's
launcher from source, gives the .exe its version details, and the release
lists SHA-256 checksums."""
import importlib.util
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_build():
    spec = importlib.util.spec_from_file_location("build413", ROOT / "packaging" / "build.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class VersionDetails(unittest.TestCase):
    def test_version_file_is_what_pyinstaller_reads(self):
        b = load_build()
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        b.ROOT = tmp
        path = b.win_version_file("4.1.3", "EaveLuxOS", "EaveLuxOS lighting control for Trimlight Edge")
        text = path.read_text(encoding="utf-8")
        got = {}

        def rec(kind):
            def f(*a, **k):
                got.setdefault(kind, []).append((a, k))
                return (kind, a, k)
            return f
        # PyInstaller evaluates this file with its own classes; the same names stand in here.
        names = {n: rec(n) for n in ("VSVersionInfo", "FixedFileInfo", "StringFileInfo", "StringTable",
                                     "StringStruct", "VarFileInfo", "VarStruct")}
        eval(text, {"__builtins__": {}}, names)
        self.assertEqual(got["FixedFileInfo"][0][1]["filevers"], (4, 1, 3, 0))
        strings = {a[0]: a[1] for a, _ in got["StringStruct"]}
        self.assertEqual(strings["ProductName"], "EaveLuxOS")
        self.assertEqual(strings["FileVersion"], "4.1.3")
        self.assertEqual(strings["OriginalFilename"], "EaveLuxOS.exe")
        self.assertIn("ThinkTank4n6", strings["CompanyName"])
        self.assertEqual(b.win_version_file("5", "x", "y").read_text(encoding="utf-8").count("(5, 0, 0, 0)"), 2)

    def test_windows_build_uses_it(self):
        src = (ROOT / "packaging" / "build.py").read_text(encoding="utf-8")
        body = src[src.index("def build_windows"):src.index("# ------------------------------------------------------------------ macOS")]
        self.assertEqual(body.count('"--version-file"'), 2)


class Workflow(unittest.TestCase):
    def test_launcher_from_source_and_checksums(self):
        wf = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        step = wf[wf.index("PYINSTALLER_COMPILE_BOOTLOADER") - 400:wf.index("PYINSTALLER_COMPILE_BOOTLOADER") + 200]
        self.assertIn("runner.os == 'Windows'", step)
        self.assertIn("--no-binary pyinstaller pyinstaller==6.11.1", step)
        self.assertIn("continue-on-error: true", step, "a failed compile falls back, never blocks a release")
        self.assertLess(wf.index("PYINSTALLER_COMPILE_BOOTLOADER"), wf.index("python packaging/build.py"))
        self.assertIn("sha256sum -- * > SHA256SUMS.txt", wf)
        self.assertLess(wf.index("SHA256SUMS.txt"), wf.index("softprops/action-gh-release"))


if __name__ == "__main__":
    unittest.main()
