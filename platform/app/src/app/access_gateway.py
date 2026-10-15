"""Shared hosted-application authorizer and streaming reverse proxy.

Only this service may reach public application backends. Browser cookies are
verified by the app-specific OAuth2 Proxy; bearer tokens are verified here.
Both paths intersect claims with the live, bounded platform access catalog.
"""
import asyncio
import contextlib
import hmac
import ipaddress
import os
import secrets
import time
from contextlib import asynccontextmanager
from datetime import datetime
from urllib.parse import urlencode

import httpx2 as httpx
import jwt
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response, StreamingResponse

from .access_contract import PolicyCreate, canonical_path, match_route
from .access_provider import audience
from .access_runtime import browser_name
from .access_tokens import TokenVerifier
from . import tracing


SESSION = "__Host-platform-activity"
CSRF = "__Host-platform-csrf"
HOP_HEADERS = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailer", "transfer-encoding", "upgrade"}


class Snapshot:
    def __init__(self):
        self.value = None
        self.compilation_failed = False

    def load(self, data, now=None):
        now = time.time() if now is None else now
        if not isinstance(data.get("generation"), int) or not now < data["expiresAt"] <= data["issuedAt"] + 300 \
                or data["issuedAt"] > now + 5:
            raise ValueError("Invalid bounded snapshot")
        hosts = set()
        for policy in data["policies"]:
            spec = policy["spec"]
            PolicyCreate.model_validate({k: spec[k] for k in PolicyCreate.model_fields})
            if spec["host"] in hosts:
                raise ValueError("Duplicate public host")
            hosts.add(spec["host"])
        if self.value and data["generation"] < self.value["generation"]:
            raise ValueError("Snapshot rollback requires access recovery")
        # An atomic reference swap prevents requests from mixing policy revisions.
        self.value = data
        self.compilation_failed = False

    def current(self, now=None):
        now = time.time() if now is None else now
        if self.compilation_failed or not self.value or now >= self.value["expiresAt"]:
            raise HTTPException(503, "Application authorization snapshot expired")
        return self.value


def admitted_identity(data, policy, claims, mode, now=None):
    now = time.time() if now is None else now
    if mode == "browser-session":
        if claims["azp"] != "browser-" + policy["id"]:
            raise HTTPException(401, "Expected browser identity")
        kind = "user"
    else:
        kind = "service"
        service = next((s for s in data["services"] if s["spec"]["policyId"] == policy["id"] and s["state"] == "active"
            and any(c.get("subject") == claims["sub"] and c.get("clientId") == claims["azp"]
                and (c["state"] == "active" or (c["state"] == "overlap" and now < datetime.fromisoformat(c["expiresAt"]).timestamp()))
                for c in s["spec"]["credentials"])), None)
        if not service:
            raise HTTPException(403, "Service principal is not approved or has been revoked")
    identity = next((p for p in data["principals"] if p["issuer"] == claims["iss"] and p["subject"] == claims["sub"]
                     and p["kind"] == kind), None)
    if not identity:
        return None, []
    live_groups = {m["spec"]["groupId"] for m in data["memberships"] if m["state"] == "active"
        and m["spec"]["policyId"] == policy["id"] and m["spec"]["principalId"] == identity["id"]}
    return identity, sorted(set(claims["groups"]) & live_groups)


def upstream_headers(raw_headers, identity, claims, groups, attributes):
    connections = set()
    for name, value in raw_headers:
        if name.lower() == b"connection":
            connections |= {h.strip().lower() for h in value.decode("latin1").split(",")}
    headers = []
    for raw_name, value in raw_headers:
        name = raw_name.decode("latin1").lower()
        if name in HOP_HEADERS | connections | {"authorization", "host", "content-length", "forwarded",
                "x-original-url", "x-rewrite-url", "x-http-method-override", "x-method-override",
                "traceparent", "tracestate", "baggage"} \
                or name.startswith(("x-platform-", "x-auth-", "x-forwarded-")):
            continue
        if name == "cookie":
            parts = [p.strip() for p in value.decode("latin1").split(";") if not p.strip().startswith("__Host-platform-")]
            if parts:
                headers.append(("cookie", "; ".join(parts)))
        else:
            headers.append((name, value.decode("latin1")))
    fields = {"Id": identity["id"], "Kind": identity["kind"], "Issuer": claims["iss"], "Subject": claims["sub"],
              "Group-Ids": " ".join(groups)}
    if identity["kind"] == "service":
        fields["Client-Id"] = claims["azp"]
    for option, claim, header in (("displayName", "name", "Name"), ("email", "email", "Email")):
        if attributes.get(option) and identity["kind"] == "user" and isinstance(claims.get(claim), str):
            value = claims[claim]
            if len(value) <= 256 and all(32 <= ord(c) <= 126 for c in value):
                fields[header] = value
    return headers + [("X-Platform-Principal-" + key, value) for key, value in fields.items()]


def session_state(raw, key, policy, now=None):
    now = time.time() if now is None else now
    try:
        value = jwt.decode(raw, key, algorithms=["HS256"], options={"require": ["exp", "iat", "epoch", "start", "last", "csrf"]})
        if value["epoch"] != policy["spec"]["sessionEpoch"] or now - value["last"] >= 1800 or now - value["start"] >= 28800:
            raise ValueError("Expired browser session")
        return value
    except (jwt.PyJWTError, ValueError, TypeError):
        raise HTTPException(401, "Browser session expired") from None


def new_session(policy, now=None):
    now = time.time() if now is None else now
    return {"iat": int(now), "start": now, "last": now, "exp": int(now + 28800),
            "epoch": policy["spec"]["sessionEpoch"], "csrf": secrets.token_urlsafe(32)}


def attach_session(response, state, key):
    response.set_cookie(SESSION, jwt.encode(state, key, algorithm="HS256"), secure=True, httponly=True, samesite="lax", max_age=28800)
    response.set_cookie(CSRF, state["csrf"], secure=True, httponly=False, samesite="lax", max_age=28800)


def clear_session(response, cookies):
    for name in set(cookies) | {SESSION, CSRF, "__Host-platform-session"}:
        if name.startswith("__Host-platform-"):
            response.delete_cookie(name, secure=True, httponly=name != CSRF, samesite="lax")


def create_gateway(api_url=None, internal_key=None, session_key=None, client=None):
    snapshot = Snapshot()
    verifiers = {}
    statistics = {"allowed": 0, "denied": 0, "unavailable": 0}
    api_url = api_url or os.environ.get("APPLICATION_ACCESS_API", "http://172.30.80.11:8000")
    internal_key = internal_key or os.environ.get("APPLICATION_ACCESS_KEY", "")
    session_key = session_key or os.environ.get("APPLICATION_SESSION_KEY", "")
    transport = client
    background = None

    async def refresh():
        headers = {"Authorization": "Bearer " + internal_key}
        result = await transport.get(api_url + "/internal/application-access/snapshot", headers=headers)
        result.raise_for_status()
        try:
            snapshot.load(result.json())
        except (ValueError, KeyError, TypeError):
            snapshot.compilation_failed = True
            raise
        ack = await transport.post(api_url + "/internal/application-access/replicas/" + os.environ.get("APPLICATION_ACCESS_REPLICA", "local"),
                                   headers=headers, json={"generation": snapshot.value["generation"]})
        ack.raise_for_status()

    async def polling():
        while True:
            try:
                await refresh()
            except Exception:
                pass  # Retain only the existing snapshot until its original deadline.
            await asyncio.sleep(2)

    @asynccontextmanager
    async def lifespan(application):
        nonlocal transport, background
        tracing.configure()
        if min(len(internal_key), len(session_key)) < 32:
            raise RuntimeError("Application boundary keys are required")
        owned = transport is None
        transport = transport or httpx.AsyncClient(timeout=httpx.Timeout(120, connect=5), follow_redirects=False, trust_env=False)
        background = asyncio.create_task(polling())
        try:
            yield
        finally:
            background.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await background
            if owned:
                await transport.aclose()
            tracing.shutdown()

    gateway = FastAPI(title="Hosted application access boundary", lifespan=lifespan, docs_url=None, openapi_url=None)

    @gateway.middleware("http")
    async def trace_boundary(request, call_next):
        with tracing.span("platform.http") as active:
            response = await call_next(request)
            active.set_attribute("http.route", request.scope.get("route").path if request.scope.get("route") else "unmatched")
            active.set_attribute("http.request.method", request.method)
            active.set_attribute("http.response.status_code", response.status_code)
            return response
    gateway.state.snapshot = snapshot
    gateway.state.refresh = refresh
    gateway.state.verifiers = verifiers

    @gateway.exception_handler(HTTPException)
    async def denied(request, error):
        statistics["unavailable" if error.status_code == 503 else "denied"] += 1
        return JSONResponse({"code": "application_access_unavailable" if error.status_code == 503 else "application_access_denied",
                             "detail": error.detail}, status_code=error.status_code,
                            headers={"Cache-Control": "no-store", **(error.headers or {})})

    def private_probe(request):
        host = request.url.hostname or ""
        try:
            ipaddress.ip_address(host)
        except ValueError:
            if host not in {"authorizer", "authorizer.platform-access.svc.cluster.local"}:
                raise HTTPException(403, "Internal boundary endpoint")

    @gateway.get("/internal/ready")
    async def ready(request: Request):
        private_probe(request)
        snapshot.current()
        return {"ready": True, "generation": snapshot.value["generation"]}

    @gateway.get("/internal/live")
    async def live(request: Request):
        private_probe(request)
        return {"live": True}

    @gateway.get("/internal/metrics")
    async def metrics(request: Request):
        private_probe(request)
        return Response("".join("platform_application_access_requests_total{decision=\"" + k + "\"} " + str(v) + "\n"
                                for k, v in statistics.items()), media_type="text/plain")

    async def oauth_response(request, policy, path):
        proxy = "http://" + browser_name(policy) + ".platform-access.svc.cluster.local:4180"
        # Only these protocol endpoints are public; /oauth2/auth and userinfo are internal.
        if path not in {"/oauth2/start", "/oauth2/callback", "/oauth2/sign_out"} or request.method != "GET":
            raise HTTPException(403, "Reserved authentication endpoint")
        if not any(r["authentication"]["mode"] == "browser-session" for r in policy["spec"]["routes"]):
            raise HTTPException(403, "Application has no browser policy")
        query = request.url.query
        if path in {"/oauth2/start", "/oauth2/sign_out"}:
            target = request.query_params.get("rd", "/")
            try:
                rule = match_route(policy["spec"], target, "GET")
            except ValueError:
                rule = None
            if not rule or rule["authentication"]["mode"] != "browser-session":
                first = next(r for r in policy["spec"]["routes"] if r["authentication"]["mode"] == "browser-session" and "GET" in r["match"]["methods"])
                target = first["match"].get("path") or first["match"]["pathPrefix"]
            query = urlencode({"rd": "https://" + policy["spec"]["host"] + target})
        upstream = await transport.get(proxy + path + ("?" + query if query else ""), headers={
            "Cookie": request.headers.get("cookie", ""), "X-Forwarded-Proto": "https", "X-Forwarded-Host": policy["spec"]["host"]})
        result = Response(upstream.content, status_code=upstream.status_code)
        for name, value in upstream.headers.multi_items():
            if name.lower() not in HOP_HEADERS | {"content-length"}:
                result.raw_headers.append((name.encode("latin1"), value.encode("latin1")))
        if path == "/oauth2/callback" and upstream.status_code in {302, 303} and any(
            c.startswith("__Host-platform-session=") and not c.startswith("__Host-platform-session=;") for c in upstream.headers.get_list("set-cookie")):
            attach_session(result, new_session(policy), session_key)
        if path == "/oauth2/sign_out":
            clear_session(result, request.cookies)
            # Provider logout is initiated by the browser; no identity token is exposed to application code.
            result.headers["location"] = snapshot.current()["issuer"] + "/protocol/openid-connect/logout"
            result.status_code = 302
        result.headers["Cache-Control"] = "no-store"
        return result

    @gateway.api_route("/{path:path}", methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "TRACE", "CONNECT"])
    async def forward(request: Request, path: str):
        # Health endpoints are available only without an application Host header; ingress cannot expose them.
        data = snapshot.current()
        host = request.headers.get("host", "").lower()
        if host.endswith(":443"):
            host = host[:-4]
        policy = next((p for p in data["policies"] if p["spec"]["host"] == host), None)
        if not policy or policy["state"] != "active":
            raise HTTPException(503 if policy else 403, "Application policy is not active")
        try:
            raw_path = request.scope["raw_path"].decode("ascii")
            decoded = canonical_path(raw_path)
            if decoded.startswith("/oauth2"):
                return await oauth_response(request, policy, decoded)
            rule = match_route(policy["spec"], raw_path, request.method)
        except (ValueError, UnicodeError):
            raise HTTPException(400, "Invalid request path") from None
        if not rule:
            raise HTTPException(403, "No application route permits this request")
        mode = rule["authentication"]["mode"]
        state = None
        cookies = []
        if mode == "bearer-token":
            auth_values = request.headers.getlist("authorization")
            if len(auth_values) != 1 or not auth_values[0].startswith("Bearer "):
                raise HTTPException(401, "Bearer token required", headers={"WWW-Authenticate": "Bearer"})
            token = auth_values[0][7:]
        else:
            try:
                state = session_state(request.cookies.get(SESSION), session_key, policy)
            except HTTPException:
                result = RedirectResponse("/oauth2/start?" + urlencode({"rd": decoded}), status_code=302)
                clear_session(result, request.cookies)
                return result
            proxy = "http://" + browser_name(policy) + ".platform-access.svc.cluster.local:4180/oauth2/auth"
            auth_response = await transport.get(proxy, headers={"Cookie": request.headers.get("cookie", ""),
                "X-Forwarded-Proto": "https", "X-Forwarded-Host": host})
            if auth_response.status_code == 401:
                result = RedirectResponse("/oauth2/start?" + urlencode({"rd": decoded}), status_code=302)
                clear_session(result, request.cookies)
                return result
            if auth_response.status_code != 202:
                raise HTTPException(503, "Browser authentication unavailable")
            token = auth_response.headers.get("x-auth-request-access-token", "")
            cookies = auth_response.headers.get_list("set-cookie")
        key = (data["issuer"], policy["spec"]["applicationId"], data["jwksUrl"])
        token_verifier = verifiers.setdefault(key, TokenVerifier(data["issuer"], audience(policy["spec"]["applicationId"]), data["jwksUrl"]))
        claims = await asyncio.to_thread(token_verifier.verify, token)
        identity, groups = admitted_identity(data, policy, claims, mode)
        if state:
            if state.get("subject") not in (None, claims["sub"]):
                raise HTTPException(401, "Browser session identity changed")
            state = {**state, "subject": claims["sub"], "last": time.time()}
            if request.method not in {"GET", "HEAD", "OPTIONS"}:
                if request.headers.get("origin") != "https://" + host or not hmac.compare_digest(
                    request.headers.get("x-platform-csrf-token", ""), state["csrf"]):
                    raise HTTPException(403, "Browser state changes require the platform CSRF token and same origin")
        if not identity or not set(groups) & set(rule["authorization"]["anyOfGroups"]):
            pending = None
            if mode == "browser-session":
                enrolled = await transport.post(api_url + "/internal/application-access/enroll", json={"policyId": policy["id"], "accessToken": token},
                    headers={"Authorization": "Bearer " + internal_key})
                enrolled.raise_for_status()
                pending = enrolled.json()
            result = JSONResponse({"code": "application_access_pending" if pending and pending["state"] == "pending" else "application_access_denied",
                **({"requestId": pending["requestId"]} if pending else {})}, status_code=403, headers={"Cache-Control": "no-store"})
            if state:
                attach_session(result, state, session_key)
            for value in cookies:
                result.raw_headers.append((b"set-cookie", value.encode("latin1")))
            return result
        headers = upstream_headers(request.headers.raw, identity, claims, groups, policy["spec"]["identityAttributes"])
        if tracing.propagation_traceparent():
            headers.append(("traceparent", tracing.propagation_traceparent()))
        url = policy["spec"]["backend"] + raw_path + ("?" + request.url.query if request.url.query else "")
        upstream = await transport.send(transport.build_request(request.method, url, headers=headers, content=request.stream()), stream=True)
        async def body():
            try:
                async for chunk in upstream.aiter_raw():
                    yield chunk
            finally:
                await upstream.aclose()
        result = StreamingResponse(body(), status_code=upstream.status_code)
        for name, value in upstream.headers.multi_items():
            if name.lower() not in HOP_HEADERS and not name.lower().startswith("x-platform-"):
                if name.lower() == "set-cookie" and value.lower().startswith("__host-platform-"):
                    continue  # An application cannot replace boundary-owned authentication or CSRF cookies.
                result.raw_headers.append((name.encode("latin1"), value.encode("latin1")))
        if state:
            attach_session(result, state, session_key)
        if tracing.trace_id():
            result.headers["X-Platform-Trace-Id"] = tracing.trace_id()
        for value in cookies:
            result.raw_headers.append((b"set-cookie", value.encode("latin1")))
        statistics["allowed"] += 1
        return result

    @gateway.exception_handler(httpx.HTTPError)
    async def dependency_unavailable(request, error):
        statistics["unavailable"] += 1
        return JSONResponse({"code": "application_access_unavailable"}, status_code=503, headers={"Cache-Control": "no-store"})

    return gateway


app = create_gateway()
