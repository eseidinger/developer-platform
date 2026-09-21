"""Trusted administrator API. Not a public multi-tenant control plane."""
import hashlib
import hmac
import logging
import os
from contextlib import asynccontextmanager

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from kubernetes import config, dynamic
from kubernetes.client import ApiClient
from pydantic import BaseModel, Field, field_validator

from .manifests import resources, validate_name

log = logging.getLogger(__name__)
auth = HTTPBearer()
runtime = None

def connect():
    return psycopg.connect(host=os.environ["POSTGRES_HOST"], dbname="platform",
        user="postgres", password=os.environ["POSTGRES_PASSWORD"],
        connect_timeout=5, autocommit=True)

@asynccontextmanager
async def lifespan(app):
    global runtime
    for key in ("PLATFORM_TOKEN", "DATABASE_KEY"):
        if len(os.environ.get(key, "")) < 32:
            raise RuntimeError(key + " must contain at least 32 characters")
    with connect() as conn:
        conn.execute("REVOKE ALL ON DATABASE platform FROM PUBLIC")
        conn.execute("""CREATE TABLE IF NOT EXISTS projects (
            name TEXT PRIMARY KEY, spec JSONB NOT NULL, status TEXT NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now())""")
    config.load_kube_config()
    runtime = dynamic.DynamicClient(ApiClient())
    yield

app = FastAPI(title="Hybrid Developer Platform", lifespan=lifespan)

def admin(credentials: HTTPAuthorizationCredentials = Depends(auth)):
    if not hmac.compare_digest(credentials.credentials, os.environ["PLATFORM_TOKEN"]):
        raise HTTPException(401, "Invalid administrator token")

class Project(BaseModel):
    name: str
    image: str = Field(min_length=1, max_length=512, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9./_:@-]+$")
    port: int = Field(default=8080, ge=1024, le=65535)

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

@app.get("/projects", dependencies=[Depends(admin)])
def projects():
    with connect() as conn:
        rows = conn.execute("SELECT name, spec, status FROM projects ORDER BY name").fetchall()
    return [{"name": name, "spec": spec, "status": status} for name, spec, status in rows]

@app.put("/projects/{name}", dependencies=[Depends(admin)])
def provision(name: str, project: Project):
    if name != project.name:
        raise HTTPException(400, "Path and project name must match")
    try:
        with connect() as conn:
            # Serialize reconciliations across API processes, including database creation.
            conn.execute("SELECT pg_advisory_lock(731904)")
            try:
                conn.execute("""INSERT INTO projects(name,spec,status) VALUES (%s,%s,'provisioning')
                    ON CONFLICT(name) DO UPDATE SET spec=excluded.spec,
                    status='provisioning',updated_at=now()""", (name, Jsonb(project.model_dump())))
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
    except Exception:
        log.error("Project reconciliation failed: %s", name)
        raise HTTPException(503, "Provisioning failed; retry the same PUT. Existing data is retained.")
    return {"name": name, "status": "applied", "namespace": "project-" + name,
            "host": name + "." + os.environ["APPS_DOMAIN"]}

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
