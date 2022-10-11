FROM golang:1.19.2-bullseye AS build

RUN go install tailscale.com/cmd/derper@latest

FROM debian:bullseye

WORKDIR /app
COPY --from=build /go/bin/derper /app/derper

ENV ADDR=b1.laisky.com
ENV PORT=443

WORKDIR /root
ENTRYPOINT echo $ADDR && /app/derper -c=$HOME/derper.conf -hostname=$ADDR -a :$PORT -stun
