"""Rebuild a retired project using retained data and newly issued credentials."""

import os
from uuid import uuid4

from fastapi import HTTPException
from psycopg.types.json import Jsonb

from .. import access_store
from ..identity import Principal
from ..manifests import component_resources
from ..stores import catalog as stores
from ..stores import providers
from . import snapshot


def restore(conn, control, operation):
    project, project_id = operation["project"], operation["project_id"]
    saved = snapshot.load(conn, project_id)
    principal = Principal(**operation["actor"])
    # A platform administrator explicitly approves the recovery snapshot. Roles
    # for automation identities remain revoked; new credentials require issuance.
    for issuer, subject, role in saved["grants"]:
        machine = conn.execute(
            "SELECT 1 FROM deployment_credentials WHERE issuer=%s AND subject=%s",
            (issuer, subject),
        ).fetchone()
        if not machine:
            conn.execute(
                """INSERT INTO platform_grants(issuer,subject,scope_kind,scope_id,role)
                VALUES(%s,%s,'project',%s,%s) ON CONFLICT DO NOTHING""",
                (issuer, subject, project, role),
            )
    # Reconcile stores first. A missing resource is never replaced by an empty
    # database; versions protect a binding revoked independently after retirement.
    for resource_id, version in saved["stores"]:
        resource = stores.resource(conn, resource_id, lock=True)
        if resource["state"] not in {"retired", "active"}:
            raise HTTPException(409, "Retained store is unavailable")
        providers.get(resource["provider"]).validate_recovery(resource)
        conn.execute(
            "UPDATE store_resources SET state='active',observed_state='pending',version=version+1 WHERE resource_id=%s AND state='retired'",
            (resource_id,),
        )
    for grant_id, resource_id, version in saved["bindings"]:
        grant = stores.grant(conn, grant_id, lock=True)
        resource = stores.resource(conn, resource_id)
        if (
            (grant["state"] == "revoked" and grant["version"] != version + 1)
            or (grant["state"] == "active" and grant["version"] != version + 2)
            or resource["state"] != "active"
        ):
            raise HTTPException(409, "A retained binding needs renewed owner approval")
        conn.execute(
            "UPDATE store_grants SET state='active',observed_state='pending',version=version+1 WHERE grant_id=%s AND state='revoked'",
            (grant_id,),
        )
    conn.execute("DELETE FROM store_project_retirements WHERE project=%s", (project,))
    conn.execute(
        "UPDATE projects SET status='restoring' WHERE project_id=%s AND status='retired'",
        (project_id,),
    )
    spec = saved["spec"]
    if spec is None:
        conn.execute(
            "UPDATE projects SET status='empty' WHERE project_id=%s", (project_id,)
        )
        return True
    # Namespace setup precedes secrets; workload creation is performed later by
    # the regular apply worker once restored store credentials have reconciled.
    namespace = component_resources(
        project,
        spec["components"],
        "192.0.2.1",
        "unused",
        spec.get("configuration"),
        os.environ["APPS_DOMAIN"],
    )[0]
    control.apply(namespace)
    for secret in saved["secrets"]:
        secret = dict(secret)
        annotations = secret.pop("annotations", {})
        secret["metadata"]["annotations"] = annotations
        # Managed service credentials are regenerated, never resurrected.
        secret["data"] = {
            k: v
            for k, v in secret.get("data", {}).items()
            if not k.startswith("ACCESS_")
        }
        control.apply(secret)
    from ..stores.worker import reconcile

    reconcile(conn, control)
    pending = conn.execute(
        """SELECT 1 FROM store_grants g JOIN store_resources r USING(resource_id)
        WHERE g.consumer_project=%s AND g.state='active' AND
        (g.observed_state<>'active' OR r.observed_state<>'active') LIMIT 1""",
        (project,),
    ).fetchone()
    if pending:
        return False
    # Record the accepted deployment exactly once and poll it on later passes.
    deployment = operation["result"].get("deployment_operation_id")
    if not deployment:
        deployment, _, revision = control.queue_deploy(
            conn, principal, project, spec, None, lifecycle=True
        )
        conn.execute(
            "UPDATE project_lifecycle_operations SET result=%s WHERE operation_id=%s",
            (
                Jsonb(
                    {"deployment_operation_id": str(deployment), "revision": revision}
                ),
                operation["operation_id"],
            ),
        )
        return False
    state = conn.execute(
        "SELECT state FROM application_operations WHERE operation_id=%s", (deployment,)
    ).fetchone()
    if not state or state[0] == "failed":
        raise HTTPException(409, "Restored deployment failed; inspect its operation")
    if state[0] != "succeeded":
        return False
    # Hosted policies are reprojected before memberships; service identities use
    # fresh generations so old tokens and secrets cannot regain access.
    for old in saved["hosted"]:
        conn.execute(
            """INSERT INTO hosted_access_resources(id,kind,project,name,state,version,spec)
            VALUES(%s,%s,%s,%s,'revoked',%s,%s) ON CONFLICT DO NOTHING""",
            (
                old["id"],
                old["kind"],
                project,
                old["name"],
                old["version"],
                Jsonb(old["spec"]),
            ),
        )
    for old in saved["hosted"]:
        row = access_store.get(conn, old["id"])
        if row["state"] in {"provisioning", "activating", "active"}:
            continue
        kind = row["kind"]
        if kind == "group":
            access_store.update(conn, row, state="active")
        elif kind in {"policy", "membership", "service-access"}:
            spec = dict(old["spec"])
            if kind == "policy":
                spec["sessionEpoch"] = uuid4().hex
                spec.pop("stageGeneration", None)
            elif kind == "service-access":
                spec["credentials"] = [{"id": uuid4().hex, "state": "provisioning"}]
            row = access_store.update(conn, row, state="provisioning", spec=spec)
            access_store.enqueue(
                conn,
                row,
                {
                    "policy": "policy.apply",
                    "membership": "membership.grant",
                    "service-access": "service.provision",
                }[kind],
                principal,
            )
    pending = conn.execute(
        "SELECT 1 FROM hosted_access_resources WHERE project=%s AND state IN ('provisioning','activating','revocation-pending') LIMIT 1",
        (project,),
    ).fetchone()
    return not pending
