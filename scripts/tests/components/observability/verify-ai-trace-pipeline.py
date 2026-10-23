#!/usr/bin/env python3
"""Read back real platform/OpenLIT spans through disposable Alloy and Tempo.

Uses synthetic provider responses; sends no OpenAI requests or live telemetry.
"""

import asyncio
import json
import os
import re
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import httpx
from app import ai_observability as obs
from app import main, tracing
from app.telemetry_gateway import sanitize
from app.trace_read import read as read_project_trace
from langchain_openai import ChatOpenAI
from openai import APIStatusError
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
)
from opentelemetry.sdk.trace.export import SpanExporter

ROOT = Path(__file__).resolve().parents[4]
MARKER = "synthetic-private-prompt-password-provider-response"
TEMPO_IMAGE = "grafana/tempo@sha256:3076b8dcdfb32fd6bc5ccef85e7b7313e6199b9cb84366257fc17ecb696db5fd"


def command(*arguments):
    result = subprocess.run(arguments, capture_output=True, timeout=60, check=False)
    if result.returncode:
        raise RuntimeError("Disposable trace fixture command failed")
    return result.stdout.decode().strip()


def wait(callback, seconds=45):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            result = callback()
            if result:
                return result
        except (OSError, ValueError, KeyError):
            pass
        time.sleep(0.25)
    raise AssertionError("Disposable trace readiness/readback timed out")


def verify_workload_trace(endpoint, query_port, opener):
    """Actual gateway sanitizer -> production Alloy -> Tempo -> scoped API read."""
    request = ExportTraceServiceRequest()
    resource = request.resource_spans.add()
    attribute = resource.resource.attributes.add()
    attribute.key = "platform.project"
    attribute.value.string_value = MARKER
    scope = resource.scope_spans.add()
    scope.scope.name = "io.quarkus.opentelemetry"
    scope.scope.version = "3.27.0"
    scope.scope.attributes.add().value.string_value = MARKER
    # Tempo search serializes trace IDs as unpadded hex. Exercise a leading
    # zero on every run while retaining a unique synthetic 120-bit suffix.
    trace_id, now = b"\x00" + uuid4().bytes[1:], time.time_ns()
    operations = (
        "chat",
        "text_completion",
        "generate_content",
        "embeddings",
        "execute_tool",
        "invoke_agent",
        "create_agent",
        "retrieval",
    )
    for index, operation in enumerate(("service", *operations)):
        span = scope.spans.add()
        span.trace_id, span.span_id = trace_id, (index + 1).to_bytes(8, "big")
        if index:
            span.parent_span_id = (1).to_bytes(8, "big")
        span.flags = 1
        span.name = (
            "langchain4j.aiservices.PrivateAssistant.privateMethod"
            if not index
            else "completion fixture-model"
        )
        span.start_time_unix_nano, span.end_time_unix_nano = now - 1000000, now
        span.status.code = 2 if operation == "execute_tool" else 1
        span.status.message = MARKER
        fields = {
            "gen_ai.prompt": MARKER,
            "gen_ai.completion": MARKER,
            "gen_ai.output.messages": MARKER,
            "gen_ai.tool.call.arguments": MARKER,
            "gen_ai.tool.call.result": MARKER,
            "gen_ai.response.id": MARKER,
            "gen_ai.client.estimated_cost": MARKER,
        }
        if index:
            fields.update(
                {
                    "gen_ai.operation.name": operation,
                    "gen_ai.system": "OPEN_AI",
                    "gen_ai.request.model": "fixture-model",
                    "gen_ai.response.model": "fixture-model-v2",
                    "gen_ai.usage.prompt_tokens": 12,
                    "gen_ai.usage.completion_tokens": 3,
                    "gen_ai.response.finish_reasons": "STOP",
                    "gen_ai.request.temperature": 0.5,
                    "gen_ai.request.top_p": 0.9,
                    "gen_ai.request.max_tokens": 128,
                }
            )
        if operation == "execute_tool":
            fields["gen_ai.tool.name"] = "lookup_weather"
            fields["error.type"] = "fixture.ProviderError"
        for key, value in fields.items():
            attr = span.attributes.add()
            attr.key = key
            if isinstance(value, str):
                attr.value.string_value = value
            elif type(value) is int:
                attr.value.int_value = value
            else:
                attr.value.double_value = value
        span.events.add().name = MARKER
    payload = sanitize(request.SerializeToString(), "fixture-ai", "web", now)
    with opener.open(
        urllib.request.Request(
            endpoint, data=payload, headers={"Content-Type": "application/x-protobuf"}
        ),
        timeout=5,
    ) as response:
        assert response.status == 200

    def stored():
        request = urllib.request.Request(
            f"http://127.0.0.1:{query_port}/api/v2/traces/{trace_id.hex()}",
            headers={"Accept": "application/json"},
        )
        with opener.open(request, timeout=3) as response:
            data = json.load(response)
        spans = [
            span
            for r in data.get("trace", {}).get("resourceSpans", [])
            for s in r.get("scopeSpans", [])
            for span in s.get("spans", [])
        ]
        return data if len(spans) == 9 else None

    data = wait(stored)
    assert MARKER not in json.dumps(data)
    spans = [
        span
        for r in data["trace"]["resourceSpans"]
        for s in r["scopeSpans"]
        for span in s["spans"]
    ]
    assert {s["name"] for s in spans} == {
        "application.ai." + op for op in ("service", *operations)
    }
    root = next(s for s in spans if s["name"] == "application.ai.service")
    assert all(s["parentSpanId"] == root["spanId"] for s in spans if s is not root)
    chat = next(s for s in spans if s["name"] == "application.ai.chat")
    fields = {a["key"]: a["value"] for a in chat["attributes"]}
    assert fields["gen_ai.request.model"]["stringValue"] == "fixture-model"
    assert fields["gen_ai.provider.name"]["stringValue"] == "openai"
    assert int(fields["gen_ai.usage.input_tokens"]["intValue"]) == 12
    assert (
        fields["gen_ai.response.finish_reasons"]["arrayValue"]["values"][0][
            "stringValue"
        ]
        == "stop"
    )
    assert not any(s.get("events") or s.get("status", {}).get("message") for s in spans)

    class Tempo:
        def open(self, request, timeout):
            return opener.open(
                urllib.request.Request(
                    request.full_url.replace(
                        "http://tempo:3200", f"http://127.0.0.1:{query_port}"
                    ),
                    headers={"Accept": "application/json"},
                ),
                timeout=timeout,
            )

    project = read_project_trace("fixture-ai", trace_id.hex(), Tempo())
    assert len(project["spans"]) == 9
    assert {s["name"] for s in project["spans"]} == {s["name"] for s in spans}
    assert any(
        s.get("attributes", {}).get("platform.ai.framework") == "langchain4j"
        for s in project["spans"]
    )
    assert read_project_trace("foreign", trace_id.hex(), Tempo()) is None
    assert MARKER not in json.dumps(project)
    for expression in (
        '{ resource.service.name = "fixture-ai.web" && span.gen_ai.request.model = "fixture-model" }',
        '{ resource.service.name = "fixture-ai.web" && span.platform.ai.framework = "langchain4j" }',
    ):

        def searchable(expression=expression):
            params = urllib.parse.urlencode(
                {
                    "q": expression,
                    "start": int(now / 1e9) - 60,
                    "end": int(time.time()) + 1,
                }
            )
            with opener.open(
                f"http://127.0.0.1:{query_port}/api/search?" + params, timeout=5
            ) as response:
                found = json.load(response)
            return any(
                t["traceID"].lower().zfill(32) == trace_id.hex()
                for t in found.get("traces", [])
            )

        wait(searchable)
    print(
        "PASS Quarkus/LangChain4j service and all AI operation spans through gateway sanitizer -> Alloy -> Tempo: model/framework searches, legacy aliases, token counts, scoped API reads, parentage and private-content removal verified."
    )


def run():
    identity = uuid4().hex[:10]
    tempo, alloy = "ai-trace-tempo-" + identity, "ai-trace-alloy-" + identity
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    exported = []

    class Capture(SpanExporter):
        def __init__(self, endpoint):
            self.delegate = OTLPSpanExporter(endpoint=endpoint, timeout=3)

        def export(self, spans):
            exported.extend(spans)
            return self.delegate.export(spans)

        def shutdown(self):
            self.delegate.shutdown()

    with tempfile.TemporaryDirectory(prefix="platform-ai-traces-") as directory:
        os.chmod(directory, 0o755)
        target = Path(directory)
        config = (ROOT / "infrastructure/monitoring/config.alloy").read_text()
        # Keep production trace processors/exporter; omit unrelated logs, metrics
        # and Kubernetes discovery. Both containers share this isolated namespace.
        config = config[
            config.index("// Private platform spans") : config.index(
                "// Direct metrics are independent"
            )
        ]
        # Alloy formatting uses tabs; exclude the metric receiver regardless of
        # indentation when selecting only the production trace processors.
        config = re.sub(
            r"(?m)^[ \t]*metrics[ \t]*=[ \t]*\[otelcol\.processor\.memory_limiter\.ai_metrics\.input\][ \t]*\n",
            "",
            config,
        )
        config = config.replace("http://tempo:4318", "http://127.0.0.1:4319")
        (target / "config.alloy").write_text(config)
        tempo_config = (
            (ROOT / "infrastructure/monitoring/tempo.yaml")
            .read_text()
            .replace("0.0.0.0:4318", "0.0.0.0:4319")
        )
        (target / "tempo.yaml").write_text(tempo_config)
        try:
            command(
                "docker",
                "run",
                "-d",
                "--name",
                tempo,
                "--memory",
                "768m",
                "--cpus",
                "1",
                "--user",
                "10001:10001",
                "--read-only",
                "--cap-drop",
                "ALL",
                "--tmpfs",
                "/data/tempo:rw,uid=10001,gid=10001,size=128m",
                "--tmpfs",
                "/var/tempo:rw,uid=10001,gid=10001,size=128m",
                "-p",
                "127.0.0.1::3200",
                "-p",
                "127.0.0.1::4318",
                "-v",
                f"{target}/tempo.yaml:/etc/tempo/tempo.yaml:ro",
                TEMPO_IMAGE,
                "-target=all",
                "-config.file=/etc/tempo/tempo.yaml",
            )
            query_port = int(
                command("docker", "port", tempo, "3200/tcp").rsplit(":", 1)[1]
            )
            otlp_port = int(
                command("docker", "port", tempo, "4318/tcp").rsplit(":", 1)[1]
            )
            command(
                "docker",
                "run",
                "-d",
                "--name",
                alloy,
                "--memory",
                "256m",
                "--cpus",
                "1",
                "--network",
                "container:" + tempo,
                "-v",
                f"{target}/config.alloy:/etc/alloy/config.alloy:ro",
                "grafana/alloy:v1.19.2",
                "run",
                "/etc/alloy/config.alloy",
            )

            def ready():
                with opener.open(
                    f"http://127.0.0.1:{query_port}/ready", timeout=2
                ) as response:
                    return response.status == 200

            wait(ready)
            wait(
                lambda: (
                    subprocess.run(
                        [
                            "docker",
                            "exec",
                            alloy,
                            "/usr/bin/bash",
                            "-c",
                            "exec 3<>/dev/tcp/127.0.0.1/4318",
                        ],
                        capture_output=True,
                        timeout=3,
                        check=False,
                    ).returncode
                    == 0
                )
            )
            endpoint = f"http://127.0.0.1:{otlp_port}/v1/traces"
            verify_workload_trace(endpoint, query_port, opener)
            with (
                patch.dict(
                    os.environ,
                    {
                        "PLATFORM_OTLP_ENDPOINT": "http://alloy:4318/v1/traces",
                        "PLATFORM_TRACE_SAMPLE_RATE": "1.0",
                        "PLATFORM_TRACE_SERVICE_NAME": "platform-api",
                    },
                ),
                patch.object(
                    tracing,
                    "OTLPSpanExporter",
                    side_effect=lambda **kwargs: Capture(endpoint),
                ),
                patch.object(
                    obs, "configure", side_effect=lambda provider: obs.install_openlit()
                ),
            ):
                tracing.configure()
            try:

                def respond(request):
                    if MARKER + "-failure" in request.content.decode():
                        return httpx.Response(
                            500,
                            json={"error": {"message": MARKER, "type": "server_error"}},
                        )
                    return httpx.Response(
                        200,
                        json={
                            "id": MARKER,
                            "object": "response",
                            "created_at": 1,
                            "model": "gpt-6.1-sol",
                            "status": "completed",
                            "error": None,
                            "output": [
                                {
                                    "id": MARKER,
                                    "type": "message",
                                    "role": "assistant",
                                    "status": "completed",
                                    "content": [
                                        {
                                            "type": "output_text",
                                            "text": MARKER,
                                            "annotations": [],
                                        }
                                    ],
                                }
                            ],
                            "usage": {
                                "input_tokens": 10,
                                "output_tokens": 2,
                                "total_tokens": 12,
                            },
                        },
                    )

                model = ChatOpenAI(
                    model="gpt-6.1-sol",
                    api_key="synthetic-only",
                    use_responses_api=True,
                    store=False,
                    max_retries=0,
                    http_client=httpx.Client(transport=httpx.MockTransport(respond)),
                )

                @main.app.get("/synthetic-ai-trace-fixture")
                async def fixture(fail: bool = False):
                    trace.get_current_span().set_attribute(
                        "unreviewed.private.attribute", MARKER
                    )
                    with (
                        obs.scope("fixture", "explain_application"),
                        tracing.span("platform.ai.run"),
                    ):
                        with tracing.span(
                            "platform.ai.tool",
                            **{"platform.ai.tool": "get_application"},
                        ):
                            pass
                        try:
                            model.invoke(MARKER + ("-failure" if fail else ""))
                        except APIStatusError:
                            return main.JSONResponse(
                                status_code=503,
                                content={"detail": "Synthetic provider failure"},
                            )
                    return {"status": "completed"}

                async def requests():
                    async with httpx.AsyncClient(
                        transport=httpx.ASGITransport(app=main.app),
                        base_url="http://fixture",
                    ) as client:
                        for index in range(100):
                            path = (
                                "/healthz"
                                if index < 90
                                else "/synthetic-ai-trace-fixture?fail="
                                + ("true" if index == 99 else "false")
                            )
                            response = await client.get(
                                path,
                                headers={
                                    "baggage": "password=" + MARKER,
                                    "traceparent": "00-"
                                    + "1" * 32
                                    + "-"
                                    + "2" * 16
                                    + "-00",
                                },
                            )
                            assert response.status_code == (503 if index == 99 else 200)

                asyncio.run(requests())
                # Trusted internal unsampled parents still suppress their child.
                parent = trace.NonRecordingSpan(
                    trace.SpanContext(1, 2, True, trace.TraceFlags(0))
                )
                with trace.use_span(parent), tracing.span("platform.operation.step"):
                    pass
                assert tracing._provider.force_flush(timeout_millis=10000)
            finally:
                tracing.shutdown()
            roots = [item for item in exported if item.name == "platform.http"]
            assert len(roots) == 100 and len({s.context.trace_id for s in roots}) == 100
            assert all(item.context.trace_id != int("1" * 32, 16) for item in roots)
            assert not any(item.name == "platform.operation.step" for item in exported)
            assert (
                len([item for item in exported if item.name == "platform.ai.model"])
                == 10
            )
            delivered = 0
            for root in roots:
                identity = f"{root.context.trace_id:032x}"

                def readback(identity=identity, root=root):
                    request = urllib.request.Request(
                        f"http://127.0.0.1:{query_port}/api/v2/traces/{identity}",
                        headers={"Accept": "application/json"},
                    )
                    with opener.open(request, timeout=3) as response:
                        data = json.load(response)
                    resources = data.get("trace", {}).get("resourceSpans", [])
                    found = [
                        s
                        for resource in resources
                        for scope in resource.get("scopeSpans", [])
                        for s in scope.get("spans", [])
                    ]
                    expected = sum(
                        item.context.trace_id == root.context.trace_id
                        for item in exported
                    )
                    return data if len(found) == expected else None

                data = wait(readback)
                assert MARKER not in json.dumps(data)
                spans = [
                    span
                    for resource in data["trace"]["resourceSpans"]
                    for scope in resource["scopeSpans"]
                    for span in scope["spans"]
                ]
                assert sum(s["name"] == "platform.http" for s in spans) == 1
                assert all(
                    not s.get("events") and not s.get("status", {}).get("message")
                    for s in spans
                )
                runs = [s for s in spans if s["name"] == "platform.ai.run"]
                if runs:
                    assert len(runs) == 1
                    children = [
                        s
                        for s in spans
                        if s["name"] in {"platform.ai.model", "platform.ai.tool"}
                    ]
                    assert len(children) == 2 and all(
                        s["parentSpanId"] == runs[0]["spanId"] for s in children
                    )
                delivered += 1
            print(
                f"PASS actual platform HTTP -> focused OpenLIT -> production Alloy -> Tempo: {delivered}/100 roots read back, 10 single model spans including provider failure; privacy, parentage and trusted unsampled-parent behavior verified. Local fixture only; 24-hour elapsed retention/capacity not claimed."
            )
        except Exception:
            for name in (alloy, tempo):
                result = subprocess.run(
                    ["docker", "logs", "--tail", "30", name],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
                print(result.stdout + result.stderr)
            raise
        finally:
            for name in (alloy, tempo):
                subprocess.run(
                    ["docker", "rm", "-f", "-v", name],
                    capture_output=True,
                    timeout=30,
                    check=False,
                )


if __name__ == "__main__":
    run()
