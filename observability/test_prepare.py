"""Regression tests for deployment input validation and generated queue policy."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import prepare


class PrepareTests(unittest.TestCase):
    def test_rejects_unsafe_origins(self):
        for value in ('http://home:4318', 'https://user:secret@home', 'https://home/v1', 'https://home?token=secret', 'https://home#fragment', 'https://home:99999'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                prepare.validate_home_url(value)

    def test_generates_three_signals_and_separate_state(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(prepare, 'ROOT', Path(directory)):
            prepare.render('https://home:14318/')
            cfg = json.loads((Path(directory) / 'generated/edge.json').read_text())['settings']
            otlp = cfg['otlp']
            self.assertTrue(otlp['receipt_gc'])
            self.assertGreater(otlp['max_storage_bytes'], otlp['max_wal_bytes'])
            self.assertNotEqual(otlp['storage_dir'], cfg['journal']['buf_dir_path'])
            for signal in ('logs', 'traces', 'metrics'):
                self.assertEqual(otlp['destinations'][0][signal + '_endpoint'], 'https://home:14318/v1/' + signal)
            self.assertNotIn('replace-with', json.dumps(cfg))

    def test_dev_never_overwrites_existing_secrets(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(prepare, 'ROOT', Path(directory)):
            (Path(directory) / '.env').write_text('protected')
            with self.assertRaises(ValueError):
                prepare.development('example:test')
            self.assertEqual((Path(directory) / '.env').read_text(), 'protected')


if __name__ == '__main__':
    unittest.main()
