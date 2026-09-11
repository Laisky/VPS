# PostgreSQL image

This image keeps the database on PostgreSQL major version 17 and pins the current compatible minor
release. Minor upgrades within 17 do not require `pg_upgrade` or dump/restore, but production still
requires a verified backup and the release-note preflight below.

## Observability defaults

The image enables low-overhead, parameter-safe diagnostics for new and existing data volumes:

- `pg_stat_statements` with query IDs, 10,000 entries, top-level tracking, persistence, and planning
  and utility statement tracking disabled;
- relation I/O timing after `pg_test_timing` measured sub-microsecond clock overhead on `b1`;
- complete logging for statements over one second and a 5% sample above 250 ms;
- parameter values omitted from statement and error logs;
- lock waits, checkpoints, temporary files over 10 MB, and autovacuum operations over one second;
- a 4 KiB activity query buffer and query IDs in the PostgreSQL log prefix; and
- a Docker health check based on `pg_isready`.

`auto_explain` is intentionally not globally preloaded. Enable it only for a bounded incident window
on a controlled role or session, with parameter logging and per-node timing disabled unless they are
explicitly required.

## Build and test

```sh
chmod +x postgre/*.sh
POSTGRES_TEST_IMAGE=ppcelery/postgres:17.11-bookworm ./postgre/test-image.sh
```

The test builds the image, waits for the real health check, verifies the server settings and bundled
extensions, creates a fixture query, and proves that `pg_stat_statements` captured buffer activity.
It then initializes a real 17.6 data volume, writes a checksum fixture, starts 17.11 over that same
volume, and verifies the data and statement statistics. Temporary containers and volumes are removed
automatically.

## Production upgrade from 17.6

1. Verify a current logical and storage-level backup before replacing the container.
2. Inventory installed extensions and logical decoding slots:

   ```sql
   SELECT extname, extversion FROM pg_extension ORDER BY extname;
   SELECT slot_name, plugin, slot_type, active FROM pg_replication_slots ORDER BY slot_name;
   ```

3. If a non-core logical decoding plugin is used, add it to PostgreSQL 17.11's
   `output_plugin_libraries` allowlist before serving decoding traffic.
4. Review the PostgreSQL 17.11 release notes for `btree_gist`, `ltree`, and deprecated `pgcrypto`
   data. Perform the documented concurrent reindex or data cleanup when the inventory requires it.
5. Build and push `ppcelery/postgres:17.11-bookworm`, update the compose checkout, and recreate only
   the PostgreSQL service during a maintenance window. Do not delete or replace `PGDATA`.
6. Wait for the container health check, then enable the SQL view in each database that operators
   need to inspect. For One API:

   ```sh
   docker exec vps_postgre_1 enable-pg-stat-statements oneapi
   ```

7. Verify the runtime:

   ```sql
   SHOW server_version;
   SHOW shared_preload_libraries;
   SHOW compute_query_id;
   SHOW track_io_timing;
   SELECT extversion FROM pg_extension WHERE extname = 'pg_stat_statements';
   SELECT stats_reset, dealloc FROM pg_stat_statements_info;
   ```

8. Observe health, locks, checkpoints, autovacuum, and the top statements through at least one
   application steady-state interval before closing the maintenance window.

Do not grant application credentials access to unrestricted statement text. Operators should use a
separate monitoring role with `pg_read_all_stats`, and exported dashboards should retain normalized
query IDs and bounded labels rather than raw parameters.

The extension versions bundled here remain unchanged during the PostgreSQL minor upgrade. Upgrading
pgvector, VectorChord, VectorChord-bm25, or pg_tokenizer requires its own compatibility matrix,
`ALTER EXTENSION ... UPDATE` plan, and index validation.

## References

- [PostgreSQL minor-version policy](https://www.postgresql.org/support/versioning/)
- [PostgreSQL 17.11 release notes](https://www.postgresql.org/docs/17/release-17-11.html)
- [`pg_stat_statements` configuration](https://www.postgresql.org/docs/17/pgstatstatements.html)
- [Runtime statistics and I/O timing](https://www.postgresql.org/docs/17/runtime-config-statistics.html)
