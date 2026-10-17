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
