#!/usr/bin/env python3
"""Exercise deployed approval SQL using rollback-only temporary tables.

Run inside the Platform API environment. No model requests, live proposals,
audit records, project revisions or workloads are written.
"""
import json
from uuid import uuid4

from app import ai_changes, ai_store, main
from app.identity import Principal


def verify():
    checks = []
    principal = Principal("https://synthetic.invalid", "synthetic-human")
    proposal, run = uuid4(), uuid4()
    digest = "a" * 64

    def rejected(name, action):
        try:
            action()
        except ai_changes.ProposalUnavailable:
            checks.append(name)
        else:
            raise AssertionError(name)

    with main.connect() as conn:
        with conn.transaction(force_rollback=True):
            conn.execute("""CREATE TEMP TABLE ai_change_proposals
                (LIKE public.ai_change_proposals INCLUDING DEFAULTS) ON COMMIT DROP""")
            conn.execute("""INSERT INTO pg_temp.ai_change_proposals
                (proposal_id,project,run_id,base_revision,target_revision,diff,diff_sha256,state)
                VALUES (%s,'synthetic-ai-guard',%s,2,1,'{}',%s,'proposed')""", (proposal, run, digest))
            rejected("unapproved_execution", lambda: ai_changes.approved_for_execution(
                conn, "synthetic-ai-guard", proposal, digest))
            rejected("changed_hash_approval", lambda: ai_changes.approve(
                conn, "synthetic-ai-guard", proposal, "b" * 64, principal))
            ai_changes.approve(conn, "synthetic-ai-guard", proposal, digest, principal)
            row = ai_changes.approved_for_execution(conn, "synthetic-ai-guard", proposal, digest)
            assert row[6] == "approved"
            checks.append("exact_hash_approved")
            rejected("foreign_project", lambda: ai_changes.approved_for_execution(
                conn, "foreign-project", proposal, digest))
            rejected("changed_hash_execution", lambda: ai_changes.approved_for_execution(
                conn, "synthetic-ai-guard", proposal, "b" * 64))
            conn.execute("UPDATE pg_temp.ai_change_proposals SET expires_at=now()-interval '1 second'")
            rejected("expired_execution", lambda: ai_changes.approved_for_execution(
                conn, "synthetic-ai-guard", proposal, digest))
            conn.execute("UPDATE pg_temp.ai_change_proposals SET expires_at=now()+interval '15 minutes'")
            ai_changes.consume(conn, "synthetic-ai-guard", proposal, uuid4(), 3)
            rejected("reused_execution", lambda: ai_changes.approved_for_execution(
                conn, "synthetic-ai-guard", proposal, digest))
            rejected("reapproval_after_execution", lambda: ai_changes.approve(
                conn, "synthetic-ai-guard", proposal, digest, principal))
            conn.execute("CREATE TEMP TABLE ai_runs (LIKE public.ai_runs INCLUDING DEFAULTS) ON COMMIT DROP")
            conn.execute("""INSERT INTO pg_temp.ai_runs
                (run_id,project,requester_issuer,requester_subject,kind,state,result)
                VALUES (%s,'synthetic-ai-guard','https://synthetic.invalid','synthetic-human',
                        'explain_application','completed','{}')""", (run,))
            assert ai_store.get_run(conn, "synthetic-ai-guard", run) is not None
            assert ai_store.get_run(conn, "foreign-project", run) is None
            checks.append("foreign_run_read")
        assert conn.execute("SELECT to_regclass('pg_temp.ai_change_proposals')").fetchone()[0] is None
        assert conn.execute("SELECT to_regclass('pg_temp.ai_runs')").fetchone()[0] is None
    return {"passed": checks, "temporary_table_rolled_back": True, "live_proposals_written": False}


if __name__ == "__main__":
    print(json.dumps(verify()))
