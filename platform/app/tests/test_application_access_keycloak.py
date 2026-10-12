"""Provider checks against an isolated Keycloak; never use the installed platform realm."""
import base64
import copy
import hashlib
import os
import secrets
import subprocess
import sys
import unittest
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import httpx2 as httpx
import jwt

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from app.access_provider import KeycloakAccessProvider, audience, derived_secret
from app.access_runtime import browser_manifests, PROXY_IMAGE
from app.access_tokens import TokenVerifier
from test_application_access import GROUP, OTHER_GROUP, POLICY


class LoginForm(HTMLParser):
    action = None
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "form" and attrs.get("id") == "kc-form-login":
            self.action = attrs["action"]


@unittest.skipUnless(os.environ.get("ACCESS_TEST_KEYCLOAK_URL"), "Requires isolated ACCESS_TEST_KEYCLOAK_URL")
class KeycloakAccessTests(unittest.TestCase):
    def setUp(self):
        self.url = os.environ["ACCESS_TEST_KEYCLOAK_URL"]
        self.http = httpx.Client(timeout=10, trust_env=False)
        response = self.http.post(self.url + "/realms/master/protocol/openid-connect/token", data={
            "grant_type": "password", "client_id": "admin-cli", "username": "test-admin", "password": "test-only-password"})
        response.raise_for_status()
        self.token = response.json()["access_token"]
        self.headers = {"Authorization": "Bearer " + self.token}
        realm = self.http.post(self.url + "/admin/realms", json={"realm": "platform", "enabled": True}, headers=self.headers)
        self.assertIn(realm.status_code, {201, 409}, realm.text)
        self.env = patch.dict(os.environ, {"KEYCLOAK_INTERNAL_URL": self.url, "DATABASE_KEY": "test" * 16,
                                          "OIDC_ISSUER": self.url + "/realms/platform"})
        self.env.start()
        self.admin = patch("app.access_provider._admin_token", return_value=self.token)
        self.admin.start()
        self.provider = KeycloakAccessProvider()
        self.policy = copy.deepcopy(POLICY)
        self.policy["id"] = "pol_" + uuid4().hex
        self.policy["spec"]["applicationId"] = uuid4().hex
        self.verifier = TokenVerifier(self.url + "/realms/platform", audience(self.policy["spec"]["applicationId"]),
                                       self.url + "/realms/platform/protocol/openid-connect/certs")

    def tearDown(self):
        self.admin.stop()
        self.env.stop()
        self.http.close()

    def test_machine_audience_scoped_groups_idempotency_and_revocation(self):
        credential = uuid4().hex
        first = self.provider.service(self.policy, credential, [GROUP])
        second = self.provider.service(self.policy, credential, [GROUP])
        self.assertEqual(first, second)
        result = self.http.post(self.url + "/realms/platform/protocol/openid-connect/token", data={
            "grant_type": "client_credentials", "client_id": first["clientId"], "client_secret": first["secret"]})
        self.assertEqual(result.status_code, 200, result.text)
        verified = self.verifier.verify(result.json()["access_token"])
        self.assertEqual(verified["groups"], [GROUP])
        self.assertEqual(verified["azp"], first["clientId"])
        self.assertEqual(verified["sub"], first["subject"])
        self.provider.delete_client(first["clientId"])
        self.provider.delete_client(first["clientId"])
        retired = self.http.post(self.url + "/realms/platform/protocol/openid-connect/token", data={
            "grant_type": "client_credentials", "client_id": first["clientId"], "client_secret": first["secret"]})
        self.assertIn(retired.status_code, {400, 401})

    def test_browser_pkce_login_without_groups_then_authorized_refresh(self):
        client_id = self.provider.browser(self.policy, self.policy["spec"]["host"], [GROUP, OTHER_GROUP])
        username = "test-human-" + uuid4().hex
        user = self.http.post(self.url + "/admin/realms/platform/users", headers=self.headers, json={
            "username": username, "enabled": True, "firstName": "Test", "lastName": "Human",
            "email": username + "@example.invalid", "emailVerified": False,
            "credentials": [{"type": "password", "value": "test-human-password", "temporary": False}]})
        self.assertEqual(user.status_code, 201, user.text)
        subject = user.headers["location"].rsplit("/", 1)[1]
        verifier = secrets.token_urlsafe(48)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        redirect = "https://" + self.policy["spec"]["host"] + "/oauth2/callback"
        login = self.http.get(self.url + "/realms/platform/protocol/openid-connect/auth", params={
            "client_id": client_id, "response_type": "code", "redirect_uri": redirect,
            "scope": "openid profile email", "state": "test-state", "nonce": "test-nonce",
            "code_challenge_method": "S256", "code_challenge": challenge})
        self.assertEqual(login.status_code, 200, login.text[:200])
        form = LoginForm()
        form.feed(login.text)
        self.assertIsNotNone(form.action)
        # This disposable provider uses loopback HTTP, while the application redirect is HTTPS.
        # Keycloak marks authentication cookies Secure; production remains HTTPS end to end.
        for cookie in self.http.cookies.jar:
            cookie.secure = False
        authorized = self.http.post(form.action, data={"username": username, "password": "test-human-password", "credentialId": ""})
        self.assertEqual(authorized.status_code, 302, authorized.text[:200])
        code = parse_qs(urlparse(authorized.headers["location"]).query)["code"][0]
        result = self.http.post(self.url + "/realms/platform/protocol/openid-connect/token", data={
            "grant_type": "authorization_code", "client_id": client_id, "client_secret": derived_secret(self.policy["id"], "browser"),
            "code": code, "redirect_uri": redirect, "code_verifier": verifier})
        self.assertEqual(result.status_code, 200, result.text)
        token = result.json()
        raw = jwt.decode(token["access_token"], options={"verify_signature": False})
        self.assertFalse({"iss", "sub", "aud", "iat", "exp", "azp", "typ"} - raw.keys(), list(raw.keys()))
        self.assertIn(raw["aud"], (self.verifier.audience, [self.verifier.audience]))
        self.assertLessEqual(raw["exp"] - raw["iat"], 300)
        self.assertEqual(raw["typ"], "Bearer")
        self.assertIn(raw.get("groups", []), ([], None))
        self.assertEqual(self.verifier.verify(token["access_token"])["groups"], [])
        self.provider.set_membership(self.policy["spec"]["applicationId"], subject, [GROUP])
        refreshed = self.http.post(self.url + "/realms/platform/protocol/openid-connect/token", data={
            "grant_type": "refresh_token", "client_id": client_id, "client_secret": derived_secret(self.policy["id"], "browser"),
            "refresh_token": token["refresh_token"]})
        self.assertEqual(refreshed.status_code, 200, refreshed.text)
        self.assertEqual(self.verifier.verify(refreshed.json()["access_token"])["groups"], [GROUP])


@unittest.skipUnless(os.environ.get("ACCESS_PROXY_CONFIG_TEST"), "Requires Docker and ACCESS_PROXY_CONFIG_TEST=1")
class ProxyConfigTests(unittest.TestCase):
    def test_generated_environment_is_accepted_by_pinned_oauth2_proxy(self):
        with patch.dict(os.environ, {"DATABASE_KEY": "test" * 16, "OIDC_ISSUER": "https://identity.test/realms/platform"}):
            manifests = browser_manifests(POLICY)
        deployment = next(m for m in manifests if m["kind"] == "Deployment")
        values = {v["name"]: v["value"] for v in deployment["spec"]["template"]["spec"]["containers"][0]["env"]}
        values.update(next(m for m in manifests if m["kind"] == "Secret")["stringData"])
        result = subprocess.run(["docker", "run", "--rm", "--env-file", "/dev/stdin", PROXY_IMAGE, "--config-test"],
            input="\n".join(k + "=" + v for k, v in values.items()), text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
