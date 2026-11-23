# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Sharing more than patterns (4.21): Studio shows (presets) and automation
templates, by share code and in the community library.

A shared automation is a template: nothing about the home it came from.
The patterns it uses travel inside it (only self-contained ones, checked
like any shared pattern) and are referred to as "@0", "@1"...; a team
becomes "any team", a person "anyone", a controller "all of them"; a zone
stays by name (and is dropped if the new home has no zone of that name);
a condition on one of your rules and a team's sound don't travel. Added,
the patterns become yours and the automation is added turned off, to look
at before turning it on."""
from __future__ import annotations

import copy
import re
import time

from .automations import ACTIONS, CONDS, EVENTS

MAX_TEMPLATE_PATTERNS = 8
_KEEP_WHEN = ("type", "team", "result", "event", "name", "at", "on", "person", "first", "last")
_KEEP_IF = ("type", "from", "to", "at", "days", "on", "effect")
_KEEP_THEN = ("type", "effect", "color", "zone", "seconds", "minutes")


class TemplateError(ValueError):
    pass


def make_template(a: dict, effects: dict) -> tuple[dict, list[dict]]:
    """An automation (as in settings) -> (template, the patterns it uses)."""
    if not isinstance(a, dict):
        raise TemplateError("No such automation.")
    pats, refs = [], {}

    def ref(key):
        if key in refs:
            return refs[key]
        e = effects.get(key)
        if not isinstance(e, dict) or ("colors" not in e and "builtin" not in e) or e.get("scene"):
            raise TemplateError(f"“{(e or {}).get('label', key)}” lives on your controller or is drawn for your house, "
                                "so this automation can't be shared. Use one of your own color patterns in it.")
        if len(pats) >= MAX_TEMPLATE_PATTERNS:
            raise TemplateError(f"An automation shares at most {MAX_TEMPLATE_PATTERNS} patterns.")
        pats.append({**e, "label": e.get("label") or key})
        refs[key] = f"@{len(pats) - 1}"
        return refs[key]
    w = {k: v for k, v in (a.get("when") or {}).items() if k in _KEEP_WHEN}
    if "team" in w:
        w["team"] = "any"
    if "person" in w:
        w["person"] = "any"
    conds = []
    for c in a.get("if") or []:
        if not isinstance(c, dict) or c.get("type") == "rule":
            continue                                        # your own rule's name means nothing elsewhere
        cc = {k: v for k, v in c.items() if k in _KEEP_IF and not k.startswith("_")}
        if cc.get("type") == "pattern":
            cc["effect"] = ref(cc["effect"])
        conds.append(cc)
    acts = []
    for x in a.get("then") or []:
        if not isinstance(x, dict) or x.get("type") == "sound":
            continue                                        # a team's sound file stays home
        xx = {k: v for k, v in x.items() if k in _KEEP_THEN}
        if xx.get("effect"):
            xx["effect"] = ref(xx["effect"])
        acts.append(xx)
    if not acts:
        raise TemplateError("Only a team's sound is in this automation, which can't be shared.")
    t = {"name": str(a.get("name") or "Automation")[:60], "when": w, "if": conds, "then": acts,
         "priority": a.get("priority", 100), "cooldown": a.get("cooldown", 30), "beats_manual": bool(a.get("beats_manual"))}
    return check_template(t, len(pats)), pats


def check_template(t, n_patterns: int) -> dict:
    """The shape of a template from someone else, before anything is added
    (the full check runs when it's added, as for one made here)."""
    if not isinstance(t, dict):
        raise TemplateError("That shared automation is damaged.")
    w = t.get("when")
    if not isinstance(w, dict) or w.get("type") not in EVENTS:
        raise TemplateError("That shared automation starts with something this version doesn't know.")
    conds, acts = t.get("if") or [], t.get("then")
    if not isinstance(conds, list) or len(conds) > 8 or not isinstance(acts, list) or not 1 <= len(acts) <= 4:
        raise TemplateError("That shared automation is damaged.")
    refs = set()
    for c in conds:
        if not isinstance(c, dict) or c.get("type") not in CONDS or c.get("type") == "rule":
            raise TemplateError("That shared automation has a condition this version doesn't know.")
        if c.get("type") == "pattern":
            refs.add(c.get("effect"))
    for x in acts:
        if not isinstance(x, dict) or x.get("type") not in ACTIONS or x.get("type") == "sound":
            raise TemplateError("That shared automation does something this version doesn't know.")
        if x.get("effect"):
            refs.add(x["effect"])
        if "device" in x:
            raise TemplateError("That shared automation names a controller.")
    for r in refs:
        if not (isinstance(r, str) and re.fullmatch(r"@\d", r) and int(r[1:]) < n_patterns):
            raise TemplateError("That shared automation uses a pattern that isn't in it.")
    if w.get("team", "any") != "any" or w.get("person", "any") != "any":
        raise TemplateError("That shared automation names someone's team or person.")
    out = {k: copy.deepcopy(t[k]) for k in ("name", "when", "if", "then", "priority", "cooldown", "beats_manual") if k in t}
    out["name"] = re.sub(r"\s+", " ", str(out.get("name") or "Shared automation")).strip()[:50] or "Shared automation"
    return out


def install(template: dict, patterns: list[dict], settings: dict) -> tuple[dict, str]:
    """(new settings, the automation's name): the patterns added as yours,
    the automation added turned off."""
    s = copy.deepcopy(settings)
    effects = s.setdefault("effects", {})
    slug = re.sub(r"[^a-z0-9]+", "_", template["name"].lower()).strip("_")[:20] or "auto"
    keys = []
    for i, p in enumerate(patterns):
        k, n = f"shared_{slug}_{i + 1}", 2
        while k in effects:
            k, n = f"shared_{slug}_{i + 1}_{n}", n + 1
        effects[k] = dict(p)
        keys.append(k)
    t = copy.deepcopy(template)
    zones = {str(z.get("name")) for z in ((s.get("map") or {}).get("zones") or []) if isinstance(z, dict)}
    for c in t.get("if", []):
        if c.get("type") == "pattern":
            c["effect"] = keys[int(c["effect"][1:])]
    for x in t["then"]:
        if x.get("effect"):
            x["effect"] = keys[int(x["effect"][1:])]
        if x.get("zone") and x["zone"] not in zones:
            del x["zone"]                                   # no such zone here: the whole house
    names = {a.get("name") for a in s.get("automations") or []}
    name, n = f"{t['name']} (shared)"[:60], 2
    while name in names:
        name, n = f"{t['name']} (shared {n})"[:60], n + 1
    t.update(name=name, id="s" + format(int(time.time() * 1000), "x")[-10:], enabled=False)
    s.setdefault("automations", []).append(t)
    return s, name
