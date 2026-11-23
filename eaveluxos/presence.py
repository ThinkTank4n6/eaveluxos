# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Who's home (4.18): arriving and leaving, for automations.

Nothing here tracks a phone. The phone does that itself (an iPhone Shortcuts
automation "When I arrive home" / "When I leave home", or the Home Assistant
companion app's zones) and tells this app with a webhook:

    POST /api/hook/presence   {"person": "Chris", "state": "home"}

The people are named under Alerts › Who's home (settings "presence"); only
their names and whether each is home are kept, in presence.json, with the
time of the last change. No locations are sent or stored."""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from .schedule import ConfigError

MAX_PEOPLE = 12
SETTLE_DEFAULT = 2          # minutes (4.18.2): a change this soon after the last one runs no automations
SETTLE_MAX = 30
MAX_NAME = 30
STATES = ("home", "away")


def check_people(raw) -> list[str]:
    """The settings' "presence": {"people": [...]} -> the names, tidied."""
    if raw is None:
        return []
    if not isinstance(raw, dict) or not isinstance(raw.get("people", []), list):
        raise ConfigError("Who's home must be {\"people\": [names]}.")
    out, seen = [], set()
    for p in raw.get("people", []):
        name = " ".join(str(p if isinstance(p, str) else "").split())
        if not 1 <= len(name) <= MAX_NAME or any(ch in name for ch in "<>\"\\"):
            raise ConfigError(f"Who's home: a name is 1 to {MAX_NAME} characters.")
        if name.lower() in seen:
            raise ConfigError(f"Who's home: {name} is on the list twice.")
        seen.add(name.lower())
        out.append(name)
    if len(out) > MAX_PEOPLE:
        raise ConfigError(f"Who's home: up to {MAX_PEOPLE} people.")
    settle_minutes(raw)
    return out


def settle_minutes(raw) -> int:
    """How long after someone's last change another one is only noted
    (a phone at the edge of the Wi-Fi going home, away, home)."""
    v = (raw or {}).get("settle_minutes", SETTLE_DEFAULT) if isinstance(raw, dict) else SETTLE_DEFAULT
    if isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= SETTLE_MAX:
        raise ConfigError(f"Who's home: ignore changes within 0 to {SETTLE_MAX} minutes.")
    return v


class Presence:
    """Whether each person is home, kept across restarts."""

    def __init__(self, data_dir, now=time.time):
        self.path = Path(data_dir) / "presence.json"
        self.now = now
        self.lock = threading.Lock()
        self.state: dict[str, dict] = {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            for k, v in (raw.get("people") or {}).items():
                if isinstance(k, str) and isinstance(v, dict) and v.get("state") in STATES:
                    self.state[k.lower()] = {"name": k[:MAX_NAME], "state": v["state"], "at": float(v.get("at") or 0)}
        except (OSError, ValueError, AttributeError, TypeError):
            pass

    def _save(self):
        try:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"people": {v["name"]: {"state": v["state"], "at": v["at"]}
                                                  for v in self.state.values()}}), encoding="utf-8")
            tmp.replace(self.path)
        except OSError:
            pass

    def find(self, people: list[str], name) -> str | None:
        """The configured name that `name` means (any case), or None."""
        n = " ".join(str(name or "").split()).lower()
        return next((p for p in people if p.lower() == n), None)

    def home(self, people: list[str]) -> set[str]:
        """Those of `people` known to be home."""
        with self.lock:
            return {p for p in people if (self.state.get(p.lower()) or {}).get("state") == "home"}

    def known(self, people: list[str]) -> bool:
        with self.lock:
            return any(p.lower() in self.state for p in people)

    def nobody_home(self, people: list[str]) -> bool | None:
        """True only when every person's phone has said they're away; None
        while someone hasn't said anything yet (Review #1, 4.18)."""
        with self.lock:
            st = [(self.state.get(p.lower()) or {}).get("state") for p in people]
        if "home" in st:
            return False
        return None if not st or None in st else True

    def set(self, people: list[str], person: str, state: str, settle: float = 0) -> dict:
        """person arrived ("home") or left ("away"). Returns what happened:
        changed, first (nobody else was home), last (now nobody is home),
        settling (changed less than `settle` seconds after this person's
        last change: noted, but no automations)."""
        if state not in STATES:
            raise ValueError(state)
        with self.lock:
            before = {p for p in people if (self.state.get(p.lower()) or {}).get("state") == "home"}
            cur = self.state.get(person.lower())
            changed = cur is None or cur["state"] != state
            settling = bool(changed and cur is not None and settle and self.now() - cur.get("at", 0) < settle)
            if changed:
                self.state[person.lower()] = {"name": person, "state": state, "at": self.now()}
                # people taken off the list are forgotten
                keep = {p.lower() for p in people}
                self.state = {k: v for k, v in self.state.items() if k in keep}
                self._save()
            after = {p for p in people if (self.state.get(p.lower()) or {}).get("state") == "home"}
            all_known = all(p.lower() in self.state for p in people)
        # first: nobody else was home; last: everyone is known to be away
        # (someone who hasn't reported yet may be home: Review #1)
        return {"changed": changed, "settling": settling, "first": state == "home" and changed and not (before - {person}),
                "last": state == "away" and changed and not after and all_known, "home": sorted(after)}

    def prune(self, people: list[str]):
        """Forget anyone no longer on the list (their last state too)."""
        keep = {p.lower() for p in people}
        with self.lock:
            if set(self.state) - keep:
                self.state = {k: v for k, v in self.state.items() if k in keep}
                self._save()

    def summary(self, people: list[str]) -> list[dict]:
        with self.lock:
            return [{"name": p, "state": (self.state.get(p.lower()) or {}).get("state"),
                     "at": (self.state.get(p.lower()) or {}).get("at")} for p in people]
