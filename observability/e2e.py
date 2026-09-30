#!/usr/bin/env python3
"""Exercise the real local edge, gateway, Victoria backends and Grafana.

Only loopback URLs are used. Run after prepare.py --dev and Compose startup.
Evidence excludes credentials, certificates, payload bodies and raw config.
"""
import base64
import gzip
import hashlib
import json
from pathlib import Path
import ssl
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import uuid

ROOT = Path(__file__).resolve().parent
ENV = dict(line.split('=', 1) for line in (ROOT / '.env').read_text().splitlines() if line and not line.startswith('#'))
TLS = ssl.create_default_context(cafile=str(ROOT / 'secrets/ca.crt'))
RESULTS = []
RUN = uuid.uuid4().hex[:12]


def http(url, payload=None, token=None, form=None, basic=False):
    """Send a bounded local request; raise HTTP errors without printing secrets."""
    if not url.startswith(('http://127.0.0.1:', 'https://127.0.0.1:')):
        raise ValueError('E2E may contact only loopback endpoints')
    headers = {}
    data = None
    if payload is not None:
        data = gzip.compress(json.dumps(payload).encode())
        headers.update({'Content-Type': 'application/json', 'Content-Encoding': 'gzip'})
    if form is not None:
        data = urlencode(form).encode()
        headers['Content-Type'] = 'application/x-www-form-urlencoded'
    if token:
        headers['Authorization'] = 'Bearer ' + token
    if basic:
        credential = ('admin:' + ENV['GRAFANA_ADMIN_PASSWORD']).encode()
        headers['Authorization'] = 'Basic ' + base64.b64encode(credential).decode()
    with urlopen(Request(url, data=data, headers=headers), context=TLS, timeout=5) as response:
        return response.read(2 << 20)


def until(check, label, seconds=100):
    """Poll eventual ingestion with a hard deadline and retain a named result."""
    start = time.monotonic()
    last = None
    while time.monotonic() - start < seconds:
        try:
            if check():
                RESULTS.append({'check': label, 'passed': True, 'seconds': round(time.monotonic() - start, 3)})
                print(label + ': PASS', flush=True)
                return
        except (HTTPError, URLError, TimeoutError, ConnectionError, ValueError, KeyError) as error:
            last = type(error).__name__
        time.sleep(0.25)
    raise AssertionError(label + ' timed out; last error class=' + str(last))


def compose(*args):
    """Run an explicit local test stack action; never use production compose files."""
    subprocess.run(['docker', 'compose', '--profile', 'edge', '--profile', 'home', *args], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)


def emit(sequence, old=False):
    """Send correlated synthetic log/span/gauge records and return their identity."""
    marker = RUN + '-' + str(sequence)
    trace_id = hashlib.sha256(marker.encode()).hexdigest()[:32]
    span_id = hashlib.sha256((marker + '-span').encode()).hexdigest()[:16]
    timestamp = time.time_ns() - (9 * 86400 if old else 60) * 10**9
    attrs = [{'key': 'service.name', 'value': {'stringValue': 'one-api'}},
             {'key': 'host.name', 'value': {'stringValue': 'b1'}},
             {'key': 'deployment.environment.name', 'value': {'stringValue': 'test'}}]
    resource = {'attributes': attrs}
    records = {
        'logs': {'resourceLogs': [{'resource': resource, 'scopeLogs': [{'logRecords': [{
            'timeUnixNano': str(timestamp), 'severityNumber': 9, 'severityText': 'INFO',
            'body': {'stringValue': marker}, 'traceId': trace_id, 'spanId': span_id}]}]}]},
        'traces': {'resourceSpans': [{'resource': resource, 'scopeSpans': [{'spans': [{
            'traceId': trace_id, 'spanId': span_id, 'name': 'one-api.canary', 'kind': 2,
            'startTimeUnixNano': str(timestamp), 'endTimeUnixNano': str(timestamp + 1000000)}]}]}]},
        'metrics': {'resourceMetrics': [{'resource': resource, 'scopeMetrics': [{'metrics': [{
            'name': 'edge_canary', 'gauge': {'dataPoints': [{'timeUnixNano': str(timestamp), 'asDouble': float(sequence),
                'attributes': [{'key': 'canary_id', 'value': {'stringValue': marker}}]}]}}]}]}]},
    }
    for signal, payload in records.items():
        response = http('https://127.0.0.1:14319/v1/' + signal, payload, ENV['EDGE_TOKEN'])
        decoded = json.loads(response or b'{}')
        if decoded.get('partialSuccess'):
            raise AssertionError('unexpected partial acceptance')
    return marker, trace_id


def query_logs(marker, interval='10m'):
    """Read stored log rows from VictoriaLogs rather than collector counters."""
    query = f'_time:{interval} AND _msg:="{marker}"'
    data = http('http://127.0.0.1:19428/select/logsql/query?' + urlencode({'query': query, 'limit': '10'}))
    return [json.loads(line) for line in data.splitlines() if line]


def stored(marker, trace_id):
    """Require linked logs, actual Jaeger spans and the exact numeric metric."""
    logs = query_logs(marker)
    traces = json.loads(http('http://127.0.0.1:20428/select/jaeger/api/traces/' + trace_id))
    metrics = json.loads(http('http://127.0.0.1:18428/api/v1/query?' + urlencode({'query': 'edge_canary{canary_id="' + marker + '"}'})))
    return bool(logs and any(row.get('trace_id') == trace_id for row in logs)
                and traces.get('data') and traces['data'][0].get('spans')
                and any(float(row['value'][1]) == float(marker.rsplit('-', 1)[1])
                        for row in metrics.get('data', {}).get('result', [])))


def reclaimed():
    """Read post-checkpoint edge receipt collection, not merely socket writes."""
    return json.loads(http('http://127.0.0.1:18088/monitor'))['otlpStorage']['acceptedReceiptsReclaimed']


def main():
    """Run positive, outage/restart, ownership-transfer and access controls."""
    evidence = ROOT / 'evidence'
    evidence.mkdir(exist_ok=True)
    passed = False
    try:
        until(lambda: json.loads(http('http://127.0.0.1:23000/api/health'))['database'] == 'ok', 'Grafana startup', 180)
        until(lambda: bool(http('http://127.0.0.1:18088/health')), 'Edge startup')
        for port, token in ((14319, ENV['EDGE_TOKEN']), (14318, ENV['HOME_TOKEN'])):
            for candidate in (None, token + '-invalid'):
                try:
                    http(f'https://127.0.0.1:{port}/v1/logs', {'resourceLogs': []}, candidate)
                    raise AssertionError('unauthenticated admission succeeded')
                except HTTPError as error:
                    assert error.code in (401, 403), error.code
        RESULTS.append({'check': 'Both receivers reject absent/wrong bearer tokens', 'passed': True})
        first = emit(1)
        until(lambda: stored(*first), 'All three signals stored and trace-correlated')
        until(lambda: reclaimed() >= 3, 'First durable receipt checkpoint')
        compose('stop', 'gateway')
        outage = emit(2)
        compose('kill', '-s', 'SIGKILL', 'edge')
        compose('up', '-d', 'edge')
        until(lambda: bool(http('http://127.0.0.1:18088/health')), 'Edge recovers during home outage')
        compose('up', '-d', 'gateway')
        until(lambda: stored(*outage), 'Post-ACK edge SIGKILL replay reaches all backends')
        until(lambda: reclaimed() >= 3, 'Replayed records checkpointed')
        compose('stop', 'victoria-logs', 'victoria-traces', 'victoria-metrics')
        before = reclaimed()
        queued = emit(3)
        until(lambda: reclaimed() >= before + 3, 'Home durably takes ownership while backends are down')
        compose('kill', '-s', 'SIGKILL', 'gateway')
        compose('up', '-d', 'gateway', 'victoria-logs', 'victoria-traces', 'victoria-metrics')
        until(lambda: stored(*queued), 'Gateway fsynced queue survives SIGKILL without edge resend')
        before_old = reclaimed()
        old_marker, old_trace = emit(4, old=True)
        until(lambda: reclaimed() >= before_old + 3, 'Out-of-retention envelopes processed')
        assert not query_logs(old_marker, '30d'), 'old log was queryable despite retention'
        try:
            old_result = json.loads(http('http://127.0.0.1:20428/select/jaeger/api/traces/' + old_trace))
        except HTTPError as error:
            if error.code != 404:
                raise
            old_result = {}  # Jaeger trace-by-ID returns 404 for an absent trace.
        assert not old_result.get('data'), 'old trace was queryable despite retention'
        RESULTS.append({'check': 'Nine-day-old logs and traces absent from seven-day stores', 'passed': True})
        for uid in ('obs-metrics', 'obs-logs', 'obs-traces'):
            until(lambda uid=uid: json.loads(http('http://127.0.0.1:23000/api/datasources/uid/' + uid + '/health', basic=True)).get('status') == 'OK', 'Grafana datasource ' + uid)
        dashboard = json.loads(http('http://127.0.0.1:23000/api/dashboards/uid/obs-pipeline', basic=True))
        assert dashboard['dashboard']['uid'] == 'obs-pipeline'
        RESULTS.append({'check': 'Provisioned dashboard available', 'passed': True})
        passed = True
    finally:
        (evidence / 'summary.json').write_text(json.dumps({'passed': passed, 'checks': RESULTS, 'limits': ['Synthetic isolated workload; not b1/home capacity certification', 'No physical power-loss test', 'Physical TTL cleanup may lag query retention']}, indent=2) + '\n')


if __name__ == '__main__':
    main()
