# VPS Compose operations

Use the Docker Compose plugin (`docker compose`, version 2 or newer).
The legacy `docker-compose` v1 executable does not support all options used by
existing host configuration, including `bind.create_host_path: false`.
Do not remove that safeguard or convert its mount to short syntax: a missing
config file must fail rather than silently become an empty directory.

Existing configuration belongs under `/opt/configs`. Preserve host-local
changes and inspect `git status` before updating either checkout. Never reset a
live Compose file to the repository version to work around validation.

## Validate without changing services

From the VPS checkout on b1:

```sh
docker compose version
op run --env-file=./one-api/b1.env -- \
  docker compose -p vps -f b1-docker-compose.yml config --quiet
```

Keep secret injection in the existing approved route. Do not print rendered
configuration or copy production environment files to a development machine.
Successful validation proves parsing only, not deployed health.

## Update one application

The intended flow is to publish the application's `latest` image, pull it, then
recreate only that application. A moving tag does not update an existing
container automatically. For example, after the specific GraphQL rollout is
approved:

```sh
op run --env-file=./one-api/b1.env -- \
  docker compose -p vps -f b1-docker-compose.yml pull graphql
op run --env-file=./one-api/b1.env -- \
  docker compose -p vps -f b1-docker-compose.yml up -d --no-deps --no-build --pull never --force-recreate graphql
```

Check the selected service's status and application health after recreation.
Compare its running image ID with the pulled image's config ID; container
`Created` age and an untagged image display alone do not prove staleness.

Do not add `--remove-orphans` to a per-service release or run a blanket
`up --force-recreate`: other applications and override-only services may be
affected. Keep the existing Compose project identity; do not rename containers
or alternate between v1 and v2 commands. This GraphQL example matches its
existing V2 naming. Some other services deliberately use `--compatibility` to
retain underscore names; preserve their existing helper flags rather than
applying that flag globally on this mixed host. Review active deployment work
before any change.

Use each application's existing release workflow/helper when it provides
secret injection, graceful shutdown, health checks or rollback. Preserve an
intentional rollback image override until that application's separate release
is authorized. Do not replace those controls with the generic example.
Database and infrastructure version pins are intentional and are not candidates
for a blanket `latest` upgrade.

## Dev machine: ARTEX

`dev-docker-compose.yml` directly defines the dev services, including ARTEX and
its dedicated PostgreSQL 16. It does not import any other Compose file.
The sibling ARTEX checkout supplies build sources and skills only.

Private configuration lives under `/opt/configs`:

| Path | Purpose |
|---|---|
| `/opt/configs/env/dev/artex.env` | Model API settings and keys; application env_file |
| `/opt/configs/env/dev/artex-postgres.env` | Database environment and password; database env_file |
| `/opt/configs/artex/dev/config.json` | Database connection; read-only application mount |
| `/opt/configs/artex/dev/jwt.key` | Existing JWT signing key; read-only mount |
| `/opt/configs/artex/dev/admin-password` | Operator's administrator password; not mounted |
| `/opt/configs/artex/dev/data/` | Private workspaces, sessions and traffic |
| `/opt/configs/artex/dev/backups/` | Private migration and database backups; not mounted |

Credential files are mode `0600`, the private directory is `0700`, and these
paths are locally excluded from the configs repository. Environment files use
`format: raw`: write raw `KEY=value` entries without surrounding quotes.

The dedicated `postgres` service uses the external volume `artex-local-pgdata`
on the `artex` network. The existing shared `postgre` service remains separate.
Ports 8787 and 8788 bind only to this host's Tailscale IPv4, `100.75.198.70`.

Run from this directory:

```sh
docker compose -p vps -f dev-docker-compose.yml up -d postgres artex
docker compose -p vps -f dev-docker-compose.yml ps
docker compose -p vps -f dev-docker-compose.yml logs --tail=100 artex
```

After editing `/opt/configs/env/dev/artex.env`:

```sh
docker compose -p vps -f dev-docker-compose.yml up -d --no-deps --force-recreate artex
```

After editing source code:

```sh
docker compose -p vps -f dev-docker-compose.yml build artex
docker compose -p vps -f dev-docker-compose.yml up -d --no-deps artex
```

Use this unified project for the dev host. Do not start the standalone ARTEX
Compose against the same database volume. When operating ARTEX alone, specify
its services so other dev services are not restarted. Full operating and
recovery notes are in
[`../ARTEX/docs/manuals/local-setup.md`](../ARTEX/docs/manuals/local-setup.md).

## Regression acceptance

Run parser acceptance with a modern Compose plugin:

```sh
python3 -m unittest discover -s tests -v
```

For isolated engine acceptance on a development/CI daemon, supply an already
available image. The tests create and remove only their uniquely named
containers; they never start the image, expose ports, read production config,
or mount a persistent data directory:

```sh
COMPOSE_ENGINE_TEST=1 COMPOSE_TEST_IMAGE=busybox:1.37.0 \
  python3 -m unittest discover -s tests -v
```

The missing-source control must fail without creating the source directory.
The existing-file control must create a read-only bind without modifying it.
