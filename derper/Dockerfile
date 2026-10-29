# Build from the VPS repository root with -f derper/Dockerfile.
FROM golang:1.27.1-bookworm@sha256:8d48e12ec56735e9358640898b9d9b9fcca110612ed8a5567438c0a1baa24e66 AS build

ENV GOTOOLCHAIN=local GOMAXPROCS=1 GOMEMLIMIT=512MiB
RUN --mount=type=cache,id=vps-derper-mod-go127,target=/go/pkg/mod go mod download -json tailscale.com@v1.102.5 > /tmp/derper-module.json \
    && grep -F '"Sum": "h1:2jK9VxQU4Vq/tyR7f2U2NqINxU0pV7R14TDBFsfguHE="' /tmp/derper-module.json \
    && cp -a /go/pkg/mod/tailscale.com@v1.102.5 /src \
    && chmod -R u+w /src
WORKDIR /src
COPY derper/patches/cert.go cmd/derper/cert.go
COPY derper/patches/cert_reload_test.go cmd/derper/cert_reload_test.go
COPY derper/patches/cert_cache_baseline_test.go cmd/derper/cert_cache_baseline_test.go
RUN --mount=type=cache,id=vps-derper-mod-go127,target=/go/pkg/mod \
    --mount=type=cache,id=vps-derper-build-go127,target=/root/.cache/go-build \
    go test -p 1 ./cmd/derper \
    && CGO_ENABLED=0 go build -p 1 -trimpath \
      -ldflags="-s -w -X tailscale.com/version.longStamp=1.102.5-vps-cert-reload.2 -X tailscale.com/version.shortStamp=1.102.5 -X tailscale.com/version.gitCommitStamp=5fb2a81b065b0a0bbbfc67ab20a0d9c6a1108115" \
      -o /out/derper ./cmd/derper

FROM debian:bookworm@sha256:2c037a04925515fdd6ea85ea14a682d0e79931f5e9f5d07b6dbfc6ba12f9e858
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*
LABEL org.opencontainers.image.title="VPS DERPer" \
      org.opencontainers.image.version="1.102.5-vps-cert-reload.2" \
      org.opencontainers.image.source="https://github.com/Laisky/VPS" \
      io.laisky.derper.upstream-revision="5fb2a81b065b0a0bbbfc67ab20a0d9c6a1108115" \
      io.laisky.derper.go-version="1.27.1"
WORKDIR /app
COPY --from=build /out/derper /app/derper
COPY derper/patches/LICENSE /usr/share/doc/derper/LICENSE
ENV ADDR=b1.laisky.com PORT=443
WORKDIR /root
ENTRYPOINT ["sh", "-c", "exec /app/derper -c=$HOME/derper.conf --hostname=$ADDR -a :$PORT -stun"]
