#!/bin/bash
# fix-collation.sh: Fix collation version mismatches for all databases in a running PostgreSQL instance.
# Usage: Intended to be run after PostgreSQL is ready and accepting connections.

set -e

# Wait for PostgreSQL to be ready
until pg_isready -U "$POSTGRES_USER" -h "localhost" > /dev/null 2>&1; do
  echo "Waiting for PostgreSQL to be ready..."
  sleep 2
done

# Always use 'postgres' user for admin tasks during init
PGUSER=postgres

# Wait for PostgreSQL to be ready, with a timeout (max 60s)
timeout=60
elapsed=0
while ! pg_isready -U "$PGUSER" > /dev/null 2>&1; do
  if [ $elapsed -ge $timeout ]; then
    echo "Timeout waiting for PostgreSQL to be ready."
    exit 1
  fi
  echo "Waiting for PostgreSQL to be ready... ($elapsed/$timeout)"
  sleep 2
  elapsed=$((elapsed+2))
done

echo "PostgreSQL is ready. Checking for collation mismatches..."

# List all databases
DBS=$(psql -U "$POSTGRES_USER" -h "localhost" -Atc "SELECT datname FROM pg_database WHERE datallowconn AND datname NOT IN ('template0','template1');")

# List all databases
DBS=$(psql -U "$PGUSER" -Atc "SELECT datname FROM pg_database WHERE datallowconn AND datname NOT IN ('template0','template1');")

for DB in $DBS; do
  # Check for collation version mismatch
  MISMATCH=$(psql -U "$POSTGRES_USER" -h "localhost" -d "$DB" -Atc "SELECT 1 FROM pg_database WHERE datname = current_database() AND datcollversion IS DISTINCT FROM pg_collation_actual_version('default');")
  if [ "$MISMATCH" = "1" ]; then
    echo "Fixing collation version for database: $DB"
    psql -U "$POSTGRES_USER" -h "localhost" -d "$DB" -c "ALTER DATABASE \"$DB\" REFRESH COLLATION VERSION;"
  else
    echo "No collation mismatch for database: $DB"
  fi
done
done
for DB in $DBS; do
  # Check for collation version mismatch
  MISMATCH=$(psql -U "$PGUSER" -d "$DB" -Atc "SELECT 1 FROM pg_database WHERE datname = current_database() AND datcollversion IS DISTINCT FROM pg_collation_actual_version('default');")
  if [ "$MISMATCH" = "1" ]; then
    echo "Fixing collation version for database: $DB"
    psql -U "$PGUSER" -d "$DB" -c "ALTER DATABASE \"$DB\" REFRESH COLLATION VERSION;"
  else
    echo "No collation mismatch for database: $DB"
  fi
done

echo "Collation version check complete."
