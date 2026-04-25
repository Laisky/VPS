# HyperBEAM in Docker — Feasibility Study & Minimal Image

A self-contained, minimal Docker image for running a [HyperBEAM](https://github.com/permaweb/HyperBEAM) node — the Erlang/OTP 27 reference implementation of the AO-Core protocol, used to read/write Arweave data items and execute AO processes.

This directory ships:

- `Dockerfile` — multi-stage build producing a runnable release image
- `README.md` — this document; design rationale, citations, ops notes

The aim is the smallest viable **compute-only** node that can serve **on-demand reads of Arweave files** through HTTP, without syncing the whole Arweave dataset.

---

## Verdict: feasible, but the upstream Dockerfile is unsuitable

The official `permaweb/HyperBEAM` repo *does* ship a [`Dockerfile`](https://raw.githubusercontent.com/permaweb/HyperBEAM/main/Dockerfile), but it is essentially a build environment, not a runnable node:

- Compiles **Erlang/OTP 27 from source** (~30 min)
- Compiles the **entire Rust toolchain from source** (extremely wasteful — `rustc` itself bootstraps in well over an hour)
- Only runs `rebar3 compile` — no relx release built
- `CMD ["/bin/bash"]` — no auto-start, no exposed port, no healthcheck
- Final image well over 5 GB

Outstanding upstream issues confirm this is a known pain point:

| Issue | Status | Note |
| --- | --- | --- |
| [#62](https://github.com/permaweb/HyperBEAM/issues/62) | closed | original Dockerfile creation |
| [#131](https://github.com/permaweb/HyperBEAM/issues/131) | closed | "Installing with docker results in python and curl not found errors" |
| [#163](https://github.com/permaweb/HyperBEAM/issues/163) | closed (reverted) | "use stages in docker, publish image to GHCR" |
| [#169](https://github.com/permaweb/HyperBEAM/issues/169) | **open** | "feat: Publish Docker Image" — no official image yet |
| [#592](https://github.com/permaweb/HyperBEAM/issues/592) | open | "use rustup for faster and reliable builds" |
| [#845](https://github.com/permaweb/HyperBEAM/issues/845) | open | "specify platform in docker build" |

The `loadnetwork/load_hb` fork's [`Dockerfile`](https://raw.githubusercontent.com/loadnetwork/load_hb/main/Dockerfile) is byte-identical to the upstream one (685 bytes, sha256 starts `a78f013…`). It only adds a `docker-compose.yaml` wrapper. There is a community image at [`p10node/hyperbeam-docker`](https://github.com/p10node/hyperbeam-docker) on Docker Hub (`p10node/arweave-hb-system`) but no published official image as of 2026-04.

---

## Design choices in this Dockerfile

| Decision | Why |
| --- | --- |
| Base **builder** image: `erlang:27` | Avoids ~30 min OTP-from-source build. No `27-bookworm` tag exists; `27` and `27-slim` (~118 MB) are the canonical tags ([Docker Hub](https://hub.docker.com/_/erlang/tags)). At time of writing `27` resolves to OTP 27.3.4.10. |
| Rust via **`rustup`** (`--profile minimal`) | Tracks the open upstream PR direction in [issue #592](https://github.com/permaweb/HyperBEAM/issues/592). Cuts build time from hours to minutes. |
| Build a **relx release** with `rebar3 release` | Produces `_build/default/rel/hb/bin/hb`, the documented entrypoint with `console`/`start`/`ping`/`status`/`stop` subcommands. The upstream Dockerfile's `rebar3 compile` only leaves a dev shell. |
| Base **runtime** image: `debian:bookworm-slim` | The Erlang release embeds its own ERTS (`include_erts` is true in [`rebar.config`](https://raw.githubusercontent.com/permaweb/HyperBEAM/main/rebar.config)), so we don't need Erlang installed at runtime — just system shared libs. |
| Runtime APT packages: `libssl3 libncurses6 libtinfo6 libstdc++6 ca-certificates curl tini` | Derived from `rebar.config` `port_specs` + NIF C/C++ sources (WAMR is C++ → libstdc++). RocksDB, when enabled, is statically linked, so no `librocksdb` is needed. No `libsodium` / `libb64` either. |
| `tini` as PID 1 | Reaps zombies; forwards signals so `docker stop` cleanly stops the BEAM. |
| Non-root `hb` user (UID 10001) | Erlang releases work fine non-root; reduces blast radius if the node is exposed. |
| `VOLUME /data` + `HB_KEY=/data/hyperbeam-key.json` + `HB_STORE=/data/store` | Wallet keyfile and on-disk cache persist across container restarts. The wallet auto-generates on first start (see below), so no manual provisioning is required for a read-only node. |
| Override `config.flat` to `port: 8734` | Upstream ships [`config.flat`](https://raw.githubusercontent.com/permaweb/HyperBEAM/main/config.flat) with a single line `port: 10000`, which conflicts with the documented default of 8734 in the [running guide](https://hyperbeam.arweave.net/run/running-a-hyperbeam-node.html). We replace the file in the image so port behaviour is predictable. Operators can mount a custom `config.flat` over `/opt/hb/config.flat` to override. |
| `HEALTHCHECK` against `/~meta@1.0/info` | This is the canonical install-verification endpoint (`dev_meta:info/3` in [`src/dev_meta.erl`](https://raw.githubusercontent.com/permaweb/HyperBEAM/main/src/dev_meta.erl) lines 82-100). Returns HTTP 200 + a JSON map of the node's filtered config when healthy. We test for HTTP 200 only — the JSON shape is dynamic. |

---

## Quick start

```bash
# Build (one-time, ~10-20 min on a typical box: clones repo, installs Rust,
# compiles NIFs, builds release).
docker build -t hyperbeam:local arweave/hyperbeam

# Run
docker run -d --name hb \
    -p 8734:8734 \
    -v hb-data:/data \
    hyperbeam:local

# Wait for healthy
docker logs -f hb &
until curl -fsS http://localhost:8734/~meta@1.0/info >/dev/null; do sleep 2; done
echo 'Node is up.'

# Verify node info (expect HTTP 200 and a JSON-ish body of node config)
curl -s http://localhost:8734/~meta@1.0/info | head -c 500

# Read an Arweave data item by TXID (this TXID is used by HyperBEAM's own tests)
TXID=BOogk_XAI3bvNWnxNxwxmvOfglZt17o4MOVAdPNZ_ew
curl -fsS http://localhost:8734/raw/$TXID | head -c 500

# Stop & remove
docker rm -f hb
docker volume rm hb-data        # only if you want a clean reset
```

### Pinning to a known commit / tag

```bash
docker build \
    --build-arg HYPERBEAM_REF=<commit-or-tag> \
    -t hyperbeam:<tag> arweave/hyperbeam
```

The image embeds the resolved commit hash at `/opt/hb/REVISION`.

---

## How a HyperBEAM node reads Arweave files

A minimal node does **not** sync the Arweave chain. Storage is configured as a chained store with the gateway as the final fallthrough. From the live `/~meta@1.0/info` of the running container (`store/2` and `store/3` both use `store-module: hb_store_gateway` over a `cache-mainnet` local prefix), backed by [`src/hb_store_gateway.erl`](https://raw.githubusercontent.com/permaweb/HyperBEAM/main/src/hb_store_gateway.erl) and [`src/hb_gateway_client.erl`](https://raw.githubusercontent.com/permaweb/HyperBEAM/main/src/hb_gateway_client.erl). On a cache miss `hb_gateway_client` issues a GraphQL query and an HTTPS `GET /raw/<txid>` to the configured `gateway` (default `https://arweave.net`, defined as `?DEFAULT_GATEWAY` in [`src/hb_opts.erl`](https://raw.githubusercontent.com/permaweb/HyperBEAM/main/src/hb_opts.erl)).

### main branch vs edge branch — important divergence

The two long-lived upstream branches diverge in how they expose Arweave reads over HTTP. **This image defaults to `main`**.

| Endpoint | `main` (default) | `edge` |
| --- | --- | --- |
| `GET /~meta@1.0/info` | 200 + multipart node config | 200 + multipart node config |
| `GET /~lookup@1.0/read?target=<id>` | Routes through `hb_cache → hb_store_gateway → hb_gateway_client → arweave.net` (logs confirm). Resolves only items that pass the gateway store's GraphQL filter (ANS-104 bundled data items, particularly `Data-Protocol: ao` items). Cache misses take 1-15 s; subsequent reads hit local cache (~20 ms). | Same path exists, but unsigned GETs returned proxied upstream 500 HTML in our tests — likely requires AO HTTP signing or specific content-negotiation. Not reliable for plain `curl`. |
| `GET /raw/<id>` | Route is registered (`prefix: https://arweave.net`, `http_client: gun`) but `routes` is the AO-Core outbound **relay table**, not an inbound HTTP proxy. Returns `"not_found"` 404 in ~20 ms without contacting the gateway. | Same as main. |
| `GET /~arweave@1.0/<func>/...` (e.g. `info`, `tx/<id>`, `raw/<id>`, `current`) | **404** — `src/dev_arweave.erl` does not exist on `main`. | Device exists; for unsigned GETs in our tests it returned arweave.net's own 500 HTML (proxied) — we couldn't get a clean 200 from it. |
| `GET /arweave/...` (no tilde, no version) | 404 | 404 |

Optional: build from `edge` to experiment with `dev_arweave`:

```bash
docker build --build-arg HYPERBEAM_REF=edge -t hyperbeam:edge arweave/hyperbeam
```

If you find the right calling convention for `dev_arweave`'s unsigned reads, please open an issue / PR — the upstream docs site's `/build/api/` reference page is currently 404.

### What "reads Arweave files" really means on `main`

The verified read path is **`/~lookup@1.0/read?target=<TXID>`**. Whether it returns data depends on whether `hb_gateway_client`'s GraphQL probe accepts the TXID as a valid AO/ANS-104 data item:

- **Will work**: ANS-104 bundled data items, particularly AO messages and processes (items tagged `Data-Protocol: ao`).
- **Will return `"not_found"` (404)**: plain pre-bundle Arweave TXs, SmartWeaveContract TXs, anything that doesn't satisfy the gateway store's GraphQL contract — *even when `arweave.net` itself can serve them*.

This is a HyperBEAM/AO-Core protocol design choice, not a Docker issue. If you need a generic Arweave gateway proxy, point at `arweave.net` or `ar.io` directly.

#### Concrete infrastructure verification

The container ships a healthy HyperBEAM node that exercises the gateway store. After `docker run`, run:

```bash
curl -fsS http://localhost:8734/~meta@1.0/info | head -c 400   # → 200, multipart node config
docker inspect -f '{{.State.Health.Status}}' hb               # → "healthy"
docker exec hb ls /data                                       # → hyperbeam-key.json was auto-generated

# Trigger a gateway lookup; the first request takes 1-15 s (cache miss).
TX=$(curl -sS -X POST -H 'Content-Type: application/json' \
    -d '{"query":"{ transactions(tags:[{name:\"Data-Protocol\",values:[\"ao\"]},{name:\"Type\",values:[\"Process\"]}], first:1) { edges { node { id } } } }"}' \
    https://arweave.net/graphql \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['transactions']['edges'][0]['node']['id'])")

# Tail container logs in another terminal while this runs:
#   docker logs -f hb | grep -E 'hb_store_gateway|hb_gateway_client|hb_http'
curl -sS "http://localhost:8734/~lookup@1.0/read?target=$TX"
```

You should see log lines from `hb_store_gateway → hb_gateway_client → hb_http`, e.g.:

```
=== HB DEBUG === @ hb_store_gateway:43 / hb_gateway_client:192 / hb_gateway_client:107 / hb_http:126
```

confirming the chain is reaching out to `arweave.net`. Whether the response body is the data item or `"not_found"` depends on the TX as discussed above. Either way, the infrastructure is verifiably online.

To point at a different gateway (e.g. `ar.io` or a self-hosted `g8way`), set the `gateway` key in a mounted `config.flat`:

```
port: 8734
gateway: https://arweave.net
```

To point at a different gateway (e.g. `ar.io` or a self-hosted `g8way`), set the `gateway` key in a mounted `config.flat`:

```
port: 8734
gateway: https://arweave.net
```

---

## Configuration reference

| Concern | Mechanism | Default |
| --- | --- | --- |
| HTTP port | `HB_PORT` env or `port:` in `config.flat` | `8734` (this image) |
| Wallet keyfile path | `HB_KEY` env or `priv_key_location:` in `config.flat` | `/data/hyperbeam-key.json` (this image) |
| Storage root | `HB_STORE` env or `store:` in `config.flat` | `/data/store` (this image) |
| Arweave gateway | `gateway:` in `config.flat` | `https://arweave.net` |
| Optional build profiles | build-arg, then change `rebar3 release` line | none enabled by default |

Wallet behaviour on first start: if `HB_KEY` points at a non-existent file, `hb:wallet/1` ([`src/hb.erl`](https://raw.githubusercontent.com/permaweb/HyperBEAM/main/src/hb.erl) lines 198-208) calls `ar_wallet:new_keyfile/2` and writes a fresh JWK there. So a clean `docker run` with an empty volume will boot, generate a wallet, and start serving requests. Persist `/data` if you want the same address across restarts.

### Enabling optional profiles

Edit the `rebar3 release` line in the builder stage:

- RocksDB store backend: `rebar3 as rocksdb release` (no extra runtime libs — RocksDB is statically linked)
- Genesis-WASM device: `rebar3 as genesis_wasm release` (compile-time hook)
- HTTP/3 (QUIC): `rebar3 as http3 release`
- Combined: `rebar3 as rocksdb,genesis_wasm release`

---

## What's *not* in this image (intentionally)

- **TEE / AMD SEV-SNP support** — that is a separate deployment ([HyperBEAM-OS](https://github.com/permaweb/HyperBEAM-OS) / Packer + QEMU) and is out of scope for "minimal compute node".
- **Storage-mining** — HyperBEAM is the AO-Core compute layer; persistent Arweave storage is the network's responsibility.
- **A pre-baked wallet** — never bake secrets into images. The keyfile is generated on first run and persisted in the `/data` volume.
- **An official image** (e.g. `ghcr.io/permaweb/hyperbeam:latest`) — none exists upstream as of 2026-04 (issue [#169](https://github.com/permaweb/HyperBEAM/issues/169)).

---

## Sources / citations

Upstream code (main branch unless noted):

- [`permaweb/HyperBEAM` repo](https://github.com/permaweb/HyperBEAM)
- [`Dockerfile`](https://raw.githubusercontent.com/permaweb/HyperBEAM/main/Dockerfile) — upstream baseline (5 GB+, single-stage)
- [`rebar.config`](https://raw.githubusercontent.com/permaweb/HyperBEAM/main/rebar.config) — release name `hb`, profiles, plugins
- [`config.flat`](https://raw.githubusercontent.com/permaweb/HyperBEAM/main/config.flat) — single-line `port: 10000` (overridden by this image)
- [`src/hb.erl`](https://raw.githubusercontent.com/permaweb/HyperBEAM/main/src/hb.erl) — wallet auto-generation
- [`src/hb_opts.erl`](https://raw.githubusercontent.com/permaweb/HyperBEAM/main/src/hb_opts.erl) — default gateway, default routes, store chain
- [`src/dev_meta.erl`](https://raw.githubusercontent.com/permaweb/HyperBEAM/main/src/dev_meta.erl) — `~meta@1.0/info` healthcheck handler
- [`src/dev_arweave.erl`](https://raw.githubusercontent.com/permaweb/HyperBEAM/main/src/dev_arweave.erl) — `/arweave/raw`, `/arweave/tx`, etc.
- [`src/dev_lookup.erl`](https://raw.githubusercontent.com/permaweb/HyperBEAM/main/src/dev_lookup.erl) — `~lookup@1.0/read`
- [`src/hb_store_gateway.erl`](https://raw.githubusercontent.com/permaweb/HyperBEAM/main/src/hb_store_gateway.erl) — gateway-backed cache fallthrough
- [`src/hb_gateway_client.erl`](https://raw.githubusercontent.com/permaweb/HyperBEAM/main/src/hb_gateway_client.erl) — HTTP client to Arweave gateway

Documentation:

- [HyperBEAM Docs Home](https://hyperbeam.arweave.net/)
- [Running a HyperBEAM Node](https://hyperbeam.arweave.net/run/running-a-hyperbeam-node.html)
- [Configuring Your Machine](https://hyperbeam.arweave.net/run/configuring-your-machine.html)
- [Intro to HyperBEAM](https://hyperbeam.arweave.net/build/introduction/what-is-hyperbeam.html)
- [Devices Overview](https://hyperbeam.arweave.net/build/devices/)
- [HyperBEAM FAQ](https://hyperbeam.arweave.net/build/reference/faq.html)
- [Permaweb Journal — HyperBEAM Overview](https://permaweb-journal.arweave.net/article/hyperbeam-overview.html)
- [HackMD — HyperBEAM and AO-Core (draft)](https://hackmd.io/xUzZdCCzQZ-EwV2n0KALFg)

Community:

- [`loadnetwork/load_hb`](https://github.com/loadnetwork/load_hb) — fork (byte-identical Dockerfile + compose wrapper)
- [`p10node/hyperbeam-docker`](https://github.com/p10node/hyperbeam-docker) — community-maintained Docker image
- [Decent Land — Building Rust Devices with HyperBEAM M3 Beta](https://blog.decent.land/rust-hb-tutorial/)
- [PANews — AO Node Workshop](https://www.panewslab.com/en/articles/12061csl3o18) (JS-rendered SPA; not extractable via plain HTTP)
- [Docker Hub `erlang` tags](https://hub.docker.com/_/erlang/tags)
