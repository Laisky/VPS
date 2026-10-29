# Home observability source integration

`home-docker-compose.yml` is the canonical home lifecycle entry. Its path-only
include loads `/opt/configs/observability/home.compose.yml`; all retained runtime
parameters and credential references remain in private `Laisky/configs`.
Install the reviewed companion module before using the updated home model.

The retained group uses five distinct `observability-*` service keys behind the
explicit `observability-home` profile. Ordinary home `up` does not activate them.
The existing fourteen home services, legacy observability definitions, images
and datasets remain unchanged. Application `latest` policy does not change
pinned infrastructure versions in this handoff.

The include does not adopt running containers from another Compose project.
The current retained group must remain untouched until the separately approved
same-data ownership handoff. That handoff requires verified backups, no concurrent
old/new state writers and preserving rollback. No runtime action is authorized
by merging these source declarations.

Follow private `observability/HOME_MANAGEMENT.md` for the exact retained paths,
image/port/retention contract, dev acceptance commands and proposed runtime steps.
In particular, preserve effective 100-year retention rather than substituting
the generic qualification stack's seven-day default. Never merge the two Grafana
databases or infer that zero recent legacy logs permits deletion.

After approval, manage the retained group through this file with project `vps`
and profile `observability-home`, selecting only the five intended service keys.
Use private `config --quiet` validation; never print expanded secret values.

## Unified target and current status

The owner authorized a coherent logs/metrics/alerts migration on 2026-10-29.
The paired private HOME_ARCHITECTURE.md selects one active gateway/store set,
one Grafana, centralized optional application-error alerts and independent
infrastructure/outage checks. The present five-service profile is a staging
foundation; preserving two active complete groups is not the final goal.
Metrics, traces and both Grafana datasets must survive qualification before
legacy roles become offline rollback profiles. No live migration has run yet.
MeTube now spells its existing implicit latest image selector explicitly; PDF
already uses latest. No infrastructure image tag or pin changes.
