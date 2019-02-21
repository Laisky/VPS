# docker build . -t ppcelery/cloudflared
# docker push ppcelery/cloudflared

# you may need to disable systemd-recolverd
# sudo systemctl stop systemd-resolved
# sudo systemctl disable systemd-resolved

FROM golang:1.11.5-alpine3.9 as gobuild

# http proxy
ENV HTTP_PROXY=http://172.16.4.26:17777
ENV HTTPS_PROXY=http://172.16.4.26:17777


RUN apk update; \
    apk add git gcc build-base; \
    go get -v github.com/cloudflare/cloudflared/cmd/cloudflared

WORKDIR /go/src/github.com/cloudflare/cloudflared/cmd/cloudflared

RUN go build --ldflags '-extldflags "-static"' ./


FROM alpine:3.9

ENV DNS1 1.1.1.1
ENV DNS2 1.0.0.1

# RUN adduser -S cloudflared

COPY --from=gobuild /etc/ssl/certs /etc/ssl/certs
COPY --from=gobuild /go/src/github.com/cloudflare/cloudflared/cmd/cloudflared/cloudflared /usr/local/bin/cloudflared
# HEALTHCHECK --interval=5s --timeout=3s --start-period=5s CMD nslookup -po=53 cloudflare.com 127.0.0.1 || exit 1

# USER cloudflared

CMD ["/bin/sh", "-c", "/usr/local/bin/cloudflared proxy-dns --address 0.0.0.0 --port 53 --upstream https://${DNS1}/.well-known/dns-query --upstream https://${DNS2}/.well-known/dns-query"]
