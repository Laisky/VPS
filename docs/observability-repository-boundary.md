# Observability source ownership and ordered rollout

VPS owns Compose definitions and overlays. Sensitive runtime inputs stay in
configs. The earlier VPS entrypoints actively included private definitions;
those private files were not stale duplicates.

## Source ownership

- `observability/compose.yml` remains the shared entrypoint, now including the
  VPS-owned `services.compose.yml`. The canonical home file includes the
  VPS-owned `observability/home.compose.yml`.
- The other eight tracked overlays live beside those modules. All ten moved
  templates retain their directives, including Compose override tags.
- Keep include project_directory `/opt/configs/observability` and explicit
  env_file `/opt/configs/observability/.env`. Existing bind paths, images, ports,
  profiles, interpolation precedence and project names remain unchanged.
- Keep secret files, generated collector settings and private manifests in configs.
  Never publish resolved YAML, tokens, passwords, hashes or private keys in VPS.
  Existing ignored generated image overlays remain bound to reviewed deployment
  manifests; this source correction does not silently repin or delete them.

## Ordered apply after separate source/deployment approval

1. Stage the paired VPS revision first, preserving each host's dirty source and
   existing ordered Compose arguments/project name. Do not reset or blindly pull.
2. Compare old/new native models in owned temporary fixtures with fake env files:
   every overlay, default/all-profile selection, paths, ports, security/resources
   and project names. Retain missing-include and invalid-listener controls.
3. Update private helper source and its exact companion pin. Existing reviewed
   manifests naming/hashing moved inputs require explicit reconciliation before
   future promotion. Business releases must not acquire telemetry dependencies.
4. Only then apply configs source removals. Retain old live files for rollback
   until every live caller uses VPS. Do not delete them as an automatic sync step.
5. Identical effective models need no restart. No live file movement, container
   recreation, image upgrade, data transfer, DNS/security or credentials action
   is performed by these Draft source PRs. Report exact impact if one is needed.

## Dedicated nginx configuration

`configs/nginx/conf.d/b1/logs.conf` versions the existing dedicated host block,
with unchanged TLS references, Basic Auth credential-file reference and `/select/`
VictoriaLogs upstream. It contains no username, password or hash. Keep htpasswd
ignored. Validate the same source with synthetic files before any separate apply;
no nginx reload or live login is included here.

## Rollback

Preserve the old entrypoint/include files, pinned images, accepted state and
coherent backups before a later path cutover. Restore source selection only;
never restore old WAL or overwrite fresh data. Keep approved seven-day retention:
reverting a flag cannot recover expired history. No down/prune/remove-orphans or
backup deletion is part of source integration.
