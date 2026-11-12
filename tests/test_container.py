# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""3.4 container support: data folder from EAVELUXOS_DATA_DIR, host names
from EAVELUXOS_ALLOWED_HOSTS, port changes refused, non-root image."""
import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from eaveluxos import server
from eaveluxos.store import resolve_data_dir

ROOT = Path(__file__).resolve().parent.parent


class Container(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        for k in ("EAVELUXOS_DATA_DIR", "EAVELUXOS_ALLOWED_HOSTS"):
            os.environ.pop(k, None)
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_data_dir_from_environment(self):
        os.environ["EAVELUXOS_DATA_DIR"] = str(self.dir / "vol")
        (self.dir / "vol").mkdir()
        self.assertEqual(resolve_data_dir(self.dir / "app"), self.dir / "vol")

    def test_allowed_hosts_from_environment(self):
        os.environ["EAVELUXOS_ALLOWED_HOSTS"] = " Lights.Home.Arpa , nas.local"
        self.assertEqual(server.env_allowed_hosts(), ["lights.home.arpa", "nas.local"])
        self.assertTrue(server.host_allowed("lights.home.arpa:8787", server.env_allowed_hosts()))
        self.assertFalse(server.host_allowed("evil.example", server.env_allowed_hosts()))

    def test_port_change_refused_in_container(self):
        app = server.App(self.dir, start=False)
        old = server.IN_CONTAINER
        server.IN_CONTAINER = True
        try:
            with self.assertRaises(server.ApiError) as e:
                app.change_port(9000)
            self.assertIn("HOST_PORT", str(e.exception))
            self.assertEqual(server.lan_addresses(), [])
        finally:
            server.IN_CONTAINER = old
            app.store.close()

    def test_image_and_compose_never_run_as_root(self):
        df = (ROOT / "Dockerfile").read_text()
        users = re.findall(r"^USER\s+(\S+)", df, re.M)
        self.assertEqual(users[-1], "10001:10001")
        self.assertIn("EAVELUXOS_DATA_DIR=/data", df)
        compose = (ROOT / "compose.yaml").read_text()
        for needle in ('user: "10001:10001"', "read_only: true", "cap_drop: [ALL]", "no-new-privileges:true",
                       "${BIND_ADDRESS:-127.0.0.1}"):
            self.assertIn(needle, compose)


if __name__ == "__main__":
    unittest.main()
