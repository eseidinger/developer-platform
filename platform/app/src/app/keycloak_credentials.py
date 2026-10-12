"""Narrow Keycloak adapter for CI service-account clients."""
import json
import os
import secrets
import urllib.error
import urllib.parse
import urllib.request
from uuid import uuid4


class ProviderError(Exception):
    pass


def _request(path: str, *, method="GET", body=None, token=None, form=False, allow_not_found=False):
    base = os.environ["KEYCLOAK_INTERNAL_URL"].rstrip("/")
    headers = {}
    data = None
    if body is not None:
        if form:
            data = urllib.parse.urlencode(body).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = "Bearer " + token
    try:
        with urllib.request.urlopen(urllib.request.Request(base + path, data=data, method=method, headers=headers),
                                    timeout=10) as response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        if allow_not_found and exc.code == 404:
            return 404, None
        raise ProviderError("Identity provider operation failed") from exc
    except (urllib.error.URLError, ValueError) as exc:
        raise ProviderError("Identity provider operation failed") from exc


def _admin_token() -> str:
    _, response = _request("/realms/platform/protocol/openid-connect/token", method="POST", form=True, body={
        "grant_type": "client_credentials",
        "client_id": os.environ.get("KEYCLOAK_PROVISIONER_CLIENT_ID", "platform-credential-provisioner"),
        "client_secret": os.environ["KEYCLOAK_PROVISIONER_SECRET"],
    })
    token = (response or {}).get("access_token")
    if not token:
        raise ProviderError("Identity provider returned no administration token")
    return token


def create_client(display_name: str) -> dict:
    token = _admin_token()
    client_id = "platform-ci-" + uuid4().hex
    client_secret = secrets.token_urlsafe(32)
    representation = {
        "clientId": client_id, "name": display_name, "enabled": True, "protocol": "openid-connect",
        "publicClient": False, "serviceAccountsEnabled": True, "standardFlowEnabled": False,
        "directAccessGrantsEnabled": False, "secret": client_secret,
        "protocolMappers": [{"name": "platform-api audience", "protocol": "openid-connect",
            "protocolMapper": "oidc-audience-mapper", "consentRequired": False,
            "config": {"included.client.audience": "platform-api", "id.token.claim": "false",
                       "access.token.claim": "true"}}],
    }
    _request("/admin/realms/platform/clients", method="POST", body=representation, token=token)
    _, clients = _request("/admin/realms/platform/clients?" + urllib.parse.urlencode({"clientId": client_id}),
                          token=token)
    if not clients or len(clients) != 1:
        raise ProviderError("Created identity-provider client could not be resolved")
    provider_id = clients[0]["id"]
    _, service_account = _request(f"/admin/realms/platform/clients/{provider_id}/service-account-user", token=token)
    subject = (service_account or {}).get("id")
    if not subject:
        raise ProviderError("Identity provider returned no service-account subject")
    return {"provider_resource_id": provider_id, "client_id": client_id,
            "client_secret": client_secret, "subject": subject}


def delete_client(provider_resource_id: str) -> None:
    _request(f"/admin/realms/platform/clients/{urllib.parse.quote(provider_resource_id, safe='')}",
             method="DELETE", token=_admin_token(), allow_not_found=True)
