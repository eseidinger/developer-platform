"""Focused OpenLIT Responses instrumentation and bounded, content-free metrics.

Do not call openlit.init(): it enables unrelated instrumentors, global providers
and runtime pricing downloads. The pinned SDK's Responses wrapper is composed
with the platform tracer and reviewed metric sinks instead.
"""

import logging
import math
import os
import re
import time
from contextlib import contextmanager
from contextvars import ContextVar
from importlib.metadata import version
from threading import Lock

from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.metrics import Observation
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.metrics.view import ExplicitBucketHistogramAggregation, View
from opentelemetry.sdk.resources import Resource
from opentelemetry.trace import Status, StatusCode

from . import ai_pricing

_scope: ContextVar[dict[str, str] | None] = ContextVar(
    "ai_telemetry_scope", default=None
)
_projects = set()
_lock = Lock()
_provider = None
_instruments = {}
_wrapped = []
_series = set()
LATENCY_BUCKETS = (0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60, 90)
TOOLS = {
    "get_application",
    "get_deployments",
    "get_runtime_status",
    "get_configuration",
    "get_logs",
    "get_metrics",
    "get_traces",
    "get_documentation",
    "get_events",
    "get_dependencies",
}
KINDS = {"explain_application", "investigate_incident", "development_assistance"}
SAFE_SPAN_KEYS = {
    "gen_ai.operation.name",
    "gen_ai.provider.name",
    "gen_ai.request.model",
    "gen_ai.response.model",
    "gen_ai.usage.input_tokens",
    "gen_ai.usage.output_tokens",
}


def _project(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,31}", value):
        return "other"
    with _lock:
        if value not in _projects and len(_projects) >= 128:
            return "other"
        _projects.add(value)
    return value


def _emit(name, value, **labels):
    instrument = _instruments.get(name)
    if (
        instrument is None
        or not isinstance(value, (float, int))
        or not math.isfinite(value)
    ):
        return
    try:
        attrs = {**(_scope.get() or {}), **labels}
        key = (name, tuple(sorted(attrs.items())))
        with _lock:
            if key not in _series and len(_series) >= 1024:
                _instruments["platform_ai_cardinality_dropped"].add(1)
                return
            _series.add(key)
        (instrument.record if name.endswith("seconds") else instrument.add)(
            value, attrs
        )
    except Exception:
        # Telemetry failures must never fail the model, tools or approval flow.
        pass


@contextmanager
def scope(project, action):
    token = _scope.set(
        {"project": _project(project), "action": action if action in KINDS else "other"}
    )
    try:
        yield
    finally:
        _scope.reset(token)


@contextmanager
def operation(kind, *, tool=None):
    start = time.monotonic()
    labels = {"operation": kind}
    if tool is not None:
        labels["tool"] = tool if tool in TOOLS else "other"
    _emit("platform_ai_in_flight", 1, **labels)
    outcome = "completed"
    try:
        yield
    except Exception as error:
        outcome = "timeout" if "timeout" in type(error).__name__.lower() else "failed"
        raise
    finally:
        _emit("platform_ai_in_flight", -1, **labels)
        _emit("platform_ai_operations", 1, outcome=outcome, **labels)
        if kind != "model":
            _emit(
                "platform_ai_duration_seconds",
                time.monotonic() - start,
                outcome=outcome,
                **labels,
            )


def outcome(state, tool_calls):
    _emit(
        "platform_ai_runs",
        1,
        outcome=state if state in {"completed", "abstained", "failed"} else "failed",
    )
    _emit("platform_ai_tool_calls", tool_calls)


def usage(estimate):
    labels = {"provider": "openai", "model": "gpt-6.1-sol"}
    _emit(
        "platform_ai_usage_observations",
        1,
        completeness="complete" if estimate.complete else "unknown",
        **labels,
    )
    for token_type, value in (
        ("input", estimate.input_tokens),
        ("cached_input", estimate.cached_tokens),
        ("output", estimate.output_tokens),
    ):
        if value is not None:
            _emit("platform_ai_tokens", value, token_type=token_type, **labels)
    if estimate.usd is not None:
        _emit(
            "platform_ai_estimated_cost_usd",
            estimate.usd,
            pricing_version=ai_pricing.VERSION,
            **labels,
        )


class _SafeSpan:
    """Drop sensitive attributes/events before they ever enter an SDK span."""

    def __init__(self, span):
        self.span = span

    def set_attribute(self, key, value):
        if key in SAFE_SPAN_KEYS:
            if key.endswith("model"):
                value = value if value == "gpt-6.1-sol" else "other"
            elif key == "gen_ai.provider.name":
                value = "openai"
            elif key == "gen_ai.operation.name":
                value = "chat"
            elif type(value) is not int or value < 0:
                return
            self.span.set_attribute(key, value)

    def set_attributes(self, attributes):
        for key, value in attributes.items():
            self.set_attribute(key, value)

    def set_status(self, status, description=None):
        self.span.set_status(
            Status(status.status_code if isinstance(status, Status) else status)
        )

    def record_exception(self, *args, **kwargs):
        self.span.set_status(Status(StatusCode.ERROR))

    def add_event(self, *args, **kwargs):
        pass

    def is_recording(self):
        return self.span.is_recording()

    def get_span_context(self):
        return self.span.get_span_context()


class _SafeTracer:
    @contextmanager
    def start_as_current_span(self, name, **kwargs):
        from . import tracing

        with tracing.span(
            "platform.ai.model",
            **{"platform.project": (_scope.get() or {}).get("project", "other")},
        ) as span:
            yield _SafeSpan(span)


class _Discard:
    def record(self, *args, **kwargs):
        pass


class _ProviderDuration:
    def record(self, value, attributes=None, **kwargs):
        # OpenLIT owns provider duration; no SDK content/host/response-ID labels.
        error = (attributes or {}).get("error.type", "")
        outcome = (
            "timeout"
            if "timeout" in error.lower()
            else "failed"
            if error
            else "completed"
        )
        _emit(
            "platform_ai_duration_seconds",
            value,
            operation="model",
            outcome=outcome,
            provider="openai",
            model="gpt-6.1-sol",
        )


def configure(tracer_provider):
    global _provider
    if _provider is not None or tracer_provider is None:
        return
    endpoint = "http://alloy:4318/v1/metrics"
    reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=endpoint, timeout=2),
        export_interval_millis=15000,
        export_timeout_millis=3000,
    )
    _provider = MeterProvider(
        resource=Resource.create({"service.name": "platform-api"}),
        metric_readers=[reader],
        views=[
            View(
                instrument_name="*seconds",
                aggregation=ExplicitBucketHistogramAggregation(LATENCY_BUCKETS),
            )
        ],
    )
    meter = _provider.get_meter("developer-platform.ai", "1")
    for name in (
        "platform_ai_operations",
        "platform_ai_runs",
        "platform_ai_tool_calls",
        "platform_ai_tokens",
        "platform_ai_usage_observations",
        "platform_ai_estimated_cost_usd",
        "platform_ai_cardinality_dropped",
        "platform_ai_changes",
        "platform_ai_spans_exported",
    ):
        _instruments[name] = meter.create_counter(name)
    _instruments["platform_ai_in_flight"] = meter.create_up_down_counter(
        "platform_ai_in_flight"
    )
    _instruments["platform_ai_duration_seconds"] = meter.create_histogram(
        "platform_ai_duration_seconds", unit="s"
    )
    meter.create_observable_gauge(
        "platform_ai_heartbeat_timestamp_seconds",
        callbacks=[lambda options: [Observation(time.time())]],
    )
    meter.create_observable_gauge(
        "platform_ai_configured_root_sample_ratio",
        callbacks=[
            lambda options: [
                Observation(float(os.environ.get("PLATFORM_TRACE_SAMPLE_RATE", "1.0")))
            ]
        ],
    )
    install_openlit()


def install_openlit():
    if _wrapped:
        return
    from openlit._config import OpenlitConfig

    OpenlitConfig()
    OpenlitConfig.capture_message_content = False
    OpenlitConfig.disable_events = True
    OpenlitConfig.custom_span_attributes = {}
    OpenlitConfig.custom_metrics_attributes = {}
    from openai.resources.responses.responses import Responses
    from openlit.instrumentation.openai.openai import responses
    from wrapt import wrap_function_wrapper

    sdk_metrics = {
        "genai_client_usage_tokens": _Discard(),
        "genai_client_operation_duration": _ProviderDuration(),
        "genai_server_tbt": _Discard(),
        "genai_server_ttft": _Discard(),
    }
    # Intentionally no SDK cost producer: local normalized pricing is authoritative.
    # SDK diagnostics may embed exception text; expose failure counts instead.
    for name, logger in logging.Logger.manager.loggerDict.items():
        if name.startswith("openlit") and isinstance(logger, logging.Logger):
            logger.disabled = True
    args = (
        version("openai"),
        "platform",
        "platform-api",
        _SafeTracer(),
        {},
        False,
        sdk_metrics,
        False,
        None,
    )
    for method in ("create", "parse"):
        if hasattr(Responses, method):
            _wrapped.append((Responses, method, getattr(Responses, method)))
            wrap_function_wrapper(
                "openai.resources.responses.responses",
                "Responses." + method,
                responses(*args),
            )


def shutdown():
    global _provider
    for cls, name, original in reversed(_wrapped):
        setattr(cls, name, original)
    _wrapped.clear()
    _instruments.clear()
    if _provider is not None:
        _provider.shutdown()
        _provider = None
