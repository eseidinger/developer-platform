"""Fixed, project-scoped Prometheus reads; no caller-supplied PromQL or series labels."""

import json
import math
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from .manifests import validate_name

MAX_RESPONSE_BYTES = 65536


def _query(project: str, component: str, expression: str, opener=None) -> float | None:
    url = os.environ.get("PROMETHEUS_URL", "http://prometheus:9090").rstrip("/")
    if url != "http://prometheus:9090":
        raise ValueError("Prometheus must use the private monitoring endpoint")
    request = urllib.request.Request(url + "/api/v1/query?" + urllib.parse.urlencode({"query": expression}))
    opener = opener or urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=2) as response:
        raw = response.read(MAX_RESPONSE_BYTES + 1)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError("Prometheus response exceeds limit")
    body = json.loads(raw)
    if body.get("status") != "success" or body.get("data", {}).get("resultType") != "vector":
        raise ValueError("Unexpected Prometheus response")
    result = body["data"].get("result", [])
    if len(result) > 1:
        raise ValueError("Unaggregated Prometheus response")
    value = float(result[0]["value"][1]) if result else None
    if value is not None and not math.isfinite(value):
        raise ValueError("Non-finite Prometheus sample")
    return value


def observe(project: str, component: str, opener=None) -> dict:
    validate_name(project)
    validate_name(component)
    selector = f'job="application-metrics",project="{project}",component="{component}"'
    now = datetime.now(timezone.utc).isoformat()
    result = {"project": project, "component": component, "observed_at": now,
              "window_seconds": 300, "source": "prometheus:application-metrics"}
    try:
        up = _query(project, component, f"up{{{selector}}}", opener)
        if up is None:
            return {**result, "state": "missing", "reason": "NoScrapeTarget"}
        if up != 1:
            return {**result, "state": "collection_failed", "reason": "ScrapeFailed"}
        requests = _query(project, component,
            f'sum(rate({{__name__=~"http_server_requests_seconds_count|http_requests_total",{selector}}}[5m]))', opener)
        errors = _query(project, component,
            f'sum(rate({{__name__=~"http_server_requests_seconds_count|http_requests_total",{selector},status=~"5..|5xx"}}[5m]))', opener)
        duration_sum = _query(project, component,
            f'sum(rate({{__name__=~"http_server_requests_seconds_sum|http_request_duration_seconds_sum",{selector}}}[5m]))', opener)
        duration_count = _query(project, component,
            f'sum(rate({{__name__=~"http_server_requests_seconds_count|http_request_duration_seconds_count",{selector}}}[5m]))', opener)
    except (OSError, ValueError, KeyError, TypeError, IndexError, json.JSONDecodeError):
        return {**result, "state": "unavailable", "reason": "PrometheusUnavailable"}
    if requests is None:
        return {**result, "state": "missing", "reason": "NoSupportedRequestSeries"}
    return {**result, "state": "ok", "request_rate_per_second": requests,
            "server_error_rate_per_second": errors,
            "mean_request_duration_seconds": (duration_sum / duration_count
                                              if duration_sum is not None and duration_count else None)}
