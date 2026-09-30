# b1 edge / home observability

This is an **opt-in shadow deployment**. It does not modify the existing b1/home
Compose services, databases, Grafana instance, public gateway, billing ledger or
production traffic. Start it only after checking spare resources on each host.

```text
one-api on b1 -- OTLP/HTTP protobuf + gzip --> go-fluentd on b1
              TLS + bearer                   synchronized journal + safe receipt GC
                                                    |
                                              Tailscale + TLS + bearer
                                                    |
home: Collector (persistent per-signal exporter queues)
      logs -> VictoriaLogs, traces -> VictoriaTraces, metrics -> VictoriaMetrics
      Grafana -> all three stores; raw telemetry retention explicitly seven days
```

## Files and dependencies

`compose.yml` provides `edge` and `home` profiles. `gateway.yaml` uses a synchronous
pipeline before persistent exporter queues; there is intentionally no in-memory
batch processor before durable acceptance. Batching happens inside each exporter
queue. Exact OTLP signal URLs avoid sending metrics to a log endpoint.

Build the reviewed go-fluentd source from
[Laisky/go-fluentd PR 20](https://github.com/Laisky/go-fluentd/pull/20). The CI
workflow pins the tested source SHA and records the resulting image. Do not
assume a previously published `latest` image understands `receipt_gc` or
`max_storage_bytes`. The companion one-api branch
`feat/secure-otlp-edge-20260930` adds safe resource detection and verifies the
production SDK's three TLS/protobuf/gzip exporters.

All third-party services have explicit version tags, not `latest`. Before
production, record registry digests and pin the verified images by digest in a
local deployment override. The pipeline is tested against the versions in this
file, not every future tag. Grafana's VictoriaLogs plugin is also pinned.

## Disposable local validation

Requirements: Docker Engine with Compose, Python 3, OpenSSL, and network access to
fetch the pinned source and images. Use a new checkout with no existing `.env`,
`secrets` or `state`. The script refuses to overwrite credentials.

```sh
# In a checkout of the reviewed go-fluentd commit:
docker build -f .docker/Dockerfile -t go-fluentd:observability-test .

# In VPS/observability:
python3 -m unittest -v test_prepare.py
python3 prepare.py --dev --home-url=https://gateway:4318
docker compose --profile edge --profile home config --quiet
docker compose --profile home run --rm --no-deps gateway validate --config=/etc/otelcol/config.yaml
docker compose --profile edge --profile home up -d
python3 e2e.py
docker compose --profile edge --profile home down
```

The development CA/certificates expire after seven days and are for loopback
validation only. Credentials are random, local, ignored by Git and never printed.
The CA private key is removed after signing the two disposable server identities.
The E2E deliberately stops and kills these local test containers; **never point
this test at production**. It uses only loopback URLs and this Compose project.

The acceptance test checks authenticated admission, nonempty logs/spans/metrics
in the real databases, matching log/trace IDs, metric values, edge SIGKILL after
local acceptance, gateway SIGKILL after durable handoff with all stores stopped,
old telemetry, Grafana datasource health and the provisioned dashboard. CI keeps
source SHAs, image identities, named checks and synthetic container logs as a
seven-day artifact. It does not certify physical power loss, WAN capacity,
24-hour outage survival, browser interactions or one-api business request load.

## Production provisioning: do not use --dev

On each host, use a reviewed checkout and a private `.env` based on `.env.example`
(mode 0600). Fill every placeholder through your secret manager. Do not run
`docker compose config` without `--quiet` in shared logs: expanded configuration
contains credentials. Tokens must be distinct random hexadecimal strings.

Provision only the necessary identities on each host. b1 needs `edge.crt`,
`edge.key` and `ca.crt`; home needs `home.crt`, `home.key` and `ca.crt`. The edge
certificate SAN must include the exact b1 address used by one-api (the supplied
override uses `100.122.41.16`); home's certificate must include `100.69.166.78` or
its selected DNS name. Keys belong to the configured runtime UID with mode 0600.
Do not copy the CA signing key to either container. Use a proper renewal process.

Provision **dedicated, quota-controlled storage** owned by `OBS_UID:OBS_GID`.
The renderer creates local test directories only; it does not create the absolute
`EDGE_STATE` / `HOME_STATE` paths in the production example. For the example UID
1000 and paths, run the relevant command on each host after mounting its disk:

```sh
# b1 only
sudo install -d -o 1000 -g 1000 -m 0700 /var/lib/observability/edge/{otlp,legacy}
# home only
sudo install -d -o 1000 -g 1000 -m 0700 /var/lib/observability/home/{collector,metrics,logs,traces,grafana}
```

Do not place the edge journal on an unbounded shared OS/one-api filesystem.
The initial logical WAL limit is 1 GiB and whole-root admission threshold is
2 GiB. These are safety starting points, **not** a hard disk quota or a promised
outage duration. Replay, per-destination receipts, quarantines, recovery copies,
filesystem overhead and Collector compaction require additional headroom.
Measure actual bytes/second and use `outage_seconds * bytes_per_second` plus
headroom to size storage. File-count-based accounting also has a CPU/I/O cost.

The home profile's configured memory ceilings total about 4.25 GiB, in addition
to the host and existing services. They are ceilings, not measured working sets.
Keep explicit disk and memory headroom while the old and shadow stacks coexist.

## Start home, then b1, then explicitly switch one-api

On home, allow ingress to TCP 14318 only from the designated b1 machine. Allow
Grafana TCP 23000 only from administrator devices. Query and management ports are
bound to loopback; use SSH forwarding for those. Tailscale membership alone is
not authorization to query all telemetry. The databases have no public ingress.
Grafana is an administrator tool, not a multi-tenant one-api customer portal.

```sh
# home, in VPS/observability; .env and TLS files already provisioned:
docker compose --profile home config --quiet
docker compose --profile home run --rm --no-deps gateway validate --config=/etc/otelcol/config.yaml
docker compose --profile home up -d

# b1, in VPS/observability; use home's real TLS origin:
python3 prepare.py --home-url=https://100.69.166.78:14318
docker compose --profile edge config --quiet
docker compose --profile edge up -d
```

Compose parses variables in the complete file, including inactive profiles;
provide the required `.env` keys on each host, but do not distribute a home
Grafana password to b1 unnecessarily: inactive-profile-only values may be unique
unused placeholders on that host. b1 and home share only the actual HOME_TOKEN.

After independent synthetic admission/query checks, merge the one-api override
explicitly, from the VPS repository root, through the **same secret injection
used by your existing one-api deployment**:

```sh
# SQL_DSN, SESSION_SECRET and existing variables must remain injected as before.
# EDGE_TOKEN is read from observability/.env; do not lose existing secrets.
docker compose --env-file observability/.env -f b1-docker-compose.yml \
  -f observability/one-api.override.yml config --quiet
docker compose --env-file observability/.env -f b1-docker-compose.yml \
  -f observability/one-api.override.yml up -d --no-deps oneapi
```

`OTEL_EXPORTER_OTLP_INSECURE=false` is required; an `https://` prefix alone is not
sufficient in one-api. Header spaces use `%20`. The CA mount is mandatory.
`stdout,otlp` retains local logs; set a Docker max-file limit as well as max-size.
`db,otlp` retains diagnostic SQL traces during comparison, but batched traces
become visible after completion rather than during a streaming request. This
never moves billing/quota consistency onto the telemetry pipeline.

Audit payload capture before the switch: API keys, cookies, full prompts and
responses must be excluded **before** the edge writes its WAL. The one-api
resource fix removes automatic process argv/owner collection, not every possible
application payload. The legacy go-fluentd filters do not process OTLP records.

## Querying and operational checks

Open Grafana on home's private address, port 23000, and use the provisioned
`Observability / one-api / Telemetry pipeline` dashboard. Explore has Metrics,
Logs and Traces data sources. Logs use `service.name`, `host.name` and the
canonical environment as stream fields, not request/user IDs. Expand a log's
native `trace_id` to open the Jaeger-backed trace view. Trace-to-log links are
provisioned. Metric exemplars remain disabled in one-api; no exemplar navigation
is claimed. The default dashboard is pipeline health, not a billing/cost report.

Check the edge's loopback `/monitor` at port 18088, especially
`otlpStorage.admissionRejected`, `otlpStorage.acceptedReceiptsReclaimed` and the
existing `otlp` destination outcomes. These counters reset on process restart.
A responding `/health` is not proof that downstream data is current. Check
Collector queue size/capacity/failures and actual newest event timestamps.

Before unattended operation, connect your existing b1/external alert channel to
home reachability, source/drop errors, queue occupancy, oldest backlog and disk
free space. Do not rely on Grafana on home to alert when home is powered off.
This PR does not invent credentials or a notification destination, and does not
silently subscribe anyone to an alert service. A useful initial alert threshold
is 80% of an established queue/disk budget; tune it using measured growth rate.

## Retention, failure semantics and rollback

All three stores explicitly receive `-retentionPeriod=7d`. This is event-time
telemetry retention, not immediate physical erasure at exactly 168 hours.
Partition cleanup/merging may lag; backups, temporary recovery data and edge
quarantines need separate lifecycle policies. Replaying an old event does not
change its event timestamp. SQL usage/billing retention is unchanged.

The edge ACK means synchronized local acceptance. A gateway ACK hands ownership
to its persistent exporter queue; it is not the database's final storage receipt.
The E2E tests this handoff by waiting for edge receipt GC before killing home.
Backend acknowledgements still carry their own durability windows. No single
copy survives disk loss; telemetry remains best-effort before edge acceptance,
and ambiguous acknowledgements can duplicate exports. This is not exactly-once.

Receipt GC checkpoints completed prefixes before deleting accepted receipts.
Unresolved gaps and quarantines are preserved, not blindly aged out. Enabling it
upgrades go-fluentd generation metadata to v2, which older binaries reject.
**Do not edit/delete that metadata to roll back**, and never restore WAL without
its matching generation/receipt state. Preserve complete owned directories.

Rollback the application by restoring its previous deployment command and OTLP
endpoint, then deliberately restarting only one-api. Keep pending edge/home
state for recovery; do not remove volumes or run prune commands. Stop the shadow
stack only after accounting for pending data. Retire old observability services
and choose any historical-data migration separately after comparison succeeds.

Production acceptance remains explicit: send actual one-api test requests,
compare P95/P99/CPU/RSS and missing telemetry, measure b1 WAL growth during an
agreed home outage, verify recovery throughput exceeds ingress, check disk
pressure and confirm administrator log/trace navigation in a browser. CI's small
synthetic workload is evidence of correctness, not production capacity.
