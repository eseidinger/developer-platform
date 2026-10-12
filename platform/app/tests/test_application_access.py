import copy
import json
import sys
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx2 as httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from app.access_contract import PolicyCreate, canonical_path, match_route
from app.access_gateway import Snapshot, admitted_identity, create_gateway, new_session, session_state, upstream_headers
from app.access_provider import KeycloakAccessProvider
from app.access_runtime import browser_manifests, protected_ingress, shared_manifests
from app.access_tokens import TokenVerifier
from app.access_worker import roll_services
from app.manifests import component_resources


GROUP = "grp_" + "a" * 32
OTHER_GROUP = "grp_" + "b" * 32
POLICY = {"id": "pol_" + "c" * 32, "kind": "policy", "project": "provider", "name": "provider", "state": "active", "version": 1,
    "spec": {"component": "api", "defaultDecision": "deny", "identityAttributes": {"displayName": False, "email": False},
        "applicationId": "d" * 32, "host": "api-provider.apps.test", "backend": "http://api.project-provider.svc.cluster.local:8080",
        "sessionEpoch": "epoch-1", "routes": [
            {"name": "human", "match": {"pathPrefix": "/app/", "path": None, "methods": ["GET", "POST"]},
             "authentication": {"mode": "browser-session"}, "authorization": {"anyOfGroups": [GROUP]}},
            {"name": "machine", "match": {"pathPrefix": "/api/", "path": None, "methods": ["GET", "POST"]},
             "authentication": {"mode": "bearer-token"}, "authorization": {"anyOfGroups": [GROUP]}}]}}


def data():
    return {"generation": 1, "issuedAt": time.time(), "expiresAt": time.time() + 299,
        "issuer": "https://identity.test/realms/platform", "jwksUrl": "http://identity.test/certs", "policies": [copy.deepcopy(POLICY)],
        "principals": [{"id": "prn_machine", "kind": "service", "issuer": "https://identity.test/realms/platform", "subject": "machine"},
                       {"id": "prn_human", "kind": "user", "issuer": "https://identity.test/realms/platform", "subject": "human"}],
        "memberships": [{"state": "active", "spec": {"policyId": POLICY["id"], "principalId": "prn_machine", "groupId": GROUP}},
                        {"state": "active", "spec": {"policyId": POLICY["id"], "principalId": "prn_human", "groupId": GROUP}}],
        "services": [{"state": "active", "spec": {"policyId": POLICY["id"], "credentials": [
            {"state": "active", "subject": "machine", "clientId": "service-current"}]}}]}


def claims(kind="service"):
    return {"iss": "https://identity.test/realms/platform", "sub": "machine" if kind == "service" else "human",
        "azp": "service-current" if kind == "service" else "browser-" + POLICY["id"], "groups": [GROUP, OTHER_GROUP]}


class AccessContractTests(unittest.TestCase):
    def test_exact_segment_matching_and_method_rules(self):
        self.assertIsNotNone(match_route(POLICY["spec"], "/api/items", "HEAD"))
        for path, method in (("/apiculture", "GET"), ("/api/items", "OPTIONS"), ("/admin", "GET")):
            self.assertIsNone(match_route(POLICY["spec"], path, method))
        self.assertEqual(canonical_path("/api/caf%C3%A9"), "/api/café")

    def test_ambiguous_paths_and_overlapping_rules_fail(self):
        for path in ("/api/%2fsecret", "/api/%5csecret", "/api/%252e%252e", "/api/../secret", "/api/%2e%2e/secret", "/api\\x", "/api/%ZZ", "/api//x"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                canonical_path(path)
        values = {k: copy.deepcopy(POLICY["spec"][k]) for k in PolicyCreate.model_fields}
        values["routes"].append({**values["routes"][1], "name": "overlap", "match": {"path": "/api/items", "methods": ["GET"]}})
        with self.assertRaises(ValidationError):
            PolicyCreate.model_validate(values)

    def test_no_anonymous_routes_scopes_or_empty_groups(self):
        for change in ({"authentication": {"mode": "none"}}, {"authorization": {"anyOfGroups": []}}, {"scopes": ["dataset.read"]}):
            values = {k: copy.deepcopy(POLICY["spec"][k]) for k in PolicyCreate.model_fields}
            values["routes"][0].update(change)
            with self.assertRaises(ValidationError):
                PolicyCreate.model_validate(values)

    def test_membership_revocation_overrides_stale_token_for_both_kinds(self):
        for kind in ("user", "service"):
            snapshot = data()
            principal, groups = admitted_identity(snapshot, POLICY, claims(kind), "browser-session" if kind == "user" else "bearer-token")
            self.assertEqual(groups, [GROUP])
            pid = principal["id"]
            for m in snapshot["memberships"]:
                if m["spec"]["principalId"] == pid:
                    m["state"] = "revocation-pending"
            self.assertEqual(admitted_identity(snapshot, POLICY, claims(kind), "browser-session" if kind == "user" else "bearer-token")[1], [])

    def test_machine_approval_and_rotation_timeout_are_authoritative(self):
        snapshot = data()
        snapshot["services"][0]["state"] = "pending"
        with self.assertRaises(HTTPException):
            admitted_identity(snapshot, POLICY, claims(), "bearer-token")
        snapshot["services"][0]["state"] = "active"
        credential = snapshot["services"][0]["spec"]["credentials"][0]
        credential.update(state="overlap", expiresAt=(datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat())
        with self.assertRaises(HTTPException):
            admitted_identity(snapshot, POLICY, claims(), "bearer-token")

    def test_snapshot_deadline_is_not_extended_by_outage(self):
        snapshot = Snapshot()
        snapshot.load(data())
        with self.assertRaises(HTTPException) as error:
            snapshot.current(snapshot.value["expiresAt"])
        self.assertEqual(error.exception.status_code, 503)
        invalid = data()
        invalid["expiresAt"] = invalid["issuedAt"] + 301
        with self.assertRaises(ValueError):
            snapshot.load(invalid)

    def test_unsigned_external_headers_and_tokens_do_not_reach_backend(self):
        raw = [(b"authorization", b"Bearer stolen"), (b"x-platform-principal-id", b"forged"),
               (b"x-auth-request-user", b"forged"), (b"x-forwarded-user", b"forged"),
               (b"cookie", b"__Host-platform-session=secret; app-theme=dark")]
        identity, groups = admitted_identity(data(), POLICY, claims(), "bearer-token")
        headers = dict(upstream_headers(raw, identity, claims(), groups, POLICY["spec"]["identityAttributes"]))
        self.assertEqual(headers["X-Platform-Principal-Id"], "prn_machine")
        self.assertEqual(headers["cookie"], "app-theme=dark")
        self.assertNotIn("authorization", headers)
        self.assertNotIn("x-auth-request-user", headers)
        self.assertNotIn("X-Platform-Principal-Email", headers)

    def test_session_idle_absolute_and_recovery_epoch(self):
        key = "k" * 32
        for state in ({**new_session(POLICY), "last": time.time() - 1801},
                      {**new_session(POLICY), "start": time.time() - 28801},
                      {**new_session(POLICY), "epoch": "old-epoch"}):
            with self.assertRaises(HTTPException):
                session_state(jwt.encode(state, key, algorithm="HS256"), key, POLICY)

    def test_network_allows_only_authorizer_to_public_backend(self):
        components = [{"name": "api", "type": "service", "resolved_image": "example@sha256:" + "0" * 64,
                       "exposure": "public", "ports": [{"name": "http", "port": 8080}]}]
        manifests = component_resources("provider", components, "172.30.80.10", "test", domain="apps.test")
        ingress = next(m for m in manifests if m["kind"] == "Ingress")
        self.assertEqual(ingress["metadata"]["namespace"], "platform-access")
        self.assertEqual(ingress["spec"]["rules"][0]["http"]["paths"][0]["backend"]["service"]["name"], "authorizer")
        isolation = next(m for m in manifests if m["kind"] == "NetworkPolicy" and m["metadata"]["name"] == "isolation")
        self.assertEqual(isolation["spec"]["podSelector"]["matchExpressions"][0]["values"], ["api"])
        protected = next(m for m in manifests if m["kind"] == "NetworkPolicy" and m["metadata"]["name"] == "api-access")
        self.assertEqual(protected["spec"]["ingress"][0]["from"][0]["podSelector"]["matchLabels"], {"platform.example/access-role": "authorizer"})

    def test_browser_proxy_has_pkce_and_bounded_cookie_but_no_group_login_filter(self):
        with patch.dict("os.environ", {"DATABASE_KEY": "test" * 16, "OIDC_ISSUER": "https://identity.test/realms/platform"}):
            manifests = browser_manifests(POLICY)
        deployment = next(m for m in manifests if m["kind"] == "Deployment")
        env = {e["name"]: e["value"] for e in deployment["spec"]["template"]["spec"]["containers"][0]["env"]}
        self.assertEqual(env["OAUTH2_PROXY_CODE_CHALLENGE_METHOD"], "S256")
        self.assertEqual(env["OAUTH2_PROXY_COOKIE_EXPIRE"], "8h")
        self.assertEqual(env["OAUTH2_PROXY_COOKIE_REFRESH"], "4m")
        self.assertNotIn("OAUTH2_PROXY_ALLOWED_GROUPS", env)  # First-login requests need an identity without membership.


class CredentialRolloutTests(unittest.TestCase):
    def test_generated_public_and_private_deployments_receive_every_secret_version(self):
        components = [{"name": name, "type": "service", "exposure": exposure,
                       "resolved_image": "example@sha256:" + "0" * 64,
                       "ports": [{"name": "http", "port": 8080}]}
                      for name, exposure in (("api", "public"), ("worker", "private"))]
        deployments = [d for project in ("consumer", "other")
                       for d in component_resources(project, components, "172.30.80.10", "test", domain="apps.test")
                       if d["kind"] == "Deployment"]
        # Model Kubernetes label selection against object metadata, not Pod labels.
        deployments.append({"metadata": {"name": "unrelated", "namespace": "project-consumer", "labels": {}}})
        resource = Mock()
        def select(*, namespace, label_selector):
            return SimpleNamespace(items=[SimpleNamespace(metadata=SimpleNamespace(name=d["metadata"]["name"]))
                for d in deployments if d["metadata"]["namespace"] == namespace
                and label_selector in d["metadata"]["labels"]])
        resource.get.side_effect = select
        runtime = Mock()
        runtime.resources.get.return_value = resource
        for version in ("provisioned", "rotated", "revoked"):
            with self.subTest(version=version):
                resource.patch.reset_mock()
                roll_services(runtime, "consumer", version)
                runtime.resources.get.assert_called_with(api_version="apps/v1", kind="Deployment")
                resource.get.assert_called_with(namespace="project-consumer", label_selector="platform.example/component")
                self.assertEqual(resource.patch.call_count, 2)
                self.assertEqual({c.kwargs["name"] for c in resource.patch.call_args_list}, {"api", "worker"})
                for call in resource.patch.call_args_list:
                    self.assertEqual(call.kwargs["namespace"], "project-consumer")
                    self.assertEqual(call.kwargs["body"], {"spec": {"template": {"metadata": {
                        "annotations": {"platform.example/secrets-version": version}}}}})
                    self.assertEqual(call.kwargs["content_type"], "application/merge-patch+json")
                    self.assertEqual(call.kwargs["field_manager"], "developer-platform-access")


class AccessTokenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def test_wrong_audience_identity_token_and_long_lived_token_fail(self):
        verifier = TokenVerifier("https://identity.test/realms/platform", "app-test", "http://unused")
        verifier.jwks = Mock()
        verifier.jwks.get_signing_key_from_jwt.return_value.key = self.key.public_key()
        value = {**claims(), "typ": "Bearer", "aud": "app-test", "iat": int(time.time()), "exp": int(time.time()) + 300}
        self.assertEqual(verifier.verify(jwt.encode(value, self.key, algorithm="RS256"))["sub"], "machine")
        for change in ({"aud": "platform-api"}, {"typ": "ID"}, {"exp": int(time.time()) + 301},
                       {"groups": ["admin"]}, {"azp": "bad\r\nheader"}):
            with self.subTest(change=change), self.assertRaises(HTTPException) as error:
                verifier.verify(jwt.encode({**value, **change}, self.key, algorithm="RS256"))
            self.assertEqual(error.exception.status_code, 401)


class GatewayTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.backend = []
        self.human_claims = claims("user")
        async def transport(request):
            if request.url.path == "/oauth2/auth":
                return httpx.Response(202, headers={"X-Auth-Request-Access-Token": "human-token"})
            if request.url.path.endswith("/enroll"):
                return httpx.Response(200, json={"principalId": "prn_human", "requestId": "req_pending", "state": "pending"})
            self.backend.append(request)
            await request.aread()
            class Stream(httpx.AsyncByteStream):
                async def __aiter__(self):
                    yield b"accepted"
            return httpx.Response(200, stream=Stream(), headers={"Set-Cookie": "__Host-platform-session=forged; Secure; Path=/"})
        self.transport = httpx.AsyncClient(transport=httpx.MockTransport(transport))
        self.gateway = create_gateway(internal_key="i" * 32, session_key="s" * 32, client=self.transport)
        self.gateway.state.snapshot.load(data())
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.gateway), base_url="https://" + POLICY["spec"]["host"])
        self.verifier = Mock()
        self.verifier.verify.side_effect = lambda token: self.human_claims if token == "human-token" else claims()
        key = ("https://identity.test/realms/platform", POLICY["spec"]["applicationId"], "http://identity.test/certs")
        self.gateway.state.verifiers[key] = self.verifier

    async def asyncTearDown(self):
        await self.client.aclose()
        await self.transport.aclose()

    async def test_machine_request_forwards_verified_identity_and_strips_bearer(self):
        response = await self.client.get("/api/items", headers={"Authorization": "Bearer machine", "X-Platform-Principal-Id": "forged"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"accepted")
        self.assertEqual(self.backend[-1].headers["x-platform-principal-id"], "prn_machine")
        self.assertNotIn("authorization", self.backend[-1].headers)
        self.assertFalse(any("=forged" in v for v in response.headers.get_list("set-cookie")))

    async def test_missing_machine_token_never_redirects_and_cookie_never_authenticates_it(self):
        self.client.cookies.set("__Host-platform-activity", jwt.encode(new_session(POLICY), "s" * 32, algorithm="HS256"))
        response = await self.client.get("/api/items")
        self.assertEqual(response.status_code, 401)
        self.assertNotIn("location", response.headers)
        self.assertEqual(self.backend, [])

    async def test_browser_redirect_first_login_and_csrf(self):
        response = await self.client.get("/app/")
        self.assertEqual(response.status_code, 302)
        state = new_session(POLICY)
        self.client.cookies.set("__Host-platform-activity", jwt.encode(state, "s" * 32, algorithm="HS256"))
        response = await self.client.post("/app/", headers={"Origin": "https://" + POLICY["spec"]["host"]})
        self.assertEqual(response.status_code, 403)
        response = await self.client.post("/app/", headers={"Origin": "https://" + POLICY["spec"]["host"], "X-Platform-CSRF-Token": state["csrf"]})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("x-platform-csrf-token", self.backend[-1].headers)
        self.gateway.state.snapshot.value["memberships"][1]["state"] = "revocation-pending"
        response = await self.client.get("/app/")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "application_access_pending")

    async def test_app_cannot_reach_probe_routes_and_snapshot_expiry_denies(self):
        self.assertEqual((await self.client.get("/internal/live")).status_code, 403)
        self.gateway.state.snapshot.value["expiresAt"] = time.time() - 1
        response = await self.client.get("/api/items", headers={"Authorization": "Bearer machine"})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.backend, [])

    async def test_invalid_policy_compilation_immediately_loses_readiness_and_access(self):
        self.gateway.state.snapshot.compilation_failed = True
        response = await self.client.get("/api/items", headers={"Authorization": "Bearer machine"})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.backend, [])


if __name__ == "__main__":
    unittest.main()
