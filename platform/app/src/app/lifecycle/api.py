"""Human administrator lifecycle previews and scope-bound operation acceptance."""

import hashlib
import json
from uuid import UUID

from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from ..identity import Principal
from ..stores import catalog as stores
from . import catalog, snapshot


class Confirmation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm_name: str
    confirm_project_id: UUID
    scope_token: str = Field(min_length=64, max_length=32768)


class LifecycleAccepted(BaseModel):
    operation_id: UUID
    kind: str
    state: str
    status_url: str


def scope(conn, control, name, action):
    current = catalog.project(conn, name)
    inventory = stores.retirement_inventory(conn, name)
    history = {}
    for key, query, parameters in (
        (
            "resources",
            "SELECT resource_id::text,version,state FROM store_resources WHERE owner_project=%s ORDER BY resource_id",
            (name,),
        ),
        (
            "grants",
            "SELECT g.grant_id::text,g.version,g.state FROM store_grants g JOIN store_resources r USING(resource_id) WHERE r.owner_project=%s OR g.consumer_project=%s ORDER BY g.grant_id",
            (name, name),
        ),
        (
            "hosted",
            "SELECT id,version,state FROM hosted_access_resources WHERE project=%s OR spec->>'providerProject'=%s ORDER BY id",
            (name, name),
        ),
    ):
        history[key] = conn.execute(query, parameters).fetchall()
    inventory["history_sha256"] = hashlib.sha256(
        json.dumps(history, default=str, sort_keys=True).encode()
    ).hexdigest()
    inventory["record_counts"] = {key: len(value) for key, value in history.items()}
    blockers = []
    if conn.execute(control.ACTIVE_OPERATION_SQL, (name,)).fetchone():
        blockers.append("application_operation_active")
    if action == "restore":
        if current["status"] != "retired":
            blockers.append("project_not_retired")
        if not conn.execute(
            "SELECT 1 FROM project_recovery_points WHERE project_id=%s",
            (current["project_id"],),
        ).fetchone():
            blockers.append("recovery_point_missing")
        if "recovery_point_missing" not in blockers:
            saved = snapshot.load(conn, current["project_id"])
            inventory["recovery_revision"] = saved["revision"]
            for identity, _ in saved["stores"]:
                row = conn.execute(
                    "SELECT state FROM store_resources WHERE resource_id=%s",
                    (identity,),
                ).fetchone()
                if not row or row[0] not in {"retired", "active"}:
                    blockers.append("retained_store_unavailable:" + identity)
    if action == "retire" and current["status"] not in {
        "applied",
        "failed",
        "empty",
        "provisioning",
    }:
        blockers.append("project_not_active")
    if action == "purge":
        consumers = conn.execute(
            """SELECT DISTINCT g.consumer_project FROM store_grants g JOIN store_resources r USING(resource_id)
            WHERE r.owner_project=%s AND g.consumer_project<>%s AND g.state IN ('pending','active') ORDER BY g.consumer_project""",
            (name, name),
        ).fetchall()
        foreign_access = conn.execute(
            """SELECT DISTINCT project FROM hosted_access_resources
            WHERE spec->>'providerProject'=%s AND project<>%s AND state NOT IN ('revoked','rejected','cancelled','expired') ORDER BY project""",
            (name, name),
        ).fetchall()
        if consumers or foreign_access:
            blockers.append("foreign_consumers_must_disconnect")
        inventory["foreign_consumers"] = sorted(
            {r[0] for r in consumers + foreign_access}
        )
    # UUID and a digest of every observed version bind the preview to the exact
    # ownership graph. No secret or AI content is embedded in the token.
    return {
        "project": name,
        "project_id": current["project_id"],
        "status": current["status"],
        "updated_at": current["updated_at"],
        "action": action,
        "inventory": inventory,
        "blockers": blockers,
    }


def install(app, control):
    caller = Depends(control.current_principal)

    def administrator(principal):
        control.require_platform_admin(principal)
        with control.connect() as conn:
            if control.access_scope(conn, principal) is not None:
                raise HTTPException(
                    403, "Lifecycle operations require a human platform administrator"
                )

    def preview(project, action, principal):
        administrator(principal)
        with control.connect() as conn, conn.transaction():
            conn.execute("SELECT pg_advisory_xact_lock(%s)", (catalog.LOCK,))
            result = scope(conn, control, project, action)
        return {
            **result,
            "scope_token": catalog.issue_token(result),
            "expires_in_seconds": catalog.TOKEN_SECONDS,
        }

    def accept(project, action, body, principal):
        administrator(principal)
        with control.connect() as conn, conn.transaction():
            conn.execute("SELECT pg_advisory_xact_lock(%s)", (catalog.LOCK,))
            result = scope(conn, control, project, action)
            accepted = catalog.enqueue(conn, project, action, body, principal, result)
            control.required_audit(
                control.actor_for(principal),
                "project." + action + ".accepted",
                "project",
                project,
                "succeeded",
                {"project": project},
                {
                    "project_id": result["project_id"],
                    "operation_id": accepted["operation_id"],
                },
            )
            if (
                action in {"retire", "purge"}
                and not conn.execute(
                    "SELECT 1 FROM project_recovery_points WHERE project_id=%s",
                    (result["project_id"],),
                ).fetchone()
            ):
                snapshot.capture(conn, control, project, result["project_id"])
        return accepted

    @app.get("/v1/projects/{project}/retirement-preview")
    def retirement_preview(project: str, principal: Principal = caller):
        return preview(project, "retire", principal)

    @app.post(
        "/v1/projects/{project}/retire",
        status_code=202,
        response_model=LifecycleAccepted,
    )
    def retire(project: str, body: Confirmation, principal: Principal = caller):
        return accept(project, "retire", body, principal)

    @app.get("/v1/operator/projects/{project}/restore-preview")
    def restore_preview(project: str, principal: Principal = caller):
        return preview(project, "restore", principal)

    @app.post(
        "/v1/operator/projects/{project}/restore",
        status_code=202,
        response_model=LifecycleAccepted,
    )
    def restore(project: str, body: Confirmation, principal: Principal = caller):
        return accept(project, "restore", body, principal)

    @app.get("/v1/operator/projects/{project}/purge-preview")
    def purge_preview(project: str, principal: Principal = caller):
        return preview(project, "purge", principal)

    @app.post(
        "/v1/operator/projects/{project}/purge",
        status_code=202,
        response_model=LifecycleAccepted,
    )
    def purge(project: str, body: Confirmation, principal: Principal = caller):
        return accept(project, "purge", body, principal)
