"""Retirement scope: what removal deletes, what it keeps, and the token that pins that scope."""
import hashlib

from .manifests import SECRET_NAME, component_resources, resources
from .secrets import PREVIOUS_SECRET_NAME

DOCUMENTATION_ADDRESS = "192.0.2.1"


def scope_token(name: str, revision: int) -> str:
    """Fingerprint of the removal scope; any new revision changes it and forces a new preview."""
    return hashlib.sha256(f"retire:{name}:{revision}".encode()).hexdigest()[:32]


def removal_scope(name: str, revision: int, spec: dict, domain: str) -> dict:
    # Only kinds and names are used; the placeholder address and password never leave this function.
    if spec.get("components") is not None:
        manifests = component_resources(name, spec["components"], DOCUMENTATION_ADDRESS, "unused",
                                        spec.get("configuration"), domain)
    else:
        manifests = resources(name, spec.get("resolved_image", spec["image"]), spec.get("port", 8080),
                              domain, DOCUMENTATION_ADDRESS, "unused", spec.get("resources"), spec.get("configuration"))
    database = "project_" + name.replace("-", "_")
    return {
        "project": name,
        "revision": revision,
        "removes": [{"kind": m["kind"], "name": m["metadata"]["name"]} for m in manifests]
                   + [{"kind": "Secret", "name": SECRET_NAME}, {"kind": "Secret", "name": PREVIOUS_SECRET_NAME}],
        "route": name + "." + domain,
        "retains": {"database": database, "role": database, "catalog_and_revisions": True},
        "scope_token": scope_token(name, revision),
    }
