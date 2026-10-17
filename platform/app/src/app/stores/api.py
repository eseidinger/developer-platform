"""Resource administration and explicit human data-access APIs."""
from contextlib import contextmanager
import os
from uuid import UUID
from fastapi import Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from psycopg.errors import UniqueViolation
from . import catalog, providers, recovery
from .contract import (ResourceCreate, ResourceRename, Version, Purge, HumanGrant,
                       BindingRequest, Approval, GrantUpdate, QuotaChange, PublicKey)
from ..identity import Principal


def reply(body, status=200):
    return JSONResponse(jsonable_encoder(body), status_code=status, headers={"Cache-Control": "no-store"})


def install(app, control):
    caller = Depends(control.current_principal)
    from starlette.routing import Host
    from . import console

    def console_lease(credential_id):
        with control.connect() as conn:
            return console.lease(conn, credential_id)

    def register_console_session(row, access, digest, expiry):
        with control.connect() as conn, conn.transaction():
            console.record_session(conn, row, access, digest, expiry)
            control.required_audit(control.actor_for(Principal(row['issuer'], row['subject'])),
                'store.console-session-issue', 'store-credential', str(row['credential_id']), 'succeeded')

    app.router.routes.insert(0, Host('console-{port:int}.' + os.environ.get('APPS_DOMAIN', 'apps.localhost'),
        app=console.create_gateway(console_lease, register=register_console_session)))

    def human(conn, principal):
        # Known automation records are insufficient: an unregistered service
        # client is still not a human. Only the supported interactive public
        # clients (code+PKCE, no service accounts) can use personal data access.
        if (principal.authorized_party not in {"platform-cli", "platform-portal"}
                or control.access_scope(conn, principal) is not None):
            raise HTTPException(403, "Personal data access requires an interactive platform CLI or portal identity")

    @contextmanager
    def mutation(principal):
        try:
            with control.connect() as conn, conn.transaction():
                catalog.lock(conn)
                if recovery.required(conn):
                    raise HTTPException(503, "Named-store recovery reconciliation is required")
                yield conn
        except catalog.NotFound:
            raise HTTPException(404, "Unknown resource or grant") from None
        except (catalog.Conflict, UniqueViolation) as exc:
            message = str(exc) if isinstance(exc, catalog.Conflict) else "Resource or grant already exists"
            raise HTTPException(409, message) from None
        except providers.ProviderUnavailable:
            raise HTTPException(503, "Store provider or capacity is not configured") from None

    def owner(conn, resource_id, principal):
        row = catalog.resource(conn, resource_id, lock=True)
        control.require_permission(principal, "manage", row["owner_project"])
        return row

    def audit(conn, principal, action, row):
        res = row if row.get("owner_project") else catalog.resource(conn, row["resource_id"])
        identity = row.get("resource_id") or row.get("grant_id")
        control.required_audit(control.actor_for(principal), "store." + action, "store-resource", str(identity),
            "succeeded", {"project": res["owner_project"]},
            {key: row[key] for key in ("state", "version", "grant_id", "mode", "consumer_project", "component") if key in row})

    @app.get("/v1/projects/{project}/store-context")
    def context(project: str, principal: Principal = caller):
        control.require_permission(principal, "view", project)
        with control.connect() as conn:
            admin = control.is_allowed(conn, principal, "manage", project)
            platform_admin = control.is_platform_admin(conn, principal)
            return reply({"project": project, "manage": admin, "platform_admin": platform_admin,
                "providers": providers.availability(),
                "limits": {"resources": 128, "grants_per_resource": 64, "concurrent_credential_leases": 512}})

    @app.get("/v1/projects/{project}/resources")
    def list_resources(project: str, principal: Principal = caller):
        control.require_permission(principal, "manage", project)
        with control.connect() as conn:
            rows = conn.execute("""SELECT row_to_json(r) FROM store_resources r
                WHERE owner_project=%s AND state<>'purged' ORDER BY created_at,resource_id LIMIT 128""", (project,)).fetchall()
        return reply({"resources": [r[0] for r in rows]})

    @app.post("/v1/projects/{project}/resources", status_code=202)
    def create_resource(project: str, body: ResourceCreate, principal: Principal = caller):
        control.require_permission(principal, "manage", project)
        with mutation(principal) as conn:
            providers.get(body.provider)
            providers.check_capacity(conn, body.provider, body.quota_bytes)
            count = conn.execute("SELECT count(*) FROM store_resources WHERE state<>'purged'").fetchone()[0]
            if count >= 128:
                raise catalog.Conflict("The operator's 128-resource allocation is full")
            row = catalog.create_resource(conn, project, body)
            audit(conn, principal, "create", row)
        return reply(row, 202)

    @app.get("/v1/resources/{resource_id}")
    def get_resource(resource_id: UUID, principal: Principal = caller):
        with mutation(principal) as conn:
            row = owner(conn, resource_id, principal)
            return reply({**row, "quota_enforcement": providers.get(row["provider"]).quota_enforcement})

    @app.patch("/v1/resources/{resource_id}")
    def rename_resource(resource_id: UUID, body: ResourceRename, principal: Principal = caller):
        with mutation(principal) as conn:
            row = owner(conn, resource_id, principal)
            catalog.assert_version(row, body.version)
            if row["state"] != "active":
                raise catalog.Conflict("Only active resources can be renamed")
            conn.execute("""UPDATE store_resources SET name=%s,version=version+1,updated_at=now()
                WHERE resource_id=%s""", (body.name, resource_id))
            row = catalog.resource(conn, resource_id)
            audit(conn, principal, "rename", row)
        return reply(row)

    @app.put("/v1/resources/{resource_id}/quota")
    def set_quota(resource_id: UUID, body: QuotaChange, principal: Principal = caller):
        control.require_platform_admin(principal)
        with mutation(principal) as conn:
            row = owner(conn, resource_id, principal)
            catalog.assert_version(row, body.version)
            if row["state"] != "active":
                raise catalog.Conflict("Only active resource quotas can change")
            providers.check_capacity(conn, row["provider"], body.quota_bytes, resource_id)
            conn.execute("""UPDATE store_resources SET quota_bytes=%s,version=version+1,
                observed_state='pending',updated_at=now() WHERE resource_id=%s""", (body.quota_bytes, resource_id))
            row = catalog.resource(conn, resource_id)
            audit(conn, principal, "quota", row)
        return reply(row, 202)

    @app.post("/v1/resources/{resource_id}/retirement", status_code=202)
    def retire_resource(resource_id: UUID, body: Version, principal: Principal = caller):
        with mutation(principal) as conn:
            row = catalog.retire(conn, owner(conn, resource_id, principal), body.version)
            audit(conn, principal, "retire", row)
        return reply(row, 202)

    @app.get("/v1/resources/{resource_id}/purge-preview")
    def purge_preview(resource_id: UUID, principal: Principal = caller):
        with mutation(principal) as conn:
            row = owner(conn, resource_id, principal)
            return reply({"resource_id": row["resource_id"], "owner_project": row["owner_project"],
                "name": row["name"], "provider": row["provider"], "state": row["state"],
                "observed_state": row["observed_state"], "version": row["version"],
                "effect": "Permanently delete this live resource; retained backups expire under their policy"})

    @app.post("/v1/resources/{resource_id}/purge", status_code=202)
    def purge_resource(resource_id: UUID, body: Purge, principal: Principal = caller):
        with mutation(principal) as conn:
            row = catalog.request_purge(conn, owner(conn, resource_id, principal), body)
            audit(conn, principal, "purge-request", row)
        return reply(row, 202)

    @app.get("/v1/resources/{resource_id}/grants")
    def list_grants(resource_id: UUID, principal: Principal = caller):
        with mutation(principal) as conn:
            owner(conn, resource_id, principal)
            rows = conn.execute("SELECT row_to_json(g) FROM store_grants g WHERE resource_id=%s ORDER BY created_at LIMIT 256", (resource_id,)).fetchall()
        return reply({"grants": [r[0] for r in rows]})

    @app.post("/v1/resources/{resource_id}/human-grants", status_code=202)
    def create_human_grant(resource_id: UUID, body: HumanGrant, principal: Principal = caller):
        with mutation(principal) as conn:
            row = catalog.create_human_grant(conn, owner(conn, resource_id, principal), body, principal.audit_id)
            audit(conn, principal, "human-grant", row)
        return reply(row, 202)

    @app.post("/v1/projects/{project}/resource-bindings", status_code=202)
    def request_binding(project: str, body: BindingRequest, principal: Principal = caller):
        control.require_permission(principal, "manage", project)
        with mutation(principal) as conn:
            row = catalog.request_binding(conn, project, body, principal.audit_id)
            audit(conn, principal, "binding-request", row)
        return reply(row, 202)

    @app.get("/v1/projects/{project}/resource-bindings")
    def list_bindings(project: str, principal: Principal = caller):
        control.require_permission(principal, "manage", project)
        with control.connect() as conn:
            rows = conn.execute("SELECT row_to_json(g) FROM store_grants g WHERE consumer_project=%s ORDER BY created_at LIMIT 256", (project,)).fetchall()
        return reply({"bindings": [r[0] for r in rows]})

    @app.post("/v1/resource-grants/{grant_id}/approval", status_code=202)
    def approve_binding(grant_id: UUID, body: Approval, principal: Principal = caller):
        with mutation(principal) as conn:
            row = catalog.grant(conn, grant_id, lock=True)
            owner(conn, row["resource_id"], principal)
            row = catalog.approve(conn, row, body, principal.audit_id)
            audit(conn, principal, "binding-approval", row)
        return reply(row, 202)

    @app.put("/v1/resource-grants/{grant_id}/mode", status_code=202)
    def change_mode(grant_id: UUID, body: GrantUpdate, principal: Principal = caller):
        with mutation(principal) as conn:
            row = catalog.grant(conn, grant_id, lock=True)
            res = owner(conn, row["resource_id"], principal)
            if (row["kind"] == "binding" and row["consumer_project"] != res["owner_project"]
                    and row["mode"] == "read-only" and body.mode == "read-write"):
                raise catalog.Conflict("Revoke and request a new cross-project binding for increased permissions")
            row = catalog.change_mode(conn, row, body, principal.audit_id)
            audit(conn, principal, "grant-mode", row)
        return reply(row, 202)

    @app.post("/v1/resource-grants/{grant_id}/revocation", status_code=202)
    def revoke_grant(grant_id: UUID, body: Version, principal: Principal = caller):
        with mutation(principal) as conn:
            row = catalog.grant(conn, grant_id, lock=True)
            # The owner can revoke every grant; a consumer admin can revoke its
            # own binding but never a human grant or another project's binding.
            res = catalog.resource(conn, row["resource_id"])
            project = row["consumer_project"] if row["kind"] == "binding" else res["owner_project"]
            with control.connect() as auth:
                owner_allowed = control.is_allowed(auth, principal, "manage", res["owner_project"])
            if not owner_allowed:
                control.require_permission(principal, "manage", project)
            row = catalog.revoke(conn, row, body.version)
            audit(conn, principal, "grant-revoke", row)
        return reply(row, 202)

    @app.put("/v1/store-access/me/key")
    def replace_key(body: PublicKey, principal: Principal = caller):
        from ..human_database_access import parse_public_key
        try:
            key, fingerprint = parse_public_key(body.public_key)
        except ValueError:
            raise HTTPException(422, "A valid Ed25519 public key is required") from None
        with mutation(principal) as conn:
            human(conn, principal)
            conn.execute("""UPDATE store_credentials c SET expires_at=now() FROM store_grants g
                WHERE c.grant_id=g.grant_id AND g.kind='human' AND g.issuer=%s AND g.subject=%s
                    AND c.state<>'revoked'""", (principal.issuer, principal.subject))
            conn.execute("""INSERT INTO store_human_keys(issuer,subject,public_key,fingerprint) VALUES(%s,%s,%s,%s)
                ON CONFLICT(issuer,subject) DO UPDATE SET public_key=excluded.public_key,fingerprint=excluded.fingerprint""",
                (principal.issuer, principal.subject, key, fingerprint))
            control.required_audit(control.actor_for(principal), "store.key-replace", "principal",
                principal.audit_id, "succeeded")
        return reply({"fingerprint": fingerprint})

    @app.get("/v1/store-access/me")
    def my_resources(principal: Principal = caller):
        with control.connect() as conn:
            human(conn, principal)
            rows = conn.execute("""SELECT row_to_json(g),row_to_json(r) FROM store_grants g
                JOIN store_resources r USING(resource_id) WHERE g.kind='human' AND g.issuer=%s
                AND g.subject=%s AND g.state='active' AND r.state='active' ORDER BY r.name LIMIT 256""",
                (principal.issuer, principal.subject)).fetchall()
            key = conn.execute("SELECT fingerprint FROM store_human_keys WHERE issuer=%s AND subject=%s",
                (principal.issuer, principal.subject)).fetchone()
        return reply({"key_fingerprint": key[0] if key else None,
            "grants": [{"grant": r[0], "resource": {**r[1], "console_url": providers.console_url(r[1]["provider"])}} for r in rows]})

    def own_human(conn, grant_id, principal):
        human(conn, principal)
        row = catalog.grant(conn, grant_id, lock=True)
        if row["kind"] != "human" or (row["issuer"], row["subject"]) != (principal.issuer, principal.subject):
            raise HTTPException(404, "Unknown human resource grant")
        return row

    @app.get("/v1/store-access/{grant_id}/credentials")
    def list_own_credentials(grant_id: UUID, principal: Principal = caller):
        with mutation(principal) as conn:
            own_human(conn, grant_id, principal)
            rows = conn.execute("""SELECT row_to_json(c) FROM store_credentials c WHERE grant_id=%s
                ORDER BY issued_at DESC LIMIT 24""", (grant_id,)).fetchall()
        return reply({"credentials": [row[0] for row in rows]})

    @app.post("/v1/store-access/{grant_id}/credentials", status_code=202)
    def issue_credential(grant_id: UUID, principal: Principal = caller):
        with mutation(principal) as conn:
            row = catalog.issue(conn, own_human(conn, grant_id, principal))
            control.required_audit(control.actor_for(principal), "store.credential-issue", "store-credential",
                row["credential_id"], "succeeded", detail={"grant_id": str(grant_id)})
        return reply(row, 202)

    @app.get("/v1/store-access/credentials/{credential_id}")
    def get_credential(credential_id: UUID, principal: Principal = caller):
        with mutation(principal) as conn:
            cred = catalog._object(conn, "store_credentials", "credential_id", credential_id)
            row = own_human(conn, cred["grant_id"], principal)
            res = catalog.resource(conn, row["resource_id"])
            catalog.active_project(conn, res["owner_project"])
            valid = conn.execute("""SELECT expires_at>now() FROM store_credentials
                WHERE credential_id=%s""", (credential_id,)).fetchone()[0]
            if (valid and cred["state"] == "issuing" and row["state"] == "active" and res["state"] == "active"
                    and cred["grant_version"] == row["version"]):
                return reply(cred, 202)
            if (not valid or cred["state"] != "active" or row["state"] != "active" or res["state"] != "active"
                    or cred["grant_version"] != row["version"]):
                raise HTTPException(409, "Credential is pending, expired, revoked or its grant changed")
            control.required_audit(control.actor_for(principal), "store.credential-reveal", "store-credential",
                str(credential_id), "succeeded", {"project": res["owner_project"]})
            connection = providers.connection(res, {**cred, 'kind': row['kind']})
            return reply({**cred, "provider": res["provider"], "connection": connection,
                "transport": "private SSH tunnel or isolated console; relay closes at credential expiry",
                **({"ssh": providers.ssh_connection(cred)} if os.environ.get("STORE_SSH_HOST") else {})})

    @app.post('/v1/store-access/credentials/{credential_id}/console')
    def launch_console(credential_id: UUID, principal: Principal = caller):
        with mutation(principal) as conn:
            cred = catalog._object(conn, 'store_credentials', 'credential_id', credential_id)
            own_human(conn, cred['grant_id'], principal)
            row = console.lease(conn, credential_id)
            if row is None:
                raise HTTPException(409, 'An active supported console lease is required')
            control.required_audit(control.actor_for(principal), 'store.console-launch', 'store-credential',
                str(credential_id), 'succeeded')
            return reply({'url': console.origin(row['relay_port']) + '/__platform/start',
                'launch': console.assertion(row, 'launch', 30)})
