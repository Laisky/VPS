#!/usr/bin/env python3
"""Check the real b1 Compose merge with temporary synthetic env_file contents.

Only `docker compose config` runs. No containers or production credentials are
used. Rendered configurations are captured, never printed or archived.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

import yaml

ROOT = Path(__file__).resolve().parent
TOKEN = 'synthetic-edge-merge-validation'
EXPECTED = {
    'OTEL_ENABLED': 'true',
    'OTEL_EXPORTER_OTLP_ENDPOINT': '100.122.41.16:14319',
    'OTEL_EXPORTER_OTLP_INSECURE': 'false',
    'OTEL_EXPORTER_OTLP_CERTIFICATE': '/run/observability/ca.crt',
    'OTEL_EXPORTER_OTLP_HEADERS': 'Authorization=Bearer%20' + TOKEN,
    'APP_LOG_SINK': 'stdout,otlp', 'TRACE_WRITE_MODE': 'batched', 'TRACE_SINK': 'db,otlp',
}


def stage_env_files(config, directory):
    """Copy the model, preserving env_file options but replacing private paths."""
    staged = copy.deepcopy(config)
    count = 0
    for service in staged['services'].values():
        if 'env_file' not in service:
            continue
        entries = service['env_file']
        if isinstance(entries, (str, dict)):
            entries = [entries]
        replacements = []
        for entry in entries:
            fixture = directory / f'fixture-{count}.env'
            fixture.write_text('# Synthetic configuration validation only.\n')
            fixture.chmod(0o600)
            count += 1
            if isinstance(entry, str):
                replacements.append(str(fixture))
            elif isinstance(entry, dict) and isinstance(entry.get('path'), str):
                replacements.append({**entry, 'path': str(fixture)})
            else:
                raise ValueError('unsupported service env_file shape')
        service['env_file'] = replacements
    return staged, count


def validate_contract(before, after, repo):
    """Reject unrelated changes, lost business state, and unsafe OTLP settings."""
    old, new = before['services'], after['services']
    if set(old) != set(new) or any(new[k] != old[k] for k in old if k != 'oneapi'):
        raise ValueError('override changed unrelated services')
    source, target = old['oneapi'], new['oneapi']
    env = target['environment']
    for key, value in EXPECTED.items():
        if env.get(key) != value:
            raise ValueError('missing or incorrect telemetry setting: ' + key)
    for key in ('SQL_DSN', 'SESSION_SECRET', 'LOG_PUSH_TOKEN', 'REDIS_CONN_STRING'):
        if not source['environment'].get(key) or env.get(key) != source['environment'][key]:
            raise ValueError('business configuration changed: ' + key)
    for key in source.keys() | target.keys():
        if key not in ('environment', 'logging', 'volumes') and source.get(key) != target.get(key):
            raise ValueError('unexpected one-api property change: ' + key)
    ca_target = EXPECTED['OTEL_EXPORTER_OTLP_CERTIFICATE']
    mounts = target.get('volumes', [])
    ca = [v for v in mounts if v.get('target') == ca_target]
    if len(ca) != 1 or not ca[0].get('read_only') or ca[0].get('source') != str(repo / 'observability/secrets/ca.crt'):
        raise ValueError('CA mount must be read-only and relative to the VPS root')
    if [v for v in mounts if v.get('target') != ca_target] != source.get('volumes', []):
        raise ValueError('existing one-api data mounts changed')
    logging = target.get('logging', {})
    if logging.get('driver') != 'json-file' or logging.get('options', {}).get('max-file') != '3' or logging.get('options', {}).get('max-size') != '100m':
        raise ValueError('local logs are not bounded as configured')


def main():
    """Resolve both real configs with fake inputs; retain only checks and hashes."""
    repo = ROOT.parent
    base, override = repo / 'b1-docker-compose.yml', ROOT / 'one-api.override.yml'
    originals = {p: p.read_bytes() for p in (base, override)}
    with tempfile.TemporaryDirectory(prefix='otlp-compose-check-') as directory:
        work = Path(directory)
        staged, count = stage_env_files(yaml.safe_load(originals[base]), work)
        staged_path = work / 'base.yml'
        staged_path.write_text(yaml.safe_dump(staged, sort_keys=False))
        envfile = work / 'interpolation.env'
        envfile.write_text(f'EDGE_TOKEN={TOKEN}\nSESSION_SECRET=synthetic-session\nSQL_DSN=synthetic-sql\nLOG_PUSH_TOKEN=synthetic-log-push\n')
        envfile.chmod(0o600)
        command = ['docker', 'compose', '--project-directory', str(repo), '--project-name', 'otlp-merge-validation', '--env-file', str(envfile), '-f', str(staged_path)]

        def render(extra):
            result = subprocess.run(command + extra + ['config', '--format', 'json'], capture_output=True, text=True, timeout=90,
                                    env={'PATH': os.environ.get('PATH', os.defpath), 'HOME': str(work)})
            if result.returncode:
                raise RuntimeError(f'Compose merge check failed with exit {result.returncode}')
            return json.loads(result.stdout)

        validate_contract(render([]), render(['-f', str(override)]), repo)
    if any(p.read_bytes() != data for p, data in originals.items()):
        raise RuntimeError('source files changed during validation')
    evidence = ROOT / 'evidence'
    evidence.mkdir(exist_ok=True)
    (evidence / 'override-validation.json').write_text(json.dumps({
        'passed': True, 'synthetic_env_files': count,
        'source_sha256': {p.name: hashlib.sha256(data).hexdigest() for p, data in originals.items()},
        'checks': ['all services retained', 'unrelated services unchanged', 'billing and Redis settings retained',
                   'TLS and authentication enforced', 'read-only CA mount', 'existing data mounts retained', 'local log rotation bounded'],
        'scope': 'Real Compose resolution with synthetic env_file contents; no production credentials or containers.'
    }, indent=2) + '\n')
    print('Compose merge contract: PASS (synthetic env files; production files unchanged)')


if __name__ == '__main__':
    main()
