#!/usr/bin/env python3
"""Create development configuration once; never overwrite existing secrets."""
from pathlib import Path
import secrets
import os
root = Path(__file__).resolve().parents[1]
target = root / ".env"
content = (root / ".env.example").read_text()
secret_keys = ("RUSTFS_ACCESS_KEY", "RUSTFS_SECRET_KEY", "QDRANT_API_KEY", "OPENSEARCH_ADMIN_PASSWORD", "OPENSEARCH_DASHBOARDS_PASSWORD", "STORE_RELAY_PASSWORD", "STORE_CONSOLE_BOOTSTRAP_PASSWORD", "STORE_CONSOLE_OIDC_SECRET", "POSTGRES_PASSWORD", "POSTGRES_MONITOR_PASSWORD", "DATABASE_KEY", "TELEMETRY_CATALOG_PASSWORD", "DATABASE_BASTION_TOKEN", "PLATFORM_AUDIT_PASSWORD", "PLATFORM_AUDIT_READER_PASSWORD", "KEYCLOAK_ADMIN_PASSWORD",
               "KEYCLOAK_DB_PASSWORD", "KEYCLOAK_PROVISIONER_SECRET", "GRAFANA_PASSWORD")
def generated(key):
    return secrets.token_hex(10 if key == "RUSTFS_ACCESS_KEY" else 32)

for key in secret_keys:
    content = content.replace(key + "=\n", key + "=" + generated(key) + "\n")
try:
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
except FileExistsError:
    existing = target.read_text()
    missing = [key for key in secret_keys if key + "=" not in existing]
    if missing:
        with target.open("a", encoding="utf-8") as output:
            if existing and not existing.endswith("\n"):
                output.write("\n")
            for key in missing:
                output.write(key + "=" + generated(key) + "\n")
        target.chmod(0o600)
        print("Added generated values for new required secrets: " + ", ".join(missing) + ".")
    else:
        print(".env already exists; configuration and secrets were preserved.")
    print("Review .env against .env.example for updated settings before running bash scripts/up.sh.")
else:
    with os.fdopen(fd, "w") as output:
        output.write(content)
    target.chmod(0o600)
    print("Created .env. Configure domains before running bash scripts/up.sh.")
(root / ".runtime").mkdir(mode=0o700, exist_ok=True)
