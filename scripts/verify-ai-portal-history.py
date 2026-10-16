#!/usr/bin/env python3
"""Verify history pagination and revision guards in rollback-only PostgreSQL temp tables.

No model calls, live project changes, proposal execution or audit writes.
"""
import json
from uuid import uuid4
from app import ai_changes, ai_store, main


def verify():
    checks = []
    with main.connect() as conn:
        with conn.transaction(force_rollback=True):
            for table in ('ai_runs', 'ai_change_proposals'):
                conn.execute(f'CREATE TEMP TABLE {table} (LIKE public.{table} INCLUDING DEFAULTS INCLUDING INDEXES) ON COMMIT DROP')
            ids = [uuid4() for _ in range(31)]
            # Equal timestamps exercise the UUID tie breaker; foreign cursors must remain scoped.
            for index, run_id in enumerate(ids):
                conn.execute("""INSERT INTO pg_temp.ai_runs
                    (run_id,project,requester_issuer,requester_subject,kind,state,model,evidence,base_revision,created_at)
                    VALUES (%s,%s,'https://synthetic.invalid','human','investigate_incident',
                    'completed','synthetic:model','[{"id":"E1"}]',2,'2026-10-16T12:00:00Z')""",
                    (run_id, 'other' if index == 30 else 'synthetic'))
            first = ai_store.history(conn, 'synthetic', 20)
            second = ai_store.history(conn, 'synthetic', 20, first[19][0])
            assert len(first) == 21 and len(second) == 10
            assert len({r[0] for r in first[:20] + second}) == 30
            checks.append('run_keyset_equal_timestamps_no_gaps_or_duplicates')
            assert ai_store.history(conn, 'synthetic', 20, ids[30]) == []
            assert ai_store.history(conn, 'synthetic', 20, uuid4()) == []
            checks.append('foreign_and_missing_run_cursors_disclose_no_rows')
            for index, run_id in enumerate(ids):
                conn.execute("""INSERT INTO pg_temp.ai_change_proposals
                    (proposal_id,project,run_id,base_revision,target_revision,diff,diff_sha256,state,created_at)
                    VALUES (%s,%s,%s,2,1,'{}',%s,'proposed','2026-10-16T12:00:00Z')""",
                    (run_id, 'other' if index == 30 else 'synthetic', run_id, 'a' * 64))
            first = ai_changes.history(conn, 'synthetic', 20)
            second = ai_changes.history(conn, 'synthetic', 20, first[19][0])
            assert len(first) == 21 and len(second) == 10
            assert len({r[0] for r in first[:20] + second}) == 30
            assert ai_changes.history(conn, 'synthetic', 20, ids[30]) == []
            checks.append('proposal_keyset_pagination_and_foreign_cursor_denial')
            for label, kind, base in [('explanation', 'explain_application', 2),
                                      ('development', 'development_assistance', 2),
                                      ('stale', 'investigate_incident', 1),
                                      ('legacy_unbound', 'investigate_incident', None)]:
                conn.execute('UPDATE pg_temp.ai_runs SET kind=%s,base_revision=%s WHERE run_id=%s', (kind, base, ids[0]))
                try:
                    ai_changes.create(conn, 'synthetic', ids[0], 2)
                except ai_changes.ProposalUnavailable:
                    checks.append(f'{label}_run_proposal_denied')
                else:
                    raise AssertionError(label)
        for table in ('ai_runs', 'ai_change_proposals'):
            assert conn.execute('SELECT to_regclass(%s)', (f'pg_temp.{table}',)).fetchone()[0] is None
    return {'result': 'passed', 'checks': checks, 'cleanup': 'rolled-back'}


if __name__ == '__main__':
    print(json.dumps(verify()))
