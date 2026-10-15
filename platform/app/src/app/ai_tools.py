"""Typed, read-only tools bound to one already-authorized project."""

import json
import logging
from collections import Counter
from datetime import datetime, timezone

from langchain_core.tools import StructuredTool

from . import application_metrics, trace_read
from .readiness import observe_deployment
from .retained_logs import observe_retained_logs


def application_view(current):
    revision, spec, state = current
    components = spec.get("components") if spec else None
    if components is None and spec:
        components = [{"name": "app", "type": "service"}]
    return {"revision": revision, "state": state,
            "components": [{"name": item["name"], "type": item["type"],
                            "metrics_enabled": bool(item.get("metrics")),
                            "tracing_enabled": bool(item.get("tracing", {}).get("enabled"))}
                           for item in (components or [])]}


SAFE_RUNTIME_REASONS = {"ObserverUnavailable", "DeploymentNotFound", "DeploymentImageMismatch",
                        "ProgressDeadlineExceeded", "ReplicaFailure", "RolloutInProgress",
                        "PodNotScheduled", "ContainerWaiting", "ContainersNotReady",
                        "CrashLoopBackOff", "OOMKilled", "ImagePullBackOff", "ErrImagePull",
                        "CreateContainerConfigError", "Unschedulable"}


def make_tools(project, current_spec, connect, runtime=None):
    """No model tool accepts a project parameter or infrastructure query language."""
    def _current():
        current = current_spec(project)
        if not current or not current[1]:
            return None
        return current

    def get_application() -> dict:
        """Read this project's revision, deployment state and component names."""
        current = _current()
        return {"source": "project-catalog", "state": "missing"} if not current else {
            "source": "project-catalog", **application_view(current)}

    def get_deployments() -> dict:
        """Read the ten most recent deployment operations for this project."""
        with connect() as conn:
            rows = conn.execute("""SELECT o.operation_id,o.revision,o.operation_kind,o.state,o.created_at,o.completed_at
                FROM application_operations o JOIN project_applications a ON a.application_id=o.application_id
                JOIN project_environments e ON e.environment_id=a.environment_id
                JOIN projects p ON p.project_id=e.project_id WHERE p.name=%s
                ORDER BY o.created_at DESC LIMIT 10""", (project,)).fetchall()
        return {"source": "application-operations", "operations": [
            {"id": str(row[0]), "revision": row[1], "kind": row[2], "state": row[3],
             "created_at": row[4].isoformat(), "completed_at": row[5].isoformat() if row[5] else None}
            for row in rows]}

    def get_metrics(component: str) -> dict:
        """Read fixed five-minute request and error metrics for an opted-in component."""
        current = _current()
        if not current or not any(c["name"] == component and c.get("metrics")
                                  for c in current[1].get("components", [])):
            return {"source": "application-metrics", "state": "not_declared"}
        return application_metrics.observe(project, component)

    def get_traces(trace_id: str) -> dict:
        """Read one trace by ID, filtered to spans verified for this project."""
        try:
            result = trace_read.read(project, trace_id)
        except (ValueError, trace_read.TraceUnavailable):
            return {"source": "project-traces", "state": "unavailable"}
        return {"source": "project-traces", "state": "missing"} if result is None else {
            "source": "project-traces", "state": "ok", "trace_id": trace_id,
            "span_count": len(result["spans"]),
            "components": sorted({s["component"] for s in result["spans"]})}

    def get_logs() -> dict:
        """Count recent safe operational log events for this project."""
        result = observe_retained_logs(project, logging.getLogger(__name__), tail=50, since_seconds=3600)
        counts = Counter(json.loads(line["message"])["event"] for line in result["lines"])
        return {"source": "retained-operational-logs", "state": result["state"],
                "window_seconds": 3600, "observed_at": result["observed_at"],
                "event_counts": dict(counts), "truncated": result["truncated"]}

    def get_events() -> dict:
        """Count recent deployment outcomes without exposing audit details."""
        data = get_deployments()
        return {"source": "application-operations", "outcomes": dict(Counter(
            operation["state"] for operation in data["operations"])),
            "observed_at": datetime.now(timezone.utc).isoformat()}

    def get_dependencies() -> dict:
        """Read bounded dependency counts from the current application declaration."""
        current = _current()
        components = current[1].get("components", []) if current else []
        return {"source": "project-catalog", "database": "retained",
                "declared_outbound_count": sum(len(c.get("outbound", [])) for c in components),
                "component_count": len(components)}

    def get_configuration() -> dict:
        """Read configuration key counts and changed key names, never values."""
        current = _current()
        if not current:
            return {"source": "project-catalog", "state": "missing"}
        with connect() as conn:
            rows = conn.execute("""SELECT r.spec FROM application_revisions r
                JOIN project_applications a ON a.application_id=r.application_id
                JOIN project_environments e ON e.environment_id=a.environment_id
                JOIN projects p ON p.project_id=e.project_id
                WHERE p.name=%s ORDER BY r.revision DESC LIMIT 2""", (project,)).fetchall()
        current_values = current[1].get("configuration") or {}
        previous_values = (rows[1][0].get("configuration") or {}) if len(rows) > 1 else {}
        changed = sorted(key for key in set(current_values) | set(previous_values)
                         if current_values.get(key) != previous_values.get(key))
        return {"source": "project-catalog", "state": "ok",
                "non_secret_key_count": len(current_values),
                "changed_key_names_since_previous_revision": changed[:20],
                "changed_count": len(changed)}

    def get_runtime_status() -> dict:
        """Read bounded deployment readiness and safe Kubernetes reason codes."""
        current = _current()
        if not current:
            return {"source": "project-runtime", "state": "missing"}
        components = current[1].get("components", [])
        service = next((c for c in components if c["type"] == "service"), None)
        if service:
            observed = observe_deployment(runtime, project, service.get("resolved_image", service["image"]),
                                          logging.getLogger(__name__), service["name"])
        else:
            image = current[1].get("resolved_image", current[1].get("image"))
            if not image:
                return {"source": "project-runtime", "state": "not_applicable"}
            observed = observe_deployment(runtime, project, image, logging.getLogger(__name__))
        reason = observed.get("reason")
        return {"source": "project-runtime", "state": observed["state"],
                "reason": reason if reason in SAFE_RUNTIME_REASONS else "OtherRuntimeReason",
                "desired_replicas": observed["desired_replicas"],
                "ready_replicas": observed["ready_replicas"],
                "observed_at": observed["observed_at"]}

    def get_documentation() -> dict:
        """Read the fixed platform reference for deployment revision and rollback semantics."""
        return {"source": "docs/api/openapi.json", "reference": "/v1/operations/{operation_id}",
                "facts": ["A deploy request queues an operation and returns its ID.",
                          "Inspect operation status and readiness before declaring recovery.",
                          "Rollback re-applies a retained revision as a new revision."],
                "observed_at": datetime.now(timezone.utc).isoformat()}

    functions = [get_application, get_deployments, get_metrics, get_traces,
                 get_logs, get_events, get_dependencies, get_configuration, get_runtime_status,
                 get_documentation]
    return [StructuredTool.from_function(func=function, name=function.__name__,
                                         description=function.__doc__.strip()) for function in functions]
