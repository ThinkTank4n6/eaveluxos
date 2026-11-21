# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Who wins tonight (4.15): for one night (noon to noon), each controller's
stretches of time, what shows in each and why, and what it beat.

Everything that wants the lights is ranked the same way the scheduler ranks
it (controller.py): schedule rules, holidays and game days by priority (ties:
the one listed first); a weather rule only replaces a rule's pattern while
that rule has the lights on, and only with a higher priority; automations
and alerts come on top when they happen. This lays that out, and warns about
what's likely to surprise: two things with the same priority at the same
time, a rule that never shows tonight, weather that could take over."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from .schedule import _rank, ts


def _kind(rule) -> str:
    if getattr(rule, "holiday", None):
        return "holiday"
    if getattr(rule, "only_dates", None) is not None:
        return "game day"
    return "rule"


def _desc(rule, at: datetime, w) -> dict:
    eff = rule.pick(w.start, at)[0]
    return {"name": rule.name, "kind": _kind(rule), "priority": rule.priority, "effect": eff.label, "effect_key": eff.key}


def night(cfg, devices: list, d: date, names: dict | None = None) -> dict:
    """devices: controller ids ([] or [None] for one schedule for all)."""
    names = names or {}
    tz = cfg.loc.tz
    start = datetime(d.year, d.month, d.day, 12, 0, tzinfo=tz)
    end = start + timedelta(days=1)
    s0, s1 = ts(start), ts(end)
    out, warnings, seen_ties = {}, [], set()
    devs = [x for x in devices if x] or [None]
    if not cfg.schedule.per_controller:
        devs = [None]                         # every controller follows the same rules: one plan
    for dev in devs:
        sch = cfg.schedule.for_controller(dev)
        ws = [w for dd in (d - timedelta(days=1), d, d + timedelta(days=1)) for r in sch.rules if (w := sch._window(r, dd))]
        edges = sorted({s0, s1} | {ts(t) for w in ws for t in (w.start, w.end) if s0 < ts(t) < s1})
        spans = []
        for a, b in zip(edges, edges[1:]):
            mid = datetime.fromtimestamp((a + b) / 2, tz)
            live = sorted((w for w in ws if w.covers(mid)), key=_rank)
            win = live[0] if live else None
            beaten = []
            seen = set()
            for w in live[1:]:
                if w.rule.name in seen:
                    continue
                seen.add(w.rule.name)
                tie = w.rule.priority == win.rule.priority
                beaten.append({**_desc(w.rule, mid, w),
                               "why": "listed later, same priority" if tie else f"lower priority ({w.rule.priority} < {win.rule.priority})"})
                if tie and (win.rule.name, w.rule.name) not in seen_ties:
                    seen_ties.add((win.rule.name, w.rule.name))
                    warnings.append({"level": "tie", "text": f"“{win.rule.name}” and “{w.rule.name}” both have priority "
                                     f"{win.rule.priority} and overlap; “{win.rule.name}” shows because it’s listed first. "
                                     f"Give the one you want a higher priority."})
            weather = []
            # 4.16.4: weather rules only count while weather is turned on (Alerts › Weather)
            if win is not None and (getattr(cfg, "weather", None) or {}).get("enabled"):
                for wr in sorted(cfg.weather_rules, key=lambda r: (-r.priority, r.order)):
                    if wr.priority > win.rule.priority:
                        weather.append({"name": wr.name, "priority": wr.priority, "when": sorted(wr.tags),
                                        "effect": wr.effect_label})
            row = {"start": a, "end": b, "on": win is not None, "winner": _desc(win.rule, mid, win) if win else None,
                   "beaten": beaten, "weather": weather}
            last = spans[-1] if spans else None
            if last and last["end"] == a and last["on"] == row["on"] and last["winner"] == row["winner"] \
                    and [x["name"] for x in last["beaten"]] == [x["name"] for x in beaten]:
                last["end"] = b
            else:
                spans.append(row)
        for x in spans:
            x["start"] = datetime.fromtimestamp(x["start"], tz).isoformat()
            x["end"] = datetime.fromtimestamp(x["end"], tz).isoformat()
        # A rule that wants tonight but never shows
        shown = {x["winner"]["name"] for x in spans if x["winner"]}
        for w in ws:
            if w.rule.name not in shown and ts(w.end) > s0 and ts(w.start) < s1 and w.start.date() == d:
                tops = []
                for x in spans:
                    if x["winner"] and ts(datetime.fromisoformat(x["start"])) < ts(w.end) and ts(datetime.fromisoformat(x["end"])) > ts(w.start) \
                            and x["winner"]["name"] not in [t["name"] for t in tops]:
                        tops.append(x["winner"])
                if tops and not any(v.get("rule") == w.rule.name and v.get("dev") == dev for v in warnings):
                    by = " and ".join(f"\u201c{t['name']}\u201d (priority {t['priority']})" for t in tops)
                    warnings.append({"level": "hidden", "rule": w.rule.name, "dev": dev,
                                     "text": f"\u201c{w.rule.name}\u201d (priority {w.rule.priority}) doesn\u2019t show tonight"
                                     f"{' on ' + names.get(dev, dev) if dev else ''}: {by} cover{'s' if len(tops) == 1 else ''} its whole time."})
        out[dev or "all"] = spans
    autos = []
    for a in (cfg.automations or []):
        if not a.get("enabled", True):
            continue
        w = a["when"]
        if w["type"] == "time":
            for dd in (d, d + timedelta(days=1)):
                t = w["_at"].resolve(dd, cfg.loc)
                if t is not None and s0 <= ts(t) < s1:
                    autos.append({"name": a["name"], "at": t.isoformat(), "priority": a["priority"], "when": f"at {w['at']}"})
        elif w["type"] in ("score", "game_start", "game_end", "weather", "webhook", "lights"):
            autos.append({"name": a["name"], "at": None, "priority": a["priority"],
                          "when": {"score": "when a team scores", "game_start": "when a game starts", "game_end": "when a game ends",
                                   "weather": "when a weather warning starts", "webhook": f"when the webhook event “{w.get('name')}” comes",
                                   "lights": "when the schedule turns the lights " + ("on" if w.get("on") else "off")}[w["type"]]})
    if any(x["weather"] for sp in out.values() for x in sp):
        warnings.append({"level": "weather", "text": "Weather rules with a higher priority replace the pattern if their weather "
                         "comes while the lights are on (listed under each stretch)."})
    return {"date": d.isoformat(), "start": start.isoformat(), "end": end.isoformat(), "devices": out,
            "warnings": warnings, "automations": autos}
