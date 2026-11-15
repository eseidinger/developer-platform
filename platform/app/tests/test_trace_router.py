"""Project UUID partitioning prevents queued traces from resurrecting erased data."""

import unittest
from uuid import uuid4

from app.trace_router import partition
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
)


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
