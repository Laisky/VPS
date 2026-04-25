#!/bin/sh
# Trustless-mode entrypoint wrapper for ar-io-core.
#
# Auto-detects a sensible START_HEIGHT on first boot so the block-header
# writer doesn't try to index from block 0. Without this, START_HEIGHT
# defaults to 0 (config.ts), meaning writers walk the entire Arweave chain
# — tens of GB of headers for a node that only cares about verifying newly-
# requested TXs.
#
# Logic:
#   - If START_WRITERS is not "true" → do nothing, let upstream handle it.
#   - If START_HEIGHT is already set  → respect operator's choice.
#   - Otherwise: query TRUSTED_NODE_URL/info for current height, subtract
#     START_HEIGHT_LAG (default 100 blocks, ~20 minutes of chain), and set
#     START_HEIGHT to that.
#
# The subtract gives us a tiny back-fill buffer so we catch a handful of
# recently-confirmed txs on first boot. All subsequent block headers are
# indexed forward from there — so the db grows ~1 block per ~2 min.
set -e

if [ "${START_WRITERS:-false}" = "true" ] && [ -z "${START_HEIGHT:-}" ]; then
    LAG=${START_HEIGHT_LAG:-100}
    URL="${TRUSTED_NODE_URL:-https://arweave.net}/info"
    SH=$(/nodejs/bin/node -e '
        const url = new URL(process.argv[1]);
        const mod = url.protocol === "https:" ? require("https") : require("http");
        mod.get(url, r => {
            let buf = "";
            r.on("data", c => buf += c);
            r.on("end", () => {
                try {
                    const h = JSON.parse(buf).height;
                    console.log(Math.max(0, h - Number(process.argv[2])));
                } catch (e) { process.exit(1); }
            });
        }).on("error", () => process.exit(1));
    ' "$URL" "$LAG" 2>/dev/null) || SH=""

    if [ -n "$SH" ]; then
        export START_HEIGHT="$SH"
        echo "[ario-trustless] Auto-set START_HEIGHT=$SH (upstream height - $LAG)"
    else
        echo "[ario-trustless] WARN: could not auto-detect height from $URL; falling back to default 0 (full-chain index)"
    fi
fi

exec /bin/sh /app/docker-entrypoint.sh "$@"
