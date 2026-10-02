"""Trusted administrator API. Not a public multi-tenant control plane."""
import hashlib
import hmac
import logging
import os
import threading
from typing import Literal
from contextlib import asynccontextmanager

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from kubernetes import config, dynamic
from kubernetes.client import ApiClient
from kubernetes.client.exceptions import ApiException
from pydantic import BaseModel, Field, field_validator

from .audit import Actor, initialize as initialize_audit, record_event
from .manifests import resources, validate_name
from .monitoring import discovery_loop, publish_catalog

log = logging.getLogger(__name__)
auth = HTTPBearer(auto_error=False)
runtime = None

def connect():
    return psycopg.connect(host=os.environ["POSTGRES_HOST"], dbname="platform",
        user="postgres", password=os.environ["POSTGRES_PASSWORD"],
        connect_timeout=5, autocommit=True)

@asynccontextmanager
async def lifespan(app):
    global runtime
    for key in ("PLATFORM_TOKEN", "DATABASE_KEY", "PLATFORM_AUDIT_PASSWORD"):
        if len(os.environ.get(key, "")) < 32:
            raise RuntimeError(key + " must contain at least 32 characters")
    with connect() as conn:
        conn.execute("REVOKE ALL ON DATABASE platform FROM PUBLIC")
        conn.execute("""CREATE TABLE IF NOT EXISTS projects (
            name TEXT PRIMARY KEY, spec JSONB NOT NULL, status TEXT NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now())""")
        initialize_audit(conn)
    config.load_kube_config()
    runtime = dynamic.DynamicClient(ApiClient())
    stop = threading.Event()
    worker = threading.Thread(target=discovery_loop, args=(stop, connect, log), daemon=True)
    worker.start()
    try:
        yield
    finally:
        stop.set()
        worker.join(timeout=6)

app = FastAPI(title="Docker-based Developer Platform Lab", lifespan=lifespan)

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


def admin(request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(auth)) -> Actor:
    if not credentials or not hmac.compare_digest(credentials.credentials, os.environ["PLATFORM_TOKEN"]):
        best_effort_audit(Actor("anonymous", None), "authentication", "platform-api", None, "denied",
                          detail={"reason": "invalid_or_missing_bearer"})
        raise HTTPException(401, "Invalid administrator token")
    actor = Actor("legacy-shared-token", "platform-admin-token")
    request.state.audit_actor = actor
    return actor


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
def projects(actor: Actor = Depends(admin)):
    with connect() as conn:
        rows = conn.execute("SELECT name, spec, status FROM projects ORDER BY name").fetchall()
    return [{"name": name, "spec": spec, "status": status} for name, spec, status in rows]

@app.put("/projects/{name}")
def provision(name: str, project: Project, actor: Actor = Depends(admin)):
    if name != project.name:
        required_audit(actor, "project.provision", "project", name, "rejected", {"project": name},
                       {"reason": "path_name_mismatch"})
        raise HTTPException(400, "Path and project name must match")
    try:
        with connect() as conn:
            # Serialize reconciliations across API processes, including database creation.
            conn.execute("SELECT pg_advisory_lock(731904)")
            try:
                conn.execute("""INSERT INTO projects(name,spec,status) VALUES (%s,%s,'provisioning')
                    ON CONFLICT(name) DO UPDATE SET spec=excluded.spec,
                    status='provisioning',updated_at=now()""", (name, Jsonb(project.model_dump())))
                # Register before side effects; failed applications must remain monitored.
                publish_catalog(conn)
                password = password_for(name)
                provision_database(conn, name, password)
                for manifest in resources(name, project.image, project.port,
                        os.environ["APPS_DOMAIN"], os.environ["POSTGRES_IP"], password):
                    apply(manifest)
                conn.execute("UPDATE projects SET status='applied',updated_at=now() WHERE name=%s", (name,))
            except Exception:
                conn.execute("UPDATE projects SET status='failed',updated_at=now() WHERE name=%s", (name,))
                raise
            finally:
                conn.execute("SELECT pg_advisory_unlock(731904)")
    except Exception as exc:
        required_audit(actor, "project.provision", "project", name, "failed", {"project": name},
                       {"error_type": type(exc).__name__})
        log.error("Project reconciliation failed: %s", name)
        raise HTTPException(503, "Provisioning failed; retry the same PUT. Existing data is retained.")
    required_audit(actor, "project.provision", "project", name, "succeeded", {"project": name},
                   {"status": "applied", "image": project.image})
    return {"name": name, "status": "applied", "namespace": "project-" + name,
            "host": name + "." + os.environ["APPS_DOMAIN"]}

class Retirement(BaseModel):
    confirm_name: str


@app.post("/projects/{name}/retire")
def retire(name: str, confirmation: Retirement, actor: Actor = Depends(admin)):
    """Acknowledge manual workload removal; retain catalog, database, and role."""
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
        log.error("Project retirement failed: %s", name)
        raise HTTPException(503, "Retirement incomplete; retry the same request. Existing data is retained.")
    required_audit(actor, "project.retire", "project", name, "succeeded", {"project": name},
                   {"status": "retired", "data_retained": True})
    return {"name": name, "status": "retired", "data_retained": True}


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
