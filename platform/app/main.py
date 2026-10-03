"""OIDC-authenticated, project-scoped platform API."""
import hashlib
import hmac
import logging
import os
import threading
import csv
import io
from datetime import datetime, timedelta, timezone
from typing import Literal
from contextlib import asynccontextmanager
from uuid import UUID

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from kubernetes import config, dynamic
from kubernetes.client import ApiClient
from kubernetes.client.exceptions import ApiException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .audit import Actor, initialize as initialize_audit, read_events, record_event, redact
from .authorization import (bootstrap_platform_admin, grant as grant_role, initialize as initialize_authorization,
                            grants_for_project, is_allowed, is_platform_admin, projects_for_principal, revoke as revoke_role,
                            upsert_principal)
from .catalog import ensure_default_application, initialize as initialize_catalog
from .identity import AuthenticationError, Principal, configured_verifier
from .manifests import resources, validate_name
from .monitoring import discovery_loop, publish_catalog
from .operations import operation_loop
from .readiness import observe_deployment
from .security_alerts import security_alert_loop

log = logging.getLogger(__name__)
auth = HTTPBearer(auto_error=False)
runtime = None
verifier = None

def connect():
    return psycopg.connect(host=os.environ["POSTGRES_HOST"], dbname="platform",
        user="postgres", password=os.environ["POSTGRES_PASSWORD"],
        connect_timeout=5, autocommit=True)

@asynccontextmanager
async def lifespan(app):
    global runtime, verifier
    for key in ("DATABASE_KEY", "PLATFORM_AUDIT_PASSWORD", "PLATFORM_AUDIT_READER_PASSWORD"):
        if len(os.environ.get(key, "")) < 32:
            raise RuntimeError(key + " must contain at least 32 characters")
    verifier = configured_verifier()
    with connect() as conn:
        conn.execute("REVOKE ALL ON DATABASE platform FROM PUBLIC")
        conn.execute("""CREATE TABLE IF NOT EXISTS projects (
            name TEXT PRIMARY KEY, spec JSONB NOT NULL, status TEXT NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now())""")
        initialize_catalog(conn)
        initialize_audit(conn)
        initialize_authorization(conn)
        bootstrap = bootstrap_platform_admin(conn, verifier.issuer)
    if bootstrap:
        required_audit(Actor("bootstrap", bootstrap.audit_id), "membership.bootstrap", "platform-grant",
                       bootstrap.audit_id, "succeeded", {"scope": "platform"}, {"role": "platform-admin"})
    config.load_kube_config()
    runtime = dynamic.DynamicClient(ApiClient())
    stop = threading.Event()
    worker = threading.Thread(target=discovery_loop, args=(stop, connect, log), daemon=True)
    worker.start()
    security_worker = threading.Thread(
        target=security_alert_loop,
        args=(stop, os.environ.get("MONITORING_DISCOVERY_DIR", "/var/lib/platform-monitoring"), log), daemon=True,
    )
    security_worker.start()
    operation_worker = threading.Thread(
        target=operation_loop,
        args=(stop, connect, password_for, provision_database, apply, resources, publish_catalog, log),
        daemon=True,
    )
    operation_worker.start()
    try:
        yield
    finally:
        stop.set()
        worker.join(timeout=6)
        security_worker.join(timeout=6)
        operation_worker.join(timeout=6)

app = FastAPI(title="Docker-based Developer Platform Lab", lifespan=lifespan)


@app.get("/", include_in_schema=False)
def portal():
    """Serve the Keycloak PKCE portal without embedding credentials in the API."""
    return FileResponse(os.path.join(os.path.dirname(__file__), "static", "portal.html"))


@app.get("/portal/config", include_in_schema=False)
def portal_config(request: Request):
    """Publish non-secret browser OIDC configuration for the same-origin portal."""
    issuer = os.environ.get("OIDC_ISSUER", "https://" + os.environ.get("IDENTITY_DOMAIN", "identity.localhost") + "/realms/platform")
    if request.url.hostname in {"localhost", "127.0.0.1"}:
        redirect_uri = str(request.base_url)
    else:
        # The proxy terminates public HTTPS and forwards HTTP to Uvicorn, so
        # request.base_url would otherwise produce an invalid HTTP callback.
        redirect_uri = "https://" + os.environ.get("PLATFORM_DOMAIN", "platform.localhost") + "/"
    return {"issuer": issuer, "client_id": "platform-portal", "redirect_uri": redirect_uri}

def best_effort_audit(actor: Actor, action: str, target_kind: str, target_id: str | None,
                      result: str, scope=None, detail=None):
    try:
        return record_event(actor, action, target_kind, target_id, result, scope, detail)
    except Exception:
        # Do not include backend error text: it may contain a credential or provider detail.
        log.error("Could not record audit event action=%s result=%s", action, result)
        return None


def required_audit(actor: Actor, action: str, target_kind: str, target_id: str | None,
                   result: str, scope=None, detail=None):
    if best_effort_audit(actor, action, target_kind, target_id, result, scope, detail) is None:
        raise HTTPException(503, "Operation outcome requires an audit record; verify state before retrying")


def actor_for(principal: Principal) -> Actor:
    return Actor("oidc", principal.audit_id)


def current_principal(request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(auth)) -> Principal:
    if not credentials:
        best_effort_audit(Actor("anonymous", None), "authentication", "platform-api", None, "denied",
                          detail={"reason": "invalid_or_missing_bearer"})
        raise HTTPException(401, "Missing bearer token")
    try:
        principal = verifier.verify(credentials.credentials)
    except AuthenticationError:
        best_effort_audit(Actor("anonymous", None), "authentication", "platform-api", None, "denied",
                          detail={"reason": "invalid_bearer"})
        raise HTTPException(401, "Invalid OIDC access token")
    with connect() as conn:
        upsert_principal(conn, principal)
    request.state.audit_actor = actor_for(principal)
    return principal


def require_permission(principal: Principal, permission: str, project: str | None = None) -> None:
    with connect() as conn:
        allowed = is_allowed(conn, principal, permission, project)
    if allowed:
        return
    actor = actor_for(principal)
    required_audit(actor, "authorization", "project" if project else "platform", project, "denied",
                   {"project": project} if project else {"scope": "platform"}, {"permission": permission})
    raise HTTPException(403, "Not authorized for this operation")


def require_platform_admin(principal: Principal) -> None:
    with connect() as conn:
        allowed = is_platform_admin(conn, principal)
    if allowed:
        return
    actor = actor_for(principal)
    required_audit(actor, "authorization", "platform", None, "denied", {"scope": "platform"},
                   {"permission": "platform-admin"})
    raise HTTPException(403, "Platform administrator permission is required")


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    actor = getattr(request.state, "audit_actor", None)
    if actor and request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        target_id = request.path_params.get("name")
        if best_effort_audit(actor, "request.validation", "platform-api", target_id, "rejected",
                             detail={"reason": "request_validation"}) is None:
            return JSONResponse(status_code=503, content={
                "detail": "Rejected request requires an audit record; retry after audit service recovery"
            })
    return await request_validation_exception_handler(request, exc)

class Project(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    image: str = Field(min_length=1, max_length=512, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9./_:@-]+$")
    port: int = Field(default=8080, ge=1024, le=65535)
    probe_profile: Literal["status", "hello-world"] = "status"

    @field_validator("name")
    @classmethod
    def check_name(cls, value):
        return validate_name(value)

def password_for(name):
    return hmac.new(os.environ["DATABASE_KEY"].encode(), name.encode(), hashlib.sha256).hexdigest()

def provision_database(conn, name, password):
    db = "project_" + name.replace("-", "_")
    if not conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (db,)).fetchone():
        conn.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE")
                     .format(sql.Identifier(db), sql.Literal(password)))
    if not conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db,)).fetchone():
        conn.execute(sql.SQL("CREATE DATABASE {} OWNER {}")
                     .format(sql.Identifier(db), sql.Identifier(db)))
    conn.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(db)))

def apply(manifest):
    resource = runtime.resources.get(api_version=manifest["apiVersion"], kind=manifest["kind"])
    args = {"name": manifest["metadata"]["name"], "body": manifest,
            "content_type": "application/apply-patch+yaml", "field_manager": "developer-platform"}
    if resource.namespaced:
        args["namespace"] = manifest["metadata"]["namespace"]
    resource.patch(**args)

@app.get("/healthz")
def health():
    return {"status": "ok"}

@app.get("/readyz")
def ready():
    try:
        with connect() as conn:
            conn.execute("SELECT 1")
        runtime.resources.get(api_version="v1", kind="Namespace").get(name="platform-system")
    except Exception:
        raise HTTPException(503, "Dependency unavailable")
    return {"status": "ready"}

@app.get("/projects")
def projects(principal: Principal = Depends(current_principal)):
    with connect() as conn:
        rows = projects_for_principal(conn, principal)
    return [{"name": name, "spec": spec, "status": status} for name, spec, status in rows]


def _operator_audit(principal: Principal, action: str, target_id: str | None, detail: dict):
    require_platform_admin(principal)
    required_audit(actor_for(principal), action, "audit" if action.startswith("audit.") else "project", target_id,
                   "succeeded", {"scope": "platform"}, detail)


@app.get("/operator/projects/{name}/permissions")
def inspect_project_permissions(name: str, principal: Principal = Depends(current_principal)):
    """Inspect project grants; this is intentionally unavailable to project members."""
    _operator_audit(principal, "security.permissions.inspect", name, {"project": name})
    with connect() as conn:
        if not conn.execute("SELECT 1 FROM projects WHERE name=%s", (name,)).fetchone():
            raise HTTPException(404, "Unknown project")
        rows = grants_for_project(conn, name)
    return {"project": name, "grants": [
        {"issuer": issuer, "subject": subject, "display_name": display_name, "role": role,
         "granted_at": granted_at.isoformat()} for issuer, subject, display_name, role, granted_at in rows
    ]}


@app.get("/operator/projects/{name}/security-configuration")
def inspect_project_security_configuration(name: str, principal: Principal = Depends(current_principal)):
    """Return the safe, managed workload and network policy contract for a project."""
    _operator_audit(principal, "security.configuration.inspect", name, {"project": name})
    with connect() as conn:
        if not conn.execute("SELECT 1 FROM projects WHERE name=%s", (name,)).fetchone():
            raise HTTPException(404, "Unknown project")
    managed = resources(name, "inspection.invalid", 8080, os.environ["APPS_DOMAIN"], os.environ["POSTGRES_IP"], "")
    selected = {item["kind"]: item for item in managed if item["kind"] in {
        "Namespace", "ResourceQuota", "LimitRange", "NetworkPolicy", "Deployment"
    }}
    deployment = selected["Deployment"]
    container = deployment["spec"]["template"]["spec"]["containers"][0]
    return {
        "project": name,
        "namespace": selected["Namespace"],
        "resource_quota": selected["ResourceQuota"]["spec"],
        "limit_range": selected["LimitRange"]["spec"],
        "network_policy": selected["NetworkPolicy"]["spec"],
        "workload_security": {
            "pod": deployment["spec"]["template"]["spec"]["securityContext"],
            "container": container["securityContext"],
            "service_account_token_automount": deployment["spec"]["template"]["spec"]["automountServiceAccountToken"],
            "secret_references": [entry["secretRef"]["name"] for entry in container.get("envFrom", [])],
        },
    }


@app.get("/operator/audit/events")
def export_audit_events(start: datetime, end: datetime, format: Literal["json", "csv"] = "json",
                        limit: int = Query(default=1000, ge=1, le=10000),
                        principal: Principal = Depends(current_principal)):
    """Export a bounded UTC audit window without secret values."""
    if start.tzinfo is None or end.tzinfo is None:
        raise HTTPException(400, "start and end must include a UTC offset")
    start, end = start.astimezone(timezone.utc), end.astimezone(timezone.utc)
    if end <= start or end - start > timedelta(days=31):
        raise HTTPException(400, "Select a positive audit window no longer than 31 days")
    _operator_audit(principal, "audit.export", None, {"start": start.isoformat(), "end": end.isoformat(), "format": format})
    events = read_events(start, end, limit)
    if format == "json":
        return {"start": start.isoformat(), "end": end.isoformat(), "events": events}
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=("id", "occurred_at", "actor_kind", "actor_id", "action",
                                                 "target_kind", "target_id", "scope", "result", "revision",
                                                 "operation_id", "detail"), extrasaction="ignore")
    writer.writeheader()
    for event in events:
        row = event.copy()
        row["scope"] = str(row["scope"])
        row["detail"] = str(row["detail"])
        writer.writerow(row)
    return PlainTextResponse(output.getvalue(), media_type="text/csv")

@app.put("/projects/{name}")
def provision(name: str, project: Project, principal: Principal = Depends(current_principal)):
    actor = actor_for(principal)
    require_permission(principal, "change", name)
    if name != project.name:
        required_audit(actor, "project.provision", "project", name, "rejected", {"project": name},
                       {"reason": "path_name_mismatch"})
        raise HTTPException(400, "Path and project name must match")
    try:
        with connect() as conn:
            # Serialize project revisions and active-operation deduplication.
            conn.execute("SELECT pg_advisory_lock(731904)")
            try:
                with conn.transaction():
                    row = conn.execute("""INSERT INTO projects(name,spec,status) VALUES (%s,%s,'provisioning')
                        ON CONFLICT(name) DO UPDATE SET spec=excluded.spec,
                        status='provisioning',updated_at=now()
                        RETURNING project_id""", (name, Jsonb(project.model_dump()))).fetchone()
                    if row is None:
                        raise RuntimeError("Could not resolve project identity")
                    application_id, revision = ensure_default_application(
                        conn, row[0], name, project.model_dump())
                    pending = conn.execute("""SELECT operation_id, state FROM application_operations
                        WHERE application_id=%s AND revision=%s AND operation_kind=%s
                        AND state IN ('queued', 'running')
                        ORDER BY created_at DESC LIMIT 1""",
                        (application_id, revision, "deploy")).fetchone()
                    if pending:
                        operation_id = pending[0]
                        operation_state = pending[1]
                    else:
                        envelope = {
                            "project_id": str(row[0]),
                            "application_id": str(application_id),
                            "project_slug": name,
                            "revision": revision,
                            "spec": project.model_dump(),
                        }
                        queued = conn.execute("""INSERT INTO application_operations(
                            application_id, revision, operation_kind, state, actor_issuer, actor_subject,
                            envelope_version, envelope)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                            RETURNING operation_id""",
                            (application_id, revision, "deploy", "queued",
                             principal.issuer, principal.subject, 1, Jsonb(envelope))).fetchone()
                        if queued is None:
                            raise RuntimeError("Could not persist deployment operation")
                        operation_id = queued[0]
                        operation_state = "queued"
            finally:
                conn.execute("SELECT pg_advisory_unlock(731904)")
    except Exception as exc:
        required_audit(actor, "project.provision", "project", name, "failed", {"project": name},
                       {"error_type": type(exc).__name__})
        log.error("Project reconciliation failed: %s (%s)", name, type(exc).__name__)
        raise HTTPException(503, "Provisioning failed; retry the same PUT. Existing data is retained.")
    required_audit(actor, "project.provision", "project", name, "succeeded", {"project": name},
                   {"state": operation_state, "revision": revision, "operation_id": str(operation_id)})
    return JSONResponse(status_code=202, content={
        "operation_id": str(operation_id),
        "state": operation_state,
        "revision": revision,
        "status_url": f"/v1/operations/{operation_id}",
    })


@app.get("/v1/operations/{operation_id}")
def operation_status(operation_id: UUID, principal: Principal = Depends(current_principal)):
    with connect() as conn:
        row = conn.execute("""SELECT o.operation_id, o.revision, o.state, o.result_version,
                o.result, o.error_code, p.name, r.spec
            FROM application_operations o
            JOIN project_applications a ON a.application_id=o.application_id
            JOIN project_environments e ON e.environment_id=a.environment_id
            JOIN projects p ON p.project_id=e.project_id
            JOIN application_revisions r
                ON r.application_id=o.application_id AND r.revision=o.revision
            WHERE o.operation_id=%s""", (operation_id,)).fetchone()
    if row is None:
        required_audit(actor_for(principal), "operation.inspect", "operation", str(operation_id),
                       "rejected", detail={"reason": "not_found"})
        raise HTTPException(404, "Unknown operation")
    require_permission(principal, "view", row[6])
    required_audit(actor_for(principal), "operation.inspect", "operation", str(operation_id),
                   "succeeded", {"project": row[6]}, {"state": row[2], "revision": row[1]})
    readiness = observe_deployment(runtime, row[6], row[7]["image"], log)
    return {
        "operation_id": str(row[0]),
        "revision": row[1],
        "state": row[2],
        "result_version": row[3],
        "result": redact(row[4]),
        "error_code": row[5],
        "readiness": readiness,
    }

class Retirement(BaseModel):
    confirm_name: str


@app.post("/projects/{name}/retire")
def retire(name: str, confirmation: Retirement, principal: Principal = Depends(current_principal)):
    """Acknowledge manual workload removal; retain catalog, database, and role."""
    actor = actor_for(principal)
    require_permission(principal, "retire", name)
    if name != confirmation.confirm_name:
        required_audit(actor, "project.retire", "project", name, "rejected", {"project": name},
                       {"reason": "confirmation_mismatch"})
        raise HTTPException(400, "Confirmation must match the project name")
    try:
        validate_name(name)
    except ValueError:
        required_audit(actor, "project.retire", "project", name, "rejected", {"project": name},
                       {"reason": "invalid_name"})
        raise HTTPException(400, "Invalid project name")
    try:
        with connect() as conn:
            conn.execute("SELECT pg_advisory_lock(731904)")
            try:
                if not conn.execute("SELECT status FROM projects WHERE name=%s", (name,)).fetchone():
                    raise HTTPException(404, "Unknown project")
                active_operation = conn.execute("""SELECT 1
                    FROM application_operations o
                    JOIN project_applications a ON a.application_id=o.application_id
                    JOIN project_environments e ON e.environment_id=a.environment_id
                    JOIN projects p ON p.project_id=e.project_id
                    WHERE p.name=%s AND o.state IN ('queued', 'running')
                    LIMIT 1""", (name,)).fetchone()
                if active_operation:
                    raise HTTPException(409, "Wait for active application operations before retirement")
                try:
                    runtime.resources.get(api_version="v1", kind="Namespace").get(name="project-" + name)
                except ApiException as exc:
                    if exc.status != 404:
                        raise
                else:
                    raise HTTPException(409, "Remove the project namespace and wait for deletion before retirement")
                conn.execute("UPDATE projects SET status='retired',updated_at=now() WHERE name=%s", (name,))
                publish_catalog(conn)
            finally:
                conn.execute("SELECT pg_advisory_unlock(731904)")
    except HTTPException as exc:
        required_audit(actor, "project.retire", "project", name,
                       "rejected" if exc.status_code < 500 else "failed", {"project": name},
                       {"status_code": exc.status_code})
        raise
    except Exception as exc:
        required_audit(actor, "project.retire", "project", name, "failed", {"project": name},
                       {"error_type": type(exc).__name__})
        log.error("Project retirement failed: %s (%s)", name, type(exc).__name__)
        raise HTTPException(503, "Retirement incomplete; retry the same request. Existing data is retained.")
    required_audit(actor, "project.retire", "project", name, "succeeded", {"project": name},
                   {"status": "retired", "data_retained": True})
    return {"name": name, "status": "retired", "data_retained": True}


class ProjectGrant(BaseModel):
    issuer: str = Field(min_length=1, max_length=2048)
    subject: str = Field(min_length=1, max_length=1024)
    role: Literal["viewer", "developer", "project-admin"]
    display_name: str | None = Field(default=None, max_length=512)


class GrantReference(BaseModel):
    issuer: str = Field(min_length=1, max_length=2048)
    subject: str = Field(min_length=1, max_length=1024)


class PlatformGrant(ProjectGrant):
    role: Literal["platform-admin"]


@app.put("/projects/{name}/grants")
def put_project_grant(name: str, grant: ProjectGrant, principal: Principal = Depends(current_principal)):
    actor = actor_for(principal)
    require_permission(principal, "grant", name)
    with connect() as conn:
        if not conn.execute("SELECT 1 FROM projects WHERE name=%s", (name,)).fetchone():
            required_audit(actor, "membership.grant", "project", name, "rejected", {"project": name},
                           {"reason": "unknown_project"})
            raise HTTPException(404, "Unknown project")
        grant_role(conn, Principal(grant.issuer, grant.subject, grant.display_name), "project", name, grant.role)
    required_audit(actor, "membership.grant", "principal", grant.issuer + "|" + grant.subject, "succeeded",
                   {"project": name}, {"role": grant.role})
    return {"project": name, "issuer": grant.issuer, "subject": grant.subject, "role": grant.role}


@app.delete("/projects/{name}/grants")
def delete_project_grant(name: str, grant: GrantReference, principal: Principal = Depends(current_principal)):
    actor = actor_for(principal)
    require_permission(principal, "grant", name)
    with connect() as conn:
        removed = revoke_role(conn, grant.issuer, grant.subject, "project", name)
    if not removed:
        required_audit(actor, "membership.revoke", "principal", grant.issuer + "|" + grant.subject, "rejected",
                       {"project": name}, {"reason": "unknown_grant"})
        raise HTTPException(404, "Unknown project grant")
    required_audit(actor, "membership.revoke", "principal", grant.issuer + "|" + grant.subject, "succeeded",
                   {"project": name})
    return {"project": name, "issuer": grant.issuer, "subject": grant.subject, "revoked": True}


@app.put("/platform/grants")
def put_platform_grant(grant: PlatformGrant, principal: Principal = Depends(current_principal)):
    actor = actor_for(principal)
    require_platform_admin(principal)
    with connect() as conn:
        grant_role(conn, Principal(grant.issuer, grant.subject, grant.display_name), "platform", None, grant.role)
    required_audit(actor, "membership.grant", "principal", grant.issuer + "|" + grant.subject, "succeeded",
                   {"scope": "platform"}, {"role": grant.role})
    return {"issuer": grant.issuer, "subject": grant.subject, "role": grant.role}


@app.delete("/platform/grants")
def delete_platform_grant(grant: GrantReference, principal: Principal = Depends(current_principal)):
    actor = actor_for(principal)
    require_platform_admin(principal)
    if principal.issuer == grant.issuer and principal.subject == grant.subject:
        required_audit(actor, "membership.revoke", "principal", actor.identifier, "rejected", {"scope": "platform"},
                       {"reason": "self_revocation"})
        raise HTTPException(409, "A platform administrator cannot revoke its own final access")
    with connect() as conn:
        removed = revoke_role(conn, grant.issuer, grant.subject, "platform", None)
    if not removed:
        required_audit(actor, "membership.revoke", "principal", grant.issuer + "|" + grant.subject, "rejected",
                       {"scope": "platform"}, {"reason": "unknown_grant"})
        raise HTTPException(404, "Unknown platform grant")
    required_audit(actor, "membership.revoke", "principal", grant.issuer + "|" + grant.subject, "succeeded",
                   {"scope": "platform"})
    return {"issuer": grant.issuer, "subject": grant.subject, "revoked": True}


@app.get("/internal/tls", include_in_schema=False)
def allow_certificate(domain: str = Query(max_length=253)):
    # Caddy on-demand TLS gate: only registered projects may obtain certificates.
    suffix = "." + os.environ["APPS_DOMAIN"]
    if not domain.endswith(suffix):
        raise HTTPException(403)
    name = domain[:-len(suffix)]
    with connect() as conn:
        row = conn.execute("SELECT status FROM projects WHERE name=%s", (name,)).fetchone()
    if not row or row[0] != "applied":
        raise HTTPException(403)
    return {"allowed": True}
