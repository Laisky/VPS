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
