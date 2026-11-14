# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Favorites pinned to Home (3.15)."""
import copy
import unittest
from pathlib import Path

from eaveluxos.schedule import ConfigError, build_config
from eaveluxos.store import DEFAULT_SETTINGS

SECRETS = {"client_id": "x", "client_secret": "y"}
JS = (Path(__file__).resolve().parent.parent / "eaveluxos" / "static" / "app.js").read_text(encoding="utf-8")


def settings(**kw):
    s = copy.deepcopy(DEFAULT_SETTINGS)
    s["location"].update(latitude=39.95, longitude=-75.16)
    s.update(kw)
    return s


class FavoritesTests(unittest.TestCase):
    def test_up_to_six_pattern_names(self):
        build_config(settings(favorites=["christmas", "warm_white"]), SECRETS)
        build_config(settings(favorites=["deleted_since"]), SECRETS)      # a removed pattern is just skipped
        for bad in (["a"] * 7, "christmas", [1, 2], {"a": 1}):
            with self.assertRaises(ConfigError, msg=bad):
                build_config(settings(favorites=bad), SECRETS)

    def test_settings_without_favorites_still_work(self):
        build_config(settings(), SECRETS)

    def test_home_and_patterns_screens(self):
        self.assertIn("const MAX_FAVS = 6;", JS)
        self.assertIn("filter(k => e[k])", JS)                          # deleted patterns drop out
        self.assertIn('data-fav="${esc(k)}"', JS)                        # the star on each pattern
        self.assertIn('<div class="favs">', JS)                          # big buttons on Home
        self.assertIn("All patterns (${effects.length})", JS)            # the rest folded away
        self.assertIn("n.favorites = n.favorites.filter(k => k !== d.del)", JS)   # deleting unpins


if __name__ == "__main__":
    unittest.main()
