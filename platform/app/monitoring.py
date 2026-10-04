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


def target_groups(rows, domain):
    if not re.fullmatch(r"[a-zA-Z0-9](?:[a-zA-Z0-9.-]*[a-zA-Z0-9])?", domain):
        raise ValueError("Invalid application domain")
    local = domain == "apps.localhost"
    groups = []
    for name, spec, status in sorted(rows):
        if status in {"empty", "retired"} or spec is None:
            continue
        validate_name(name)
        profile = spec.get("probe_profile", "status")
        if profile not in PROFILES:
            raise ValueError("Unknown probe profile")
        host = name + "." + domain
        url = ("http://" if local else "https://") + host + "/"
        groups.append({"targets": ["http://proxy/" if local else url], "labels": {
            "project": name, "application": name, "namespace": "project-" + name,
            "instance": url, "probe_hostname": host,
            "probe_module": ("http_" if local else "https_") + profile.replace("-", "_"),
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
    directory.mkdir(parents=True, exist_ok=True)
    atomic_write(directory / "applications.json", json.dumps(groups) + "\n")
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
