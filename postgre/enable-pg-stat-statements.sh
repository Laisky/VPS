#!/usr/bin/env bash
set -Eeuo pipefail

pg_user="${POSTGRES_USER:-postgres}"
default_database="${POSTGRES_DB:-$pg_user}"

if (( $# == 0 )); then
  databases=("$default_database" "template1")
else
  databases=("$@")
fi

preloaded="$(psql --username "$pg_user" --dbname "$default_database" --tuples-only --no-align \
  --set ON_ERROR_STOP=1 --command "SHOW shared_preload_libraries")"
preloaded="${preloaded//[[:space:]]/}"
if [[ ",$preloaded," != *,pg_stat_statements,* ]]; then
  echo "pg_stat_statements is not present in shared_preload_libraries" >&2
  exit 1
fi

for database in "${databases[@]}"; do
  psql --username "$pg_user" --dbname "$database" --set ON_ERROR_STOP=1 \
    --command "CREATE EXTENSION IF NOT EXISTS pg_stat_statements"
done
