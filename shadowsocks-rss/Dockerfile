FROM python:3.4.8-alpine3.7
RUN apk update && apk upgrade && \
    apk add --no-cache bash git ca-certificates && \
    update-ca-certificates

ADD https://s3.laisky.com/public/ssr.tar.gz /
RUN tar -xzf /ssr.tar.gz

ENTRYPOINT /usr/local/bin/python /shadowsocks/shadowsocks/server.py -c /opt/configs/shadowsocks-rss/config.json
