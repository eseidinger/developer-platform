"""Partition already sanitized private OTLP traces by immutable project identity.

Alloy remains the sanitization boundary. This final hop rejects retired or
removed projects, including batches that were queued before their deletion.
Tempo stores each project in an independently erasable tenant.
"""

import os
from collections import defaultdict
from uuid import UUID

import httpx2 as httpx
import psycopg
from fastapi import FastAPI, HTTPException, Request, Response
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
)

app = FastAPI(docs_url=None, openapi_url=None)
MAX_BODY = 2 * 1024 * 1024


def project_partition(project, *, for_read=False):
    with psycopg.connect(
        host=os.environ["POSTGRES_HOST"],
        dbname="platform",
        user="telemetry_catalog",
        password=os.environ["TELEMETRY_CATALOG_PASSWORD"],
        connect_timeout=2,
    ) as conn:
        row = conn.execute(
            (
                "SELECT project_id::text FROM telemetry_project_identities WHERE project=%s"
                if for_read
                else "SELECT project_id::text FROM telemetry_project_partitions WHERE project=%s"
            ),
            (project,),
        ).fetchone()
    return str(UUID(row[0])) if row else None


def partition(body, lookup=project_partition):
    batch = ExportTraceServiceRequest()
    batch.ParseFromString(body)
    result = defaultdict(ExportTraceServiceRequest)
    cache = {}
    for resource in batch.resource_spans:
        project = next(
            (
                a.value.string_value
                for a in resource.resource.attributes
                if a.key == "platform.project"
            ),
            None,
        )
        for scope in resource.scope_spans:
            for span in scope.spans:
                name = next(
                    (
                        a.value.string_value
                        for a in span.attributes
                        if a.key == "platform.project"
                    ),
                    project,
                )
                if name:
                    if name not in cache:
                        cache[name] = lookup(name)
                    tenant = cache[name]
                    if tenant is None:
                        continue
                else:
                    tenant = "platform"
                target = result[tenant].resource_spans.add()
                target.resource.CopyFrom(resource.resource)
                if name:
                    attribute = target.resource.attributes.add()
                    attribute.key = "platform.project_id"
                    attribute.value.string_value = tenant
                output = target.scope_spans.add()
                output.scope.CopyFrom(scope.scope)
                output.spans.add().CopyFrom(span)
    return {key: value.SerializeToString() for key, value in result.items()}


@app.get("/healthz")
def health():
    return {"status": "ok"}


@app.post("/v1/traces")
async def traces(request: Request):
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_BODY:
            raise HTTPException(413, "Trace batch is too large")
    batches = partition(bytes(body))
    with httpx.Client(timeout=3, trust_env=False, follow_redirects=False) as client:
        for tenant, value in batches.items():
            response = client.post(
                "http://tempo:4318/v1/traces",
                content=value,
                headers={
                    "Content-Type": "application/x-protobuf",
                    "X-Scope-OrgID": tenant,
                },
            )
            response.raise_for_status()
    return Response(content=b"", media_type="application/x-protobuf")
