"""Generate reproducible operator dashboards from reviewed PromQL definitions."""

import json
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "infrastructure/monitoring/dashboards"


def panel(index, title, expr, *, unit="short", description="", kind="timeseries", legend="{{job}} {{instance}} {{project}} {{component}}"):
    return {
        "id": index,
        "type": kind,
        "title": title,
        "description": description + " Missing data means collection or target discovery needs checking.",
        "datasource": {"type": "prometheus", "uid": "prometheus"},
        "gridPos": {"h": 8, "w": 12, "x": ((index - 1) % 2) * 12, "y": ((index - 1) // 2) * 8},
        "targets": [{"refId": "A", "expr": expr, "legendFormat": legend}],
        "fieldConfig": {"defaults": {"unit": unit}, "overrides": []},
        "options": {"legend": {"displayMode": "list", "placement": "bottom"}},
    }


DASHBOARDS = [
    ("platform-health-delivery", "Platform health and delivery", [
        ("Core scrape availability", 'up{job=~"prometheus|host|kubernetes-state|blackbox-exporter|alloy"}', "short",
         "Prometheus target availability (1 = scrape succeeded); this does not prove application health."),
        ("Public access boundary probes", 'probe_success{job="applications"}', "short",
         "A successful protected probe proves access boundary denial, not backend readiness."),
        ("Unavailable component replicas", 'kube_deployment_status_replicas_unavailable{namespace=~"project-.*"}', "short",
         "Kubernetes deployment status for project namespaces.", "{{namespace}} / {{deployment}}"),
        ("Discovery age", 'time() - platform_discovery_last_success_timestamp_seconds', "s",
         "Seconds since the platform published application target discovery."),
    ]),
    ("workloads-capacity", "Workloads and capacity", [
        ("Project pod readiness", 'kube_pod_status_ready{namespace=~"project-.*",condition="true"}', "short",
         "One means the pod is ready; zero means unready. Terminal pods may still appear.", "{{namespace}} / {{pod}}"),
        ("Desired deployment replicas", 'kube_deployment_spec_replicas{namespace=~"project-.*"}', "short",
         "Desired replicas, compare with unavailable replicas on the health dashboard.", "{{namespace}} / {{deployment}}"),
        ("Host memory available", 'node_memory_MemAvailable_bytes{job="host"}', "bytes",
         "Host available memory from node exporter, not a per-project quota."),
        ("Host CPU utilization", '1 - avg by (instance) (rate(node_cpu_seconds_total{job="host",mode="idle"}[5m]))', "percentunit",
         "Five-minute host CPU use. Database and per-container CPU signals are not currently collected."),
    ]),
    ("telemetry-security", "Telemetry pipeline and security", [
        ("Collector and backend scrape availability", 'up{job=~"alloy|prometheus|host|alertmanager"}', "short",
         "A missing series indicates scrape configuration or discovery failure."),
        ("Security events in 15-minute window", 'platform_security_events_in_window', "short",
         "Audit-derived bounded counts by category; no event content is exposed."),
        ("Security audit collection age", 'time() - platform_security_audit_collection_success', "s",
         "Seconds since audit metric collection last succeeded."),
        ("Trace filesystem used", 'node_filesystem_size_bytes{mountpoint="/var/lib/developer-platform/tempo"} - node_filesystem_avail_bytes{mountpoint="/var/lib/developer-platform/tempo"}', "bytes",
         "Four GiB bounded trace filesystem. Missing data means mount or node exporter failure."),
    ]),
]


def application_variables(metric="up"):
    def variable(name, query, sort=1):
        return {"name": name, "type": "query", "datasource": {"type": "prometheus", "uid": "prometheus"},
                "query": {"query": query, "refId": "PrometheusVariableQueryEditor-VariableQuery"},
                "refresh": 1, "sort": sort, "multi": False, "includeAll": False,
                "current": {"text": "", "value": ""}}
    return {"list": [
        variable("project", f'label_values({metric}{{job="application-metrics"}}, project)'),
        variable("application", f'label_values({metric}{{job="application-metrics",project="$project"}}, application)'),
        variable("component", f'label_values({metric}{{job="application-metrics",project="$project",application="$application"}}, component)'),
    ]}


SELECTOR = 'job="application-metrics",project="$project",application="$application",component="$component"'
LEGACY_DASHBOARDS = ("application-spring-boot", "application-quarkus", "application-fastapi")


def application_dashboard():
    def request_rate(extra=""):
        # Prefer Micrometer when both conventions are exported by one component.
        return (f'sum(rate(http_server_requests_seconds_count{{{SELECTOR}{extra}}}[5m])) or '
                f'sum(rate(http_requests_total{{{SELECTOR}{extra}}}[5m]))')

    def mean_duration(metric):
        return (f'sum(rate({metric}_sum{{{SELECTOR}}}[5m])) / '
                f'(sum(rate({metric}_count{{{SELECTOR}}}[5m])) > 0)')

    errors = request_rate(',status=~"5..|5xx"')
    panels = [
        panel(1, "Collection state", f'up{{{SELECTOR}}}',
              description="One is a successful private scrape; zero is a failed scrape."),
        panel(2, "Request rate", request_rate(), unit="reqps",
              description="Five-minute HTTP request rate. Supports Micrometer and Prometheus FastAPI Instrumentator; prefers Micrometer if both are present."),
        panel(3, "Server error rate", f'({errors}) or (({request_rate()}) * 0)', unit="reqps",
              description="Five-minute 5xx rate. Zero is shown only when a supported request counter is present."),
        panel(4, "Mean request duration",
              f'({mean_duration("http_server_requests_seconds")}) or ({mean_duration("http_request_duration_seconds")})',
              unit="s", description="Five-minute mean duration; no data until requests and a supported duration series exist."),
    ]
    return application_base("application-metrics", "Application metrics", panels)


def application_base(uid, title, panels, metric="up"):
    return {"uid": uid, "title": title, "schemaVersion": 41, "version": 1,
            "editable": False, "timezone": "browser", "refresh": "30s",
            "time": {"from": "now-1h", "to": "now"},
            "tags": ["developer-platform", "operator", "application-metrics"],
            "templating": application_variables(metric), "panels": panels}


def micrometer_dashboard():
    panels = []

    def add(title, definitions, unit="short", description=""):
        current = panel(len(panels) + 1, title, "", unit=unit,
                        description=description or "Micrometer JVM/process metrics for the selected component. Unsupported binders produce no data.")
        current["targets"] = [{"refId": chr(65 + i), "expr": expr, "legendFormat": legend}
                              for i, (legend, expr) in enumerate(definitions)]
        panels.append(current)

    def metric(name, extra=""):
        return f'{name}{{{SELECTOR}{extra}}}'

    add("Collection state", [("Scrape", metric("up"))],
        description="One is a successful private scrape. This dashboard requires Micrometer JVM binders and a JVM runtime.")
    add("JVM uptime", [("Uptime", f'max({metric("process_uptime_seconds")})')], "s")
    for area, title in (("heap", "Heap memory"), ("nonheap", "Non-heap memory")):
        definitions = []
        for kind in ("used", "committed", "max"):
            expression = metric("jvm_memory_" + kind + "_bytes", f',area="{area}"')
            if kind == "max":
                expression += " > 0"
            definitions.append((kind.capitalize(), f'sum({expression})'))
        add(title, definitions, "bytes",
            "Memory aggregated across pools in this area. Unknown or nonpositive maxima are omitted.")
    add("Memory by pool", [("{{area}} / {{id}}", metric("jvm_memory_used_bytes"))], "bytes")
    add("CPU usage", [("Process", f'max({metric("process_cpu_usage")})'),
                      ("System", f'max({metric("system_cpu_usage")})')], "percentunit")
    add("Threads", [(kind.capitalize(), f'sum({metric("jvm_threads_" + kind + "_threads")})')
                    for kind in ("live", "daemon", "peak")])
    add("Thread states", [("{{state}}", f'sum by (state) ({metric("jvm_threads_states_threads")})')])
    add("GC pause rate", [("{{gc}} / {{action}} / {{cause}}", f'sum by (gc,action,cause) (rate({metric("jvm_gc_pause_seconds_count")}[5m]))')], "ops")
    add("GC mean pause duration", [("Mean pause", f'sum(rate({metric("jvm_gc_pause_seconds_sum")}[5m])) / (sum(rate({metric("jvm_gc_pause_seconds_count")}[5m])) > 0)')], "s")
    add("GC maximum pause", [("{{gc}} / {{action}} / {{cause}}", metric("jvm_gc_pause_seconds_max"))], "s")
    add("GC allocation and promotion", [(kind.capitalize(), f'sum(rate({metric("jvm_gc_memory_" + kind + "_bytes_total")}[5m]))')
                                        for kind in ("allocated", "promoted")], "Bps")
    add("GC live and maximum data", [(kind.capitalize(), f'sum({metric("jvm_gc_" + kind + "_data_size_bytes")})')
                                     for kind in ("live", "max")], "bytes")
    add("GC overhead and memory pressure", [("GC overhead", metric("jvm_gc_overhead")),
                                            ("{{pool}} after GC", metric("jvm_memory_usage_after_gc"))], "percentunit")
    add("Loaded classes", [("Loaded", f'sum({metric("jvm_classes_loaded_classes")})')])
    add("Class unloading rate", [("Unloaded", f'sum(rate({metric("jvm_classes_unloaded_classes_total")}[5m]))')], "ops")
    add("Buffer memory", [("{{id}} / used", metric("jvm_buffer_memory_used_bytes")),
                           ("{{id}} / capacity", metric("jvm_buffer_total_capacity_bytes"))], "bytes")
    add("Buffer count", [("{{id}}", metric("jvm_buffer_count_buffers"))])
    add("File descriptors", [(kind.capitalize(), f'max({metric("process_files_" + kind + "_files")})')
                             for kind in ("open", "max")])
    return application_base("micrometer-jvm", "Micrometer JVM", panels, "jvm_memory_used_bytes")


def generate(check=False):
    ROOT.mkdir(parents=True, exist_ok=True)
    expected = {}
    for uid, title, definitions in DASHBOARDS:
        dashboard = {
            "uid": uid, "title": title, "schemaVersion": 41, "version": 1,
            "editable": False, "timezone": "browser", "refresh": "30s",
            "time": {"from": "now-1h", "to": "now"},
            "tags": ["developer-platform", "operator"],
            "panels": [panel(i, name, expr, unit=unit, description=description,
                             **({"legend": legend[0]} if legend else {}))
                       for i, (name, expr, unit, description, *legend) in enumerate(definitions, 1)],
        }
        expected[uid] = dashboard
    for dashboard in (application_dashboard(), micrometer_dashboard()):
        expected[dashboard["uid"]] = dashboard
    stale = []
    for uid, dashboard in expected.items():
        path = ROOT / f"{uid}.json"
        contents = json.dumps(dashboard, indent=2) + "\n"
        if check:
            if not path.exists() or path.read_text() != contents:
                stale.append(path.name)
        else:
            path.write_text(contents)
    for uid in LEGACY_DASHBOARDS:
        path = ROOT / f"{uid}.json"
        if check and path.exists():
            stale.append(path.name)
        elif not check:
            path.unlink(missing_ok=True)
    if stale:
        raise SystemExit("Stale dashboards; run scripts/generate-dashboards.py: " + ", ".join(stale))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    generate(parser.parse_args().check)
