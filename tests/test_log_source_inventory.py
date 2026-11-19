"""Detect Compose sources that have not been included in logging planning."""
import json
from pathlib import Path
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]


class LogInventoryTest(unittest.TestCase):
    def test_compose_services_are_in_inventory(self):
        inventory = json.loads((ROOT / 'tests/log_source_inventory.json').read_text())
        files = {p.name for p in ROOT.glob('*docker-compose.yml')}
        self.assertEqual(files, set(inventory), 'review new or removed host manifests')
        allowed = {'needs_classification', 'configured_graphql', 'proposed_ramjet', 'oneapi_route_review'}
        for name, sources in inventory.items():
            with self.subTest(manifest=name):
                services = yaml.safe_load((ROOT / name).read_text())['services']
                self.assertEqual(set(services), set(sources), 'review new or removed sources')
                self.assertTrue(set(sources.values()) <= allowed)


if __name__ == '__main__':
    unittest.main()
