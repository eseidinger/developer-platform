"""Provider-neutral project resource inventory for the developer API."""
from typing import Any


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
    return {"state": "ok", "reason": None, "namespace": namespace,
            "deployments": [{"name": _name(item), "replicas": _get(_get(item, "spec", {}), "replicas", 0),
                              "ready_replicas": _get(_get(item, "status", {}), "ready_replicas", 0),
                              "containers": _allocation(item)}
                            for item in deployments],
            "instances": [{"name": _name(item), "phase": _get(_get(item, "status", {}), "phase", "Unknown")}
                          for item in pods],
            "services": [_name(item) for item in services],
            "routes": [_name(item) for item in ingresses],
            "quotas": [{"name": _name(item), "hard": _get(_get(item, "status", {}), "hard", {})} for item in quotas],
            "limit_ranges": [_name(item) for item in limits],
            "data_services": [{"type": "postgresql", "name": "managed", "scope": "project"}]}
