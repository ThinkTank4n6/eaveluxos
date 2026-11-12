# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Build EaveLuxOS for the computer you're on.

    python -m pip install pyinstaller pillow tzdata cryptography
    python packaging/build.py

Output in dist/:
  Windows        EaveLuxOS-Windows.zip     EaveLuxOS.exe (no console) + EaveLuxOS-cli.exe
  macOS          EaveLuxOS-macOS.dmg       EaveLuxOS.app, drag to Applications
  Linux / Pi     eaveluxos_<ver>_<arch>.deb   installs to /opt/eaveluxos, menu entry, "eaveluxos" command
                 EaveLuxOS-Linux-<arch>.tar.gz   portable folder for other distributions
GitHub builds all of these for every release (.github/workflows/release.yml).
"""
import os
import platform
import plistlib
import re
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
ICON = ROOT / "eaveluxos" / "static" / "icon-512.png"
DOCS = ("README.md", "MANUAL.md", "LICENSE", "CHANGELOG.md")
SEP = ";" if os.name == "nt" else ":"


def version() -> str:
    m = re.search(r'VERSION = "([^"]+)"', (ROOT / "eaveluxos" / "version.py").read_text(encoding="utf-8"))
    return m.group(1) if m else "0.0.0"


def pyinstaller(name: str, *extra: str):
    args = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--name", name,
            "--add-data", f"{ROOT / 'eaveluxos' / 'static'}{SEP}eaveluxos/static",
            "--add-data", f"{ROOT / 'MANUAL.md'}{SEP}.", "--add-data", f"{ROOT / 'LICENSE'}{SEP}.",
            "--collect-submodules", "eaveluxos", "--collect-submodules", "cryptography", "--collect-data", "tzdata", "--icon", str(ICON),
            "--distpath", str(DIST / "bin"), "--workpath", str(ROOT / "build"), "--specpath", str(ROOT / "build"), *extra]
    subprocess.run(args + [str(ROOT / "main.py")], check=True, cwd=ROOT)


# ------------------------------------------------------------------ Windows
def build_windows():
    pyinstaller("EaveLuxOS", "--onefile", "--windowed")
    pyinstaller("EaveLuxOS-cli", "--onefile")
    out = DIST / "EaveLuxOS-Windows.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in ("EaveLuxOS.exe", "EaveLuxOS-cli.exe"):
            z.write(DIST / "bin" / f, f"EaveLuxOS/{f}")
        for doc in DOCS:
            z.write(ROOT / doc, f"EaveLuxOS/{doc}")
    return [out]


# ------------------------------------------------------------------ macOS
def finish_mac_app(app: Path, ver: str):
    """Run without a Dock icon (it's a background service with a web page),
    set the version, then re-sign ad hoc: Apple-silicon Macs refuse to run an
    app whose Info.plist changed after signing."""
    plist = app / "Contents" / "Info.plist"
    info = plistlib.loads(plist.read_bytes())
    info.update({"LSUIElement": True, "CFBundleShortVersionString": ver, "CFBundleVersion": ver,
                 "CFBundleName": "EaveLuxOS", "CFBundleDisplayName": "EaveLuxOS",
                 "NSHumanReadableCopyright": "© 2026 Christopher A. Tankelewicz (ThinkTank4n6). MIT License."})
    plist.write_bytes(plistlib.dumps(info))
    if shutil.which("codesign"):
        subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(app)], check=True)


def make_dmg(app: Path, out: Path):
    stage = DIST / "dmg"
    shutil.rmtree(stage, ignore_errors=True)
    stage.mkdir(parents=True)
    shutil.copytree(app, stage / app.name, symlinks=True)
    (stage / "Applications").symlink_to("/Applications")       # drag-to-install target
    for doc in ("README.md", "MANUAL.md", "LICENSE"):
        shutil.copy(ROOT / doc, stage / doc)
    subprocess.run(["hdiutil", "create", "-volname", "EaveLuxOS", "-srcfolder", str(stage),
                    "-ov", "-format", "UDZO", str(out)], check=True)


def build_mac():
    ver = version()
    pyinstaller("EaveLuxOS", "--windowed", "--onedir", "--osx-bundle-identifier", "com.thinktank4n6.eaveluxos")
    app = DIST / "bin" / "EaveLuxOS.app"
    finish_mac_app(app, ver)
    out = DIST / "EaveLuxOS-macOS.dmg"
    make_dmg(app, out)
    return [out]


# ------------------------------------------------------------------ Linux / Raspberry Pi
DESKTOP = """[Desktop Entry]
Type=Application
Name=EaveLuxOS
GenericName=Lighting control
Comment=The Intelligent Lighting Control Platform
Exec={exec} run --open
Icon=eaveluxos
Terminal=false
Categories=Utility;
"""


def deb_arch(machine: str) -> str:
    return {"x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64", "arm64": "arm64", "armv7l": "armhf"}.get(machine, machine)


def package_linux(binary: Path, ver: str, machine: str) -> list[Path]:
    """Wrap a built executable as a .deb (Debian, Ubuntu, Mint, Raspberry Pi
    OS) and a portable .tar.gz. Separate from the build so it can be tested."""
    arch = deb_arch(machine)
    outs = []
    DIST.mkdir(parents=True, exist_ok=True)
    # portable folder
    tar_out = DIST / f"EaveLuxOS-Linux-{machine}.tar.gz"
    with tarfile.open(tar_out, "w:gz") as t:
        def executable(ti):
            ti.mode = 0o755   # Windows file systems don't keep the execute bit
            return ti
        t.add(binary, "EaveLuxOS/eaveluxos", filter=executable)
        for doc in DOCS:
            t.add(ROOT / doc, f"EaveLuxOS/{doc}")
    outs.append(tar_out)
    # .deb
    if shutil.which("dpkg-deb"):
        root = DIST / "deb"
        shutil.rmtree(root, ignore_errors=True)
        (root / "DEBIAN").mkdir(parents=True)
        (root / "opt/eaveluxos").mkdir(parents=True)
        (root / "usr/bin").mkdir(parents=True)
        (root / "usr/share/applications").mkdir(parents=True)
        (root / "usr/share/icons/hicolor/512x512/apps").mkdir(parents=True)
        (root / f"usr/share/doc/eaveluxos").mkdir(parents=True)
        shutil.copy(binary, root / "opt/eaveluxos/eaveluxos")
        os.chmod(root / "opt/eaveluxos/eaveluxos", 0o755)
        (root / "usr/bin/eaveluxos").symlink_to("/opt/eaveluxos/eaveluxos")
        (root / "usr/share/applications/eaveluxos.desktop").write_text(DESKTOP.format(exec="/opt/eaveluxos/eaveluxos"), encoding="utf-8")
        shutil.copy(ICON, root / "usr/share/icons/hicolor/512x512/apps/eaveluxos.png")
        for doc in ("README.md", "MANUAL.md", "CHANGELOG.md"):
            shutil.copy(ROOT / doc, root / f"usr/share/doc/eaveluxos/{doc}")
        shutil.copy(ROOT / "LICENSE", root / "usr/share/doc/eaveluxos/copyright")
        size_kb = sum(f.stat().st_size for f in root.rglob("*") if f.is_file() and not f.is_symlink()) // 1024
        (root / "DEBIAN/control").write_text(
            "Package: eaveluxos\n"
            f"Version: {ver}\n"
            f"Architecture: {arch}\n"
            "Maintainer: Christopher A. Tankelewicz (ThinkTank4n6)\n"
            f"Installed-Size: {size_kb}\n"
            "Section: utils\n"
            "Priority: optional\n"
            "Description: EaveLuxOS - The Intelligent Lighting Control Platform\n"
            " True sunrise/sunset scheduling, a pattern designer, house map and safety\n"
            " net for Trimlight Edge permanent lighting controllers. Settings are kept\n"
            " per user in ~/.local/share/eaveluxos. Not affiliated with Trimlight.\n", encoding="utf-8")
        deb_out = DIST / f"eaveluxos_{ver}_{arch}.deb"
        subprocess.run(["dpkg-deb", "--root-owner-group", "--build", str(root), str(deb_out)], check=True,
                       stdout=subprocess.DEVNULL)
        outs.append(deb_out)
    return outs


def build_linux():
    pyinstaller("eaveluxos", "--onefile")
    return package_linux(DIST / "bin" / "eaveluxos", version(), platform.machine())


def main():
    shutil.rmtree(DIST, ignore_errors=True)
    system = platform.system()
    outs = {"Windows": build_windows, "Darwin": build_mac, "Linux": build_linux}[system]()
    for o in outs:
        print(f"Built {o}")


if __name__ == "__main__":
    main()
