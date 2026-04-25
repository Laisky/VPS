# syntax=docker/dockerfile:1.7
# Minimal multi-stage Dockerfile for a HyperBEAM (AO-Core) node.
# Upstream: https://github.com/permaweb/HyperBEAM
#
# Improvements over the upstream Dockerfile:
#   - Uses official `erlang:27` image (no source-build of OTP).
#   - Installs Rust via rustup (minimal profile) instead of compiling from source.
#   - Builds a relx release (`rebar3 release`) instead of leaving a dev shell.
#   - Multi-stage: ~200-400 MB runtime image vs >5 GB single-stage.
#   - Runs as non-root, persists wallet/cache to /data, healthcheck on /~meta@1.0/info.
#
# Build:   docker build -t hyperbeam:local arweave/hyperbeam
# Run:     docker run --rm -p 8734:8734 -v hb-data:/data hyperbeam:local
# Verify:  curl -fsS http://localhost:8734/~meta@1.0/info

ARG HYPERBEAM_REF=main
ARG ERLANG_TAG=27

############################
#  Stage 1 - Build release #
############################
FROM erlang:${ERLANG_TAG} AS builder

ENV DEBIAN_FRONTEND=noninteractive \
    CARGO_HOME=/opt/cargo \
    RUSTUP_HOME=/opt/rustup \
    PATH=/opt/cargo/bin:${PATH}

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        cmake \
        git \
        pkg-config \
        ca-certificates \
        curl \
        libssl-dev \
        libncurses-dev \
    && rm -rf /var/lib/apt/lists/*

RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \
      | sh -s -- -y --profile minimal --default-toolchain stable

RUN curl -fsSL -o /usr/local/bin/rebar3 https://s3.amazonaws.com/rebar3/rebar3 \
    && chmod +x /usr/local/bin/rebar3

ARG HYPERBEAM_REF
WORKDIR /src
RUN git clone --depth 1 --branch "${HYPERBEAM_REF}" \
        https://github.com/permaweb/HyperBEAM.git hb \
    && git -C hb rev-parse HEAD > /src/REVISION

WORKDIR /src/hb
# Pre-seed config.flat so the relx overlay always finds it: upstream `main`
# ships `port: 10000`, `edge` doesn't ship it at all (release fails with enoent
# during the overlay copy step). Writing our own file works for both branches.
RUN printf 'port: 8734\n' > /src/hb/config.flat
RUN rebar3 release

############################
#  Stage 2 - Runtime       #
############################
FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive \
    HB_PORT=8734 \
    HB_KEY=/data/hyperbeam-key.json \
    HB_STORE=/data/store

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        libssl3 \
        libncurses6 \
        libtinfo6 \
        libstdc++6 \
        tini \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system --gid 10001 hb \
    && useradd --system --uid 10001 --gid hb --home-dir /data --shell /usr/sbin/nologin hb \
    && mkdir -p /data \
    && chown -R hb:hb /data

COPY --from=builder /src/hb/_build/default/rel/hb /opt/hb
COPY --from=builder /src/REVISION /opt/hb/REVISION

# config.flat (port: 8734) is already pre-seeded into the release by the
# builder stage. Operators can still override at runtime by mounting a custom
# config.flat over /opt/hb/config.flat.
RUN chown -R hb:hb /opt/hb

USER hb
WORKDIR /data
VOLUME ["/data"]
EXPOSE 8734

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${HB_PORT}/~meta@1.0/info" >/dev/null || exit 1

ENTRYPOINT ["/usr/bin/tini", "--", "/opt/hb/bin/hb"]
CMD ["foreground"]
