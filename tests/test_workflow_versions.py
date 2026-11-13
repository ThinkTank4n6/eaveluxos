# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""GitHub workflows use actions that run on Node.js 24. GitHub removed Node 20
from its runners in September 2026, so older majors would stop working."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml")) + \
    sorted((ROOT / "tools" / "community-library" / ".github" / "workflows").glob("*.yml"))
# The first major version of each action that runs on Node 24.
NODE24 = {"actions/checkout": 5, "actions/setup-python": 6, "actions/upload-artifact": 6,
          "actions/download-artifact": 7, "softprops/action-gh-release": 3}


class WorkflowVersionTests(unittest.TestCase):
    def test_found_the_workflows(self):
        self.assertEqual({p.name for p in WORKFLOWS}, {"release.yml", "tests.yml", "check.yml", "index.yml"})

    def test_every_action_runs_on_node_24(self):
        seen = set()
        for wf in WORKFLOWS:
            for action, ver in re.findall(r"uses:\s*([\w.-]+/[\w.-]+)@v(\d+)", wf.read_text(encoding="utf-8")):
                seen.add(action)
                with self.subTest(workflow=wf.name, action=action):
                    self.assertIn(action, NODE24, "a new action: add its first Node 24 major to NODE24")
                    self.assertGreaterEqual(int(ver), NODE24[action])
        self.assertEqual(seen, set(NODE24))

    def test_no_moving_ubuntu_label(self):
        # ubuntu-latest moves to a new Ubuntu without warning; Python builds can lag behind it.
        for wf in WORKFLOWS:
            with self.subTest(workflow=wf.name):
                self.assertNotIn("ubuntu-latest", wf.read_text(encoding="utf-8"))

    def test_workflows_still_parse(self):
        try:
            import yaml
        except ImportError:
            self.skipTest("PyYAML not installed")
        for wf in WORKFLOWS:
            with self.subTest(workflow=wf.name):
                doc = yaml.safe_load(wf.read_text(encoding="utf-8"))
                self.assertIn("jobs", doc)


if __name__ == "__main__":
    unittest.main()
