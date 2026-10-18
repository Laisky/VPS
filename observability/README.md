# Observability deployment entrypoint

Runtime configuration is owned by **Laisky/configs**, mounted at `/opt/configs`.
This directory deliberately contains only this guide and a path-only Compose
entrypoint. Collector settings, go-fluentd generation, Grafana provisioning and
dashboards, service parameters, environment templates and the one-api override
are maintained in `/opt/configs/observability`, not duplicated in VPS.

## Deployment

Use the corresponding reviewed revisions of VPS and configs. Provision the
private environment and TLS identities using the runbook at
`/opt/configs/observability/README.md`. Do not use development credentials on a
server. The wrapper explicitly loads configuration and its environment from the
mounted path and does not fall back to files in the VPS checkout.

From the VPS repository root, start home before the edge:

```sh
# On home:
docker compose --env-file /opt/configs/observability/.env \
  -f observability/compose.yml --profile home config --quiet
docker compose --env-file /opt/configs/observability/.env \
  -f observability/compose.yml --profile home up -d

# On b1, after configuration and storage provisioning:
docker compose --env-file /opt/configs/observability/.env \
  -f observability/compose.yml --profile edge config --quiet
docker compose --env-file /opt/configs/observability/.env \
  -f observability/compose.yml --profile edge up -d
```

The one-api override is also external. After verification, use the following
through the **existing business-secret injection mechanism**; do not lose the
variables needed by `b1-docker-compose.yml`:

```sh
docker compose --env-file /opt/configs/observability/.env \
  -f b1-docker-compose.yml \
  -f /opt/configs/observability/one-api.override.yml config --quiet
docker compose --env-file /opt/configs/observability/.env \
  -f b1-docker-compose.yml \
  -f /opt/configs/observability/one-api.override.yml up -d --no-deps oneapi
```

Use `config --quiet` rather than printing expanded secrets. Persistent data stays
at the explicitly provisioned data locations; `/opt/configs` is not a production
database volume. Existing b1/home Compose services and billing data are unchanged
until the operator explicitly applies the external override.

## Verification and rollback

The public workflow checks that runtime files/inline parameters are not
reintroduced here. Real-container acceptance runs in the **private configs CI**
against an exact VPS revision, with its checkout mounted at `/opt/configs`.
It exercises this actual entrypoint, resolves the real one-api merge with fake
secret files, and retains authentication, retention and SIGKILL recovery checks.
No private repository checkout, credentials or configuration artifacts are
published by VPS CI. Consult the linked companion PR for the tested revision
pair and private acceptance evidence.

This repository split does not itself deploy services, relocate existing data or
change delivery guarantees. Follow the private runbook for a controlled rollout
and rollback. Preserve the edge's complete version-compatible state; do not
reset checkpoints or remove pending data to make an older binary start.


## Ramjet and GraphQL application logs

This source change wires the optional application OTLP bridges to the existing b1 go-fluentd TLS endpoint. Stdout stays enabled, bounded by each existing Docker logging configuration. It is not collected a second time, so enabling OTLP does not duplicate stdout ingestion. There is no automatic stdout backfill.

Both service bridges must be released and qualified before enabling these entries. Do not apply this complete compose file over a dirty live checkout: reconcile only these two service changes with the current owner. A source PR does not authorize production credential configuration, hostname mappings, mounts or service recreations.

### Configuration contract

Each service uses `APP_LOG_OTLP_ENDPOINT=https://b1.snake-carp.ts.net:14319`, `APP_LOG_OTLP_TOKEN_FILE=/run/observability/edge-token`, `APP_LOG_OTLP_CA_FILE=/run/observability/ca.crt`, host `b1` and environment `production`. Service names are fixed by the applications: `go-ramjet` and `graphql`. The hostname mapping preserves TLS name verification while resolving the existing collector Tailnet address.

The token and CA are individual read-only bind mounts. `create_host_path: false` fails closed if a required host file is missing. The existing CA is public trust material; the bearer token must remain private. Do not paste token values in chat, command arguments, CI output or Git. Provision this file through the approved secure operator procedure; do not extract credentials from another application container.

### Attended rollout requirements

1. Obtain owner approval for each source merge and Draft removal. Use the existing publication flow, verify tested source revisions and immutable image receipts, and coordinate the short service window with the OneAPI/runtime owner.
2. Obtain specific action-time approval to materialize the existing edge bearer token opaquely into `/opt/configs/observability/secrets/app-otlp-token`, add the individual token/CA mounts and hostname mapping, and recreate only the two intended services. No credential is supplied by this repository. The currently observed host path is absent; `docker compose up` before preparation must fail rather than create a directory.
3. Keep the secrets parent private. The token file must be readable by the existing service identity (GraphQL UID1000 and Ramjet root in the observed runtime), with no world access. Validate file type, ownership and mode without exposing its value. Confirm the exact CA and TLS hostname match the collector. Preserve TLS/authentication throughout.
4. Reconcile the two service properties into the current live compose source without overwriting unrelated dirty work, then validate the resolved model privately. Recreate one service at a time using the established application release procedure. Do not restart Docker, Tailscale, go-fluentd, OneAPI or the home stack.
5. Query actual fresh records and useful content after each service release. Confirm stdout still works, SDK bounded-failure diagnostics remain local, collector rejection/quarantine counters stay clear and no unrelated container changed. Preserve historical records and WAL roots.

### Acceptance and recovery

VictoriaLogs' verified private query base is `http://100.69.166.78:19428`; the UI is `/select/vmui/`, and the LogsQL API is `/select/logsql/query`. Use an explicit recent time range and `service.name:="go-ramjet"` or `service.name:="graphql"`. Stored labels include `host.name` and `deployment.environment.name`; Body appears as `_msg`. Acceptance must assert a known harmless original operational message and its fields, not only a row count. Do not expose request bodies or credentials while collecting evidence.

Application SDK queues are bounded and memory-only. Normal process shutdown flushes within a finite deadline; abrupt exits and pre-collector-ACK loss remain possible. go-fluentd acknowledges durable admission and later replays accepted work to the existing persistent home gateway. Ambiguous acknowledgements can duplicate. Current home retention is finite 100 years and does not guarantee available disk space; monitor queue storage, free bytes/inodes and oldest pending age independently.

If optional OTLP configuration prevents a healthy service start, remove only these new service environment/mount/hostname entries through the attended deployment process and return to the established stdout-only behavior. Preserve private credential files, accepted collector state and all historical data. Do not roll back or delete shared collector queues. Actual image rollback follows each application's established approved release procedure; this change creates no local rollback tag or image.

Public `logs.laisky.com` nginx/authentication is a separate security approval. This integration makes no public ingress, DNS, firewall or Tailscale change.
