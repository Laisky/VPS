# Trustworthy Read-Only Arweave Gateway

A single-container, read-only Arweave gateway built on [ar-io-core](https://github.com/ar-io/ar-io-node). Every response to an indexed L1 transaction carries the **full Arweave RSA signature and owner public key** as HTTP headers, so clients can verify the cryptographic chain end-to-end **without trusting this gateway**.

This directory ships:

- `Dockerfile` — wraps `ghcr.io/ar-io/ar-io-core:latest` with a trustworthy-read-only profile
- `entrypoint.sh` — auto-detects a sane `START_HEIGHT` on first boot so the block writer doesn't crawl from genesis
- `README.md` — design rationale, verification recipe, ops notes

No observer. No mempool. No bundling. No Redis. No Envoy. No ClickHouse. No wallet. One container.

TLS is intentionally not handled — terminate HTTPS at your existing reverse proxy and forward to `:4000`.

---

## The verifiable contract

Every successful response carries these headers:

| Header | Meaning | Source |
| --- | --- | --- |
| `X-AR-IO-Data-Id` | the requested TXID (echo) | parsed from URL |
| `X-AR-IO-Digest` | sha256 of the response body, base64url | computed locally on serve |
| `ETag` | quoted `X-AR-IO-Digest` | computed locally |
| `X-AR-IO-Hops` | how many upstream hops this byte stream travelled | response path |
| `X-AR-IO-Cache` (as `X-Cache`) | `HIT` / `MISS` against local cache | local DB |
| `X-AR-IO-Trusted` | `true` if upstream vouched for bytes | per-source flag |
| `X-AR-IO-Verified` | `true` once `DataVerificationWorker` has re-derived `data_root` locally from cached chunks and confirmed it matches the tx's `data_root` | background worker |

For **L1 transactions indexed by the local writer** (controlled by `START_HEIGHT` / `STOP_HEIGHT`), also:

| Header | Meaning |
| --- | --- |
| `X-Arweave-Signature` | RSA signature computed by the tx's owner over `sha256(data_root, tags, owner, anchor, target, quantity, reward, last_tx)` |
| `X-Arweave-Owner` | RSA public key of the owner (base64url, 4096-bit modulus) |
| `X-Arweave-Owner-Address` | `sha256(X-Arweave-Owner)` — the canonical Arweave address |
| `X-Arweave-Anchor` | anti-replay anchor |
| `X-Arweave-Tag-Count` | number of tx tags |
| `X-Arweave-Tag-<Name>` | each tx tag as its own header |
| `X-Arweave-Signature-Type` | key scheme (1 = RSA-PSS) |

### How a client proves a response is genuine

```text
1. Verify the tx signature:
     RSA_verify(X-Arweave-Signature,
                pub = X-Arweave-Owner,
                msg = canonical_tx_hash(X-Arweave-Tag-*,
                                       X-Arweave-Anchor,
                                       X-Arweave-Owner,
                                       data_root_from_signed_fields))
   → proves the owner authorised publishing these tx fields.

2. Confirm the served bytes match the data_root the owner signed:
     - For L1 non-bundled: sha256(response body) should map to the tx's
       data_root via the Arweave merkle layout. Either fetch
       /tx/<id>/data_root to compare (simple) or recompute it locally
       (strict).

3. The gateway cannot forge step 1 (no owner private key) and cannot
   forge step 2 (bytes must hash to data_root). It can only fail to
   respond or return slow — availability is the only attack surface.
```

The `X-Arweave-*` headers in our responses come **from our local tx-header index**, not passed through from upstream. This was verified empirically:

```bash
# Neither arweave.net nor permagate.io nor ar-io.dev emit X-Arweave-Signature:
curl -sI https://arweave.net/<TXID>   | grep -i x-arweave    # → (nothing)
curl -sI https://permagate.io/<TXID>  | grep -i x-arweave    # → (nothing)
curl -sI https://ar-io.dev/<TXID>     | grep -i x-arweave    # → (nothing)

# Our gateway, for a locally-indexed TX, does:
curl -sI http://localhost:4000/<TXID> | grep -i x-arweave
# → X-Arweave-Signature: A-zWtcdjki3EkrPqPJN2O-uSfoX_9Td7...
# → X-Arweave-Owner:     mnYyORuqJPaF-9yhAC3-BIRHIji5ybKGiUu8zfdUAKJ...
# → X-Arweave-Owner-Address: PxGZxzvJSx_ER-VdeqCjMZb0owf6bO5ecOQErRROrPw
# → X-Arweave-Anchor: 9DF307uWM31h8YyitQ8V1WC25fWSp7J7GmipQF67hUxXhahRV3y8leKFDeBMLuXe
# → X-Arweave-Tag-Content-Type: image/jpeg
```

---

## What's in the box

### 1. Block-header writer, bounded by `START_HEIGHT`

`START_WRITERS=true` is on by default. The writer indexes block headers (+ their tx headers) from `START_HEIGHT` forward. The `entrypoint.sh` auto-detects current Arweave height on first boot and sets `START_HEIGHT = current - 100` (about 20 min of back-fill) so the writer doesn't try to crawl from block 0.

Disk cost of the header index is small — roughly **~1 MB per 100 blocks** with default ANS-104 filters off. Writers resume from wherever the local DB left off on subsequent container starts.

To widen the retention window at boot, override at `docker run` time:

```bash
docker run -e START_HEIGHT=1800000 ar-io:local    # index from height 1800000
docker run -e START_HEIGHT_LAG=1000 ar-io:local   # auto-detect, but 1000 blocks back
docker run -e START_WRITERS=false ar-io:local     # disable writers (loses X-Arweave-* headers)
```

### 2. Trustless retrieval, then gateway fallback

Cache-miss fetches are tried in this order (`ON_DEMAND_RETRIEVAL_ORDER`):

1. `ar-io-network` — AR.IO peer mesh; merkle-verified per chunk at fetch time
2. `chunks-offset-aware` — Arweave L1 peer chunks; merkle-verified per chunk
3. `trusted-gateways` — last-resort relay from `TRUSTED_GATEWAYS_URLS`

The `DataVerificationWorker` re-derives `data_root` from cached chunks regardless of how they were fetched, so the gateway fallback is a transport bypass (availability), **not** a trust bypass (the verify flag still depends on byte-level agreement with the tx's `data_root` from `TRUSTED_NODE_URL`).

In practice the Arweave L1 peer mesh returns 404 for most chunks (they're sharded across miners and not uniformly replicated), so `trusted-gateways` ends up serving the majority of cache misses. The `X-Arweave-Signature` still works — it comes from the local tx-header index, not the chunk path.

### 3. In-process caches

All caches use code defaults (`lmdb` / `node` / `memory`) — no Redis sidecar required. The upstream `docker-compose.yaml` overrides these to `redis`, but for standalone we take the defaults.

### 4. Auto-generated admin key

`ADMIN_API_KEY` is printed in logs on first boot if unset. Override at `docker run` time if you want a deterministic key. Read endpoints (`GET /<TXID>`, `/raw/<TXID>`, `/graphql`, `/ar-io/info`, `/ar-io/healthcheck`) don't need it.

---

## Quick start

```bash
# Build.
docker build -t ar-io:local arweave/ario

# Run. Persistent volume holds the tx-header index + payload cache.
docker run -d --name ario \
    -p 4000:4000 \
    -v ario-data:/app/data \
    ar-io:local

# First start: ~8s for migrations, then entrypoint sets START_HEIGHT.
until curl -fsS http://localhost:4000/ar-io/healthcheck >/dev/null; do sleep 2; done
docker logs ario 2>&1 | grep 'ario-trustless\|Block imported' | head

# Request any Arweave data by ID. After a few minutes of writer catch-up,
# responses for post-START_HEIGHT L1 TXs carry the full Arweave signature
# headers.
TX=$(curl -sS -X POST -H 'Content-Type: application/json' \
    -d '{"query":"{ transactions(first:1,sort:HEIGHT_DESC){edges{node{id}}} }"}' \
    https://arweave.net/graphql \
  | jq -r '.data.transactions.edges[0].node.id')

curl -sSI "http://localhost:4000/$TX" \
  | grep -iE '^(x-cache|x-ar-io|x-arweave|etag)' \
  | sort
```

Typical healthy output for an indexed L1 TX:

```
ETag: "_HHWMDPmFBwfke-XJjWJ9_fzRWUmCh7hfAkUlNtGk1U"
X-Arweave-Anchor: 9DF307uWM31h8YyitQ8V1WC25fWSp7J7Gm…
X-Arweave-Owner: mnYyORuqJPaF-9yhAC3-BIRHIji5ybKGiUu8zfdUAK…
X-Arweave-Owner-Address: PxGZxzvJSx_ER-VdeqCjMZb0owf6bO5ecOQErRROrPw
X-Arweave-Signature: A-zWtcdjki3EkrPqPJN2O-uSfoX_9Td7Z1zu5nb…
X-Arweave-Signature-Type: 1
X-Arweave-Tag-Content-Type: image/jpeg
X-Arweave-Tag-Count: 1
X-AR-IO-Data-Id: Dw4TPRLSAu71Clezkd1qwJC-vVlMFKIu2mIEVEetLXM
X-AR-IO-Digest: _HHWMDPmFBwfke-XJjWJ9_fzRWUmCh7hfAkUlNtGk1U
X-AR-IO-Hops: 1
X-AR-IO-Trusted: true
X-Cache: HIT
```

---

## Caveats worth writing down

- **`TRUSTED_NODE_URL` is still a trust anchor for tx-header metadata.** Writers pull block headers and tx metadata from it. For end-to-end trustlessness all the way down to block validation, point `TRUSTED_NODE_URL` at a local Arweave full node (see [`arweave/Dockerfile`](../Dockerfile) in the parent of this directory). A client that wants the full independent chain-of-custody should verify the tx's inclusion in a block via a chain node — our gateway deliberately doesn't.

- **Bundled data items (ANS-104) don't get `X-Arweave-*` headers in this config.** We keep `ANS104_UNBUNDLE_FILTER='{"never":true}'` because unbundling and indexing every data item on mainnet is an expensive, disk-heavy operation. For bundled items you still get `X-AR-IO-Digest` (local sha256) and, via `X-AR-IO-Root-Transaction-Id`, the parent bundle's TX — fetch that bundle separately to get its signature.

- **`X-AR-IO-Verified: true` doesn't flip for on-demand-served bytes in a read-only node.** The `DataVerificationWorker` scans items in the local verification index populated primarily by writers. Without a populated index for the specific data item's parent bundle, the flag stays `false`. Treat it as best-effort; the primary cryptographic signal is `X-Arweave-Signature` + digest, not this flag.

- **Peer mesh availability is a real limitation.** Strict `chunks-offset-aware` + `ar-io-network` retrieval works only when Arweave L1 miners or AR.IO gateways happen to hold the specific chunks. Most modern traffic (bundled) falls through to `trusted-gateways`. We still serve the right bytes — the signature header is what makes the answer verifiable, regardless of which source delivered the bytes.

- **Availability fallback is non-trust-verified at fetch time.** If all chunk sources fail and `trusted-gateways` serves the bytes, `X-AR-IO-Trusted: true` is set but nothing cryptographic enforced the bytes at serve time. The client-side signature check catches a malicious upstream; a merely *malicious* (not liar) upstream would just withhold correct bytes.

---

## Configuration reference

All env vars have sensible defaults baked into the image. Override at `docker run` time.

| Concern | Env var | Default (this image) |
| --- | --- | --- |
| HTTP port | `CORE_PORT` | `4000` |
| Data root (volume) | `DATA_PATH` | `/app/data` |
| Trust anchor (tx headers) | `TRUSTED_NODE_URL` | `https://arweave.net` |
| Gateway fallback list | `TRUSTED_GATEWAYS_URLS` | `{arweave.net: 1, permagate.io: 2, ar-io.dev: 3}` |
| Retrieval order | `ON_DEMAND_RETRIEVAL_ORDER` | `ar-io-network,chunks-offset-aware,trusted-gateways` |
| Chunk data sources | `CHUNK_DATA_RETRIEVAL_ORDER` | `ar-io-network,arweave-network` |
| Writers | `START_WRITERS` | `true` |
| Writer window start | `START_HEIGHT` | unset → entrypoint sets to `current - START_HEIGHT_LAG` |
| Writer window lag | `START_HEIGHT_LAG` | `100` blocks |
| Background verification | `ENABLE_BACKGROUND_DATA_VERIFICATION` | `true` |
| Verification period | `BACKGROUND_DATA_VERIFICATION_INTERVAL_SECONDS` | `60` |
| Verification priority floor | `MIN_DATA_VERIFICATION_PRIORITY` | `0` |
| Observer | `RUN_OBSERVER` | `false` |
| Mempool watcher | `ENABLE_MEMPOOL_WATCHER` | `false` |
| Bundle backfill | `BACKFILL_BUNDLE_RECORDS` | `false` |
| ANS-104 unbundle filter | `ANS104_UNBUNDLE_FILTER` | `{"never":true}` |
| ANS-104 index filter | `ANS104_INDEX_FILTER` | `{"never":true}` |
| Envoy peer DNS | `ARWEAVE_PEER_DNS_RECORDS` | (empty; unused without Envoy) |
| Payload cache cap | `CONTIGUOUS_DATA_CACHE_CLEANUP_THRESHOLD` | 10 GiB |
| Chunk cache cap | `CHUNK_DATA_CACHE_CLEANUP_THRESHOLD` | 2 GiB |
| Admin key | `ADMIN_API_KEY` | auto-generated in logs |

### Upgrading to a stricter deployment

- Run a local Arweave full node and set `TRUSTED_NODE_URL=http://arweave-full:1984` — removes arweave.net as the tx-header trust anchor. Pair with the parent directory's `arweave/Dockerfile`.
- Enable ANS-104 unbundling (`ANS104_UNBUNDLE_FILTER={"always":true}`) if you want `X-Arweave-Signature` coverage on bundled data items. Expect significant disk (~~100 GB+) and CPU cost.
- Put Envoy in front and set `ARWEAVE_PEER_DNS_RECORDS=peers.arweave.xyz` to use DNS-discovered Arweave peers for chunk fetches instead of the hardcoded `data-1..data-17.arweave.xyz` list.

---

## Resource footprint (measured)

- **Image size**: ~1.29 GB (most of which is the shipped `cdb64` index of ~964 M ANS-104 data items)
- **Cold boot**: ~8 s to healthcheck (50 SQLite migrations + entrypoint height lookup)
- **RAM**: ~1-2 GB idle, 4-8 GB under load
- **Disk** (`/app/data`): ~5-10 GB baseline; grows up to `CONTIGUOUS_DATA_CACHE_CLEANUP_THRESHOLD` (10 GiB default) for payload cache. Header index grows at roughly 1 MB per 100 blocks with ANS-104 filters off — negligible compared to payload cache.
- **Network**: outbound HTTPS to `TRUSTED_NODE_URL`, `TRUSTED_GATEWAYS_URLS`, and Arweave L1 peers (`data-1..data-17.arweave.xyz`) on port 1984.

---

## Citations

Upstream code (main branch unless noted):

- [`ar-io/ar-io-node`](https://github.com/ar-io/ar-io-node) — the project (AGPL-3.0)
- [`Dockerfile`](https://raw.githubusercontent.com/ar-io/ar-io-node/main/Dockerfile)
- [`docker-compose.yaml`](https://raw.githubusercontent.com/ar-io/ar-io-node/main/docker-compose.yaml)
- [`.env.example`](https://raw.githubusercontent.com/ar-io/ar-io-node/main/.env.example)
- [`docs/envs.md`](https://github.com/ar-io/ar-io-node/blob/main/docs/envs.md)
- [`docs/openapi.yaml`](https://raw.githubusercontent.com/ar-io/ar-io-node/main/docs/openapi.yaml)
- [`src/config.ts`](https://raw.githubusercontent.com/ar-io/ar-io-node/main/src/config.ts) — `TRUSTED_GATEWAYS_URLS` parser (lines 133-164), `ON_DEMAND_RETRIEVAL_ORDER` (lines 796-801), `START_HEIGHT` default (line 1028)
- [`src/system.ts`](https://raw.githubusercontent.com/ar-io/ar-io-node/main/src/system.ts) — source dispatch (line 1036)
- [`src/lib/validation.ts`](https://raw.githubusercontent.com/ar-io/ar-io-node/main/src/lib/validation.ts) — `validateChunk` (lines 91-114)
- [`src/data/ar-io-chunk-source.ts`](https://raw.githubusercontent.com/ar-io/ar-io-node/main/src/data/ar-io-chunk-source.ts) — AR.IO peer chunk fetch + verify
- [`src/arweave/composite-client.ts`](https://raw.githubusercontent.com/ar-io/ar-io-node/main/src/arweave/composite-client.ts) — L1 peer chunk fetch + verify
- [`src/workers/data-verification.ts`](https://raw.githubusercontent.com/ar-io/ar-io-node/main/src/workers/data-verification.ts) — background data-root re-derivation
- [`src/routes/data/handlers.ts`](https://raw.githubusercontent.com/ar-io/ar-io-node/main/src/routes/data/handlers.ts) — response header construction
- [`src/database/standalone-sqlite.ts`](https://raw.githubusercontent.com/ar-io/ar-io-node/main/src/database/standalone-sqlite.ts) — `getVerifiableDataIds` filter
