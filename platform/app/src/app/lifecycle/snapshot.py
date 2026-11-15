"""Capture recovery input before retirement removes Kubernetes application secrets."""

from fastapi import HTTPException

from .. import access_store
from ..manifests import SECRET_NAME
from ..secrets import PREVIOUS_SECRET_NAME, _get
from . import catalog


def capture(conn, control, project, project_id):
    found = conn.execute(
        "SELECT encrypted_snapshot FROM project_recovery_points WHERE project_id=%s",
        (project_id,),
    ).fetchone()
    if found:
        return catalog.unseal(project_id, found[0])
    current = control.current_spec(project)
    secrets = []
    if current and current[1]:
        for name in (SECRET_NAME, PREVIOUS_SECRET_NAME):
            existing = _get(control.runtime, name, project)
            if existing:
                # resourceVersion, UID and managedFields belong to the old
                # Kubernetes object and must never be replayed into a new one.
                secrets.append(
                    {
                        "apiVersion": "v1",
                        "kind": "Secret",
                        "type": "Opaque",
                        "metadata": {"name": name, "namespace": "project-" + project},
                        "data": existing.get("data", {}),
                        "annotations": existing.get("metadata", {}).get(
                            "annotations", {}
                        ),
                    }
                )
    grants = conn.execute(
        "SELECT issuer,subject,role FROM platform_grants WHERE scope_kind='project' AND scope_id=%s ORDER BY issuer,subject,role",
        (project,),
    ).fetchall()
    bindings = conn.execute(
        """SELECT g.grant_id::text,g.resource_id::text,g.version FROM store_grants g
        WHERE g.kind='binding' AND g.consumer_project=%s AND g.state='active' ORDER BY g.grant_id""",
        (project,),
    ).fetchall()
    stores = conn.execute(
        "SELECT resource_id::text,version FROM store_resources WHERE owner_project=%s AND state='active' ORDER BY resource_id",
        (project,),
    ).fetchall()
    hosted = [
        row
        for row in access_store.listing(conn)
        if row["project"] == project and row["state"] in {"active", "pending"}
    ]
    value = {
        "revision": (current[0] or 0) if current else 0,
        "spec": current[1] if current else None,
        "secrets": secrets,
        "grants": grants,
        "bindings": bindings,
        "stores": stores,
        "hosted": hosted,
    }
    conn.execute(
        "INSERT INTO project_recovery_points(project_id,encrypted_snapshot) VALUES(%s,%s)",
        (project_id, catalog.seal(project_id, value)),
    )
    return value


def load(conn, project_id):
    row = conn.execute(
        "SELECT encrypted_snapshot FROM project_recovery_points WHERE project_id=%s",
        (project_id,),
    ).fetchone()
    if not row:
        raise HTTPException(409, "The project has no recovery point")
    return catalog.unseal(project_id, row[0])
