FROM golang:1.17.2-buster

RUN go install tailscale.com/cmd/derper@main

ENV ADDR=b1.laisky.com

RUN echo $ADDR

CMD derper -hostname=$ADDR -a :443 -stun
