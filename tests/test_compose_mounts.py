"""Exercise modern Compose parsing and bind-source safety without production data."""

import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
import uuid


class ComposeMountTests(unittest.TestCase):
    """Verify that the chosen Compose CLI preserves fail-closed bind semantics."""

    @classmethod
    def setUpClass(cls):
        """Require a modern Compose plugin rather than silently falling back to v1."""
        result = subprocess.run(
            ["docker", "compose", "version", "--short"],
            capture_output=True, text=True, check=True, timeout=30,
        )
        match = re.match(r"v?(\d+)\.", result.stdout.strip())
        if match is None or int(match.group(1)) < 2:
            raise RuntimeError("Docker Compose plugin version 2 or newer is required")

    def setUp(self):
        """Create a private temporary project without application configuration."""
        self.temp = tempfile.TemporaryDirectory(prefix="vps-compose-contract-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = "vps-contract-" + uuid.uuid4().hex[:16]
        self.source = self.root / "required-config.txt"
        self.image = os.environ.get("COMPOSE_TEST_IMAGE", "busybox:1.37.0")
        config = {
            "services": {
                "probe": {
                    "image": self.image,
                    "entrypoint": ["true"],
                    "network_mode": "none",
                    "pull_policy": "never",
                    "volumes": [{
                        "type": "bind",
                        "source": str(self.source),
                        "target": "/contract/config.txt",
                        "read_only": True,
                        "bind": {"create_host_path": False},
                    }],
                },
            },
        }
        self.file = self.root / "compose.json"
        self.file.write_text(json.dumps(config), encoding="utf-8")
        self.env = dict(os.environ, COMPOSE_DISABLE_ENV_FILE="1")
        self.env.pop("COMPOSE_FILE", None)
        self.env.pop("COMPOSE_PROFILES", None)

    def compose(self, *args):
        """Run only this explicit temporary Compose project and capture diagnostics."""
        return subprocess.run(
            ["docker", "compose", "--project-name", self.project,
             "--project-directory", str(self.root), "--file", str(self.file), *args],
            env=self.env, cwd=self.root, capture_output=True, text=True, timeout=60,
        )

    def remove_test_container(self):
        """Remove only this project's never-started probe, without deleting volumes."""
        result = self.compose("rm", "--force", "--stop", "probe")
        self.assertEqual(result.returncode, 0, result.stderr)

    def require_local_image(self):
        """Fail before engine acceptance if the explicit test image is unavailable."""
        result = subprocess.run(
            ["docker", "image", "inspect", self.image],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, "Load COMPOSE_TEST_IMAGE before engine tests")

    def test_long_bind_safety_survives_parsing(self):
        """Modern parsing must retain both read-only and no-auto-create semantics."""
        result = self.compose("config", "--format", "json")
        self.assertEqual(result.returncode, 0, result.stderr)
        mount = json.loads(result.stdout)["services"]["probe"]["volumes"][0]
        self.assertEqual(mount["source"], str(self.source))
        self.assertTrue(mount["read_only"])
        self.assertIs(mount["bind"]["create_host_path"], False)
        self.assertFalse(self.source.exists())

    @unittest.skipUnless(os.environ.get("COMPOSE_ENGINE_TEST") == "1", "engine opt-in required")
    def test_missing_bind_source_fails_without_creating_directory(self):
        """A missing required file must stop creation and remain absent on the host."""
        self.require_local_image()
        self.addCleanup(self.remove_test_container)
        result = self.compose("create", "--pull", "never", "probe")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("bind", result.stderr.lower())
        self.assertFalse(self.source.exists(), result.stderr)

    @unittest.skipUnless(os.environ.get("COMPOSE_ENGINE_TEST") == "1", "engine opt-in required")
    def test_existing_file_binds_read_only_without_running(self):
        """An existing file must mount read-only while its bytes and runtime stay unchanged."""
        self.require_local_image()
        self.source.write_text("isolated acceptance fixture\n", encoding="utf-8")
        self.addCleanup(self.remove_test_container)
        result = self.compose("create", "--pull", "never", "probe")
        self.assertEqual(result.returncode, 0, result.stderr)
        container = self.compose("ps", "--all", "--quiet", "probe")
        self.assertEqual(container.returncode, 0, container.stderr)
        ids = container.stdout.split()
        self.assertEqual(len(ids), 1)
        inspected = subprocess.run(
            ["docker", "inspect", ids[0]], capture_output=True, text=True,
            check=True, timeout=30,
        )
        details = json.loads(inspected.stdout)[0]
        self.assertEqual(details["State"]["Status"], "created")
        mount = next(m for m in details["Mounts"] if m["Destination"] == "/contract/config.txt")
        self.assertFalse(mount["RW"])
        self.assertEqual(mount["Source"], str(self.source))
        self.assertEqual(self.source.read_text(encoding="utf-8"), "isolated acceptance fixture\n")


if __name__ == "__main__":
    unittest.main()
