"""Obtain short-lived recovery tokens from a private, local test-runner credential."""

import ipaddress
import json
import stat
import urllib.parse
import urllib.request
from pathlib import Path


def access_token(root: Path) -> str:
    """Renew a token through the guest's private Keycloak address.

    The credential is issued only after the isolated API starts. This avoids
    expiry during the long restore and keeps the secret out of Ansible output.
    """
    credential_file = root / ".runtime/recovery/test-runner.json"
    if (
        credential_file.is_symlink()
        or not credential_file.is_file()
        or stat.S_IMODE(credential_file.stat().st_mode) != 0o600
    ):
        raise RuntimeError("Recovery credential must have mode 0600")
    credential = json.loads(credential_file.read_text())
    expected_endpoint = (
        "https://identity.localhost/realms/platform/protocol/openid-connect/token"
    )
    if (
        credential.get("platform_api_url") != "http://127.0.0.1:8000"
        or credential.get("platform_oidc_token_url") != expected_endpoint
    ):
        raise RuntimeError("Recovery credential has an unexpected origin")

    settings = dict(
        line.split("=", 1)
        for line in (root / ".env").read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )
    if settings.get("IDENTITY_DOMAIN") != "identity.localhost":
        raise RuntimeError("Recovery identity domain is not isolated")
    keycloak_ip = ipaddress.ip_address(settings["KEYCLOAK_IP"])
    if not keycloak_ip.is_private or keycloak_ip.version != 4:
        raise RuntimeError("Recovery identity address is not private IPv4")
    endpoint = (
        f"http://{keycloak_ip}:8080/realms/platform/protocol/openid-connect/token"
    )
    data = urllib.parse.urlencode(
        {
            "grant_type": "client_credentials",
            "client_id": credential["platform_test_runner_client_id"],
            "client_secret": credential["platform_test_runner_client_secret"],
        }
    ).encode()
    # Do not inherit proxy variables when calling the guest's private address.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(
        urllib.request.Request(endpoint, data=data), timeout=15
    ) as response:
        token = json.load(response).get("access_token")
    if not isinstance(token, str) or not token:
        raise RuntimeError("Recovery token endpoint returned no access token")
    return token
