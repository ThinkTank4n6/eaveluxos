"""4.22.5 review #1: Patterns › In the Trimlight app showed "Test Lightning"
as plain "Custom · Static": the controller's Lightning on it was read
(extra: "lightning") but dropped when the card was built. Standalone; BUG,
or OK with --fixed."""
import sys

FIXED = "--fixed" in sys.argv
local = {"patterns": [{"id": 20, "name": "Test Lightning", "effect": {"mode": 0}, "extra": "lightning"}]}


def cards(r):
    effects = [{"id": p["id"], "name": p["name"], **p["effect"]} for p in r["patterns"]]
    if FIXED:
        effects = [{**e, "_fx": p["extra"]} for e, p in zip(effects, r["patterns"])]
    return [f'{e["name"]}: Custom · Static' + (" · ⚡ Lightning" if e.get("_fx") == "lightning" else "")
            for e in effects]


card = cards(local)[0]
print(("OK: " if "Lightning" in card.split(":")[1] else "BUG: ") + card)
