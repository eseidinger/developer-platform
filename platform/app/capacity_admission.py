"""Conservative opt-in aggregate Kubernetes request admission."""
import os

from .manifests import DEFAULT_RESOURCES, _mebibytes, _millicores


def _get(value, name, default=None):
    return value.get(name, default) if isinstance(value, dict) else getattr(value, name, default)


def _items(runtime, api_version, kind):
    return _get(runtime.resources.get(api_version=api_version, kind=kind).get(), "items", []) or []


def _request_total(containers):
    total = {"cpu": 0, "memory": 0}
    for container in containers:
        requests = _get(_get(container, "resources", {}), "requests", {}) or {}
        for key, parser in (("cpu", _millicores), ("memory", _mebibytes)):
            if _get(requests, key) is not None:
                total[key] += parser(_get(requests, key))
    return total


def _proposed(spec):
    components = spec.get("components") or [{"type": "service", "resources": spec.get("resources")}]
    total = {"cpu": 0, "memory": 0}
    for component in components:
        resources = component.get("resources") or DEFAULT_RESOURCES
        replicas = component.get("replicas", 1) if component["type"] == "service" else 1
        values = _request_total([{"resources": resources}])
        for key in total:
            total[key] += values[key] * replicas
    return total


def assess(runtime, spec, log):
    """Return a safe decision; enabled admission never assumes missing capacity is free."""
    if os.environ.get("CAPACITY_ADMISSION_ENABLED", "false").lower() != "true":
        return {"state": "disabled"}
    if runtime is None:
        return {"state": "unavailable", "reason": "KubernetesApiUnavailable"}
    try:
        nodes, pods = _items(runtime, "v1", "Node"), _items(runtime, "v1", "Pod")
        capacity = {"cpu": 0, "memory": 0}
        for node in nodes:
            allocatable = _get(_get(node, "status", {}), "allocatable", {}) or {}
            capacity["cpu"] += _millicores(_get(allocatable, "cpu"))
            capacity["memory"] += _mebibytes(_get(allocatable, "memory"))
        used = {"cpu": 0, "memory": 0}
        for pod in pods:
            if _get(_get(pod, "status", {}), "phase") not in {"Succeeded", "Failed"}:
                values = _request_total(_get(_get(pod, "spec", {}), "containers", []) or [])
                for key in used:
                    used[key] += values[key]
    except Exception as exc:
        log.error("Capacity admission query failed error_type=%s", type(exc).__name__)
        return {"state": "unavailable", "reason": "KubernetesApiUnavailable"}
    try:
        reserve = {"cpu": int(os.environ.get("CAPACITY_RESERVE_CPU_MILLICORES", "2000")),
                   "memory": int(os.environ.get("CAPACITY_RESERVE_MEMORY_MIB", "8192"))}
        if any(value < 0 for value in reserve.values()):
            raise ValueError
    except ValueError:
        return {"state": "unavailable", "reason": "InvalidCapacityReserve"}
    proposed = _proposed(spec)
    available = {key: capacity[key] - reserve[key] - used[key] for key in capacity}
    if any(proposed[key] > available[key] for key in proposed):
        return {"state": "rejected", "reason": "InsufficientReservedCapacity", "available": available,
                "proposed": proposed}
    return {"state": "accepted", "available": available, "proposed": proposed}
