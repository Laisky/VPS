"""Negative controls for the Compose merge oracle and env-file isolation."""
import copy
from pathlib import Path
import tempfile
import unittest
import check_override as check


class OverrideTests(unittest.TestCase):
    def setUp(self):
        self.repo = Path('/test-vps')
        service = {'image': 'one-api:fixed', 'ports': [{'target': 3000}],
                   'environment': {key: 'synthetic-' + key for key in ('SQL_DSN', 'SESSION_SECRET', 'LOG_PUSH_TOKEN', 'REDIS_CONN_STRING')},
                   'volumes': [{'target': '/data', 'source': '/var/lib/oneapi', 'type': 'bind'}],
                   'logging': {'driver': 'json-file', 'options': {'max-size': '100m'}}}
        self.before = {'services': {'oneapi': service, 'unrelated': {'image': 'untouched:1'}}}
        self.after = copy.deepcopy(self.before)
        target = self.after['services']['oneapi']
        target['environment'].update(check.EXPECTED)
        target['volumes'].append({'target': check.EXPECTED['OTEL_EXPORTER_OTLP_CERTIFICATE'],
                                  'source': str(self.repo / 'observability/secrets/ca.crt'), 'read_only': True, 'type': 'bind'})
        target['logging']['options']['max-file'] = '3'

    def test_valid_contract(self):
        check.validate_contract(self.before, self.after, self.repo)

    def test_unsafe_telemetry_or_business_mutation_fails(self):
        for key in list(check.EXPECTED) + ['SQL_DSN', 'SESSION_SECRET', 'LOG_PUSH_TOKEN', 'REDIS_CONN_STRING']:
            with self.subTest(key=key):
                mutated = copy.deepcopy(self.after)
                mutated['services']['oneapi']['environment'].pop(key)
                with self.assertRaises(ValueError):
                    check.validate_contract(self.before, mutated, self.repo)

    def test_unrelated_service_data_and_ca_changes_fail(self):
        def unrelated(model):
            model['services']['unrelated']['image'] = 'changed:2'
        def data(model):
            model['services']['oneapi']['volumes'][0]['source'] = '/wrong-data'
        def ca(model):
            model['services']['oneapi']['volumes'][1]['read_only'] = False
        def rotation(model):
            model['services']['oneapi']['logging']['options'].pop('max-file')
        for change in (unrelated, data, ca, rotation):
            with self.subTest(change=change.__name__):
                mutated = copy.deepcopy(self.after)
                change(mutated)
                with self.assertRaises(ValueError):
                    check.validate_contract(self.before, mutated, self.repo)

    def test_staging_preserves_source_and_long_syntax_without_reading_private_files(self):
        original = {'services': {'a': {'env_file': '/missing/private.env'},
                                 'b': {'env_file': ['/also-missing.env', {'path': '/secret.env', 'required': True, 'format': 'raw'}]},
                                 'c': {'image': 'untouched:1'}}}
        snapshot = copy.deepcopy(original)
        with tempfile.TemporaryDirectory() as directory:
            staged, count = check.stage_env_files(original, Path(directory))
            self.assertEqual(count, 3)
            self.assertEqual(original, snapshot)
            self.assertEqual(staged['services']['c'], original['services']['c'])
            for name in ('a', 'b'):
                for entry in staged['services'][name]['env_file']:
                    path = Path(entry['path'] if isinstance(entry, dict) else entry)
                    self.assertEqual(path.parent, Path(directory))
                    self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(staged['services']['b']['env_file'][1]['format'], 'raw')
            self.assertTrue(staged['services']['b']['env_file'][1]['required'])


if __name__ == '__main__':
    unittest.main()
