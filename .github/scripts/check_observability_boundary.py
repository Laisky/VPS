#!/usr/bin/env python3
"""Keep Compose in VPS and credential/configuration payloads outside it."""

from pathlib import Path
import re
import shutil
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[2]
PRIVATE = "/opt/configs/observability"
COMPOSE_FILES = {
    "compose.yml",
    "services.compose.yml",
    "home.compose.yml",
    "attended.override.yml",
    "capacity.override.yml",
    "e2e.override.yml",
    "images.amd64.override.yml",
    "one-api.image.yml",
    "one-api.override.yml",
    "production.override.yml",
    "tailnet.override.yml",
}
ENTRY = {
    "name": "observability",
    "include": [
        {
            "path": "./services.compose.yml",
            "project_directory": PRIVATE,
            "env_file": PRIVATE + "/.env",
        }
    ],
}
HOME_INCLUDE = [
    {
        "path": "./observability/home.compose.yml",
        "project_directory": PRIVATE,
        "env_file": PRIVATE + "/.env",
    }
]


class ComposeLoader(yaml.SafeLoader):
    pass


def compose_tag(loader, tag, node):
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    if isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node)
    return loader.construct_scalar(node)


ComposeLoader.add_multi_constructor("!", compose_tag)


def require(value, message):
    if not value:
        raise ValueError(message)


def private_payloads(value):
    """Reject literal credentials without echoing their values in diagnostics."""
    if isinstance(value, dict):
        env = value.get("environment", {})
        if isinstance(env, list):
            env = dict(item.split("=", 1) for item in env if "=" in item)
        if isinstance(env, dict):
            reference = r"\$\{[A-Z_][A-Z0-9_]*(?::\?[^}]+)?\}"
            for key, item in env.items():
                if any(word in key.upper() for word in ("TOKEN", "PASSWORD", "SECRET")):
                    require(
                        isinstance(item, str) and re.fullmatch(reference, item),
                        "credential fields must contain only required variable references",
                    )
                if key == "OTEL_EXPORTER_OTLP_HEADERS":
                    require(
                        isinstance(item, str)
                        and re.fullmatch("Authorization=Bearer%20" + reference, item),
                        "literal authorization forbidden",
                    )
        for item in value.values():
            private_payloads(item)
    elif isinstance(value, list):
        for item in value:
            private_payloads(item)
    elif isinstance(value, str):
        require(
            not re.search(r"://[^/\s:@]+:[^/\s@]+@", value), "URL credential forbidden"
        )
        require(
            not re.search(r"-----BEGIN|\$2[aby]\$", value),
            "credential payload forbidden",
        )


def validate_home(root):
    home = yaml.safe_load((root / "home-docker-compose.yml").read_text())
    require(
        home.get("include") == HOME_INCLUDE,
        "home must include its VPS module with private env input",
    )
    require(
        not any(name.startswith("observability-") for name in home.get("services", {})),
        "canonical home services must have one definition",
    )


def validate(root):
    directory = root / "observability"
    actual = {
        str(p.relative_to(directory)) for p in directory.rglob("*") if p.is_file()
    }
    require(
        actual == COMPOSE_FILES | {"README.md"},
        "only reviewed Compose source and documentation belong here",
    )
    require(
        yaml.safe_load((directory / "compose.yml").read_text()) == ENTRY,
        "canonical entrypoint or private interpolation reference changed",
    )
    for name in COMPOSE_FILES:
        private_payloads(
            yaml.load((directory / name).read_text(), Loader=ComposeLoader)
        )
    shared = yaml.safe_load((directory / "services.compose.yml").read_text())
    require(
        set(shared["services"])
        == {
            "edge",
            "gateway",
            "victoria-metrics",
            "victoria-logs",
            "victoria-traces",
            "grafana",
        },
        "shared service definitions changed",
    )
    home = yaml.safe_load((directory / "home.compose.yml").read_text())
    require(
        set(home["services"])
        == {
            "observability-" + name
            for name in (
                "gateway",
                "victoria-metrics",
                "victoria-logs",
                "victoria-traces",
                "grafana",
            )
        },
        "canonical home definitions changed",
    )


class BoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copytree(ROOT / "observability", self.root / "observability")
        (self.root / "home-docker-compose.yml").write_text(
            yaml.safe_dump({"include": HOME_INCLUDE, "services": {}})
        )

    def test_reviewed_source_and_private_references_pass(self):
        validate(self.root)
        validate_home(self.root)

    def test_old_private_compose_dependency_is_rejected(self):
        p = self.root / "observability/compose.yml"
        p.write_text(
            p.read_text().replace("./services.compose.yml", PRIVATE + "/compose.yml")
        )
        with self.assertRaisesRegex(ValueError, "entrypoint"):
            validate(self.root)

    def test_wrong_home_include_is_rejected(self):
        p = self.root / "home-docker-compose.yml"
        p.write_text(
            p.read_text().replace(
                "./observability/home.compose.yml", PRIVATE + "/home.compose.yml"
            )
        )
        with self.assertRaisesRegex(ValueError, "VPS module"):
            validate_home(self.root)

    def test_private_env_reference_cannot_move(self):
        p = self.root / "observability/compose.yml"
        p.write_text(p.read_text().replace(PRIVATE + "/.env", "./.env"))
        with self.assertRaises(ValueError):
            validate(self.root)

    def test_literal_credential_is_rejected_without_value_disclosure(self):
        p = self.root / "observability/home.compose.yml"
        model = yaml.safe_load(p.read_text())
        model["services"]["observability-gateway"]["environment"][
            "HOME_TOKEN"
        ] = "synthetic-forbidden-value"
        p.write_text(yaml.safe_dump(model))
        with self.assertRaisesRegex(ValueError, "variable references") as error:
            validate(self.root)
        self.assertNotIn("synthetic-forbidden-value", str(error.exception))

    def test_duplicate_inline_home_role_is_rejected(self):
        p = self.root / "home-docker-compose.yml"
        p.write_text(
            yaml.safe_dump(
                {"include": HOME_INCLUDE, "services": {"observability-gateway": {}}}
            )
        )
        with self.assertRaisesRegex(ValueError, "one definition"):
            validate_home(self.root)

    def test_runtime_payloads_and_unknown_files_are_rejected(self):
        for name in (".env", "gateway.yaml", "secrets/token", "extra.compose.yml"):
            p = self.root / "observability" / name
            p.parent.mkdir(exist_ok=True)
            p.write_text("synthetic forbidden payload")
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate(self.root)
            p.unlink()

    def test_private_url_and_header_literals_are_rejected(self):
        for model in (
            {"url": "https://user:synthetic@host"},
            {
                "environment": {
                    "OTEL_EXPORTER_OTLP_HEADERS": "Authorization=Bearer%20synthetic"
                }
            },
        ):
            with self.subTest(model_keys=list(model)), self.assertRaises(ValueError):
                private_payloads(model)


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(BoundaryTests)
    )
    if not result.wasSuccessful():
        raise SystemExit(1)
    validate(ROOT)
    validate_home(ROOT)
    print("Observability repository boundary: PASS")
