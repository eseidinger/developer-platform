import time
import unittest
from types import SimpleNamespace as Obj

from fastapi import HTTPException
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

from app.telemetry_gateway import _identity, sanitize


class GatewayBoundaryTests(unittest.TestCase):
    def test_sanitizer_replaces_provenance_and_discards_untrusted_content(self):
        now = time.time_ns()
        original = ExportTraceServiceRequest()
        resource = original.resource_spans.add()
        attribute = resource.resource.attributes.add()
        attribute.key = "platform.project"
        attribute.value.string_value = "foreign"
        span = resource.scope_spans.add().spans.add()
        span.trace_id = b"a" * 16
        span.span_id = b"b" * 8
        span.flags = 1
        span.name = "GET /customers/private-name"
        span.start_time_unix_nano = now - 1000
        span.end_time_unix_nano = now
        secret = span.attributes.add()
        secret.key = "db.statement"
        secret.value.string_value = "SELECT password"
        event = span.events.add()
        event.name = "password=secret"
        encoded = sanitize(original.SerializeToString(), "shop", "api", now)
        self.assertNotIn(b"password", encoded)
        self.assertNotIn(b"foreign", encoded)
        safe = ExportTraceServiceRequest.FromString(encoded)
        self.assertEqual(safe.resource_spans[0].scope_spans[0].spans[0].name, "application.span")
        self.assertEqual({a.key: a.value.string_value for a in safe.resource_spans[0].resource.attributes}
                         ["platform.project"], "shop")

    def test_token_review_must_match_live_bound_pod_and_catalog(self):
        user = Obj(username="system:serviceaccount:project-shop:telemetry-api", extra={
            "authentication.kubernetes.io/pod-name": ["api-123"],
            "authentication.kubernetes.io/pod-uid": ["uid-123"]})
        review = Obj(status=Obj(authenticated=True, audiences=["platform-telemetry"], user=user))
        pod = Obj(metadata=Obj(uid="uid-123", namespace="project-shop", name="api-123",
                               labels={"app.kubernetes.io/name": "shop", "platform.example/component": "api"}),
                  spec=Obj(service_account_name="telemetry-api"))
        self.assertEqual(_identity(review, pod, lambda project, component: True), ("shop", "api"))
        altered = Obj(**{**pod.__dict__, "metadata": Obj(**{**pod.metadata.__dict__, "uid": "other"})})
        with self.assertRaises(HTTPException):
            _identity(review, altered, lambda project, component: True)
        with self.assertRaises(HTTPException):
            _identity(review, pod, lambda project, component: False)


if __name__ == "__main__":
    unittest.main()
