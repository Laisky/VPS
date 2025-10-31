#!/bin/bash
# fix-collation-on-start.sh: Run collation fix after PostgreSQL is fully up (not during initdb)
# Place this script in the image and run it as a background process or as a custom CMD/ENTRYPOINT.

set -e

PGUSER=postgres
# Wait for PostgreSQL to be ready (max 120s)
timeout=120
elapsed=0
while ! pg_isready -U "$PGUSER" > /dev/null 2>&1; do
  if [ $elapsed -ge $timeout ]; then
    echo "Timeout waiting for PostgreSQL to be ready. Skipping collation fix."
    exit 0
  fi
  echo "[fix-collation-on-start] Waiting for PostgreSQL to be ready... ($elapsed/$timeout)"
  sleep 2
  elapsed=$((elapsed+2))
done

echo "[fix-collation-on-start] PostgreSQL is ready. Checking for collation mismatches..."
DBS=$(psql -U "$PGUSER" -Atc "SELECT datname FROM pg_database WHERE datallowconn AND datname NOT IN ('template0','template1');")
for DB in $DBS; do
  # Get the OID of the default collation for this database
  COLL_OID=$(psql -U "$PGUSER" -d "$DB" -Atc "SELECT c.oid FROM pg_collation c JOIN pg_database d ON c.collname = d.datcollate AND c.collcollate = d.datcollate AND c.collctype = d.datctype WHERE d.datname = current_database() LIMIT 1;")
  if [ -z "$COLL_OID" ]; then
    echo "[fix-collation-on-start] Could not determine collation OID for database: $DB, skipping."
    continue
  fi
  # Check for collation version mismatch
  MISMATCH=$(psql -U "$PGUSER" -d "$DB" -Atc "SELECT 1 FROM pg_database WHERE datname = current_database() AND datcollversion IS DISTINCT FROM pg_collation_actual_version($COLL_OID);")
  if [ "$MISMATCH" = "1" ]; then
    echo "[fix-collation-on-start] Fixing collation version for database: $DB"
    psql -U "$PGUSER" -d "$DB" -c "ALTER DATABASE \"$DB\" REFRESH COLLATION VERSION;"
  else
    echo "[fix-collation-on-start] No collation mismatch for database: $DB"
  fi
done

echo "[fix-collation-on-start] Collation version check complete."
