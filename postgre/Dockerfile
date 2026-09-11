# docker build . -f postgre/Dockerfile -t ppcelery/postgres:latest
# PostgreSQL minor releases are cumulative security and correctness updates. Keep the major at 17
# for on-disk compatibility, and assert the intended minor so package installs cannot drift it.
FROM postgres:17.11-bookworm

ARG PG_MAJOR=17

# =====================================
# Install build dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    build-essential wget \
    postgresql-server-dev-${PG_MAJOR}=${PG_VERSION} \
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
# Install PostGIS. PostgreSQL 17's contrib modules are provided by the pinned server package.
RUN apt-get install -y --no-install-recommends \
    postgresql-${PG_MAJOR}-postgis-3 \
    && postgres --version | grep -Eq 'PostgreSQL\) 17\.11([.]| |$)' \
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
RUN apt-get remove -y build-essential postgresql-server-dev-${PG_MAJOR} git \
    && apt-get autoremove -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf /pgvector /tmp/*.deb

# Apply observability settings through server arguments so existing PGDATA volumes receive them.
# New databases get the SQL view automatically; existing databases use the same idempotent helper
# explicitly after the upgraded server is healthy.
COPY postgre/observability-entrypoint.sh /usr/local/bin/observability-entrypoint
COPY postgre/enable-pg-stat-statements.sh /usr/local/bin/enable-pg-stat-statements
RUN chmod 0755 /usr/local/bin/observability-entrypoint /usr/local/bin/enable-pg-stat-statements \
    && ln -s /usr/local/bin/enable-pg-stat-statements \
        /docker-entrypoint-initdb.d/20-enable-pg-stat-statements.sh

ENTRYPOINT ["/usr/local/bin/observability-entrypoint"]
CMD ["postgres"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=5 \
    CMD pg_isready --username "${POSTGRES_USER:-postgres}" \
        --dbname "${POSTGRES_DB:-${POSTGRES_USER:-postgres}}" || exit 1

# Expose the default PostgreSQL port
EXPOSE 5432
