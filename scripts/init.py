#!/usr/bin/env python3
"""Generate missing development secrets while preserving configured values."""

import os
import secrets
import tempfile
from pathlib import Path

SECRET_KEYS = (
    "NEO4J_ADMIN_KEY",
    "STORE_MONITOR_PASSWORD",
    "NEO4J_CONTROLLER_KEY",
    "RUSTFS_ACCESS_KEY",
    "RUSTFS_SECRET_KEY",
    "QDRANT_API_KEY",
    "OPENSEARCH_ADMIN_PASSWORD",
    "OPENSEARCH_DASHBOARDS_PASSWORD",
    "STORE_OPENSEARCH_CONSOLE_COOKIE_KEY",
    "STORE_RELAY_PASSWORD",
    "STORE_CONSOLE_BOOTSTRAP_PASSWORD",
    "STORE_CONSOLE_OIDC_SECRET",
    "POSTGRES_PASSWORD",
    "POSTGRES_MONITOR_PASSWORD",
    "DATABASE_KEY",
    "TELEMETRY_CATALOG_PASSWORD",
    "DATABASE_BASTION_TOKEN",
    "PLATFORM_AUDIT_PASSWORD",
    "PLATFORM_AUDIT_READER_PASSWORD",
    "KEYCLOAK_ADMIN_PASSWORD",
    "KEYCLOAK_DB_PASSWORD",
    "KEYCLOAK_PROVISIONER_SECRET",
    "GRAFANA_PASSWORD",
)


def initialize(root):
    """Fill absent or empty secret assignments; never interpret configuration as shell."""
    target = root / ".env"
    if target.is_symlink():
        raise ValueError("Configuration must not be a symlink")
    existing = target.exists()
    content = (target if existing else root / ".env.example").read_text()
    lines = content.splitlines()
    positions = {}
    for index, line in enumerate(lines):
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            positions[key] = (index, value)
    changed = []
    for key in SECRET_KEYS:
        entry = positions.get(key)
        if entry is not None and entry[1].strip():
            continue
        value = secrets.token_hex(10 if key == "RUSTFS_ACCESS_KEY" else 32)
        assignment = key + "=" + value
        if entry is None:
            lines.append(assignment)
        else:
            lines[entry[0]] = assignment
        changed.append(key)
    if changed or not existing:
        # Replace atomically so an interrupted write cannot truncate live credentials.
        descriptor, temporary = tempfile.mkstemp(prefix=".env-", dir=root)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                output.write("\n".join(lines) + "\n")
            os.replace(temporary, target)
        finally:
            Path(temporary).unlink(missing_ok=True)
    target.chmod(0o600)
    (root / ".runtime").mkdir(mode=0o700, exist_ok=True)
    return changed


def main():
    changed = initialize(Path(__file__).resolve().parents[1])
    if changed:
        print("Generated missing or empty credentials: " + ", ".join(changed) + ".")
    else:
        print(".env already exists; configuration and secrets were preserved.")
    print("Review .env against .env.example before running bash scripts/up.sh.")


if __name__ == "__main__":
    main()
