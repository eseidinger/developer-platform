#!/usr/bin/env python3
"""Create development configuration once; never overwrite existing secrets."""
from pathlib import Path
import secrets
import os
root = Path(__file__).resolve().parents[1]
target = root / ".env"
content = (root / ".env.example").read_text()
for key in ("POSTGRES_PASSWORD", "PLATFORM_TOKEN", "DATABASE_KEY", "GRAFANA_PASSWORD"):
    content = content.replace(key + "=\n", key + "=" + secrets.token_hex(32) + "\n")
with os.fdopen(os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as output:
    output.write(content)
target.chmod(0o600)
(root / ".runtime").mkdir(mode=0o700, exist_ok=True)
print("Created .env. Configure domains before running bash scripts/up.sh.")
