"""Narrow, deterministic rollback proposals and single-use approvals."""

import hashlib
import json
from uuid import uuid4

from psycopg.types.json import Jsonb


class ProposalUnavailable(Exception):
    pass


def initialize(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS ai_change_proposals (
        proposal_id UUID PRIMARY KEY, project TEXT NOT NULL REFERENCES projects(name),
        run_id UUID NOT NULL REFERENCES ai_runs(run_id),
        base_revision BIGINT NOT NULL, target_revision BIGINT NOT NULL,
        diff JSONB NOT NULL, diff_sha256 TEXT NOT NULL,
        state TEXT NOT NULL CHECK (state IN ('proposed','approved','executed')),
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        approved_at TIMESTAMPTZ, expires_at TIMESTAMPTZ,
        approver_issuer TEXT, approver_subject TEXT,
        operation_id UUID, resulting_revision BIGINT,
        UNIQUE (run_id))""")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS ai_proposals_history_idx ON ai_change_proposals(project,created_at DESC,proposal_id DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS ai_change_proposals_project_idx ON ai_change_proposals(project,created_at DESC)"
    )


def canonical_diff(project, base, target, base_spec, target_spec):
    # A reviewable structural diff without configuration or secret values.
    paths = sorted(
        "/" + key
        for key in set(base_spec) | set(target_spec)
        if base_spec.get(key) != target_spec.get(key)
    )
    diff = {
        "action": "rollback",
        "project": project,
        "base_revision": base,
        "target_revision": target,
        "changed_paths": paths,
    }
    digest = hashlib.sha256(
        json.dumps(diff, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return diff, digest


def candidate(conn, project, base_revision, runtime_failed=None):
    row = conn.execute(
        """SELECT o.revision,o.state FROM application_operations o
        JOIN project_applications a ON a.application_id=o.application_id
        JOIN project_environments e ON e.environment_id=a.environment_id
        JOIN projects p ON p.project_id=e.project_id
        WHERE p.name=%s ORDER BY o.created_at DESC LIMIT 1""",
        (project,),
    ).fetchone()
    if not row or row[0] != base_revision:
        raise ProposalUnavailable("Latest deployment revision changed")
    if row[1] != "failed" and not (
        row[1] == "succeeded"
        and runtime_failed is not None
        and runtime_failed() is True
    ):
        raise ProposalUnavailable(
            "Latest revision has neither a failed apply nor a confirmed runtime failure"
        )
    target = conn.execute(
        """SELECT o.revision,r.spec FROM application_operations o
        JOIN project_applications a ON a.application_id=o.application_id
        JOIN project_environments e ON e.environment_id=a.environment_id
        JOIN projects p ON p.project_id=e.project_id
        JOIN application_revisions r ON r.application_id=o.application_id AND r.revision=o.revision
        WHERE p.name=%s AND o.state='succeeded' AND o.revision<%s
        ORDER BY o.completed_at DESC LIMIT 1""",
        (project, base_revision),
    ).fetchone()
    if not target:
        raise ProposalUnavailable("No successful retained revision is available")
    current = conn.execute(
        """SELECT r.spec FROM application_revisions r
        JOIN project_applications a ON a.application_id=r.application_id
        JOIN project_environments e ON e.environment_id=a.environment_id
        JOIN projects p ON p.project_id=e.project_id
        WHERE p.name=%s AND r.revision=%s""",
        (project, base_revision),
    ).fetchone()
    if not current:
        raise ProposalUnavailable("Base revision was pruned")
    return target[0], current[0], target[1]


def create(conn, project, run_id, base_revision, runtime_failed=None):
    run = conn.execute(
        "SELECT state,evidence,kind,base_revision FROM ai_runs WHERE project=%s AND run_id=%s",
        (project, run_id),
    ).fetchone()
    if (
        not run
        or run[0] != "completed"
        or not run[1]
        or run[2] != "investigate_incident"
        or run[3] != base_revision
    ):
        raise ProposalUnavailable(
            "A completed sourced investigation bound to the current revision is required"
        )
    target, base_spec, target_spec = candidate(
        conn, project, base_revision, runtime_failed
    )
    diff, digest = canonical_diff(
        project, base_revision, target, base_spec, target_spec
    )
    proposal_id = uuid4()
    inserted = conn.execute(
        """INSERT INTO ai_change_proposals
        (proposal_id,project,run_id,base_revision,target_revision,diff,diff_sha256,state)
        VALUES (%s,%s,%s,%s,%s,%s,%s,'proposed') ON CONFLICT (run_id) DO NOTHING RETURNING proposal_id""",
        (proposal_id, project, run_id, base_revision, target, Jsonb(diff), digest),
    ).fetchone()
    if not inserted:
        raise ProposalUnavailable(
            "An existing proposal already uses this investigation; inspect proposal history"
        )
    return proposal_id, diff, digest


def get(conn, project, proposal_id, *, lock=False):
    suffix = " FOR UPDATE" if lock else ""
    return conn.execute(
        """SELECT proposal_id,run_id,base_revision,target_revision,diff,diff_sha256,
        state,created_at,approved_at,expires_at,operation_id,resulting_revision
        FROM ai_change_proposals WHERE project=%s AND proposal_id=%s"""
        + suffix,
        (project, proposal_id),
    ).fetchone()


def approve(conn, project, proposal_id, digest, principal):
    row = get(conn, project, proposal_id, lock=True)
    if not row or row[6] != "proposed" or row[5] != digest:
        raise ProposalUnavailable("Proposal is unavailable or its diff changed")
    conn.execute(
        """UPDATE ai_change_proposals SET state='approved',approved_at=now(),
        expires_at=now()+interval '15 minutes',approver_issuer=%s,approver_subject=%s
        WHERE project=%s AND proposal_id=%s""",
        (principal.issuer, principal.subject, project, proposal_id),
    )
    return row


def approved_for_execution(conn, project, proposal_id, digest):
    row = get(conn, project, proposal_id, lock=True)
    if not row or row[6] != "approved" or row[5] != digest:
        raise ProposalUnavailable("Approval is missing, used or changed")
    valid = conn.execute(
        "SELECT expires_at>now() FROM ai_change_proposals WHERE proposal_id=%s",
        (proposal_id,),
    ).fetchone()[0]
    if not valid:
        raise ProposalUnavailable("Approval has expired")
    return row


def consume(conn, project, proposal_id, operation_id, revision):
    conn.execute(
        """UPDATE ai_change_proposals SET state='executed',operation_id=%s,
        resulting_revision=%s WHERE project=%s AND proposal_id=%s AND state='approved'""",
        (operation_id, revision, project, proposal_id),
    )


def history(conn, project, limit, before=None):
    return conn.execute(
        """SELECT proposal_id,run_id,base_revision,target_revision,diff,diff_sha256,
        state,created_at,approved_at,expires_at,operation_id,resulting_revision
        FROM ai_change_proposals WHERE project=%s AND (%s::uuid IS NULL OR (created_at,proposal_id)<(
            SELECT created_at,proposal_id FROM ai_change_proposals WHERE project=%s AND proposal_id=%s))
        ORDER BY created_at DESC,proposal_id DESC LIMIT %s""",
        (project, before, project, before, limit + 1),
    ).fetchall()
