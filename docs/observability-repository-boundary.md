# Observability source ownership and ordered rollout

## Per-machine production configuration

All home services are defined directly in `home-docker-compose.yml`. Home has no
Compose include, extends, overlay or shared YAML anchor. Repeated settings are
intentional for this small fleet. The five canonical observability services and
four offline rollback definitions keep their existing names, image digests,
paths, ports, limits, networks and approved seven-day retention.

configs holds private program configuration and existing env/secret inputs, not
Compose definitions. Grafana, the Collector, Prometheus and the edge collector
consume different native file formats; keeping those program files separate is
not a Compose layering requirement. There is no Python source-path resolver.

Use the existing home project `vps` and private interpolation file explicitly:

```sh
docker compose --env-file /opt/configs/observability/.env \
  -f /home/laisky/repo/laisky/VPS/home-docker-compose.yml -p vps config --quiet
```

If a caller already supplies project env files, put the private file FIRST and
retain those existing env files in their original order after it. Shell values
still take precedence. Do not add a service env_file: that would expose unrelated
private inputs to containers. Never print resolved configuration to shared logs.

## Compatibility exception outside production home

`observability/` retains the existing non-home edge/application release inputs
and isolated qualification overlays, unchanged from configs. These are not part
of the home production command. They preserve existing b1 release manifests and
disposable failure tests; removing them would change unrelated callers. No new
production abstraction or blanket migration of other hosts is introduced here.

## Ordered apply after separate deployment approval

1. Stage the paired VPS revision first without resetting dirty host checkouts.
2. Compare old/new native models using synthetic env files. Validate default and
   rollback profiles, existing project-env precedence, private paths, image pins,
   security/resources and unique active ports. The private test rejects actual
   listener, state, credential-reference or retention drift.
3. Update callers to the direct home command above. Keep the existing project
   name and env-file order. Reconcile any reviewed manifest hashes explicitly.
4. Only then apply configs source removals. Preserve old live Compose files for
   rollback until all callers use VPS; source removal is not a live deletion.
5. Identical effective models require no service restart. These Drafts perform
   no live path movement, recreation, upgrade, data transfer or security change.

## Dedicated nginx configuration

`configs/nginx/conf.d/b1/logs.conf` versions the existing dedicated host block.
TLS, Basic Auth credential-file reference and the `/select/` VictoriaLogs upstream
are unchanged. The file contains no username, password or hash; htpasswd remains
ignored. Synthetic checks are not a live login or nginx reload.

## Rollback

Keep previous source revisions, live files, pinned images, accepted state and
coherent backups. Restore source selection and original arguments only; never
restore old WAL over fresh data. Preserve seven-day retention: changing flags
cannot recover expired history. No down/prune/remove-orphans or backup deletion.

## Small-repository CI

Automatic checks are the eight inexpensive repository-boundary controls and the
Compose parser bind-declaration check when its relevant files change. Automatic
runs do not pull an acceptance image or create test containers. The existing
Compose compatibility workflow runs engine controls only through manual dispatch.
Full paired-model, nginx request and telemetry integration campaigns remain local
or explicitly manual in configs; no matrix is added.
