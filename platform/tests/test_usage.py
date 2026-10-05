import logging
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock

from kubernetes.client.exceptions import ApiException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.usage import observe_usage, parse_cpu, parse_memory

NOW = datetime(2026, 10, 3, 12, 0, 0, tzinfo=timezone.utc)
log = logging.getLogger("test")


def runtime_with(result=None, error=None):
    runtime = Mock()
    client = runtime.resources.get.return_value
    if error:
        client.get.side_effect = error
    else:
        client.get.return_value = result
    return runtime


def pod(name, age=15, cpu="250m", memory="64Mi", containers=1):
    stamp = (NOW - timedelta(seconds=age)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"metadata": {"name": name}, "timestamp": stamp, "window": "30s",
            "containers": [{"name": "c%d" % i, "usage": {"cpu": cpu, "memory": memory}}
                           for i in range(containers)]}


class UsageTests(unittest.TestCase):
    def test_quantities_parse(self):
        self.assertEqual(parse_cpu("250m"), 250)
        self.assertEqual(parse_cpu("2"), 2000)
        self.assertEqual(parse_cpu("500000n"), 0.5)
        self.assertEqual(parse_cpu("1500u"), 1.5)
        self.assertEqual(parse_memory("64Mi"), 64 * 1024 * 1024)
        self.assertEqual(parse_memory("1Ki"), 1024)
        self.assertEqual(parse_memory("2G"), 2_000_000_000)
        self.assertEqual(parse_memory("12345"), 12345)

    def test_fresh_metrics_are_summed_per_pod_and_in_total(self):
        runtime = runtime_with({"items": [pod("a", containers=2), pod("b")]})
        result = observe_usage(runtime, "smoke", log, now=NOW)
        self.assertEqual(result["state"], "ok")
        self.assertIsNone(result["reason"])
        self.assertEqual([p["name"] for p in result["pods"]], ["a", "b"])
        self.assertEqual(result["pods"][0]["cpu_millicores"], 500)
        self.assertEqual(result["totals"], {"cpu_millicores": 750, "memory_bytes": 3 * 64 * 1024 * 1024})
        runtime.resources.get.assert_called_with(api_version="metrics.k8s.io/v1beta1", kind="PodMetrics")
        runtime.resources.get.return_value.get.assert_called_with(namespace="project-smoke")

    def test_old_samples_are_labelled_stale_but_still_reported(self):
        result = observe_usage(runtime_with({"items": [pod("a", age=600)]}), "smoke", log, now=NOW)
        self.assertEqual(result["state"], "stale")
        self.assertEqual(result["reason"], "SampleOlderThan120s")
        self.assertEqual(result["totals"]["cpu_millicores"], 250)

    def test_no_samples_is_missing(self):
        result = observe_usage(runtime_with({"items": []}), "smoke", log, now=NOW)
        self.assertEqual(result["state"], "missing")
        self.assertEqual(result["reason"], "NoMetricsForProject")
        self.assertEqual(result["pods"], [])
        self.assertIsNone(result["totals"])

    def test_metrics_api_failures_are_unavailable_without_leaking_details(self):
        for error in (ApiException(status=404), ApiException(status=503), RuntimeError("secret detail")):
            result = observe_usage(runtime_with(error=error), "smoke", log, now=NOW)
            self.assertEqual(result["state"], "unavailable")
            self.assertEqual(result["reason"], "MetricsApiUnavailable")
            self.assertNotIn("secret", str(result))
        self.assertEqual(observe_usage(None, "smoke", log, now=NOW)["state"], "unavailable")

    def test_malformed_sample_is_unavailable(self):
        result = observe_usage(runtime_with({"items": [{"metadata": {"name": "a"}, "containers": [{}]}]}),
                               "smoke", log, now=NOW)
        self.assertEqual(result["state"], "unavailable")


if __name__ == "__main__":
    unittest.main()
