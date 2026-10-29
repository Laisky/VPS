#!/bin/sh
# Run inside a disposable, unpatched upstream source copy containing the baseline test.
set -eu
log=$(mktemp)
trap 'rm -f -- "$log"' EXIT HUP INT TERM
set +e
GOMAXPROCS=1 GOMEMLIMIT=512MiB GOTOOLCHAIN=local go test -p 1 ./cmd/derper -run '^TestManualCertReloadBaseline$' -count=1 >"$log" 2>&1
status=$?
set -e
cat "$log"
if [ "$status" -eq 1 ] && grep -Fq 'after valid on-disk renewal got certificate serial 1; want 2' "$log"; then
    echo 'Expected upstream renewal failure confirmed'
    exit 0
fi
echo 'Baseline did not produce the expected behavioral failure' >&2
exit 1
