# DERPer manual certificate reload

This downstream build pins Tailscale v1.102.5 and applies the manual certificate
reload patch in patches/cert.go. Build from the repository root with
`docker build -f derper/Dockerfile .`. The image build runs the DERPer Go
unit tests; see tests/README.md for isolated integration fixtures.

Manual mode retains upstream startup acceptance for expired or not-yet-valid
certificates. New handshakes reject a cached certificate outside its validity
period; unlike upstream, the server will not present an expired fallback.

New TLS handshakes periodically check for renewed manual certificates. Invalid
or incomplete replacements retain the last valid certificate; once that
certificate expires, new handshakes fail. Existing connections are preserved.
Automatic ACME and self-signed certificate paths retain their prior behavior.

A deployment also needs directory mounts that preserve the certificate
lineage symlinks; replacing a single-file bind can leave the old inode mounted.
Review and validate deployment-specific mounts independently. This source
change does not publish an image, change a tag, or restart a service.

## HK / RackNerd rollout checks

Keep `ppcelery/derper:latest`: this repository intentionally supports pulling
and recreating services without editing an image pin. A tag alone is not proof
that a particular local image implements reload. Before rollout:

1. Confirm the configured `live/<lineage>` and `archive/<lineage>` directories
   already exist and the live symlinks resolve into the matching archive.
   HK/RackNerd binds set `create_host_path: false`; a wrong path must fail rather
   than silently becoming an empty directory. Do not create empty directories
   to work around this failure.
2. Use the host's existing Compose project identity and helper flags to pull
   `derper`. Record `docker image inspect ppcelery/derper:latest` image ID,
   RepoDigests, and version label. Retain the previous running image ID for
   rollback. No production private keys belong in test evidence.
3. Qualify the pulled image using the isolated integration fixtures, passing
   its immutable local image ID to `--image` and the rendered host startup
   snippet to `--rollout-snippet`. Labels are provenance hints, not acceptance.
   If the tag moves before recreation, requalify the replacement image.
4. Recreate only `derper` with the same project identity. This can disconnect
   current relay sessions; hot reload does not make deployment nondisruptive.
   Verify the running container's image ID equals the qualified ID, and verify
   the hostname, certificate fingerprint and expiry presented on port 12444.

Configuration tests do not establish that production hosts are ready. The
image-level fixture is local/opt-in rather than a heavy pull-request CI gate.
Run the actual missing-directory bind controls locally with
`COMPOSE_ENGINE_TEST=1 python3 -m unittest discover -s tests -p test_derper_cert_mounts.py -v`.
They use only temporary paths and never start the probe containers.
