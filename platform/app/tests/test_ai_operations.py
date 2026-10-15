import json
import os
import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage
from langchain_core.tools import StructuredTool

from app import ai_agent, ai_changes, ai_evaluation, ai_model, ai_tools


class _Bound:
    def __init__(self, replies):
        self.replies = iter(replies)

    def invoke(self, messages):
        return next(self.replies)


class _Model:
    name = "test:fixture"

    def __init__(self, replies):
        self.replies = replies
        self.bound_names = []

    def bind_tools(self, tools):
        self.bound_names = [tool.name for tool in tools]
        return _Bound(self.replies)


class _Query:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class _ApprovalConnection:
    def __init__(self, row, valid=True):
        self.row = row
        self.valid = valid

    def execute(self, statement, params):
        if "expires_at>now()" in statement:
            return _Query((self.valid,))
        return _Query(self.row)


def _answer(summary, references, insufficient=False):
    return AIMessage(content=json.dumps({"summary": summary, "hypotheses": [
        {"statement": "Deployment is unavailable", "source_ids": references}],
        "gaps": [], "insufficient_evidence": insufficient}))


class AIOperationsTests(unittest.TestCase):
    def test_model_fails_closed_without_verified_terms(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key",
             "OPENAI_EU_PROJECT_VERIFIED": "true", "OPENAI_EU_PROCESSING_VERIFIED": "true"}, clear=True):
            with self.assertRaises(ai_model.ModelUnavailable):
                ai_model.configured_model()

    def test_tool_call_cites_only_scoped_evidence(self):
        tool = StructuredTool.from_function(func=lambda: {"source": "project-catalog", "state": "applied"},
                                            name="get_application", description="Read current project")
        model = _Model([AIMessage(content="", tool_calls=[{
            "name": "get_application", "args": {}, "id": "call-1"}]),
            _answer("Application deployment is unavailable", ["E1"])])
        outcome = ai_agent.run("explain_application", "run-1", model, [tool])
        self.assertEqual(outcome["state"], "completed")
        self.assertEqual(outcome["tool_calls"], 1)
        self.assertEqual(outcome["evidence"][0]["source"], "project-catalog")

    def test_missing_or_foreign_citation_abstains(self):
        model = _Model([_answer("certain root cause", ["foreign-source"])])
        outcome = ai_agent.run("investigate_incident", "run-2", model, [])
        self.assertEqual(outcome["state"], "abstained")
        self.assertEqual(outcome["result"]["hypotheses"], [])

    def test_unknown_tool_cannot_execute(self):
        model = _Model([AIMessage(content="", tool_calls=[{
            "name": "deploy", "args": {}, "id": "call-1"}])])
        outcome = ai_agent.run("investigate_incident", "run-3", model, [])
        self.assertEqual(outcome["state"], "abstained")
        self.assertEqual(outcome["tool_calls"], 0)

    def test_extra_project_argument_is_rejected_before_tool_execution(self):
        calls = []
        def read() -> dict:
            calls.append(1)
            return {"state": "ok"}
        tool = StructuredTool.from_function(func=read, name="get_application", description="Read")
        model = _Model([AIMessage(content="", tool_calls=[{
            "name": "get_application", "args": {"project": "foreign"}, "id": "call-1"}])])
        outcome = ai_agent.run("investigate_incident", "run-4", model, [tool])
        self.assertEqual(outcome["state"], "abstained")
        self.assertEqual(calls, [])

    def test_application_view_omits_configuration_and_images(self):
        view = ai_tools.application_view((2, {"configuration": {"PASSWORD": "secret"},
            "components": [{"name": "api", "type": "service", "image": "private.example/image"}]}, "applied"))
        self.assertEqual(view["revision"], 2)
        self.assertNotIn("secret", str(view))
        self.assertNotIn("private.example", str(view))

    def test_canonical_rollback_diff_is_value_free_and_revision_bound(self):
        before = {"components": [{"image": "private.example/old"}],
                  "configuration": {"PASSWORD": "old-secret"}}
        after = {"components": [{"image": "private.example/new"}],
                 "configuration": {"PASSWORD": "new-secret"}}
        diff, digest = ai_changes.canonical_diff("shop", 5, 3, after, before)
        self.assertEqual(diff["changed_paths"], ["/components", "/configuration"])
        self.assertEqual(len(digest), 64)
        self.assertNotIn("secret", str(diff))
        self.assertNotEqual(digest, ai_changes.canonical_diff("shop", 6, 3, after, before)[1])

    def test_read_tools_do_not_accept_project_argument(self):
        seen = []
        def current(project):
            seen.append(project)
            return (2, {"configuration": {"TOKEN": "secret"},
                        "components": [{"name": "api", "type": "service"}]}, "applied")
        tools = {tool.name: tool for tool in ai_tools.make_tools("shop", current, None)}
        result = tools["get_application"].invoke({})
        self.assertEqual(seen, ["shop"])
        self.assertNotIn("secret", str(result))
        self.assertNotIn("project", tools["get_application"].args)
        self.assertNotIn("project", tools["get_metrics"].args)

    def test_approval_requires_exact_unused_hash_and_current_expiry(self):
        row = ("proposal", "run", 5, 3, {}, "a" * 64, "approved",
               None, None, None, None, None)
        self.assertEqual(ai_changes.approved_for_execution(
            _ApprovalConnection(row), "shop", "proposal", "a" * 64), row)
        for connection, digest in [(_ApprovalConnection(row), "b" * 64),
                                   (_ApprovalConnection((*row[:6], "executed", *row[7:])), "a" * 64),
                                   (_ApprovalConnection(row, False), "a" * 64)]:
            with self.assertRaises(ai_changes.ProposalUnavailable):
                ai_changes.approved_for_execution(connection, "shop", "proposal", digest)

    def test_runtime_tool_restricts_provider_reason_and_image(self):
        current = lambda project: (3, {"components": [{"name": "api", "type": "service",
            "image": "private.example/app", "resolved_image": "private.example/app@sha256:abc"}]}, "applied")
        with patch.object(ai_tools, "observe_deployment", return_value={
                "state": "failed", "reason": "password=secret", "desired_replicas": 1,
                "ready_replicas": 0, "observed_at": "2026-10-15T20:00:00Z"}):
            tools = {tool.name: tool for tool in ai_tools.make_tools("shop", current, None)}
            observed = tools["get_runtime_status"].invoke({})
        self.assertEqual(observed["reason"], "OtherRuntimeReason")
        self.assertNotIn("secret", str(observed))
        self.assertNotIn("private.example", str(observed))

    def test_evaluation_scoring_requires_sourced_diagnosis_and_abstention(self):
        known = ai_evaluation.CASES[0]
        outcome = {"result": {"hypotheses": [{"statement": "Database host is suspect",
                    "source_ids": ["E1"]}], "insufficient_evidence": False},
                   "tool_calls": 2, "estimated_cost_usd": 0.01}
        self.assertTrue(ai_evaluation.score(known, outcome)["passed"])
        outcome["result"]["hypotheses"][0]["source_ids"] = []
        self.assertFalse(ai_evaluation.score(known, outcome)["passed"])
        unknown = ai_evaluation.CASES[3]
        outcome["result"] = {"hypotheses": [], "insufficient_evidence": True}
        self.assertTrue(ai_evaluation.score(unknown, outcome)["passed"])


if __name__ == "__main__":
    unittest.main()
