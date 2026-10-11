"""Repeatable live acceptance with explicit scope, private journaling and safe evidence.

No invocation deploys/upgrades the platform, publishes images, or deletes a
database. `plan` is offline. `run` creates only uniquely named fixture resources.
Recovery requires separate consent and an otherwise empty lab. Outage drills
remain explicitly deferred; this harness does not stop platform services.
"""
import argparse
import base64
import copy
import hashlib
import ipaddress
import json
import os
import re
import secrets
import stat
import subprocess
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import httpx2 as httpx
import jwt


ROOT = Path(__file__).resolve().parents[2]
RUN_PATTERN = re.compile(r"[0-9a-f]{12}")
IMAGE_PATTERN = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9._:/-]+@sha256:[0-9a-f]{64}")
DEFERRED = ["real-backup-restore", "browser-30-minute-idle-and-8-hour-absolute-expiry",
            "24-hour-rotation-adoption-timeout", "30/90-day-request-retention",
            "component-monitoring-and-central-log-retention", "control-plane-outage",
            "dns-address-change-reapply", "held-machine-token-expiry",
            "recovery-reconciliation-rehearsal", "external-use-case-suite"]


class DrillError(Exception):
    """A fixed safe code, never a dependency exception or response body."""


def require(condition, code):
    if not condition:
        raise DrillError(code)


def utc():
    return datetime.now(timezone.utc).isoformat()


def origin(url, *, internal=False):
    parts = urlsplit(url)
    require(not parts.username and not parts.password and not parts.query and not parts.fragment,
            "invalid_origin")
    require(parts.hostname and parts.path in ("", "/"), "invalid_origin")
    allowed_http = parts.hostname in {"localhost", "127.0.0.1", "::1"}
    if internal and parts.hostname:
        try:
            allowed_http = ipaddress.ip_address(parts.hostname).is_private
        except ValueError:
            pass
    require(parts.scheme == "https" or (parts.scheme == "http" and allowed_http), "https_required")
    return urlunsplit((parts.scheme, parts.netloc, "", "", ""))


def private_text(path):
    path = Path(path)
    require(not path.is_symlink() and path.is_file(), "private_file_missing")
    require(stat.S_IMODE(path.stat().st_mode) & 0o077 == 0, "private_file_permissions")
    return path.read_text()


def settings(path):
    values = {}
    for line in private_text(path).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, value = line.split("=", 1)
        require(re.fullmatch(r"[A-Z][A-Z0-9_]*", key), "invalid_settings")
        values[key] = value
    return values


def fingerprint(value):
    return hashlib.sha256(value.encode()).hexdigest()


def project_names(run_id):
    require(RUN_PATTERN.fullmatch(run_id), "invalid_run_id")
    return {role: "ha-" + run_id + "-" + role for role in ("provider", "consumer")}


def declaration(project, role, image, run_id, provider_url, issuer):
    names = project_names(run_id)
    require(project == names[role] and IMAGE_PATTERN.fullmatch(image), "invalid_fixture_declaration")
    outbound = [{"dns": urlsplit(url).hostname, "port": 443} for url in (provider_url, issuer)] if role == "consumer" else []
    limits = {"requests": {"cpu": "50m", "memory": "64Mi"}, "limits": {"cpu": "250m", "memory": "128Mi"}}
    def component(name, public):
        return {"name": name, "type": "service", "runtime": {"type": "container", "image": image,
                    **({"args": ["fixture.py", "--worker"], "command": ["python"]} if not public else {})},
            "ports": [{"name": "http", "protocol": "http", "port": 8080}],
            "replicas": 1, "exposure": "public" if public else "private", "resources": copy.deepcopy(limits),
            "health": {"readiness": {"path": "/health/ready", "port": 8080}},
            "outbound": copy.deepcopy(outbound) if public else []}
    return {"apiVersion": "platform.example/v1alpha2", "kind": "Application", "metadata": {"name": project},
        "spec": {"components": [component("api", True), component("worker", False)],
            "configuration": {"values": {"ACCEPTANCE_RUN_ID": run_id, "FIXTURE_ROLE": role,
                                            "PROVIDER_URL": provider_url}},
            "resources": [{"name": "state", "type": "postgres", "profile": "shared-dev", "deletionPolicy": "retain"}]}}


def access_policy(readers, humans, administrators):
    def route(name, prefix, mode, groups, methods):
        return {"name": name, "match": {"pathPrefix": prefix, "methods": methods},
                "authentication": {"mode": mode}, "authorization": {"anyOfGroups": groups}}
    return {"component": "api", "defaultDecision": "deny", "identityAttributes": {"displayName": False, "email": False},
        "routes": [route("browser", "/app/", "browser-session", [humans], ["GET", "POST"]),
            route("machine", "/api/", "bearer-token", [readers], ["GET", "POST"]),
            route("machine-admin", "/machine-admin/", "bearer-token", [administrators], ["GET"])]}


class Journal:
    """Evidence is a whitelist; recovery handles are private and contain NO credentials."""
    def __init__(self, directory, api, run_id, *, resume=False):
        self.directory = Path(directory)
        require(not self.directory.is_symlink(), "unsafe_output_directory")
        if resume:
            self.state = json.loads(private_text(self.directory / "state.json"))
            self.report = json.loads(private_text(self.directory / "report.json"))
            require(self.state["runId"] == run_id and self.state["api"] == api, "journal_scope_mismatch")
            require(self.state["projects"] == project_names(run_id), "journal_scope_mismatch")
        else:
            require(not self.directory.exists(), "run_directory_exists")
            self.directory.mkdir(parents=True, mode=0o700)
            self.state = {"runId": run_id, "api": api, "projects": project_names(run_id),
                          "createdProjects": [], "personas": [], "human": None, "clients": []}
            self.report = {"format": 1, "runId": run_id, "startedAt": utc(), "result": "running",
                           "gateClosed": False, "checks": [], "deferred": list(DEFERRED)}
            self.save()

    def save(self):
        for name, value in (("state.json", self.state), ("report.json", self.report)):
            path = self.directory / name
            require(not path.is_symlink(), "unsafe_output_file")
            temporary = self.directory / ("." + name + "." + uuid4().hex + ".tmp")
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w") as output:
                json.dump(value, output, indent=2)
                output.write("\n")
            os.replace(temporary, path)

    def check(self, name, passed, **measurements):
        require(re.fullmatch(r"[a-z0-9-]+", name), "invalid_check_name")
        # Dependency payloads, free-form errors, identifiers and arbitrary strings are forbidden.
        require(all(isinstance(v, (bool, int, float)) and not isinstance(v, str) for v in measurements.values()),
                "unsafe_evidence")
        require(all(re.fullmatch(r"[a-zA-Z]+", k) for k in measurements), "unsafe_evidence")
        self.report["checks"].append({"name": name, "result": "passed" if passed else "failed",
                                       "at": utc(), **measurements})
        self.save()
        print(("PASS " if passed else "FAIL ") + name, flush=True)
        require(passed, name)


def wait_for(check, code, seconds=180, *, clock=time.monotonic, sleep=time.sleep):
    deadline = clock() + seconds
    next_notice = clock() + 30
    while True:
        result = check()
        if result:
            return result
        if clock() >= deadline:
            raise DrillError(code)
        if clock() >= next_notice:
            print("WAIT " + code, flush=True)
            next_notice = clock() + 30
        sleep(min(2, max(0, deadline - clock())))


class Tokens:
    def __init__(self, token=None, client=None, refresh=None):
        self.token, self.client, self.refresh = token, client, refresh

    def get(self):
        if self.refresh:
            claims = jwt.decode(self.token, options={"verify_signature": False})  # Expiry scheduling ONLY.
            if claims["exp"] <= time.time() + 45:
                self.token, self.refresh = self.client.refresh(self.refresh)
        return self.token


class API:
    def __init__(self, url, tokens):
        self.url, self.tokens = origin(url), tokens
        self.http = httpx.Client(timeout=20, follow_redirects=False, trust_env=False)

    def request(self, method, path, body=None, *, etag=None, key=None, statuses=(200,)):
        require(path.startswith("/") and not path.startswith("//"), "invalid_api_path")
        headers = {"Authorization": "Bearer " + self.tokens.get()}
        if etag is not None:
            headers["If-Match"] = '"' + str(etag) + '"'
        if key:
            headers["Idempotency-Key"] = key
        result = self.http.request(method, self.url + path, json=body, headers=headers)
        require(result.status_code in statuses, "control_api_http_" + str(result.status_code))
        return result.json()

    def operation(self, response, seconds=180):
        path = response["status_url"]
        require(re.fullmatch(r"/v1/(?:access-)?operations/[0-9a-f-]+", path), "invalid_operation_url")
        def finished():
            row = self.request("GET", path)
            require(row["state"] != "failed", "operation_failed")
            return row if row["state"] == "succeeded" else None
        return wait_for(finished, "operation_pending", seconds)


class Form(HTMLParser):
    def __init__(self):
        super().__init__()
        self.action = None
        self.hidden = {}
        self.inside = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "form" and attrs.get("id") == "kc-form-login":
            self.action, self.inside = attrs.get("action"), True
        if self.inside and tag == "input" and attrs.get("type") == "hidden" and attrs.get("name"):
            self.hidden[attrs["name"]] = attrs.get("value", "")

    def handle_endtag(self, tag):
        if tag == "form":
            self.inside = False


def submit_login(http, page, issuer, username, password):
    form = Form()
    form.feed(page.text)
    require(form.action is not None, "login_form_missing")
    target, trusted = urlsplit(form.action), urlsplit(issuer)
    require((target.scheme, target.netloc) == (trusted.scheme, trusted.netloc)
            and target.path.startswith(trusted.path + "/login-actions/"), "untrusted_login_destination")
    return http.post(form.action, data={**form.hidden, "username": username, "password": password,
                                      "credentialId": ""})


class Keycloak:
    def __init__(self, config):
        self.issuer = config.get("OIDC_ISSUER") or "https://" + config["IDENTITY_DOMAIN"] + "/realms/platform"
        require(urlsplit(self.issuer).path == "/realms/platform", "unsupported_realm")
        origin(urlunsplit((*urlsplit(self.issuer)[:2], "", "", "")))
        self.internal = origin("http://" + config.get("KEYCLOAK_IP", "172.30.80.12") + ":8080", internal=True)
        self.provisioner_secret = config["KEYCLOAK_PROVISIONER_SECRET"]
        self.http = httpx.Client(timeout=15, follow_redirects=False, trust_env=False)

    def admin(self, method, path, body=None, statuses=(200, 201, 204)):
        result = self.http.post(self.internal + "/realms/platform/protocol/openid-connect/token", data={
            "grant_type": "client_credentials", "client_id": "platform-credential-provisioner",
            "client_secret": self.provisioner_secret})
        require(result.status_code == 200, "identity_provisioner_unavailable")
        result = self.http.request(method, self.internal + "/admin/realms/platform/" + path,
                                  json=body, headers={"Authorization": "Bearer " + result.json()["access_token"]})
        require(result.status_code in statuses, "identity_admin_http_" + str(result.status_code))
        return result

    def client(self, run_id, suffix, audience, *, browser=False):
        client_id, secret = "ha-" + run_id + "-" + suffix, secrets.token_urlsafe(32)
        representation = {"clientId": client_id, "enabled": True, "protocol": "openid-connect", "publicClient": False,
            "secret": secret, "standardFlowEnabled": browser, "serviceAccountsEnabled": not browser,
            "directAccessGrantsEnabled": False, "fullScopeAllowed": False,
            "defaultClientScopes": ["basic"] if browser else [], "optionalClientScopes": [],
            "redirectUris": ["https://" + urlsplit(self.issuer).hostname + "/acceptance/callback"] if browser else [],
            "attributes": {"access.token.lifespan": "300", "pkce.code.challenge.method": "S256"},
            "protocolMappers": [{"name": "target", "protocol": "openid-connect", "protocolMapper": "oidc-audience-mapper",
                "config": {"included.client.audience": audience, "access.token.claim": "true", "id.token.claim": "false"}}]}
        existing = self.admin("GET", "clients", statuses=(200,)).json()
        require(not any(c["clientId"] == client_id for c in existing), "identity_client_collision")
        self.admin("POST", "clients", representation)
        found = self.admin("GET", "clients?clientId=" + client_id, statuses=(200,)).json()
        require(len(found) == 1, "identity_client_missing")
        return {"id": found[0]["id"], "clientId": client_id}, secret, representation["redirectUris"]

    def human(self, run_id):
        username, password = "ha-" + run_id + "-human", secrets.token_urlsafe(24)
        result = self.admin("POST", "users", {"username": username, "enabled": True, "firstName": "Synthetic",
            "lastName": "Fixture", "email": username + "@example.invalid", "emailVerified": False,
            "credentials": [{"type": "password", "value": password, "temporary": False}]})
        subject = result.headers["location"].rsplit("/", 1)[1]
        return {"id": subject, "username": username}, password


class OperatorRefresh:
    """Renew an existing operator's public-client session; never persist renewed tokens."""
    def __init__(self, keycloak, client_id):
        require(client_id in {"platform-cli", "platform-portal"}, "unsupported_operator_client")
        self.keycloak, self.client_id = keycloak, client_id

    def refresh(self, refresh):
        result = self.keycloak.http.post(self.keycloak.issuer + "/protocol/openid-connect/token", data={
            "grant_type": "refresh_token", "client_id": self.client_id, "refresh_token": refresh})
        require(result.status_code == 200, "operator_token_refresh_failed")
        payload = result.json()
        return payload["access_token"], payload["refresh_token"]


class Kube:
    def __init__(self, config):
        self.command = [str(config), "--kubeconfig", str(ROOT / ".runtime/admin.kubeconfig")]

    def call(self, *args, data=None, timeout=30):
        result = subprocess.run(self.command + list(args), input=data, text=True, capture_output=True, timeout=timeout)
        require(result.returncode == 0, "kubernetes_command_failed")
        return result.stdout

    def obj(self, kind, name, namespace):
        return json.loads(self.call("-n", namespace, "get", kind, name, "-o", "json"))

    def binding(self, project, prefix):
        require(re.fullmatch(r"ACCESS_[0-9A-F]{12}", prefix), "invalid_binding_prefix")
        # Only a known fixture project's secret is read, and values never enter evidence/state.
        secret = self.obj("secret", "app-secrets", "project-" + project)["data"]
        return {suffix: base64.b64decode(secret[prefix + "_" + suffix]).decode()
                for suffix in ("CLIENT_ID", "CLIENT_SECRET", "TOKEN_URL")}

    def exec_json(self, project, component, script, body):
        result = self.call("-n", "project-" + project, "exec", "-i", "deploy/" + component,
                           "--", "python", "-c", script, data=json.dumps(body), timeout=45)
        return json.loads(result)


NETWORK_PROBE = """import json,socket,sys
p=json.load(sys.stdin)
addresses=socket.getaddrinfo(p['host'],p['port'],type=socket.SOCK_STREAM)
results=[]
for family,kind,proto,_,address in addresses:
    sock=socket.socket(family,kind,proto);sock.settimeout(2)
    try:
        sock.connect(address);results.append(True)
    except TimeoutError:
        results.append(False)
    except OSError:
        print(json.dumps({'resolved':True,'blocked':False,'unexpectedNetworkError':True}));sys.exit(0)
    finally:
        sock.close()
print(json.dumps({'resolved':bool(addresses),'blocked':bool(results) and not any(results)}))
"""


class MachineTokens(Tokens):
    def __init__(self, credentials):
        super().__init__()
        endpoint = urlsplit(credentials["TOKEN_URL"])
        require(endpoint.scheme == "https" and endpoint.hostname and not endpoint.username
                and not endpoint.password and not endpoint.query and not endpoint.fragment,
                "unsafe_token_endpoint")
        self.credentials = credentials
        self.http = httpx.Client(timeout=15, follow_redirects=False, trust_env=False)

    def get(self):
        if self.token and jwt.decode(self.token, options={"verify_signature": False})["exp"] > time.time() + 45:
            return self.token
        value = self.credentials
        result = self.http.post(value["TOKEN_URL"], data={"grant_type": "client_credentials",
            "client_id": value["CLIENT_ID"], "client_secret": value["CLIENT_SECRET"]})
        require(result.status_code == 200, "service_token_unavailable")
        self.token = result.json()["access_token"]
        return self.token


class Drill:
    def __init__(self, args, journal, api, keycloak, kube):
        self.args, self.journal, self.api, self.keycloak, self.kube = args, journal, api, keycloak, kube
        self.run_id = journal.state["runId"]
        self.projects = project_names(self.run_id)
        self.urls = {role: "https://api-" + project + "." + args.apps_domain for role, project in self.projects.items()}
        self.owners, self.policies, self.groups = {}, {}, {}
        self.public = httpx.Client(timeout=15, follow_redirects=False, trust_env=False)
        self.browser = httpx.Client(timeout=20, follow_redirects=False, trust_env=False)

    def check(self, name, condition, **measurements):
        self.journal.check(name, condition, **measurements)

    def resource(self, role, kind, rid=None):
        return "/v1/projects/" + self.projects[role] + "/" + kind + ("/" + rid if rid else "")

    def policy_path(self, role):
        return self.resource(role, "applications") + "/" + self.projects[role] + "/access-policy"

    def fetch_service(self, row):
        rows = self.api.request("GET", "/v1/projects/" + row["project"] + "/service-access-requests")["items"]
        return next(r for r in rows if r["id"] == row["id"])

    def public_call(self, path, token=None, *, role="provider", method="GET", headers=None, body=None):
        return self.public.request(method, self.urls[role] + path, json=body,
            headers={**({"Authorization": "Bearer " + token} if token else {}), **(headers or {})})

    def approved_identity(self, token, *, role="provider"):
        result = self.public_call("/api/identity", token, role=role)
        require(result.status_code == 200, "approved_request_failed")
        data = result.json()
        require(data["fixtureVersion"] == 1 and data["runId"] == self.run_id, "wrong_fixture")
        require(not data["authorizationPresent"] and not data["platformCookiePresent"], "credential_forwarded")
        principal = data["principal"]
        require(principal["Kind"] == "service" and principal["Id"] and principal["Client-Id"], "identity_headers_missing")
        return principal

    def browser_follow(self, response):
        allowed = {origin(self.urls["provider"]), origin(self.keycloak.issuer.split("/realms/")[0])}
        for _ in range(12):
            if response.status_code not in (302, 303):
                return response
            target = str(response.url.join(response.headers["location"]))
            parts = urlsplit(target)
            require(urlunsplit((parts.scheme, parts.netloc, "", "", "")) in allowed, "untrusted_browser_redirect")
            response = self.browser.get(target)
        raise DrillError("browser_redirect_loop")

    def browser_login(self, username, password):
        response = self.browser_follow(self.browser.get(self.urls["provider"] + "/app/identity"))
        if response.status_code == 200 and "kc-form-login" in response.text:
            response = self.browser_follow(submit_login(self.browser, response, self.keycloak.issuer, username, password))
        return response

    def bootstrap(self):
        human, password = self.keycloak.human(self.run_id)
        self.journal.state["human"] = human
        self.journal.state["issuer"] = self.keycloak.issuer
        self.journal.save()
        self.api.request("PUT", "/platform/grants", {"issuer": self.keycloak.issuer, "subject": human["id"],
                                                     "role": "platform-admin"})
        return human, password

    def setup(self):
        capabilities = self.api.request("GET", "/v1/capabilities")
        require(set(capabilities["hostedApplicationAccess"]["modes"]) == {"browser-session", "bearer-token"},
                "hosted_access_not_installed")
        self.journal.state["image"] = self.args.fixture_image
        self.journal.state["appsDomain"] = self.args.apps_domain
        self.journal.state["marker"] = "durable-" + self.run_id
        self.journal.save()
        operation_ids = {}
        human, password = self.bootstrap()
        for role, project in self.projects.items():
            self.api.request("POST", "/projects", {"name": project}, statuses=(201,))
            self.journal.state["createdProjects"].append(project)
            self.journal.save()
            persona = self.api.request("POST", "/platform/test-identities", {"name": "ha-" + self.run_id + "-" + role,
                "role": "project-admin", "project": project, "test_run_id": self.run_id, "expires_in_hours": 2}, statuses=(201,))
            self.journal.state["personas"].append(persona["credential_id"])
            self.journal.save()
            owner = API(self.api.url, MachineTokens({"CLIENT_ID": persona["client_id"], "CLIENT_SECRET": persona["client_secret"],
                                                     "TOKEN_URL": persona["token_endpoint"]}))
            self.owners[role] = owner
            spec = declaration(project, role, self.args.fixture_image, self.run_id, self.urls["provider"], self.keycloak.issuer)
            deployed = owner.request("PUT", "/projects/" + project, spec, etag=0, statuses=(202,))
            operation = owner.operation(deployed)
            require(re.fullmatch(r"[0-9a-f-]{36}", deployed["operation_id"]), "invalid_operation_id")
            operation_ids[role] = {"deployment": deployed["operation_id"]}
            self.journal.state[role + "Revision"] = operation["revision"]
            self.kube.call("-n", "project-" + project, "rollout", "status", "deployment/api", "--timeout=120s", timeout=130)
            self.kube.call("-n", "project-" + project, "rollout", "status", "deployment/worker", "--timeout=120s", timeout=130)
            for component in ("api", "worker"):
                deployment = self.kube.obj("deployment", component, "project-" + project)
                require(deployment["spec"]["template"]["spec"]["containers"][0]["image"] == self.args.fixture_image,
                        "fixture_image_mismatch")
                require(deployment["spec"]["template"]["spec"]["containers"][0]["resources"]
                        == spec["spec"]["components"][0]["resources"], "fixture_resource_mismatch")
            owner.request("PUT", "/v1/projects/" + project + "/governance", {
                "maximumDataClassification": "Internal", "maximumTelemetryClassification": "Internal",
                "personalData": False, "domainRetentionOwner": "Acceptance operator",
                "domainRetentionPolicy": "Synthetic markers only. Retire on exit; retained database purge requires separate operator approval.",
                "purgeAuthority": "Acceptance operator", "recoveryOwner": "Acceptance operator"})
            groups = {}
            for name in ("readers", "humans", "administrators"):
                row = owner.request("POST", self.resource(role, "application-groups"),
                    {"name": name, "displayName": name.capitalize()}, key=self.run_id + "-" + name, statuses=(201,))
                groups[name] = row["id"]
            self.groups[role] = groups
            policy = owner.request("PUT", self.policy_path(role), access_policy(groups["readers"], groups["humans"], groups["administrators"]), statuses=(202,))
            owner.operation(policy)
            require(re.fullmatch(r"[0-9a-f-]{36}", policy["operation_id"]), "invalid_operation_id")
            operation_ids[role]["policy"] = policy["operation_id"]
            self.policies[role] = owner.request("GET", self.policy_path(role))
        self.journal.report["fixture"] = {"image": self.args.fixture_image, "projects": self.projects,
            "urls": self.urls, "revisions": {r: self.journal.state[r + "Revision"] for r in self.projects},
            "operationIds": operation_ids, "resourcesPerComponent": spec["spec"]["components"][0]["resources"]}
        self.journal.save()
        self.check("digest-pinned-multi-component-readiness", True, projects=2, components=4)
        return human, password

    def service(self, consumer, provider):
        row = self.owners[consumer].request("POST", self.resource(consumer, "service-access-requests"), {
            "name": "reader", "providerProject": self.projects[provider], "application": self.projects[provider],
            "projectWideCredential": True}, key=self.run_id + "-reader", statuses=(201,))
        require(row["state"] == "pending" and row["spec"]["credentials"] == [], "unapproved_credential_exists")
        wrong = self.owners[consumer].request("POST", self.resource(consumer, "service-access-requests", row["id"]) + "/approve",
            {"groups": [self.groups[provider]["readers"]]}, etag=row["version"], statuses=(404,))
        require("detail" in wrong, "consumer_approved_provider_access")
        approved = self.owners[provider].request("POST", self.resource(provider, "service-access-requests", row["id"]) + "/approve",
            {"groups": [self.groups[provider]["readers"]]}, etag=row["version"], statuses=(202,))
        self.owners[provider].operation(approved)
        row = self.fetch_service(row)
        require(row["state"] == "active", "service_not_active")
        return row, MachineTokens(self.kube.binding(row["project"], row["spec"]["secretPrefix"]))

    def human_checks(self, human, password):
        pending = self.browser_login(human["username"], password)
        self.check("human-platform-admin-first-login-pending", pending.status_code == 403
                   and pending.json().get("code") == "application_access_pending")
        request_id = pending.json()["requestId"]
        rows = self.owners["provider"].request("GET", self.resource("provider", "application-access-requests"))["items"]
        row = next(r for r in rows if r["id"] == request_id)
        granted = self.owners["provider"].request("POST", self.resource("provider", "application-access-requests", request_id) + "/approve",
            {"groups": [self.groups["provider"]["humans"]]}, etag=row["version"], statuses=(202,))
        # Human approval has multiple membership operations, not a single status URL.
        def effective():
            result = self.browser.get(self.urls["provider"] + "/app/identity")
            require(result.status_code in (200, 403), "browser_refresh_failed")
            return result if result.status_code == 200 else None
        started = time.monotonic()
        approved = wait_for(effective, "human_claim_refresh", 305)
        principal = approved.json()["principal"]
        self.check("human-approval-and-bounded-claim-refresh", principal["Kind"] == "user"
                   and principal["Group-Ids"] == self.groups["provider"]["humans"], seconds=round(time.monotonic() - started, 3))
        self.check("optional-personal-attributes-withheld", principal["Name"] is None and principal["Email"] is None)
        cookies = [c for c in self.browser.cookies.jar if c.name.startswith("__Host-platform-")]
        self.check("browser-secure-cookie-boundary", bool(cookies) and all(c.secure and c.path == "/" and not c.domain_specified
            for c in cookies) and all(c.has_nonstandard_attr("HttpOnly") for c in cookies if c.name != "__Host-platform-csrf"))
        denied = self.browser.post(self.urls["provider"] + "/app/identity")
        valid = self.browser.post(self.urls["provider"] + "/app/identity", headers={
            "Origin": self.urls["provider"], "X-Platform-CSRF-Token": self.browser.cookies.get("__Host-platform-csrf")})
        self.check("browser-csrf", denied.status_code == 403 and valid.status_code == 200)
        self.keycloak.admin("PUT", "users/" + human["id"], {"firstName": "Renamed", "lastName": "Fixture"})
        self.browser.cookies.clear()
        renamed = self.browser_login(human["username"], password)
        self.check("human-stable-identity-after-rename", renamed.status_code == 200 and renamed.json()["principal"]["Id"] == principal["Id"])
        self.journal.state["humanPrincipalHash"] = fingerprint(principal["Id"])
        self.journal.save()
        return principal["Id"]

    def machine_checks(self, service, machines, wrong_machines):
        token = machines.get()
        principal = self.approved_identity(token)
        decoded = jwt.decode(token, options={"verify_signature": False})
        self.check("machine-audience-and-client-scoped-groups", decoded["aud"] == service["spec"]["audience"]
            and decoded.get("groups") == [self.groups["provider"]["readers"]]
            and decoded["exp"] - decoded["iat"] <= 300 and principal["Group-Ids"] == self.groups["provider"]["readers"])
        self.journal.state["machinePrincipalHash"] = fingerprint(principal["Id"])
        self.journal.save()
        for name, path, sent, expected in (("missing-token", "/api/identity", None, 401),
                ("invalid-token", "/api/identity", "invalid", 401),
                ("wrong-audience", "/api/identity", wrong_machines.get(), 401),
                ("wrong-group", "/machine-admin/identity", token, 403),
                ("unmatched-route", "/not-configured", token, 403),
                ("segment-prefix", "/apiculture/identity", token, 403),
                ("encoded-slash", "/api/%2Fidentity", token, 400)):
            result = self.public_call(path, sent)
            self.check(name, result.status_code == expected and "location" not in result.headers, httpStatus=result.status_code)
        head = self.public_call("/api/identity", token, method="HEAD")
        options = self.public_call("/api/identity", token, method="OPTIONS")
        self.check("head-and-explicit-options", head.status_code == 200 and options.status_code == 403)
        forged = self.public_call("/api/identity", token, headers={"X-Platform-Principal-Id": "forged",
            "X-Platform-Principal-Group-Ids": "forged", "X-Platform-Principal-Kind": "user", "X-Original-URL": "/machine-admin/identity"})
        self.check("forged-headers-replaced-and-bearer-stripped", forged.status_code == 200
            and forged.json()["principal"] == principal and not forged.json()["authorizationPresent"])
        client, secret, _ = self.keycloak.client(self.run_id, "unapproved", service["spec"]["audience"])
        self.journal.state["clients"].append(client)
        self.journal.save()
        unapproved = MachineTokens({"CLIENT_ID": client["clientId"], "CLIENT_SECRET": secret,
                                   "TOKEN_URL": self.keycloak.issuer + "/protocol/openid-connect/token"})
        self.check("valid-but-unapproved-machine", self.public_call("/api/identity", unapproved.get()).status_code == 403)
        self.kube.call("-n", "project-" + self.projects["consumer"], "rollout", "status", "deployment/api", "--timeout=120s", timeout=130)
        self.kube.call("-n", "project-" + self.projects["consumer"], "rollout", "status", "deployment/worker", "--timeout=120s", timeout=130)
        binding = self.kube.exec_json(self.projects["consumer"], "worker", "import hashlib,json,os,sys; p=json.load(sys.stdin); "
            "v=os.environ.get(p['prefix']+'_CLIENT_ID',''); print(json.dumps({'present':bool(v) and bool(os.environ.get(p['prefix']+'_CLIENT_SECRET')) "
            "and bool(os.environ.get(p['prefix']+'_TOKEN_URL')), 'matches':hashlib.sha256(v.encode()).hexdigest()==p['clientHash']}))",
            {"prefix": service["spec"]["secretPrefix"], "clientHash": fingerprint(principal["Client-Id"])})
        self.check("project-wide-binding-visible-to-private-worker", binding.get("present") and binding.get("matches"))
        probe = self.public_call("/api/probe", wrong_machines.get(), role="consumer",
                                 headers={"X-Correlation-Id": self.run_id})
        self.check("consumer-public-https-managed-binding", probe.status_code == 200 and probe.json()["providerStatus"] == 200
                   and probe.json()["provider"]["principal"]["Id"] == principal["Id"])
        self.check("synthetic-cross-project-correlation", probe.json()["provider"]["correlationHash"] == fingerprint(self.run_id))
        return principal

    def network_checks(self):
        backend = "api.project-" + self.projects["provider"] + ".svc.cluster.local"
        for role in ("provider", "consumer"):
            result = self.kube.exec_json(self.projects[role], "worker", NETWORK_PROBE, {"host": backend, "port": 8080})
            self.check(role + "-direct-backend-bypass-denied", result.get("resolved") and result.get("blocked"))
        result = self.kube.exec_json(self.projects["consumer"], "api", NETWORK_PROBE,
                                     {"host": self.args.unrelated_host, "port": 443})
        self.check("unrelated-egress-denied", result.get("resolved") and result.get("blocked"))
        policy = self.kube.obj("networkpolicy", "api-egress", "project-" + self.projects["consumer"])
        destinations = [peer["ipBlock"]["cidr"] for rule in policy["spec"]["egress"] for peer in rule.get("to", []) if "ipBlock" in peer]
        self.check("dns-egress-pinned-to-host-addresses", bool(destinations) and all(ipaddress.ip_network(c).prefixlen
            == ipaddress.ip_network(c).max_prefixlen for c in destinations), addresses=len(destinations))
        self.journal.report["pinnedEgressCidrs"] = sorted(destinations)
        self.journal.save()

    def persistence(self, machines, other):
        marker = self.journal.state["marker"]
        written = self.public_call("/api/state", machines.get(), method="POST", body={"marker": marker})
        isolated = self.public_call("/api/state", other.get(), role="consumer")
        self.check("separate-project-postgresql-state", written.status_code == 200 and isolated.status_code == 200
                   and isolated.json()["marker"] != marker)
        operation = self.api.request("POST", "/projects/" + self.projects["provider"] + "/restart", statuses=(202,))
        restarted = self.api.operation(operation)
        self.check("restart-preserves-provider-revision", restarted["revision"] == self.journal.state["providerRevision"])
        self.kube.call("-n", "project-" + self.projects["provider"], "rollout", "status", "deployment/api", "--timeout=120s", timeout=130)
        read = self.public_call("/api/state", machines.get())
        self.check("state-retained-after-restart", read.status_code == 200 and read.json()["marker"] == marker)

    def policy_checks(self, machines):
        owner = self.owners["provider"]
        current = owner.request("GET", self.policy_path("provider"))
        fields = ("component", "defaultDecision", "identityAttributes", "routes")
        body = {k: copy.deepcopy(current["spec"][k]) for k in fields}
        invalid = copy.deepcopy(body)
        invalid["routes"].append({**invalid["routes"][0], "name": "overlap"})
        owner.request("PUT", self.policy_path("provider"), invalid, etag=current["version"], statuses=(422,))
        self.check("overlapping-policy-rejected", True)
        body["routes"][1]["match"]["pathPrefix"] = "/api/state"
        changed = owner.request("PUT", self.policy_path("provider"), body, etag=current["version"], statuses=(202,))
        owner.operation(changed)
        wait_for(lambda: self.public_call("/api/identity", machines.get()).status_code == 403,
                 "restrictive_policy_activation", 60)
        self.check("restrictive-policy-activation", True)
        current = owner.request("GET", self.policy_path("provider"))
        rollback = owner.request("POST", self.policy_path("provider") + "/rollback", etag=current["version"], statuses=(202,))
        owner.operation(rollback)
        wait_for(lambda: self.public_call("/api/identity", machines.get()).status_code == 200,
                 "policy_rollback_activation", 60)
        self.check("immutable-policy-rollback", True)

    def rotate(self, service, machines, *, emergency=False):
        service = self.fetch_service(service)
        token = machines.get()
        previous = self.approved_identity(token)
        path = self.resource("consumer", "service-access-requests", service["id"])
        rotated = self.owners["consumer"].request("POST", path + "/rotate", {"emergency": emergency},
                                                  etag=service["version"], statuses=(202,))
        self.owners["consumer"].operation(rotated)
        service = self.fetch_service(service)
        replacement = MachineTokens(self.kube.binding(service["project"], service["spec"]["secretPrefix"]))
        wait_for(lambda: self.public_call("/api/identity", replacement.get()).status_code == 200,
                 "replacement_activation", 60)
        current = self.approved_identity(replacement.get())
        self.check("emergency-stable-principal" if emergency else "normal-rotation-stable-principal",
                   current["Id"] == previous["Id"] and current["Client-Id"] != previous["Client-Id"])
        if not emergency:
            overlapping = [c for c in service["spec"]["credentials"] if c["state"] == "overlap"]
            self.check("normal-overlap-bounded", len(overlapping) == 1 and
                datetime.fromisoformat(overlapping[0]["expiresAt"]).timestamp() - time.time() <= 86400
                and self.public_call("/api/identity", token).status_code == 200)
            confirmed = self.owners["consumer"].request("POST", path + "/confirm", etag=service["version"], statuses=(202,))
            self.owners["consumer"].operation(confirmed)
        started = time.monotonic()
        wait_for(lambda: self.public_call("/api/identity", token).status_code == 403, "old-client-denial", 300)
        self.check("emergency-no-overlap" if emergency else "adoption-revokes-old-client", True,
                   seconds=round(time.monotonic() - started, 3))
        return self.fetch_service(service), replacement

    def expiry(self, machines):
        token = machines.get()
        claims = jwt.decode(token, options={"verify_signature": False})
        remaining = claims["exp"] - time.time()
        require(0 < remaining <= 300, "unexpected_token_lifetime")
        # Hold THIS token; renewing it would make the expiry assertion meaningless.
        started = time.monotonic()
        wait_for(lambda: self.public_call("/api/identity", token).status_code == 401,
                 "held_token_expiry", remaining + 5)
        self.check("expired-machine-token-denied", True, seconds=round(time.monotonic() - started, 3))

    def isolated_lab(self):
        rows = self.api.request("GET", "/projects")
        require(all(r["name"] in self.projects.values() for r in rows),
                "recovery_requires_empty_lab")

    def recovery(self, service, machines, human, password):
        self.isolated_lab()
        old_token = machines.get()
        previous = self.approved_identity(old_token)
        started = time.monotonic()
        response = self.api.request("POST", "/operator/application-access/recover", statuses=(202,))
        require(response["browserSessionsInvalidated"], "recovery_sessions_not_invalidated")
        for operation_id in response["operationIds"]:
            self.api.operation({"status_url": "/v1/access-operations/" + operation_id})
        service = self.fetch_service(service)
        replacement = MachineTokens(self.kube.binding(service["project"], service["spec"]["secretPrefix"]))
        wait_for(lambda: self.public_call("/api/identity", replacement.get()).status_code == 200,
                 "recovery_activation", 60)
        current = self.approved_identity(replacement.get())
        wait_for(lambda: self.public_call("/api/identity", old_token).status_code == 403,
                 "recovery_old_token", 60)
        stale = self.browser.get(self.urls["provider"] + "/app/identity")
        self.check("recovery-invalidates-browser-and-machine-credentials", stale.status_code == 302
                   and current["Id"] == previous["Id"] and current["Client-Id"] != previous["Client-Id"],
                   seconds=round(time.monotonic() - started, 3))
        self.browser.cookies.clear()
        renewed = self.browser_login(human["username"], password)
        read = self.public_call("/api/state", replacement.get())
        self.check("recovery-reconciles-principals-groups-and-state", renewed.status_code == 200
                   and fingerprint(renewed.json()["principal"]["Id"]) == self.journal.state["humanPrincipalHash"]
                   and read.status_code == 200 and read.json()["marker"] == self.journal.state["marker"])
        return service, replacement

    def revocations(self, service, machines, human_principal):
        owner = self.owners["provider"]
        memberships = owner.request("GET", self.resource("provider", "application-group-memberships"))["items"]
        rows = [m for m in memberships if m["spec"]["principalId"] == human_principal and m["state"] == "active"]
        require(rows, "human_membership_missing")
        started = time.monotonic()
        for row in rows:
            result = owner.request("DELETE", self.resource("provider", "application-group-memberships", row["id"]),
                                   etag=row["version"], statuses=(202,))
            owner.operation(result)
        wait_for(lambda: self.browser.get(self.urls["provider"] + "/app/identity").status_code == 403,
                 "human_revocation", 300)
        self.check("human-revocation-with-existing-session", True, seconds=round(time.monotonic() - started, 3))
        service = self.fetch_service(service)
        token = machines.get()
        started = time.monotonic()
        result = owner.request("DELETE", self.resource("provider", "service-access-requests", service["id"]),
                               etag=service["version"], statuses=(202,))
        owner.operation(result)
        wait_for(lambda: self.public_call("/api/identity", token).status_code == 403, "machine_revocation", 300)
        self.check("machine-revocation-with-issued-token", True, seconds=round(time.monotonic() - started, 3))

    def run(self):
        human, password = self.setup()
        service, machines = self.service("consumer", "provider")
        _, reverse = self.service("provider", "consumer")
        # Wait for snapshot publication, not just the asynchronous operation result.
        wait_for(lambda: self.public_call("/api/identity", machines.get()).status_code == 200,
                 "service_activation", 60)
        wait_for(lambda: self.public_call("/api/identity", reverse.get(), role="consumer").status_code == 200,
                 "reverse_service_activation", 60)
        principal = self.human_checks(human, password)
        self.machine_checks(service, machines, reverse)
        self.network_checks()
        self.persistence(machines, reverse)
        self.policy_checks(machines)
        service, machines = self.rotate(service, machines)
        service, machines = self.rotate(service, machines, emergency=True)
        if self.args.timed:
            self.expiry(machines)
            self.journal.report["deferred"].remove("held-machine-token-expiry")
        if self.args.allow_recovery_reconcile:
            service, machines = self.recovery(service, machines, human, password)
            self.journal.report["deferred"].remove("recovery-reconciliation-rehearsal")
        self.revocations(service, machines, principal)


def cleanup(journal, api, keycloak):
    """Retire ONLY owned fixture projects. Never purge their retained databases."""
    state = journal.state
    names = project_names(state["runId"])
    require(state["projects"] == names and set(state["createdProjects"]) <= set(names.values()), "cleanup_scope_mismatch")
    rows = {r["name"]: r for r in api.request("GET", "/projects")}
    for project in state["createdProjects"]:
        row = rows.get(project)
        require(row is not None, "cleanup_project_missing")
        if row["status"] == "retired":
            continue
        spec = row["spec"]
        require(spec is None or ((spec.get("configuration") or {}).get("ACCEPTANCE_RUN_ID") == state["runId"]
            and all(c["image"] == state["image"] for c in spec.get("components", []))), "cleanup_project_changed")
        preview = api.request("GET", "/projects/" + project + "/retirement-preview")
        require(not preview["blockers"], "cleanup_retirement_blocked")
        confirmation = {"confirm_name": project, "scope_token": preview["scope_token"]}
        def retired():
            result = api.request("POST", "/projects/" + project + "/retire", confirmation, statuses=(200, 202))
            return result.get("status") == "retired"
        wait_for(retired, "fixture_retirement", 180)
    known = api.request("GET", "/platform/test-identities?test_run_id=" + state["runId"])["credentials"]
    require(set(state["personas"]) <= {p["credential_id"] for p in known}, "cleanup_persona_scope_mismatch")
    for persona in known:
        require(persona["test_run_id"] == state["runId"] and persona["project"] in names.values(),
                "cleanup_persona_scope_mismatch")
        def revoked():
            return api.request("DELETE", "/platform/test-identities/" + persona["credential_id"], statuses=(200, 202))["status"] == "revoked"
        wait_for(revoked, "fixture_persona_revocation", 60)
    for client in state["clients"]:
        require(re.fullmatch(r"ha-" + state["runId"] + r"-[a-z]+", client["clientId"]), "cleanup_client_scope_mismatch")
        require(re.fullmatch(r"[0-9a-f-]{36}", client["id"]), "cleanup_client_scope_mismatch")
        response = keycloak.admin("GET", "clients/" + client["id"], statuses=(200, 404))
        if response.status_code == 200:
            require(response.json()["clientId"] == client["clientId"], "cleanup_client_changed")
            keycloak.admin("DELETE", "clients/" + client["id"], statuses=(204, 404))
    human = state["human"]
    if human:
        require(human["username"] == "ha-" + state["runId"] + "-human"
                and re.fullmatch(r"[0-9a-f-]{36}", human["id"]), "cleanup_human_scope_mismatch")
        require(state["issuer"] == keycloak.issuer, "cleanup_issuer_mismatch")
        response = keycloak.admin("GET", "users/" + human["id"], statuses=(200, 404))
        if response.status_code == 200:
            require(response.json()["username"] == human["username"], "cleanup_human_changed")
        api.request("DELETE", "/platform/grants", {"issuer": state["issuer"], "subject": human["id"]}, statuses=(200, 404))
        keycloak.admin("DELETE", "users/" + human["id"], statuses=(204, 404))
    journal.report["cleanup"] = "completed-data-retained"
    journal.save()


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("command", choices=("plan", "run", "cleanup"), nargs="?", default="plan")
    result.add_argument("--api", default="http://127.0.0.1:8000")
    result.add_argument("--run-id", default=None)
    result.add_argument("--output", type=Path)
    result.add_argument("--fixture-image")
    result.add_argument("--apps-domain", default="apps.example.invalid")
    result.add_argument("--issuer", default="https://identity.example.invalid/realms/platform", help="Offline plan only")
    result.add_argument("--unrelated-host", default="example.com", help="Resolvable destination outside permitted egress")
    result.add_argument("--settings", type=Path, default=ROOT / ".env")
    result.add_argument("--operator-token-file", type=Path, help="0600 JSON: access_token, refresh_token, client_id")
    result.add_argument("--kubectl", default="kubectl")
    result.add_argument("--confirm-environment", help="For live commands, repeat the exact API origin")
    result.add_argument("--timed", action="store_true", help="Also hold a machine token until its real expiry")
    result.add_argument("--allow-recovery-reconcile", action="store_true", help="GLOBAL reconciliation; isolated empty lab only, NOT a backup restore")
    return result


def validate(args):
    args.api = origin(args.api)
    require(args.command != "cleanup" or args.run_id is not None, "cleanup_requires_run_id")
    args.run_id = args.run_id or uuid4().hex[:12]
    project_names(args.run_id)
    require(re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", args.apps_domain), "invalid_apps_domain")
    require(re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", args.unrelated_host), "invalid_unrelated_host")
    if args.command != "cleanup":
        require(args.fixture_image and IMAGE_PATTERN.fullmatch(args.fixture_image), "digest_pinned_fixture_image_required")
    if args.command != "plan":
        require(args.confirm_environment == args.api, "explicit_environment_confirmation_required")
        require(args.operator_token_file is not None, "operator_token_file_required")
    args.output = args.output or ROOT / ".runtime/hosted-access" / args.run_id


def operator_tokens(path, keycloak):
    payload = json.loads(private_text(path))
    require(set(payload) == {"access_token", "refresh_token", "client_id"}
            and all(isinstance(v, str) and v for v in payload.values()), "invalid_operator_session")
    return Tokens(payload["access_token"], OperatorRefresh(keycloak, payload["client_id"]), payload["refresh_token"])


def main(argv=None):
    journal = None
    try:
        args = parser().parse_args(argv)
        validate(args)
        if args.command == "plan":
            names = project_names(args.run_id)
            print(json.dumps({"format": 1, "runId": args.run_id, "mutates": False,
                "declarations": [declaration(p, r, args.fixture_image, args.run_id,
                    "https://api-" + names["provider"] + "." + args.apps_domain, args.issuer) for r, p in names.items()],
                "accessPolicyIntent": access_policy("readers", "humans", "administrators"),
                "serviceAccessIntent": {"consumer": names["consumer"], "provider": names["provider"],
                                        "groups": ["readers"], "requiresProviderApproval": True, "projectWideCredential": True},
                "deferred": DEFERRED, "gateClosed": False}, indent=2))
            return 0
        config = settings(args.settings)
        keycloak = Keycloak(config)
        require(args.command != "run" or config["APPS_DOMAIN"] == args.apps_domain, "apps_domain_mismatch")
        api = API(args.api, operator_tokens(args.operator_token_file, keycloak))
        # Validate a renewable HUMAN administrator before provisioning anything.
        api.request("GET", "/platform/test-runner-credentials")
        journal = Journal(args.output, args.api, args.run_id, resume=args.command == "cleanup")
        if args.command == "cleanup":
            try:
                cleanup(journal, api, keycloak)
            except (Exception, KeyboardInterrupt):
                journal.report["cleanup"] = "incomplete-retry-required"
                journal.save()
                raise
            return 0
        journal.report["requestedDrills"] = {"tokenExpiry": args.timed, "recoveryReconcile": args.allow_recovery_reconcile}
        journal.report["harnessSha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        journal.save()
        error = None
        try:
            Drill(args, journal, api, keycloak, Kube(args.kubectl)).run()
        except (Exception, KeyboardInterrupt) as exc:
            error = str(exc) if isinstance(exc, DrillError) else "interrupted" if isinstance(exc, KeyboardInterrupt) else "dependency_failure"
        finally:
            try:
                cleanup(journal, api, keycloak)
            except (Exception, KeyboardInterrupt):
                journal.report["cleanup"] = "incomplete-retry-required"
                error = error or "cleanup_failed"
        journal.report.update(result="failed" if error else "core-passed", finishedAt=utc())
        if error:
            journal.report["errorCode"] = error
        journal.save()
        print("REPORT " + str(args.output / "report.json"), flush=True)
        print("Full acceptance gate remains open; see deferred checks.", flush=True)
        return 1 if error else 0
    except (Exception, KeyboardInterrupt) as exc:
        code = str(exc) if isinstance(exc, DrillError) else "interrupted" if isinstance(exc, KeyboardInterrupt) else "configuration_or_dependency_failure"
        print("ERROR " + code, flush=True)
        return 1
