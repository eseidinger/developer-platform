"""Exercise profile persistence and human refresh without a real keyring or IdP."""

import json
from itertools import count
from urllib.parse import parse_qs

import httpx
import pytest

from platform_cli.authentication import HumanAuthentication
from platform_cli.profiles import Profile, ProfileStore, SessionStore


def test_profile_file_has_no_session_material(tmp_path):
    store = ProfileStore(tmp_path)
    profile = Profile("https://platform.example", "https://identity.example/realms/platform", project="orders")
    store.create("lab", profile)
    assert store.selected("lab") == ("lab", profile)
    assert store.path.stat().st_mode & 0o077 == 0
    assert "refresh_token" not in store.path.read_text()
    store.use("lab")
    assert store.selected() == ("lab", profile)
    store.delete("lab")
    assert store.selected() == (None, None)


def test_device_login_and_refresh_keep_only_refresh_material_in_keyring(monkeypatch):
    profile = Profile("https://platform.example", "https://identity.example/realms/platform")
    sessions = SessionStore("lab", profile)
    stored = {}

    class MemoryKeyring:
        def get_password(self, service, name):
            return stored.get((service, name))

        def set_password(self, service, name, value):
            stored[(service, name)] = value

        def delete_password(self, service, name):
            del stored[(service, name)]

    monkeypatch.setattr(sessions, "backend", lambda: MemoryKeyring())
    calls = []

    def handler(request):
        calls.append(request)
        path = request.url.path
        if path.endswith("/.well-known/openid-configuration"):
            issuer = profile.issuer
            return httpx.Response(200, json={"issuer": issuer,
                "token_endpoint": issuer + "/protocol/openid-connect/token",
                "device_authorization_endpoint": issuer + "/protocol/openid-connect/auth/device",
                "userinfo_endpoint": issuer + "/protocol/openid-connect/userinfo"})
        if path.endswith("/auth/device"):
            values = parse_qs(request.content.decode())
            assert values["client_id"] == ["platform-cli"]
            assert values["code_challenge_method"] == ["S256"]
            assert "code_challenge" in values
            return httpx.Response(200, json={"device_code": "device-code", "user_code": "user-code",
                                             "verification_uri": "https://identity.example/verify",
                                             "expires_in": 30, "interval": 1})
        if path.endswith("/token"):
            values = parse_qs(request.content.decode())
            if values["grant_type"] == ["urn:ietf:params:oauth:grant-type:device_code"]:
                assert "code_verifier" in values
                if sum(1 for item in calls if item.url.path.endswith("/token")) == 1:
                    return httpx.Response(400, json={"error": "authorization_pending"})
                return httpx.Response(200, json={"access_token": "access-one", "token_type": "Bearer",
                                                 "refresh_token": "refresh-one", "expires_in": 60})
            assert values["refresh_token"] == ["refresh-one"]
            return httpx.Response(200, json={"access_token": "access-two", "token_type": "Bearer",
                                             "refresh_token": "refresh-two", "expires_in": 60})
        if path.endswith("/userinfo"):
            return httpx.Response(200, json={"sub": "human-subject"})
        raise AssertionError(path)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    auth = HumanAuthentication(profile, sessions, client)
    times = count()
    subject = auth.login(lambda uri, code: None, clock=lambda: next(times), sleep=lambda seconds: None)
    assert subject == "human-subject"
    assert sessions.get()["refresh_token"] == "refresh-one"
    assert "access-one" not in json.dumps(list(stored.values()))
    assert auth.refresh().access_token == "access-two"
    assert sessions.get()["refresh_token"] == "refresh-two"


def test_profile_rejects_embedded_url_credentials():
    with pytest.raises(ValueError):
        Profile("https://user:password@platform.example", "https://identity.example")
