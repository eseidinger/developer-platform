"""Restartable lifecycle worker; project fences outlive disconnected HTTP requests."""

from fastapi import HTTPException
from psycopg.types.json import Jsonb

from ..identity import Principal
from . import catalog
from .restore import restore

WORKER_LOCK = 731925


def retire(conn, control, operation):
    name = operation["project"]
    current = control.current_retirement_scope(conn, name)
    if current is None:
        raise HTTPException(409, "Retirement scope is unavailable")
    access = control.retirement_access_inventory(conn, name)
    token = control.retirement_scope_token(name, current["revision"], access)
    result = control.retire(
        name,
        control.Retirement(confirm_name=name, scope_token=token),
        Principal(**operation["actor"]),
    )
    if getattr(result, "status_code", 200) != 200:
        return False
    pending = conn.execute(
        """SELECT EXISTS(SELECT 1 FROM deployment_credentials WHERE project=%s AND status<>'revoked')
        OR EXISTS(SELECT 1 FROM hosted_access_resources WHERE (project=%s OR spec->>'providerProject'=%s)
        AND kind IN ('group','policy','membership','service-access') AND state<>'revoked')
        OR EXISTS(SELECT 1 FROM store_credentials c JOIN store_grants g USING(grant_id)
        JOIN store_resources r USING(resource_id) WHERE (r.owner_project=%s OR g.consumer_project=%s) AND c.state<>'revoked')""",
        (name, name, name, name, name),
    ).fetchone()
    return not pending[0]


def process_one(control):
    with control.connect() as conn:
        if not conn.execute(
            "SELECT pg_try_advisory_lock(%s)", (WORKER_LOCK,)
        ).fetchone()[0]:
            return False
        try:
            catalog.expire_receipts(conn)
            selected = conn.execute("""SELECT operation_id::text,project_id::text,project,action,actor,result,step FROM project_lifecycle_operations
                WHERE state IN ('queued','running','blocked') ORDER BY updated_at LIMIT 1""").fetchone()
            if not selected:
                return False
            operation = dict(
                zip(
                    (
                        "operation_id",
                        "project_id",
                        "project",
                        "action",
                        "actor",
                        "result",
                        "step",
                    ),
                    selected,
                )
            )
            # Every external action is preceded by checking the immutable identity.
            project = conn.execute(
                "SELECT project_id::text FROM projects WHERE name=%s",
                (operation["project"],),
            ).fetchone()
            if not project or project[0] != operation["project_id"]:
                # A purge may have removed the catalog just before process exit.
                if (
                    operation["action"] == "purge"
                    and operation["step"] == "catalog_removed"
                ):
                    from .erasure import verified_receipt

                    complete = verified_receipt(operation, final=True)
                else:
                    raise HTTPException(409, "Project identity no longer matches")
            else:
                conn.execute(
                    "UPDATE project_lifecycle_operations SET state='running',error_code=NULL,updated_at=now() WHERE operation_id=%s",
                    (operation["operation_id"],),
                )
                if operation["action"] == "retire":
                    complete = retire(conn, control, operation)
                elif operation["action"] == "restore":
                    with conn.transaction():
                        conn.execute("SELECT pg_advisory_xact_lock(731904)")
                        complete = restore(conn, control, operation)
                else:
                    from .purge import purge

                    complete = purge(conn, control, operation)
            if not complete:
                conn.execute(
                    "UPDATE project_lifecycle_operations SET updated_at=now() WHERE operation_id=%s",
                    (operation["operation_id"],),
                )
            if complete:
                with conn.transaction():
                    if operation["action"] == "purge":
                        conn.execute(
                            "UPDATE project_lifecycle_operations SET result=result || %s WHERE operation_id=%s",
                            (
                                Jsonb({"backups_removed": True}),
                                operation["operation_id"],
                            ),
                        )
                    conn.execute(
                        "UPDATE project_lifecycle_operations SET state='succeeded',error_code=NULL,completed_at=now(),updated_at=now() WHERE operation_id=%s",
                        (operation["operation_id"],),
                    )
                    if operation["action"] == "restore":
                        conn.execute(
                            "DELETE FROM project_recovery_points WHERE project_id=%s",
                            (operation["project_id"],),
                        )
            return True
        except Exception as exc:  # noqa: BLE001 - Provider failures must leave durable, retryable work.
            # Provider errors can contain connection strings and secrets. Persist
            # only the error class; the current step is enough for safe retry.
            if "operation" in locals():
                code = type(exc).__name__
                conn.execute(
                    "UPDATE project_lifecycle_operations SET state='blocked',error_code=%s,updated_at=now() WHERE operation_id=%s",
                    (code, operation["operation_id"]),
                )
                control.log.warning(
                    "Lifecycle operation waiting operation_id=%s reason=%s",
                    operation["operation_id"],
                    code,
                )
            return False
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", (WORKER_LOCK,))


def loop(stop, control):
    while not stop.is_set():
        try:
            process_one(control)
        except Exception as exc:  # noqa: BLE001 - Provider failures must leave durable, retryable work.
            control.log.warning(
                "Lifecycle worker unavailable reason=%s", type(exc).__name__
            )
        stop.wait(3)
