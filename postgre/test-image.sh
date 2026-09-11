#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
image="${POSTGRES_TEST_IMAGE:-vps-postgres:observability-test}"
container="vps-postgres-observability-test-$$"

cleanup() {
  docker rm -f "$container" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker build --file "$repo_root/postgre/Dockerfile" --tag "$image" "$repo_root"
docker run --detach --name "$container" \
  --env POSTGRES_PASSWORD=observability-test \
  --env POSTGRES_DB=observability_test \
  "$image" >/dev/null

for _ in $(seq 1 90); do
  health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}missing{{end}}' "$container")"
  if [[ "$health" == "healthy" ]]; then
    break
  fi
  if [[ "$health" == "unhealthy" ]]; then
    docker logs "$container"
    exit 1
  fi
  sleep 1
done

[[ "$(docker inspect --format '{{.State.Health.Status}}' "$container")" == "healthy" ]]

docker exec "$container" psql --username postgres --dbname observability_test \
  --set ON_ERROR_STOP=1 --tuples-only --no-align <<'SQL'
DO $$
BEGIN
  IF current_setting('server_version') !~ '^17[.]11([.]|$)' THEN
    RAISE EXCEPTION 'unexpected PostgreSQL version: %', current_setting('server_version');
  END IF;
  IF position('pg_stat_statements' IN current_setting('shared_preload_libraries')) = 0 THEN
    RAISE EXCEPTION 'pg_stat_statements is not preloaded';
  END IF;
  IF current_setting('compute_query_id') <> 'on' THEN
    RAISE EXCEPTION 'compute_query_id must be on';
  END IF;
  IF current_setting('track_io_timing') <> 'on' THEN
    RAISE EXCEPTION 'track_io_timing must be on';
  END IF;
  IF current_setting('pg_stat_statements.track') <> 'top' THEN
    RAISE EXCEPTION 'pg_stat_statements.track must be top';
  END IF;
  IF current_setting('pg_stat_statements.track_planning') <> 'off' THEN
    RAISE EXCEPTION 'planning statistics must remain off by default';
  END IF;
  IF current_setting('pg_stat_statements.track_utility') <> 'off' THEN
    RAISE EXCEPTION 'utility statement tracking must remain off to avoid retaining literals';
  END IF;
  IF current_setting('log_parameter_max_length') <> '0' THEN
    RAISE EXCEPTION 'statement parameter logging must be disabled';
  END IF;
END
$$;

DO $$
BEGIN
  IF (SELECT count(*) FROM pg_extension WHERE extname = 'pg_stat_statements') <> 1 THEN
    RAISE EXCEPTION 'pg_stat_statements extension was not created';
  END IF;
END
$$;

CREATE TABLE observability_probe (id bigint PRIMARY KEY, payload text NOT NULL);
INSERT INTO observability_probe
SELECT value, repeat('x', 64) FROM generate_series(1, 1000) AS value;
SELECT count(*) FROM observability_probe WHERE id > 500;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_stat_statements
    WHERE query LIKE '%observability_probe%'
      AND calls > 0
      AND shared_blks_hit + shared_blks_read > 0
  ) THEN
    RAISE EXCEPTION 'fixture query was not captured with buffer activity';
  END IF;
END
$$;

CREATE EXTENSION vector;
CREATE EXTENSION vchord;
CREATE EXTENSION pg_tokenizer;
CREATE EXTENSION vchord_bm25;
CREATE EXTENSION postgis;

DO $$
BEGIN
  IF (
    SELECT count(*)
    FROM pg_extension
    WHERE extname IN ('vector', 'vchord', 'vchord_bm25', 'pg_tokenizer', 'postgis')
  ) <> 5 THEN
    RAISE EXCEPTION 'one or more bundled extensions could not be installed';
  END IF;
  IF (
    SELECT count(*)
    FROM pg_extension
    WHERE (extname, extversion) IN (
      ('vector', '0.8.1'),
      ('vchord', '0.5.3'),
      ('vchord_bm25', '0.2.2'),
      ('pg_tokenizer', '0.1.1')
    )
  ) <> 4 THEN
    RAISE EXCEPTION 'bundled vector extension versions do not match the compatibility set';
  END IF;
END
$$;
SQL

echo "PostgreSQL image observability contract passed"
"$repo_root/postgre/test-minor-upgrade.sh" "$image"
