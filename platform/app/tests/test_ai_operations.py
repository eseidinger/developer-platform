import json
import os
import unittest
from unittest.mock import patch, MagicMock

from langchain_core.messages import AIMessage
from langchain_core.tools import StructuredTool

from app import ai_agent, ai_changes, ai_evaluation, ai_model, ai_tools, authorization


class _Bound:
    def __init__(self, replies):
        self.replies = iter(replies)

    def invoke(self, messages, **kwargs):
        reply = next(self.replies)
        if isinstance(reply, Exception):
            raise reply
        return reply


class _Model:
    name = "test:fixture"

    def __init__(self, replies):
        self.replies = replies
        self.bound_names = []
        self.bind_modes = []
        self.bound = _Bound(replies)

    def bind_tools(self, tools, *, allow_tools=True):
        self.bound_names = [tool.name for tool in tools]
        self.bind_modes.append(allow_tools)
        return self.bound

    def estimate_cost_usd(self, input_tokens, output_tokens):
        return 0.000001 * (input_tokens + output_tokens)

    def reserve_cost_usd(self, input_tokens):
        return self.estimate_cost_usd(input_tokens, 1024)


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
    def test_exhausted_read_budget_gets_a_tools_disabled_final_assessment(self):
        reads = []
        def read() -> dict:
            reads.append(1)
            return {"source": "project-runtime", "state": "failed", "reason": "OOMKilled"}
        tool = StructuredTool.from_function(read, name="get_runtime_status", description="Read readiness")
        replies = [AIMessage(content="", tool_calls=[{
            "name": tool.name, "args": {}, "id": "c" + str(i)}]) for i in range(8)]
        model = _Model(replies + [_answer("Likely memory exhaustion", ["E1"])])
        outcome = ai_agent.run("investigate_incident", "synthetic-budget", model, [tool])
        self.assertEqual(outcome["state"], "completed")
        self.assertEqual(outcome["tool_calls"], 8)
        self.assertEqual(len(reads), 8)
        self.assertEqual(model.bind_modes, [True, False])

    def test_finalization_cannot_execute_an_extra_tool_if_provider_ignores_disable(self):
        reads = []
        def read() -> dict:
            reads.append(1)
            return {"source": "project-runtime", "state": "missing"}
        tool = StructuredTool.from_function(read, name="get_runtime_status", description="Read readiness")
        replies = [AIMessage(content="", tool_calls=[{
            "name": tool.name, "args": {}, "id": "c" + str(i)}]) for i in range(9)]
        outcome = ai_agent.run("investigate_incident", "synthetic-budget", _Model(replies), [tool])
        self.assertEqual(outcome["state"], "abstained")
        self.assertEqual(outcome["tool_calls"], 8)
        self.assertEqual(len(reads), 8)

    def test_openai_finalization_disables_tools_at_provider_boundary(self):
        adapter = object.__new__(ai_model.OpenAIModelAdapter)
        from unittest.mock import Mock
        adapter.model = Mock()
        adapter.bind_tools([], allow_tools=False)
        adapter.model.bind_tools.assert_called_once_with([], parallel_tool_calls=False, tool_choice="none")

    def test_revision_comparison_exposes_fields_not_startup_or_secret_values(self):
        previous = {"components": [{"name": "web", "args": ["old-secret"]}],
                    "configuration": {"TOKEN": "old-secret"}}
        current_spec = {"components": [{"name": "web", "args": ["new-secret"]}],
                        "configuration": {"TOKEN": "new-secret"}}
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.execute.return_value.fetchall.return_value = [(2, current_spec), (1, previous)]
        tools = {t.name: t for t in ai_tools.make_tools("shop", lambda _: (2, current_spec, "applied"),
                                                       lambda: connection)}
        result = tools["get_configuration"].invoke({})
        self.assertEqual(result["component_changes"], [{"component": "web", "fields": ["args"]}])
        self.assertEqual(result["previous_revision"], 1)
        self.assertEqual(result["changed_key_names_since_previous_revision"], ["TOKEN"])
        self.assertNotIn("secret", json.dumps(result).replace("non_secret", ""))
        self.assertEqual(connection.execute.call_args.args[1], ("shop", 2))
        connection.execute.return_value.fetchall.return_value = [(2, current_spec)]
        unavailable = tools["get_configuration"].invoke({})
        self.assertEqual(unavailable["comparison_state"], "unavailable")
        self.assertIsNone(unavailable["changed_count"])
        self.assertNotIn("component_changes", unavailable)

    def test_explicit_global_acceptance_uses_global_endpoint_without_eu_claims(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key", "OPENAI_DATA_REGION": "global",
                                    "OPENAI_GLOBAL_PROCESSING_ACCEPTED": "true"}, clear=True), \
                patch("langchain_openai.ChatOpenAI") as client:
            model = ai_model.configured_model()
        args = client.call_args.kwargs
        self.assertEqual(args["base_url"], "https://api.openai.com/v1")
        self.assertFalse(args["store"])
        self.assertFalse(args["use_previous_response_id"])
        self.assertEqual(args["service_tier"], "default")
        self.assertAlmostEqual(model.estimate_cost_usd(1000, 1000), .012)

    def test_global_region_requires_acceptance_and_api_key(self):
        for values in ({"OPENAI_API_KEY": "test-key"}, {"OPENAI_GLOBAL_PROCESSING_ACCEPTED": "true"}):
            with self.subTest(values=tuple(values)), patch.dict(os.environ, {"OPENAI_DATA_REGION": "global", **values}, clear=True):
                with self.assertRaises(ai_model.ModelUnavailable):
                    ai_model.configured_model()

    def test_eu_and_unknown_regions_never_fall_back_to_global(self):
        for region in ("eu", "unknown"):
            with self.subTest(region=region), patch.dict(os.environ, {
                "OPENAI_API_KEY": "test-key", "OPENAI_DATA_REGION": region,
                "OPENAI_GLOBAL_PROCESSING_ACCEPTED": "true"}, clear=True), \
                    patch("langchain_openai.ChatOpenAI") as client:
                with self.assertRaises(ai_model.ModelUnavailable):
                    ai_model.configured_model()
                client.assert_not_called()

    def test_verified_eu_region_keeps_eu_endpoint_and_cost(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key", "OPENAI_DATA_REGION": "eu",
            "OPENAI_EU_PROJECT_VERIFIED": "true", "OPENAI_EU_PROCESSING_VERIFIED": "true",
            "OPENAI_MODIFIED_RETENTION_AMENDMENT_VERIFIED": "true"}, clear=True), \
                patch("langchain_openai.ChatOpenAI") as client:
            model = ai_model.configured_model()
        self.assertEqual(client.call_args.kwargs["base_url"], "https://eu.api.openai.com/v1")
        self.assertAlmostEqual(model.estimate_cost_usd(1000, 1000), .0132)

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

    def test_catalog_explanation_completes_with_sourced_facts_and_no_hypothesis(self):
        tool = StructuredTool.from_function(func=lambda: {"source": "project-catalog", "state": "applied",
            "revision": 17, "components": [{"name": "web", "type": "service"}]},
            name="get_application", description="Read the current catalog")
        final = AIMessage(content=json.dumps({"summary": "Revision 17 is applied.",
            "observations": [{"statement": "The web component is a service.", "source_ids": ["E1"]}],
            "hypotheses": [], "gaps": ["Business functionality and runtime health are not described."],
            "insufficient_evidence": False}))
        model = _Model([AIMessage(content="", tool_calls=[{
            "name": "get_application", "args": {}, "id": "call-1"}]), final])
        outcome = ai_agent.run("explain_application", "run-explanation", model, [tool])
        self.assertEqual(outcome["state"], "completed")
        self.assertEqual(outcome["result"]["hypotheses"], [])
        self.assertEqual(outcome["result"]["observations"][0]["source_ids"], ["E1"])
        self.assertEqual(outcome["tool_calls"], 1)

    def test_explanation_rejects_missing_unavailable_or_foreign_observation_sources(self):
        for refs, evidence in (([], [{"id": "E1", "state": "applied"}]),
                               (["foreign"], [{"id": "E1", "state": "applied"}]),
                               (["E1"], [{"id": "E1", "state": "missing"}]),
                               (["E1"], [])):
            with self.subTest(refs=refs, evidence=evidence):
                message = AIMessage(content=json.dumps({"summary": "Some facts.",
                    "observations": [{"statement": "A service exists.", "source_ids": refs}],
                    "hypotheses": [], "gaps": [], "insufficient_evidence": False}))
                self.assertTrue(ai_agent._parse_final(message, evidence, "explain_application")["insufficient_evidence"])

    def test_incident_diagnosis_still_requires_hypotheses_not_only_observations(self):
        message = AIMessage(content=json.dumps({"summary": "A service exists.",
            "observations": [{"statement": "A service exists.", "source_ids": ["E1"]}],
            "hypotheses": [], "gaps": [], "insufficient_evidence": False}))
        result = ai_agent._parse_final(message, [{"id": "E1", "state": "applied"}], "investigate_incident")
        self.assertTrue(result["insufficient_evidence"])

    def test_missing_logs_can_be_cited_as_availability_without_erasing_supported_diagnosis(self):
        message = AIMessage(content=json.dumps({"summary": "The rollout has failed; logs are absent.",
            "observations": [{"statement": "The database is healthy.", "source_ids": ["E2"]}],
            "hypotheses": [{"statement": "A startup failure is suspected; logs do not explain why.",
                            "source_ids": ["E1", "E2"]}],
            "gaps": ["No logs were returned."], "insufficient_evidence": False}))
        evidence = [{"id": "E1", "state": "failed"}, {"id": "E2", "state": "no_output"}]
        result = ai_agent._parse_final(message, evidence)
        self.assertFalse(result["insufficient_evidence"])
        self.assertEqual(len(result["hypotheses"]), 1)
        self.assertTrue(result["observations"][0]["availability_only"])
        self.assertNotIn("database is healthy", str(result))

    def test_missing_evidence_alone_cannot_support_a_diagnosis(self):
        message = _answer("Unsupported diagnosis", ["E1"])
        result = ai_agent._parse_final(message, [{"id": "E1", "state": "no_output"}])
        self.assertTrue(result["insufficient_evidence"])
        self.assertEqual(result["validation_error"], "hypothesis_without_available_source")

    def test_validation_reason_is_safe_and_distinguishes_malformed_output(self):
        with self.assertLogs("app.ai_agent", level="WARNING") as logs:
            result = ai_agent._parse_final(AIMessage(content='{"secret-provider-payload":'), [])
        self.assertEqual(result["validation_error"], "invalid_json")
        self.assertNotIn("secret-provider-payload", str(result) + str(logs.output))

    def test_missing_or_foreign_citation_abstains(self):
        model = _Model([_answer("certain root cause", ["foreign-source"])])
        outcome = ai_agent.run("investigate_incident", "run-2", model, [])
        self.assertEqual(outcome["state"], "abstained")
        self.assertEqual(outcome["result"]["hypotheses"], [])

    def test_model_failure_preserves_prior_evidence_usage_and_does_not_retry(self):
        tool = StructuredTool.from_function(func=lambda: {"source": "project-runtime", "state": "ready"},
                                            name="get_runtime_status", description="Read readiness")
        reply = AIMessage(content="", tool_calls=[{"name": "get_runtime_status", "args": {}, "id": "c1"}],
                          usage_metadata={"input_tokens": 100, "output_tokens": 20, "total_tokens": 120})
        model = _Model([reply, TimeoutError("secret provider diagnostics must not escape")])
        with self.assertLogs("app.ai_agent", level="ERROR") as logs:
            result = ai_agent.run("investigate_incident", "run-timeout", model, [tool])
        self.assertEqual(result["state"], "failed")
        self.assertEqual(result["tool_calls"], 1)
        self.assertEqual(result["evidence"][0]["source"], "project-runtime")
        self.assertAlmostEqual(result["estimated_cost_usd"], .00012)
        self.assertFalse(result["result"]["usage_complete"])
        self.assertNotIn("secret provider diagnostics", str(result) + str(logs.output))

    def test_model_timeout_is_bounded_by_remaining_run_budget(self):
        from unittest.mock import Mock
        model = _Model([])
        bound = Mock()
        bound.invoke.return_value = _answer("Missing data", [], True)
        model.bind_tools = lambda tools: bound
        ticks = iter([0, 80, 85])
        ai_agent.run("investigate_incident", "run-deadline", model, [], clock=lambda: next(ticks))
        self.assertEqual(bound.invoke.call_args.kwargs["timeout"], 5)

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

    def test_manage_authority_excludes_developer_and_deployment_credential(self):
        principal = type("Principal", (), {"issuer": "issuer", "subject": "person"})()
        with patch.object(authorization, "_roles", return_value={"developer"}), \
             patch("app.deployment_credentials.access_scope", return_value=None):
            self.assertFalse(authorization.is_allowed(None, principal, "manage", "shop"))
        with patch.object(authorization, "_roles", return_value={"project-admin"}), \
             patch("app.deployment_credentials.access_scope", return_value=None):
            self.assertTrue(authorization.is_allowed(None, principal, "manage", "shop"))
        machine = type("Machine", (), {"active": True, "kind": "deployment", "project": "shop"})()
        with patch.object(authorization, "_roles", return_value={"project-admin"}), \
             patch("app.deployment_credentials.access_scope", return_value=machine):
            self.assertFalse(authorization.is_allowed(None, principal, "manage", "shop"))


if __name__ == "__main__":
    unittest.main()
