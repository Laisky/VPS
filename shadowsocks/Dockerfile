FROM golang:1.12.5-alpine3.9 AS gobin
RUN apk update && apk upgrade && \
    apk add --no-cache bash git ca-certificates && \
    update-ca-certificates

RUN go get github.com/shadowsocks/shadowsocks-go/cmd/shadowsocks-server

# ---------------------------------

FROM alpine:3.9
COPY --from=gobin /go/bin/shadowsocks-server  shadowsocks-server
COPY --from=gobin /etc/ssl/certs /etc/ssl/certs

ENTRYPOINT ./shadowsocks-server -c /opt/configs/shadowsocks/config.json


