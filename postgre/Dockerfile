# docker build . -f postgre/Dockerfile  -t ppcelery/postgres:latest
#
# Should not upgrade the minor version of Postgres, because of https://x.com/gwenshap/status/1990942970682749183
FROM postgres:17.2-bookworm

ARG PG_MAJOR=17

# =====================================
# Install build dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    build-essential wget \
    postgresql-server-dev-17 \
    git \
    ca-certificates

# -------------------------------------
# Build and install pgvector
# pgvector is an extension for PostgreSQL that provides vector data types and functions for machine learning applications.
RUN git clone --branch v0.8.1 https://github.com/pgvector/pgvector.git \
    && cd pgvector \
    && make \
    && make install

# -------------------------------------
# Install extension: ctext, PostGIS
# ctext is a case-insensitive text search extension.
# PostGIS adds support for geographic objects to the PostgreSQL database.
RUN apt-get install -y --no-install-recommends \
    postgresql-contrib-17 \
    postgresql-17-postgis-3 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# -------------------------------------
# Install vchord_bm25

ARG VCHORDBM25=0.2.2
ARG PGTOKENIZER=0.1.1
ARG VCHORD=0.5.3
# ARG PGVECTOR=0.8.1

RUN wget https://github.com/tensorchord/VectorChord-bm25/releases/download/${VCHORDBM25}/postgresql-${PG_MAJOR}-vchord-bm25_${VCHORDBM25}-1_$(dpkg --print-architecture).deb -P /tmp && \
    wget https://github.com/tensorchord/pg_tokenizer.rs/releases/download/${PGTOKENIZER}/postgresql-${PG_MAJOR}-pg-tokenizer_${PGTOKENIZER}-1_$(dpkg --print-architecture).deb -P /tmp && \
    wget https://github.com/tensorchord/VectorChord/releases/download/${VCHORD}/postgresql-${PG_MAJOR}-vchord_${VCHORD}-1_$(dpkg --print-architecture).deb -P /tmp && \
    # apt-get install -y postgresql-${PG_MAJOR}-pgvector=${PGVECTOR}-* && \
    apt-get install -y /tmp/postgresql-${PG_MAJOR}-vchord_${VCHORD}-1_$(dpkg --print-architecture).deb && \
    apt-get install -y /tmp/postgresql-${PG_MAJOR}-pg-tokenizer_${PGTOKENIZER}-1_$(dpkg --print-architecture).deb && \
    apt-get install -y /tmp/postgresql-${PG_MAJOR}-vchord-bm25_${VCHORDBM25}-1_$(dpkg --print-architecture).deb

# =====================================
# Cleanup
RUN apt-get remove -y build-essential postgresql-server-dev-17 git \
    && apt-get autoremove -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf /pgvector


# Add pgvector to shared_preload_libraries
RUN echo "shared_preload_libraries='vchord,vchord_bm25,vector,pg_tokenizer'" >> /usr/share/postgresql/postgresql.conf.sample



# Copy collation fix script for post-startup
COPY ./postgre/fix-collation-on-start.sh /usr/local/bin/fix-collation-on-start.sh
RUN chmod +x /usr/local/bin/fix-collation-on-start.sh

# Set default command to run Postgres in the foreground and the collation fix in the background
CMD ["bash", "-c", "/usr/local/bin/fix-collation-on-start.sh & exec docker-entrypoint.sh postgres"]

# Expose the default PostgreSQL port
EXPOSE 5432
