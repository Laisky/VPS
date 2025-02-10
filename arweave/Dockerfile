# Multi-stage Dockerfile to build and run an Arweave node

############
# Builder  #
############
FROM ubuntu:20.04 AS builder
ENV DEBIAN_FRONTEND=noninteractive

# Install required packages including ca-certificates
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        git \
        erlang \
        gcc \
        g++ \
        clang \
        cmake \
        make \
        libsqlite3-dev \
        wget \
        ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Install rebar3 (Erlang build tool) using curl to ensure proper binary download
RUN curl -Lo /usr/local/bin/rebar3 https://s3.amazonaws.com/rebar3/rebar3 && \
    chmod +x /usr/local/bin/rebar3

# Clone Arweave repository with submodules
WORKDIR /app
RUN git clone --recursive https://github.com/ArweaveTeam/arweave.git

# Build the Arweave node using rebar3 in prod profile.
WORKDIR /app/arweave
RUN rebar3 as prod tar

############
# Runtime  #
############
FROM ubuntu:20.04
ENV DEBIAN_FRONTEND=noninteractive

# Install runtime dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        erlang \
        libsqlite3-dev \
        ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Copy the built release from the builder stage
COPY --from=builder /app/arweave/_build/prod/rel/arweave /arweave

WORKDIR /arweave

# Expose needed port (adjust if necessary)
EXPOSE 1984

# Default command: start the Arweave node.
CMD ["./bin/start"]
