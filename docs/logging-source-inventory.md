# Unified logging: source inventory and acceptance

The desired path is each intended log source → b1 or another appropriately
located go-fluentd → authenticated persistent home gateway → VictoriaLogs. This
is a target, not an assertion about the deployed fleet. The machine-readable
inventory in `tests/log_source_inventory.json` lists every service declared in
root per-host Compose files, including rollback-profile services and development
manifests. RackNerd is historical, not an assumed live deployment target.
A source listed there is not automatically active or approved for collection. It does not cover host journals, standalone containers, external
systems, files, or services deployed outside these manifests; reconcile those
against each host's actual inventory before declaring coverage.

## Present source evidence and unresolved decisions

- b1 GraphQL has optional application OTLP settings in master. The PR proposes
  equivalent Ramjet settings. Both retain local stdout; verify a single central
  ingestion route for each, deployed image support and live effective configuration.
- b1 OneAPI declares an OTEL endpoint to home and a separate log-push API in the
  Compose source. The private logging runbook describes a separate go-fluentd
  route and deliberately limited OneAPI log payload. Determine the effective
  runtime paths and signals before modifying either; avoid duplicate ingestion,
  bypass, privacy regressions and the existing OneAPI release hold. Do not infer
  that the source endpoint alone proves which logs are exported.
- Home has a separate `go-ramjet` service without the b1 application OTLP
  settings; b1 configuration does not cover it. Its current routes require
  independent discovery and qualification.
- The configs compatibility Collector defines a logs pipeline directly to
  VictoriaLogs through memory limiting and batching, bypassing go-fluentd and
  the durable home gateway. This is a source-level route, not proof of current
  live traffic. Inventory its producers, signal use and privacy constraints before
  cutover. A logs-only change must preserve the existing metrics, traces and
  PostgreSQL pipelines, authenticate the chosen edge route and avoid loops or
  duplicate delivery. The compatible receiver, credentials, buffering and
  topology have not yet been qualified; do not redirect this shared receiver
  until those contracts and the rollback are verified.
- All other declared services are `needs_classification`: choose and document
  their intended logs, privacy and retention constraints, source/collector route,
  authentication, and owner. This includes the fleet outside b1, home services,
  collector and sink diagnostics, rollback profiles and development services.
  Collector/sink failure visibility must have an independent path; do not create
  an unbounded ingestion feedback loop. Mark exclusions only after owner review.
- Docker `json-file` settings preserve local output; they do not establish central
  delivery. Do not tail Docker's private JSON files or assume historic backfill.

`test_log_source_inventory.py` detects added or removed per-host Compose sources;
its classifications are planning markers, not runtime acceptance or permission to
collect sensitive data. Review new root manifests and any source outside Compose.

## Qualification and attended acceptance

For each source, record the signal and payload policy, original and destination
identity, configuration revision and immutable image digest, valid transport and
collector codec, plus an independent failure signal. Qualify with synthetic
records in an isolated stack before changing a live route. Verify useful original
content and fields where allowed, source-side filtering where required, and one
central path without accidental duplication. Prove wrong/missing auth and TLS
identity fail closed without weakening access. Validate read-only required mounts,
source shutdown, bounded queues, admission pressure, outage/replay and restart.

Edge HTTP success represents its durable admission only after its sync boundary;
pre-admission SDK memory can drop records. Home gateway queue acceptance is not a
claim of synchronous VictoriaLogs persistence. Ambiguous ACKs can duplicate,
finite disk and retention limit recovery, and replay capacity must exceed live
input. Monitor rejection, drops, age, free space and collector health through an
independent route; an unavailable metric is unknown, not healthy.

Before any rollout, inspect the live checkout and source/container inventory,
verify compatible released images and private configs, capture rollback identities,
confirm disk headroom and preserve all WAL, receipts and existing data. Obtain
specific approval for credentials, networking/security or service recreation.
Apply only an individually reviewed source at a time, verify fresh harmless
records and independent failure visibility, and stop on mismatch. Roll back only
the affected source route while preserving accepted state and a compatible replay
binary. Offline tests, source merges and green CI are not production acceptance.

## Collector adapter and codec constraints

The native OTLP pipeline is separate from legacy Fluent, syslog, Kafka and HTTP
inputs. Selecting a Docker Fluent logging driver alone does not route records
into the native OTLP pipeline. The legacy Fluent sender's flush is not a durable
receiver acknowledgement. The current collector has no native file/journald
tailer or OTLP/gRPC receiver; any adapter requires an explicit delivery and
privacy contract, failure handling, source identity and isolated end-to-end tests.

Qualify the exact collector image and `otlp-record-base64-v1` codec with the
home gateway and VictoriaLogs: include typed and nested attributes, multiline
records and large records near the approximately 2 MiB Victoria row limit.
Destination configuration currently requires all three signal URLs and fans each
signal to every destination; a compatible gateway is necessary. Do not enable an
indefinite archive-retention mode or claim a sink-commit acknowledgement without
a separately designed retirement policy and evidence. The collector's opt-in
real Victoria sink outage/recovery test must run on the candidate image and
configuration; the existence of the test or a skipped run is not acceptance.
