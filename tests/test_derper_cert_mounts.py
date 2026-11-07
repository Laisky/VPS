"""Guard DERPer certificate mounts so certificate renewals reach running containers."""

import json
import os
from pathlib import Path
import re
import subprocess
import unittest

REPO = Path(__file__).resolve().parent.parent
CERT_FILE_SUFFIXES = (".pem", ".crt", ".key")
LIVE_LINEAGE = re.compile(r"^(?P<root>.*/letsencrypt)/live/(?P<lineage>[^/]+)$")
DERPER_SERVICE = re.compile(r"^  derper:\s*$", re.M)


def derper_compose_files():
    """derper_compose_files returns every compose file that defines an uncommented derper service."""
    return sorted(path for path in REPO.glob("*-docker-compose.yml")
                  if DERPER_SERVICE.search(path.read_text(encoding="utf-8")))


def rendered_derper(path):
    """rendered_derper returns the derper service as normalized by the Compose CLI for path.

    Service env files live only on the deployment hosts under /opt/configs, so they are
    not resolved; mounts do not depend on them.
    """
    env = dict(os.environ, COMPOSE_DISABLE_ENV_FILE="1")
    env.pop("COMPOSE_FILE", None)
    env.pop("COMPOSE_PROFILES", None)
    result = subprocess.run(
        ["docker", "compose", "--project-directory", str(REPO), "--file", str(path),
         "config", "--no-env-resolution", "--format", "json", "derper"],
        env=env, cwd=REPO, capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        raise AssertionError(f"{path.name}: docker compose config failed: {result.stderr}")
    return json.loads(result.stdout)["services"]["derper"]


class DerperCertMountTests(unittest.TestCase):
    """Verify that every DERPer service mounts certificate lineages, not pinned files."""

    @classmethod
    def setUpClass(cls):
        """setUpClass requires the Compose plugin that the existing mount contract uses."""
        result = subprocess.run(
            ["docker", "compose", "version", "--short"],
            capture_output=True, text=True, check=True, timeout=30,
        )
        match = re.match(r"v?(\d+)\.", result.stdout.strip())
        if match is None or int(match.group(1)) < 2:
            raise RuntimeError("Docker Compose plugin version 2 or newer is required")
        cls.files = derper_compose_files()

    def test_derper_services_are_discovered(self):
        """test_derper_services_are_discovered fails if discovery silently matches nothing."""
        self.assertTrue(self.files, "no compose file defines a derper service")

    def test_no_single_file_certificate_binds(self):
        """test_no_single_file_certificate_binds rejects binds that pin one certificate inode."""
        for path in self.files:
            for mount in rendered_derper(path).get("volumes", []):
                if mount.get("type") != "bind":
                    continue
                with self.subTest(file=path.name, source=mount["source"]):
                    self.assertFalse(
                        mount["source"].endswith(CERT_FILE_SUFFIXES),
                        "bind the certbot live/archive lineage directories instead of a single "
                        "certificate file; a file bind keeps the old inode after renewal",
                    )

    def test_live_lineage_mounts_include_archive(self):
        """test_live_lineage_mounts_include_archive requires live symlink targets to resolve."""
        for path in self.files:
            binds = [m for m in rendered_derper(path).get("volumes", []) if m.get("type") == "bind"]
            targets = {m["target"]: m for m in binds}
            for mount in binds:
                match = LIVE_LINEAGE.match(mount["source"])
                if match is None:
                    continue
                with self.subTest(file=path.name, source=mount["source"]):
                    target = LIVE_LINEAGE.match(mount["target"])
                    self.assertIsNotNone(target, "live lineage must keep its letsencrypt/live/<name> layout")
                    self.assertEqual(target.group("lineage"), match.group("lineage"))
                    archive_target = f"{target.group('root')}/archive/{match.group('lineage')}"
                    archive = targets.get(archive_target)
                    self.assertIsNotNone(archive, f"missing archive mount at {archive_target}")
                    self.assertEqual(
                        archive["source"], f"{match.group('root')}/archive/{match.group('lineage')}")
                    self.assertTrue(mount.get("read_only"), "live lineage must be read-only")
                    self.assertTrue(archive.get("read_only"), "archive lineage must be read-only")


if __name__ == "__main__":
    unittest.main()
