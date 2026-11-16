"""Project UUID partitioning prevents queued traces from resurrecting erased data."""

import gzip
import unittest
from unittest.mock import patch
from uuid import uuid4

from app.trace_router import partition
from fastapi.testclient import TestClient
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
)

from app import trace_router


class TracePartitionTests(unittest.TestCase):
    def test_splits_projects_and_drops_batches_for_inactive_projects(self):
        source = ExportTraceServiceRequest()
        resource = source.resource_spans.add()
        scope = resource.scope_spans.add()
        for index, project in enumerate(("first", "second", "retired", None)):
            span = scope.spans.add()
            span.trace_id = bytes([index + 1]) * 16
            span.span_id = bytes([index + 1]) * 8
            if project:
                attribute = span.attributes.add()
                attribute.key = "platform.project"
                attribute.value.string_value = project
        identifiers = {"first": str(uuid4()), "second": str(uuid4()), "retired": None}
        result = partition(source.SerializeToString(), identifiers.get)
        self.assertEqual(
            set(result), {identifiers["first"], identifiers["second"], "platform"}
        )
        for tenant, body in result.items():
            batch = ExportTraceServiceRequest()
            batch.ParseFromString(body)
            spans = [
                span
                for resource in batch.resource_spans
                for scope in resource.scope_spans
                for span in scope.spans
            ]
            self.assertEqual(len(spans), 1)
            if tenant != "platform":
                attributes = {
                    a.key: a.value.string_value
                    for a in batch.resource_spans[0].resource.attributes
                }
                self.assertEqual(attributes["platform.project_id"], tenant)


class TraceTransportTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(trace_router.app)
        self.batch = ExportTraceServiceRequest()
        self.batch.resource_spans.add().scope_spans.add().spans.add().name = (
            "platform.http"
        )

    def test_plain_and_gzip_otlp_reach_the_same_tenant(self):
        payload = self.batch.SerializeToString()
        for encoding, body in (("identity", payload), ("gzip", gzip.compress(payload))):
            with (
                self.subTest(encoding=encoding),
                patch.object(trace_router.httpx, "Client") as client,
            ):
                response = self.client.post(
                    "/v1/traces",
                    content=body,
                    headers={"Content-Encoding": encoding},
                )
                self.assertEqual(response.status_code, 200)
                arguments = client.return_value.__enter__.return_value.post.call_args
                self.assertEqual(
                    arguments.kwargs["headers"]["X-Scope-OrgID"], "platform"
                )
                self.assertEqual(
                    arguments.kwargs["content"],
                    trace_router.partition(payload)["platform"],
                )

    def test_expanded_gzip_payload_is_bounded(self):
        response = self.client.post(
            "/v1/traces",
            content=gzip.compress(b"x" * (trace_router.MAX_BODY + 1)),
            headers={"Content-Encoding": "gzip"},
        )
        self.assertEqual(response.status_code, 413)

    def test_invalid_or_unsupported_payloads_are_rejected(self):
        for encoding, body, status in (
            ("gzip", b"invalid", 400),
            ("gzip", gzip.compress(b"valid")[:-3], 400),
            ("gzip", gzip.compress(b"") + gzip.compress(b""), 400),
            ("br", b"invalid", 415),
            ("identity", b"invalid protobuf", 400),
        ):
            with self.subTest(encoding=encoding, status=status):
                response = self.client.post(
                    "/v1/traces",
                    content=body,
                    headers={"Content-Encoding": encoding},
                )
                self.assertEqual(response.status_code, status)
