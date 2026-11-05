# Non-home release and isolated qualification compatibility inputs

Production home uses only `../home-docker-compose.yml`, with every service defined
directly. This directory is not included or overlaid by home.

The existing edge/application release and disposable qualification inputs remain
here to preserve their separate callers and reviewed manifests. Private native
program configuration, env files and secrets remain in configs. No resolved
credentials or runtime data belong in this public repository.

See [source ownership and rollout](../docs/observability-repository-boundary.md).
