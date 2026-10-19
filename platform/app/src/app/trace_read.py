"""Fixed, project-filtered Tempo trace read. Never proxy raw trace documents."""

import base64
import json
import re
import time
import urllib.error
import urllib.request

from . import workload_trace


class TraceUnavailable(Exception):
    pass


def read(project: str, trace_id: str, opener=None, now=None) -> dict | None:
    if not re.fullmatch(r"[0-9a-f]{32}", trace_id) or int(trace_id, 16) == 0:
        raise ValueError("Invalid trace ID")
    now = int(time.time() if now is None else now)
    url = f"http://tempo:3200/api/v2/traces/{trace_id}?start={now - 86400}&end={now}"
    opener = opener or urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(urllib.request.Request(url, headers={"Accept": "application/json"}), timeout=2) as response:
            raw = response.read(1048577)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise TraceUnavailable() from None
    except (OSError, TimeoutError):
        raise TraceUnavailable() from None
    if len(raw) > 1048576:
        raise TraceUnavailable()
    try:
        source = json.loads(raw)
        spans = []
        for resource in source["trace"]["resourceSpans"]:
            attributes = {a["key"]: a["value"].get("stringValue") for a in resource["resource"]["attributes"]}
            if attributes.get("platform.project") != project:
                continue
            component = attributes.get("platform.component")
            if not isinstance(component, str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,31}", component):
                continue
            for scope in resource["scopeSpans"]:
                for span in scope["spans"]:
                    if base64.b64decode(span["traceId"]).hex() != trace_id:
                        continue
                    start = int(span["startTimeUnixNano"])
                    end = int(span["endTimeUnixNano"])
                    if not (now - 86400) * 10 ** 9 <= start <= end <= (now + 60) * 10 ** 9:
                        continue
                    result = {"component": component, "span_id": base64.b64decode(span["spanId"]).hex(),
                              "parent_span_id": base64.b64decode(span.get("parentSpanId", "")).hex(),
                              "start_time_unix_nano": start, "end_time_unix_nano": end,
                              "name": "application.span"}
                    fields = {a["key"]: workload_trace.json_value(a["value"])
                              for a in span.get("attributes", []) if a["key"] in workload_trace.INPUT_KEYS}
                    instrument = scope.get("scope", {})
                    scope_name, version = workload_trace.instrumentation(instrument.get("name"), instrument.get("version"))
                    fields = workload_trace.attributes(fields, scope_name)
                    result["name"] = workload_trace.span_name(fields, span.get("name"))
                    if fields:
                        result["attributes"] = fields
                    if scope_name != "platform-verified-workload":
                        result["instrumentation"] = {"name": scope_name, **({"version": version} if version else {})}
                    status_code = span.get("status", {}).get("code")
                    if isinstance(status_code, str):
                        status_code = {"STATUS_CODE_UNSET":0, "STATUS_CODE_OK":1, "STATUS_CODE_ERROR":2}.get(status_code)
                    if type(status_code) is int and status_code in {0, 1, 2}:
                        result["status"] = status_code
                    kind = span.get("kind")
                    if isinstance(kind, str):
                        kind = {"SPAN_KIND_UNSPECIFIED":0, "SPAN_KIND_INTERNAL":1, "SPAN_KIND_SERVER":2,
                                "SPAN_KIND_CLIENT":3, "SPAN_KIND_PRODUCER":4, "SPAN_KIND_CONSUMER":5}.get(kind)
                    if type(kind) is int and 0 <= kind <= 5:
                        result["kind"] = kind
                    method = fields.get("http.request.method")
                    status = fields.get("http.response.status_code")
                    if method:
                        result["method"] = method
                    if status is not None:
                        result["status_code"] = status
                    spans.append(result)
                    if len(spans) > 200:
                        raise TraceUnavailable()
    except (KeyError, TypeError, ValueError, OverflowError, json.JSONDecodeError):
        raise TraceUnavailable() from None
    if not spans:
        return None
    output = {"project": project, "trace_id": trace_id, "spans": spans,
              "window_seconds": 86400, "sampled": True}
    if len(json.dumps(output).encode()) > 65536:
        raise TraceUnavailable()
    return output
