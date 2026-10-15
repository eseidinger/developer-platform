"""Trace context is bounded and cannot carry arbitrary incoming metadata."""

import unittest

from app import tracing


class TraceBoundaryTests(unittest.TestCase):
    def test_sampling_configuration_rejects_invalid_values(self):
        for value in ("-0.1", "1.1", "nan", "inf", "random"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                tracing.sample_rate(value)
        self.assertEqual(tracing.sample_rate("0"), 0)
        self.assertEqual(tracing.sample_rate("0.1"), 0.1)
        self.assertEqual(tracing.sample_rate("1"), 1)

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
