import io
import json
import unittest

from app import application_metrics, monitoring


class _Opener:
    def __init__(self, values):
        self.values = iter(values)
        self.urls = []

    def open(self, request, timeout):
        self.urls.append(request.full_url)
        value = next(self.values)
        result = [] if value is None else [{"metric": {}, "value": [1, str(value)]}]
        return io.BytesIO(
            json.dumps(
                {
                    "status": "success",
                    "data": {"resultType": "vector", "result": result},
                }
            ).encode()
        )


class ApplicationMetricsTests(unittest.TestCase):
    def test_only_applied_declared_service_has_private_target(self):
        spec = {
            "components": [
                {
                    "name": "api",
                    "type": "service",
                    "ports": [{"name": "http", "port": 8080}],
                    "metrics": {"port": "http", "path": "/metrics"},
                },
                {"name": "job", "type": "scheduled"},
            ]
        }
        rows = [
            ("shop", spec, "applied"),
            ("staged", spec, "provisioning"),
            ("retired", spec, "retired"),
        ]
        groups = monitoring.metric_target_groups(rows)
        self.assertEqual(len(groups), 1)
        self.assertEqual(
            groups[0]["labels"]["proxy_path"],
            "/api/v1/namespaces/project-shop/services/http:api:http/proxy/metrics",
        )
        self.assertNotIn("secret", str(groups))

    def test_scoped_read_reports_collection_gap_and_only_aggregate_values(self):
        failed = application_metrics.observe("shop", "api", _Opener([0]))
        self.assertEqual(failed["state"], "collection_failed")
        opener = _Opener([1, 10, 1, 5, 10])
        result = application_metrics.observe("shop", "api", opener)
        self.assertEqual(result["state"], "ok")
        self.assertEqual(result["mean_request_duration_seconds"], 0.5)
        self.assertEqual(result["server_error_rate_per_second"], 1)
        self.assertEqual(len(opener.urls), 5)
        for url in opener.urls:
            self.assertIn("project%3D%22shop%22", url)
            self.assertIn("component%3D%22api%22", url)
        with self.assertRaises(ValueError):
            application_metrics.observe('shop"}', "api", opener)


if __name__ == "__main__":
    unittest.main()
