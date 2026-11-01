# Observability Compose sources

VPS owns the shared entrypoint, service modules and overlays here. Sensitive
configuration, secret files and env inputs stay under `/opt/configs`.
The shared entrypoint preserves private interpolation/project-directory semantics;
the canonical home entrypoint preserves project `vps` and seven-day retention.

[Ordered rollout and rollback](../docs/observability-repository-boundary.md)
requires staging VPS before configs removals. Do not remove old live files or
restart services automatically. No image, credential, security, DNS or alert
change is implied by the source move.
