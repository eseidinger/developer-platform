import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock

import httpx2 as httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.retained_logs import observe_retained_logs, safe_event

NOW = datetime(2026, 10, 11, tzinfo=timezone.utc)
STAMP = str(int(NOW.timestamp() * 1_000_000_000) - 1)
CORRELATION = "a" * 32


class RetainedLogTests(unittest.TestCase):
    def read(self, data=None, status=200, **kwargs):
        self.requests = []
        self.log = Mock()
        if data is None:
            data = {"status": "success", "data": {"resultType": "streams", "result": [{
                "stream": {"job": "kubernetes-workloads", "project": "demo", "namespace": "project-demo",
                           "component": "api", "pod": "api-123", "container": "api"},
                "values": [[STAMP, json.dumps({"event": "request.completed", "level": "info",
                                                "correlationId": CORRELATION, "token": "do-not-copy"}),
                            {"revision": "1", "operation_id": "12345678-1234-1234-1234-123456789abc"}]],
            }]}}
        def respond(request):
            self.requests.append(request)
            return httpx.Response(status, json=data)
        factory = lambda **options: httpx.Client(transport=httpx.MockTransport(respond), **options)
        return observe_retained_logs("demo", self.log, now=NOW, client_factory=factory, **kwargs)

    def test_fixed_project_filter_metadata_and_unknown_fields_removed(self):
        result = self.read(component="api", instance="api-123")
        self.assertEqual(result["state"], "ok")
        self.assertEqual(result["lines"][0]["revision"], "1")
        self.assertEqual(result["next_cursor"], STAMP)
        self.assertNotIn("do-not-copy", json.dumps(result))
        params = self.requests[0].url.params
        self.assertEqual(params["query"], '{job="kubernetes-workloads",project="demo",namespace="project-demo",component="api",pod="api-123"}')
        self.assertEqual(params["limit"], "201")
        self.assertEqual(result["retention"]["seconds"], 604800)

    def test_backend_error_is_unavailable_not_empty_or_sensitive_diagnostics(self):
        for status in (302, 401, 500):
            result = self.read({"secret": "hidden-backend-value"}, status=status)
            self.assertEqual(result["state"], "unavailable")
            self.assertEqual(result["lines"], [])
            self.assertNotIn("hidden-backend-value", str(result) + str(self.log.mock_calls))

    def test_wrong_project_stream_rejected_before_returning_any_lines(self):
        data = {"status": "success", "data": {"resultType": "streams", "result": [{
            "stream": {"job": "kubernetes-workloads", "project": "other", "namespace": "project-other"},
            "values": [[STAMP, '{"event":"request.failed","level":"error"}']],
        }]}}
        self.assertEqual(self.read(data)["state"], "unavailable")

    def test_malformed_result_and_unsafe_events_are_not_forwarded(self):
        for data in ({}, {"status": "success", "data": {"resultType": "matrix", "result": []}}):
            self.assertEqual(self.read(data)["state"], "unavailable")
        for event in ("not-json", '{"event":"token-secret","level":"info"}',
                      '{"event":"request.completed","level":"info","correlationId":"customer@example.org"}',
                      '{"event":"request.completed","level":"info","correlationId":42}'):
            with self.subTest(event=event), self.assertRaises((ValueError, TypeError)):
                safe_event(event)

    def test_cursor_excludes_already_returned_timestamp_and_ranges_are_bounded(self):
        self.read(after=STAMP, before="2026-10-11T00:00:00Z")
        self.assertEqual(self.requests[0].url.params["start"], str(int(STAMP) + 1))
        for bounds in ({"after": "not-a-date"}, {"before": "2026-01-01T00:00:00Z"},
                       {"after": "2026-10-11T00:00:00"}, {"since_seconds": 604801}):
            with self.subTest(bounds=bounds), self.assertRaises(ValueError):
                self.read(**bounds)

    def test_empty_success_is_no_output(self):
        result = self.read({"status": "success", "data": {"resultType": "streams", "result": []}})
        self.assertEqual(result["state"], "no_output")

    def test_default_loki_encoding_flattens_structured_metadata(self):
        data = {"status": "success", "data": {"resultType": "streams", "result": [{
            "stream": {"job": "kubernetes-workloads", "project": "demo", "namespace": "project-demo",
                       "revision": "2", "operation_id": "12345678-1234-1234-1234-123456789abc"},
            "values": [[STAMP, '{"event":"job.completed","level":"info","correlationId":""}']],
        }]}}
        result = self.read(data)
        self.assertEqual(result["state"], "ok")
        self.assertEqual(result["lines"][0]["revision"], "2")
        self.assertIsNotNone(result["lines"][0]["operation_id"])


if __name__ == "__main__":
    unittest.main()
