"""Bounded, project-authorized Loki reads; no client-supplied LogQL or backend URL."""
import json
import os
import re
from datetime import datetime, timezone

import httpx2 as httpx

from .manifests import validate_name

RETENTION_SECONDS = 7 * 86400
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
EVENT = re.compile(r"(application|request|job)\.(started|ready|completed|failed)\Z")
CORRELATION = re.compile(r"(?:[a-f0-9]{32}|[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12})?\Z")


def safe_event(message):
    """Defence in depth: allowlist again when reading administrative storage."""
    event = json.loads(message)
    if (not isinstance(event, dict) or not isinstance(event.get("event"), str)
            or not EVENT.fullmatch(event["event"])
            or event.get("level") not in ("debug", "info", "warning", "error")
            or not isinstance(event.get("correlationId", ""), str)
            or not CORRELATION.fullmatch(event.get("correlationId", ""))):
        raise ValueError("Invalid operational envelope")
    return {"event": event["event"], "level": event["level"], "correlationId": event.get("correlationId", "")}


def _time(value, default):
    if value is None:
        return default
    if re.fullmatch(r"[0-9]{19}", value):
        return int(value)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError()
        return int(parsed.timestamp() * 1_000_000_000)
    except (ValueError, OverflowError):
        raise ValueError("Log bounds require a UTC timestamp or nanosecond cursor") from None


def observe_retained_logs(project, log, tail=200, since_seconds=RETENTION_SECONDS,
                          component=None, instance=None, after=None, before=None,
                          now=None, client_factory=httpx.Client):
    validate_name(project)
    if component:
        validate_name(component)
    if not 1 <= tail <= 1000 or not 1 <= since_seconds <= RETENTION_SECONDS:
        raise ValueError("Invalid log limits")
    now = now or datetime.now(timezone.utc)
    end = int(now.timestamp() * 1_000_000_000)
    floor = end - RETENTION_SECONDS * 1_000_000_000
    start = max(floor, _time(after, end - since_seconds * 1_000_000_000) + (1 if after else 0))
    end = min(end, _time(before, end))
    if start > end:
        raise ValueError("Invalid log time range")
    labels = {"job": "kubernetes-workloads", "project": project, "namespace": "project-" + project}
    if component:
        labels["component"] = component
    if instance:
        labels["pod"] = instance
    query = "{" + ",".join(key + "=" + json.dumps(value) for key, value in labels.items()) + "}"
    result = {"state": "no_output", "reason": "NoLogLines", "lines": [], "truncated": False,
              "observed_at": now.isoformat(), "next_cursor": None,
              "retention": {"source": "loki", "state": "configured", "seconds": RETENTION_SECONDS,
                            "format": "operational-envelope-v1"}}
    try:
        with client_factory(timeout=5, follow_redirects=False, trust_env=False) as client:
            with client.stream("GET", os.environ.get("LOKI_URL", "http://loki:3100") + "/loki/api/v1/query_range",
                               params={"query": query, "start": str(start), "end": str(end),
                                       "direction": "forward", "limit": tail + 1}) as response:
                response.raise_for_status()
                content = bytearray()
                for chunk in response.iter_bytes():
                    content.extend(chunk)
                    if len(content) > MAX_RESPONSE_BYTES:
                        raise ValueError("Log response limit exceeded")
        data = json.loads(content)
        if data["status"] != "success" or data["data"]["resultType"] != "streams":
            raise ValueError("Invalid log response")
        lines = []
        for stream in data["data"]["result"]:
            # Backend filtering is not our authorization boundary. Check it again.
            if any(stream["stream"].get(key) != value for key, value in labels.items()):
                raise ValueError("Unexpected log stream")
            for entry in stream["values"]:
                timestamp = int(entry[0])
                if not start <= timestamp <= end:
                    raise ValueError("Unexpected log timestamp")
                event = safe_event(entry[1])
                # Loki's default query encoding flattens structured metadata into
                # the returned stream map. It is not necessarily an index label.
                metadata = entry[2] if len(entry) > 2 else stream["stream"]
                revision = str(metadata.get("revision", ""))
                operation_id = str(metadata.get("operation_id", ""))
                lines.append({"timestamp": str(timestamp), "pod": stream["stream"].get("pod", ""),
                              "container": stream["stream"].get("container", ""),
                              "component": stream["stream"].get("component", "app"),
                              "revision": revision if re.fullmatch(r"[0-9]{1,10}", revision) else None,
                              "operation_id": operation_id if re.fullmatch(r"[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}", operation_id) else None,
                              "message": json.dumps(event, separators=(",", ":"))})
        lines.sort(key=lambda line: int(line["timestamp"]))
        result.update(lines=lines[:tail], truncated=len(lines) > tail)
        if result["lines"]:
            result.update(state="ok", reason=None, next_cursor=result["lines"][-1]["timestamp"])
        return result
    except Exception as exc:
        log.error("Retained log query failed project=%s error_type=%s", project, type(exc).__name__)
        return {**result, "state": "unavailable", "reason": "CentralLogUnavailable", "lines": [],
                "next_cursor": None, "truncated": False}
