"""Guard DERPer certificate mounts so certificate renewals reach running containers."""

import copy
import shlex
import json
import os
from pathlib import Path
import re
import subprocess
import unittest
import tempfile
import uuid

REPO = Path(__file__).resolve().parent.parent
CERT_FILE_SUFFIXES = (".pem", ".crt", ".key")
LIVE_LINEAGE = re.compile(r"^(?P<root>.*/letsencrypt)/live/(?P<lineage>[^/]+)$")
DERPER_SERVICE = re.compile(r"^\s+derper:\s*$", re.M)


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


AFFECTED_HOSTS = ("hk", "racknerd")


def assert_runtime_contract(service, host):
    """Validate the known deployment contract, including absent-mount failures.

    Strict checks target hosts changed by this PR; other legacy layouts need
    their own review rather than guessed requirements.
    """
    hostname = host + ".laisky.com"
    binds = {m["target"]: m for m in service.get("volumes", []) if m.get("type") == "bind"}
    for kind in ("live", "archive"):
        target = f"/etc/letsencrypt/{kind}/{hostname}"
        mount = binds.get(target)
        assert mount is not None, f"missing required {kind} lineage"
        assert mount["source"] == f"/opt/configs/swag/{host}{target}", "wrong lineage source"
        assert mount.get("read_only"), "lineage must be read-only"
        # Require explicit false: current Compose exports short binds as an empty
        # bind object, which must not be mistaken for an explicit opt-out.
        assert mount.get("bind", {}).get("create_host_path") is False, "lineage must fail closed"
    entry = service.get("entrypoint", [])
    assert len(entry) == 3 and entry[:2] == ["/bin/sh", "-ec"], "shell entrypoint missing"
    commands = [shlex.split(line) for line in entry[2].splitlines() if line.strip()]
    assert ["mkdir", "-p", "/run/derper-certs"] in commands, "alias directory missing"
    for source, suffix in (("fullchain.pem", "crt"), ("privkey.pem", "key")):
        expected = ["ln", "-sfn", f"/etc/letsencrypt/live/{hostname}/{source}",
                    f"/run/derper-certs/{hostname}.{suffix}"]
        assert expected in commands, "certificate alias missing or incorrect"
    invocation = commands[-1]
    assert invocation[:2] == ["exec", "/app/derper"], "derper must replace shell"
    for option in (f"--hostname={hostname}", "-certdir=/run/derper-certs", "-certmode=manual"):
        assert option in invocation, f"missing runtime option {option}"


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
        cls.services = {p.name: rendered_derper(p) for p in cls.files}

    def test_derper_services_are_discovered(self):
        """test_derper_services_are_discovered fails if discovery silently matches nothing."""
        self.assertTrue(self.files, "no compose file defines a derper service")

    def test_no_single_file_certificate_binds(self):
        """test_no_single_file_certificate_binds rejects binds that pin one certificate inode."""
        for path in self.files:
            for mount in self.services[path.name].get("volumes", []):
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
            binds = [m for m in self.services[path.name].get("volumes", []) if m.get("type") == "bind"]
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

    def test_affected_hosts_runtime_contract(self):
        for host in AFFECTED_HOSTS:
            with self.subTest(host=host):
                assert_runtime_contract(self.services[host + "-docker-compose.yml"], host)

    def test_runtime_contract_rejects_regressions(self):
        """Mutation controls prevent a green guard that ignores broken contracts."""
        for host in AFFECTED_HOSTS:
            original = self.services[host + "-docker-compose.yml"]
            mutations = {}
            for kind in ("live", "archive"):
                candidate = copy.deepcopy(original)
                candidate["volumes"] = [m for m in candidate["volumes"] if f"/{kind}/" not in m["target"]]
                mutations["missing " + kind] = candidate
            for field, value in (("read_only", False), ("bind", {"create_host_path": True}), ("bind", {})):
                candidate = copy.deepcopy(original)
                candidate["volumes"][0][field] = value
                mutations[field + repr(value)] = candidate
            for old, new in (("ln -sfn", "echo"), ("-certdir=/run/derper-certs", "-certdir=/wrong"),
                             ("exec /app/derper", "/app/derper")):
                candidate = copy.deepcopy(original)
                candidate["entrypoint"][2] = candidate["entrypoint"][2].replace(old, new)
                mutations[old] = candidate
            for name, candidate in mutations.items():
                with self.subTest(host=host, mutation=name), self.assertRaises(AssertionError):
                    assert_runtime_contract(candidate, host)

    @unittest.skipUnless(os.environ.get("COMPOSE_ENGINE_TEST") == "1", "engine opt-in required")
    def test_actual_lineage_binds_fail_closed(self):
        """Use rendered mount options against disposable missing directories."""
        image = os.environ.get("COMPOSE_TEST_IMAGE", "alpine:3")
        subprocess.run(["docker", "image", "inspect", image], check=True, capture_output=True)
        for host in AFFECTED_HOSTS:
            for original in self.services[host + "-docker-compose.yml"]["volumes"]:
                with self.subTest(host=host, target=original["target"]), tempfile.TemporaryDirectory(prefix="derper-bind-") as root:
                    source = Path(root) / "missing-lineage"
                    mount = copy.deepcopy(original)
                    mount["source"] = str(source)
                    project = "derper-bind-" + uuid.uuid4().hex[:12]
                    config = {"services": {"probe": {"image": image, "entrypoint": ["true"],
                              "network_mode": "none", "pull_policy": "never", "volumes": [mount]}}}
                    path = Path(root) / "compose.json"
                    path.write_text(json.dumps(config))
                    base = ["docker", "compose", "-p", project, "-f", str(path)]
                    try:
                        failed = subprocess.run(base + ["create", "--pull", "never"], capture_output=True, text=True, timeout=60)
                        self.assertNotEqual(failed.returncode, 0)
                        self.assertIn("bind", failed.stderr.lower())
                        self.assertFalse(source.exists())
                        # Original short-syntax control admits the missing source.
                        config["services"]["probe"]["volumes"] = [f"{source}:{mount['target']}:ro"]
                        path.write_text(json.dumps(config))
                        accepted = subprocess.run(base + ["create", "--pull", "never"], capture_output=True, text=True, timeout=60)
                        self.assertEqual(accepted.returncode, 0, accepted.stderr)
                    finally:
                        subprocess.run(base + ["rm", "--force", "--stop"], check=True, capture_output=True, timeout=60)


if __name__ == "__main__":
    unittest.main()
