"""Portal history boundaries and trusted revision binding."""

import unittest
from contextlib import ExitStack
from unittest.mock import Mock, patch
from uuid import uuid4

from app.identity import Principal
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import ai_changes, ai_store, main

HUMAN = Principal("https://issuer.example", "human")


class PortalTests(unittest.TestCase):
    def test_proposals_require_current_bound_completed_investigations(self):
        for row in [
            None,
            ("abstained", ["E1"], "investigate_incident", 2),
            ("completed", [], "investigate_incident", 2),
            ("completed", ["E1"], "explain_application", 2),
            ("completed", ["E1"], "development_assistance", 2),
            ("completed", ["E1"], "investigate_incident", None),
            ("completed", ["E1"], "investigate_incident", 1),
        ]:
            with (
                self.subTest(row=row),
                patch.object(ai_changes, "candidate") as candidate,
            ):
                conn = Mock()
                conn.execute.return_value.fetchone.return_value = row
                with self.assertRaises(ai_changes.ProposalUnavailable):
                    ai_changes.create(conn, "demo", uuid4(), 2)
                candidate.assert_not_called()

    def test_valid_investigation_and_duplicate_proposal(self):
        for inserted in [(uuid4(),), None]:
            conn = Mock()
            conn.execute.return_value.fetchone.side_effect = [
                ("completed", ["E1"], "investigate_incident", 2),
                inserted,
            ]
            with patch.object(
                ai_changes,
                "candidate",
                return_value=(1, {"image": "bad"}, {"image": "good"}),
            ):
                if inserted:
                    self.assertEqual(
                        ai_changes.create(conn, "demo", uuid4(), 2)[1]["base_revision"],
                        2,
                    )
                else:
                    with self.assertRaises(ai_changes.ProposalUnavailable):
                        ai_changes.create(conn, "demo", uuid4(), 2)

    def test_history_sql_scopes_cursor_and_bounded_rows(self):
        for module, table in [
            (ai_store, "ai_runs"),
            (ai_changes, "ai_change_proposals"),
        ]:
            conn = Mock()
            cursor = uuid4()
            module.history(conn, "demo", 20, cursor)
            sql, args = conn.execute.call_args.args
            self.assertIn(table, sql)
            self.assertEqual(sql.count("project=%s"), 2)
            self.assertIn("ORDER BY created_at DESC", sql)
            self.assertEqual(args, ("demo", cursor, "demo", cursor, 21))

    def test_stale_run_reconciliation_is_scoped_and_keeps_new_runs_running(self):
        conn = Mock()
        ai_store.fail_interrupted_runs(conn, "demo")
        statement, params = conn.execute.call_args.args
        self.assertIn("project=%s AND state='running'", statement)
        self.assertIn("created_at < now()", statement)
        self.assertIn("state='failed'", statement)
        self.assertEqual(params[1:], ("demo", ai_store.STALE_RUN_MINUTES))
        self.assertTrue(params[0].obj["insufficient_evidence"])

    def test_context_distinguishes_policy_admin_project_manager_and_automation(self):
        for scope, manager, admin in [
            (None, False, False),
            (None, True, False),
            (None, True, True),
            ({"automation": True}, True, True),
        ]:
            with (
                self.subTest(scope=scope, manager=manager, admin=admin),
                ExitStack() as stack,
            ):
                stack.enter_context(patch.object(main, "require_permission"))
                stack.enter_context(patch.object(main, "connect"))
                stack.enter_context(
                    patch.object(main, "access_scope", return_value=scope)
                )
                stack.enter_context(
                    patch.object(main, "is_allowed", return_value=manager)
                )
                stack.enter_context(
                    patch.object(main, "is_platform_admin", return_value=admin)
                )
                stack.enter_context(
                    patch.object(main, "current_spec", return_value=(3, {}, "applied"))
                )
                stack.enter_context(
                    patch.object(ai_store, "classification", return_value="internal")
                )
                context = main.ai_context("demo", HUMAN)
                self.assertEqual(
                    context["permissions"],
                    {
                        "run": scope is None,
                        "manage": scope is None and manager,
                        "edit_policy": scope is None and admin,
                    },
                )
                self.assertEqual(context["current_revision"], 3)

    def test_pagination_validation_and_denied_reads(self):
        main.app.dependency_overrides[main.current_principal] = lambda: HUMAN
        try:
            client = TestClient(main.app)
            with (
                patch.object(
                    main, "require_permission", side_effect=HTTPException(403, "Denied")
                ),
                patch.object(ai_store, "history") as history,
                patch.object(ai_changes, "history") as proposals,
            ):
                for suffix in ("runs", "proposals", "context"):
                    self.assertEqual(
                        client.get(f"/projects/demo/ai/{suffix}").status_code, 403
                    )
                for query in ("limit=0", "limit=51", "before=invalid"):
                    self.assertEqual(
                        client.get(f"/projects/demo/ai/runs?{query}").status_code, 422
                    )
                history.assert_not_called()
                proposals.assert_not_called()
        finally:
            main.app.dependency_overrides.clear()

    def test_run_history_is_summary_only_and_next_cursor_is_last_visible(self):
        ids = [uuid4() for _ in range(3)]
        rows = [
            (
                i,
                "investigate_incident",
                "completed",
                "model",
                4,
                0.01,
                "date",
                "date",
                2,
            )
            for i in ids
        ]
        with (
            patch.object(main, "require_permission"),
            patch.object(main, "connect"),
            patch.object(ai_store, "history", return_value=rows),
            patch.object(ai_store, "fail_interrupted_runs") as reconcile,
        ):
            result = main.list_ai_runs("demo", 2, None, HUMAN)
        reconcile.assert_called_once()
        self.assertEqual(reconcile.call_args.args[1], "demo")
        self.assertEqual(result["next_cursor"], str(ids[1]))
        self.assertEqual(len(result["items"]), 2)
        self.assertNotIn("result", result["items"][0])
        self.assertNotIn("evidence", result["items"][0])
