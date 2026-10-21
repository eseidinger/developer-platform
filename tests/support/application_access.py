"""Synthetic policy and identity snapshots shared by API and harness tests."""

import copy
import time

GROUP = "grp_" + "a" * 32
OTHER_GROUP = "grp_" + "b" * 32
POLICY = {
    "id": "pol_" + "c" * 32,
    "kind": "policy",
    "project": "provider",
    "name": "provider",
    "state": "active",
    "version": 1,
    "spec": {
        "component": "api",
        "defaultDecision": "deny",
        "identityAttributes": {"displayName": False, "email": False},
        "applicationId": "d" * 32,
        "host": "api-provider.apps.test",
        "backend": "http://api.project-provider.svc.cluster.local:8080",
        "sessionEpoch": "epoch-1",
        "routes": [
            {
                "name": "human",
                "match": {
                    "pathPrefix": "/app/",
                    "path": None,
                    "methods": ["GET", "POST"],
                },
                "authentication": {"mode": "browser-session"},
                "authorization": {"anyOfGroups": [GROUP]},
            },
            {
                "name": "machine",
                "match": {
                    "pathPrefix": "/api/",
                    "path": None,
                    "methods": ["GET", "POST"],
                },
                "authentication": {"mode": "bearer-token"},
                "authorization": {"anyOfGroups": [GROUP]},
            },
        ],
    },
}


def data():
    return {
        "generation": 1,
        "issuedAt": time.time(),
        "expiresAt": time.time() + 299,
        "issuer": "https://identity.test/realms/platform",
        "jwksUrl": "http://identity.test/certs",
        "policies": [copy.deepcopy(POLICY)],
        "principals": [
            {
                "id": "prn_machine",
                "kind": "service",
                "issuer": "https://identity.test/realms/platform",
                "subject": "machine",
            },
            {
                "id": "prn_human",
                "kind": "user",
                "issuer": "https://identity.test/realms/platform",
                "subject": "human",
            },
        ],
        "memberships": [
            {
                "state": "active",
                "spec": {
                    "policyId": POLICY["id"],
                    "principalId": "prn_machine",
                    "groupId": GROUP,
                },
            },
            {
                "state": "active",
                "spec": {
                    "policyId": POLICY["id"],
                    "principalId": "prn_human",
                    "groupId": GROUP,
                },
            },
        ],
        "services": [
            {
                "state": "active",
                "spec": {
                    "policyId": POLICY["id"],
                    "credentials": [
                        {
                            "state": "active",
                            "subject": "machine",
                            "clientId": "service-current",
                        }
                    ],
                },
            }
        ],
    }


def claims(kind="service"):
    return {
        "iss": "https://identity.test/realms/platform",
        "sub": "machine" if kind == "service" else "human",
        "azp": "service-current" if kind == "service" else "browser-" + POLICY["id"],
        "groups": [GROUP, OTHER_GROUP],
    }
