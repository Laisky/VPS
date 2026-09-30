"""Negative controls prevent false retention passes and production fault tests."""
import unittest
from e2e_checks import counter_value, require_development


class E2EChecks(unittest.TestCase):
    def test_exact_counter_with_labels(self):
        text = '# TYPE vl_rows_dropped_total counter\nvl_rows_dropped_total{reason="too_old"} 2\nvl_rows_dropped_total{reason="future"} 0\nother_vl_rows_dropped_total 100\n'
        self.assertEqual(counter_value(text, 'vl_rows_dropped_total'), 2)
        self.assertEqual(counter_value('vt_rows_dropped_total 0\n', 'vt_rows_dropped_total'), 0)

    def test_missing_or_other_metric_never_counts_as_a_drop(self):
        for text in ('', '# HELP vl_rows_dropped_total test', 'vl_rows_dropped_total_wrong 9', 'unrelated 10'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                counter_value(text, 'vl_rows_dropped_total')

    def test_invalid_counter_never_passes(self):
        for value in ('NaN', '+Inf', '-1', 'invalid'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                counter_value('vt_rows_dropped_total ' + value, 'vt_rows_dropped_total')

    def test_development_guard(self):
        dev = {'OBSERVABILITY_DEV_ONLY': 'true', 'EDGE_BIND': '127.0.0.1', 'HOME_BIND': '127.0.0.1'}
        require_development(dev)
        for key, value in (('OBSERVABILITY_DEV_ONLY', ''), ('EDGE_BIND', '0.0.0.0'), ('HOME_BIND', '100.64.0.1'),
                           ('EDGE_STATE', '/production'), ('HOME_STATE', './existing'), ('DOCKER_HOST', 'tcp://remote'), ('DOCKER_CONTEXT', 'production')):
            with self.subTest(key=key), self.assertRaises(ValueError):
                require_development({**dev, key: value})


if __name__ == '__main__':
    unittest.main()
