#!/usr/bin/env python3
"""Install shared access infrastructure with the operator's existing admin kubeconfig.

Secret material goes straight to kubectl stdin. It is never printed or written
to a generated manifest, application revision, or acceptance evidence.
"""
import json
import os
from pathlib import Path
import subprocess
import sys

from env import settings

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "platform" / "app" / "src"))
from app.access_provider import derived_secret
from app.access_runtime import shared_manifests


def main():
    config = settings()
    os.environ["DATABASE_KEY"] = config["DATABASE_KEY"]
    api_ip = config.get("PLATFORM_API_IP", "172.30.80.11")
    identity_ip = config.get("KEYCLOAK_IP", "172.30.80.12")
    image = os.environ.get("APPLICATION_ACCESS_IMAGE", "developer-platform-access-authorizer:local")
    manifests = shared_manifests(image, api_ip, identity_ip, derived_secret("platform", "internal"),
                                 derived_secret("platform", "sessions"))
    command = ["kubectl", "--kubeconfig", str(root / ".runtime/admin.kubeconfig")]
    for manifest in manifests:
        subprocess.run(command + ["apply", "--server-side", "--field-manager=developer-platform-access-bootstrap", "-f", "-"],
                       input=json.dumps(manifest), text=True, check=True)


if __name__ == "__main__":
    main()
