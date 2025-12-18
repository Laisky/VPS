#!/usr/bin/env bash
# Consolidated collation fix script.
# This script replaces the previous two scripts and is safe to run as a background
# helper during container startup. It keeps backward compatibility by accepting
# the same environment variables and exit semantics (skips quietly if unable to
# connect).

set -u

# Configuration
# Default timeouts (seconds)
WAIT_TIMEOUT=${FIX_COLLATION_WAIT_TIMEOUT:-120}

# Choose admin user: prefer POSTGRES_USER (recommended by official images),
# otherwise fall back to 'postgres'. This preserves backward compatibility.
PGUSER="${POSTGRES_USER:-postgres}"

log() { printf "%s\n" "[fix-collation-on-start] $*"; }

wait_for_postgres() {
  local elapsed=0
  while ! pg_isready -U "$PGUSER" > /dev/null 2>&1; do
    if [ $elapsed -ge $WAIT_TIMEOUT ]; then
      log "Timeout waiting for PostgreSQL to be ready. Skipping collation fix."
      return 1
    fi
    log "Waiting for PostgreSQL to be ready... ($elapsed/$WAIT_TIMEOUT)"
    sleep 2
    elapsed=$((elapsed+2))
  done
  return 0
}

check_user_connects() {
  # Returns 0 if PGUSER can run a trivial query, non-zero otherwise.
  if psql -U "$PGUSER" -Atc 'SELECT 1' > /dev/null 2>&1; then
    return 0
  fi
  return 1
}

main() {
  # Wait for readiness
  if ! wait_for_postgres; then
    return 0
  fi

  log "PostgreSQL is ready. Determining usable role for admin operations..."

  log "Refreshing collation version for template1 (if needed)..."
  psql -U "$PGUSER" -d postgres -c \
    "ALTER DATABASE template1 REFRESH COLLATION VERSION;" \
    || log "template1 collation refresh skipped or failed"

  # If chosen PGUSER doesn't work, try the other common env var (safe fallback)
  if ! check_user_connects; then
    if [ -n "${POSTGRES_USER:-}" ] && [ "$PGUSER" != "$POSTGRES_USER" ]; then
      log "PGUSER '$PGUSER' failed; trying POSTGRES_USER='$POSTGRES_USER'"
      PGUSER="$POSTGRES_USER"
    fi
  fi

  if ! check_user_connects; then
    log "Cannot connect as role '$PGUSER' — role may not exist. Skipping collation fix."
    return 0
  fi

  log "Checking for collation mismatches..."

  # List databases that allow connections, skip template DBs
  local DBS
  DBS=$(psql -U "$PGUSER" -Atc "SELECT datname FROM pg_database WHERE datallowconn AND datname NOT IN ('template0','template1');") || DBS=""

  for DB in $DBS; do
    # Determine a collation OID for the database default collation
    COLL_OID=$(psql -U "$PGUSER" -d "$DB" -Atc "SELECT (SELECT oid FROM pg_collation WHERE collname = (SELECT datcollate FROM pg_database WHERE datname = current_database()) LIMIT 1);" ) || true
    if [ -z "$COLL_OID" ]; then
      log "Could not determine collation OID for database: $DB, skipping."
      continue
    fi

    # Check mismatch using the found OID
    MISMATCH=$(psql -U "$PGUSER" -d "$DB" -Atc "SELECT 1 FROM pg_database WHERE datname = current_database() AND datcollversion IS DISTINCT FROM pg_collation_actual_version($COLL_OID);") || true
    if [ "$MISMATCH" = "1" ]; then
      log "Fixing collation version for database: $DB"
      psql -U "$PGUSER" -d "$DB" -c "ALTER DATABASE \"$DB\" REFRESH COLLATION VERSION;" || log "Failed to refresh collation for $DB"
    else
      log "No collation mismatch for database: $DB"
    fi
  done

  log "Collation version check complete."
  return 0
}

main "$@"
