"""Rebuild disposable Prometheus discovery from the durable project catalog."""
import json
import os
import re
import tempfile
import time
from pathlib import Path

from .manifests import validate_name

LOCK_ID = 731904
PROFILES = ("status", "hello-world")


def _target(name, component, domain, health, protected):
    """Public reachability is distinct from Kubernetes semantic readiness.

    Never put application credentials in discovery or bypass the authorizer.
    A protected probe expects a denial/login response, not application content.
    """
    validate_name(name)
    if component:
        validate_name(component)
    profile = health.get("probe_profile", "status")
    if profile not in PROFILES:
        raise ValueError("Unknown probe profile")
    path = health.get("readiness_path", "/")
    # A stored declaration must not turn discovery into arbitrary URL/parameter injection.
    if (not isinstance(path, str) or len(path) > 256
            or not re.fullmatch(r"/[A-Za-z0-9._~!$&'()*+,;=:@%/-]*", path)
            or path.startswith("//")):
        raise ValueError("Invalid readiness path")
    local = domain == "apps.localhost"
    host = (component + "-" if component else "") + name + "." + domain
    url = ("http://" if local else "https://") + host + path
    return {"targets": ["http://proxy" + path if local else url], "labels": {
        "project": name, "environment": "default", "application": name,
        "component": component or "app", "namespace": "project-" + name,
        "instance": url, "probe_hostname": host,
        "probe_kind": "access-boundary" if protected else "application-health",
        "health_profile": "custom" if "readiness_path" in health else profile,
        "probe_module": ("http_" if local else "https_") +
                        ("protected" if protected else profile.replace("-", "_")),
    }}


def target_groups(rows, domain):
    if not re.fullmatch(r"[a-zA-Z0-9](?:[a-zA-Z0-9.-]*[a-zA-Z0-9])?", domain):
        raise ValueError("Invalid application domain")
    groups = []
    for name, spec, status in sorted(rows):
        if status in {"empty", "retired"} or spec is None:
            continue
        validate_name(name)
        if spec.get("components") is not None:
            for component in sorted(spec["components"], key=lambda item: item["name"]):
                if component["type"] == "service" and component.get("exposure") == "public":
                    groups.append(_target(name, component["name"], domain, component, True))
        else:
            groups.append(_target(name, None, domain, spec, False))
    return groups


def metric_target_groups(rows):
    """Private Kubernetes service-proxy scrape targets from accepted active specs."""
    groups = []
    for name, spec, status in sorted(rows):
        if status != "applied" or not spec or spec.get("components") is None:
            continue
        validate_name(name)
        for component in sorted(spec["components"], key=lambda item: item["name"]):
            metrics = component.get("metrics")
            if component["type"] != "service" or not metrics:
                continue
            validate_name(component["name"])
            port = metrics["port"]
            path = metrics["path"]
            if port not in {p["name"] for p in component.get("ports", [])}:
                raise ValueError("Metrics port must be declared")
            if (not isinstance(path, str) or not re.fullmatch(r"/[A-Za-z0-9._~/-]{0,127}", path)
                    or "//" in path or any(segment in {".", ".."} for segment in path.split("/"))):
                raise ValueError("Invalid metrics path")
            groups.append({"targets": ["k3d-workloads-server-0:6443"], "labels": {
                "project": name, "environment": "default", "application": name,
                "component": component["name"], "namespace": "project-" + name,
                "proxy_path": f"/api/v1/namespaces/project-{name}/services/http:{component['name']}:{port}/proxy{path}",
            }})
    return groups


def atomic_write(path, content):
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix=".discovery-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
            os.fchmod(stream.fileno(), 0o644)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def publish_catalog(conn):
    """Caller holds the shared lifecycle advisory lock. Never publish on query error."""
    directory = Path(os.environ.get("MONITORING_DISCOVERY_DIR", "/var/lib/platform-monitoring"))
    rows = conn.execute("SELECT name, spec, status FROM projects ORDER BY name").fetchall()
    groups = target_groups(rows, os.environ["APPS_DOMAIN"])
    metric_groups = metric_target_groups(rows)
    directory.mkdir(parents=True, exist_ok=True)
    atomic_write(directory / "applications.json", json.dumps(groups) + "\n")
    atomic_write(directory / "application-metrics.json", json.dumps(metric_groups) + "\n")
    atomic_write(directory / "discovery.prom",
                 "# HELP platform_discovery_last_success_timestamp_seconds Last catalog publication.\n"
                 "# TYPE platform_discovery_last_success_timestamp_seconds gauge\n"
                 f"platform_discovery_last_success_timestamp_seconds {time.time()}\n"
                 "# HELP platform_discovery_targets Number of registered application probes.\n"
                 "# TYPE platform_discovery_targets gauge\n"
                 f"platform_discovery_targets {len(groups)}\n")


def reconcile(connect):
    with connect() as conn:
        if not conn.execute("SELECT pg_try_advisory_lock(%s)", (LOCK_ID,)).fetchone()[0]:
            return
        try:
            publish_catalog(conn)
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", (LOCK_ID,))


def discovery_loop(stop, connect, log):
    while not stop.is_set():
        try:
            reconcile(connect)
        except Exception:
            # Do not replace valid targets or log credentials on a database/filesystem failure.
            log.error("Application monitoring discovery failed; retaining previous targets")
        stop.wait(30)
