# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""3.7.2: the release is published once, by one job, after all builds pass,
so its notes aren't repeated once per build machine."""
import re
import unittest
from pathlib import Path

WF = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "release.yml"


def jobs(text):
    """{job name: its text}, for the top-level jobs in a workflow file."""
    body = text.split("\njobs:\n", 1)[1]
    parts = re.split(r"^  ([A-Za-z0-9_-]+):\n", body, flags=re.M)
    return {parts[i]: parts[i + 1] for i in range(1, len(parts), 2)}


class ReleaseWorkflow(unittest.TestCase):
    def test_one_publish_job_after_the_builds(self):
        text = WF.read_text(encoding="utf-8")
        j = jobs(text)
        self.assertEqual(text.count("softprops/action-gh-release"), 1)
        self.assertIn("softprops/action-gh-release", j["publish"])
        self.assertNotIn("softprops/action-gh-release", j["build"])
        self.assertIn("needs: build", j["publish"])
        self.assertIn("matrix:", j["build"])
        self.assertNotIn("matrix:", j["publish"])
        self.assertIn("actions/download-artifact", j["publish"])
        self.assertIn("merge-multiple: true", j["publish"])
        self.assertIn("startsWith(github.ref, 'refs/tags/')", j["publish"])


class ZonesEditable(unittest.TestCase):
    def test_house_map_zones_have_an_edit_dialog(self):
        js = (WF.parents[2] / "eaveluxos" / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn('data-editzone="${i}"', js)
        self.assertIn("function zoneDialog(", js)
        for msg in ("Bulbs go from 1 to", "The last bulb can\\u2019t be before the first.", "There's already a zone named"):
            self.assertIn(msg, js)


if __name__ == "__main__":
    unittest.main()
