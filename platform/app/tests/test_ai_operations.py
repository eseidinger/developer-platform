import json
import os
import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage
from langchain_core.tools import StructuredTool

from app import ai_agent, ai_changes, ai_model, ai_tools


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


if __name__ == "__main__":
    unittest.main()
