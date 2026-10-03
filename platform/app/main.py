"""OIDC-authenticated, project-scoped platform API."""
import hashlib
import hmac
import logging
import os
import threading
import csv
import io
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional, Union
from contextlib import asynccontextmanager
from uuid import UUID

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from kubernetes import config, dynamic
from kubernetes.client import ApiClient
from kubernetes.client.exceptions import ApiException
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .audit import Actor, initialize as initialize_audit, read_events, record_event, redact
from .authorization import (bootstrap_platform_admin, grant as grant_role, initialize as initialize_authorization,
                            grants_for_project, is_allowed, is_platform_admin, projects_for_principal, revoke as revoke_role,
                            upsert_principal)
from .catalog import ensure_default_application, initialize as initialize_catalog
from .images import ImageResolutionError, allowed_registries, resolve_image
from .identity import AuthenticationError, Principal, configured_verifier
from .spec import CAPABILITIES, ApplicationEnvelope, error_code, to_flat
from .config import normalize_configuration, observe_activation
from .manifests import normalize_resources, resources, validate_name
from .monitoring import discovery_loop, publish_catalog
from .operations import operation_loop
from .drift import drift_loop, observe_drift
from .readiness import observe_deployment
from .usage import observe_usage
from .logs import observe_logs
from .retirement import removal_scope
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
    drift_worker = threading.Thread(
        target=drift_loop,
        args=(stop, connect, lambda: runtime, best_effort_audit, log,
              float(os.environ.get("DRIFT_SCAN_INTERVAL_SECONDS", "300"))),
        daemon=True,
    )
    drift_worker.start()
    try:
        yield
    finally:
        stop.set()
        worker.join(timeout=6)
        security_worker.join(timeout=6)
        operation_worker.join(timeout=6)
        drift_worker.join(timeout=6)

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
    if request.method == "PUT" and request.url.path.startswith("/projects/") and request.url.path.count("/") == 2:
        return JSONResponse(status_code=422, content={
            "detail": jsonable_encoder(exc.errors()),
            "code": error_code(getattr(exc, "body", None), exc.errors())})
    return await request_validation_exception_handler(request, exc)

class Project(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    image: str = Field(min_length=1, max_length=512, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9./_:@-]+$")
    port: int = Field(default=8080, ge=1024, le=65535)
    probe_profile: Literal["status", "hello-world"] = "status"
    resources: Optional[dict] = None
    configuration: Optional[dict] = None

    @field_validator("resources")
    @classmethod
    def check_resources(cls, value):
        return None if value is None else normalize_resources(value)

    @field_validator("configuration")
    @classmethod
    def check_configuration(cls, value):
        return None if value is None else normalize_configuration(value)

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


@app.get("/v1/capabilities")
def capabilities(principal: Principal = Depends(current_principal)):
    """Declare what a deployment spec may request in each environment."""
    return {**CAPABILITIES, "imageRegistries": sorted(allowed_registries())}


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

class RevisionConflict(Exception):
    def __init__(self, current: int):
        self.current = current


def expected_revision(value: Optional[str]) -> Optional[int]:
    """Parse `If-Match: <revision>` (0 means the project must not exist yet)."""
    if value is None:
        return None
    text = value.strip()
    if text.startswith("W/"):
        text = text[2:]
    text = text.strip('"')
    if not text.isascii() or not text.isdigit():
        raise HTTPException(400, "If-Match must be a revision number")
    return int(text)


class RevisionNotFound(Exception):
    pass


class ProjectRetired(Exception):
    pass


def queue_deploy(conn, principal: Principal, name: str, spec: Optional[dict],
                 expected: Optional[int], target: Optional[int] = None):
    """Persist a revision and its deploy operation under the global lock.

    With `target`, the spec is read from that retained revision inside the lock, so pruning
    cannot race with a rollback. Returns (operation_id, state, revision).
    """
    # Serialize project revisions and active-operation deduplication.
    conn.execute("SELECT pg_advisory_lock(731904)")
    try:
        with conn.transaction():
            if expected is not None:
                current = conn.execute("""SELECT max(r.revision) FROM projects p
                    JOIN project_environments e ON e.project_id=p.project_id
                    JOIN project_applications a ON a.environment_id=e.environment_id
                    JOIN application_revisions r ON r.application_id=a.application_id
                    WHERE p.name=%s""", (name,)).fetchone()
                current_revision = current[0] if current and current[0] is not None else 0
                if current_revision != expected:
                    raise RevisionConflict(current_revision)
            if target is not None:
                found = conn.execute("""SELECT r.spec, p.status FROM projects p
                    JOIN project_environments e ON e.project_id=p.project_id
                    JOIN project_applications a ON a.environment_id=e.environment_id
                    JOIN application_revisions r ON r.application_id=a.application_id
                    WHERE p.name=%s AND r.revision=%s""", (name, target)).fetchone()
                if found is None:
                    raise RevisionNotFound()
                if found[1] == "retired":
                    raise ProjectRetired()
                spec = found[0]
            row = conn.execute("""INSERT INTO projects(name,spec,status) VALUES (%s,%s,'provisioning')
                ON CONFLICT(name) DO UPDATE SET spec=excluded.spec,
                status='provisioning',updated_at=now()
                RETURNING project_id""", (name, Jsonb(spec))).fetchone()
            if row is None:
                raise RuntimeError("Could not resolve project identity")
            application_id, revision = ensure_default_application(conn, row[0], name, spec)
            pending = conn.execute("""SELECT operation_id, state FROM application_operations
                WHERE application_id=%s AND revision=%s AND operation_kind=%s
                AND state IN ('queued', 'running')
                ORDER BY created_at DESC LIMIT 1""",
                (application_id, revision, "deploy")).fetchone()
            if pending:
                return pending[0], pending[1], revision
            envelope = {
                "project_id": str(row[0]),
                "application_id": str(application_id),
                "project_slug": name,
                "revision": revision,
                "spec": spec,
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
            return queued[0], "queued", revision
    finally:
        conn.execute("SELECT pg_advisory_unlock(731904)")


@app.put("/projects/{name}")
def provision(name: str, body: Union[ApplicationEnvelope, Project],
              principal: Principal = Depends(current_principal),
              if_match: Optional[str] = Header(None)):
    """Accept the flat project body or a versioned `Application` envelope.

    An optional `If-Match: <revision>` header makes the update conditional on the
    current desired revision; a stale value returns 409 with the current revision.
    """
    if isinstance(body, ApplicationEnvelope):
        try:
            project = Project.model_validate(to_flat(body.model_dump(exclude_none=True)))
        except ValidationError as exc:
            raise RequestValidationError(exc.errors(include_context=False))
    else:
        project = body
    actor = actor_for(principal)
    require_permission(principal, "change", name)
    try:
        expected = expected_revision(if_match)
    except HTTPException:
        required_audit(actor, "project.provision", "project", name, "rejected", {"project": name},
                       {"reason": "invalid_if_match"})
        raise
    if name != project.name:
        required_audit(actor, "project.provision", "project", name, "rejected", {"project": name},
                       {"reason": "path_name_mismatch"})
        raise HTTPException(400, "Path and project name must match")
    # Resolve before taking locks or writing so registry failures have no side effects.
    try:
        resolved_image = resolve_image(project.image)
    except ImageResolutionError as exc:
        status_code = 503 if exc.reason == "unavailable" else 422
        required_audit(actor, "project.provision", "project", name, "rejected", {"project": name},
                       {"reason": "image_" + exc.reason})
        messages = {
            "not_found": "Image tag or digest was not found in its registry",
            "unsupported_registry": "Image registry is not supported by this platform",
            "unavailable": "Image registry is unavailable; retry the same PUT",
        }
        raise HTTPException(status_code, messages[exc.reason])
    spec = {**project.model_dump(exclude_none=True), "resolved_image": resolved_image}
    try:
        with connect() as conn:
            operation_id, operation_state, revision = queue_deploy(
                conn, principal, name, spec, expected)
    except RevisionConflict as conflict:
        required_audit(actor, "project.provision", "project", name, "rejected", {"project": name},
                       {"reason": "revision_conflict", "expected": expected, "current": conflict.current})
        return JSONResponse(status_code=409, content={
            "detail": "The project changed since the expected revision; re-read it and retry",
            "code": "revision_conflict", "current_revision": conflict.current})
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


@app.get("/projects/{name}/drift")
def drift(name: str, principal: Principal = Depends(current_principal)):
    """Compare the live Deployment with the desired revision; report only, never repair."""
    require_permission(principal, "view", name)
    actor = actor_for(principal)
    with connect() as conn:
        current = conn.execute("""SELECT max(r.revision), (array_agg(r.spec ORDER BY r.revision DESC))[1]
            FROM projects p
            JOIN project_environments e ON e.project_id=p.project_id
            JOIN project_applications a ON a.environment_id=e.environment_id
            JOIN application_revisions r ON r.application_id=a.application_id
            WHERE p.name=%s""", (name,)).fetchone()
    if current is None or current[0] is None:
        required_audit(actor, "project.drift.inspect", "project", name, "rejected", {"project": name},
                       {"reason": "not_found"})
        raise HTTPException(404, "Unknown project")
    result = observe_drift(runtime, name, current[1], log)
    detail = {"revision": current[0], "state": result["state"],
              "fields": [d["field"] for d in result["differences"]]}
    required_audit(actor, "project.drift.detected" if result["state"] == "drifted" else "project.drift.inspect",
                   "project", name, "succeeded", {"project": name}, detail)
    return {"project": name, "revision": current[0], **result}


class ConfigurationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    values: dict


def current_spec(name: str):
    with connect() as conn:
        return conn.execute("""SELECT max(r.revision), (array_agg(r.spec ORDER BY r.revision DESC))[1], p.status
            FROM projects p
            JOIN project_environments e ON e.project_id=p.project_id
            JOIN project_applications a ON a.environment_id=e.environment_id
            JOIN application_revisions r ON r.application_id=a.application_id
            WHERE p.name=%s GROUP BY p.status""", (name,)).fetchone()


@app.get("/projects/{name}/configuration")
def get_configuration(name: str, principal: Principal = Depends(current_principal)):
    """Desired configuration values and whether the running deployment has activated them."""
    require_permission(principal, "view", name)
    actor = actor_for(principal)
    current = current_spec(name)
    if current is None or current[0] is None:
        required_audit(actor, "project.configuration.read", "project", name, "rejected",
                       {"project": name}, {"reason": "not_found"})
        raise HTTPException(404, "Unknown project")
    values = current[1].get("configuration") or {}
    activation = observe_activation(runtime, name, values)
    required_audit(actor, "project.configuration.read", "project", name, "succeeded",
                   {"project": name}, {"revision": current[0], "names": sorted(values)})
    return {"project": name, "revision": current[0], "values": values, "activation": activation}


@app.put("/projects/{name}/configuration")
def put_configuration(name: str, body: ConfigurationBody,
                      principal: Principal = Depends(current_principal),
                      if_match: Optional[str] = Header(None)):
    """Replace the configuration values: adds, updates and removes in one validated revision.

    The change is a new desired revision (conditional on `If-Match`) that rolls the pods.
    """
    require_permission(principal, "change", name)
    actor = actor_for(principal)
    try:
        expected = expected_revision(if_match)
    except HTTPException:
        required_audit(actor, "project.configuration.update", "project", name, "rejected",
                       {"project": name}, {"reason": "invalid_if_match"})
        raise
    try:
        values = normalize_configuration(body.values)
    except ValueError as exc:
        required_audit(actor, "project.configuration.update", "project", name, "rejected",
                       {"project": name}, {"reason": "invalid_configuration", "names": sorted(map(str, body.values))})
        return JSONResponse(status_code=422, content={"detail": str(exc), "code": "invalid_configuration"})
    current = current_spec(name)
    if current is None or current[0] is None:
        required_audit(actor, "project.configuration.update", "project", name, "rejected",
                       {"project": name}, {"reason": "not_found"})
        raise HTTPException(404, "Unknown project")
    if current[2] == "retired":
        required_audit(actor, "project.configuration.update", "project", name, "rejected",
                       {"project": name}, {"reason": "retired"})
        raise HTTPException(409, "Project is retired")
    spec = {k: v for k, v in current[1].items() if k != "configuration"}
    if values:
        spec["configuration"] = values
    try:
        with connect() as conn:
            operation_id, operation_state, revision = queue_deploy(
                conn, principal, name, spec, expected if expected is not None else current[0])
    except RevisionConflict as conflict:
        required_audit(actor, "project.configuration.update", "project", name, "rejected",
                       {"project": name}, {"reason": "revision_conflict", "expected": expected,
                                           "current": conflict.current})
        return JSONResponse(status_code=409, content={
            "detail": "The project changed since the expected revision; re-read it and retry",
            "code": "revision_conflict", "current_revision": conflict.current})
    except Exception as exc:
        required_audit(actor, "project.configuration.update", "project", name, "failed",
                       {"project": name}, {"error_type": type(exc).__name__})
        raise HTTPException(503, "Configuration change failed; retry the same request.")
    required_audit(actor, "project.configuration.update", "project", name, "succeeded",
                   {"project": name}, {"revision": revision, "operation_id": str(operation_id),
                                       "names": sorted(values)})
    return JSONResponse(status_code=202, content={
        "operation_id": str(operation_id), "state": operation_state, "revision": revision,
        "rollout_required": True, "status_url": f"/v1/operations/{operation_id}"})


class Rollback(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(gt=0)


@app.get("/projects/{name}/revisions")
def revisions(name: str, principal: Principal = Depends(current_principal)):
    """List the retained desired revisions, newest first."""
    require_permission(principal, "view", name)
    actor = actor_for(principal)
    with connect() as conn:
        rows = conn.execute("""SELECT r.revision, r.created_at, r.spec
            FROM projects p
            JOIN project_environments e ON e.project_id=p.project_id
            JOIN project_applications a ON a.environment_id=e.environment_id
            JOIN application_revisions r ON r.application_id=a.application_id
            WHERE p.name=%s ORDER BY r.revision DESC""", (name,)).fetchall()
    if not rows:
        required_audit(actor, "project.revisions.list", "project", name, "rejected",
                       {"project": name}, {"reason": "not_found"})
        raise HTTPException(404, "Unknown project")
    required_audit(actor, "project.revisions.list", "project", name, "succeeded",
                   {"project": name}, {"count": len(rows)})
    return {"project": name, "current_revision": rows[0][0], "revisions": [
        {"revision": r[0], "created_at": r[1].isoformat(), "current": r[0] == rows[0][0],
         "image": r[2].get("resolved_image", r[2]["image"]), "port": r[2]["port"],
         "resources": r[2].get("resources")}
        for r in rows]}


@app.get("/projects/{name}/resource-usage")
def resource_usage(name: str, principal: Principal = Depends(current_principal)):
    """Current CPU and memory per pod; missing, stale and unavailable metrics are labelled in `state`."""
    require_permission(principal, "view", name)
    actor = actor_for(principal)
    with connect() as conn:
        known = conn.execute("SELECT 1 FROM projects WHERE name=%s", (name,)).fetchone()
    if not known:
        required_audit(actor, "project.usage.inspect", "project", name, "rejected",
                       {"project": name}, {"reason": "not_found"})
        raise HTTPException(404, "Unknown project")
    usage = observe_usage(runtime, name, log)
    required_audit(actor, "project.usage.inspect", "project", name, "succeeded",
                   {"project": name}, {"state": usage["state"]})
    return {"project": name, **usage}


@app.get("/projects/{name}/logs")
def project_logs(name: str, tail: int = Query(200, ge=1, le=1000),
                 since_seconds: Optional[int] = Query(None, ge=1, le=86400),
                 principal: Principal = Depends(current_principal)):
    """Recent timestamped log lines with pod and container attribution; never streams."""
    require_permission(principal, "view", name)
    actor = actor_for(principal)
    with connect() as conn:
        known = conn.execute("SELECT 1 FROM projects WHERE name=%s", (name,)).fetchone()
    if not known:
        required_audit(actor, "project.logs.read", "project", name, "rejected",
                       {"project": name}, {"reason": "not_found"})
        raise HTTPException(404, "Unknown project")
    result = observe_logs(runtime, name, log, tail, since_seconds)
    required_audit(actor, "project.logs.read", "project", name, "succeeded",
                   {"project": name}, {"state": result["state"], "lines": len(result["lines"])})
    return {"project": name, **result}


@app.post("/projects/{name}/rollback")
def rollback(name: str, body: Rollback, principal: Principal = Depends(current_principal),
             if_match: Optional[str] = Header(None)):
    """Re-apply a retained revision as a new revision; databases are never rolled back."""
    actor = actor_for(principal)
    require_permission(principal, "change", name)
    try:
        expected = expected_revision(if_match)
    except HTTPException:
        required_audit(actor, "project.rollback", "project", name, "rejected", {"project": name},
                       {"reason": "invalid_if_match"})
        raise
    detail = {"target": body.revision}
    try:
        with connect() as conn:
            operation_id, operation_state, revision = queue_deploy(
                conn, principal, name, None, expected, target=body.revision)
    except RevisionConflict as conflict:
        required_audit(actor, "project.rollback", "project", name, "rejected", {"project": name},
                       {**detail, "reason": "revision_conflict", "current": conflict.current})
        return JSONResponse(status_code=409, content={
            "detail": "The project changed since the expected revision; re-read it and retry",
            "code": "revision_conflict", "current_revision": conflict.current})
    except RevisionNotFound:
        required_audit(actor, "project.rollback", "project", name, "rejected", {"project": name},
                       {**detail, "reason": "revision_not_found"})
        raise HTTPException(404, "Unknown project or revision; it may have been pruned")
    except ProjectRetired:
        required_audit(actor, "project.rollback", "project", name, "rejected", {"project": name},
                       {**detail, "reason": "project_retired"})
        raise HTTPException(409, "Retired projects cannot be rolled back")
    except Exception as exc:
        required_audit(actor, "project.rollback", "project", name, "failed", {"project": name},
                       {**detail, "error_type": type(exc).__name__})
        log.error("Rollback failed: %s (%s)", name, type(exc).__name__)
        raise HTTPException(503, "Rollback failed; retry the same request. Existing data is retained.")
    required_audit(actor, "project.rollback", "project", name, "succeeded", {"project": name},
                   {**detail, "state": operation_state, "revision": revision,
                    "operation_id": str(operation_id)})
    return JSONResponse(status_code=202, content={
        "operation_id": str(operation_id),
        "state": operation_state,
        "revision": revision,
        "status_url": f"/v1/operations/{operation_id}",
    })


@app.post("/projects/{name}/restart")
def restart(name: str, principal: Principal = Depends(current_principal)):
    """Queue a rolling restart of the current desired revision without changing the spec."""
    actor = actor_for(principal)
    require_permission(principal, "change", name)
    try:
        validate_name(name)
    except ValueError:
        required_audit(actor, "project.restart", "project", name, "rejected", {"project": name},
                       {"reason": "invalid_name"})
        raise HTTPException(400, "Invalid project name")
    try:
        with connect() as conn:
            conn.execute("SELECT pg_advisory_lock(731904)")
            try:
                with conn.transaction():
                    current = conn.execute("""SELECT p.project_id, p.status, a.application_id, r.revision, r.spec
                        FROM projects p
                        JOIN project_environments e ON e.project_id=p.project_id
                        JOIN project_applications a ON a.environment_id=e.environment_id
                        JOIN application_revisions r ON r.application_id=a.application_id
                        WHERE p.name=%s ORDER BY r.revision DESC LIMIT 1""", (name,)).fetchone()
                    if current is None:
                        raise HTTPException(404, "Unknown project")
                    project_id, project_status, application_id, revision, spec = current
                    if project_status != "applied":
                        raise HTTPException(409, "Only an applied project can be restarted")
                    pending = conn.execute("""SELECT operation_id, state FROM application_operations
                        WHERE application_id=%s AND revision=%s AND operation_kind=%s
                        AND state IN ('queued', 'running')
                        ORDER BY created_at DESC LIMIT 1""",
                        (application_id, revision, "restart")).fetchone()
                    if pending:
                        operation_id, operation_state = pending
                    else:
                        envelope = {
                            "project_id": str(project_id),
                            "application_id": str(application_id),
                            "project_slug": name,
                            "revision": revision,
                            "spec": spec,
                        }
                        queued = conn.execute("""INSERT INTO application_operations(
                            application_id, revision, operation_kind, state, actor_issuer, actor_subject,
                            envelope_version, envelope)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                            RETURNING operation_id""",
                            (application_id, revision, "restart", "queued",
                             principal.issuer, principal.subject, 1, Jsonb(envelope))).fetchone()
                        if queued is None:
                            raise RuntimeError("Could not persist restart operation")
                        operation_id = queued[0]
                        operation_state = "queued"
            finally:
                conn.execute("SELECT pg_advisory_unlock(731904)")
    except HTTPException as exc:
        required_audit(actor, "project.restart", "project", name, "rejected", {"project": name},
                       {"status_code": exc.status_code})
        raise
    except Exception as exc:
        required_audit(actor, "project.restart", "project", name, "failed", {"project": name},
                       {"error_type": type(exc).__name__})
        log.error("Project restart request failed: %s (%s)", name, type(exc).__name__)
        raise HTTPException(503, "Restart request failed; retry the same request.")
    required_audit(actor, "project.restart", "project", name, "succeeded", {"project": name},
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
    readiness = observe_deployment(runtime, row[6], row[7].get("resolved_image", row[7]["image"]), log)
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
    scope_token: Optional[str] = Field(default=None, max_length=128)


ACTIVE_OPERATION_SQL = """SELECT 1
    FROM application_operations o
    JOIN project_applications a ON a.application_id=o.application_id
    JOIN project_environments e ON e.environment_id=a.environment_id
    JOIN projects p ON p.project_id=e.project_id
    WHERE p.name=%s AND o.state IN ('queued', 'running')
    LIMIT 1"""


def current_retirement_scope(conn, name):
    row = conn.execute("""SELECT max(r.revision), (array_agg(r.spec ORDER BY r.revision DESC))[1]
        FROM projects p
        JOIN project_environments e ON e.project_id=p.project_id
        JOIN project_applications a ON a.environment_id=e.environment_id
        JOIN application_revisions r ON r.application_id=a.application_id
        WHERE p.name=%s""", (name,)).fetchone()
    if row is None or row[0] is None:
        return None
    return removal_scope(name, row[0], row[1], os.environ["APPS_DOMAIN"])


def namespace_exists(name):
    try:
        runtime.resources.get(api_version="v1", kind="Namespace").get(name="project-" + name)
    except ApiException as exc:
        if exc.status != 404:
            raise
        return False
    return True


@app.get("/projects/{name}/retirement-preview")
def retirement_preview(name: str, principal: Principal = Depends(current_principal)):
    """Show what retirement would remove and keep; the token pins this scope for confirmation."""
    actor = actor_for(principal)
    require_permission(principal, "retire", name)
    try:
        validate_name(name)
    except ValueError:
        raise HTTPException(400, "Invalid project name")
    with connect() as conn:
        status = conn.execute("SELECT status FROM projects WHERE name=%s", (name,)).fetchone()
        scope = current_retirement_scope(conn, name) if status else None
        active = bool(status and conn.execute(ACTIVE_OPERATION_SQL, (name,)).fetchone())
    if scope is None:
        required_audit(actor, "project.retire.preview", "project", name, "rejected",
                       {"project": name}, {"reason": "not_found"})
        raise HTTPException(404, "Unknown project")
    blockers = (["active_operation"] if active else []) + (["already_retired"] if status[0] == "retired" else [])
    required_audit(actor, "project.retire.preview", "project", name, "succeeded",
                   {"project": name}, {"revision": scope["revision"], "blockers": blockers})
    return {**scope, "status": status[0], "blockers": blockers}


@app.post("/projects/{name}/retire")
def retire(name: str, confirmation: Retirement, principal: Principal = Depends(current_principal)):
    """Retire a project, keeping its catalog entry, database and role.

    With the `scope_token` from the preview the platform deletes the project namespace itself; a
    namespace that is still terminating answers 202 and the identical request is retried. Without
    a token the namespace must already have been removed manually.
    """
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
    retiring = False
    try:
        with connect() as conn:
            conn.execute("SELECT pg_advisory_lock(731904)")
            try:
                if not conn.execute("SELECT status FROM projects WHERE name=%s", (name,)).fetchone():
                    raise HTTPException(404, "Unknown project")
                if conn.execute(ACTIVE_OPERATION_SQL, (name,)).fetchone():
                    raise HTTPException(409, "Wait for active application operations before retirement")
                scope = current_retirement_scope(conn, name)
                if confirmation.scope_token is not None:
                    if scope is None or not hmac.compare_digest(confirmation.scope_token, scope["scope_token"]):
                        required_audit(actor, "project.retire", "project", name, "rejected",
                                       {"project": name}, {"reason": "scope_changed"})
                        return JSONResponse(status_code=409, content={
                            "detail": "The project changed since the preview; request a new preview",
                            "code": "scope_changed"})
                    try:
                        runtime.resources.get(api_version="v1", kind="Namespace").delete(name="project-" + name)
                    except ApiException as exc:
                        if exc.status != 404:
                            raise
                    required_audit(actor, "project.retire.requested", "project", name, "succeeded",
                                   {"project": name}, {"revision": scope["revision"]})
                if namespace_exists(name):
                    if confirmation.scope_token is None:
                        raise HTTPException(409, "Remove the project namespace and wait for deletion before retirement")
                    retiring = True
                else:
                    with conn.transaction():
                        conn.execute("UPDATE projects SET status='retired',updated_at=now() WHERE name=%s", (name,))
                        if scope is not None:
                            conn.execute("""INSERT INTO project_retirements(project_id, inventory)
                                SELECT project_id, %s FROM projects WHERE name=%s
                                ON CONFLICT(project_id) DO UPDATE
                                SET inventory=excluded.inventory, retired_at=now()""",
                                         (Jsonb({"revision": scope["revision"], **scope["retains"]}), name))
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
    if retiring:
        return JSONResponse(status_code=202, content={
            "name": name, "status": "retiring", "data_retained": True,
            "detail": "Namespace deletion is in progress; repeat the same request to complete retirement"})
    required_audit(actor, "project.retire", "project", name, "succeeded", {"project": name},
                   {"status": "retired", "data_retained": True})
    return {"name": name, "status": "retired", "data_retained": True,
            "retained": scope["retains"] if scope else None}


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
