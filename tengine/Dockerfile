# db ./tengine -t ppcelery/tengine:2.3.3
FROM debian:bullseye

RUN apt-get update \
    && apt-get install -y --no-install-recommends g++ make gcc git \
    build-essential ca-certificates curl wget \
    libpcre3-dev libssl-dev zlib1g-dev \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*


WORKDIR /app

RUN wget https://s3.laisky.com/public/tengine-2.3.3.tar.gz \
    && tar -xzf tengine-2.3.3.tar.gz

RUN cd tengine-2.3.3 \
    && ./configure \
    && make \
    && make install

RUN rm -rf tengine-2.3.3.tar.gz tengine-2.3.3

ADD nginx.conf /etc/nginx/nginx.conf
ADD mime.types /etc/nginx/mime.types

ENTRYPOINT [ "/usr/local/nginx/sbin/nginx", "-g", "daemon off;" ]
