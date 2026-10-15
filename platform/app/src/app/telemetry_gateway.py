"""Authenticated OTLP ingress for opted-in project Pods."""

import asyncio
import os
import re
import threading
import time
import urllib.request
from contextlib import asynccontextmanager

import psycopg
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response
from kubernetes import client, config
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest, ExportTraceServiceResponse,
)
from google.protobuf.message import DecodeError

from .manifests import validate_name

MAX_BODY = 262144
MAX_SPANS = 200
_METHODS = {"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"}
_held = threading.Lock()
_tokens = 131072.0
_last = time.monotonic()
_disk_full = False


def _rate_ok(size):
    global _tokens, _last
    with _held:
        now = time.monotonic()
        _tokens = min(131072.0, _tokens + (now - _last) * 16384)
        _last = now
        if size > _tokens:
            return False
        _tokens -= size
        return True


def _disk_ok():
    global _disk_full
    stats = os.statvfs("/run/tempo")
    if not 3 * 1024 ** 3 <= stats.f_blocks * stats.f_frsize <= 4 * 1024 ** 3:
        return False
    used = (stats.f_blocks - stats.f_bfree) * stats.f_frsize
    if used >= 3 * 1024 ** 3:
        _disk_full = True
    elif used < 2 * 1024 ** 3:
        _disk_full = False
    return not _disk_full


def _identity(review, pod, catalog):
    status = review.status
    if not status.authenticated or "platform-telemetry" not in (status.audiences or []):
        raise HTTPException(403, "Telemetry identity denied")
    username = status.user.username or ""
    match = re.fullmatch(r"system:serviceaccount:(project-[a-z0-9-]+):(telemetry-[a-z0-9-]+)", username)
    if not match:
        raise HTTPException(403, "Telemetry identity denied")
    namespace, account = match.groups()
    project = namespace.removeprefix("project-")
    component = account.removeprefix("telemetry-")
    try:
        validate_name(project)
        validate_name(component)
    except ValueError:
        raise HTTPException(403, "Telemetry identity denied") from None
    extra = status.user.extra or {}
    pod_names = extra.get("authentication.kubernetes.io/pod-name") or []
    pod_uids = extra.get("authentication.kubernetes.io/pod-uid") or []
    if len(pod_names) != 1 or len(pod_uids) != 1:
        raise HTTPException(403, "Pod-bound token required")
    if (str(pod.metadata.uid) != pod_uids[0] or pod.metadata.namespace != namespace
            or pod.metadata.name != pod_names[0] or pod.spec.service_account_name != account
            or pod.metadata.labels.get("app.kubernetes.io/name") != project
            or pod.metadata.labels.get("platform.example/component") != component):
        raise HTTPException(403, "Telemetry Pod mismatch")
    if not catalog(project, component):
        raise HTTPException(403, "Tracing is not active for this component")
    return project, component


def sanitize(payload: bytes, project: str, component: str, now_ns=None) -> bytes:
    incoming = ExportTraceServiceRequest()
    incoming.ParseFromString(payload)
    safe = ExportTraceServiceRequest()
    output = safe.resource_spans.add()
    for key, value in (("service.name", project + "." + component),
                       ("platform.project", project), ("platform.application", project),
                       ("platform.component", component)):
        attribute = output.resource.attributes.add()
        attribute.key = key
        attribute.value.string_value = value
    scope = output.scope_spans.add()
    scope.scope.name = "platform-verified-workload"
    now_ns = now_ns or time.time_ns()
    count = 0
    for resource_spans in incoming.resource_spans:
        for scope_spans in resource_spans.scope_spans:
            for span in scope_spans.spans:
                count += 1
                if count > MAX_SPANS or len(span.trace_id) != 16 or len(span.span_id) != 8 \
                        or not any(span.trace_id) or not any(span.span_id) or not span.flags & 1:
                    raise ValueError("Invalid or excessive spans")
                if (span.start_time_unix_nano <= 0 or span.end_time_unix_nano < span.start_time_unix_nano
                        or span.start_time_unix_nano < now_ns - 24 * 3600 * 10 ** 9
                        or span.end_time_unix_nano > now_ns + 5 * 60 * 10 ** 9
                        or span.end_time_unix_nano - span.start_time_unix_nano > 5 * 60 * 10 ** 9):
                    raise ValueError("Span time is outside the accepted window")
                clean = scope.spans.add()
                clean.trace_id = span.trace_id
                clean.span_id = span.span_id
                if len(span.parent_span_id) == 8:
                    clean.parent_span_id = span.parent_span_id
                clean.name = "application.span"
                clean.kind = span.kind
                clean.start_time_unix_nano = span.start_time_unix_nano
                clean.end_time_unix_nano = span.end_time_unix_nano
                clean.flags = 1
                if span.status.code == 2:
                    clean.status.code = 2
                for attribute in span.attributes:
                    if attribute.key == "http.request.method" and attribute.value.string_value in _METHODS:
                        item = clean.attributes.add()
                        item.key = attribute.key
                        item.value.string_value = attribute.value.string_value
                    elif attribute.key == "http.response.status_code" and 100 <= attribute.value.int_value <= 599:
                        item = clean.attributes.add()
                        item.key = attribute.key
                        item.value.int_value = attribute.value.int_value
    if count == 0:
        raise ValueError("Empty trace batch")
    result = safe.SerializeToString()
    if len(result) > MAX_BODY:
        raise ValueError("Sanitized batch exceeds limit")
    return result


def _catalog(project, component):
    with psycopg.connect(host=os.environ["POSTGRES_HOST"], dbname="platform", user="telemetry_catalog",
                         password=os.environ["TELEMETRY_CATALOG_PASSWORD"], connect_timeout=2) as conn:
        return bool(conn.execute("SELECT 1 FROM telemetry_component_opt_ins WHERE project=%s AND component=%s",
                                 (project, component)).fetchone())


def _forward(body):
    request = urllib.request.Request("http://alloy:4318/v1/traces", data=body, method="POST",
                                     headers={"Content-Type": "application/x-protobuf"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=2) as result:
        if result.status != 200:
            raise ValueError("Collector rejected batch")


@asynccontextmanager
async def lifespan(_app):
    config.load_kube_config(os.environ["KUBECONFIG"])
    _app.state.auth = client.AuthenticationV1Api()
    _app.state.core = client.CoreV1Api()
    yield


app = FastAPI(title="Private workload telemetry gateway", docs_url=None, openapi_url=None, lifespan=lifespan)


@app.get("/healthz")
def health():
    return {"state": "ready"}


@app.post("/v1/traces")
async def receive(request: Request):
    authorization = request.headers.get("authorization", "")
    if not authorization.startswith("Bearer ") or len(authorization) > 8192:
        raise HTTPException(401, "Pod-bound bearer token required")
    if request.headers.get("content-type", "").split(";", 1)[0] != "application/x-protobuf":
        raise HTTPException(415, "OTLP protobuf required")
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_BODY:
            raise HTTPException(413, "Trace batch exceeds limit")
    if not _rate_ok(len(body)):
        raise HTTPException(429, "Trace ingress rate exceeded")
    try:
        token = authorization[7:]
        review = await asyncio.to_thread(app.state.auth.create_token_review,
            {"apiVersion": "authentication.k8s.io/v1", "kind": "TokenReview",
             "spec": {"token": token, "audiences": ["platform-telemetry"]}})
        if not review.status.authenticated or "platform-telemetry" not in (review.status.audiences or []):
            raise HTTPException(403, "Telemetry identity denied")
        extra = review.status.user.extra or {} if review.status.user else {}
        names = extra.get("authentication.kubernetes.io/pod-name") or []
        username = review.status.user.username or "" if review.status.user else ""
        parts = username.split(":")
        if (len(parts) != 4 or not re.fullmatch(r"project-[a-z0-9-]{1,40}", parts[2])
                or len(names) != 1 or not re.fullmatch(r"[a-z0-9-]{1,63}", names[0])):
            raise HTTPException(403, "Pod-bound token required")
        pod = await asyncio.to_thread(app.state.core.read_namespaced_pod, names[0], parts[2])
        project, component = await asyncio.to_thread(_identity, review, pod, _catalog)
        if not _disk_ok():
            raise HTTPException(503, "Trace storage admission paused")
        safe = sanitize(bytes(body), project, component)
        await asyncio.to_thread(_forward, safe)
    except HTTPException:
        raise
    except (ValueError, DecodeError):
        raise HTTPException(422, "Invalid trace batch") from None
    except Exception:
        raise HTTPException(503, "Telemetry verification or collection unavailable") from None
    return Response(ExportTraceServiceResponse().SerializeToString(), media_type="application/x-protobuf")
