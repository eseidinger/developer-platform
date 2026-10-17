"""Generate reproducible operator dashboards from reviewed PromQL definitions."""

import json
import argparse
from urllib.parse import urlencode
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
        ("Core scrape availability", 'up{job=~"prometheus|postgres|host|kubernetes-state|kubernetes-cadvisor|blackbox-exporter|alloy"}', "short",
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
         "Five-minute host CPU use across the platform host."),
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


def augment_capacity(dashboard):
    dashboard["templating"] = {"list": [{
        "name": "namespace", "label": "Project namespace", "type": "query",
        "datasource": {"type": "prometheus", "uid": "prometheus"},
        "query": {"query": 'label_values(kube_pod_info{job="kubernetes-state",namespace=~"project-.+"}, namespace)',
                  "refId": "PrometheusVariableQueryEditor-VariableQuery"},
        "refresh": 1, "sort": 1, "multi": True, "includeAll": True,
        "allValue": "project-.+", "current": {"text": "All", "value": "$__all"},
    }]}
    for current in dashboard["panels"][:2]:
        current["targets"][0]["expr"] = current["targets"][0]["expr"].replace('namespace=~"project-.*"', 'namespace=~"$namespace"')
    for scope in ("pod", "deployment"):
        for resource, unit, usage, suffix in (
            ("CPU", "cores", "cpu_usage_cores", "cpu"),
            ("memory", "bytes", "memory_working_set_bytes", "memory"),
        ):
            current = panel(len(dashboard["panels"]) + 1, f"{scope.capitalize()} {resource}: usage, requests and limits", "", unit=unit,
                            description="Active pods only. Steady-state container totals include native tracing sidecars, excluding ordinary startup init containers and pod overhead. CPU is measured in cores; memory usage is working set. Limits are absent if any container (or deployment pod) lacks a positive limit. These are configured totals, not scheduler admission or peak startup requirements.")
            definitions = [("Usage", usage), ("Requests", f"{suffix}_requests_{unit}"), ("Limits", f"{suffix}_limits_{unit}")]
            current["targets"] = [{"refId": chr(65 + i),
                                   "expr": f'platform:{scope}_{metric}:sum{{namespace=~"$namespace"}}',
                                   "legendFormat": "{{namespace}} / {{" + scope + "}} — " + label}
                                  for i, (label, metric) in enumerate(definitions)]
            dashboard["panels"].append(current)
    dashboard["panels"].append(panel(len(dashboard["panels"]) + 1, "Container usage collection", 'up{job="kubernetes-cadvisor"}',
                                      description="TLS-verified kubelet cAdvisor scrape by node; zero means usage collection failed.", legend="{{node}}"))
    disk = 'job="host",device=~"/dev/.+",fstype!~"tmpfs|devtmpfs|overlay|squashfs"'
    size = f'node_filesystem_size_bytes{{{disk}}}'
    available = f'node_filesystem_avail_bytes{{{disk}}}'
    dashboard["panels"].append(panel(len(dashboard["panels"]) + 1, "Host storage used", f'1 - ({available} / ({size} > 0))', unit="percentunit",
                                      description="Filesystem space unavailable to an unprivileged process, including reserved blocks. Disk filesystems only; independent of project selection.", legend="{{instance}} {{mountpoint}}"))
    current = panel(len(dashboard["panels"]) + 1, "Host storage capacity and available space", "", unit="bytes",
                    description="Disk filesystem total capacity and space available to an unprivileged process. Independent of project selection.")
    current["targets"] = [{"refId": "A", "expr": size, "legendFormat": "{{mountpoint}} — Capacity"},
                          {"refId": "B", "expr": available, "legendFormat": "{{mountpoint}} — Available"}]
    dashboard["panels"].append(current)
    dashboard["panels"].append(panel(len(dashboard["panels"]) + 1, "Host inode usage",
                                      f'1 - (node_filesystem_files_free{{{disk}}} / (node_filesystem_files{{{disk}}} > 0))', unit="percentunit",
                                      description="Fraction of inodes used on disk filesystems reporting inode capacity. Independent of project selection.", legend="{{instance}} {{mountpoint}}"))


def postgres_dashboard():
    selected = 'job="postgres",datname="$database"'
    panels = []

    def add(title, definitions, unit="short", description=""):
        current = panel(len(panels) + 1, title, "", unit=unit, description=description)
        current["targets"] = [{"refId": chr(65 + i), "expr": expr, "legendFormat": label}
                              for i, (label, expr) in enumerate(definitions)]
        panels.append(current)

    add("Collection and database availability", [("Exporter scrape", 'up{job="postgres"}'), ("Database connection", 'pg_up{job="postgres"}'),
                                                ("Collection error (1 = error)", 'pg_exporter_last_scrape_error{job="postgres"}')],
        description="Shared exporter and database health. Zero collection errors is healthy; missing series is not success.")
    add("Server connection usage", [("Connections", 'sum(pg_stat_database_numbackends{job="postgres"})'),
                                    ("Server limit", 'max(pg_platform_settings_max_connections{job="postgres"})')],
        description="Shared PostgreSQL server across all databases. The limit includes reserved connection slots; it is not a project quota.")
    add("Server connection-limit utilization", [("Shared utilization", 'sum(pg_stat_database_numbackends{job="postgres"}) / (max(pg_platform_settings_max_connections{job="postgres"}) > 0)')], "percentunit",
        "Shared server utilization against max_connections, including reserved capacity.")
    add("Server uptime", [("Uptime", 'time() - pg_postmaster_start_time_seconds{job="postgres"}')], "s", "Shared server time since postmaster start.")
    add("Database connections", [("{{state}}", f'pg_platform_activity_connections{{{selected}}}')],
        description="Selected database client connections by state, excluding the monitoring query.")
    add("Database configured connection limit", [("Positive database limit", f'pg_database_connection_limit{{{selected}}} > 0')],
        description="Only a positive per-database limit is shown. PostgreSQL -1 means no separate database limit; the server limit still applies.")
    add("Database size", [("{{datname}}", f'pg_database_size_bytes{{{selected}}}')], "bytes", "Selected database on-disk size; not the host's free space.")
    add("Transactions and rollbacks", [(label, f'rate(pg_stat_database_{metric}{{{selected}}}[5m])')
                                      for label, metric in [("Commits", "xact_commit"), ("Rollbacks", "xact_rollback")]], "ops",
        "Five-minute transaction rates for the selected database.")
    hits = f'rate(pg_stat_database_blks_hit{{{selected}}}[5m])'
    reads = f'rate(pg_stat_database_blks_read{{{selected}}}[5m])'
    add("Database buffer cache hit ratio", [("Hit ratio", f'{hits} / (({hits} + {reads}) > 0)')], "percentunit",
        "PostgreSQL shared-buffer hit ratio; excludes the OS cache. No ratio until block activity exists.")
    add("Database block reads", [("Disk reads", reads), ("Buffer hits", hits)], "ops", "Five-minute block read rates.")
    add("Temporary data written", [("Temporary bytes/s", f'rate(pg_stat_database_temp_bytes{{{selected}}}[5m])')], "Bps", "Selected database temporary-file write rate.")
    add("Deadlocks and temporary files", [(label, f'rate(pg_stat_database_{metric}{{{selected}}}[5m])')
                                         for label, metric in [("Deadlocks/s", "deadlocks"), ("Temporary files/s", "temp_files")]], "ops", "Five-minute database counter rates.")
    add("Database locks", [("{{mode}}", f'pg_locks_count{{{selected}}}')], description="Current locks by lock mode, including granted and waiting locks.")
    add("Database lock waits", [("{{state}}", f'pg_platform_activity_lock_waits{{{selected}}}')], description="Client connections waiting for a lock; no SQL text or session identities are collected.")
    add("Oldest open transaction", [("{{state}}", f'pg_platform_activity_max_transaction_seconds{{{selected}}}')], "s", "Age by client connection state; zero means no open transaction in that state.")
    dashboard = {"uid": "postgresql", "title": "PostgreSQL", "schemaVersion": 41, "version": 1,
                 "editable": False, "timezone": "browser", "refresh": "30s",
                 "time": {"from": "now-1h", "to": "now"}, "tags": ["developer-platform", "operator", "postgresql"], "panels": panels}
    dashboard["templating"] = {"list": [{"name": "database", "label": "Database", "type": "query",
        "datasource": {"type": "prometheus", "uid": "prometheus"},
        "query": {"query": 'label_values(pg_database_size_bytes{job="postgres"}, datname)', "refId": "PrometheusVariableQueryEditor-VariableQuery"},
        "refresh": 1, "sort": 1, "multi": False, "includeAll": False, "current": {"text": "platform", "value": "platform"}}]}
    return dashboard


def ai_dashboards():
    """Direct metrics only: exporter acceptance is not Tempo persistence proof."""
    variables = []
    for name, source in (("project", "platform_ai_runs_total"), ("action", "platform_ai_runs_total"),
                         ("provider", "platform_ai_tokens_total"), ("model", "platform_ai_tokens_total")):
        variables.append({"name": name, "type": "query", "datasource": {"type": "prometheus", "uid": "prometheus"},
            "query": {"query": f'label_values({source}, {name})', "refId": "VariableQuery"},
            "refresh": 1, "multi": True, "includeAll": True, "allValue": ".*",
            "current": {"text": "All", "value": "$__all"}})
    selected = 'project=~"$project",action=~"$action"'
    model = selected + ',provider=~"$provider",model=~"$model"'
    definitions = [
        ("ai-operations", "AI operations", [
            ("Run outcomes", f'sum by (outcome) (rate(platform_ai_runs_total{{{selected}}}[5m]))', "ops", "Completed, abstained and failed runs. Empty data is unknown, not zero."),
            ("Model and tool call outcomes", f'sum by (operation,outcome,tool) (rate(platform_ai_operations_total{{{selected},operation=~"model|tool"}}[5m]))', "ops", "One application counter per actual attempt. Tool names are allowlisted."),
            ("Operation p50 duration", f'histogram_quantile(0.50, sum by (le,operation) (rate(platform_ai_duration_seconds_bucket{{{selected}}}[5m])))', "s", "OpenLIT owns provider duration; platform owns run/tool duration."),
            ("Operation p95 duration", f'histogram_quantile(0.95, sum by (le,operation) (rate(platform_ai_duration_seconds_bucket{{{selected}}}[5m])))', "s", "Latency buckets are bounded at source; includes failed provider calls."),
            ("In-flight operations", f'sum by (operation) (platform_ai_in_flight{{{selected}}})', "short", "Active work in this API process. Missing data is not idle."),
            ("Tool calls per finished run", f'sum(rate(platform_ai_tool_calls_total{{{selected}}}[5m])) / sum(rate(platform_ai_runs_total{{{selected}}}[5m]))', "short", "No denominator means no observed completions; do not substitute zero."),
            ("Approvals and queued executions", 'sum by (operation,outcome) (increase(platform_ai_changes_total{project=~"$project"}[$__range]))', "short", "Durable audit remains authoritative. Queued execution is not successful workload recovery."),
        ]),
        ("ai-usage-cost", "AI usage and estimated cost", [
            ("Input, cached input and output tokens", f'sum by (token_type,model) (increase(platform_ai_tokens_total{{{model}}}[$__range]))', "short", "Cached input is a subset of input: never sum all three token types as total usage."),
            ("Usage and estimate completeness", f'sum by (completeness,model) (increase(platform_ai_usage_observations_total{{{model}}}[$__range]))', "short", "Unknown includes missing/failed usage, unsupported models and unverified cached-input pricing."),
            ("Known estimated cost (USD)", f'sum by (model,pricing_version) (increase(platform_ai_estimated_cost_usd_total{{{model}}}[$__range]))', "currencyUSD", "Partial known estimates only. Read alongside unknown observations. Versioned local pricing; provider bills are actual charges."),
            ("Estimated cost rate (USD/s)", f'sum by (model,pricing_version) (rate(platform_ai_estimated_cost_usd_total{{{model}}}[5m]))', "currencyUSD", "Not billing. Collection outages and incomplete usage undercount; durable run records retain estimate provenance."),
        ]),
        ("ai-telemetry-health", "AI telemetry health", [
            ("Direct metric heartbeat age", 'time() - platform_ai_heartbeat_timestamp_seconds', "s", "A stale/missing heartbeat signals collection failure, not zero AI traffic. Global pipeline panel, independent of project filters."),
            ("Configured root sampling", 'platform_ai_configured_root_sample_ratio', "percentunit", "Expected 100%. Configuration does not prove delivered trace coverage."),
            ("Finished operations expecting spans", f'sum by (operation) (increase(platform_ai_operations_total{{{selected}}}[$__range]))', "short", "Application attempts; compare with global exported spans cautiously across process restarts and in-flight boundaries."),
            ("AI span export acceptance", 'sum by (operation,outcome) (increase(platform_ai_spans_exported_total[$__range]))', "short", "Global SDK batch exporter result, not per-project or proof of Tempo persistence. Failed batches may be lost."),
            ("Collector trace failures", 'sum(rate(otelcol_exporter_send_failed_spans_total[5m]))', "ops", "Global Alloy exporter failures. Missing series requires checking collector version/discovery."),
            ("Metric export queue", 'otelcol_exporter_queue_size{exporter="otlphttp/ai_metrics"}', "short", "Global Alloy metric export queue. Direct metrics can be lost after bounded retry or queue overflow."),
            ("Cardinality drops", 'increase(platform_ai_cardinality_dropped_total[$__range])', "short", "Source refuses new metric series beyond 1024 attribute sets; at most 128 named projects plus other."),
            ("Trace filesystem available", 'node_filesystem_avail_bytes{mountpoint="/var/lib/developer-platform/tempo"}', "bytes", "Current 4 GiB trace volume and 24-hour retention remain in force. Storage growth must be measured before resize."),
            ("Tempo ingestion", 'sum(rate(tempo_distributor_spans_received_total[5m]))', "ops", "Global backend ingestion, not proof that a particular AI run is retained."),
        ]),
    ]
    dashboards = []
    for uid, title, entries in definitions:
        dashboards.append({"uid": uid, "title": title, "schemaVersion": 41, "version": 1,
            "editable": False, "timezone": "browser", "refresh": "30s", "time": {"from": "now-1h", "to": "now"},
            "tags": ["developer-platform", "operator", "ai"], "templating": {"list": variables},
            "links": [{"title": "Explore AI traces (last hour)", "type": "link", "targetBlank": True,
                "url": "/explore?" + urlencode({"schemaVersion": "1", "panes": json.dumps({"ai": {
                    "datasource": "tempo", "queries": [{"refId": "A", "queryType": "traceql",
                    "query": '{ resource.service.name = "platform-api" && name = "platform.ai.run" }'}],
                    "range": {"from": "now-1h", "to": "now"}}})})}],
            "panels": [panel(i, name, expr, unit=unit, description=description,
                legend="{{operation}} {{outcome}} {{tool}} {{token_type}} {{model}} {{pricing_version}} {{completeness}}")
                for i, (name, expr, unit, description) in enumerate(entries, 1)]})
    return dashboards


def store_dashboard():
    entries = [
        ("Logical usage / approved quota", 'platform_store_used_bytes / platform_store_quota_bytes', "percentunit", "Logical resource allocation. PostgreSQL byte quotas are advisory, not hard write limits. Missing usage is unknown."),
        ("Measured logical usage", 'platform_store_used_bytes', "bytes", "Last successful sample; retained values may be stale. Not physical volume size or backup usage."),
        ("Usage measurement age", 'time() - platform_store_usage_measured_timestamp_seconds', "s", "Zero timestamp means no successful reading. Sampling is bounded to eight resources per pass."),
        ("Usage measurement errors", 'platform_store_usage_error', "short", "One means the latest attempt failed; last successful usage remains visible."),
        ("Verified hard quota support", 'platform_store_hard_quota', "short", "Zero means advisory enforcement. Monitoring and capacity admission do not enforce a hard provider byte limit."),
        ("Desired state pending", 'platform_store_reconcile_pending', "short", "Provisioning, retirement, purge or configuration has not reached observed state."),
        ("Active credential generations", 'platform_store_credentials_active', "short", "Includes bounded rotation overlap and early human renewal. No principal or credential IDs are labels."),
        ("Provider access cleanup pending", 'platform_store_credentials_cleanup_pending', "short", "Expired or stale provider identities awaiting cleanup; relay denies them independently."),
        ("Store controller heartbeat age", 'time() - platform_store_worker_last_success_timestamp_seconds', "s", "Committed worker pass and successful metrics publication. Missing/stale is unavailable, not idle."),
    ]
    return {"uid": "named-data-stores", "title": "Named data-store resources", "schemaVersion": 41,
        "version": 1, "editable": False, "timezone": "browser", "refresh": "30s",
        "time": {"from": "now-1h", "to": "now"}, "tags": ["developer-platform", "operator", "stores"],
        "panels": [panel(i, title, expr, unit=unit, description=description,
            legend="{{project}} {{resource_id}} {{provider}}")
            for i, (title, expr, unit, description) in enumerate(entries, 1)]}


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
        if uid == "workloads-capacity":
            augment_capacity(dashboard)
        expected[uid] = dashboard
    for dashboard in (application_dashboard(), micrometer_dashboard(), postgres_dashboard(), store_dashboard(), *ai_dashboards()):
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
