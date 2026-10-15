"""Generate reproducible operator dashboards from reviewed PromQL definitions."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "infrastructure/monitoring/dashboards"


def panel(index, title, expr, *, unit="short", description="", kind="timeseries"):
    return {
        "id": index,
        "type": kind,
        "title": title,
        "description": description + " Missing data means collection or target discovery needs checking.",
        "datasource": {"type": "prometheus", "uid": "prometheus"},
        "gridPos": {"h": 8, "w": 12, "x": ((index - 1) % 2) * 12, "y": ((index - 1) // 2) * 8},
        "targets": [{"refId": "A", "expr": expr, "legendFormat": "{{job}} {{instance}} {{project}} {{component}}"}],
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
         "Kubernetes deployment status for project namespaces."),
        ("Discovery age", 'time() - platform_discovery_last_success_timestamp_seconds', "s",
         "Seconds since the platform published application target discovery."),
    ]),
    ("workloads-capacity", "Workloads and capacity", [
        ("Project pod readiness", 'kube_pod_status_ready{namespace=~"project-.*",condition="true"}', "short",
         "One means the pod is ready; zero means unready. Terminal pods may still appear."),
        ("Desired deployment replicas", 'kube_deployment_spec_replicas{namespace=~"project-.*"}', "short",
         "Desired replicas, compare with unavailable replicas on the health dashboard."),
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


def application_variables():
    def variable(name, query, sort=1):
        return {"name": name, "type": "query", "datasource": {"type": "prometheus", "uid": "prometheus"},
                "query": {"query": query, "refId": "PrometheusVariableQueryEditor-VariableQuery"},
                "refresh": 1, "sort": sort, "multi": False, "includeAll": False,
                "current": {"text": "", "value": ""}}
    return {"list": [
        variable("project", 'label_values(up{job="application-metrics"}, project)'),
        variable("application", 'label_values(up{job="application-metrics",project="$project"}, application)'),
        variable("component", 'label_values(up{job="application-metrics",project="$project",application="$application"}, component)'),
    ]}


def framework_dashboard(framework, metric):
    selector = 'job="application-metrics",project="$project",application="$application",component="$component"'
    requests = f'{metric}_count' if metric != "http_requests_total" else metric
    duration = "http_request_duration_seconds" if framework == "FastAPI" else "http_server_requests_seconds"
    panels = [
        panel(1, "Collection state", f'up{{{selector}}}',
              description="One is a successful private scrape; zero is a failed scrape."),
        panel(2, "Request rate", f'sum(rate({requests}{{{selector}}}[5m]))', unit="reqps",
              description="Five-minute request rate from the framework's HTTP server counter."),
        panel(3, "Server error rate", f'sum(rate({requests}{{{selector},status=~"5..|5xx"}}[5m]))', unit="reqps",
              description="Five-minute 5xx rate; an empty panel can mean no error series was emitted."),
        panel(4, "Mean request duration",
              f'sum(rate({duration}_sum{{{selector}}}[5m])) / sum(rate({duration}_count{{{selector}}}[5m]))',
              unit="s", description="Five-minute mean duration; no data when no duration series exists."),
    ]
    return {"uid": "application-" + framework.lower().replace(" ", "-"),
            "title": framework + " application metrics", "schemaVersion": 41, "version": 1,
            "editable": False, "timezone": "browser", "refresh": "30s",
            "time": {"from": "now-1h", "to": "now"},
            "tags": ["developer-platform", "operator", "application-metrics"],
            "templating": application_variables(), "panels": panels}


def generate():
    ROOT.mkdir(parents=True, exist_ok=True)
    for uid, title, definitions in DASHBOARDS:
        dashboard = {
            "uid": uid, "title": title, "schemaVersion": 41, "version": 1,
            "editable": False, "timezone": "browser", "refresh": "30s",
            "time": {"from": "now-1h", "to": "now"},
            "tags": ["developer-platform", "operator"],
            "panels": [panel(i, name, expr, unit=unit, description=description)
                       for i, (name, expr, unit, description) in enumerate(definitions, 1)],
        }
        (ROOT / f"{uid}.json").write_text(json.dumps(dashboard, indent=2) + "\n")
    for framework, metric in (("Spring Boot", "http_server_requests_seconds"),
                              ("Quarkus", "http_server_requests_seconds"),
                              ("FastAPI", "http_requests_total")):
        dashboard = framework_dashboard(framework, metric)
        (ROOT / f"{dashboard['uid']}.json").write_text(json.dumps(dashboard, indent=2) + "\n")


if __name__ == "__main__":
    generate()
