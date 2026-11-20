# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Install a new version, and go back if it doesn't start (4.15).

For the Windows and Linux (.tar.gz) downloads, which are single programs in
a folder this app can write to. A Mac app, the Linux package (.deb), a
system service and a copy run from the source code keep updating as before
(a download link and the release notes).

1. Download the release's file for this computer and its SHA256SUMS.txt
   from GitHub (only github.com and GitHub's own download hosts, over
   verified HTTPS), and check the file's SHA-256 against the list. This
   catches a damaged or incomplete download; both come from the same
   release, so it isn't a signature.
2. Unpack it beside the program and check it holds what it should.
3. Rename each program file to NAME.previous (kept for going back) and put
   the new one in its place. Windows allows renaming a running program.
4. Stop this copy's scheduler and web server, start the new copy, and wait
   for it to answer as the new version and keep answering for a while.
5. If it doesn't: stop it, put the previous files back, start them again.
   Either way, data/update.json says what happened, and Setup › App shows it.

Roll back (Setup › App) does steps 3-5 with the .previous files."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

from .trust import client_context

log = logging.getLogger("eaveluxos.selfupdate")

ALLOWED_HOSTS = {"github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com",
                 "github-releases.githubusercontent.com"}
MAX_DOWNLOAD = 400 * 1024 * 1024
START_WAIT = 90.0          # seconds for the new copy to answer as the new version
STEADY = 20.0              # then it must keep answering this long


class UpdateError(Exception):
    pass


def plan(frozen=None, system=None, exe=None, supervised=None, writable=os.access) -> dict:
    """What this copy can do: {"ok", "why", "files": program files in its
    folder, "dir", "kind": "windows"|"linux"}."""
    frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    system = system or platform.system()
    exe = Path(exe or sys.executable)
    if supervised is None:
        supervised = "1" in (os.environ.get("EAVELUXOS_SUPERVISED"), os.environ.get("LUMAOS_SUPERVISED"),
                             os.environ.get("TRIMLIGHT_SUPERVISED"))
    no = lambda why: {"ok": False, "why": why, "files": [], "dir": str(exe.parent), "kind": None}
    if not frozen:
        return no("This copy runs from the source code: update it with git pull or the new source zip.")
    if supervised:
        return no("A system service runs this copy: install the new version the way you installed this one.")
    if system == "Windows":
        names = [n for n in ("EaveLuxOS.exe", "EaveLuxOS-cli.exe") if (exe.parent / n).is_file()]
        kind = "windows"
    elif system == "Linux":
        if str(exe).startswith(("/opt/", "/usr/")):
            return no("This copy was installed as a package (.deb): install the new package the same way.")
        names = [exe.name]
        kind = "linux"
    else:
        return no("On a Mac, open the new download and drag EaveLuxOS to Applications, as before.")
    if exe.name not in names:
        return no("This program's name isn't one the download replaces.")
    if not writable(str(exe.parent), os.W_OK):
        return no(f"This app can't write to its own folder ({exe.parent}): update it by hand.")
    return {"ok": True, "why": "", "files": names, "dir": str(exe.parent), "kind": kind}


class _OnlyGitHub(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        u = urllib.parse.urlparse(newurl)
        if u.scheme != "https" or u.hostname not in ALLOWED_HOSTS:
            raise UpdateError(f"The download was sent to {u.hostname}, which isn't GitHub. Stopped.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _open(url: str):
    u = urllib.parse.urlparse(url)
    if u.scheme != "https" or u.hostname not in ALLOWED_HOSTS:
        raise UpdateError("Only downloads from GitHub are used.")
    opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=client_context()), _OnlyGitHub)
    from .version import VERSION
    return opener.open(urllib.request.Request(url, headers={"User-Agent": f"EaveLuxOS/{VERSION}"}), timeout=60)


def download(url: str, dest: Path, opener=_open) -> str:
    """Save url to dest; returns its SHA-256 (hex)."""
    h, n = hashlib.sha256(), 0
    try:
        with opener(url) as r, open(dest, "wb") as f:
            while True:
                chunk = r.read(1 << 16)
                if not chunk:
                    break
                n += len(chunk)
                if n > MAX_DOWNLOAD:
                    raise UpdateError("The download is far larger than any EaveLuxOS release. Stopped.")
                h.update(chunk)
                f.write(chunk)
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        raise UpdateError(f"The download didn't finish: {getattr(e, 'reason', e)}") from None
    return h.hexdigest()


def expected_hash(sums: str, name: str) -> str:
    for line in sums.splitlines():
        parts = line.strip().split()
        if len(parts) == 2 and parts[1].lstrip("*") == name and len(parts[0]) == 64:
            return parts[0].lower()
    raise UpdateError(f"The release's SHA256SUMS.txt doesn't list {name}.")


def unpack(archive: Path, into: Path, kind: str, files: list[str]) -> dict:
    """{program name: unpacked path}. Refuses anything outside `into`."""
    if into.exists():
        shutil.rmtree(into, ignore_errors=True)
    into.mkdir(parents=True)
    got = {}
    if kind == "windows":
        with zipfile.ZipFile(archive) as z:
            for info in z.infolist():
                name = Path(info.filename).name
                if name in files and not info.is_dir():
                    out = into / name
                    with z.open(info) as src, open(out, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    got[name] = out
    else:
        with tarfile.open(archive, "r:gz") as t:
            for m in t.getmembers():
                name = Path(m.name).name
                if name in files and m.isfile():
                    out = into / name
                    with t.extractfile(m) as src, open(out, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    out.chmod(0o755)
                    got[name] = out
    missing = [f for f in files if f not in got]
    if missing:
        raise UpdateError(f"The download doesn't hold {', '.join(missing)}.")
    return got


def swap_in(folder: Path, new: dict) -> list[tuple[Path, Path]]:
    """Each program -> NAME.previous, the new one in its place. Undone if
    any step fails. Returns [(program, previous)]."""
    done = []
    try:
        for name, src in new.items():
            cur, prev = folder / name, folder / (name + ".previous")
            if prev.exists():
                prev.unlink()
            cur.rename(prev)
            done.append((cur, prev))
            shutil.move(str(src), str(cur))
    except OSError as e:
        swap_back(done)
        raise UpdateError(f"Couldn't put the new version in place ({e}); nothing was changed.") from None
    return done


def swap_back(done):
    """Put the .previous files back (the new ones go to NAME.failed)."""
    for cur, prev in reversed(done):
        try:
            if cur.exists():
                failed = cur.with_name(cur.name + ".failed")
                if failed.exists():
                    failed.unlink()
                cur.rename(failed)
            prev.rename(cur)
        except OSError as e:
            log.error("Couldn't put %s back: %s", cur, e)


class Updater:
    """state file: data/update.json. hooks: stop() (this copy's scheduler and
    web server), spawn() -> process (the program, started again), answers()
    -> the version answering on the port or None, quit() (this process)."""

    def __init__(self, data_dir: Path, plan_=None, stop=None, spawn=None, answers=None, quit=None,
                 sleep=time.sleep, clock=time.monotonic, opener=_open):
        self.path = Path(data_dir) / "update.json"
        self.plan = plan_ or plan()
        self.stop, self.spawn, self.answers, self.quit = stop, spawn, answers, quit
        self.sleep, self.clock, self.opener = sleep, clock, opener
        self.busy = False

    def state(self) -> dict:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _write(self, **kw):
        st = {**self.state(), **kw, "at": time.time()}
        try:
            self.path.write_text(json.dumps(st), encoding="utf-8")
        except OSError:
            pass
        return st

    def cleanup(self):
        """Review #2: after an update finished (either way), the download and
        the unpacked copy (about a hundred megabytes) go."""
        if not self.plan["ok"] or self.state().get("stage") not in ("done", "rolled_back"):
            return
        work = Path(self.plan["dir"]) / ".eaveluxos-update"
        if work.is_dir():
            shutil.rmtree(work, ignore_errors=True)
        for n in self.plan["files"]:
            f = Path(self.plan["dir"]) / (n + ".failed")
            try:
                f.unlink(missing_ok=True)
            except OSError:
                pass

    def can_roll_back(self) -> bool:
        if not self.plan["ok"]:
            return False
        folder = Path(self.plan["dir"])
        return all((folder / (n + ".previous")).is_file() for n in self.plan["files"])

    def prepare(self, release: dict, asset: str) -> dict:
        """Download, check and unpack. Returns {name: unpacked path}."""
        if not self.plan["ok"]:
            raise UpdateError(self.plan["why"])
        assets = release.get("assets") or {}
        if asset not in assets or "SHA256SUMS.txt" not in assets:
            raise UpdateError("This release doesn't have a download for this computer with its SHA256SUMS.txt.")
        folder = Path(self.plan["dir"])
        work = folder / ".eaveluxos-update"
        work.mkdir(exist_ok=True)
        sums = work / "SHA256SUMS.txt"
        download(assets["SHA256SUMS.txt"], sums, self.opener)
        want = expected_hash(sums.read_text(encoding="utf-8", errors="replace"), asset)
        archive = work / asset
        got = download(assets[asset], archive, self.opener)
        if got != want:
            archive.unlink(missing_ok=True)
            raise UpdateError("The download's SHA-256 doesn't match the release's list. It wasn't installed.")
        new = unpack(archive, work / "new", self.plan["kind"], self.plan["files"])
        self._write(stage="ready", to=release["version"], sha256=got)
        return new

    def install(self, new: dict, frm: str, to: str):
        """Swap in, hand over to the new copy, and go back if it doesn't
        start. Ends this process either way (quit())."""
        folder = Path(self.plan["dir"])
        done = swap_in(folder, new)
        self._write(stage="trying", frm=frm, to=to)
        log.info("Update: starting EaveLuxOS %s (from %s).", to, frm)
        self._handover(done, frm, to)

    def roll_back(self, frm: str):
        """Put the previous version back (Setup › App › Roll back)."""
        if not self.can_roll_back():
            raise UpdateError("There's no previous version kept here to go back to.")
        folder = Path(self.plan["dir"])
        prev = self.state().get("frm") or "the previous version"
        work = folder / ".eaveluxos-update" / "back"
        work.mkdir(parents=True, exist_ok=True)
        new = {}
        for n in self.plan["files"]:
            shutil.copy2(folder / (n + ".previous"), work / n)
            new[n] = work / n
        done = swap_in(folder, new)
        self._write(stage="trying", frm=frm, to=prev, manual_back=True)
        self._handover(done, frm, prev if prev != "the previous version" else None)

    def _handover(self, done, frm: str, to: str | None):
        self.stop()
        proc = None
        why = None
        try:
            proc = self.spawn()
            end = self.clock() + START_WAIT
            while True:
                if proc.poll() is not None:
                    why = f"the new copy closed (code {proc.returncode})"
                    break
                v = self.answers()
                if v and (to is None or v == to):
                    break
                if self.clock() > end:
                    why = "the new copy didn't answer in time"
                    break
                self.sleep(0.5)
            if why is None:
                steady = self.clock() + STEADY
                while self.clock() < steady:
                    self.sleep(1.0)
                    if proc.poll() is not None or not self.answers():
                        why = "the new copy stopped answering soon after starting"
                        break
        except Exception as e:          # never leave the house without a running copy
            why = f"starting it failed ({e})"
        if why is None:
            self._write(stage="done", frm=frm, to=to, why=None)
            log.info("Update: %s is running. This copy (%s) closes.", to, frm)
            return self.quit()
        log.error("Update to %s failed: %s. Going back to %s.", to, why, frm)
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        swap_back(done)
        self._write(stage="rolled_back", frm=frm, to=to, why=why)
        try:
            self.spawn()
        except Exception as e:
            log.error("Couldn't start %s again: %s. Start EaveLuxOS by hand.", frm, e)
        return self.quit()
