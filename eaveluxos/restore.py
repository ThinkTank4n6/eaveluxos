# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Put patterns back on a controller from one of its backups (3.15).

The safety net backs up the controller before every change it makes
(data/controller-backups; the first one, from before this app ever wrote to
the controller, is kept forever). After a factory reset, or after deleting a
pattern by mistake, those backups are the only copy of patterns made in the
Trimlight app. This copies chosen ones back.

It only ever adds: a pattern whose name is already on the controller is
skipped, nothing is overwritten or deleted. It backs up the controller first,
lets Trimlight's cloud catch up after each new pattern (saving two in a row
can get both the same number, which leaves the cloud unable to read the
controller: code 12006, Nov 13, 2026), and stops at the first problem.
"""
import contextlib
import json
import logging
import re
import time
from datetime import datetime
from pathlib import Path

from .api import TrimlightError

log = logging.getLogger("eaveluxos.restore")
NAME_RE = re.compile(r"([A-Za-z0-9_-]+)-(\d{8}-\d{6}-\d{6}|original)\.json")
FIELDS = ("name", "category", "mode", "speed", "brightness", "pixelLen", "reverse", "pixels")
MAX_PATTERNS = 60          # the Trimlight Edge library's size


class RestoreError(Exception):
    pass


def _label(stamp: str) -> str:
    if stamp == "original":
        return "Before EaveLuxOS first changed the controller"
    try:
        return datetime.strptime(stamp[:15], "%Y%m%d-%H%M%S").strftime("%b %d, %Y, %I:%M %p").replace(" 0", " ")
    except ValueError:
        return stamp


def list_backups(folder: Path, device: str | None = None) -> list[dict]:
    """Backups, newest first, the original last."""
    out = []
    for f in Path(folder).glob("*.json") if Path(folder).is_dir() else []:
        m = NAME_RE.fullmatch(f.name)
        if not m or (device and m.group(1) != device):
            continue
        try:
            det = json.loads(f.read_text(encoding="utf-8"))
            n = len([e for e in det.get("effects", []) or [] if isinstance(e, dict)])
        except (OSError, ValueError, AttributeError):
            continue
        out.append({"file": f.name, "device": m.group(1), "original": m.group(2) == "original",
                    "label": _label(m.group(2)), "patterns": n, "sort": m.group(2)})
    newest = sorted([b for b in out if not b["original"]], key=lambda b: b["sort"], reverse=True)
    return [{k: v for k, v in b.items() if k != "sort"} for b in newest + [b for b in out if b["original"]]]


def read_backup(folder: Path, name: str) -> dict:
    if not NAME_RE.fullmatch(str(name)):
        raise RestoreError("Unknown backup.")
    f = Path(folder) / name
    try:
        det = json.loads(f.read_text(encoding="utf-8"))
    except OSError:
        raise RestoreError("That backup no longer exists.") from None
    except ValueError:
        raise RestoreError("That backup file is damaged.") from None
    if not isinstance(det, dict):
        raise RestoreError("That backup file is damaged.")
    return det


def patterns_in(det: dict) -> list[dict]:
    """The patterns in a backup, as the screen lists them."""
    out = []
    for e in det.get("effects", []) or []:
        if isinstance(e, dict) and isinstance(e.get("id"), int) and str(e.get("name") or "").strip():
            out.append({"id": e["id"], "name": str(e["name"]), "category": e.get("category"),
                        "kind": "Built-in effect" if e.get("category") == 0 else "Custom colors" if e.get("category") == 1 else "Pattern"})
    return out


def _payload(e: dict) -> dict:
    p = {k: e[k] for k in FIELDS if k in e}
    p["id"] = -1                                       # always a new pattern
    return p


def restore(api, dev: str, now, det: dict, ids: list, backup=None, lock=None) -> dict:
    """Copy the patterns with these backup ids onto the controller.
    backup(detail): saves a backup of the controller first. lock: the
    command lock, held for the first read and for each save together with
    its wait for the cloud (about 3 seconds), and released between patterns,
    so a scheduled on/off never waits for the whole restore (3.15.1). Never
    released between a save and its wait: another new pattern saved before
    the cloud catches up can get the same number. Returns {"restored": [...],
    "skipped": [...], "duplicates": [...]}: skipped were already on the controller;
    duplicates had the same name as another one in the backup."""
    lock = lock or contextlib.nullcontext()
    wanted = {i for i in ids if isinstance(i, int) and not isinstance(i, bool)}
    chosen = [e for e in det.get("effects", []) or [] if isinstance(e, dict) and e.get("id") in wanted]
    if not chosen:
        raise RestoreError("Choose at least one pattern to put back.")
    with lock:
        try:
            cur = api.get_device(dev, now)
        except TrimlightError as e:
            raise RestoreError(f"Couldn't read the controller first, so nothing was changed: {e}") from None
        if backup:
            backup(cur)
    lib = cur.get("effects", []) or []
    have = {str(e.get("name", "")).strip().lower() for e in lib}
    taken = {e.get("id") for e in lib}
    restored, skipped, duplicates = [], [], []
    room = MAX_PATTERNS - len(lib)
    for e in chosen:
        name = str(e.get("name", "")).strip()
        if name.lower() in have:
            # Already on the controller, or a second pattern with the same
            # name in this backup (just put back): say which (3.15.1).
            (duplicates if name in restored or name.lower() in {n.lower() for n in restored} else skipped).append(name)
            continue
        if room <= 0:
            raise RestoreError(f"The controller's pattern library is full ({MAX_PATTERNS}). Put back so far: "
                               f"{', '.join(restored) or 'none'}. Delete some in the Trimlight app, then try again.")
        with lock:                                  # one save and its wait for the cloud, together
            try:
                r = api.save_effect(dev, _payload(e)) or {}
            except TrimlightError as x:
                raise RestoreError(f"Stopped at “{name}”: {x}. Put back so far: {', '.join(restored) or 'none'}.") from None
            rid = r.get("id")
            if rid is not None and rid not in taken:
                resync = getattr(api, "resync", None)  # let the cloud catch up before the next one
                if resync:
                    resync(dev, now)
        # Python's locks aren't first-come, first-served: re-taking it at once
        # would starve a scheduled on/off waiting for it. Give it a turn.
        time.sleep(0.05)
        if rid is None or rid in taken:
            # Numbered like an existing pattern: Trimlight can't read the
            # controller until one of the two is removed, and deleting by
            # number here might remove the other one. Stop and say which.
            log.warning("Restore: Trimlight numbered %r %s, already in use.", name, rid)
            raise RestoreError(f"Trimlight gave “{name}” a number that was already in use, so the restore stopped. "
                               f"If the controller now can't be read, delete “{name}” in the Trimlight Edge app, "
                               "then try again. Put back before it: " + (", ".join(restored) or "none") + ".")
        taken.add(rid)
        have.add(name.lower())
        restored.append(name)
        room -= 1
    if restored:
        try:
            with lock:
                api.get_device(dev, now)               # it still reads normally
        except TrimlightError as x:
            raise RestoreError(f"Put back {', '.join(restored)}, but now the controller can't be read: {x}") from None
    return {"restored": restored, "skipped": skipped, "duplicates": duplicates}
