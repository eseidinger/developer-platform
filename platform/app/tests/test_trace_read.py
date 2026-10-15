import base64
import io
import json
import time
import unittest

from app import trace_read


class _Opener:
    def __init__(self, document):
        self.document = document

    def open(self, request, timeout):
        return io.BytesIO(json.dumps(self.document).encode())


class ScopedTraceReadTests(unittest.TestCase):
    def test_foreign_and_platform_spans_are_omitted(self):
        now = int(time.time())
        trace = "a" * 32
        raw_id = base64.b64encode(bytes.fromhex(trace)).decode()
        span_id = base64.b64encode(b"b" * 8).decode()
        span = {"traceId": raw_id, "spanId": span_id,
                "startTimeUnixNano": str((now - 1) * 10 ** 9),
                "endTimeUnixNano": str(now * 10 ** 9), "name": "password=secret",
                "attributes": [{"key": "db.statement", "value": {"stringValue": "SELECT password"}}]}
        def resource(project):
            return {"resource": {"attributes": [{"key": "platform.project", "value": {"stringValue": project}},
                                                {"key": "platform.component", "value": {"stringValue": "api"}}]},
                    "scopeSpans": [{"spans": [span]}]}
        response = trace_read.read("shop", trace, _Opener({"trace": {"resourceSpans": [
            resource("foreign"), resource("shop"), {"resource": {"attributes": []}, "scopeSpans": [{"spans": [span]}]}]}}), now)
        self.assertEqual(len(response["spans"]), 1)
        self.assertNotIn("secret", str(response))
        self.assertNotIn("foreign", str(response))


if __name__ == "__main__":
    unittest.main()
