#!/usr/bin/env python3
"""Disposable, bounded DERPer integration fixtures; never reads production keys.

python3 test_integration.py --mount-only
python3 test_integration.py --image IMAGE --entrypoint /app/derper
python3 test_integration.py --baseline-bin /absolute/path/to/unpatched/derper

Requires local Docker images and Python cryptography. Images are never pulled.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import socket
import ssl
import subprocess
import tempfile
import time
import unittest

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

HOST = "fixture.derp.invalid"
ARGS = None


def command(*args, timeout=20):
    return subprocess.check_output(args, timeout=timeout, text=True).strip()


def staged_script(options):
    if ARGS.rollout_snippet:
        text = Path(ARGS.rollout_snippet).read_text()
        lines = text.splitlines()
        begin = next(i for i, line in enumerate(lines) if line == "    - |")
        script = "\n".join(line[6:] for line in lines[begin + 1:] if line.startswith("      "))
        hostname = re.search(r"--hostname=([^\s]+)", script).group(1)
        lineage = re.search(r"/etc/letsencrypt/live/([^/]+)/fullchain.pem", script).group(1)
        expected_mounts = {f"/etc/letsencrypt/live/{lineage}", f"/etc/letsencrypt/archive/{lineage}"}
        mounts = re.findall(r'^    - "[^\"]+:(/etc/letsencrypt[^\"]+):ro"$', text, re.M)
        if set(mounts) != expected_mounts or len(mounts) != 2:
            raise AssertionError("Rollout must mount only stable live/archive lineage directories read-only")
        script = script.replace(hostname, HOST).replace("/etc/letsencrypt/live/" + lineage,
                                                       "/etc/letsencrypt/live/" + HOST)
        script = re.sub(r"-c=/[^\s]+", "-c=/tmp/disposable-derper.conf", script)
        script = re.sub(r"(?<!\S)-stun(?=\s|$)", "-stun=false", script)
        # Only fixture hostname/config/STUN are substituted; alias command flags
        # and DERPer invocation otherwise come from the actual review snippet.
        return script
    return ("mkdir -p /run/derper-certs\n"
            f"ln -sfn /etc/letsencrypt/live/{HOST}/fullchain.pem /run/derper-certs/{HOST}.crt\n"
            f"ln -sfn /etc/letsencrypt/live/{HOST}/privkey.pem /run/derper-certs/{HOST}.key\n"
            "exec " + shlex.quote(ARGS.entrypoint) + " " + " ".join(map(shlex.quote, options))
            + " -a=:12444 -c=/tmp/disposable-derper.conf --certdir=/run/derper-certs")


class Fixtures:
    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="derper-fixture-")
        self.root = Path(self.tmp.name).resolve()
        # Disposable generated fixtures must be readable by the candidate's
        # unprivileged container UID; no production certificate material exists here.
        self.root.chmod(0o755)
        self.archive = self.root / "archive" / HOST
        self.live = self.root / "live" / HOST
        self.archive.mkdir(parents=True)
        self.live.mkdir(parents=True)
        self.aliases = self.root / "aliases"
        self.aliases.mkdir(mode=0o777)
        self.aliases.chmod(0o777)  # disposable RW alias mount, no private contents
        now = dt.datetime.now(dt.timezone.utc)
        self.ca_key = ec.generate_private_key(ec.SECP256R1())
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Disposable fixture CA")])
        self.ca = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
                   .public_key(self.ca_key.public_key()).serial_number(x509.random_serial_number())
                   .not_valid_before(now - dt.timedelta(minutes=5))
                   .not_valid_after(now + dt.timedelta(days=2))
                   .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
                   .sign(self.ca_key, hashes.SHA256()))
        self.ca_path = self.root / "ca.crt"
        self.ca_path.write_bytes(self.ca.public_bytes(serialization.Encoding.PEM))
        self.leaves = {}
        self.create("old")
        self.create("new")
        self.create("wrong", hostname="wrong.fixture.invalid")
        self.create("expired", expired=True)
        self.publish("old")

    def create(self, label, hostname=HOST, expired=False):
        now = dt.datetime.now(dt.timezone.utc)
        key = ec.generate_private_key(ec.SECP256R1())
        cert = (x509.CertificateBuilder()
                .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, hostname)]))
                .issuer_name(self.ca.subject).public_key(key.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(now - dt.timedelta(days=1) if expired else now - dt.timedelta(minutes=5))
                .not_valid_after(now - dt.timedelta(minutes=1) if expired else now + dt.timedelta(days=1))
                .add_extension(x509.SubjectAlternativeName([x509.DNSName(hostname)]), critical=False)
                .sign(self.ca_key, hashes.SHA256()))
        certpath = self.archive / (label + ".crt")
        keypath = self.archive / (label + ".key")
        certpath.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        keypath.write_bytes(key.private_bytes(serialization.Encoding.PEM,
                                             serialization.PrivateFormat.PKCS8,
                                             serialization.NoEncryption()))
        keypath.chmod(0o644)
        self.leaves[label] = hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest()

    def publish(self, cert, key=None):
        # Mirrors Certbot live symlink replacement; two-file updates are not atomic.
        for suffix, label, canonical in (("crt", cert, "fullchain.pem"),
                                          ("key", key or cert, "privkey.pem")):
            for filename in (HOST + "." + suffix, canonical):
                dest = self.live / filename
                staged = dest.with_suffix(dest.suffix + ".next")
                staged.symlink_to("../../archive/" + HOST + "/" + label + "." + suffix)
                os.replace(staged, dest)

    def close(self):
        # Only TemporaryDirectory's uniquely created fixture tree is removed.
        self.tmp.cleanup()


class BindMountRegression(unittest.TestCase):
    def test_single_file_stays_old_directory_tracks_symlink(self):
        fixture = Fixtures()
        container = None
        try:
            image = command("docker", "image", "inspect", ARGS.mount_image, "--format", "{{.Id}}")
            container = command("docker", "run", "-d", "--pull=never", "--network=none",
                                "--label=laisky.derper.fixture=disposable-integration",
                                "--cpus=1", "--memory=256m", "--pids-limit=32",
                                "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges",
                                "--mount", f"type=bind,src={fixture.live / (HOST + '.crt')},dst=/single.crt,readonly",
                                "--mount", f"type=bind,src={fixture.root},dst=/tree,readonly",
                                image, "sh", "-c", "sleep 120")
            old = fixture.archive.joinpath("old.crt").read_text().strip()
            new = fixture.archive.joinpath("new.crt").read_text().strip()
            self.assertEqual(command("docker", "exec", container, "cat", "/single.crt"), old)
            fixture.publish("new")
            self.assertEqual(command("docker", "exec", container, "cat", "/single.crt"), old)
            self.assertEqual(command("docker", "exec", container, "cat", f"/tree/live/{HOST}/{HOST}.crt"), new)
            print("EVIDENCE: single-file bind retained old certificate; directory-tree symlink resolved new certificate")
        finally:
            if container:
                subprocess.run(["docker", "rm", "-f", container], check=True, timeout=10,
                               stdout=subprocess.DEVNULL)
            fixture.close()


class TLSRegression(unittest.TestCase):
    def setUp(self):
        if not ARGS.image and not ARGS.baseline_bin:
            self.skipTest("Supply --image for candidate or --baseline-bin for upstream")
        self.fixture = Fixtures()
        self.container = None
        self.process = None
        self.addCleanup(self.cleanup)
        options = ["--hostname=" + HOST, "--certmode=manual", "--http-port=-1", "--stun=false"]
        if ARGS.image:
            image = command("docker", "image", "inspect", ARGS.image, "--format", "{{.Id}}")
            script = staged_script(options)
            self.container = command("docker", "run", "-d", "--pull=never", "--cpus=1",
                                    "--label=laisky.derper.fixture=disposable-integration",
                                    "--memory=256m", "--pids-limit=64", "--read-only", "--cap-drop=ALL",
                                    "--security-opt=no-new-privileges", "--tmpfs", "/tmp:rw,noexec,nosuid,size=4m",
                                    "-p", "127.0.0.1::12444", "--mount",
                                    f"type=bind,src={self.fixture.live},dst=/etc/letsencrypt/live/{HOST},readonly",
                                    "--mount", f"type=bind,src={self.fixture.archive},dst=/etc/letsencrypt/archive/{HOST},readonly",
                                    "--mount", f"type=bind,src={self.fixture.aliases},dst=/run/derper-certs",
                                    "--entrypoint", "/bin/sh", image, "-ec", script)
            self.refresh_port()
        else:
            with socket.socket() as reservation:
                reservation.bind(("127.0.0.1", 0))
                self.port = reservation.getsockname()[1]
            self.process = subprocess.Popen([ARGS.baseline_bin, *options, "-a=127.0.0.1:" + str(self.port),
                                             "-c=" + str(self.fixture.root / "disposable.conf"),
                                             "--certdir=" + str(self.fixture.live)],
                                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + 8
        while True:
            try:
                with self.connect() as conn:
                    self.assertEqual(self.fingerprint(conn), self.fixture.leaves["old"])
                break
            except (OSError, ssl.SSLError):
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.1)

    def cleanup(self):
        if self.container:
            subprocess.run(["docker", "rm", "-f", self.container], check=True, timeout=10,
                           stdout=subprocess.DEVNULL)
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        self.fixture.close()

    def connect(self, hostname=HOST, trust=True):
        context = ssl.create_default_context(cafile=str(self.fixture.ca_path) if trust else None)
        raw = socket.create_connection(("127.0.0.1", self.port), timeout=3)
        try:
            return context.wrap_socket(raw, server_hostname=hostname)
        except Exception:
            raw.close()
            raise

    def refresh_port(self):
        binding = json.loads(command("docker", "inspect", "--format", "{{json .NetworkSettings.Ports}}",
                                     self.container))["12444/tcp"][0]
        self.assertEqual(binding["HostIp"], "127.0.0.1")
        self.port = int(binding["HostPort"])

    @staticmethod
    def fingerprint(conn):
        return hashlib.sha256(conn.getpeercert(binary_form=True)).hexdigest()

    def assert_leaf(self, label, wait=0):
        if wait:
            time.sleep(wait)
        with self.connect() as conn:
            self.assertEqual(self.fingerprint(conn), self.fixture.leaves[label])
            conn.sendall(b"GET / HTTP/1.1\r\nHost: fixture.derp.invalid\r\nConnection: close\r\n\r\n")
            self.assertIn(b"200", conn.recv(256).split(b"\r\n", 1)[0])

    def test_atomic_renewal_and_existing_connection(self):
        with self.connect() as existing:
            self.fixture.publish("new")
            expected = "old" if ARGS.baseline_bin else "new"
            self.assert_leaf(expected, wait=1.2)
            self.assertEqual(self.fingerprint(existing), self.fixture.leaves["old"])
            existing.sendall(b"GET / HTTP/1.1\r\nHost: fixture.derp.invalid\r\nConnection: close\r\n\r\n")
            self.assertIn(b"200", existing.recv(256).split(b"\r\n", 1)[0])
        print("EVIDENCE: fresh handshake served " + expected + "; established TLS connection remained healthy")

    def test_partial_and_invalid_updates_keep_last_valid(self):
        if ARGS.baseline_bin:
            self.skipTest("Reload rejection belongs to candidate")
        for cert, key in (("new", "old"), ("wrong", "wrong"), ("expired", "expired")):
            self.fixture.publish(cert, key)
            self.assert_leaf("old", wait=1.2)
        self.fixture.publish("new")
        self.assert_leaf("new", wait=1.2)
        target = self.fixture.live / "fullchain.pem"
        staged = target.with_suffix(".broken")
        staged.write_text("not a certificate\n")
        os.replace(staged, target)
        self.assert_leaf("new", wait=1.2)
        self.fixture.publish("old")
        self.assert_leaf("old", wait=1.2)
        if self.container:
            lines = subprocess.check_output(
                ["docker", "logs", self.container], timeout=8, text=True,
                stderr=subprocess.STDOUT).splitlines()
            signals = [line for line in lines if "manual certificate reload" in line]
            self.assertEqual(len(signals), 2, "warnings/recovery flooded during rapid invalid updates")
            self.assertTrue(signals[0].endswith(
                "WARNING: manual certificate reload rejected; cached certificate unchanged"))
            self.assertTrue(signals[1].endswith("manual certificate reload recovered"))
            print("EVIDENCE: one fixed rejection warning and one recovery; valid fallback uninterrupted")

    def test_same_container_restart_aliases_are_idempotent(self):
        if not self.container:
            self.skipTest("Staged entrypoint restart belongs to candidate")
        self.fixture.publish("new")
        self.assert_leaf("new", wait=1.2)
        aliases_before = {p.name: os.readlink(p) for p in self.fixture.aliases.iterdir()}
        self.assertEqual(len(aliases_before), 2)
        previous_port = self.port
        command("docker", "restart", "--time=2", self.container)
        self.refresh_port()  # Docker may reallocate an ephemeral published port.
        deadline = time.monotonic() + 8
        while True:
            try:
                self.assert_leaf("new")
                break
            except (OSError, ssl.SSLError):
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.1)
        self.assertEqual({p.name: os.readlink(p) for p in self.fixture.aliases.iterdir()}, aliases_before)
        self.assertEqual(command("docker", "inspect", "--format", "{{.State.Running}}", self.container), "true")
        print("EVIDENCE: exact staged lineage mounts and persistent aliases survived same-container restart")
        print("EVIDENCE: restart loopback port reallocated=" + str(previous_port != self.port))

    def test_client_trust_and_hostname_are_enforced(self):
        with self.assertRaises(ssl.SSLCertVerificationError):
            self.connect(trust=False)
        # Server rejects wrong SNI; client may receive either hostname validation
        # failure or the server's TLS alert. Both must fail, never return a socket.
        with self.assertRaises(ssl.SSLError):
            self.connect(hostname="wrong.fixture.invalid")
        self.assert_leaf("old")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image")
    parser.add_argument("--entrypoint", default="/app/derper")
    parser.add_argument("--baseline-bin")
    parser.add_argument("--rollout-snippet", help="Test actual reviewed service shell block with generated fixture substitutions")
    parser.add_argument("--mount-image", default="alpine:3")
    parser.add_argument("--mount-only", action="store_true")
    ARGS = parser.parse_args()
    if ARGS.image and ARGS.baseline_bin:
        parser.error("Choose candidate image or baseline binary")
    suite = unittest.TestSuite()
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(BindMountRegression))
    if not ARGS.mount_only:
        suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TLSRegression))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
