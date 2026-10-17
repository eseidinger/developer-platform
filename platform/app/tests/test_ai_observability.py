"""Exercise the real LangChain -> OpenAI Responses -> OpenLIT path offline."""
import json
import unittest
from unittest.mock import patch

import httpx
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from app import ai_observability as obs, ai_pricing, tracing

MARKER = "seed-private-prompt-password-token-evidence"


class OpenLITTests(unittest.TestCase):
    def setUp(self):
        self.exporter = InMemorySpanExporter()
        self.provider = TracerProvider()
        self.provider.add_span_processor(SimpleSpanProcessor(self.exporter))
        self.tracer_patch = patch.object(tracing, "_tracer", self.provider.get_tracer("fixture"))
        self.tracer_patch.start()
        self.reader = InMemoryMetricReader()
        self.meter_provider = MeterProvider(metric_readers=[self.reader])
        self.saved = obs._instruments.copy()
        obs._instruments.clear()
        obs._series.clear()
        meter = self.meter_provider.get_meter("fixture")
        for name in ("platform_ai_operations", "platform_ai_runs", "platform_ai_tool_calls", "platform_ai_tokens",
                     "platform_ai_usage_observations", "platform_ai_estimated_cost_usd", "platform_ai_cardinality_dropped"):
            obs._instruments[name] = meter.create_counter(name)
        obs._instruments["platform_ai_duration_seconds"] = meter.create_histogram("platform_ai_duration_seconds")
        obs._instruments["platform_ai_in_flight"] = meter.create_up_down_counter("platform_ai_in_flight")
        obs.install_openlit()

    def tearDown(self):
        obs.shutdown()
        obs._instruments.update(self.saved)
        self.tracer_patch.stop()
        self.provider.shutdown()
        self.meter_provider.shutdown()

    def client(self, handler):
        return ChatOpenAI(model="gpt-6.1-sol", api_key="synthetic-key", use_responses_api=True,
            store=False, max_retries=0, http_client=httpx.Client(transport=httpx.MockTransport(handler)))

    def test_real_responses_path_preserves_parentage_drops_content_and_emits_one_duration(self):
        requests = []
        def respond(request):
            requests.append(json.loads(request.content))
            return httpx.Response(200, json={"id": MARKER, "object": "response", "created_at": 1,
                "model": "gpt-6.1-sol", "status": "completed", "error": None,
                "output": [{"id": MARKER, "type": "message", "role": "assistant", "status": "completed",
                    "content": [{"type": "output_text", "text": MARKER, "annotations": []}]}],
                "usage": {"input_tokens": 100, "output_tokens": 10, "total_tokens": 110,
                    "input_tokens_details": {"cached_tokens": 0}, "output_tokens_details": {"reasoning_tokens": 0}}})
        model = self.client(respond)
        with obs.scope("lab", "explain_application"), tracing.span("platform.ai.run"):
            for allow_tools in (True, False):
                options = {} if allow_tools else {"tool_choice": "none"}
                with obs.operation("model"):
                    answer = model.bind_tools([], **options).invoke([HumanMessage(content=MARKER)])
                obs.usage(ai_pricing.estimate("openai:gpt-6.1-sol", answer.usage_metadata))
        spans = self.exporter.get_finished_spans()
        model_spans = [s for s in spans if s.name == "platform.ai.model"]
        root = next(s for s in spans if s.name == "platform.ai.run")
        self.assertEqual(len(model_spans), 2)
        self.assertTrue(all(s.parent.span_id == root.context.span_id for s in model_spans))
        self.assertTrue(all(s.context.trace_id == root.context.trace_id for s in model_spans))
        self.assertTrue(all(not s.events for s in spans))
        self.assertNotIn(MARKER, str([(s.name, dict(s.attributes), str(s.status)) for s in spans]))
        self.assertTrue(all(r["store"] is False for r in requests))
        data = self.reader.get_metrics_data()
        metrics = {m.name: m for rm in data.resource_metrics for sm in rm.scope_metrics for m in sm.metrics}
        self.assertEqual(sum(p.count for p in metrics["platform_ai_duration_seconds"].data.data_points), 2)
        self.assertEqual(sum(p.value for p in metrics["platform_ai_tokens"].data.data_points), 220)
        self.assertNotIn(MARKER, str(data))

    def test_provider_failure_has_no_exception_content_and_no_fake_zero_usage(self):
        def respond(request):
            return httpx.Response(500, json={"error": {"message": MARKER, "type": "server_error"}})
        with obs.scope("lab", "investigate_incident"), tracing.span("platform.ai.run"):
            with self.assertRaises(Exception), obs.operation("model"):
                self.client(respond).invoke(MARKER)
        spans = self.exporter.get_finished_spans()
        self.assertEqual(len([s for s in spans if s.name == "platform.ai.model"]), 1)
        self.assertTrue(all(not s.events for s in spans))
        self.assertNotIn(MARKER, str([(dict(s.attributes), str(s.status)) for s in spans]))
        data = str(self.reader.get_metrics_data())
        self.assertNotIn(MARKER, data)
        self.assertNotIn("platform_ai_tokens", data)

    def test_local_prices_distinguish_missing_cached_unknown_and_zero(self):
        self.assertFalse(ai_pricing.estimate("openai:gpt-6.1-sol", {}).complete)
        self.assertIsNone(ai_pricing.estimate("unknown", {"input_tokens": 1, "output_tokens": 1}).usd)
        self.assertIsNone(ai_pricing.estimate("openai:gpt-6.1-sol", {"input_tokens": 100,
            "output_tokens": 10, "input_token_details": {"cache_read": 5}}).usd)
        self.assertEqual(ai_pricing.estimate("openai:gpt-6.1-sol", {"input_tokens": 0, "output_tokens": 0}).usd, 0)
        self.assertAlmostEqual(ai_pricing.estimate("openai:gpt-6.1-sol", {"input_tokens": 1000,
            "output_tokens": 1000}).usd, .012)
        with patch.dict(ai_pricing.RATES, {"fixture": (2, .2, 10)}):
            self.assertAlmostEqual(ai_pricing.estimate("fixture", {"input_tokens": 100,
                "input_token_details": {"cache_read": 50}, "output_tokens": 10}).usd, .00021)

    def test_metrics_failure_does_not_change_operation(self):
        with patch.object(obs, "_instruments", {"platform_ai_runs": unittest.mock.Mock(add=unittest.mock.Mock(side_effect=RuntimeError))}):
            obs.outcome("completed", 0)


if __name__ == "__main__":
    unittest.main()
