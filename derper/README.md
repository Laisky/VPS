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
