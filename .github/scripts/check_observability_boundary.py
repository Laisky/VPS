#!/usr/bin/env python3
"""Keep observability runtime configuration out of the public VPS repository."""
from pathlib import Path
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[2]
ENTRY = {'name': 'observability', 'include': [{
    'path': '/opt/configs/observability/compose.yml',
    'project_directory': '/opt/configs/observability',
    'env_file': '/opt/configs/observability/.env',
}]}
ALLOWED = {'compose.yml', 'README.md'}
HOME_INCLUDE = [{
    'path': '/opt/configs/observability/home.compose.yml',
    'project_directory': '/opt/configs/observability',
    'env_file': '/opt/configs/observability/.env',
}]


def validate_home(root):
    # Retained settings remain private; legacy home services remain distinct.
    home = yaml.safe_load((root / 'home-docker-compose.yml').read_text())
    if home.get('include') != HOME_INCLUDE:
        raise ValueError('home requires the exact private observability include')
    if any(name.startswith('observability-') for name in home.get('services', {})):
        raise ValueError('retained runtime service settings belong in private configs')



def validate(root):
    """Require a path-only entrypoint, with no duplicate configuration or fallback."""
    directory = root / 'observability'
    actual = {str(p.relative_to(directory)) for p in directory.rglob('*') if p.is_file()}
    if actual != ALLOWED:
        raise ValueError('observability may contain only the entrypoint and documentation')
    if yaml.safe_load((directory / 'compose.yml').read_text()) != ENTRY:
        raise ValueError('runtime settings belong in /opt/configs, not in VPS')


class BoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'observability').mkdir()
        (self.root / 'observability/README.md').write_text('Deployment entrypoint\n')
        (self.root / 'observability/compose.yml').write_text(yaml.safe_dump(ENTRY))

    def test_home_private_include_is_required_and_path_only(self):
        path = self.root / 'home-docker-compose.yml'
        model = {'include': HOME_INCLUDE, 'services': {'legacy': {'image': 'synthetic:latest'}}}
        path.write_text(yaml.safe_dump(model))
        validate_home(self.root)
        for changed in [
            {'services': model['services']},
            {'include': [{'path': './fallback.yml'}], 'services': model['services']},
            {'include': HOME_INCLUDE, 'services': {'observability-gateway': {'image': 'forbidden'}}},
        ]:
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                path.write_text(yaml.safe_dump(changed))
                validate_home(self.root)

    def test_path_only_entrypoint(self):
        validate(self.root)

    def test_inline_settings_are_rejected(self):
        path = self.root / 'observability/compose.yml'
        model = yaml.safe_load(path.read_text())
        model['services'] = {'edge': {'environment': {'RUNTIME_CONFIG': 'forbidden'}}}
        path.write_text(yaml.safe_dump(model))
        with self.assertRaises(ValueError):
            validate(self.root)

    def test_alternative_config_root_is_rejected(self):
        path = self.root / 'observability/compose.yml'
        path.write_text(path.read_text().replace('/opt/configs', './configs'))
        with self.assertRaises(ValueError):
            validate(self.root)

    def test_duplicate_runtime_files_are_rejected(self):
        for name in ('gateway.yaml', '.env.example', 'prepare.py', 'grafana/dashboard.json'):
            with self.subTest(name=name):
                path = self.root / 'observability' / name
                path.parent.mkdir(exist_ok=True)
                path.write_text('duplicate')
                with self.assertRaises(ValueError):
                    validate(self.root)
                path.unlink()


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(BoundaryTests))
    if not result.wasSuccessful():
        raise SystemExit(1)
    validate(ROOT)
    validate_home(ROOT)
    print('Observability repository boundary: PASS')
