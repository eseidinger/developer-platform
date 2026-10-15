"""Explicit, bounded platform spans. Never attach unreviewed request or provider data."""

import os
import re
from contextlib import contextmanager

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from opentelemetry.trace import Link, SpanContext, TraceFlags, TraceState


_TRACEPARENT = re.compile(r"^00-([0-9a-f]{32})-([0-9a-f]{16})-([01])1$")
_tracer = trace.get_tracer("developer-platform")
_provider = None


def sample_rate(value: str) -> float:
    try:
        rate = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("PLATFORM_TRACE_SAMPLE_RATE must be between 0 and 1") from exc
    if not 0 <= rate <= 1:
        raise ValueError("PLATFORM_TRACE_SAMPLE_RATE must be between 0 and 1")
    return rate


def configure() -> None:
    """Called before workers start; exporter failures never enter request handling."""
    global _provider, _tracer
    rate = sample_rate(os.environ.get("PLATFORM_TRACE_SAMPLE_RATE", "0.1"))
    endpoint = os.environ.get("PLATFORM_OTLP_ENDPOINT")
    if not endpoint:
        return
    if not endpoint.startswith("http://alloy:4318/"):
        raise ValueError("PLATFORM_OTLP_ENDPOINT must use the private Alloy endpoint")
    _provider = TracerProvider(
        resource=Resource.create({"service.name": "platform-api"}),
        sampler=ParentBased(TraceIdRatioBased(rate)),
    )
    _provider.add_span_processor(BatchSpanProcessor(
        OTLPSpanExporter(endpoint=endpoint, timeout=2),
        max_queue_size=512, max_export_batch_size=128, schedule_delay_millis=2000,
    ))
    _tracer = _provider.get_tracer("developer-platform")


def shutdown() -> None:
    global _provider
    if _provider is not None:
        _provider.shutdown()
        _provider = None


def trace_id() -> str | None:
    context = trace.get_current_span().get_span_context()
    return f"{context.trace_id:032x}" if context.is_valid and context.trace_flags.sampled else None


def annotate(key: str, value: str | int) -> None:
    # Only call with a reviewed literal key and a bounded, non-sensitive value.
    trace.get_current_span().set_attribute(key, value)


def current_traceparent() -> str | None:
    context = trace.get_current_span().get_span_context()
    if not context.is_valid or not context.trace_flags.sampled:
        return None
    return f"00-{context.trace_id:032x}-{context.span_id:016x}-01"


def origin_link(value: str | None) -> list[Link]:
    match = _TRACEPARENT.fullmatch(value) if isinstance(value, str) else None
    if not match or int(match[1], 16) == 0 or int(match[2], 16) == 0:
        return []
    return [Link(SpanContext(int(match[1], 16), int(match[2], 16),
                             is_remote=True, trace_flags=TraceFlags(1),
                             trace_state=TraceState()))]


@contextmanager
def span(name: str, *, links=None, **safe_attributes):
    with _tracer.start_as_current_span(name, links=links or [],
                                       record_exception=False, set_status_on_exception=False) as active:
        for key, value in safe_attributes.items():
            if isinstance(value, (str, int, bool, float)):
                active.set_attribute(key, value)
        yield active
