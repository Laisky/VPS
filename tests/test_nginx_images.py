"""Offline Compose contract for the NGINX2Root source remediation."""
import json
import os
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class NginxImageTests(unittest.TestCase):
    def test_active_nginx_uses_fixed_stable_image(self):
        for host in ("b1", "fs", "hk"):
            with self.subTest(host=host):
                result = subprocess.run(
                    ["docker", "compose", "--project-directory", str(ROOT),
                     "-f", str(ROOT / (host + "-docker-compose.yml")),
                     "config", "--no-interpolate", "--format", "json"],
                    env=dict(os.environ, COMPOSE_DISABLE_ENV_FILE="1"),
                    capture_output=True, text=True, timeout=30,
                )
                # Do not print complete service definitions or interpolated secrets.
                self.assertEqual(result.returncode, 0, "Compose parsing failed: " + host)
                service = json.loads(result.stdout)["services"]["nginx"]
                self.assertEqual(service["image"], "nginx:1.30.7")


if __name__ == "__main__":
    unittest.main()
