from datetime import datetime, timezone
from typing import Any

STALE_AFTER_SECONDS = 120
_CPU = {"n": 1e-6, "u": 1e-3, "m": 1.0, "": 1000.0}
_MEMORY = {"Ki": 1024, "Mi": 1024 ** 2, "Gi": 1024 ** 3, "Ti": 1024 ** 4, "k": 1000, "K": 1000,
           "M": 1000 ** 2, "G": 1000 ** 3, "T": 1000 ** 4, "": 1}


def _split(value: str, units: dict) -> tuple[float, float]:
    for suffix in sorted(units, key=len, reverse=True):
        if suffix and value.endswith(suffix):
            return float(value[:-len(suffix)]), units[suffix]
    return float(value), units[""]


def parse_cpu(value: str) -> float:
    number, factor = _split(str(value), _CPU)
    return number * factor


def parse_memory(value: str) -> int:
    number, factor = _split(str(value), _MEMORY)
    return int(number * factor)


def _get(value: Any, name: str):
    return value[name] if isinstance(value, dict) else getattr(value, name)


def _result(state: str, reason: str | None, now: datetime, pods=None, totals=None) -> dict[str, Any]:
    return {"state": state, "reason": reason, "pods": pods or [], "totals": totals,
            "stale_after_seconds": STALE_AFTER_SECONDS, "observed_at": now.isoformat()}


def observe_usage(runtime: Any, project: str, log, now: datetime | None = None) -> dict[str, Any]:
    """Report current CPU and memory per pod from the Kubernetes metrics API.

    `state` is `ok`, `stale` (samples older than the freshness limit), `missing` (the metrics API
    answered but holds no samples) or `unavailable` (the metrics API could not be queried).
    """
    now = now or datetime.now(timezone.utc)
    if runtime is None:
        return _result("unavailable", "MetricsApiUnavailable", now)
    try:
        response = runtime.resources.get(api_version="metrics.k8s.io/v1beta1", kind="PodMetrics").get(
            namespace="project-" + project)
        items = _get(response, "items") or []
    except Exception as exc:
        log.error("Pod metrics query failed project=%s error_type=%s", project, type(exc).__name__)
        return _result("unavailable", "MetricsApiUnavailable", now)
    if not items:
        return _result("missing", "NoMetricsForProject", now)
    try:
        pods, oldest = [], 0.0
        for item in items:
            sampled = datetime.fromisoformat(str(_get(item, "timestamp")).replace("Z", "+00:00"))
            oldest = max(oldest, (now - sampled).total_seconds())
            containers = _get(item, "containers") or []
            pods.append({
                "name": _get(_get(item, "metadata"), "name"),
                "cpu_millicores": sum(parse_cpu(_get(_get(c, "usage"), "cpu")) for c in containers),
                "memory_bytes": sum(parse_memory(_get(_get(c, "usage"), "memory")) for c in containers),
                "sampled_at": sampled.isoformat()})
    except Exception as exc:
        log.error("Pod metrics malformed project=%s error_type=%s", project, type(exc).__name__)
        return _result("unavailable", "MetricsApiUnavailable", now)
    pods.sort(key=lambda p: p["name"])
    totals = {"cpu_millicores": sum(p["cpu_millicores"] for p in pods),
              "memory_bytes": sum(p["memory_bytes"] for p in pods)}
    if oldest > STALE_AFTER_SECONDS:
        return _result("stale", "SampleOlderThan%ds" % STALE_AFTER_SECONDS, now, pods, totals)
    return _result("ok", None, now, pods, totals)
