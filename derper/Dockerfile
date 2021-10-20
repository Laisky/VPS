FROM golang:1.17.2-buster

RUN go install tailscale.com/cmd/derper@main

ENV ADDR=b1.laisky.com
ENV PORT=12987

WORKDIR /root
ENTRYPOINT echo $ADDR && derper -c=/root/derper.conf -hostname=$ADDR -a :$PORT -stun
