#!/usr/bin/env python3
"""Export Caddy's public local CA for isolated services that verify local OIDC."""

import os
import ssl
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.internal.env import parse_environment


def prepare(root):
    config = parse_environment((root / ".env").read_text())
    directory = root / ".runtime" / "trust"
    if directory.is_symlink():
        raise ValueError("Trust directory must not be a symlink")
    directory.mkdir(mode=0o755, parents=True, exist_ok=True)
    domain = config.get("IDENTITY_DOMAIN", "identity.localhost").lower().rstrip(".")
    if not domain.endswith(".localhost") and domain != "localhost":
        return

    # Copy one public certificate, never mount Caddy's private CA storage.
    result = subprocess.run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "proxy",
            "cat",
            "/data/caddy/pki/authorities/local/root.crt",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    if result.returncode:
        raise ValueError("Start the edge proxy before preparing local CA trust")
    ssl.create_default_context().load_verify_locations(cadata=result.stdout)
    target = directory / "local-ca.pem"
    if target.is_symlink():
        raise ValueError("Public CA destination must not be a symlink")
    descriptor, temporary = tempfile.mkstemp(prefix=".local-ca-", dir=directory)
    try:
        with os.fdopen(descriptor, "w", encoding="ascii") as output:
            output.write(result.stdout)
        # Isolated services run as different users; this certificate is public.
        os.chmod(temporary, 0o644)
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        prepare(ROOT)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        raise SystemExit(
            "Local CA preparation failed: " + type(error).__name__
        ) from None
    print("Service certificate trust prepared; TLS verification remains enabled.")
