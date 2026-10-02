#!/usr/bin/env python3
"""Create development configuration once; never overwrite existing secrets."""
from pathlib import Path
import secrets
import os
root = Path(__file__).resolve().parents[1]
target = root / ".env"
content = (root / ".env.example").read_text()
secret_keys = ("POSTGRES_PASSWORD", "PLATFORM_TOKEN", "DATABASE_KEY", "PLATFORM_AUDIT_PASSWORD", "GRAFANA_PASSWORD")
for key in secret_keys:
    content = content.replace(key + "=\n", key + "=" + secrets.token_hex(32) + "\n")
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
                output.write(key + "=" + secrets.token_hex(32) + "\n")
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
