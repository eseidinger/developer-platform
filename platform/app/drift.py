"""Report differences between the desired revision and the live Deployment; never changes the cluster."""
from typing import Any

from kubernetes.client.exceptions import ApiException

from .audit import Actor
from .manifests import _mebibytes, _millicores, normalize_resources


def _field(value: Any, name: str, default=None):
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _canonical(kind: str, value: Any):
    try:
        return _millicores(value) if kind == "cpu" else _mebibytes(value)
    except ValueError:
        return str(value)


def observe_drift(runtime: Any, project: str, spec: dict, log) -> dict[str, Any]:
    if runtime is None:
        return {"state": "unknown", "differences": []}
    try:
        deployment = runtime.resources.get(api_version="apps/v1", kind="Deployment").get(
            name=project, namespace="project-" + project)
    except ApiException as exc:
        if exc.status == 404:
            return {"state": "not_found", "differences": []}
        log.error("Drift query failed project=%s error_type=%s", project, type(exc).__name__)
        return {"state": "unknown", "differences": []}
    except Exception as exc:
        log.error("Drift query failed project=%s error_type=%s", project, type(exc).__name__)
        return {"state": "unknown", "differences": []}

    template = _field(_field(deployment, "spec", {}), "template", {})
    containers = _field(_field(template, "spec", {}), "containers", []) or []
    container = containers[0] if containers else {}
    replicas = _field(_field(deployment, "spec", {}), "replicas", 1)
    observed_resources = _field(container, "resources", {}) or {}
    differences = []

    def compare(name, desired, observed):
        if desired != observed:
            differences.append({"field": name, "desired": desired, "observed": observed})

    compare("image", spec.get("resolved_image", spec["image"]), _field(container, "image"))
    compare("replicas", 1, 1 if replicas is None else replicas)
    desired_resources = normalize_resources(spec.get("resources") or {})
    for section, values in desired_resources.items():
        seen = _field(observed_resources, section, {}) or {}
        for key, desired in values.items():
            observed = seen.get(key) if isinstance(seen, dict) else _field(seen, key)
            if _canonical(key, desired) != (None if observed is None else _canonical(key, observed)):
                differences.append({"field": f"resources.{section}.{key}", "desired": desired,
                                    "observed": observed})
    return {"state": "drifted" if differences else "in_sync", "differences": differences}


def scan_once(connect, runtime, audit, state: dict, log) -> None:
    """Audit drift transitions for applied projects; `state` maps project -> drifted fields or None."""
    with connect() as conn:
        rows = conn.execute("""SELECT p.name, r.revision, r.spec
            FROM projects p
            JOIN project_environments e ON e.project_id=p.project_id
            JOIN project_applications a ON a.environment_id=e.environment_id
            JOIN LATERAL (SELECT revision, spec FROM application_revisions
                WHERE application_id=a.application_id ORDER BY revision DESC LIMIT 1) r ON true
            WHERE p.status='applied'""").fetchall()
    for name in set(state) - {row[0] for row in rows}:
        del state[name]
    actor = Actor("system", "drift-scan")
    for name, revision, spec in rows:
        result = observe_drift(runtime, name, spec, log)
        if result["state"] == "drifted":
            fields = sorted(d["field"] for d in result["differences"])
            if state.get(name) != fields:
                state[name] = fields
                audit(actor, "project.drift.detected", "project", name, "succeeded",
                      {"project": name}, {"revision": revision, "fields": fields})
        elif result["state"] == "in_sync" and state.get(name):
            state[name] = None
            audit(actor, "project.drift.resolved", "project", name, "succeeded",
                  {"project": name}, {"revision": revision})


def drift_loop(stop, connect, get_runtime, audit, log, interval: float) -> None:
    state: dict = {}
    while not stop.wait(interval):
        try:
            scan_once(connect, get_runtime(), audit, state, log)
        except Exception as exc:
            log.error("Drift scan failed error_type=%s", type(exc).__name__)
