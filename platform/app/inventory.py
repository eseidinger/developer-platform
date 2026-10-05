"""Provider-neutral project resource inventory for the developer API."""
from typing import Any
from .usage import parse_cpu, parse_memory


def _get(value: Any, name: str, default=None):
    return value.get(name, default) if isinstance(value, dict) else getattr(value, name, default)


def _items(runtime: Any, api_version: str, kind: str, namespace: str) -> list[Any]:
    return _get(runtime.resources.get(api_version=api_version, kind=kind).get(namespace=namespace), "items") or []


def _name(item: Any) -> str:
    return _get(_get(item, "metadata", {}), "name", "")


def _allocation(item: Any) -> list[dict]:
    template = _get(_get(_get(item, "spec", {}), "template", {}), "spec", {})
    return [{"name": _get(container, "name", ""),
             "requests": _get(_get(container, "resources", {}), "requests", {}),
             "limits": _get(_get(container, "resources", {}), "limits", {})}
            for container in (_get(template, "containers", []) or [])]


def _totals(deployments: list[Any]) -> dict:
    totals = {section: {"cpu_millicores": 0.0, "memory_bytes": 0} for section in ("requests", "limits")}
    for deployment in deployments:
        replicas = _get(_get(deployment, "spec", {}), "replicas", 0) or 0
        for container in _allocation(deployment):
            for section in totals:
                values = container[section]
                if values.get("cpu") is not None:
                    totals[section]["cpu_millicores"] += replicas * parse_cpu(values["cpu"])
                if values.get("memory") is not None:
                    totals[section]["memory_bytes"] += replicas * parse_memory(values["memory"])
    for section in totals:
        totals[section]["cpu_millicores"] = round(totals[section]["cpu_millicores"], 3)
    return totals


def _quota_comparisons(quotas: list[Any], declared: dict) -> list[dict]:
    """Compare desired Deployment allocation with every applicable ResourceQuota hard limit."""
    quantities = {
        "requests.cpu": ("requests", "cpu_millicores", parse_cpu),
        "requests.memory": ("requests", "memory_bytes", parse_memory),
        "limits.cpu": ("limits", "cpu_millicores", parse_cpu),
        "limits.memory": ("limits", "memory_bytes", parse_memory),
    }
    comparisons = []
    for quota in quotas:
        hard = _get(_get(quota, "status", {}), "hard", {}) or {}
        resources = {}
        for resource, (section, unit, parser) in quantities.items():
            if resource not in hard:
                continue
            try:
                limit = parser(hard[resource])
            except (TypeError, ValueError):
                continue
            allocated = declared[section][unit]
            resources[resource] = {"declared": allocated, "hard": limit,
                                   "remaining": max(0, round(limit - allocated, 3)),
                                   "state": "within" if allocated <= limit else "exceeded"}
        comparisons.append({"name": _name(quota), "resources": resources})
    return comparisons


def observe_inventory(runtime: Any, project: str, log) -> dict:
    """Return safe Kubernetes topology; provider errors are explicit, never empty inventory."""
    if runtime is None:
        return {"state": "unavailable", "reason": "KubernetesApiUnavailable"}
    namespace = "project-" + project
    try:
        deployments = _items(runtime, "apps/v1", "Deployment", namespace)
        pods = _items(runtime, "v1", "Pod", namespace)
        services = _items(runtime, "v1", "Service", namespace)
        ingresses = _items(runtime, "networking.k8s.io/v1", "Ingress", namespace)
        quotas = _items(runtime, "v1", "ResourceQuota", namespace)
        limits = _items(runtime, "v1", "LimitRange", namespace)
    except Exception as exc:
        log.error("Project inventory query failed project=%s error_type=%s", project, type(exc).__name__)
        return {"state": "unavailable", "reason": "KubernetesApiUnavailable"}
    declared = _totals(deployments)
    return {"state": "ok", "reason": None, "namespace": namespace,
            "deployments": [{"name": _name(item), "replicas": _get(_get(item, "spec", {}), "replicas", 0),
                              "ready_replicas": _get(_get(item, "status", {}), "ready_replicas", 0),
                              "containers": _allocation(item)}
                            for item in deployments],
            "declared_totals": declared,
            "instances": [{"name": _name(item), "phase": _get(_get(item, "status", {}), "phase", "Unknown")}
                          for item in pods],
            "services": [_name(item) for item in services],
            "routes": [_name(item) for item in ingresses],
            "quotas": [{"name": _name(item), "hard": _get(_get(item, "status", {}), "hard", {})} for item in quotas],
            "quota_comparisons": _quota_comparisons(quotas, declared),
            "limit_ranges": [_name(item) for item in limits],
            "data_services": [{"type": "postgresql", "name": "managed", "scope": "project"}]}


def observe_cluster_capacity(runtime: Any, log) -> dict:
    """Expose allocatable Kubernetes capacity; provider failure is explicit."""
    if runtime is None:
        return {"state": "unavailable", "reason": "KubernetesApiUnavailable", "nodes": []}
    try:
        nodes = _items(runtime, "v1", "Node", "")
        metrics = _items(runtime, "metrics.k8s.io/v1beta1", "NodeMetrics", "")
    except Exception as exc:
        log.error("Capacity query failed error_type=%s", type(exc).__name__)
        return {"state": "unavailable", "reason": "KubernetesApiUnavailable", "nodes": []}
    by_name = {_name(metric): _get(metric, "usage", {}) for metric in metrics}
    return {"state": "ok", "reason": None, "nodes": [
        {"name": _name(node), "capacity": _get(_get(node, "status", {}), "capacity", {}),
         "allocatable": _get(_get(node, "status", {}), "allocatable", {}),
         "usage": by_name.get(_name(node)), "usage_state": "ok" if _name(node) in by_name else "missing"}
        for node in nodes]}
