"""Trace context is bounded and cannot carry arbitrary incoming metadata."""

import os
import unittest
from unittest.mock import patch

from app import tracing


class TraceBoundaryTests(unittest.TestCase):
    def test_sampling_configuration_rejects_invalid_values(self):
        for value in ("-0.1", "1.1", "nan", "inf", "random"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                tracing.sample_rate(value)
        self.assertEqual(tracing.sample_rate("0"), 0)
        self.assertEqual(tracing.sample_rate("0.1"), 0.1)
        self.assertEqual(tracing.sample_rate("1"), 1)

    def test_default_samples_every_root_and_operator_override_is_respected(self):
        for override, expected in ((None, True), ("0", False)):
            env = {"PLATFORM_OTLP_ENDPOINT": "http://alloy:4318/v1/traces"}
            if override is not None:
                env["PLATFORM_TRACE_SAMPLE_RATE"] = override
            with self.subTest(override=override), patch.dict(os.environ, env, clear=True), \
                    patch.object(tracing, "_provider"), patch.object(tracing, "_tracer"), \
                    patch.object(tracing, "TracerProvider") as provider, \
                    patch.object(tracing, "BatchSpanProcessor"), \
                    patch.object(tracing, "OTLPSpanExporter"), \
                    patch("app.ai_observability.configure"):
                tracing.configure()
                sampler = provider.call_args.kwargs["sampler"]
                for trace_id in (1, 2**64, 2**128 - 1):
                    self.assertEqual(sampler.should_sample(None, trace_id, "test").decision.is_sampled(),
                                     expected)

    def test_operation_link_accepts_only_sampled_internal_traceparent(self):
        valid = "00-0123456789abcdef0123456789abcdef-0123456789abcdef-01"
        self.assertEqual(len(tracing.origin_link(valid)), 1)
        self.assertEqual(tracing.origin_link(valid)[0].context.trace_id,
                         int("0123456789abcdef0123456789abcdef", 16))
        for invalid in ("", "00-" + "0" * 32 + "-0123456789abcdef-01",
                        valid[:-2] + "00", valid + "-baggage", False, None):
            with self.subTest(invalid=invalid):
                self.assertEqual(tracing.origin_link(invalid), [])


if __name__ == "__main__":
    unittest.main()
