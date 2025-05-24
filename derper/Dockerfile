# db . -f ./derper/Dockerfile -t ppcelery/derper:latest
FROM golang:1.24.3-bookworm AS build

# ADD https://www.random.org/strings/?num=1&len=16&digits=on&upperalpha=on&loweralpha=on&unique=on&format=plain /tmp/random
RUN go install tailscale.com/cmd/derper@latest

FROM debian:bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates haveged \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=build /go/bin/derper /app/derper

ENV ADDR=b1.laisky.com
ENV PORT=443

WORKDIR /root
ENTRYPOINT ["sh", "-c", "echo $ADDR && /app/derper -c=$HOME/derper.conf --hostname=$ADDR -a :$PORT -stun"]
