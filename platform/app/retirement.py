"""Retirement scope: what removal deletes, what it keeps, and the token that pins that scope."""
import hashlib
import hmac
import json
import os

from .manifests import SECRET_NAME, component_resources, resources
from .secrets import PREVIOUS_SECRET_NAME

DOCUMENTATION_ADDRESS = "192.0.2.1"


def scope_token(name: str, revision: int, access=None) -> str:
    """Fingerprint of the removal scope; any new revision changes it and forces a new preview."""
    encoded = json.dumps(access or {}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(f"retire:{name}:{revision}:{encoded}".encode()).hexdigest()[:32]


def purge_scope_token(name: str, project_id: str, retired_at: str, credential_states: dict[str, int]) -> str:
    """Bind a destructive purge confirmation to one retired catalog state."""
    state = json.dumps(credential_states, sort_keys=True, separators=(",", ":"))
    message = f"purge:{name}:{project_id}:{retired_at}:{state}".encode()
    return hmac.new(os.environ["DATABASE_KEY"].encode(), message, hashlib.sha256).hexdigest()[:32]


def removal_scope(name: str, revision: int, spec: dict, domain: str) -> dict:
    # Only kinds and names are used; the placeholder address and password never leave this function.
    if spec.get("components") is not None:
        manifests = component_resources(name, spec["components"], DOCUMENTATION_ADDRESS, "unused",
                                        spec.get("configuration"), domain)
    else:
        manifests = resources(name, spec.get("resolved_image", spec["image"]), spec.get("port", 8080),
                              domain, DOCUMENTATION_ADDRESS, "unused", spec.get("resources"), spec.get("configuration"))
    database = "project_" + name.replace("-", "_")
    routes = [rule["host"] for manifest in manifests if manifest["kind"] == "Ingress"
              for rule in manifest["spec"].get("rules", [])]
    return {
        "project": name,
        "revision": revision,
        "removes": [{"kind": m["kind"], "name": m["metadata"]["name"]} for m in manifests]
                   + [{"kind": "Secret", "name": SECRET_NAME}, {"kind": "Secret", "name": PREVIOUS_SECRET_NAME}],
        "route": routes[0] if len(routes) == 1 else None,
        "routes": routes,
        "retains": {"database": database, "role": database, "catalog_and_revisions": True},
        "scope_token": scope_token(name, revision),
    }
