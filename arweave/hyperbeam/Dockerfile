# db . -f ./arweave/hyperbeam/Dockerfile -t ppcelery/hyperbeam
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    git \
    pkg-config \
    ncurses-dev \
    libssl-dev \
    sudo \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Force Git to use HTTP/1.1
RUN git config --system http.version HTTP/1.1

# Install Erlang with shallow clone
RUN git clone --depth 1 --branch maint-27 https://github.com/erlang/otp.git && \
    cd otp && \
    ./configure --without-wx --without-debugger --without-observer --without-et && \
    make -j"$(nproc)" && \
    make install && \
    cd .. && \
    rm -rf otp

# Verify Erlang installation
RUN erl -eval 'erlang:display(erlang:system_info(otp_release)), halt().'

# Install Rebar3
RUN git clone https://github.com/erlang/rebar3.git && \
    cd rebar3 && \
    ./bootstrap && \
    mv rebar3 /usr/local/bin/ && \
    cd .. && \
    rm -rf rebar3

RUN rebar3 --version

# Install Node.js
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/*

RUN node -v && npm -v

# Install Rust
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --default-toolchain stable
ENV PATH="/root/.cargo/bin:${PATH}"

RUN rustc --version && cargo --version

# Install HyperBEAM
WORKDIR /app
RUN git clone https://github.com/permaweb/HyperBEAM && \
    cd HyperBEAM && \
    rebar3 compile

WORKDIR /app/HyperBEAM
CMD ["rebar3", "shell"]
