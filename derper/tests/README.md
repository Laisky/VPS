# Disposable DERPer integration fixtures

Run on the development machine with Python 3, `cryptography`, Docker, and an
already available local Alpine image. No images are pulled. All certificate
authorities, leaf certificates, private keys, and DERP identities are generated
for the test and removed afterward. No production files are used.

```sh
python3 derper/tests/test_integration.py --mount-only
python3 derper/tests/test_integration.py --baseline-bin /path/to/unpatched/derper
python3 derper/tests/test_integration.py --image derper-candidate:local
```

The mount reproduction runs offline and demonstrates the original failure:
a single-file certificate bind retains the old inode after renewal changes a
`live` symlink, while a directory-tree bind follows the updated symlink.

The optional unpatched binary test expects fresh TLS handshakes to continue
serving the original certificate. The candidate image test instead expects
reload after the one-second throttle, and verifies existing connections remain
usable. Candidate tests also cover partial certificate/key updates, incorrect
hostname, expired and malformed certificates, recovery, client trust/SNI, and
same-container restart with persistent alias files. An optional rollout snippet
may be supplied separately to exercise a deployment-specific shell block and
read-only lineage mounts.

Docker fixtures use an immutable local image ID, a read-only root filesystem,
no capabilities, one CPU, 256 MiB memory, and bounded process counts. The mount
fixture uses `--network=none`; the TLS fixture publishes only to `127.0.0.1`.
Only the owned test containers and unique temporary fixture directories are
removed. The generated test private keys are readable by the container's
unprivileged UID; this does not prescribe production key permissions.

TLS tests mount only the generated lineage's live/archive directories read-only.
The sole writable bind is the disposable alias directory, so alias files survive
a same-container restart and idempotence is actually exercised.
These tests require directory-mounted certificate material for the candidate.
They intentionally do not suggest that in-process reload can repair a pinned
single-file mount. Invalid identity/key startup rejection and expired-last-good-certificate behavior
are covered by the Go unit tests in `patches/cert_reload_test.go`.


Renewal observability regressions assert fixed privacy-safe messages, one warning
per minute across repeated failures and bad/good flapping, one recovery signal
per logged failure, no extra healthy logs, and unchanged valid fallback during
concurrent handshakes. Runtime fixtures assert the actual Docker log contains
exactly one rejection warning and one recovery during rapid invalid updates.
These signals report reload attempts, not certificate public-chain trust.

For a source baseline, copy the pinned upstream module to a disposable directory,
copy patches/cert_cache_baseline_test.go into cmd/derper, then run from that
module root: /path/to/derper/tests/check_upstream_baseline.sh. A zero exit
means the exact expected renewal failure was observed. Run
go test -p 1 ./cmd/derper -run TestManualCertStartupValidityCompatibility
against both upstream and patched copies to check startup compatibility.
