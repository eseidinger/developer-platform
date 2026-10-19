import base64
import io
import json
import time
import unittest

from app import trace_read
from google.protobuf.json_format import MessageToDict
from app.telemetry_gateway import sanitize
from test_telemetry_gateway import ai_batch


class _Opener:
    def __init__(self, document):
        self.document = document

    def open(self, request, timeout):
        return io.BytesIO(json.dumps(self.document).encode())


class ScopedTraceReadTests(unittest.TestCase):
    def test_project_reads_retain_ai_metadata_but_revalidate_backend_content(self):
        original, span, now_ns = ai_batch({"gen_ai.operation.name":"chat", "gen_ai.request.model":"test-model",
            "gen_ai.usage.input_tokens":12, "gen_ai.usage.output_tokens":3})
        span.status.code = 2
        span.status.message = "PRIVATE_PAYLOAD"
        from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
        safe = ExportTraceServiceRequest.FromString(sanitize(original.SerializeToString(), "shop", "api", now_ns))
        document = MessageToDict(safe)
        stored = document['resourceSpans'][0]['scopeSpans'][0]['spans'][0]
        stored['attributes'].extend([{'key':'gen_ai.input.messages','value':{'stringValue':'PRIVATE_PAYLOAD'}},
            {'key':'gen_ai.request.temperature','value':{'doubleValue':float('inf')}}])
        response = trace_read.read('shop', (b'a'*16).hex(), _Opener({'trace':document}), now_ns//10**9)
        item = response['spans'][0]
        self.assertEqual(item['name'], 'application.ai.chat')
        self.assertEqual(item['attributes']['gen_ai.request.model'], 'test-model')
        self.assertEqual(item['attributes']['gen_ai.usage.input_tokens'], 12)
        self.assertEqual(item['status'], 2)
        self.assertEqual(item['kind'], 3)
        self.assertEqual(item['instrumentation'], {'name':'io.quarkiverse.langchain4j','version':'1.2.3'})
        self.assertNotIn('PRIVATE_PAYLOAD', str(response))
        self.assertNotIn('gen_ai.request.temperature', item['attributes'])

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
