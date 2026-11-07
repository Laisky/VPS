"""Render b1 with synthetic env files and verify the application OTLP contract."""
import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
ENV_PATHS = (
    '/opt/configs/tinyproxy/auth.env',
    '/opt/configs/env/b1/broadcastchannel.env',
    '/opt/configs/env/b1/postgre.env',
)
OTLP_ENV = {
    'APP_LOG_OTLP_ENDPOINT': 'https://b1.snake-carp.ts.net:14319',
    'APP_LOG_OTLP_TOKEN_FILE': '/run/observability/edge-token',
    'APP_LOG_OTLP_CA_FILE': '/run/observability/ca.crt',
    'APP_LOG_OTLP_HOST': 'b1', 'APP_LOG_OTLP_ENV': 'production',
}
MOUNTS = {
    '/run/observability/edge-token': '/opt/configs/observability/secrets/app-otlp-token',
    '/run/observability/ca.crt': '/opt/configs/observability/secrets/ca.crt',
}


class B1ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = (ROOT / 'b1-docker-compose.yml').read_text()
        cls.spec = yaml.safe_load(cls.raw)
        cls.temp = tempfile.TemporaryDirectory(prefix='b1-synthetic-')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.path = Path(cls.temp.name)
        cls.current = cls.render(cls.raw, 'current')
        base = os.environ.get('B1_BASE_REF')
        cls.base = None
        if base:
            source = subprocess.check_output(
                ['git', 'show', f'{base}:b1-docker-compose.yml'], cwd=ROOT, text=True)
            cls.base = cls.render(source, 'base')

    @classmethod
    def render(cls, source, name):
        # Reject unknown env files or includes before Compose can read the host.
        model = yaml.safe_load(source)
        if model.get('include'):
            raise AssertionError('unexpected Compose include')
        paths = [p for service in model['services'].values()
                 for p in service.get('env_file', [])]
        if sorted(paths) != sorted(ENV_PATHS):
            raise AssertionError('unexpected env_file references')
        # Replace only the three external env_file paths, with empty synthetic files.
        for i, external in enumerate(ENV_PATHS):
            if source.count(external) != 1:
                raise AssertionError(f'expected one env_file reference: {external}')
            fixture = cls.path / f'{i}.env'
            fixture.write_text('# synthetic fixture; no production values\n')
            source = source.replace(external, str(fixture))
        compose = cls.path / f'{name}.yml'
        compose.write_text(source)
        env = {'PATH': os.environ['PATH'], 'HOME': str(cls.path),
               'COMPOSE_DISABLE_ENV_FILE': '1', 'SESSION_SECRET': 'synthetic-session',
               'SQL_DSN': 'synthetic-dsn', 'LOG_PUSH_TOKEN': 'synthetic-token'}
        result = subprocess.run(['docker', 'compose', '-p', 'b1-contract', '-f',
                                 str(compose), 'config', '--format', 'json'],
                                env=env, text=True, capture_output=True, timeout=60, check=True)
        return json.loads(result.stdout)

    def test_both_services_keep_required_mounts_and_grace(self):
        for name in ('graphql', 'go-ramjet'):
            with self.subTest(service=name):
                raw = self.spec['services'][name]
                rendered = self.current['services'][name]
                self.assertEqual(rendered['stop_grace_period'], '30s')
                self.assertEqual({k: rendered['environment'][k] for k in OTLP_ENV}, OTLP_ENV)
                for target, source in MOUNTS.items():
                    mount = next(m for m in raw['volumes'] if isinstance(m, dict) and m.get('target') == target)
                    self.assertEqual(mount['source'], source)
                    self.assertIs(mount['read_only'], True)
                    self.assertIs(mount['bind']['create_host_path'], False)
                    parsed = next(m for m in rendered['volumes'] if m.get('target') == target)
                    self.assertEqual(parsed['source'], source)
                    self.assertIs(parsed['read_only'], True)

    def test_only_intended_ramjet_change_relative_to_base(self):
        if self.base is None:
            self.skipTest('B1_BASE_REF is required for comparison')
        current = copy.deepcopy(self.current)
        base = copy.deepcopy(self.base)
        service = current['services']['go-ramjet']
        self.assertEqual(service.pop('stop_grace_period'), '30s')
        for key, value in OTLP_ENV.items():
            self.assertEqual(service['environment'].pop(key), value)
        self.assertEqual(service.pop('extra_hosts'), ['b1.snake-carp.ts.net=100.122.41.16'])
        service['volumes'] = [m for m in service['volumes'] if m.get('target') not in MOUNTS]
        self.assertEqual(current, base)


if __name__ == '__main__':
    unittest.main()
