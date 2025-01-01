# db . -f ./glider/Dockerfile -t ppcelery/glider:latest
FROM golang:1.23.4-bullseye AS builder

RUN go install github.com/nadoo/glider@latest

FROM debian:bullseye

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates haveged \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /go/bin/glider /app/glider

ENTRYPOINT ["/app/glider"]
