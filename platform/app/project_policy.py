"""Operator-controlled project quota policy shared by admission and manifests."""
import json
import os
import re


DEFAULT_QUOTA = {
    "requests.cpu": "2", "requests.memory": "2Gi", "limits.cpu": "4", "limits.memory": "4Gi",
    "pods": "10", "services": "5", "services.loadbalancers": "0", "services.nodeports": "0",
    "persistentvolumeclaims": "0",
}
OVERRIDABLE = {"requests.cpu", "requests.memory", "limits.cpu", "limits.memory", "pods"}


def _cpu(value):
    text = str(value)
    if re.fullmatch(r"[1-9][0-9]{0,4}m", text):
        return int(text[:-1])
    if re.fullmatch(r"[1-9][0-9]?(?:\.[0-9]{1,3})?", text):
        return round(float(text) * 1000)
    raise ValueError


def _memory(value):
    match = re.fullmatch(r"([1-9][0-9]{0,4})(Mi|Gi)", str(value))
    if not match:
        raise ValueError
    return int(match[1]) * (1024 if match[2] == "Gi" else 1)


def _validate_override(values):
    if not isinstance(values, dict) or set(values) - OVERRIDABLE:
        raise ValueError("operator project quota policy is invalid")
    try:
        for key, value in values.items():
            if key.endswith("cpu"):
                _cpu(value)
            elif key.endswith("memory"):
                _memory(value)
            elif not isinstance(value, (str, int)) or int(value) < 1:
                raise ValueError
    except (TypeError, ValueError) as exc:
        raise ValueError("operator project quota policy is invalid") from exc


def quota_for(project: str) -> dict:
    """Return the effective fail-closed quota for a valid project name."""
    try:
        configured = json.loads(os.environ.get("PROJECT_QUOTAS_JSON", "{}"))
    except json.JSONDecodeError as exc:
        raise ValueError("operator project quota policy is invalid") from exc
    if not isinstance(configured, dict) or any(not isinstance(name, str) for name in configured):
        raise ValueError("operator project quota policy is invalid")
    default = configured.get("default", {})
    selected = configured.get(project, {})
    _validate_override(default)
    _validate_override(selected)
    return {**DEFAULT_QUOTA, **default, **selected}


def validate_component_capacity(project: str, components: list[dict]) -> None:
    """Reject a requested rollout that cannot fit the effective namespace quota."""
    quota = quota_for(project)
    steady_pods, largest_service = 0, 0
    totals = {section: {"cpu": 0, "memory": 0} for section in ("requests", "limits")}
    surge = {section: {"cpu": 0, "memory": 0} for section in ("requests", "limits")}
    for component in components:
        replicas = component.get("replicas", 1) if component["type"] == "service" else 1
        steady_pods += replicas
        largest_service = max(largest_service, replicas if component["type"] == "service" else 0)
        requested = component.get("resources") or {"requests": {"cpu": "100m", "memory": "128Mi"},
                                                     "limits": {"cpu": "500m", "memory": "256Mi"}}
        for section in totals:
            cpu, memory = _cpu(requested[section]["cpu"]), _memory(requested[section]["memory"])
            totals[section]["cpu"] += cpu * replicas
            totals[section]["memory"] += memory * replicas
            if component["type"] == "service":
                surge[section]["cpu"] = max(surge[section]["cpu"], cpu * replicas)
                surge[section]["memory"] = max(surge[section]["memory"], memory * replicas)
    if steady_pods + largest_service > int(quota["pods"]):
        raise ValueError("components exceed the namespace pod quota during rollout")
    limits = {"requests": {"cpu": _cpu(quota["requests.cpu"]), "memory": _memory(quota["requests.memory"])},
              "limits": {"cpu": _cpu(quota["limits.cpu"]), "memory": _memory(quota["limits.memory"])}}
    for section in totals:
        for resource in totals[section]:
            if totals[section][resource] + surge[section][resource] > limits[section][resource]:
                raise ValueError("components exceed the namespace resource quota during rollout")
