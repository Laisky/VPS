#!/usr/bin/env sh
set -eu

run_postgres() {
  set -- postgres \
    -c "shared_preload_libraries=vchord,vchord_bm25,vector,pg_tokenizer,pg_stat_statements" \
    -c "compute_query_id=on" \
    -c "pg_stat_statements.max=10000" \
    -c "pg_stat_statements.track=top" \
    -c "pg_stat_statements.track_utility=off" \
    -c "pg_stat_statements.track_planning=off" \
    -c "pg_stat_statements.save=on" \
    -c "track_io_timing=on" \
    -c "track_activity_query_size=4096" \
    -c "log_min_duration_statement=1000" \
    -c "log_min_duration_sample=250" \
    -c "log_statement_sample_rate=0.05" \
    -c "log_parameter_max_length=0" \
    -c "log_parameter_max_length_on_error=0" \
    -c "log_lock_waits=on" \
    -c "deadlock_timeout=1s" \
    -c "log_temp_files=10MB" \
    -c "log_autovacuum_min_duration=1000" \
    -c "log_checkpoints=on" \
    -c "log_line_prefix=%m [%p] %q%u@%d/%a qid=%Q " \
    "$@"

  exec /usr/local/bin/docker-entrypoint.sh "$@"
}

# Apply conservative cluster-wide observability defaults to both new and existing data volumes.
# Operator-supplied postgres arguments remain last and can override any default deliberately.
if [ "${1:-}" = "postgres" ]; then
  shift
  run_postgres "$@"
elif [ "${1#-}" != "$1" ]; then
  run_postgres "$@"
fi

exec /usr/local/bin/docker-entrypoint.sh "$@"
