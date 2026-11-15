"""Username lookup must never grant authority to an unresolved identity."""

import pytest
from fastapi import HTTPException

from app import human_identity, keycloak_credentials


def test_username_resolves_to_stable_subject(monkeypatch):
    monkeypatch.setenv("OIDC_ISSUER", "https://identity.example/realms/platform")
    monkeypatch.setattr(keycloak_credentials, "_admin_token", lambda: "token")

    def request(path, **kwargs):
        assert "username=alice" in path
        assert "exact=true" in path
        return 200, [{"username": "alice", "enabled": True, "id": "stable-id"}]

    monkeypatch.setattr(keycloak_credentials, "_request", request)
    assert human_identity.resolve(None, None, "alice") == (
        "https://identity.example/realms/platform",
        "stable-id",
    )


@pytest.mark.parametrize(
    "users",
    [
        [],
        [{"username": "alice", "enabled": False, "id": "id"}],
        [
            {"username": "alice", "enabled": True, "id": "first"},
            {"username": "alice", "enabled": True, "id": "second"},
        ],
    ],
)
def test_unknown_or_disabled_username_is_rejected(monkeypatch, users):
    monkeypatch.setattr(keycloak_credentials, "_admin_token", lambda: "token")
    monkeypatch.setattr(keycloak_credentials, "_request", lambda *a, **k: (200, users))
    with pytest.raises(HTTPException) as error:
        human_identity.resolve(None, None, "alice")
    assert error.value.status_code == 404


def test_legacy_identity_and_mixed_input(monkeypatch):
    assert human_identity.resolve("issuer", "subject", None) == ("issuer", "subject")
    with pytest.raises(HTTPException) as error:
        human_identity.resolve("issuer", "subject", "alice")
    assert error.value.status_code == 422


def test_provider_failure_does_not_resolve_username(monkeypatch):
    def fail(_username):
        raise keycloak_credentials.ProviderError("unavailable")

    monkeypatch.setattr(human_identity, "resolve_username", fail)
    with pytest.raises(HTTPException) as error:
        human_identity.resolve(None, None, "alice")
    assert error.value.status_code == 503
