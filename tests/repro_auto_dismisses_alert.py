# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Review #1 (4.11): during a Tornado Warning, an automation that shows a
pattern (or turns the lights off, or flashes one controller) went through the
same path as a choice made by hand, and a choice made by hand means "not now"
to a weather warning: the warning was dismissed and its pattern replaced,
just because a team scored or the clock reached sunset. The controller is
real; the cloud and the Weather Service are faked.
Run: python3 tests/repro_auto_dismisses_alert.py"""
import sys; from pathlib import Path; sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import copy, types
from eaveluxos import automations as AU
from eaveluxos.schedule import build_config
from eaveluxos.server import App
from tests.test_automations411 import EngineBase, auto, settings

t = EngineBase("run"); EngineBase.run = lambda s: None; t.setUp()
s = settings([auto(**{"if": []}, then=[{"type": "show", "effect": "christmas", "minutes": 30}])], t.RULES)
s["weather_alerts"] = {"enabled": True, "groups": ["tornado"], "effect": "severe", "turn_on": True}
t.c.cfg = build_config(s, {"client_id": "x", "client_secret": "y"})
t.c.wx_alerts = types.SimpleNamespace(active=lambda now=None: [{"id": "w1", "event": "Tornado Warning", "group": "tornado", "ends": None}])
t.at(20)
print("before the goal:", t.c._target(commit=False).reason)
app = types.SimpleNamespace(ctrl=t.c)
app.auto_show = lambda x, a, ev: App.auto_show(app, x, a, ev)     # the server's own action
out = AU.Engine(app, now=lambda: 1000.0).event({"type": "score", "team": "nhl-phi", "abbr": "phi", "game": None})
r = t.c._target(commit=False).reason
print("after the goal: ", r, "|", out[0], "| dismissed:", list(t.c.alert_dismissed))
print("OK: the warning stays on top" if r == "alert" and not t.c.alert_dismissed else "BUG: a goal dismissed the Tornado Warning")
