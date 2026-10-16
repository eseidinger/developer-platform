#!/usr/bin/env python3
"""Operator-only bounded Tempo readback; print verification metadata, never content.

Run inside the Platform API environment with a sampled AI trace ID argument.
"""
import argparse
import json
import re
import time
import urllib.request

ALLOWED = {
    "http.route", "http.request.method", "http.response.status_code", "platform.outcome",
    "platform.operation.id", "platform.operation.kind", "platform.operation.revision",
    "platform.step", "platform.resource_kind", "platform.error_type",
    "platform.ai.run_id", "platform.ai.kind", "platform.ai.model", "platform.ai.tool",
    "platform.ai.input_tokens", "platform.ai.output_tokens", "platform.ai.outcome",
    "platform.ai.tool_error_count",
}


def review(trace_id):
    if not re.fullmatch(r"[0-9a-f]{32}", trace_id) or int(trace_id, 16) == 0:
        raise ValueError("Invalid trace ID")
    now = int(time.time())
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(urllib.request.Request(
            f"http://tempo:3200/api/v2/traces/{trace_id}?start={now-86400}&end={now}",
            headers={"Accept": "application/json"}), timeout=5) as response:
        raw = response.read(1048577)
    assert len(raw) <= 1048576, "Trace exceeds review limit"
    spans = []
    for resource in json.loads(raw)["trace"]["resourceSpans"]:
        assert {a["key"] for a in resource["resource"].get("attributes", [])} <= {
            "service.name", "platform.project", "platform.application", "platform.component"}
        for scope in resource["scopeSpans"]:
            for span in scope["spans"]:
                assert {a["key"] for a in span.get("attributes", [])} <= ALLOWED
                assert not span.get("events") and not span.get("status", {}).get("message")
                assert int(span["endTimeUnixNano"]) >= int(span["startTimeUnixNano"])
                spans.append(span)
                assert len(spans) <= 200, "Too many spans for bounded review"
    runs = [s for s in spans if s["name"] == "platform.ai.run"]
    assert len(runs) == 1, "Expected one AI run"
    root = runs[0]
    children = [s for s in spans if s["name"] in {"platform.ai.model", "platform.ai.tool"}]
    assert children and all(s.get("parentSpanId") == root["spanId"] for s in children)
    names = [s["name"] for s in children]
    assert "platform.ai.model" in names and "platform.ai.tool" in names
    attributes = {a["key"]: a["value"] for a in root.get("attributes", [])}
    assert "platform.ai.run_id" in attributes and "platform.ai.kind" in attributes
    return {"ai_run_spans": 1, "model_spans": names.count("platform.ai.model"),
            "tool_spans": names.count("platform.ai.tool"), "parent_child_correlation": True,
            "allowlisted_attributes_only": True, "span_events_and_status_messages_empty": True}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace_id")
    print(json.dumps(review(parser.parse_args().trace_id)))
