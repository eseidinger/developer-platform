"""Durable, retryable hosted-access reconciliation and credential cleanup."""
import os
import time
from datetime import datetime, timezone

from fastapi import HTTPException

from . import access_store as store
from .access_provider import KeycloakAccessProvider, audience
from .access_runtime import browser_manifests, browser_name, protected_ingress
from .identity import Principal
from .secrets import confirm_secret, remove_secret, write_secret


def policy_groups(policy):
    return sorted({g for r in policy["spec"]["routes"] for g in r["authorization"]["anyOfGroups"]})


def selected_memberships(conn, policy_id, principal_id):
    return [m for m in store.listing(conn, "membership") if m["spec"]["policyId"] == policy_id
            and m["spec"]["principalId"] == principal_id]


def desired_groups(conn, policy_id, principal_id):
    return sorted({m["spec"]["groupId"] for m in selected_memberships(conn, policy_id, principal_id)
                   if m["state"] in {"provisioning", "active"}})


def roll_services(runtime, project, version):
    resource = runtime.resources.get(api_version="apps/v1", kind="Deployment")
    items = resource.get(namespace="project-" + project, label_selector="platform.example/component").items
    for deployment in items:
        resource.patch(name=deployment.metadata.name, namespace="project-" + project,
            body={"spec": {"template": {"metadata": {"annotations": {"platform.example/secrets-version": version}}}}},
            content_type="application/merge-patch+json", field_manager="developer-platform-access")


def ready_replicas(runtime):
    pods = runtime.resources.get(api_version="v1", kind="Pod").get(namespace="platform-access",
        label_selector="platform.example/access-role=authorizer").items
    return {p.metadata.uid for p in pods if not p.metadata.get("deletionTimestamp") and any(
        c.type == "Ready" and c.status == "True" for c in (p.status.get("conditions") or []))}


def proxy_ready(runtime, policy):
    try:
        deployment = runtime.resources.get(api_version="apps/v1", kind="Deployment").get(
            name=browser_name(policy), namespace="platform-access")
        return deployment.status.get("observedGeneration", 0) >= deployment.metadata.generation \
            and deployment.status.get("updatedReplicas", 0) == 1 and deployment.status.get("readyReplicas", 0) == 1
    except Exception:
        return False


def projection(conn, provider, policy, principal_id):
    groups = desired_groups(conn, policy["id"], principal_id)
    aliases = conn.execute("SELECT subject FROM hosted_access_principals WHERE id=%s AND issuer=%s",
                          (principal_id, os.environ["OIDC_ISSUER"])).fetchall()
    service = next((r for r in store.listing(conn, "service-access") if r["spec"]["principalId"] == principal_id), None)
    if service:
        live = {c.get("subject") for c in service["spec"]["credentials"] if c["state"] in {"active", "overlap"}}
        aliases = [(s,) for (s,) in aliases if s in live]
    for (subject,) in aliases:
        provider.set_membership(policy["spec"]["applicationId"], subject, groups)


def reconcile(conn, row, action, actor, provider, runtime, apply, remove):
    kind, spec = row["kind"], row["spec"]
    if kind == "group":
        for policy in store.listing(conn, "policy", row["project"]):
            provider.delete_role(policy["spec"]["applicationId"], row["id"])
        store.update(conn, row, state="revoked")
    elif kind == "policy":
        if row["state"] == "revocation-pending":
            provider.delete_client("browser-" + row["id"])
            provider.delete_client(audience(spec["applicationId"]))
            for manifest in browser_manifests(row) + [protected_ingress(spec["host"])]:
                try:
                    remove(manifest)
                except Exception as exc:
                    if getattr(exc, "status", None) != 404:
                        raise
            store.update(conn, row, state="revoked")
            return True
        store.application(conn, row["project"], row["name"], spec["component"])
        groups = policy_groups(row)
        provider.resource(spec["applicationId"])
        for gid in groups:
            provider.role(spec["applicationId"], gid)
        browser = any(r["authentication"]["mode"] == "browser-session" for r in spec["routes"])
        if browser:
            provider.browser(row, spec["host"], groups)
            for manifest in browser_manifests(row):
                apply(manifest)
            if not proxy_ready(runtime, row):
                return False
        apply(protected_ingress(spec["host"], row["project"]))
        if row["state"] != "activating":
            # Deny first. Stage one complete policy; do not grant until every ready replica has compiled it.
            row = store.update(conn, row, state="activating", spec={**spec, "stageGeneration": store.generation(conn) + 1})
            return False
        replicas = ready_replicas(runtime)
        acks = {r[0] for r in conn.execute("""SELECT id FROM hosted_access_replicas
            WHERE generation >= %s AND observed_at>now()-interval '10 seconds'""", (spec["stageGeneration"],)).fetchall()}
        if len(replicas) < int(os.environ.get("APPLICATION_ACCESS_REPLICAS", "2")) or not replicas <= acks:
            return False
        store.update(conn, row, state="active")
    elif kind == "membership":
        policy = store.get(conn, spec["policyId"], kind="policy")
        if policy["state"] in {"revoked", "revocation-pending"}:
            store.update(conn, row, state="revoked")
            return True
        if policy["state"] != "active":
            return False
        projection(conn, provider, policy, spec["principalId"])
        store.update(conn, row, state="revoked" if row["state"] == "revocation-pending" else "active")
    elif kind == "service-access":
        policy = store.get(conn, spec["policyId"], kind="policy")
        revoking = row["state"] == "revocation-pending"
        if not revoking and policy["state"] != "active":
            return False
        prefix = "ACCESS_" + row["id"][-12:].upper()
        credentials = [dict(c) for c in spec["credentials"]]
        memberships = selected_memberships(conn, policy["id"], spec["principalId"])
        groups = desired_groups(conn, policy["id"], spec["principalId"]) if memberships or spec.get("membershipsEstablished") else spec["groups"]
        now = datetime.now(timezone.utc)
        for credential in credentials:
            expired = credential["state"] == "overlap" and datetime.fromisoformat(credential["expiresAt"]) <= now
            if revoking or expired or credential["state"] == "revocation-pending":
                provider.delete_client("service-" + credential["id"])
                credential["state"] = "revoked"
                if expired:
                    spec = {**spec, "adoption": "adoption-timeout"}
        for credential in credentials:
            if credential["state"] != "provisioning":
                continue
            found = provider.service(policy, credential["id"], groups)
            store.principal(conn, os.environ["OIDC_ISSUER"], found["subject"], "service", spec["principalId"])
            for gid in groups:
                name = policy["id"] + ":" + spec["principalId"] + ":" + gid
                membership = store.by_name(conn, "membership", policy["project"], name)
                if not membership:
                    membership = store.create(conn, "membership", policy["project"], name,
                        {"policyId": policy["id"], "principalId": spec["principalId"], "groupId": gid,
                         "issuer": os.environ["OIDC_ISSUER"], "subject": found["subject"]}, "provisioning")
                if membership["state"] == "provisioning":
                    store.update(conn, membership, state="active")
            # The caller receives a managed secret, never an API response containing credential values.
            for suffix, value in (("CLIENT_ID", found["clientId"]), ("CLIENT_SECRET", found["secret"]),
                                  ("TOKEN_URL", os.environ["OIDC_ISSUER"] + "/protocol/openid-connect/token")):
                version = write_secret(runtime, row["project"], prefix + "_" + suffix, value)
            roll_services(runtime, row["project"], version)
            credential.update({"state": "active", "clientId": found["clientId"], "subject": found["subject"]})
        if revoking:
            for membership in memberships:
                if membership["state"] != "revoked":
                    store.update(conn, membership, state="revoked")
            exists = True
            try:
                runtime.resources.get(api_version="v1", kind="Namespace").get(name="project-" + row["project"])
            except Exception as exc:
                if getattr(exc, "status", None) != 404:
                    raise
                exists = False
            if exists:
                for suffix in ("CLIENT_ID", "CLIENT_SECRET", "TOKEN_URL"):
                    version = remove_secret(runtime, row["project"], prefix + "_" + suffix)
                roll_services(runtime, row["project"], version)
        elif not any(c["state"] == "overlap" for c in credentials):
            for suffix in ("CLIENT_ID", "CLIENT_SECRET", "TOKEN_URL"):
                confirm_secret(runtime, row["project"], prefix + "_" + suffix)
        store.update(conn, row, state="revoked" if revoking else "active", spec={**spec,
            "credentials": credentials, "membershipsEstablished": True, "secretPrefix": prefix, "audience": audience(policy["spec"]["applicationId"]),
            "providerUrl": "https://" + policy["spec"]["host"]})
    return True


def process_one(control, provider_factory=KeycloakAccessProvider):
    with control.connect() as conn, store.locked(conn):
        op = conn.execute("""SELECT id, resource_id, version, action, actor_issuer, actor_subject
            FROM hosted_access_operations WHERE state IN ('queued','running')
            AND (state='queued' OR updated_at<now()-interval '2 seconds') ORDER BY updated_at LIMIT 1""").fetchone()
        if not op:
            return False
        oid, resource_id, version, action, issuer, subject = op
        row = store.get(conn, resource_id)
        if version != row["version"]:
            conn.execute("UPDATE hosted_access_operations SET state='succeeded', error_code='superseded', updated_at=now() WHERE id=%s", (oid,))
            return True
        conn.execute("""UPDATE hosted_access_operations SET state='running', attempts=attempts+1,
            updated_at=now() WHERE id=%s""", (oid,))
        actor = Principal(issuer, subject)
        try:
            # Revocations keep running after administrator authority changes. Grants recheck authority.
            if "revoke" not in action and "cleanup" not in action:
                permission_project = row["spec"].get("providerProject", row["project"]) if action == "service.provision" else row["project"]
                from .authorization import is_allowed
                if not is_allowed(conn, actor, "grant" if action not in {"service.rotate"} else "change", permission_project):
                    raise HTTPException(403, "Administrator authority was revoked")
            if row["state"] in {"revoked", "rejected", "cancelled"}:
                done = True
            elif action.endswith("grant") and row["state"] == "revocation-pending":
                done = True  # Superseded grant must never resurrect a membership.
            else:
                with conn.transaction():
                    done = reconcile(conn, row, action, actor, provider_factory(), control.runtime, control.apply, control.remove)
            latest = store.get(conn, resource_id)
            conn.execute("""UPDATE hosted_access_operations SET state=%s, version=%s, error_code=NULL, updated_at=now()
                WHERE id=%s""", ("succeeded" if done else "running", latest["version"], oid))
            if done:
                control.required_audit(control.actor_for(actor), "application-access.reconcile", row["kind"], row["id"],
                    "succeeded", {"project": row["project"]}, {"operationId": str(oid), "action": action})
        except Exception as exc:
            # Failed cleanup remains retryable and non-authorizing. No exception message is persisted or logged.
            permanent = isinstance(exc, HTTPException) and exc.status_code in {403, 404, 409}
            if permanent and "revoke" not in action:
                latest = store.get(conn, row["id"])
                store.update(conn, latest, state="failed")
            conn.execute("""UPDATE hosted_access_operations SET state=%s, error_code=%s, updated_at=now() WHERE id=%s""",
                ("failed" if permanent and "revoke" not in action else "running", "authorization_revoked" if permanent else "provider_unavailable", oid))
            control.best_effort_audit(control.actor_for(actor), "application-access.reconcile", row["kind"], row["id"],
                "failed", {"project": row["project"]}, {"operationId": str(oid), "errorType": type(exc).__name__})
    return True


def maintain(control):
    """Expire requests and overlaps even when provider cleanup is unavailable."""
    with control.connect() as conn, store.locked(conn):
        internal = Principal("platform-internal", "credential-expiry")
        for row in store.prune(conn):
            control.required_audit(control.actor_for(internal), "application-access.request.expire", row["kind"], row["id"],
                "succeeded", {"project": row["project"]}, {"state": "expired"})
        for row in store.listing(conn, "service-access"):
            if row["state"] != "active":
                continue
            creds = []
            changed = False
            for c in row["spec"]["credentials"]:
                if c["state"] == "overlap" and datetime.fromisoformat(c["expiresAt"]) <= datetime.now(timezone.utc):
                    c = {**c, "state": "revocation-pending"}
                    changed = True
                creds.append(c)
            if changed:
                row = store.update(conn, row, spec={**row["spec"], "credentials": creds, "adoption": "adoption-timeout"})
                store.enqueue(conn, row, "service.cleanup", internal)
                control.required_audit(control.actor_for(internal), "application-access.rotation.expire", row["kind"], row["id"],
                    "succeeded", {"project": row["project"]}, {"adoption": "adoption-timeout"})


def loop(stop, control):
    last_maintenance = 0
    while not stop.is_set():
        try:
            if time.monotonic() - last_maintenance >= 30:
                maintain(control)
                last_maintenance = time.monotonic()
            process_one(control)
        except Exception as exc:
            control.log.error("Hosted access reconciliation failed error_type=%s", type(exc).__name__)
        stop.wait(1)
