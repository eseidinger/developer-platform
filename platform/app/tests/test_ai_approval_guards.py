"""Rejected approval/execution requests must never queue or consume a change."""

import unittest
from contextlib import ExitStack
from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.identity import Principal
from fastapi import HTTPException

from app import main


class ApprovalEndpointGuardTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.principal = Principal("https://issuer.example", "human")
        self.proposal = uuid4()
        self.body = main.AIApprovalRequest(diff_sha256="a" * 64)
        self.conn = MagicMock()
        self.conn.__enter__.return_value = self.conn
        self.stack.enter_context(patch.object(main, "connect", return_value=self.conn))
        self.permission = self.stack.enter_context(
            patch.object(main, "require_permission")
        )
        self.scope = self.stack.enter_context(
            patch.object(main, "access_scope", return_value=None)
        )
        self.allowed = self.stack.enter_context(
            patch.object(main, "is_allowed", return_value=True)
        )
        self.queue = self.stack.enter_context(patch.object(main, "queue_deploy"))
        self.consume = self.stack.enter_context(
            patch.object(main.ai_changes, "consume")
        )
        self.audit = self.stack.enter_context(patch.object(main, "required_audit"))

    def execute(self):
        return main.execute_ai_proposal("lab", self.proposal, self.body, self.principal)

    def assert_rejected_without_write(self, status):
        with self.assertRaises(HTTPException) as error:
            self.execute()
        self.assertEqual(error.exception.status_code, status)
        self.queue.assert_not_called()
        self.consume.assert_not_called()

    def test_initial_project_permission_denial_stops_before_database(self):
        self.permission.side_effect = HTTPException(403, "Denied")
        self.assert_rejected_without_write(403)
        self.conn.__enter__.assert_not_called()

    def test_automation_cannot_approve_or_execute(self):
        self.scope.return_value = {"kind": "automation"}
        self.assert_rejected_without_write(403)
        with patch.object(main.ai_changes, "approve") as approve:
            with self.assertRaises(HTTPException) as error:
                main.approve_ai_proposal(
                    "lab", self.proposal, self.body, self.principal
                )
            self.assertEqual(error.exception.status_code, 403)
            approve.assert_not_called()

    def test_permission_is_rechecked_inside_transaction(self):
        self.allowed.return_value = False
        self.assert_rejected_without_write(403)
        self.conn.transaction.assert_called_once()
        self.allowed.assert_called_once_with(self.conn, self.principal, "manage", "lab")

    def test_unavailable_approval_rejected_and_audited_before_queue(self):
        with patch.object(
            main.ai_changes,
            "approved_for_execution",
            side_effect=main.ai_changes.ProposalUnavailable("Unavailable"),
        ):
            self.assert_rejected_without_write(409)
        self.assertEqual(self.audit.call_args.args[4], "rejected")

    def test_stale_base_revision_does_not_consume_approval(self):
        row = (self.proposal, uuid4(), 2, 1)
        with patch.object(main.ai_changes, "approved_for_execution", return_value=row):
            self.queue.side_effect = main.RevisionConflict(3)
            with self.assertRaises(HTTPException) as error:
                self.execute()
        self.assertEqual(error.exception.status_code, 409)
        self.queue.assert_called_once_with(
            self.conn, self.principal, "lab", None, 2, target=1
        )
        self.consume.assert_not_called()
        self.assertEqual(self.audit.call_args.args[4], "rejected")

    def test_queue_rejects_stale_revision_before_any_mutation(self):
        # Exercise the real queue function's revision check, not the endpoint mock.
        self.stack.close()
        connection = MagicMock()
        connection.execute.return_value.fetchone.return_value = (3,)
        with self.assertRaises(main.RevisionConflict):
            main.queue_deploy(connection, self.principal, "lab", None, 2, target=1)
        statements = [call.args[0] for call in connection.execute.call_args_list]
        self.assertFalse(
            any(
                word in statement
                for statement in statements
                for word in ("INSERT ", "UPDATE ", "DELETE ")
            )
        )
        self.assertIn("pg_advisory_unlock", statements[-1])

    def test_approval_changed_hash_rejection_is_audited(self):
        with (
            patch.object(
                main.ai_changes,
                "approve",
                side_effect=main.ai_changes.ProposalUnavailable("Diff changed"),
            ),
            self.assertRaises(HTTPException) as error,
        ):
            main.approve_ai_proposal("lab", self.proposal, self.body, self.principal)
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(self.audit.call_args.args[4], "rejected")
        self.queue.assert_not_called()
