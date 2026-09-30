"""Fail-closed, side-effect-free checks for the disposable observability E2E."""
import math
import re


def require_development(env):
    """Refuse destructive test actions for production or external-state settings."""
    if env.get('OBSERVABILITY_DEV_ONLY') != 'true':
        raise ValueError('E2E requires a disposable environment created with prepare.py --dev')
    if any(env.get(key) != '127.0.0.1' for key in ('EDGE_BIND', 'HOME_BIND')):
        raise ValueError('E2E requires loopback-only bindings')
    if any(env.get(key) for key in ('DOCKER_HOST', 'DOCKER_CONTEXT')):
        raise ValueError('E2E refuses explicit remote Docker overrides')
    if env.get('EDGE_STATE') or env.get('HOME_STATE'):
        raise ValueError('E2E refuses explicit state paths; use a fresh disposable checkout')


def counter_value(text, name):
    """Sum exact Prometheus counter samples; missing/invalid counters never pass."""
    pattern = re.compile(re.escape(name) + r'(?:\{[^\n]*\})?\s+(\S+)(?:\s+\d+)?')
    values = []
    for line in text.splitlines():
        match = pattern.fullmatch(line)
        if match:
            value = float(match.group(1))
            if not math.isfinite(value) or value < 0:
                raise ValueError('invalid counter: ' + name)
            values.append(value)
    if not values:
        raise ValueError('missing counter: ' + name)
    return sum(values)
