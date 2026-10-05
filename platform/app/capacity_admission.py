"""Conservative opt-in aggregate Kubernetes request admission."""
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
import os

from kubernetes.utils.quantity import parse_quantity

from .manifests import DEFAULT_RESOURCES


def _get(value, name, default=None):
    return value.get(name, default) if isinstance(value, dict) else getattr(value, name, default)


def _items(runtime, api_version, kind):
    return _get(runtime.resources.get(api_version=api_version, kind=kind).get(namespace=""), "items", []) or []


def _cpu_millicores(value, rounding=ROUND_CEILING):
    quantity = parse_quantity(str(value)) * Decimal(1000)
    if quantity < 0:
        raise ValueError("negative CPU quantity")
    return int(quantity.to_integral_value(rounding=rounding))


def _memory_mib(value, rounding=ROUND_CEILING):
    quantity = parse_quantity(str(value)) / Decimal(1024 * 1024)
    if quantity < 0:
        raise ValueError("negative memory quantity")
    return int(quantity.to_integral_value(rounding=rounding))


def _request_total(containers):
    total = {"cpu": 0, "memory": 0}
    for container in containers:
        requests = _get(_get(container, "resources", {}), "requests", {}) or {}
        for key, parser in (("cpu", _cpu_millicores), ("memory", _memory_mib)):
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


def snapshot(runtime, log):
    """Return the request-based admission inputs using explicit CPU/memory units."""
    if os.environ.get("CAPACITY_ADMISSION_ENABLED", "false").lower() != "true":
        return {"state": "disabled", "enabled": False}
    if runtime is None:
        return {"state": "unavailable", "enabled": True, "reason": "KubernetesApiUnavailable"}
    try:
        nodes, pods = _items(runtime, "v1", "Node"), _items(runtime, "v1", "Pod")
    except Exception as exc:
        log.error("Capacity admission query failed error_type=%s", type(exc).__name__)
        return {"state": "unavailable", "enabled": True, "reason": "KubernetesApiUnavailable"}
    try:
        allocatable = {"cpu": 0, "memory": 0}
        for node in nodes:
            values = _get(_get(node, "status", {}), "allocatable", {}) or {}
            allocatable["cpu"] += _cpu_millicores(_get(values, "cpu"), ROUND_FLOOR)
            allocatable["memory"] += _memory_mib(_get(values, "memory"), ROUND_FLOOR)
        requested = {"cpu": 0, "memory": 0}
        for pod in pods:
            if _get(_get(pod, "status", {}), "phase") not in {"Succeeded", "Failed"}:
                values = _request_total(_get(_get(pod, "spec", {}), "containers", []) or [])
                for key in requested:
                    requested[key] += values[key]
    except (ArithmeticError, TypeError, ValueError) as exc:
        log.error("Capacity admission data invalid error_type=%s", type(exc).__name__)
        return {"state": "unavailable", "enabled": True, "reason": "InvalidKubernetesCapacityData"}
    try:
        reserve = {"cpu": int(os.environ.get("CAPACITY_RESERVE_CPU_MILLICORES", "2000")),
                   "memory": int(os.environ.get("CAPACITY_RESERVE_MEMORY_MIB", "8192"))}
        if any(value < 0 for value in reserve.values()):
            raise ValueError
    except ValueError:
        return {"state": "unavailable", "enabled": True, "reason": "InvalidCapacityReserve"}
    available = {key: allocatable[key] - reserve[key] - requested[key] for key in allocatable}
    def public(values):
        return {"cpu_millicores": values["cpu"], "memory_mib": values["memory"]}
    return {"state": "ok", "enabled": True, "allocatable": public(allocatable),
            "requested": public(requested), "reserve": public(reserve), "available": public(available)}


def assess(runtime, spec, log):
    """Return a safe decision; enabled admission never assumes missing capacity is free."""
    current = snapshot(runtime, log)
    if current["state"] == "disabled":
        return {"state": "disabled"}
    if current["state"] != "ok":
        return {"state": "unavailable", "reason": current["reason"]}
    proposed = _proposed(spec)
    available = {"cpu": current["available"]["cpu_millicores"],
                 "memory": current["available"]["memory_mib"]}
    if any(proposed[key] > available[key] for key in proposed):
        return {"state": "rejected", "reason": "InsufficientReservedCapacity", "available": available,
                "proposed": proposed}
    return {"state": "accepted", "available": available, "proposed": proposed}
