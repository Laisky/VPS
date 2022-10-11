FROM golang:1.19.2-bullseye

RUN go install tailscale.com/cmd/derper@latest

ENV ADDR=b1.laisky.com
ENV PORT=443

WORKDIR /root
ENTRYPOINT echo $ADDR && derper -c=$HOME/derper.conf -hostname=$ADDR -a :$PORT -stun
