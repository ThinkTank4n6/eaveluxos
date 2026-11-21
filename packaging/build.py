# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Build EaveLuxOS for the computer you're on.

    python -m pip install pyinstaller pillow tzdata cryptography certifi
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
    # 4.16.3: which version the bundled files belong to (main.own_files_check)
    marker = ROOT / "build" / "bundle-version.txt"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(version(), encoding="utf-8")
    args = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--name", name,
            "--add-data", f"{marker}{SEP}.",
            "--add-data", f"{ROOT / 'eaveluxos' / 'static'}{SEP}eaveluxos/static",
            "--add-data", f"{ROOT / 'MANUAL.md'}{SEP}.", "--add-data", f"{ROOT / 'LICENSE'}{SEP}.",
            "--collect-submodules", "eaveluxos", "--collect-submodules", "cryptography", "--collect-data", "tzdata",
            # Mozilla's list of certificate authorities: the Mac app can't use the system's (trust.py)
            "--hidden-import", "certifi", "--collect-data", "certifi",
            # Pillow: house photos are shrunk by the app, not the browser (server.shrink_photo)
            "--hidden-import", "PIL.Image", "--hidden-import", "PIL.ImageOps", "--hidden-import", "PIL.JpegImagePlugin",
            "--hidden-import", "PIL.MpoImagePlugin", "--hidden-import", "PIL.PngImagePlugin", "--hidden-import", "PIL.WebPImagePlugin", "--icon", str(ICON),
            "--distpath", str(DIST / "bin"), "--workpath", str(ROOT / "build"), "--specpath", str(ROOT / "build"), *extra]
    subprocess.run(args + [str(ROOT / "main.py")], check=True, cwd=ROOT)


# ------------------------------------------------------------------ Windows
def win_version_file(ver: str, name: str, description: str) -> Path:
    """The details Windows shows under the .exe's Properties › Details
    (4.1.3). An .exe with none looks anonymous to Microsoft Defender's
    guesses; this says what it is and who made it."""
    nums = [int(n) for n in re.findall(r"\d+", ver)[:4]]
    nums += [0] * (4 - len(nums))
    tup = tuple(nums)
    text = f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={tup}, prodvers={tup}, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1,
                    subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'Christopher A. Tankelewicz (ThinkTank4n6)'),
      StringStruct('FileDescription', {description!r}),
      StringStruct('FileVersion', {ver!r}),
      StringStruct('InternalName', {name!r}),
      StringStruct('LegalCopyright', '\u00a9 2026 Christopher A. Tankelewicz (ThinkTank4n6). MIT License.'),
      StringStruct('OriginalFilename', {name + '.exe'!r}),
      StringStruct('ProductName', 'EaveLuxOS'),
      StringStruct('ProductVersion', {ver!r}),
      StringStruct('Comments', 'Schedules Trimlight Edge permanent lights. https://github.com/ThinkTank4n6/eaveluxos')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""
    out = ROOT / "build" / f"{name}-version.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    return out


def build_windows():
    ver = version()
    pyinstaller("EaveLuxOS", "--onefile", "--windowed", "--version-file",
                str(win_version_file(ver, "EaveLuxOS", "EaveLuxOS lighting control for Trimlight Edge")))
    pyinstaller("EaveLuxOS-cli", "--onefile", "--version-file",
                str(win_version_file(ver, "EaveLuxOS-cli", "EaveLuxOS command line")))
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
    # 4.10.1: an Intel Mac gets its own (the usual one is for Apple silicon)
    intel = platform.machine().lower() in ("x86_64", "amd64", "i386")
    out = DIST / ("EaveLuxOS-macOS-Intel.dmg" if intel else "EaveLuxOS-macOS.dmg")
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
