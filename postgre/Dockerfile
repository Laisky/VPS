# docker build . -f postgre/Dockerfile  -t ppcelery/postgres:latest
FROM postgres:17-bullseye

# Install build dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        postgresql-server-dev-17 \
        git \
        ca-certificates

# Build and install pgvector
# pgvector is an extension for PostgreSQL that provides vector data types and functions for machine learning applications.
RUN git clone --branch v0.8.0 https://github.com/pgvector/pgvector.git \
    && cd pgvector \
    && make \
    && make install

# Install extension: ctext, PostGIS
# ctext is a case-insensitive text search extension.
# PostGIS adds support for geographic objects to the PostgreSQL database.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        postgresql-contrib-17 \
        postgresql-17-postgis-3 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

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
EXPOSE 5432
