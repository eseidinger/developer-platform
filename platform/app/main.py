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
from uuid import UUID, uuid4

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
from fastapi import Body, Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from kubernetes import config, dynamic
from kubernetes.client import ApiClient
from kubernetes.client.exceptions import ApiException
from pydantic import BaseModel, ConfigDict, Field, ValidationError, ValidationInfo, field_validator, model_validator

from .audit import Actor, initialize as initialize_audit, read_events, record_event, redact
from .authorization import (bootstrap_platform_admin, grant as grant_role, initialize as initialize_authorization,
                            grants_for_platform, grants_for_project, is_allowed, is_platform_admin, projects_for_principal, revoke as revoke_role,
                            upsert_principal)
from .catalog import component_view, ensure_default_application, initialize as initialize_catalog
from .images import ImageResolutionError, allowed_registries, resolve_image
from .identity import AuthenticationError, Principal, configured_verifier
from .spec import CAPABILITIES, ApplicationEnvelope, ApplicationEnvelopeV1Alpha2, error_code, to_flat
from .config import normalize_configuration, observe_activation
from .manifests import component_resources, normalize_resources, resources, validate_name
from .project_policy import validate_component_capacity
from .monitoring import discovery_loop, publish_catalog
from .operations import operation_loop
from .drift import drift_loop, observe_drift
from .readiness import observe_deployment
from .usage import observe_usage
from .inventory import observe_inventory, observe_cluster_capacity
from .capacity_admission import assess as assess_capacity, snapshot as capacity_admission_snapshot
from .rollback import dependency_report
from .logs import observe_logs
from .component_status import observe_components
from .secrets import (SecretsUnavailable, MAX_SECRETS, confirm_secret, observe_secret_activation, read_secret,
                      remove_secret, revert_secret, roll_pods, validate_secret_name, validate_secret_value, write_secret)
from .retirement import purge_scope_token, removal_scope, scope_token as retirement_scope_token
from .security_alerts import security_alert_loop
from .deployment_credentials import access_scope, cleanup_loop as credential_cleanup_loop
from .deployment_credentials import initialize as initialize_deployment_credentials, record_use
from .deployment_credentials import public_record as public_credential_record
from .keycloak_credentials import ProviderError as CredentialProviderError
from .keycloak_credentials import create_client as create_credential_client, delete_client as delete_credential_client

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
            name TEXT PRIMARY KEY, spec JSONB, status TEXT NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now())""")
        conn.execute("ALTER TABLE projects ALTER COLUMN spec DROP NOT NULL")
        conn.execute("""CREATE TABLE IF NOT EXISTS data_service_recovery_requests (
            request_id UUID PRIMARY KEY, project TEXT NOT NULL REFERENCES projects(name),
            reason TEXT NOT NULL, status TEXT NOT NULL, requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            requested_by TEXT NOT NULL, reviewed_at TIMESTAMPTZ, reviewed_by TEXT)""")
        initialize_catalog(conn)
        initialize_audit(conn)
        initialize_authorization(conn)
        initialize_deployment_credentials(conn)
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
        args=(stop, connect, password_for, provision_database, apply, resources, publish_catalog, log, remove),
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
    credential_cleanup_worker = threading.Thread(
        target=credential_cleanup_loop,
        args=(stop, connect, delete_credential_client, best_effort_audit, log), daemon=True,
    )
    credential_cleanup_worker.start()
    try:
        yield
    finally:
        stop.set()
        worker.join(timeout=6)
        security_worker.join(timeout=6)
        operation_worker.join(timeout=6)
        drift_worker.join(timeout=6)
        credential_cleanup_worker.join(timeout=6)

app = FastAPI(title="Docker-based Developer Platform Lab", lifespan=lifespan)
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
app.mount("/assets", StaticFiles(directory=os.path.join(STATIC_DIR, "assets"), check_dir=False), name="static-assets")


@app.get("/", include_in_schema=False)
def portal():
    """Serve the built browser portal without embedding credentials in the API."""
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/projects/{name}", include_in_schema=False)
@app.get("/platform/administration", include_in_schema=False)
def portal_route(name: str | None = None):
    """Serve the browser portal for supported client-side routes and deep links."""
    return portal()


@app.get("/favicon.svg", include_in_schema=False)
def favicon():
    return FileResponse(os.path.join(STATIC_DIR, "favicon.svg"))


@app.get("/icons.svg", include_in_schema=False)
def icons():
    return FileResponse(os.path.join(STATIC_DIR, "icons.svg"))


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
        machine = access_scope(conn, principal)
        if machine is not None and not machine.active:
            best_effort_audit(actor_for(principal), "authentication", "automation-credential",
                              str(machine.credential_id), "denied", {"project": machine.project},
                              {"reason": "revoked_or_expired", "kind": machine.kind})
            raise HTTPException(403, "Automation credential is revoked or expired")
        record_use(conn, principal)
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


def require_human_platform_admin(principal: Principal) -> None:
    """Require a platform administrator that is not backed by an automation credential."""
    require_platform_admin(principal)
    with connect() as conn:
        machine = access_scope(conn, principal)
    if machine is None:
        return
    required_audit(actor_for(principal), "authorization", "platform", None, "denied",
                   {"scope": "platform"}, {"permission": "human-platform-admin"})
    raise HTTPException(403, "A human platform administrator is required")


def require_test_identity_manager(principal: Principal) -> None:
    """Permit a human platform administrator or the dedicated test-runner profile."""
    require_platform_admin(principal)
    with connect() as conn:
        machine = access_scope(conn, principal)
    if machine is None or machine.kind == "test-runner":
        return
    required_audit(actor_for(principal), "authorization", "platform", None, "denied",
                   {"scope": "platform"}, {"permission": "test-identity-manager"})
    raise HTTPException(403, "Only a human platform administrator or test runner may manage test identities")


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


@app.exception_handler(psycopg.OperationalError)
async def database_unavailable(request: Request, exc: psycopg.OperationalError):
    """Fail closed without leaking connection details when the control database is unavailable."""
    log.error("Platform database unavailable while handling request")
    return JSONResponse(status_code=503, content={"detail": "Platform database is temporarily unavailable"})

class Project(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    image: Optional[str] = Field(default=None, min_length=1, max_length=512, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9./_:@-]+$")
    port: int = Field(default=8080, ge=1024, le=65535)
    probe_profile: Literal["status", "hello-world"] = "status"
    readiness_path: Optional[str] = Field(default=None, min_length=1, max_length=256,
                                          pattern=r"^/[A-Za-z0-9._~!$&'()*+,;=:@%/-]*$")
    readiness_port: Optional[int] = Field(default=None, ge=1024, le=65535)
    resources: Optional[dict] = None
    configuration: Optional[dict] = None
    components: Optional[list[dict]] = None

    @field_validator("components")
    @classmethod
    def components_require_versioned_envelope(cls, value, info: ValidationInfo):
        if value is not None and not (info.context or {}).get("versioned_envelope"):
            raise ValueError("components require a versioned Application envelope")
        return value

    @model_validator(mode="after")
    def one_workload_shape(self):
        if (self.image is None) == (self.components is None):
            raise ValueError("provide either image or components")
        if self.readiness_port is not None and self.image is not None and self.readiness_port != self.port:
            raise ValueError("readiness_port must equal the application port")
        components = self.components if self.components is not None else [{"type": "service", "resources": self.resources}]
        validate_component_capacity(self.name, components)
        return self

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


class DataServiceRecoveryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: Literal["unavailable", "access", "data_integrity", "other"]


class DataServiceRecoveryReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["acknowledged", "resolved"]


class DeploymentCredentialCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")
    expires_in_days: int = Field(default=30, ge=1, le=90)


class DeploymentCredentialRotate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expires_in_days: int = Field(default=30, ge=1, le=90)
    overlap_hours: int = Field(default=1, ge=0, le=24)


class EmptyProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str

    @field_validator("name")
    @classmethod
    def check_name(cls, value):
        return validate_name(value)


class TestRunnerCredentialCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")
    expires_in_days: int = Field(default=7, ge=1, le=30)


class TestIdentityCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")
    role: Literal["viewer", "developer", "project-admin", "platform-admin"]
    project: str | None = None
    test_run_id: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")
    expires_in_hours: int = Field(default=2, ge=1, le=24)

    @model_validator(mode="after")
    def role_scope(self):
        if self.role == "platform-admin" and self.project is not None:
            raise ValueError("platform-admin must use platform scope")
        if self.role != "platform-admin" and self.project is None:
            raise ValueError("project roles require a project")
        if self.project is not None:
            self.project = validate_name(self.project)
        return self

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


def remove(manifest):
    """Delete one managed Kubernetes object during component reconciliation."""
    resource = runtime.resources.get(api_version=manifest["apiVersion"], kind=manifest["kind"])
    args = {"name": manifest["metadata"]["name"]}
    if resource.namespaced:
        args["namespace"] = manifest["metadata"]["namespace"]
    resource.delete(**args)

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


@app.post("/projects")
def create_empty_project(body: EmptyProjectCreate, principal: Principal = Depends(current_principal)):
    """Create an authorization and credential scope before its first deployment."""
    require_platform_admin(principal)
    actor = actor_for(principal)
    with connect() as conn:
        row = conn.execute("""INSERT INTO projects(name, spec, status) VALUES (%s, NULL, 'empty')
            ON CONFLICT(name) DO NOTHING RETURNING name, status, updated_at""", (body.name,)).fetchone()
    if row is None:
        required_audit(actor, "project.create", "project", body.name, "rejected",
                       {"project": body.name}, {"reason": "name_in_use"})
        return JSONResponse(status_code=409, content={
            "detail": "Project name is already in use", "code": "name_in_use"})
    required_audit(actor, "project.create", "project", body.name, "succeeded",
                   {"project": body.name}, {"status": "empty"})
    return JSONResponse(status_code=201, content=jsonable_encoder({
        "name": row[0], "status": row[1], "spec": None, "created_at": row[2]}))


@app.get("/v1/capabilities")
def capabilities(principal: Principal = Depends(current_principal)):
    """Declare what a deployment spec may request in each environment."""
    return {**CAPABILITIES, "imageRegistries": sorted(allowed_registries())}


@app.post("/projects/{name}/deployment-credentials")
def create_deployment_credential(name: str, body: DeploymentCredentialCreate,
                                 principal: Principal = Depends(current_principal)):
    """Create a project-scoped OIDC client and return its secret exactly once."""
    require_permission(principal, "grant", name)
    actor = actor_for(principal)
    provider = None
    try:
        with connect() as conn:
            if not conn.execute("SELECT 1 FROM projects WHERE name=%s", (name,)).fetchone():
                raise HTTPException(404, "Unknown project")
        provider = create_credential_client(f"{name}: {body.name}")
        machine = Principal(verifier.issuer, provider["subject"], "CI " + body.name)
        with connect() as conn, conn.transaction():
            grant_role(conn, machine, "project", name, "developer")
            row = conn.execute("""INSERT INTO deployment_credentials(
                    name, project, issuer, subject, provider_client_id, provider_resource_id,
                    status, created_by_issuer, created_by_subject, expires_at)
                VALUES (%s,%s,%s,%s,%s,%s,'active',%s,%s,now()+make_interval(days => %s))
                RETURNING credential_id, name, kind, project, environment, status, created_at,
                          expires_at, expires_at<=now(), last_used_at, rotated_from, test_run_id""",
                (body.name, name, machine.issuer, machine.subject, provider["client_id"],
                 provider["provider_resource_id"], principal.issuer, principal.subject,
                 body.expires_in_days)).fetchone()
        result = {**public_credential_record(row), "token_endpoint": verifier.issuer + "/protocol/openid-connect/token",
                  "client_id": provider["client_id"], "client_secret": provider["client_secret"]}
    except HTTPException:
        raise
    except Exception as exc:
        if provider:
            try:
                delete_credential_client(provider["provider_resource_id"])
            except Exception:
                pass
        required_audit(actor, "deployment-credential.create", "project", name, "failed",
                       {"project": name}, {"error_type": type(exc).__name__})
        raise HTTPException(503, "Credential creation failed without returning a usable secret")
    required_audit(actor, "deployment-credential.create", "deployment-credential", result["credential_id"],
                   "succeeded", {"project": name}, {"name": body.name, "expires_at": result["expires_at"]})
    return JSONResponse(status_code=201, content=jsonable_encoder(result))


@app.get("/projects/{name}/deployment-credentials")
def list_deployment_credentials(name: str, principal: Principal = Depends(current_principal)):
    require_permission(principal, "grant", name)
    with connect() as conn:
        rows = conn.execute("""SELECT credential_id, name, kind, project, environment, status, created_at,
                expires_at, expires_at<=now(), last_used_at, rotated_from, test_run_id
            FROM deployment_credentials WHERE kind='deployment' AND project=%s
            ORDER BY created_at, credential_id""", (name,)).fetchall()
    required_audit(actor_for(principal), "deployment-credential.list", "project", name, "succeeded",
                   {"project": name}, {"count": len(rows)})
    return {"project": name, "credentials": [public_credential_record(row) for row in rows]}


@app.post("/projects/{name}/deployment-credentials/{credential_id}/rotate")
def rotate_deployment_credential(name: str, credential_id: UUID, body: DeploymentCredentialRotate,
                                 principal: Principal = Depends(current_principal)):
    """Create a linked replacement and bound how long the predecessor remains usable."""
    require_permission(principal, "grant", name)
    actor = actor_for(principal)
    with connect() as conn:
        predecessor = conn.execute("""SELECT name, status, expires_at>now()
            FROM deployment_credentials WHERE kind='deployment' AND project=%s AND credential_id=%s""",
                                   (name, credential_id)).fetchone()
    if predecessor is None:
        raise HTTPException(404, "Unknown deployment credential")
    if predecessor[1] != "active" or not predecessor[2]:
        raise HTTPException(409, "Only an active deployment credential can be rotated")

    suffix = "-r-" + uuid4().hex[:8]
    replacement_name = predecessor[0][:(64 - len(suffix))] + suffix
    provider = None
    try:
        provider = create_credential_client(f"{name}: {replacement_name}")
        machine = Principal(verifier.issuer, provider["subject"], "CI " + replacement_name)
        with connect() as conn, conn.transaction():
            locked = conn.execute("""SELECT status, expires_at>now()
                FROM deployment_credentials WHERE kind='deployment' AND project=%s AND credential_id=%s FOR UPDATE""",
                                  (name, credential_id)).fetchone()
            if locked is None or locked[0] != "active" or not locked[1]:
                raise RuntimeError("Deployment credential became inactive during rotation")
            grant_role(conn, machine, "project", name, "developer")
            row = conn.execute("""INSERT INTO deployment_credentials(
                    name, project, issuer, subject, provider_client_id, provider_resource_id,
                    status, created_by_issuer, created_by_subject, expires_at, rotated_from)
                VALUES (%s,%s,%s,%s,%s,%s,'active',%s,%s,now()+make_interval(days => %s),%s)
                RETURNING credential_id, name, kind, project, environment, status, created_at,
                          expires_at, expires_at<=now(), last_used_at, rotated_from, test_run_id""",
                (replacement_name, name, machine.issuer, machine.subject, provider["client_id"],
                 provider["provider_resource_id"], principal.issuer, principal.subject,
                 body.expires_in_days, credential_id)).fetchone()
            old_expiry = conn.execute("""UPDATE deployment_credentials
                    SET expires_at=LEAST(expires_at, now()+make_interval(hours => %s))
                WHERE credential_id=%s RETURNING expires_at""",
                                      (body.overlap_hours, credential_id)).fetchone()[0]
        result = {**public_credential_record(row),
                  "token_endpoint": verifier.issuer + "/protocol/openid-connect/token",
                  "client_id": provider["client_id"], "client_secret": provider["client_secret"],
                  "predecessor_id": str(credential_id), "predecessor_expires_at": old_expiry.isoformat()}
    except Exception as exc:
        if provider:
            try:
                delete_credential_client(provider["provider_resource_id"])
            except Exception:
                pass
        required_audit(actor, "deployment-credential.rotate", "deployment-credential", str(credential_id),
                       "failed", {"project": name}, {"error_type": type(exc).__name__})
        raise HTTPException(503, "Credential rotation failed without returning a usable secret")
    required_audit(actor, "deployment-credential.rotate", "deployment-credential", result["credential_id"],
                   "succeeded", {"project": name},
                   {"rotated_from": str(credential_id), "overlap_hours": body.overlap_hours,
                    "expires_at": result["expires_at"]})
    return JSONResponse(status_code=201, content=jsonable_encoder(result))


@app.delete("/projects/{name}/deployment-credentials/{credential_id}")
def revoke_deployment_credential(name: str, credential_id: UUID,
                                principal: Principal = Depends(current_principal)):
    """Deny platform access first, then remove the identity-provider client."""
    require_permission(principal, "grant", name)
    actor = actor_for(principal)
    with connect() as conn, conn.transaction():
        row = conn.execute("""SELECT provider_resource_id, issuer, subject, status
            FROM deployment_credentials WHERE kind='deployment' AND project=%s AND credential_id=%s FOR UPDATE""",
                           (name, credential_id)).fetchone()
        if row is None:
            raise HTTPException(404, "Unknown deployment credential")
        if row[3] == "revoked":
            return {"credential_id": str(credential_id), "status": "revoked"}
        revoke_role(conn, row[1], row[2], "project", name)
        conn.execute("""UPDATE deployment_credentials SET status='revocation_pending'
            WHERE credential_id=%s""", (credential_id,))
    try:
        delete_credential_client(row[0])
    except CredentialProviderError:
        required_audit(actor, "deployment-credential.revoke", "deployment-credential", str(credential_id),
                       "failed", {"project": name}, {"state": "revocation_pending"})
        return JSONResponse(status_code=202, content={"credential_id": str(credential_id),
                                                      "status": "revocation_pending"})
    with connect() as conn:
        conn.execute("""UPDATE deployment_credentials SET status='revoked', revoked_at=now()
            WHERE credential_id=%s""", (credential_id,))
    required_audit(actor, "deployment-credential.revoke", "deployment-credential", str(credential_id),
                   "succeeded", {"project": name}, {"status": "revoked"})
    return {"credential_id": str(credential_id), "status": "revoked"}


@app.post("/platform/test-runner-credentials")
def create_test_runner_credential(body: TestRunnerCredentialCreate,
                                  principal: Principal = Depends(current_principal)):
    """Create the reusable suite identity; automation identities cannot invoke this endpoint."""
    require_human_platform_admin(principal)
    actor = actor_for(principal)
    provider = None
    try:
        provider = create_credential_client("Platform test runner: " + body.name)
        machine = Principal(verifier.issuer, provider["subject"], "Test runner " + body.name)
        with connect() as conn, conn.transaction():
            grant_role(conn, machine, "platform", None, "platform-admin")
            row = conn.execute("""INSERT INTO deployment_credentials(
                    name, kind, project, issuer, subject, provider_client_id, provider_resource_id,
                    status, created_by_issuer, created_by_subject, expires_at)
                VALUES (%s,'test-runner',NULL,%s,%s,%s,%s,'active',%s,%s,
                        now()+make_interval(days => %s))
                RETURNING credential_id, name, kind, project, environment, status, created_at,
                          expires_at, expires_at<=now(), last_used_at, rotated_from, test_run_id""",
                (body.name, machine.issuer, machine.subject, provider["client_id"],
                 provider["provider_resource_id"], principal.issuer, principal.subject,
                 body.expires_in_days)).fetchone()
        result = {**public_credential_record(row),
                  "token_endpoint": verifier.issuer + "/protocol/openid-connect/token",
                  "client_id": provider["client_id"], "client_secret": provider["client_secret"]}
    except Exception as exc:
        if provider:
            try:
                delete_credential_client(provider["provider_resource_id"])
            except Exception:
                pass
        required_audit(actor, "test-runner-credential.create", "platform", None, "failed",
                       {"scope": "platform"}, {"error_type": type(exc).__name__})
        raise HTTPException(503, "Test-runner creation failed without returning a usable secret")
    required_audit(actor, "test-runner-credential.create", "automation-credential",
                   result["credential_id"], "succeeded", {"scope": "platform"},
                   {"name": body.name, "expires_at": result["expires_at"]})
    return JSONResponse(status_code=201, content=jsonable_encoder(result))


@app.get("/platform/test-runner-credentials")
def list_test_runner_credentials(principal: Principal = Depends(current_principal)):
    require_human_platform_admin(principal)
    with connect() as conn:
        rows = conn.execute("""SELECT credential_id, name, kind, project, environment, status, created_at,
                expires_at, expires_at<=now(), last_used_at, rotated_from, test_run_id
            FROM deployment_credentials WHERE kind='test-runner'
            ORDER BY created_at, credential_id""").fetchall()
    required_audit(actor_for(principal), "test-runner-credential.list", "platform", None, "succeeded",
                   {"scope": "platform"}, {"count": len(rows)})
    return {"credentials": [public_credential_record(row) for row in rows]}


@app.post("/platform/test-runner-credentials/{credential_id}/rotate")
def rotate_test_runner_credential(credential_id: UUID, body: DeploymentCredentialRotate,
                                  principal: Principal = Depends(current_principal)):
    require_human_platform_admin(principal)
    actor = actor_for(principal)
    with connect() as conn:
        predecessor = conn.execute("""SELECT name, status, expires_at>now()
            FROM deployment_credentials WHERE kind='test-runner' AND credential_id=%s""",
                                   (credential_id,)).fetchone()
    if predecessor is None:
        raise HTTPException(404, "Unknown test-runner credential")
    if predecessor[1] != "active" or not predecessor[2]:
        raise HTTPException(409, "Only an active test-runner credential can be rotated")
    suffix = "-r-" + uuid4().hex[:8]
    replacement_name = predecessor[0][:(64 - len(suffix))] + suffix
    provider = None
    try:
        provider = create_credential_client("Platform test runner: " + replacement_name)
        machine = Principal(verifier.issuer, provider["subject"], "Test runner " + replacement_name)
        with connect() as conn, conn.transaction():
            locked = conn.execute("""SELECT status, expires_at>now() FROM deployment_credentials
                WHERE kind='test-runner' AND credential_id=%s FOR UPDATE""", (credential_id,)).fetchone()
            if locked is None or locked[0] != "active" or not locked[1]:
                raise RuntimeError("Test-runner credential became inactive during rotation")
            grant_role(conn, machine, "platform", None, "platform-admin")
            row = conn.execute("""INSERT INTO deployment_credentials(
                    name, kind, project, issuer, subject, provider_client_id, provider_resource_id,
                    status, created_by_issuer, created_by_subject, expires_at, rotated_from)
                VALUES (%s,'test-runner',NULL,%s,%s,%s,%s,'active',%s,%s,
                        now()+make_interval(days => %s),%s)
                RETURNING credential_id, name, kind, project, environment, status, created_at,
                          expires_at, expires_at<=now(), last_used_at, rotated_from, test_run_id""",
                (replacement_name, machine.issuer, machine.subject, provider["client_id"],
                 provider["provider_resource_id"], principal.issuer, principal.subject,
                 body.expires_in_days, credential_id)).fetchone()
            old_expiry = conn.execute("""UPDATE deployment_credentials
                    SET expires_at=LEAST(expires_at, now()+make_interval(hours => %s))
                WHERE credential_id=%s RETURNING expires_at""",
                                      (body.overlap_hours, credential_id)).fetchone()[0]
        result = {**public_credential_record(row),
                  "token_endpoint": verifier.issuer + "/protocol/openid-connect/token",
                  "client_id": provider["client_id"], "client_secret": provider["client_secret"],
                  "predecessor_id": str(credential_id), "predecessor_expires_at": old_expiry.isoformat()}
    except Exception as exc:
        if provider:
            try:
                delete_credential_client(provider["provider_resource_id"])
            except Exception:
                pass
        required_audit(actor, "test-runner-credential.rotate", "automation-credential",
                       str(credential_id), "failed", {"scope": "platform"},
                       {"error_type": type(exc).__name__})
        raise HTTPException(503, "Test-runner rotation failed without returning a usable secret")
    required_audit(actor, "test-runner-credential.rotate", "automation-credential",
                   result["credential_id"], "succeeded", {"scope": "platform"},
                   {"rotated_from": str(credential_id), "overlap_hours": body.overlap_hours})
    return JSONResponse(status_code=201, content=jsonable_encoder(result))


@app.delete("/platform/test-runner-credentials/{credential_id}")
def revoke_test_runner_credential(credential_id: UUID,
                                  principal: Principal = Depends(current_principal)):
    require_human_platform_admin(principal)
    actor = actor_for(principal)
    with connect() as conn, conn.transaction():
        row = conn.execute("""SELECT provider_resource_id, issuer, subject, status
            FROM deployment_credentials WHERE kind='test-runner' AND credential_id=%s FOR UPDATE""",
                           (credential_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "Unknown test-runner credential")
        if row[3] == "revoked":
            return {"credential_id": str(credential_id), "status": "revoked"}
        revoke_role(conn, row[1], row[2], "platform", None)
        conn.execute("UPDATE deployment_credentials SET status='revocation_pending' WHERE credential_id=%s",
                     (credential_id,))
    try:
        delete_credential_client(row[0])
    except CredentialProviderError:
        required_audit(actor, "test-runner-credential.revoke", "automation-credential",
                       str(credential_id), "failed", {"scope": "platform"},
                       {"state": "revocation_pending"})
        return JSONResponse(status_code=202, content={"credential_id": str(credential_id),
                                                      "status": "revocation_pending"})
    with connect() as conn:
        conn.execute("""UPDATE deployment_credentials SET status='revoked', revoked_at=now()
            WHERE credential_id=%s""", (credential_id,))
    required_audit(actor, "test-runner-credential.revoke", "automation-credential",
                   str(credential_id), "succeeded", {"scope": "platform"}, {"status": "revoked"})
    return {"credential_id": str(credential_id), "status": "revoked"}


@app.post("/platform/test-identities")
def create_test_identity(body: TestIdentityCreate,
                         principal: Principal = Depends(current_principal)):
    """Create a short-lived service-account persona tied to one test run."""
    require_test_identity_manager(principal)
    actor = actor_for(principal)
    if body.project is not None:
        with connect() as conn:
            if not conn.execute("SELECT 1 FROM projects WHERE name=%s", (body.project,)).fetchone():
                raise HTTPException(404, "Unknown project")
    provider = None
    try:
        provider = create_credential_client(f"Test persona {body.test_run_id}: {body.name}")
        machine = Principal(verifier.issuer, provider["subject"], "Test persona " + body.name)
        with connect() as conn, conn.transaction():
            if body.role == "platform-admin":
                grant_role(conn, machine, "platform", None, body.role)
            else:
                grant_role(conn, machine, "project", body.project, body.role)
            row = conn.execute("""INSERT INTO deployment_credentials(
                    name, kind, project, issuer, subject, provider_client_id, provider_resource_id,
                    status, created_by_issuer, created_by_subject, expires_at, test_run_id)
                VALUES (%s,'test-persona',%s,%s,%s,%s,%s,'active',%s,%s,
                        now()+make_interval(hours => %s),%s)
                RETURNING credential_id, name, kind, project, environment, status, created_at,
                          expires_at, expires_at<=now(), last_used_at, rotated_from, test_run_id""",
                (body.name, body.project, machine.issuer, machine.subject, provider["client_id"],
                 provider["provider_resource_id"], principal.issuer, principal.subject,
                 body.expires_in_hours, body.test_run_id)).fetchone()
        result = {**public_credential_record(row), "role": body.role,
                  "token_endpoint": verifier.issuer + "/protocol/openid-connect/token",
                  "client_id": provider["client_id"], "client_secret": provider["client_secret"]}
    except HTTPException:
        raise
    except Exception as exc:
        if provider:
            try:
                delete_credential_client(provider["provider_resource_id"])
            except Exception:
                pass
        required_audit(actor, "test-identity.create", "test-run", body.test_run_id, "failed",
                       {"project": body.project}, {"error_type": type(exc).__name__})
        raise HTTPException(503, "Test identity creation failed without returning a usable secret")
    required_audit(actor, "test-identity.create", "automation-credential", result["credential_id"],
                   "succeeded", {"project": body.project},
                   {"role": body.role, "test_run_id": body.test_run_id, "expires_at": result["expires_at"]})
    return JSONResponse(status_code=201, content=jsonable_encoder(result))


@app.get("/platform/test-identities")
def list_test_identities(test_run_id: str | None = Query(None, max_length=64),
                         principal: Principal = Depends(current_principal)):
    require_test_identity_manager(principal)
    with connect() as conn:
        rows = conn.execute("""SELECT credential_id, name, kind, project, environment, status, created_at,
                expires_at, expires_at<=now(), last_used_at, rotated_from, test_run_id,
                (SELECT role FROM platform_grants g
                 WHERE g.issuer=deployment_credentials.issuer
                   AND g.subject=deployment_credentials.subject LIMIT 1)
            FROM deployment_credentials WHERE kind='test-persona' AND (%s IS NULL OR test_run_id=%s)
            ORDER BY created_at, credential_id""", (test_run_id, test_run_id)).fetchall()
    required_audit(actor_for(principal), "test-identity.list", "test-run", test_run_id, "succeeded",
                   {"scope": "platform"}, {"count": len(rows)})
    return {"credentials": [{**public_credential_record(row[:12]), "role": row[12]} for row in rows]}


@app.delete("/platform/test-identities/{credential_id}")
def revoke_test_identity(credential_id: UUID, principal: Principal = Depends(current_principal)):
    require_test_identity_manager(principal)
    actor = actor_for(principal)
    with connect() as conn, conn.transaction():
        row = conn.execute("""SELECT provider_resource_id, issuer, subject, status, test_run_id, project
            FROM deployment_credentials WHERE kind='test-persona' AND credential_id=%s FOR UPDATE""",
                           (credential_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "Unknown test identity")
        if row[3] == "revoked":
            return {"credential_id": str(credential_id), "status": "revoked"}
        conn.execute("DELETE FROM platform_grants WHERE issuer=%s AND subject=%s", (row[1], row[2]))
        conn.execute("UPDATE deployment_credentials SET status='revocation_pending' WHERE credential_id=%s",
                     (credential_id,))
    try:
        delete_credential_client(row[0])
    except CredentialProviderError:
        required_audit(actor, "test-identity.revoke", "automation-credential", str(credential_id),
                       "failed", {"project": row[5]},
                       {"state": "revocation_pending", "test_run_id": row[4]})
        return JSONResponse(status_code=202, content={"credential_id": str(credential_id),
                                                      "status": "revocation_pending"})
    with connect() as conn:
        conn.execute("""UPDATE deployment_credentials SET status='revoked', revoked_at=now()
            WHERE credential_id=%s""", (credential_id,))
    required_audit(actor, "test-identity.revoke", "automation-credential", str(credential_id),
                   "succeeded", {"project": row[5]}, {"test_run_id": row[4]})
    return {"credential_id": str(credential_id), "status": "revoked"}


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
def provision(name: str, body: Union[ApplicationEnvelopeV1Alpha2, ApplicationEnvelope, Project],
              principal: Principal = Depends(current_principal),
              if_match: Optional[str] = Header(None)):
    """Accept the flat project body or a versioned `Application` envelope.

    An optional `If-Match: <revision>` header makes the update conditional on the
    current desired revision; a stale value returns 409 with the current revision.
    """
    if isinstance(body, (ApplicationEnvelope, ApplicationEnvelopeV1Alpha2)):
        try:
            project = Project.model_validate(to_flat(body.model_dump(exclude_none=True)),
                                            context={"versioned_envelope": True})
        except ValidationError as exc:
            raise RequestValidationError(exc.errors(include_context=False))
    else:
        project = body
    actor = actor_for(principal)
    require_permission(principal, "deploy", name)
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
        if project.components is not None:
            resolved_components = []
            for component in project.components:
                resolved_components.append({**component, "resolved_image": resolve_image(component["image"])})
        else:
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
    spec = project.model_dump(exclude_none=True)
    if project.components is not None:
        spec["components"] = resolved_components
    else:
        spec["resolved_image"] = resolved_image
    # Configuration is managed by its dedicated, revisioned endpoint. A deployment
    # envelope that omits it must not erase those separately managed values while
    # migrating a legacy application or updating one component.
    if "configuration" not in spec:
        current = current_spec(name)
        if current and current[1] and current[1].get("configuration"):
            spec["configuration"] = current[1]["configuration"]
    capacity = assess_capacity(runtime, spec, log)
    if capacity["state"] == "unavailable":
        raise HTTPException(503, "Capacity admission is unavailable; retry without assuming free capacity")
    if capacity["state"] == "rejected":
        required_audit(actor, "project.provision", "project", name, "rejected", {"project": name},
                       {"reason": "insufficient_reserved_capacity"})
        raise HTTPException(422, "Requested rollout exceeds remaining reserved cluster capacity")
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
    current = current_spec(name)
    if current is None:
        required_audit(actor, "project.drift.inspect", "project", name, "rejected", {"project": name},
                       {"reason": "not_found"})
        raise HTTPException(404, "Unknown project")
    if current[0] is None:
        raise HTTPException(409, "Project has not been deployed")
    result = observe_drift(runtime, name, current[1], log)
    detail = {"revision": current[0], "state": result["state"],
              "fields": [d["field"] for d in result["differences"]]}
    required_audit(actor, "project.drift.detected" if result["state"] == "drifted" else "project.drift.inspect",
                   "project", name, "succeeded", {"project": name}, detail)
    return {"project": name, "revision": current[0], **result}


@app.get("/projects/{name}/components")
def component_status(name: str, principal: Principal = Depends(current_principal)):
    """Live, per-component status for a v1alpha2 application revision."""
    require_permission(principal, "view", name)
    actor = actor_for(principal)
    current = current_spec(name)
    if current is None:
        required_audit(actor, "project.components.read", "project", name, "rejected",
                       {"project": name}, {"reason": "not_found"})
        raise HTTPException(404, "Unknown project")
    if current[0] is None:
        raise HTTPException(409, "Project has not been deployed")
    components = current[1].get("components")
    if components is None:
        raise HTTPException(409, "Component status requires a v1alpha2 application revision")
    result = observe_components(runtime, name, components, log)
    required_audit(actor, "project.components.read", "project", name, "succeeded",
                   {"project": name}, {"revision": current[0], "count": len(components)})
    return {"project": name, "revision": current[0], **result}


class ConfigurationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    values: dict


def current_spec(name: str):
    with connect() as conn:
        return conn.execute("""SELECT max(r.revision), (array_agg(r.spec ORDER BY r.revision DESC))[1], p.status
            FROM projects p
            LEFT JOIN project_environments e ON e.project_id=p.project_id
            LEFT JOIN project_applications a ON a.environment_id=e.environment_id
            LEFT JOIN application_revisions r ON r.application_id=a.application_id
            WHERE p.name=%s GROUP BY p.status""", (name,)).fetchone()


@app.get("/projects/{name}/configuration")
def get_configuration(name: str, principal: Principal = Depends(current_principal)):
    """Desired configuration values and whether the running deployment has activated them."""
    require_permission(principal, "view", name)
    actor = actor_for(principal)
    current = current_spec(name)
    if current is None:
        required_audit(actor, "project.configuration.read", "project", name, "rejected",
                       {"project": name}, {"reason": "not_found"})
        raise HTTPException(404, "Unknown project")
    if current[0] is None:
        raise HTTPException(409, "Project has not been deployed")
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
    if current is None:
        required_audit(actor, "project.configuration.update", "project", name, "rejected",
                       {"project": name}, {"reason": "not_found"})
        raise HTTPException(404, "Unknown project")
    if current[0] is None:
        raise HTTPException(409, "Project has not been deployed")
    try:
        stored = read_secret(runtime, name)
    except SecretsUnavailable:
        stored = None
    clash = sorted(set(values) & {s["name"] for s in (stored or {}).get("secrets", [])})
    if clash:
        required_audit(actor, "project.configuration.update", "project", name, "rejected",
                       {"project": name}, {"reason": "name_in_use", "names": clash})
        return JSONResponse(status_code=409, content={
            "detail": "These names are already secrets: " + ", ".join(clash), "code": "name_in_use"})
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


def secrets_project(name: str, principal: Principal, permission: str, action: str):
    """Authorize and require an active project for the secret endpoints."""
    require_permission(principal, permission, name)
    actor = actor_for(principal)
    current = current_spec(name)
    if current is None:
        required_audit(actor, action, "project", name, "rejected", {"project": name}, {"reason": "not_found"})
        raise HTTPException(404, "Unknown project")
    if current[0] is None:
        raise HTTPException(409, "Project has not been deployed")
    if current[2] == "retired":
        required_audit(actor, action, "project", name, "rejected", {"project": name}, {"reason": "retired"})
        raise HTTPException(409, "Project is retired")
    return actor, current


def secrets_unavailable(actor, action: str, name: str):
    required_audit(actor, action, "project", name, "failed", {"project": name}, {"error_type": "SecretsUnavailable"})
    raise HTTPException(503, "Secrets are unavailable; retry the same request.")


@app.get("/projects/{name}/secrets")
def list_secrets(name: str, principal: Principal = Depends(current_principal)):
    """Secret names and change times, never values, plus whether the pods run the current version."""
    actor, _ = secrets_project(name, principal, "view", "project.secret.list")
    try:
        stored = read_secret(runtime, name)
    except SecretsUnavailable:
        secrets_unavailable(actor, "project.secret.list", name)
    names = [s["name"] for s in (stored or {}).get("secrets", [])]
    activation = observe_secret_activation(runtime, name, (stored or {}).get("version"))
    required_audit(actor, "project.secret.list", "project", name, "succeeded", {"project": name},
                   {"count": len(names)})
    return {"project": name, "secrets": (stored or {}).get("secrets", []), "activation": activation}


@app.put("/projects/{name}/secrets/{secret}")
def set_secret(name: str, secret: str, body: dict = Body(...),
               principal: Principal = Depends(current_principal)):
    """Create or rotate one write-only secret; the pods restart to pick it up."""
    actor, current = secrets_project(name, principal, "change", "project.secret.set")
    detail = {"name": secret}
    try:
        validate_secret_name(secret)
        if set(body) != {"value"}:
            raise ValueError('body must be {"value": "..."}')
        validate_secret_value(body["value"])
    except ValueError as exc:
        required_audit(actor, "project.secret.set", "project", name, "rejected", {"project": name},
                       {"reason": "invalid_secret", **detail})
        return JSONResponse(status_code=422, content={"detail": str(exc), "code": "invalid_secret"})
    if secret in (current[1].get("configuration") or {}):
        required_audit(actor, "project.secret.set", "project", name, "rejected", {"project": name},
                       {"reason": "name_in_use", **detail})
        return JSONResponse(status_code=409, content={
            "detail": f"{secret} is already a configuration value", "code": "name_in_use"})
    try:
        stored = read_secret(runtime, name)
        existing = {s["name"] for s in (stored or {}).get("secrets", [])}
        if secret not in existing and len(existing) >= MAX_SECRETS:
            required_audit(actor, "project.secret.set", "project", name, "rejected", {"project": name},
                           {"reason": "too_many_secrets", **detail})
            return JSONResponse(status_code=422, content={
                "detail": f"at most {MAX_SECRETS} secrets", "code": "invalid_secret"})
        version = write_secret(runtime, name, secret, body["value"])
        rolled = roll_pods(runtime, name, version)
    except SecretsUnavailable:
        secrets_unavailable(actor, "project.secret.set", name)
    required_audit(actor, "project.secret.set", "project", name, "succeeded", {"project": name},
                   {"rotated": secret in existing, "rollout_started": rolled, **detail})
    return JSONResponse(status_code=202, content={
        "name": secret, "rotated": secret in existing, "rollout_required": True, "rollout_started": rolled})


@app.delete("/projects/{name}/secrets/{secret}")
def delete_secret(name: str, secret: str, principal: Principal = Depends(current_principal)):
    """Remove one secret; the pods restart so the variable disappears."""
    actor, _ = secrets_project(name, principal, "change", "project.secret.delete")
    try:
        validate_secret_name(secret)
        stored = read_secret(runtime, name)
        if secret not in {s["name"] for s in (stored or {}).get("secrets", [])}:
            required_audit(actor, "project.secret.delete", "project", name, "rejected", {"project": name},
                           {"reason": "not_found", "name": secret})
            raise HTTPException(404, "Unknown secret")
        version = remove_secret(runtime, name, secret)
        rolled = roll_pods(runtime, name, version)
    except ValueError:
        raise HTTPException(404, "Unknown secret")
    except SecretsUnavailable:
        secrets_unavailable(actor, "project.secret.delete", name)
    required_audit(actor, "project.secret.delete", "project", name, "succeeded", {"project": name},
                   {"name": secret, "rollout_started": rolled})
    return JSONResponse(status_code=202, content={
        "name": secret, "rollout_required": True, "rollout_started": rolled})


@app.post("/projects/{name}/secrets/{secret}/confirm")
def confirm_secret_rotation(name: str, secret: str, principal: Principal = Depends(current_principal)):
    """Revoke the previous value once the pods run the new one."""
    actor, _ = secrets_project(name, principal, "change", "project.secret.confirm")
    try:
        validate_secret_name(secret)
        stored = read_secret(runtime, name)
        entry = next((s for s in (stored or {}).get("secrets", []) if s["name"] == secret), None)
        if entry is None:
            raise HTTPException(404, "Unknown secret")
        if entry["state"] != "rotating":
            required_audit(actor, "project.secret.confirm", "project", name, "rejected", {"project": name},
                           {"reason": "no_previous_version", "name": secret})
            return JSONResponse(status_code=409, content={
                "detail": "No previous version is held", "code": "no_previous_version"})
        activation = observe_secret_activation(runtime, name, stored["version"])
        if activation["state"] != "active":
            required_audit(actor, "project.secret.confirm", "project", name, "rejected", {"project": name},
                           {"reason": "not_adopted", "name": secret})
            return JSONResponse(status_code=409, content={
                "detail": "The pods do not run the new version yet", "code": "not_adopted",
                "activation": activation})
        confirm_secret(runtime, name, secret)
    except ValueError:
        raise HTTPException(404, "Unknown secret")
    except SecretsUnavailable:
        secrets_unavailable(actor, "project.secret.confirm", name)
    required_audit(actor, "project.secret.confirm", "project", name, "succeeded", {"project": name},
                   {"name": secret, "version": entry["version"]})
    return {"name": secret, "version": entry["version"], "state": "active"}


@app.post("/projects/{name}/secrets/{secret}/revert")
def revert_secret_rotation(name: str, secret: str, principal: Principal = Depends(current_principal)):
    """Make the previous value current again and restart the pods."""
    actor, _ = secrets_project(name, principal, "change", "project.secret.revert")
    try:
        validate_secret_name(secret)
        version = revert_secret(runtime, name, secret)
        if version is None:
            required_audit(actor, "project.secret.revert", "project", name, "rejected", {"project": name},
                           {"reason": "no_previous_version", "name": secret})
            return JSONResponse(status_code=409, content={
                "detail": "No previous version is held", "code": "no_previous_version"})
        rolled = roll_pods(runtime, name, version)
    except ValueError:
        raise HTTPException(404, "Unknown secret")
    except SecretsUnavailable:
        secrets_unavailable(actor, "project.secret.revert", name)
    required_audit(actor, "project.secret.revert", "project", name, "succeeded", {"project": name},
                   {"name": secret, "rollout_started": rolled})
    return JSONResponse(status_code=202, content={
        "name": secret, "rollout_required": True, "rollout_started": rolled})


class Rollback(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(gt=0)


@app.get("/projects/{name}/revisions")
def revisions(name: str, principal: Principal = Depends(current_principal)):
    """List the retained desired revisions, newest first."""
    require_permission(principal, "view", name)
    actor = actor_for(principal)
    with connect() as conn:
        project = conn.execute("SELECT status FROM projects WHERE name=%s", (name,)).fetchone()
        rows = conn.execute("""SELECT r.revision, r.created_at, r.spec
            FROM projects p
            JOIN project_environments e ON e.project_id=p.project_id
            JOIN project_applications a ON a.environment_id=e.environment_id
            JOIN application_revisions r ON r.application_id=a.application_id
            WHERE p.name=%s ORDER BY r.revision DESC""", (name,)).fetchall()
    if project is None:
        required_audit(actor, "project.revisions.list", "project", name, "rejected",
                       {"project": name}, {"reason": "not_found"})
        raise HTTPException(404, "Unknown project")
    if not rows:
        required_audit(actor, "project.revisions.list", "project", name, "succeeded",
                       {"project": name}, {"count": 0})
        return {"project": name, "current_revision": None, "revisions": []}
    required_audit(actor, "project.revisions.list", "project", name, "succeeded",
                   {"project": name}, {"count": len(rows)})
    return {"project": name, "current_revision": rows[0][0], "revisions": [
        {"revision": r[0], "created_at": r[1].isoformat(), "current": r[0] == rows[0][0],
         "image": r[2].get("resolved_image", r[2].get("image")), "port": r[2].get("port"),
         "dependencies": dependency_report(r[2]),
         "components": [{"name": c["name"], "type": c["type"], "image": c.get("resolved_image", c["image"]),
                         **({"legacy": True} if c.get("legacy") else {})} for c in component_view(r[2])],
         "resources": r[2].get("resources")}
        for r in rows]}


@app.get("/projects/{name}/resource-usage")
def resource_usage(name: str, principal: Principal = Depends(current_principal)):
    """Current CPU and memory per pod; missing, stale and unavailable metrics are labelled in `state`."""
    require_permission(principal, "view", name)
    actor = actor_for(principal)
    with connect() as conn:
        known = conn.execute("SELECT status FROM projects WHERE name=%s", (name,)).fetchone()
    if not known:
        required_audit(actor, "project.usage.inspect", "project", name, "rejected",
                       {"project": name}, {"reason": "not_found"})
        raise HTTPException(404, "Unknown project")
    if known[0] == "empty":
        raise HTTPException(409, "Project has not been deployed")
    usage = observe_usage(runtime, name, log)
    required_audit(actor, "project.usage.inspect", "project", name, "succeeded",
                   {"project": name}, {"state": usage["state"]})
    return {"project": name, **usage}


@app.get("/projects/{name}/resources")
def resource_inventory(name: str, principal: Principal = Depends(current_principal)):
    """Authorized deployed-resource inventory; unavailable provider data is explicit."""
    require_permission(principal, "view", name)
    actor = actor_for(principal)
    with connect() as conn:
        known = conn.execute("SELECT status FROM projects WHERE name=%s", (name,)).fetchone()
    if not known:
        raise HTTPException(404, "Unknown project")
    if known[0] == "empty":
        raise HTTPException(409, "Project has not been deployed")
    inventory = observe_inventory(runtime, name, log)
    inventory["usage"] = observe_usage(runtime, name, log)
    required_audit(actor, "project.resources.inspect", "project", name, "succeeded",
                   {"project": name}, {"state": inventory["state"], "usage_state": inventory["usage"]["state"]})
    return {"project": name, **inventory}


def _recovery_record(row):
    if row is None:
        return None
    return {"request_id": str(row[0]), "reason": row[1], "status": row[2], "requested_at": row[3].isoformat(),
            "reviewed_at": row[4].isoformat() if row[4] else None}


@app.get("/projects/{name}/data-services")
def data_services(name: str, principal: Principal = Depends(current_principal)):
    """Report managed-database availability and the latest recovery outcome."""
    require_permission(principal, "view", name)
    database = "project_" + name.replace("-", "_")
    try:
        with connect() as conn:
            if not conn.execute("SELECT 1 FROM projects WHERE name=%s", (name,)).fetchone():
                raise HTTPException(404, "Unknown project")
            available = bool(conn.execute("SELECT 1 FROM pg_database WHERE datname=%s", (database,)).fetchone())
            request = conn.execute("""SELECT request_id, reason, status, requested_at, reviewed_at
                FROM data_service_recovery_requests WHERE project=%s ORDER BY requested_at DESC LIMIT 1""",
                                   (name,)).fetchone()
    except HTTPException:
        raise
    except Exception as exc:
        log.error("Data-service observation failed project=%s error_type=%s", name, type(exc).__name__)
        available, request = None, None
    state = "available" if available else "unavailable"
    required_audit(actor_for(principal), "data-service.inspect", "project", name, "succeeded", {"project": name},
                   {"state": state})
    return {"project": name, "services": [{"type": "postgresql", "name": "managed", "state": state,
                                              "reason": None if available else "DatabaseUnavailable"}],
            "latest_recovery_request": _recovery_record(request)}


@app.post("/projects/{name}/data-services/recovery-requests", status_code=201)
def request_data_service_recovery(name: str, body: DataServiceRecoveryRequest,
                                  principal: Principal = Depends(current_principal)):
    """Create a bounded operator-reviewable recovery request without incident details or credentials."""
    require_permission(principal, "change", name)
    request_id = uuid4()
    with connect() as conn:
        if not conn.execute("SELECT 1 FROM projects WHERE name=%s", (name,)).fetchone():
            raise HTTPException(404, "Unknown project")
        row = conn.execute("""INSERT INTO data_service_recovery_requests
            (request_id, project, reason, status, requested_by) VALUES (%s, %s, %s, 'requested', %s)
            RETURNING request_id, reason, status, requested_at, reviewed_at""",
                           (request_id, name, body.reason, actor_for(principal).identifier)).fetchone()
    required_audit(actor_for(principal), "data-service.recovery.request", "project", name, "succeeded",
                   {"project": name}, {"request_id": str(request_id), "reason": body.reason})
    return {"project": name, **_recovery_record(row)}


@app.get("/operator/data-service-recovery-requests")
def list_data_service_recovery_requests(principal: Principal = Depends(current_principal)):
    require_platform_admin(principal)
    with connect() as conn:
        rows = conn.execute("""SELECT request_id, project, reason, status, requested_at, reviewed_at
            FROM data_service_recovery_requests ORDER BY requested_at DESC LIMIT 100""").fetchall()
    required_audit(actor_for(principal), "data-service.recovery.list", "platform", "recovery-requests", "succeeded",
                   {"scope": "platform"}, {"count": len(rows)})
    return {"requests": [{"project": row[1], **_recovery_record((row[0], row[2], row[3], row[4], row[5]))}
                         for row in rows]}


@app.patch("/operator/data-service-recovery-requests/{request_id}")
def review_data_service_recovery_request(request_id: UUID, body: DataServiceRecoveryReview,
                                         principal: Principal = Depends(current_principal)):
    require_platform_admin(principal)
    with connect() as conn:
        row = conn.execute("""UPDATE data_service_recovery_requests
            SET status=%s, reviewed_at=now(), reviewed_by=%s WHERE request_id=%s
            RETURNING project, request_id, reason, status, requested_at, reviewed_at""",
                           (body.status, actor_for(principal).identifier, request_id)).fetchone()
    if row is None:
        raise HTTPException(404, "Unknown recovery request")
    required_audit(actor_for(principal), "data-service.recovery.review", "project", row[0], "succeeded",
                   {"project": row[0]}, {"request_id": str(request_id), "status": body.status})
    return {"project": row[0], **_recovery_record(row[1:])}


@app.get("/operator/capacity")
def operator_capacity(principal: Principal = Depends(current_principal)):
    require_platform_admin(principal)
    result = observe_cluster_capacity(runtime, log)
    admission = capacity_admission_snapshot(runtime, log)
    required_audit(actor_for(principal), "capacity.inspect", "platform", "capacity", "succeeded", {},
                   {"state": result["state"], "admission_state": admission["state"]})
    return {**result, "admission": admission}


@app.get("/projects/{name}/logs")
def project_logs(name: str, tail: int = Query(200, ge=1, le=1000),
                 since_seconds: Optional[int] = Query(None, ge=1, le=86400),
                 component: Optional[str] = Query(None, pattern=r"^[a-z][a-z0-9-]{0,31}$"),
                 instance: Optional[str] = Query(None, pattern=r"^[a-z0-9]([-a-z0-9.]{0,251}[a-z0-9])?$"),
                 search: Optional[str] = Query(None, min_length=1, max_length=256),
                 after: Optional[str] = Query(None, max_length=64),
                 before: Optional[str] = Query(None, max_length=64),
                 principal: Principal = Depends(current_principal)):
    """Authorized log snapshot; repeat with `after=next_cursor` to follow new entries."""
    # FastAPI resolves Query defaults for HTTP requests. Keep direct handler tests and
    # other in-process callers from leaking those sentinel objects into audit/results.
    instance = instance if isinstance(instance, str) else None
    search = search if isinstance(search, str) else None
    after = after if isinstance(after, str) else None
    before = before if isinstance(before, str) else None
    require_permission(principal, "view", name)
    actor = actor_for(principal)
    with connect() as conn:
        known = conn.execute("SELECT status FROM projects WHERE name=%s", (name,)).fetchone()
    if not known:
        required_audit(actor, "project.logs.read", "project", name, "rejected",
                       {"project": name}, {"reason": "not_found"})
        raise HTTPException(404, "Unknown project")
    if known[0] == "empty":
        raise HTTPException(409, "Project has not been deployed")
    if component is not None:
        current = current_spec(name)
        available = {item["name"] for item in ((current[1] or {}).get("components") if current else [])}
        if component not in available:
            required_audit(actor, "project.logs.read", "project", name, "rejected",
                           {"project": name}, {"reason": "unknown_component", "component": component})
            raise HTTPException(404, "Unknown component")
        result = observe_logs(runtime, name, log, tail, since_seconds, component=component,
                              instance=instance, search=search, after=after, before=before)
    else:
        result = observe_logs(runtime, name, log, tail, since_seconds, instance=instance,
                              search=search, after=after, before=before)
    required_audit(actor, "project.logs.read", "project", name, "succeeded",
                   {"project": name}, {"state": result["state"], "lines": len(result["lines"]),
                    "component": component, "instance": instance, "search": bool(search)})
    return {"project": name, **result}


@app.post("/projects/{name}/rollback")
def rollback(name: str, body: Rollback, principal: Principal = Depends(current_principal),
             if_match: Optional[str] = Header(None)):
    """Re-apply a retained revision as a new revision; databases are never rolled back."""
    actor = actor_for(principal)
    require_permission(principal, "change", name)
    current = current_spec(name)
    if current is None:
        raise HTTPException(404, "Unknown project")
    if current[0] is None:
        raise HTTPException(409, "Project has not been deployed")
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
    current_specification = current_spec(name)
    if current_specification is None:
        raise HTTPException(404, "Unknown project")
    if current_specification[0] is None:
        raise HTTPException(409, "Project has not been deployed")
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
    components = row[7].get("components")
    if components:
        services = [component for component in components if component["type"] == "service"]
        readiness = {"state": "not_applicable"} if not services else observe_deployment(
            runtime, row[6], services[0].get("resolved_image", services[0]["image"]), log, services[0]["name"])
    else:
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


class ProjectPurge(BaseModel):
    """Explicit confirmation required to permanently purge a retired project."""
    model_config = ConfigDict(extra="forbid")
    confirm_name: str = Field(min_length=1, max_length=63)
    scope_token: str = Field(min_length=32, max_length=128)


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
        project = conn.execute("SELECT status FROM projects WHERE name=%s", (name,)).fetchone()
        if project is None:
            return None
        return {"project": name, "revision": 0, "removes": [], "route": None, "routes": [],
                "retains": {"database": None, "role": None, "catalog_and_revisions": True},
                "scope_token": retirement_scope_token(name, 0)}
    return removal_scope(name, row[0], row[1], os.environ["APPS_DOMAIN"])


def retirement_access_inventory(conn, name):
    grants = conn.execute("SELECT role, count(*) FROM platform_grants WHERE scope_kind='project' AND scope_id=%s GROUP BY role", (name,)).fetchall()
    credentials = conn.execute("SELECT status, count(*) FROM deployment_credentials WHERE project=%s GROUP BY status", (name,)).fetchall()
    return {"grants_by_role": {role: count for role, count in grants},
            "credentials_by_status": {state: count for state, count in credentials}}


def project_database_name(name: str) -> str:
    """Return the deterministic, validated database and role name for a project."""
    validate_name(name)
    return "project_" + name.replace("-", "_")


def current_purge_scope(conn, name: str):
    """Return the destructive scope only for a retired project.

    Older retired projects may predate retirement-inventory records, so their
    durable project status is authoritative and ``updated_at`` anchors the token.
    """
    row = conn.execute("""SELECT p.project_id::text, COALESCE(r.retired_at, p.updated_at)
        FROM projects p LEFT JOIN project_retirements r ON r.project_id=p.project_id
        WHERE p.name=%s AND p.status='retired'""", (name,)).fetchone()
    if row is None:
        return None
    credential_rows = conn.execute("""SELECT status, count(*) FROM deployment_credentials
        WHERE project=%s GROUP BY status""", (name,)).fetchall()
    credential_states = {status: count for status, count in credential_rows}
    database = project_database_name(name)
    return {
        "project": name,
        "database": database,
        "role": database,
        "catalog": ["project", "environments", "applications", "revisions", "operations", "retirement inventory"],
        "audit_records_retained": True,
        "credential_cleanup": credential_states,
        "scope_token": purge_scope_token(name, row[0], row[1].isoformat(), credential_states),
    }


def drop_project_database_and_role(conn, name: str) -> None:
    """Drop only the deterministic SQL resources after a verified purge confirmation."""
    database = project_database_name(name)
    conn.execute("""SELECT pg_terminate_backend(pid) FROM pg_stat_activity
        WHERE datname=%s AND pid <> pg_backend_pid()""", (database,))
    conn.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(database)))
    conn.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(database)))


def delete_project_catalog(conn, name: str) -> None:
    """Delete the complete project-owned catalog in foreign-key order."""
    conn.execute("DELETE FROM data_service_recovery_requests WHERE project=%s", (name,))
    conn.execute("DELETE FROM deployment_credentials WHERE project=%s", (name,))
    conn.execute("DELETE FROM platform_grants WHERE scope_kind='project' AND scope_id=%s", (name,))
    conn.execute("""DELETE FROM application_operations WHERE application_id IN (
        SELECT a.application_id FROM project_applications a
        JOIN project_environments e ON e.environment_id=a.environment_id
        JOIN projects p ON p.project_id=e.project_id WHERE p.name=%s)""", (name,))
    conn.execute("""DELETE FROM application_revisions WHERE application_id IN (
        SELECT a.application_id FROM project_applications a
        JOIN project_environments e ON e.environment_id=a.environment_id
        JOIN projects p ON p.project_id=e.project_id WHERE p.name=%s)""", (name,))
    conn.execute("""DELETE FROM project_applications WHERE environment_id IN (
        SELECT e.environment_id FROM project_environments e
        JOIN projects p ON p.project_id=e.project_id WHERE p.name=%s)""", (name,))
    conn.execute("""DELETE FROM project_environments WHERE project_id IN (
        SELECT project_id FROM projects WHERE name=%s)""", (name,))
    conn.execute("""DELETE FROM project_retirements WHERE project_id IN (
        SELECT project_id FROM projects WHERE name=%s)""", (name,))
    conn.execute("DELETE FROM projects WHERE name=%s", (name,))


@app.get("/operator/projects/{name}/retirement")
def inspect_retirement(name: str, principal: Principal = Depends(current_principal)):
    """Inspect retained retirement inventory and fail-closed credential cleanup progress."""
    require_platform_admin(principal)
    with connect() as conn:
        row = conn.execute("""SELECT p.status, r.retired_at, r.inventory FROM projects p
            LEFT JOIN project_retirements r ON r.project_id=p.project_id WHERE p.name=%s""", (name,)).fetchone()
        if row is None:
            raise HTTPException(404, "Unknown project")
        access = retirement_access_inventory(conn, name)
    required_audit(actor_for(principal), "project.retirement.inspect", "project", name, "succeeded",
                   {"scope": "platform"}, {"status": row[0]})
    return {"project": name, "status": row[0], "retired_at": row[1].isoformat() if row[1] else None,
            "retained": row[2], "credential_cleanup": access["credentials_by_status"]}


@app.get("/operator/projects/{name}/purge-preview")
def purge_preview(name: str, principal: Principal = Depends(current_principal)):
    """Show permanent-deletion scope for a retired project to a platform administrator."""
    require_platform_admin(principal)
    try:
        validate_name(name)
    except ValueError:
        raise HTTPException(400, "Invalid project name")
    with connect() as conn:
        scope = current_purge_scope(conn, name)
    if scope is None:
        raise HTTPException(409, "Only a retired project can be permanently purged")
    required_audit(actor_for(principal), "project.purge.preview", "project", name, "succeeded",
                   {"scope": "platform", "project": name}, {"credential_cleanup": scope["credential_cleanup"]})
    return scope


@app.post("/operator/projects/{name}/purge")
def purge_project(name: str, confirmation: ProjectPurge, principal: Principal = Depends(current_principal)):
    """Permanently remove a retired project's SQL resources and catalog, retaining audit evidence."""
    require_platform_admin(principal)
    actor = actor_for(principal)
    if confirmation.confirm_name != name:
        required_audit(actor, "project.purge", "project", name, "rejected",
                       {"scope": "platform", "project": name}, {"reason": "confirmation_mismatch"})
        raise HTTPException(400, "Confirmation must match the project name")
    try:
        validate_name(name)
    except ValueError:
        raise HTTPException(400, "Invalid project name")
    with connect() as conn:
        conn.execute("SELECT pg_advisory_lock(731904)")
        try:
            scope = current_purge_scope(conn, name)
            if scope is None:
                raise HTTPException(409, "Only a retired project can be permanently purged")
            if not hmac.compare_digest(confirmation.scope_token, scope["scope_token"]):
                required_audit(actor, "project.purge", "project", name, "rejected",
                               {"scope": "platform", "project": name}, {"reason": "scope_changed"})
                return JSONResponse(status_code=409, content={
                    "detail": "The retained project state changed; request a new purge preview",
                    "code": "scope_changed"})
            pending = sum(count for status, count in scope["credential_cleanup"].items() if status != "revoked")
            if pending:
                raise HTTPException(409, "Wait for all deployment credentials to be revoked before purging")
            required_audit(actor, "project.purge.requested", "project", name, "succeeded",
                           {"scope": "platform", "project": name}, {"audit_records_retained": True})
            drop_project_database_and_role(conn, name)
            with conn.transaction():
                delete_project_catalog(conn, name)
            publish_catalog(conn)
        except HTTPException as exc:
            required_audit(actor, "project.purge", "project", name, "rejected",
                           {"scope": "platform", "project": name}, {"status_code": exc.status_code})
            raise
        except Exception as exc:
            required_audit(actor, "project.purge", "project", name, "failed",
                           {"scope": "platform", "project": name}, {"error_type": type(exc).__name__})
            log.error("Permanent project purge failed project=%s error_type=%s", name, type(exc).__name__)
            raise HTTPException(503, "Purge did not complete; verify state before retrying")
        finally:
            conn.execute("SELECT pg_advisory_unlock(731904)")
    required_audit(actor, "project.purge", "project", name, "succeeded",
                   {"scope": "platform", "project": name}, {"audit_records_retained": True})
    return {"name": name, "status": "purged", "audit_records_retained": True}


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
        access = retirement_access_inventory(conn, name) if status else {"grants_by_role": {}, "credentials_by_status": {}}
    if scope is None:
        required_audit(actor, "project.retire.preview", "project", name, "rejected",
                       {"project": name}, {"reason": "not_found"})
        raise HTTPException(404, "Unknown project")
    blockers = (["active_operation"] if active else []) + (["already_retired"] if status[0] == "retired" else [])
    required_audit(actor, "project.retire.preview", "project", name, "succeeded",
                   {"project": name}, {"revision": scope["revision"], "blockers": blockers})
    scope["access"] = access
    scope["scope_token"] = retirement_scope_token(name, scope["revision"], access)
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
                if scope is not None:
                    access = retirement_access_inventory(conn, name)
                    scope["scope_token"] = retirement_scope_token(name, scope["revision"], access)
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
                        # Retiring a project ends access immediately. Provider-client deletion is retried by the
                        # existing fail-closed credential cleanup worker; credentials are never silently retained active.
                        conn.execute("DELETE FROM platform_grants WHERE scope_kind='project' AND scope_id=%s", (name,))
                        conn.execute("""UPDATE deployment_credentials SET status='revocation_pending'
                            WHERE project=%s AND status NOT IN ('revoked', 'revocation_pending')""", (name,))
                        if scope is not None:
                            conn.execute("""INSERT INTO project_retirements(project_id, inventory)
                                SELECT project_id, %s FROM projects WHERE name=%s
                                ON CONFLICT(project_id) DO UPDATE
                                SET inventory=excluded.inventory, retired_at=now()""",
                                         (Jsonb({"revision": scope["revision"], **scope["retains"]}), name))
                    publish_catalog(conn)
                    required_audit(actor, "project.retire.access_revoked", "project", name, "succeeded",
                                   {"project": name}, {"credential_cleanup": "pending"})
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


@app.get("/projects/{name}/grants")
def get_project_grants(name: str, principal: Principal = Depends(current_principal)):
    """List grants for a project administrator; operator inspection remains separate."""
    require_permission(principal, "grant", name)
    with connect() as conn:
        if not conn.execute("SELECT 1 FROM projects WHERE name=%s", (name,)).fetchone():
            raise HTTPException(404, "Unknown project")
        rows = grants_for_project(conn, name)
    return {"project": name, "grants": [
        {"issuer": issuer, "subject": subject, "display_name": display_name, "role": role,
         "granted_at": granted_at.isoformat()} for issuer, subject, display_name, role, granted_at in rows
    ]}


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


@app.get("/platform/grants")
def get_platform_grants(principal: Principal = Depends(current_principal)):
    """List platform administrators for platform-administration UI and automation."""
    require_platform_admin(principal)
    with connect() as conn:
        rows = grants_for_platform(conn)
    return {"grants": [
        {"issuer": issuer, "subject": subject, "display_name": display_name, "role": role,
         "granted_at": granted_at.isoformat()} for issuer, subject, display_name, role, granted_at in rows
    ]}


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
    """Authorize only the exact public hostname generated from an applied spec."""
    suffix = "." + os.environ["APPS_DOMAIN"]
    if not domain.endswith(suffix):
        raise HTTPException(403)
    host = domain[:-len(suffix)]
    with connect() as conn:
        projects = conn.execute("SELECT name, spec FROM projects WHERE status='applied'").fetchall()
    for name, spec in projects:
        components = (spec or {}).get("components")
        if components is None:
            # The legacy shape has exactly one public route at <project>.<domain>.
            if host == name:
                return {"allowed": True}
            continue
        for component in components:
            if (component.get("type") == "service" and component.get("exposure") == "public"
                    and host == f"{component.get('name')}-{name}"):
                return {"allowed": True}
    raise HTTPException(403)
