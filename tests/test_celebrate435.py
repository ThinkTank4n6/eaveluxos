# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""4.3.5: score celebrations and game-day lights are two separate switches."""
import copy
import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path

from eaveluxos.schedule import build_config
from eaveluxos.store import DEFAULT_SETTINGS


def settings(**gd):
    s = copy.deepcopy(DEFAULT_SETTINGS)
    s["location"].update(latitude=39.95, longitude=-75.16)
    s["effects"]["team_nhl_phi"] = {"label": "Flyers colors", "colors": ["#F74902", "#FFFFFF"], "counts": [4, 4]}
    # 4.28: "during" given, since a team without one now gets game time
    s["gameday"] = {"teams": [{"league": "nhl", "team": "phi", "name": "Flyers", "effect": "team_nhl_phi",
                               "on": "sunset", "off": "23:00", "celebrate": True, "during": "evening"},
                              {"league": "nfl", "team": "phi", "name": "Eagles", "effect": "team_nhl_phi", "during": "evening"}], **gd}
    return s


def cfg(**gd):
    return build_config(settings(**gd), {"client_id": "x", "client_secret": "y"},
                        gamedates={"nhl-phi": {date(2026, 11, 20)}, "nfl-phi": {date(2026, 11, 22)}})


class Switches(unittest.TestCase):
    def game_rules(self, c):
        return [r.name for r in c.schedule.rules if "game day" in r.name]

    def test_celebrations_without_game_day_lights(self):
        c = cfg(enabled=False, celebrate_enabled=True)
        self.assertEqual(list(c.celebrate), ["nhl-phi"])
        self.assertEqual(self.game_rules(c), [])

    def test_game_day_lights_without_celebrations(self):
        c = cfg(enabled=True, celebrate_enabled=False)
        self.assertEqual(c.celebrate, {})
        self.assertEqual(len(self.game_rules(c)), 2)

    def test_settings_from_before_keep_working(self):
        self.assertEqual(list(cfg(enabled=True).celebrate), ["nhl-phi"])     # one switch ran both
        self.assertEqual(cfg(enabled=False).celebrate, {})

    def test_schedules_checked_for_what_needs_them(self):
        from eaveluxos.server import App
        d = Path(tempfile.mkdtemp())
        try:
            app = App(d, start=False)
            s = copy.deepcopy(app.store.settings)
            s.update(settings(enabled=False, celebrate_enabled=True))
            app.store.save_settings(s)
            self.assertEqual([t["name"] for t in app.game_teams()], ["Flyers"])   # the Eagles don't celebrate
            s = copy.deepcopy(app.store.settings)
            s["gameday"]["enabled"] = True
            app.store.save_settings(s)
            self.assertEqual([t["name"] for t in app.game_teams()], ["Flyers", "Eagles"])
            s["gameday"].update(enabled=False, celebrate_enabled=False)
            app.store.save_settings(s)
            self.assertEqual(app.game_teams(), [])
            app.store.close()
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_screen(self):
        js = (Path(__file__).resolve().parent.parent / "eaveluxos" / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="gdparty"', js)
        self.assertIn("Works whether or not game-day lights are on", js)


if __name__ == "__main__":
    unittest.main()
