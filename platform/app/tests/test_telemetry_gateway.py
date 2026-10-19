import time
import unittest
from types import SimpleNamespace as Obj

from fastapi import HTTPException
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

from app.telemetry_gateway import _identity, sanitize
from app import workload_trace


def ai_batch(attributes=None, name="completion test-model", scope="io.quarkiverse.langchain4j"):
    now = time.time_ns()
    original = ExportTraceServiceRequest()
    resource = original.resource_spans.add()
    group = resource.scope_spans.add()
    group.scope.name = scope
    group.scope.version = "1.2.3"
    span = group.spans.add()
    span.trace_id = b"a" * 16
    span.span_id = b"b" * 8
    span.parent_span_id = b"c" * 8
    span.flags = 1
    span.name = name
    span.kind = 3
    span.status.code = 1
    span.start_time_unix_nano = now - 1000
    span.end_time_unix_nano = now
    for key, value in (attributes or {}).items():
        item = span.attributes.add()
        item.key = key
        if isinstance(value, str): item.value.string_value = value
        elif type(value) is bool: item.value.bool_value = value
        elif type(value) is int: item.value.int_value = value
        elif type(value) is float: item.value.double_value = value
        elif isinstance(value, list):
            for reason in value: item.value.array_value.values.add().string_value = reason
    return original, span, now


def sanitized_span(batch, now):
    result = ExportTraceServiceRequest.FromString(sanitize(batch.SerializeToString(), "shop", "api", now))
    group = result.resource_spans[0].scope_spans[0]
    span = group.spans[0]
    return group, span, {a.key: workload_trace.protobuf_value(a.value) for a in span.attributes}


class GatewayBoundaryTests(unittest.TestCase):
    def test_otlp_flags_without_sampled_bit_are_valid_exported_spans(self):
        for flags in (0, 256, 768):
            with self.subTest(flags=flags):
                batch, span, now = ai_batch()
                span.flags = flags
                _, clean, _ = sanitized_span(batch, now)
                self.assertEqual(clean.trace_id, span.trace_id)
                self.assertEqual(clean.span_id, span.span_id)

    def test_real_python_sdk_encoded_span_is_accepted(self):
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
        from opentelemetry.exporter.otlp.proto.common.trace_encoder import encode_spans
        provider = TracerProvider()
        exporter = InMemorySpanExporter()
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        try:
            with provider.get_tracer("worker").start_as_current_span("scheduled-work"):
                pass
            batch = encode_spans(exporter.get_finished_spans())
            _, clean, _ = sanitized_span(batch, time.time_ns())
            self.assertEqual(clean.name, "application.span")
            self.assertTrue(any(clean.trace_id))
        finally:
            provider.shutdown()

    def test_ai_metadata_parentage_timing_and_library_survive_without_private_content(self):
        original, span, now = ai_batch({
            "gen_ai.operation.name": "chat", "gen_ai.provider.name": "openai",
            "gen_ai.request.model": "test-model", "gen_ai.response.model": "test-model-v2",
            "gen_ai.usage.input_tokens": 12, "gen_ai.usage.output_tokens": 3,
            "gen_ai.request.max_tokens": 128, "gen_ai.request.temperature": 0.5,
            "gen_ai.request.top_p": 0.9, "gen_ai.response.finish_reasons": ["STOP"],
            "gen_ai.tool.name": "lookup_weather", "http.request.method": "POST",
            "http.response.status_code": 200, "error.type": "example.RetryError",
            "gen_ai.input.messages": "PRIVATE_PAYLOAD", "gen_ai.prompt": "PRIVATE_PAYLOAD",
            "gen_ai.completion": "PRIVATE_PAYLOAD", "gen_ai.response.id": "PRIVATE_PAYLOAD",
            "gen_ai.client.estimated_cost": "PRIVATE_PAYLOAD", "gen_ai.tool.call.arguments": "PRIVATE_PAYLOAD",
        })
        span.name += " PRIVATE_PAYLOAD"
        span.status.message = "PRIVATE_PAYLOAD"
        span.events.add().name = "PRIVATE_PAYLOAD"
        original.resource_spans[0].scope_spans[0].scope.attributes.add().value.string_value = "PRIVATE_PAYLOAD"
        group, clean, fields = sanitized_span(original, now)
        self.assertEqual(clean.name, "application.ai.chat")
        self.assertEqual(fields["platform.ai.framework"], "langchain4j")
        self.assertEqual(fields["platform.instrumentation.name"], "io.quarkiverse.langchain4j")
        self.assertEqual(fields["gen_ai.response.finish_reasons"], ["stop"])
        self.assertEqual(fields["gen_ai.usage.input_tokens"], 12)
        self.assertEqual(fields["gen_ai.request.temperature"], .5)
        self.assertEqual(len(fields), 16)
        self.assertEqual(group.scope.version, "1.2.3")
        self.assertEqual((clean.parent_span_id, clean.trace_id, clean.span_id), (b"c"*8, b"a"*16, b"b"*8))
        self.assertEqual((clean.start_time_unix_nano, clean.end_time_unix_nano, clean.kind, clean.status.code),
                         (now-1000, now, 3, 1))
        self.assertNotIn(b"PRIVATE_PAYLOAD", clean.SerializeToString())
        self.assertFalse(group.scope.attributes)

    def test_legacy_langchain4j_conventions_are_normalized(self):
        original, _, now = ai_batch({"gen_ai.system": "OPEN_AI", "gen_ai.request.model": "test-model",
            "gen_ai.usage.prompt_tokens": 5, "gen_ai.usage.completion_tokens": 2,
            "gen_ai.response.finish_reasons": "TOOL_EXECUTION"})
        _, clean, fields = sanitized_span(original, now)
        self.assertEqual(clean.name, "application.ai.chat")
        self.assertEqual(fields["gen_ai.provider.name"], "openai")
        self.assertEqual(fields["gen_ai.usage.input_tokens"], 5)
        self.assertEqual(fields["gen_ai.usage.output_tokens"], 2)
        self.assertEqual(fields["gen_ai.response.finish_reasons"], ["tool_calls"])
        self.assertNotIn("gen_ai.system", fields)

    def test_service_and_tool_names_are_useful_without_retaining_method_names(self):
        original, _, now = ai_batch(name="langchain4j.aiservices.PrivateAssistant.privateMethod",
                                    scope="io.quarkus.opentelemetry")
        _, clean, fields = sanitized_span(original, now)
        self.assertEqual(clean.name, "application.ai.service")
        self.assertEqual(fields["platform.ai.framework"], "langchain4j")
        self.assertNotIn(b"PrivateAssistant", clean.SerializeToString())
        original, _, now = ai_batch({"gen_ai.operation.name":"execute_tool", "gen_ai.tool.name":"lookup_weather"},
                                    name="langchain4j.tools.lookup_weather")
        self.assertEqual(sanitized_span(original, now)[1].name, "application.ai.execute_tool")
        original, _, now = ai_batch({"gen_ai.operation.name":"chat"}, scope="io.opentelemetry.langchain4j-1.0")
        self.assertEqual(sanitized_span(original, now)[2]["platform.ai.framework"], "langchain4j")

    def test_malformed_metadata_is_dropped_and_standard_values_win_over_legacy(self):
        original, _, now = ai_batch({"gen_ai.operation.name":"private operation", "gen_ai.provider.name": "openai",
            "gen_ai.system":"wrong", "gen_ai.request.model":"secret model with spaces",
            "gen_ai.response.model":"x"*129, "gen_ai.usage.input_tokens":-1,
            "gen_ai.usage.output_tokens":True, "gen_ai.request.temperature":float('nan'),
            "gen_ai.request.top_p":1.1, "gen_ai.response.finish_reasons":["password=secret"],
            "gen_ai.tool.name":"https://private.example/path"}, name="private operation", scope="scope with private content")
        group, clean, fields = sanitized_span(original, now)
        self.assertEqual(clean.name, "application.span")
        self.assertEqual(fields, {"gen_ai.provider.name":"openai"})
        self.assertEqual(group.scope.name, "platform-verified-workload")

    def test_only_exception_type_is_retained_without_message_stack_or_events(self):
        original, span, now = ai_batch({"gen_ai.operation.name":"chat"})
        span.status.code = 2
        event = span.events.add()
        event.name = "exception"
        for key, value in [("exception.type","java.lang.IllegalStateException"),
                           ("exception.message","PRIVATE_PAYLOAD"),("exception.stacktrace","PRIVATE_PAYLOAD")]:
            field=event.attributes.add(); field.key=key; field.value.string_value=value
        _, clean, fields = sanitized_span(original, now)
        self.assertEqual(fields["error.type"], "java.lang.IllegalStateException")
        self.assertEqual(clean.status.code, 2)
        self.assertFalse(clean.events)
        self.assertNotIn(b"PRIVATE_PAYLOAD", clean.SerializeToString())

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
