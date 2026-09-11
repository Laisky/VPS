#!/usr/bin/env bash
set -Eeuo pipefail

image="${1:-${POSTGRES_TEST_IMAGE:-vps-postgres:observability-test}}"
suffix="$$-$RANDOM"
old_container="vps-postgres-17-6-$suffix"
new_container="vps-postgres-17-11-$suffix"
volume="vps-postgres-minor-upgrade-$suffix"

cleanup() {
  docker rm -f "$old_container" "$new_container" >/dev/null 2>&1 || true
  docker volume rm "$volume" >/dev/null 2>&1 || true
}
trap cleanup EXIT

wait_for_server() {
  local container="$1"
  local require_init_complete="${2:-false}"

  for _ in $(seq 1 90); do
    if [[ "$require_init_complete" == "false" ]] || \
      docker logs "$container" 2>&1 | grep -q 'PostgreSQL init process complete'; then
      if docker exec "$container" pg_isready --username postgres --dbname upgrade_test \
        >/dev/null 2>&1; then
        return
      fi
    fi
    if [[ "$(docker inspect --format '{{.State.Running}}' "$container")" != "true" ]]; then
      docker logs "$container"
      return 1
    fi
    sleep 1
  done

  docker logs "$container"
  return 1
}

docker image inspect "$image" >/dev/null
docker volume create "$volume" >/dev/null

docker run --detach --name "$old_container" \
  --env POSTGRES_PASSWORD=minor-upgrade-test \
  --env POSTGRES_DB=upgrade_test \
  --volume "$volume:/var/lib/postgresql/data" \
  postgres:17.6-bookworm >/dev/null
wait_for_server "$old_container" true

docker exec "$old_container" psql --username postgres --dbname upgrade_test \
  --set ON_ERROR_STOP=1 <<'SQL'
CREATE TABLE upgrade_probe (id bigint PRIMARY KEY, payload text NOT NULL);
INSERT INTO upgrade_probe
SELECT value, md5(value::text) FROM generate_series(1, 1000) AS value;
SQL

docker stop --time 90 "$old_container" >/dev/null
docker rm "$old_container" >/dev/null

docker run --detach --name "$new_container" \
  --env POSTGRES_PASSWORD=minor-upgrade-test \
  --env POSTGRES_DB=upgrade_test \
  --volume "$volume:/var/lib/postgresql/data" \
  "$image" >/dev/null
wait_for_server "$new_container"

docker exec "$new_container" enable-pg-stat-statements upgrade_test >/dev/null
docker exec "$new_container" psql --username postgres --dbname upgrade_test \
  --set ON_ERROR_STOP=1 <<'SQL'
DO $$
BEGIN
  IF current_setting('server_version') !~ '^17[.]11([.]|$)' THEN
    RAISE EXCEPTION 'unexpected PostgreSQL version after upgrade: %', current_setting('server_version');
  END IF;
  IF (SELECT count(*) FROM upgrade_probe) <> 1000 THEN
    RAISE EXCEPTION 'upgrade fixture row count changed';
  END IF;
  IF (SELECT sum(id) FROM upgrade_probe) <> 500500 THEN
    RAISE EXCEPTION 'upgrade fixture checksum changed';
  END IF;
  IF (SELECT count(*) FROM pg_extension WHERE extname = 'pg_stat_statements') <> 1 THEN
    RAISE EXCEPTION 'pg_stat_statements was not enabled on the existing database';
  END IF;
END
$$;

SELECT count(*) FROM upgrade_probe WHERE id > 750;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_stat_statements
    WHERE query LIKE '%upgrade_probe%'
      AND calls > 0
  ) THEN
    RAISE EXCEPTION 'upgraded cluster queries were not captured';
  END IF;
END
$$;
SQL

echo "PostgreSQL 17.6 to 17.11 data-volume regression passed"
