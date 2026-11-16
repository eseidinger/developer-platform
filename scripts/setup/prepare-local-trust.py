#!/usr/bin/env python3
"""Export Caddy's public local CA for isolated services that verify local OIDC."""

import os
import ssl
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.internal.env import parse_environment


def public_certificate(root, service):
    # Copy one public certificate, never mount Caddy's private CA storage.
    for attempt in range(15):
        result = subprocess.run(
            [
                "docker",
                "compose",
                "exec",
                "-T",
                service,
                "cat",
                "/data/caddy/pki/authorities/local/root.crt",
            ],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        if not result.returncode:
            break
        if attempt == 14:
            raise ValueError("Start the HTTPS gateways before preparing local CA trust")
        time.sleep(1)
    ssl.create_default_context().load_verify_locations(cadata=result.stdout)
    return result.stdout


def write_public(directory, name, content):
    target = directory / name
    if target.is_symlink():
        raise ValueError("Public CA destination must not be a symlink")
    descriptor, temporary = tempfile.mkstemp(prefix=".local-ca-", dir=directory)
    try:
        with os.fdopen(descriptor, "w", encoding="ascii") as output:
            output.write(content)
        # Isolated services run as different users; this certificate is public.
        os.chmod(temporary, 0o644)
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)


def prepare(root, *, runtime=False):
    config = parse_environment((root / ".env").read_text())
    if runtime:
        # Match Compose/up.sh without reading unrelated environment or secrets.
        config.update(
            {
                key: os.environ[key]
                for key in ("IDENTITY_DOMAIN", "LOCAL_APPLICATION_HTTPS_ENABLED")
                if key in os.environ
            }
        )
    directory = root / ".runtime" / "trust"
    if directory.is_symlink():
        raise ValueError("Trust directory must not be a symlink")
    directory.mkdir(mode=0o755, parents=True, exist_ok=True)
    domain = config.get("IDENTITY_DOMAIN", "identity.localhost").lower().rstrip(".")
    if not domain.endswith(".localhost") and domain != "localhost":
        return
    certificate = public_certificate(root, "proxy")
    write_public(directory, "local-ca.pem", certificate)
    if config.get("LOCAL_APPLICATION_HTTPS_ENABLED") == "true":
        application_ca = public_certificate(root, "local-application-edge")
        # Retain public roots as well: a declared external HTTPS destination
        # should not lose verification when local trust is added to the image.
        roots = "".join(
            ssl.DER_cert_to_PEM_cert(der)
            for der in ssl.create_default_context().get_ca_certs(binary_form=True)
        )
        write_public(directory, "local-application-ca.pem", application_ca)
        write_public(
            directory, "application-ca-bundle.pem", roots + certificate + application_ca
        )


if __name__ == "__main__":
    try:
        prepare(ROOT, runtime=True)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        raise SystemExit(
            "Local CA preparation failed: " + type(error).__name__
        ) from None
    print("Service certificate trust prepared; TLS verification remains enabled.")
