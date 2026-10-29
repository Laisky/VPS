# Canonical home observability

The owner authorized one coherent logs/metrics/alerts system on 2026-10-29,
permitting historical LOG loss only. The canonical Compose file includes the
private home module; runtime configuration and credential references stay private.

Default native resolution selects 15 services: nine existing applications,
the existing compatibility/PostgreSQL collector and one canonical gateway,
three stores and Grafana. Four legacy backend/UI definitions require the explicit
observability-legacy-rollback profile and remain available with original data.

The compatibility collector keeps existing 4317/4318 clients and PostgreSQL
collection. Existing 8428/9428/10428 slots transfer to the same canonical stores;
18428/19428/20428 remain. No second active store, network attachment, exposure
expansion or credential change is needed. MeTube explicitly uses latest and
PDF already does; version-sensitive infrastructure remains pinned.

Native controls separately resolve default versus rollback roles and preserve
unrelated definitions, dependencies and security/state/port boundaries. Source
selection does not stop or adopt current containers; live migration is unfinished.

Private HOME_ARCHITECTURE.md and HOME_MANAGEMENT.md specify the finite packet,
non-log conservation, coherent backups, metrics native import, trace collision
checks, Grafana UID preservation and same-state rollback. Protected Grafana
metadata and the specifically rejected home-to-dev raw telemetry transfer are
narrow prerequisites; synthetic controls continue independently. No broad repeat
approval for consolidation is requested.

Collector PR50 remains inactive with its owner. Infrastructure/outage alerting
must be independent of ingestion; no live Telegram credential/send activation
is included. CI/source success is not production or alert-delivery acceptance.
