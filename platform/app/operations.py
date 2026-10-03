"""Durable deployment-operation execution with restart recovery."""
import logging
import os
import threading
from typing import Any, Callable

from psycopg.types.json import Jsonb

from .audit import Actor, record_event
from .authorization import is_allowed
from .identity import Principal


LIFECYCLE_LOCK_ID = 731904
OPERATION_LOCK_SQL = "SELECT pg_try_advisory_lock(hashtextextended(%s, 0))"


def _audit_actor(issuer: str, subject: str) -> Actor:
    if issuer and subject:
        return Actor("oidc", issuer + "|" + subject)
    return Actor("worker", None)


def _finish_failed(conn, operation_id, actor: Actor, project: str, revision: int,
                   error_code: str, audit_result: str, mark_project_failed: bool,
                   log: logging.Logger) -> None:
    record_event(actor, "operation.execute", "operation", str(operation_id), audit_result,
                 {"project": project}, {"error_code": error_code},
                 revision=str(revision), operation_id=str(operation_id))
    with conn.transaction():
        if mark_project_failed:
            conn.execute("UPDATE projects SET status='failed',updated_at=now() WHERE name=%s", (project,))
        conn.execute("""UPDATE application_operations SET state='failed', result_version=1,
            result=%s, error_code=%s, updated_at=now(), completed_at=now()
            WHERE operation_id=%s""",
            (Jsonb({"error_code": error_code}), error_code, operation_id))
    log.error("Deployment operation failed operation_id=%s error_code=%s", operation_id, error_code)


def _execute_locked(conn, operation_id, password_for: Callable, provision_database: Callable,
                    apply: Callable, resources: Callable, publish_catalog: Callable,
                    log: logging.Logger) -> None:
    row = conn.execute("""SELECT o.operation_id, o.application_id, o.revision, o.operation_kind,
            o.state, o.envelope_version, o.envelope, o.actor_issuer, o.actor_subject,
            p.project_id, p.name, p.status
        FROM application_operations o
        JOIN project_applications a ON a.application_id=o.application_id
        JOIN project_environments e ON e.environment_id=a.environment_id
        JOIN projects p ON p.project_id=e.project_id
        WHERE o.operation_id=%s""", (operation_id,)).fetchone()
    if row is None or row[4] not in {"queued", "running"}:
        return

    (_, application_id, revision, operation_kind, _, envelope_version, envelope,
     actor_issuer, actor_subject, project_id, project, project_status) = row
    actor = _audit_actor(actor_issuer, actor_subject)
    conn.execute("""UPDATE application_operations SET state='running',
        attempt_count=attempt_count+1, started_at=COALESCE(started_at, now()), updated_at=now()
        WHERE operation_id=%s""", (operation_id,))

    desired = conn.execute("""SELECT revision, spec FROM application_revisions
        WHERE application_id=%s ORDER BY revision DESC LIMIT 1""", (application_id,)).fetchone()
    if desired is None or desired[0] != revision:
        _finish_failed(conn, operation_id, actor, project, revision,
                       "stale_revision", "rejected", False, log)
        return
    if not actor_issuer or not actor_subject or not is_allowed(
            conn, Principal(actor_issuer, actor_subject), "change", project):
        _finish_failed(conn, operation_id, actor, project, revision,
                       "authorization_revoked", "denied", True, log)
        return
    if project_status == "retired":
        _finish_failed(conn, operation_id, actor, project, revision,
                       "project_retired", "rejected", False, log)
        return
    expected_identity = {
        "project_id": str(project_id),
        "application_id": str(application_id),
        "project_slug": project,
        "revision": revision,
        "spec": desired[1],
    }
    if operation_kind != "deploy" or envelope_version != 1 or envelope != expected_identity:
        _finish_failed(conn, operation_id, actor, project, revision,
                       "invalid_operation_envelope", "rejected", True, log)
        return

    try:
        publish_catalog(conn)
        password = password_for(project)
        provision_database(conn, project, password)
        spec = desired[1]
        for manifest in resources(project, spec["image"], spec["port"],
                                 os.environ["APPS_DOMAIN"], os.environ["POSTGRES_IP"], password):
            apply(manifest)
    except Exception as exc:
        log.error("Deployment provider step failed operation_id=%s error_type=%s",
                  operation_id, type(exc).__name__)
        _finish_failed(conn, operation_id, actor, project, revision,
                       "provider_error", "failed", True, log)
        return

    result: dict[str, Any] = {
        "status": "applied",
        "project": project,
        "namespace": "project-" + project,
        "host": project + "." + os.environ["APPS_DOMAIN"],
    }
    record_event(actor, "operation.execute", "operation", str(operation_id), "succeeded",
                 {"project": project}, {"status": "applied"},
                 revision=str(revision), operation_id=str(operation_id))
    with conn.transaction():
        conn.execute("UPDATE projects SET status='applied',updated_at=now() WHERE name=%s", (project,))
        conn.execute("""UPDATE application_operations SET state='succeeded', result_version=1,
            result=%s, error_code=NULL, updated_at=now(), completed_at=now()
            WHERE operation_id=%s""", (Jsonb(result), operation_id))
    log.info("Deployment operation applied operation_id=%s project=%s revision=%s",
             operation_id, project, revision)


def process_one(connect: Callable, password_for: Callable, provision_database: Callable,
                apply: Callable, resources: Callable, publish_catalog: Callable,
                log: logging.Logger) -> bool:
    with connect() as conn:
        candidates = conn.execute("""SELECT operation_id FROM application_operations
            WHERE state IN ('queued', 'running') ORDER BY created_at LIMIT 100""").fetchall()
        for (operation_id,) in candidates:
            acquired = conn.execute(OPERATION_LOCK_SQL, (str(operation_id),)).fetchone()
            if not acquired or not acquired[0]:
                continue
            lifecycle_locked = False
            try:
                conn.execute("SELECT pg_advisory_lock(%s)", (LIFECYCLE_LOCK_ID,))
                lifecycle_locked = True
                _execute_locked(conn, operation_id, password_for, provision_database,
                                apply, resources, publish_catalog, log)
                return True
            finally:
                if lifecycle_locked:
                    conn.execute("SELECT pg_advisory_unlock(%s)", (LIFECYCLE_LOCK_ID,))
                conn.execute("SELECT pg_advisory_unlock(hashtextextended(%s, 0))",
                             (str(operation_id),))
    return False


def operation_loop(stop: threading.Event, connect: Callable, password_for: Callable,
                   provision_database: Callable, apply: Callable, resources: Callable,
                   publish_catalog: Callable, log: logging.Logger) -> None:
    while not stop.is_set():
        try:
            processed = process_one(connect, password_for, provision_database,
                                    apply, resources, publish_catalog, log)
        except Exception as exc:
            log.error("Operation worker iteration failed error_type=%s", type(exc).__name__)
            processed = False
        if not processed:
            stop.wait(2)
