# db . -t ppcelery/postgres:latest
FROM postgres:17.2-bullseye

# Install build dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        postgresql-server-dev-17 \
        git \
        ca-certificates

# Build and install pgvector
RUN git clone --branch v0.8.0 https://github.com/pgvector/pgvector.git \
    && cd pgvector \
    && make \
    && make install

# Cleanup
RUN apt-get remove -y build-essential postgresql-server-dev-17 git \
    && apt-get autoremove -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf /pgvector

# Add pgvector to shared_preload_libraries
RUN echo "shared_preload_libraries='vector'" >> /usr/share/postgresql/postgresql.conf.sample

# Expose the default PostgreSQL port
EXPOSE 5432
