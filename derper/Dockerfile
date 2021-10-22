FROM golang:1.17.2-buster

RUN go install tailscale.com/cmd/derper@main

ENV ADDR=b1.laisky.com
ENV PORT=443

<<<<<<< HEAD
RUN echo $ADDR

CMD derper -hostname=$ADDR -a :443 -stun
=======
WORKDIR /root
ENTRYPOINT echo $ADDR && derper -c=$HOME/derper.conf -hostname=$ADDR -a :$PORT -stun
>>>>>>> 4abfa4a6ae6b89f82acfa9fcbe7c4a24fb340dee
