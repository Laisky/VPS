# docker-compose for my VPS

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


Prepare configs:

```sh
git clone git@gitlab.com:Laisky/configs.git /opt/config
```

Run:

```
docker-compose build
docker-compose up -d --remove-orphans --force-recreate
```


## TODO

- [x] mongodb
- [ ] fluentd
- [ ] blog
- [x] shadowsocks
- [x] shadowsocksr
- [ ] v2ray
- [ ] ramjet
- [ ] nginx
- [x] rocket.chat
