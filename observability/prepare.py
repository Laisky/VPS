#!/usr/bin/env python3
"""Render non-secret edge configuration. --dev creates disposable local secrets.

Production: provision secrets/{ca.crt,edge.crt,edge.key,home.crt,home.key} and a
private .env separately. Never copy the development CA private key to servers.
"""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import secrets
import subprocess
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent


def validate_home_url(value):
    """Return a validated HTTPS origin without embedded credentials or paths."""
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("home URL must be an HTTPS origin without credentials")
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise ValueError("home URL must not include a path, query or fragment")
    if parsed.port is not None and not 1 <= parsed.port <= 65535:
        raise ValueError("invalid home port")
    return value.rstrip("/")


def render(home_url):
    """Write an OTLP configuration with explicit admission and replay bounds."""
    home = validate_home_url(home_url)
    config = {"settings": {"otlp": {
        "enabled": True, "listen_addr": "0.0.0.0:4318", "storage_dir": "/state/otlp",
        "bearer_token_env": "GO_FLUENTD_OTLP_TOKEN",
        "tls_cert_file": "/run/observability/edge.crt",
        "tls_key_file": "/run/observability/edge.key",
        "max_connections": 64, "max_concurrent": 4,
        "max_wire_bytes": 1048576, "max_decoded_bytes": 4194304,
        "max_items": 10000, "max_response_bytes": 65536,
        "max_wal_bytes": 1073741824, "max_storage_bytes": 2147483648,
        "receipt_gc": True, "journal_gzip": True,
        "replay_batch": 64, "replay_interval": "1s",
        "request_timeout": "10s", "shutdown_timeout": "30s",
        "destinations": [{
            "id": "home-observability-v1",
            "logs_endpoint": home + "/v1/logs",
            "metrics_endpoint": home + "/v1/metrics",
            "traces_endpoint": home + "/v1/traces",
            "bearer_token_env": "GO_FLUENTD_HOME_TOKEN",
            "ca_file": "/run/observability/ca.crt", "gzip": True,
            "timeout": "5s", "max_attempts": 2,
            "initial_backoff": "500ms", "max_backoff": "5s"}],
    }, "journal": {"buf_dir_path": "/state/legacy", "buf_file_bytes": 1048576,
                   "is_compress": False, "committed_id_sec": 120,
                   "group_commit_max_messages": 1, "journal_out_chan_len": 32,
                   "commit_id_chan_len": 32, "child_data_chan_len": 32,
                   "child_id_chan_len": 32, "gc_inteval_sec": 3600}}}
    generated = ROOT / "generated"
    generated.mkdir(mode=0o700, exist_ok=True)
    (generated / "edge.json").write_text(json.dumps(config, indent=2) + "\n")
    for directory in ("edge/otlp", "edge/legacy", "home/collector", "home/metrics", "home/logs", "home/traces", "home/grafana"):
        (ROOT / "state" / directory).mkdir(mode=0o700, parents=True, exist_ok=True)


def development(image):
    """Create a local-only CA and synthetic credentials without overwriting state."""
    private = ROOT / "secrets"
    if private.exists() or (ROOT / ".env").exists():
        raise ValueError("refusing to overwrite secrets or .env; use a new test directory")
    private.mkdir(mode=0o700)
    def openssl(*args):
        subprocess.run(["openssl", *args], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    openssl("req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "7",
            "-keyout", str(private / "ca.key"), "-out", str(private / "ca.crt"),
            "-subj", "/CN=Disposable observability test CA")
    for name, sans in (("edge", "DNS:edge,IP:127.0.0.1"), ("home", "DNS:gateway,IP:127.0.0.1")):
        ext = private / (name + ".ext")
        ext.write_text("subjectAltName=" + sans + "\nextendedKeyUsage=serverAuth\n")
        openssl("req", "-newkey", "rsa:2048", "-nodes", "-keyout", str(private / (name + ".key")),
                "-out", str(private / (name + ".csr")), "-subj", "/CN=" + name)
        openssl("x509", "-req", "-in", str(private / (name + ".csr")), "-CA", str(private / "ca.crt"),
                "-CAkey", str(private / "ca.key"), "-CAcreateserial", "-days", "7", "-extfile", str(ext),
                "-out", str(private / (name + ".crt")))
    # Only public CA and server identities are needed at runtime.
    (private / "ca.key").unlink()
    values = {"OBSERVABILITY_DEV_ONLY": "true", "GO_FLUENTD_IMAGE": image, "OBS_UID": str(os.getuid()), "OBS_GID": str(os.getgid()),
              "EDGE_TOKEN": secrets.token_hex(32), "HOME_TOKEN": secrets.token_hex(32),
              "GRAFANA_ADMIN_PASSWORD": secrets.token_hex(32), "EDGE_BIND": "127.0.0.1", "HOME_BIND": "127.0.0.1"}
    (ROOT / ".env").write_text("\n".join(f"{key}={value}" for key, value in values.items()) + "\n")
    os.chmod(ROOT / ".env", 0o600)


def main():
    """Parse explicit rendering/development options and fail without secret output."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home-url", required=True)
    parser.add_argument("--dev", action="store_true")
    parser.add_argument("--image", default="go-fluentd:observability-test")
    args = parser.parse_args()
    os.umask(0o077)
    validate_home_url(args.home_url)
    if args.dev:
        development(args.image)
    render(args.home_url)
    print("Rendered edge configuration; no production service was modified.")


if __name__ == "__main__":
    main()
