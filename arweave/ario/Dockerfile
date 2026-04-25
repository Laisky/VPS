# syntax=docker/dockerfile:1.7
# Minimal *trustworthy* read-only ar.io Arweave gateway.
#
# Every response carries enough cryptographic metadata for the client to
# independently verify the tx content against the Arweave blockchain without
# trusting this gateway:
#
#   X-Arweave-Signature          — the tx's RSA signature (base64url)
#   X-Arweave-Owner              — the owner's RSA public key (base64url)
#   X-Arweave-Owner-Address      — sha256(owner) — the Arweave address
#   X-Arweave-Tag-*              — all tx tags (Content-Type, App-Name, …)
#   X-AR-IO-Digest               — sha256 of the response body
#   ETag                         — quoted X-AR-IO-Digest
#   X-AR-IO-Hops                 — upstream hop count (0 = direct peer chunk)
#   X-AR-IO-Trusted / Verified   — server-side attestation flags
#
# With `X-Arweave-Signature` + `X-Arweave-Owner` the client can verify the
# full Arweave tx signature (it covers the data_root), and comparing the
# response body's sha256 to the derived data_root closes the cryptographic
# chain end-to-end. This gateway cannot forge any of these fields without
# the owner's private key.
#
# These `X-Arweave-*` fields are only populated when writers are enabled,
# because they come from the locally-indexed tx-header store. The bundled
# entrypoint.sh auto-detects a recent START_HEIGHT on first boot so the
# writer starts ~100 blocks behind current, instead of crawling from block 0.
#
# Upstream image: https://github.com/ar-io/ar-io-node
#
# Build:  docker build -t ar-io:local arweave/ario
# Run:    docker run -d --name ario -p 4000:4000 -v ario-data:/app/data ar-io:local
# Verify: curl -fsSI http://localhost:4000/<TXID>

ARG AR_IO_CORE_TAG=latest
FROM ghcr.io/ar-io/ar-io-core:${AR_IO_CORE_TAG}

# --- Trust boundary --------------------------------------------------------
ENV TRUSTED_NODE_URL=https://arweave.net

# Multi-upstream list used as last-resort fallback in the retrieval order.
ENV TRUSTED_GATEWAYS_URLS='{"https://arweave.net":1,"https://permagate.io":2,"https://ar-io.dev":3}'

# --- Retrieval order -------------------------------------------------------
# Prefer sources that merkle-verify chunks at fetch time; fall through to
# trusted-gateways only when Arweave peer mesh can't serve the chunk.
# DataVerificationWorker will re-derive data_root for cached bytes regardless
# of how they were fetched, so gateway fallback is a transport bypass, not a
# trust bypass. See src/data/tx-chunks-data-source.ts + src/lib/validation.ts.
ENV ON_DEMAND_RETRIEVAL_ORDER=ar-io-network,chunks-offset-aware,trusted-gateways
ENV CHUNK_DATA_RETRIEVAL_ORDER=ar-io-network,arweave-network
ENV CHUNK_METADATA_RETRIEVAL_ORDER=ar-io-network,arweave-network

# --- Block-header writer ---------------------------------------------------
# Must be on to populate the local tx-header index that lets the read path
# emit X-Arweave-Signature / X-Arweave-Owner / X-Arweave-Tag-*. Without
# writers the response lacks all of those fields and clients have no way to
# independently verify the tx.
#
# The entrypoint auto-sets START_HEIGHT = current-100 on first boot. To index
# more history, set START_HEIGHT=<value> at `docker run` time (writers resume
# from wherever the local db left off on subsequent starts).
ENV START_WRITERS=true

# --- Background re-verification --------------------------------------------
# Re-derives data_root from cached bytes and flips the DB `verified` flag,
# making X-AR-IO-Verified reflect end-to-end cryptographic agreement with
# TRUSTED_NODE_URL. Lag-bounded: first scan runs at boot, then every INTERVAL.
ENV ENABLE_BACKGROUND_DATA_VERIFICATION=true \
    BACKGROUND_DATA_VERIFICATION_INTERVAL_SECONDS=60 \
    MIN_DATA_VERIFICATION_PRIORITY=0 \
    MAX_VERIFICATION_RETRIES=5

# --- Read-only posture -----------------------------------------------------
# Writers index block/tx headers but we still disable bundle unbundling and
# observer/mempool subsystems. Keeps the db small (tx-headers only, no
# expanded ANS-104 data-item rows).
ENV RUN_OBSERVER=false \
    ENABLE_MEMPOOL_WATCHER=false \
    BACKFILL_BUNDLE_RECORDS=false \
    ANS104_UNBUNDLE_FILTER='{"never":true}' \
    ANS104_INDEX_FILTER='{"never":true}' \
    ARWEAVE_PEER_DNS_RECORDS=

# Cache backends use code defaults (lmdb / node / memory) — all in-process.

# --- Disk-bound LRU cleanup ------------------------------------------------
ENV ENABLE_CHUNK_DATA_CACHE_CLEANUP=true \
    ENABLE_FS_HEADER_CACHE_CLEANUP=true \
    CONTIGUOUS_DATA_CACHE_CLEANUP_THRESHOLD=10737418240 \
    CHUNK_DATA_CACHE_CLEANUP_THRESHOLD=2147483648

# --- Entrypoint ------------------------------------------------------------
# Distroless-based image has no chmod; BuildKit's COPY --chmod does the job.
COPY --chmod=755 entrypoint.sh /usr/local/bin/ario-entrypoint.sh
ENTRYPOINT ["/usr/local/bin/ario-entrypoint.sh"]

# ADMIN_API_KEY auto-generates on first boot if unset. Read endpoints don't
# need it. /app/data volume, port 4000, HEALTHCHECK come from the base image.
