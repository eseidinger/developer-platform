import json
import unittest

from app import ai_evaluation, ai_tools


class EvaluationContractTests(unittest.TestCase):
    def test_fixture_diagnostics_come_from_production_reader_and_projection(self):
        host, pool = ai_evaluation.CASES[:2]
        self.assertEqual(
            host.observations["get_logs"]["diagnostics"]["failure_codes"],
            ["database_hostname_resolution_failed"],
        )
        self.assertEqual(
            pool.observations["get_logs"]["diagnostics"]["failure_codes"],
            ["database_pool_capacity_timeout"],
        )
        for case in (host, pool):
            self.assertEqual(
                case.observations["get_logs"]["retained_state"], "no_output"
            )
            self.assertNotIn("synthetic.invalid", json.dumps(case.observations))
        for case in ai_evaluation.CASES[-2:]:
            self.assertTrue(case.must_abstain)
            self.assertEqual(
                case.observations["get_logs"]["diagnostics"]["failure_codes"], []
            )

    def test_tools_share_production_argument_contracts_and_descriptions(self):
        production = {
            t.name: t
            for t in ai_tools.make_tools("synthetic", lambda _: None, lambda: None)
        }
        fixtures = {t.name: t for t in ai_evaluation.tools_for(ai_evaluation.CASES[0])}
        self.assertEqual(set(production), set(fixtures))
        for name, tool in production.items():
            self.assertEqual(tool.description, fixtures[name].description)
            self.assertEqual(tool.args, fixtures[name].args)
        self.assertEqual(fixtures["get_logs"].invoke({})["state"], "ok")
        self.assertEqual(
            fixtures["get_metrics"].invoke({"component": "foreign"})["state"],
            "not_declared",
        )

    def test_diagnosis_must_cite_discriminating_source_in_the_matching_hypothesis(self):
        case = ai_evaluation.CASES[0]
        outcome = {
            "state": "completed",
            "result": {
                "hypotheses": [
                    {
                        "statement": "Database hostname resolution failed",
                        "source_ids": ["E1"],
                    }
                ],
                "insufficient_evidence": False,
            },
            "evidence": [{"id": "E1", "tool": "get_configuration", "state": "ok"}],
            "tool_calls": 2,
            "estimated_cost_usd": 0.01,
        }
        self.assertFalse(ai_evaluation.score(case, outcome)["passed"])
        outcome["evidence"][0]["tool"] = "get_logs"
        self.assertTrue(ai_evaluation.score(case, outcome)["passed"])
        outcome["evidence"][0]["state"] = "unavailable"
        self.assertFalse(ai_evaluation.score(case, outcome)["passed"])

    def test_provider_failure_is_not_a_passing_abstention(self):
        outcome = {
            "state": "failed",
            "result": {"hypotheses": [], "insufficient_evidence": True},
            "tool_calls": 0,
            "estimated_cost_usd": 0,
        }
        self.assertFalse(ai_evaluation.score(ai_evaluation.CASES[3], outcome)["passed"])

    def test_original_six_cases_remain_available(self):
        self.assertEqual(len(ai_evaluation.LEGACY_CASES), 6)
        self.assertNotIn(
            "diagnostics", ai_evaluation.LEGACY_CASES[0].observations["get_logs"]
        )
