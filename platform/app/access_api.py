"""Hosted-application access APIs, installed using the existing control-plane dependencies."""
import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import Body, Depends, Header, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from . import access_store as store
from .access_contract import Approval, Governance, GroupCreate, PolicyCreate, Rotation, ServiceRequest
from .access_provider import audience, derived_secret
from .audit import Actor
from .identity import Principal


def response(row, operation=None, status=200):
    payload = dict(row)
    if operation:
        payload["operation_id"] = operation
        payload["status_url"] = "/v1/access-operations/" + operation
    return JSONResponse(jsonable_encoder(payload), status_code=status,
                        headers={"ETag": '"' + str(row["version"]) + '"', "Cache-Control": "no-store"})


def internal_authorization(value):
    key = os.environ.get("APPLICATION_ACCESS_KEY") or (derived_secret("platform", "internal") if os.environ.get("DATABASE_KEY") else "")
    if len(key) < 32 or not hmac.compare_digest(value or "", "Bearer " + key):
        raise HTTPException(401, "Invalid access-boundary credential")


def install(app, control):
    caller = Depends(control.current_principal)

    def audit(principal, action, row):
        control.required_audit(control.actor_for(principal), "application-access." + action,
            row["kind"], row["id"], "succeeded", {"project": row["project"]},
            {"state": row["state"], "version": row["version"]})

    @app.post("/v1/projects/{project}/application-groups", status_code=202)
    def create_group(project: str, body: GroupCreate, principal: Principal = caller,
                     idempotency_key: str = Header(alias="Idempotency-Key")):
        control.require_permission(principal, "grant", project)
        with control.connect() as conn, store.locked(conn):
            store.project_exists(conn, project)
            replay, digest = store.replay(conn, project, "group", idempotency_key, body.model_dump())
            if replay:
                return response(replay)
            row = store.create(conn, "group", project, body.name, {"displayName": body.displayName}, "active")
            store.remember(conn, row, idempotency_key, digest)
            audit(principal, "group.create", row)
        return response(row, status=201)

    @app.get("/v1/projects/{project}/application-groups")
    def list_groups(project: str, principal: Principal = caller):
        control.require_permission(principal, "view", project)
        with control.connect() as conn:
            return {"items": store.listing(conn, "group", project)}

    @app.delete("/v1/projects/{project}/application-groups/{resource_id}", status_code=202)
    def delete_group(project: str, resource_id: str, principal: Principal = caller,
                     if_match: str = Header(alias="If-Match")):
        control.require_permission(principal, "grant", project)
        with control.connect() as conn, store.locked(conn):
            row = store.get(conn, resource_id, project, "group")
            store.check_version(row, if_match)
            for ref in store.listing(conn, project=project):
                if ref["kind"] == "membership" and ref["state"] != "revoked" and ref["spec"]["groupId"] == resource_id:
                    raise HTTPException(409, "Group is referenced by a membership")
                if ref["kind"] == "policy" and ref["state"] != "revoked":
                    if any(resource_id in r["authorization"]["anyOfGroups"] for r in ref["spec"]["routes"]):
                        raise HTTPException(409, "Group is referenced by a policy")
            row = store.update(conn, row, state="revocation-pending")
            op = store.enqueue(conn, row, "group.revoke", principal)
            audit(principal, "group.revoke", row)
        return response(row, op, 202)

    @app.put("/v1/projects/{project}/governance")
    def governance(project: str, body: Governance, principal: Principal = caller,
                   if_match: str | None = Header(None, alias="If-Match")):
        control.require_permission(principal, "grant", project)
        with control.connect() as conn, store.locked(conn):
            store.project_exists(conn, project)
            row = store.by_name(conn, "governance", project, "project")
            if row:
                store.check_version(row, if_match)
                # A deployed email opt-in cannot outlive its handling record.
                if not body.personalData and any(p["spec"].get("identityAttributes", {}).get("email")
                    for p in store.listing(conn, "policy", project) if p["state"] != "revoked"):
                    raise HTTPException(409, "Disable email release before lowering governance")
                row = store.update(conn, row, spec=body.model_dump())
            else:
                row = store.create(conn, "governance", project, "project", body.model_dump(), "active")
            audit(principal, "governance.update", row)
        return response(row)

    @app.get("/v1/projects/{project}/governance")
    def get_governance(project: str, principal: Principal = caller):
        control.require_permission(principal, "view", project)
        with control.connect() as conn:
            row = store.by_name(conn, "governance", project, "project")
            if row is None:
                raise HTTPException(404, "Project governance is not recorded")
            return response(row)

    def save_policy(conn, project, application, spec, principal, if_match):
        app_id, component = store.application(conn, project, application, spec["component"])
        governance = store.by_name(conn, "governance", project, "project")
        if spec["identityAttributes"]["email"] and (not governance or not governance["spec"]["personalData"]):
            raise HTTPException(409, "Email release requires classified personal-data governance")
        for route in spec["routes"]:
            route["authorization"]["anyOfGroups"] = store.resolve_groups(conn, project,
                route["authorization"]["anyOfGroups"])
        row = store.by_name(conn, "policy", project, application)
        host = component["name"] + "-" + project + "." + os.environ["APPS_DOMAIN"]
        values = {**spec, "applicationId": app_id, "host": host,
                  "backend": "http://" + component["name"] + ".project-" + project + ".svc.cluster.local:" + str(component["ports"][0]["port"])}
        if row:
            store.check_version(row, if_match)
            if row["state"] not in {"active", "failed"}:
                raise HTTPException(409, "Wait for the pending policy operation")
            values["sessionEpoch"] = row["spec"]["sessionEpoch"]
            values["previousRevision"] = row["spec"].get("revisionId")
        else:
            if if_match not in (None, '"0"'):
                raise HTTPException(412, "Policy does not exist")
            values["sessionEpoch"] = store.nonce()
        revision = store.create(conn, "policy-revision", project, application + ":" + uuid4().hex, values, "accepted")
        values["revisionId"] = revision["id"]
        row = store.update(conn, row, spec=values, state="provisioning") if row else store.create(
            conn, "policy", project, application, values, "provisioning")
        op = store.enqueue(conn, row, "policy.apply", principal)
        audit(principal, "policy.accept", row)
        return row, op

    @app.put("/v1/projects/{project}/applications/{application}/access-policy", status_code=202)
    def policy(project: str, application: str, body: PolicyCreate, principal: Principal = caller,
               if_match: str | None = Header(None, alias="If-Match")):
        control.require_permission(principal, "grant", project)
        with control.connect() as conn, store.locked(conn):
            row, op = save_policy(conn, project, application, body.model_dump(), principal, if_match)
        return response(row, op, 202)

    @app.get("/v1/projects/{project}/applications/{application}/access-policy")
    def get_policy(project: str, application: str, principal: Principal = caller):
        control.require_permission(principal, "view", project)
        with control.connect() as conn:
            row = store.by_name(conn, "policy", project, application)
            if not row:
                raise HTTPException(404, "Access policy is not configured")
            return response(row)

    @app.get("/v1/projects/{project}/applications/{application}/access-policy/revisions")
    def revisions(project: str, application: str, principal: Principal = caller):
        control.require_permission(principal, "view", project)
        with control.connect() as conn:
            return {"items": [r for r in store.listing(conn, "policy-revision", project)
                              if r["name"].startswith(application + ":")]}

    @app.post("/v1/projects/{project}/applications/{application}/access-policy/rollback", status_code=202)
    def rollback_policy(project: str, application: str, principal: Principal = caller,
                        if_match: str = Header(alias="If-Match")):
        control.require_permission(principal, "grant", project)
        with control.connect() as conn, store.locked(conn):
            row = store.by_name(conn, "policy", project, application)
            if not row or not row["spec"].get("previousRevision"):
                raise HTTPException(409, "No prior policy revision")
            previous = store.get(conn, row["spec"]["previousRevision"], project, "policy-revision")["spec"]
            spec = PolicyCreate.model_validate({k: previous[k] for k in PolicyCreate.model_fields}).model_dump()
            row, op = save_policy(conn, project, application, spec, principal, if_match)
        return response(row, op, 202)

    @app.get("/v1/projects/{project}/application-access-requests")
    def requests(project: str, state: str | None = Query(None), principal: Principal = caller):
        control.require_permission(principal, "grant", project)
        with control.connect() as conn:
            rows = store.listing(conn, "human-request", project)
            return {"items": [r for r in rows if state is None or r["state"] == state]}

    @app.post("/v1/projects/{project}/application-access-requests/{resource_id}/approve", status_code=202)
    def approve_human(project: str, resource_id: str, body: Approval, principal: Principal = caller,
                      if_match: str = Header(alias="If-Match")):
        control.require_permission(principal, "grant", project)
        with control.connect() as conn, store.locked(conn):
            row = store.get(conn, resource_id, project, "human-request")
            store.check_version(row, if_match)
            if row["state"] != "pending" or datetime.fromisoformat(row["spec"]["expiresAt"]) <= datetime.now(timezone.utc):
                raise HTTPException(409, "Request is not pending; explicitly reopen rejected requests")
            groups = store.resolve_groups(conn, project, body.groups)
            store.get(conn, row["spec"]["policyId"], project, "policy")
            store.memberships(conn, project, row["spec"]["policyId"], row["spec"]["principalId"], groups,
                              row["spec"]["issuer"], row["spec"]["subject"], principal)
            row = store.update(conn, row, state="approved")
            audit(principal, "human.approve", row)
        return response(row, status=202)

    def human_transition(project, resource_id, principal, if_match, target):
        control.require_permission(principal, "grant", project)
        with control.connect() as conn, store.locked(conn):
            row = store.get(conn, resource_id, project, "human-request")
            store.check_version(row, if_match)
            allowed = {"pending"} if target in {"rejected", "cancelled"} else {"rejected", "expired", "cancelled"}
            if row["state"] not in allowed:
                raise HTTPException(409, "Invalid human-request transition")
            spec = row["spec"]
            if target == "pending":
                spec = {**spec, "expiresAt": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()}
            row = store.update(conn, row, state=target, spec=spec)
            audit(principal, "human." + target, row)
        return response(row)

    @app.post("/v1/projects/{project}/application-access-requests/{resource_id}/reject")
    def reject_human(project: str, resource_id: str, principal: Principal = caller,
                     if_match: str = Header(alias="If-Match")):
        return human_transition(project, resource_id, principal, if_match, "rejected")

    @app.post("/v1/projects/{project}/application-access-requests/{resource_id}/reopen")
    def reopen_human(project: str, resource_id: str, principal: Principal = caller,
                     if_match: str = Header(alias="If-Match")):
        return human_transition(project, resource_id, principal, if_match, "pending")

    @app.post("/v1/projects/{project}/application-access-requests/{resource_id}/cancel")
    def cancel_human(project: str, resource_id: str, principal: Principal = caller,
                     if_match: str = Header(alias="If-Match")):
        return human_transition(project, resource_id, principal, if_match, "cancelled")

    @app.get("/v1/projects/{project}/application-group-memberships")
    def list_memberships(project: str, principal: Principal = caller):
        control.require_permission(principal, "grant", project)
        with control.connect() as conn:
            return {"items": store.listing(conn, "membership", project)}

    @app.post("/v1/projects/{project}/application-access-requests/{resource_id}/groups", status_code=202)
    def assign_human_groups(project: str, resource_id: str, body: Approval, principal: Principal = caller,
                            if_match: str = Header(alias="If-Match")):
        control.require_permission(principal, "grant", project)
        with control.connect() as conn, store.locked(conn):
            row = store.get(conn, resource_id, project, "human-request")
            store.check_version(row, if_match)
            if row["state"] != "approved":
                raise HTTPException(409, "Identity has no approved application request")
            spec = row["spec"]
            store.memberships(conn, project, spec["policyId"], spec["principalId"],
                store.resolve_groups(conn, project, body.groups), spec["issuer"], spec["subject"], principal)
            row = store.update(conn, row)
            audit(principal, "human.groups", row)
        return response(row, status=202)

    @app.delete("/v1/projects/{project}/application-group-memberships/{resource_id}", status_code=202)
    def revoke_membership(project: str, resource_id: str, principal: Principal = caller,
                          if_match: str = Header(alias="If-Match")):
        control.require_permission(principal, "grant", project)
        with control.connect() as conn, store.locked(conn):
            row = store.get(conn, resource_id, project, "membership")
            store.check_version(row, if_match)
            row = store.update(conn, row, state="revocation-pending")
            op = store.enqueue(conn, row, "membership.revoke", principal)
            audit(principal, "membership.revoke", row)
        return response(row, op, 202)

    @app.post("/v1/projects/{project}/service-access-requests", status_code=202)
    def request_service(project: str, body: ServiceRequest, principal: Principal = caller,
                        idempotency_key: str = Header(alias="Idempotency-Key")):
        control.require_permission(principal, "change", project)
        with control.connect() as conn, store.locked(conn):
            store.project_exists(conn, project)
            prior, digest = store.replay(conn, project, "service-access", idempotency_key, body.model_dump())
            if prior:
                return response(prior)
            policy = store.by_name(conn, "policy", body.providerProject, body.application)
            store.application(conn, body.providerProject, body.application)
            if not policy or policy["state"] != "active" or not any(
                r["authentication"]["mode"] == "bearer-token" for r in policy["spec"]["routes"]):
                raise HTTPException(409, "Target has no active bearer-token policy")
            row = store.create(conn, "service-access", project, body.name,
                {**body.model_dump(), "policyId": policy["id"], "principalId": "prn_" + uuid4().hex,
                 "groups": [], "credentials": []})
            store.remember(conn, row, idempotency_key, digest)
            audit(principal, "service.request", row)
        return response(row, status=201)

    @app.get("/v1/projects/{project}/service-access-requests")
    def service_requests(project: str, principal: Principal = caller):
        control.require_permission(principal, "view", project)
        with control.connect() as conn:
            return {"items": [r for r in store.listing(conn, "service-access") if r["project"] == project
                              or r["spec"]["providerProject"] == project]}

    @app.post("/v1/projects/{project}/service-access-requests/{resource_id}/approve", status_code=202)
    def approve_service(project: str, resource_id: str, body: Approval, principal: Principal = caller,
                        if_match: str = Header(alias="If-Match")):
        control.require_permission(principal, "grant", project)
        with control.connect() as conn, store.locked(conn):
            row = store.get(conn, resource_id, kind="service-access")
            if row["spec"]["providerProject"] != project:
                raise HTTPException(404, "Unknown provider service-access request")
            store.check_version(row, if_match)
            if row["state"] != "pending":
                raise HTTPException(409, "Service request is not pending")
            groups = store.resolve_groups(conn, project, body.groups)
            policy = store.get(conn, row["spec"]["policyId"], project, "policy")
            allowed = {g for r in policy["spec"]["routes"] if r["authentication"]["mode"] == "bearer-token"
                       for g in r["authorization"]["anyOfGroups"]}
            if not set(groups) <= allowed:
                raise HTTPException(422, "Assign only groups used by target bearer-token routes")
            row = store.update(conn, row, state="provisioning", spec={**row["spec"], "groups": groups,
                "credentials": [{"id": uuid4().hex, "state": "provisioning"}]})
            op = store.enqueue(conn, row, "service.provision", principal)
            audit(principal, "service.approve", row)
        return response(row, op, 202)

    def revoke_service(project, resource_id, principal, if_match, target="revocation-pending"):
        with control.connect() as conn, store.locked(conn):
            row = store.get(conn, resource_id, kind="service-access")
            if row["spec"]["providerProject"] == project:
                control.require_permission(principal, "grant", project)
            elif row["project"] == project:
                control.require_permission(principal, "change", project)
            else:
                raise HTTPException(404, "Unknown service request")
            store.check_version(row, if_match)
            if target in {"rejected", "cancelled"} and row["state"] != "pending":
                raise HTTPException(409, "Service request is no longer pending")
            row = store.update(conn, row, state=target)
            op = store.enqueue(conn, row, "service.revoke", principal) if target == "revocation-pending" else None
            audit(principal, "service." + target, row)
        return response(row, op, 202 if op else 200)

    @app.post("/v1/projects/{project}/service-access-requests/{resource_id}/reject")
    def reject_service(project: str, resource_id: str, principal: Principal = caller,
                       if_match: str = Header(alias="If-Match")):
        # Only the provider may reject; consumers cancel their own pending request.
        control.require_permission(principal, "grant", project)
        with control.connect() as conn:
            if store.get(conn, resource_id, kind="service-access")["spec"]["providerProject"] != project:
                raise HTTPException(404, "Unknown provider request")
        return revoke_service(project, resource_id, principal, if_match, "rejected")

    @app.post("/v1/projects/{project}/service-access-requests/{resource_id}/cancel")
    def cancel_service(project: str, resource_id: str, principal: Principal = caller,
                       if_match: str = Header(alias="If-Match")):
        control.require_permission(principal, "change", project)
        with control.connect() as conn:
            store.get(conn, resource_id, project, "service-access")
        return revoke_service(project, resource_id, principal, if_match, "cancelled")

    @app.delete("/v1/projects/{project}/service-access-requests/{resource_id}", status_code=202)
    def revoke_access(project: str, resource_id: str, principal: Principal = caller,
                      if_match: str = Header(alias="If-Match")):
        return revoke_service(project, resource_id, principal, if_match)

    @app.post("/v1/projects/{project}/service-access-requests/{resource_id}/rotate", status_code=202)
    def rotate_service(project: str, resource_id: str, body: Rotation, principal: Principal = caller,
                       if_match: str = Header(alias="If-Match")):
        control.require_permission(principal, "change", project)
        with control.connect() as conn, store.locked(conn):
            row = store.get(conn, resource_id, project, "service-access")
            store.check_version(row, if_match)
            if row["state"] != "active" or any(c["state"] == "overlap" for c in row["spec"]["credentials"]):
                raise HTTPException(409, "Service access is not ready for rotation")
            until = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
            credentials = [{**c, "state": "revocation-pending" if body.emergency else "overlap", "expiresAt": until}
                           if c["state"] == "active" else c for c in row["spec"]["credentials"]]
            credentials.append({"id": uuid4().hex, "state": "provisioning"})
            row = store.update(conn, row, spec={**row["spec"], "credentials": credentials})
            op = store.enqueue(conn, row, "service.rotate", principal)
            audit(principal, "service.rotate", row)
        return response(row, op, 202)

    @app.post("/v1/projects/{project}/service-access-requests/{resource_id}/confirm", status_code=202)
    def confirm_service(project: str, resource_id: str, principal: Principal = caller,
                        if_match: str = Header(alias="If-Match")):
        control.require_permission(principal, "change", project)
        with control.connect() as conn, store.locked(conn):
            row = store.get(conn, resource_id, project, "service-access")
            store.check_version(row, if_match)
            if not any(c["state"] == "active" for c in row["spec"]["credentials"]):
                raise HTTPException(409, "Replacement credential is not active")
            creds = [{**c, "state": "revocation-pending"} if c["state"] == "overlap" else c
                     for c in row["spec"]["credentials"]]
            row = store.update(conn, row, spec={**row["spec"], "credentials": creds, "adoption": "confirmed"})
            op = store.enqueue(conn, row, "service.cleanup", principal)
            audit(principal, "service.confirm", row)
        return response(row, op, 202)

    @app.get("/v1/access-operations/{operation_id}")
    def access_operation(operation_id: str, principal: Principal = caller):
        with control.connect() as conn:
            op = conn.execute("""SELECT resource_id, state, attempts, error_code, created_at, updated_at
                FROM hosted_access_operations WHERE id::text=%s""", (operation_id,)).fetchone()
            if not op:
                raise HTTPException(404, "Unknown access operation")
            row = store.get(conn, op[0])
            try:
                control.require_permission(principal, "view", row["project"])
            except HTTPException as exc:
                if exc.status_code != 403 or row["kind"] != "service-access":
                    raise
                control.require_permission(principal, "view", row["spec"]["providerProject"])
            return {"id": operation_id, "resourceId": op[0], "state": op[1], "attempts": op[2],
                    "errorCode": op[3], "createdAt": op[4], "updatedAt": op[5]}

    @app.post("/v1/access-operations/{operation_id}/retry", status_code=202)
    def retry_operation(operation_id: str, principal: Principal = caller,
                        if_match: str = Header(alias="If-Match")):
        with control.connect() as conn, store.locked(conn):
            op = conn.execute("SELECT resource_id, action, state FROM hosted_access_operations WHERE id::text=%s", (operation_id,)).fetchone()
            if not op:
                raise HTTPException(404, "Unknown access operation")
            row = store.get(conn, op[0])
            project = row["spec"].get("providerProject", row["project"]) if op[1] == "service.provision" else row["project"]
            control.require_permission(principal, "change" if op[1] == "service.rotate" else "grant", project)
            store.check_version(row, if_match)
            if op[2] != "failed" or row["state"] != "failed":
                raise HTTPException(409, "Only a failed resource operation can be retried")
            row = store.update(conn, row, state="provisioning")
            new_op = store.enqueue(conn, row, op[1], principal)
            audit(principal, "operation.retry", row)
        return response(row, new_op, 202)

    @app.post("/operator/application-access/recover", status_code=202)
    def recover(principal: Principal = caller):
        control.require_human_platform_admin(principal)
        operations = []
        with control.connect() as conn, store.locked(conn):
            for row in store.listing(conn):
                if row["kind"] == "policy" and row["state"] not in {"revoked", "revocation-pending"}:
                    row = store.update(conn, row, state="provisioning", spec={**row["spec"], "sessionEpoch": store.nonce()})
                    operations.append(store.enqueue(conn, row, "policy.apply", principal))
                elif row["kind"] == "membership" and row["state"] in {"active", "provisioning"}:
                    row = store.update(conn, row, state="provisioning")
                    operations.append(store.enqueue(conn, row, "membership.grant", principal))
                elif row["kind"] == "service-access" and row["state"] in {"active", "provisioning"} and row["spec"]["credentials"]:
                    # Invalidate old credential subjects in snapshots before restoring any provider state.
                    creds = [{**c, "state": "revocation-pending"} for c in row["spec"]["credentials"] if c["state"] != "revoked"]
                    creds.append({"id": uuid4().hex, "state": "provisioning"})
                    row = store.update(conn, row, state="provisioning", spec={**row["spec"], "credentials": creds})
                    operations.append(store.enqueue(conn, row, "service.rotate", principal))
                elif row["state"] == "revocation-pending" and row["kind"] in {"membership", "service-access", "policy", "group"}:
                    operations.append(store.enqueue(conn, row, row["kind"] + ".revoke", principal))
                else:
                    continue
                audit(principal, "recover", row)
            conn.execute("""INSERT INTO hosted_access_metadata(key,value) VALUES ('recovery-required','false')
                ON CONFLICT(key) DO UPDATE SET value='false'""")
            store.bump(conn)
        return {"operationIds": operations, "browserSessionsInvalidated": True}

    @app.get("/internal/application-access/snapshot", include_in_schema=False)
    def snapshot(authorization: str | None = Header(None)):
        internal_authorization(authorization)
        with control.connect() as conn, conn.transaction():
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            now = datetime.now(timezone.utc)
            rows = store.listing(conn)
            required = conn.execute("SELECT value FROM hosted_access_metadata WHERE key='recovery-required'").fetchone()
            recovery_required = bool(required and required[0])
            retired = {r[0] for r in conn.execute("SELECT name FROM projects WHERE status='retired'").fetchall()}
            aliases = conn.execute("SELECT issuer, subject, id, kind FROM hosted_access_principals").fetchall()
            policies = []
            for row in rows:
                if row["kind"] != "policy" or row["project"] in retired:
                    continue
                try:
                    _, component = store.application(conn, row["project"], row["name"], row["spec"]["component"])
                    backend = "http://" + component["name"] + ".project-" + row["project"] + ".svc.cluster.local:" + str(component["ports"][0]["port"])
                    if backend != row["spec"]["backend"] or row["spec"]["host"] != component["name"] + "-" + row["project"] + "." + os.environ["APPS_DOMAIN"]:
                        continue
                except HTTPException:
                    continue
                policies.append(row)
            return {"generation": store.generation(conn), "issuedAt": now.timestamp(), "expiresAt": (now + timedelta(minutes=5)).timestamp(),
                "issuer": os.environ["OIDC_ISSUER"], "jwksUrl": os.environ.get("APPLICATION_ACCESS_JWKS_URL", os.environ["OIDC_JWKS_URL"]),
                "policies": [] if recovery_required else policies,
                "recoveryRequired": recovery_required,
                "memberships": [r for r in rows if r["kind"] == "membership" and r["project"] not in retired],
                "services": [r for r in rows if r["kind"] == "service-access" and r["project"] not in retired and r["spec"]["providerProject"] not in retired],
                "principals": [{"issuer": r[0], "subject": r[1], "id": r[2], "kind": r[3]} for r in aliases]}

    @app.post("/internal/application-access/replicas/{replica_id}", include_in_schema=False)
    def replica(replica_id: str, body: dict = Body(...), authorization: str | None = Header(None)):
        internal_authorization(authorization)
        if not 1 <= len(replica_id) <= 100 or not isinstance(body.get("generation"), int):
            raise HTTPException(422, "Invalid replica acknowledgement")
        with control.connect() as conn:
            conn.execute("""INSERT INTO hosted_access_replicas(id, generation) VALUES (%s,%s)
                ON CONFLICT(id) DO UPDATE SET generation=excluded.generation, observed_at=now()""", (replica_id, body["generation"]))
        return {"acknowledged": True}

    @app.post("/internal/application-access/enroll", include_in_schema=False)
    def enroll(body: dict = Body(...), authorization: str | None = Header(None)):
        internal_authorization(authorization)
        from .access_tokens import TokenVerifier
        with control.connect() as conn, store.locked(conn):
            policy = store.get(conn, body.get("policyId"), kind="policy")
            if policy["state"] != "active":
                raise HTTPException(503, "Application policy is not active")
            token = TokenVerifier(os.environ["OIDC_ISSUER"], audience(policy["spec"]["applicationId"]),
                                  os.environ["OIDC_JWKS_URL"]).verify(body.get("accessToken", ""))
            if token["azp"] != "browser-" + policy["id"]:
                raise HTTPException(401, "Expected the application browser identity")
            pid, request = store.enroll(conn, policy, token["iss"], token["sub"])
            control.required_audit(Actor("oidc", token["iss"] + "|" + token["sub"]),
                "application-access.human.enroll", "human-request", request["id"], "succeeded",
                {"project": policy["project"]}, {"state": request["state"]})
        return {"principalId": pid, "requestId": request["id"], "state": request["state"]}
