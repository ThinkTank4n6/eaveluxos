# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Put patterns back on a controller from one of its backups (3.15).

The safety net backs up the controller before every change it makes
(data/controller-backups; the first one, from before this app ever wrote to
the controller, is kept forever). After a factory reset, or after deleting a
pattern by mistake, those backups are the only copy of patterns made in the
Trimlight app. This copies chosen ones back.

This module lists and reads the backups. Since 4.3 the patterns are put back
over the home network (localmode.Local.restore), never through Trimlight's
cloud: cloud saves numbered patterns out of step with the controller and
left its copy unreadable (code 12006, Nov 13 and 15, 2026).
"""
import json
import logging
import re
from datetime import datetime
from pathlib import Path


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
