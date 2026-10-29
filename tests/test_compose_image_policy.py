"""Check routine application image tags without reading production environment files."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

# These are application services, not a registry-prefix rule. Keep databases,
# attestation, networking infrastructure and deliberate rollback images outside
# this list. A service whose upstream has no latest tag needs separate review.
APPLICATIONS = {
    "b1-docker-compose.yml": {
        "oneapi": "ppcelery/one-api",
        "graphql": "ppcelery/laisky-blog-graphql",
        "blog-v2": "ppcelery/laisky-blog-v2",
        "go-ramjet": "ppcelery/go-ramjet",
        "wiki": "ppcelery/wiki",
    },
    "racknerd-docker-compose.yml": {
        "oneapi": "ppcelery/one-api",
        "blog-v2": "ppcelery/laisky-blog-v2",
        "go-ramjet": "ppcelery/go-ramjet",
        "wiki": "ppcelery/wiki",
        "channel_boardcast": "ppcelery/boardcastchannel",
    },
    "home-docker-compose.yml": {
        "go-ramjet": "ppcelery/go-ramjet",
        "ramjet": "ppcelery/ramjet",
        "pdf": "frooodle/s-pdf",
        "metube": "ghcr.io/alexta69/metube",
    },
}


def policy_errors(expected, services):
    """Return service names that do not select their intended latest image."""
    failures = []
    for name, repository in expected.items():
        service = services.get(name)
        image = service.get("image") if isinstance(service, dict) else None
        # An untagged Docker reference selects latest; allow it for compatibility
        # while an explicit :latest tag is preferred for clarity.
        if image not in (repository, repository + ":latest"):
            failures.append(name)
    return failures


def compose_services(file_name):
    """Parse a checked-in Compose file without resolving env files or values."""
    env = dict(os.environ)
    env["COMPOSE_DISABLE_ENV_FILE"] = "1"
    env.pop("COMPOSE_FILE", None)
    env.pop("COMPOSE_PROFILES", None)
    result = subprocess.run(
        ["docker", "compose", "--profile", "*", "-f", str(ROOT / file_name),
         "config", "--no-env-resolution", "--no-interpolate",
         "--no-path-resolution", "--format", "json"],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=30,
    )
    if result.returncode:
        raise RuntimeError("Compose parsing failed for " + file_name)
    return json.loads(result.stdout)["services"]


class ApplicationImagePolicyTests(unittest.TestCase):
    """Keep selected application images on latest while preserving pinned infrastructure."""

    def test_current_application_images_resolve_to_latest(self):
        for file_name, expected in APPLICATIONS.items():
            with self.subTest(compose_file=file_name):
                self.assertEqual(policy_errors(expected, compose_services(file_name)), [])

    def test_real_compose_mutation_rejects_fixed_app_tag(self):
        source = (ROOT / "b1-docker-compose.yml").read_text(encoding="utf-8")
        original = "image: ppcelery/laisky-blog-graphql:latest"
        self.assertEqual(source.count(original), 1)
        with tempfile.TemporaryDirectory(prefix="vps-image-policy-") as directory:
            candidate = Path(directory) / "compose.yml"
            candidate.write_text(source.replace(original, "image: ppcelery/laisky-blog-graphql:v1"),
                                 encoding="utf-8")
            failures = policy_errors(APPLICATIONS["b1-docker-compose.yml"],
                                     compose_services(candidate))
            self.assertEqual(failures, ["graphql"])

    def test_pinned_application_tags_and_digests_are_rejected(self):
        expected = {"application": "example/application"}
        for image in ("example/application:v1", "example/application@sha256:" + "a" * 64):
            with self.subTest(image=image):
                self.assertEqual(policy_errors(expected, {"application": {"image": image}}),
                                 ["application"])

    def test_latest_controls_and_pinned_infrastructure_are_accepted(self):
        expected = {"application": "example/application"}
        for image in ("example/application", "example/application:latest"):
            services = {"application": {"image": image},
                        "database": {"image": "postgres:16"},
                        "attestation": {"image": "ppcelery/pccs:v2.2"}}
            with self.subTest(image=image):
                self.assertEqual(policy_errors(expected, services), [])

    def test_missing_or_wrong_application_is_rejected(self):
        expected = {"application": "example/application"}
        self.assertEqual(policy_errors(expected, {}), ["application"])
        self.assertEqual(policy_errors(expected, {"application": {"image": "other/application:latest"}}),
                         ["application"])


if __name__ == "__main__":
    unittest.main()
