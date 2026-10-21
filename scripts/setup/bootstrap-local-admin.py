#!/usr/bin/env python3
"""Create the first named local administrator without an interactive login.

The temporary password stays in a private recovery file. Keycloak requires the
person to replace it at first login; automation uses separate runner identities.
"""

import argparse
import getpass
import ipaddress
import json
import os
import secrets
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.internal.env import parse_environment
from scripts.internal.platform_configuration import configure


def create_admin(root, username, output):
    config = parse_environment((root / ".env").read_text())
    address = ipaddress.IPv4Address(config.get("KEYCLOAK_IP", "172.30.80.12"))
    if not address.is_private:
        raise ValueError("Local bootstrap requires the private identity service")
    base = f"http://{address}:8080"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def request(path, *, body=None, token=None, form=False):
        headers = {}
        data = None
        if body is not None:
            data = (urllib.parse.urlencode(body) if form else json.dumps(body)).encode()
            headers["Content-Type"] = (
                "application/x-www-form-urlencoded" if form else "application/json"
            )
        if token:
            headers["Authorization"] = "Bearer " + token
        return opener.open(
            urllib.request.Request(base + path, data=data, headers=headers), timeout=20
        )

    with request(
        "/realms/master/protocol/openid-connect/token",
        form=True,
        body={
            "grant_type": "password",
            "client_id": "admin-cli",
            "username": "admin",
            "password": config["KEYCLOAK_ADMIN_PASSWORD"],
        },
    ) as response:
        token = json.load(response)["access_token"]
    with request(
        "/admin/realms/platform/users?"
        + urllib.parse.urlencode({"username": username, "exact": "true"}),
        token=token,
    ) as response:
        if json.load(response):
            raise ValueError(
                "Existing users must not have their passwords reset by bootstrap"
            )
    if output.parent.is_symlink():
        raise ValueError("Private output directory must not be a symlink")
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if output.parent.stat().st_mode & 0o077:
        raise ValueError("Private output directory permissions are required")
    password = secrets.token_urlsafe(32)
    descriptor = os.open(
        output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
    )
    record = {
        "username": username,
        "temporary_password": password,
        "identity_url": "https://" + config["IDENTITY_DOMAIN"],
        "status": "creation-pending",
    }
    # Preserve the password even if the create response is lost; never reset on retry.
    with os.fdopen(descriptor, "w", encoding="utf-8") as destination:
        json.dump(record, destination, indent=2)
        destination.write("\n")
    with request(
        "/admin/realms/platform/users",
        token=token,
        body={
            "username": username,
            "enabled": True,
            "firstName": username,
            "credentials": [{"type": "password", "value": password, "temporary": True}],
            "requiredActions": ["UPDATE_PASSWORD"],
        },
    ) as response:
        subject = response.headers["Location"].rsplit("/", 1)[1]
    configure(root, {"options": {"bootstrap_subject": subject}})
    record.update(status="created", subject=subject)
    output.write_text(json.dumps(record, indent=2) + "\n")
    return subject


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", default=getpass.getuser())
    parser.add_argument(
        "--output", type=Path, default=ROOT / ".runtime/initial-admin.json"
    )
    args = parser.parse_args()
    try:
        create_admin(ROOT, args.username, args.output.absolute())
    except (OSError, ValueError, KeyError, urllib.error.URLError):
        parser.exit(
            1,
            "Administrator bootstrap failed. Check identity readiness and private configuration; preserve any recovery file before retrying.\n",
        )
    print(f"Administrator created. Private temporary password: {args.output}")
    print("Keycloak requires a password change at first login.")


if __name__ == "__main__":
    main()
