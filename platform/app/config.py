"""Non-secret application configuration: validation, and observation of its activation."""
import re
from typing import Any, Optional

from kubernetes.client.exceptions import ApiException

MAX_VALUES = 50
MAX_VALUE_LENGTH = 1024
_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")
_RESERVED_PREFIXES = ("PG", "KUBERNETES_", "PLATFORM_")
_SECRET_LIKE = re.compile(r"PASS|SECRET|TOKEN|CREDENTIAL|PRIVATE|API_?KEY|AUTH", re.IGNORECASE)


def check_env_name(key: Any, allow_secret_like: bool = False) -> None:
    if not isinstance(key, str) or not _NAME.match(key):
        raise ValueError("names must be letters, digits and underscores, not start with a digit")
    if key.upper().startswith(_RESERVED_PREFIXES):
        raise ValueError(f"name {key} is reserved by the platform")
    if not allow_secret_like and _SECRET_LIKE.search(key):
        raise ValueError(f"configuration name {key} looks like a secret; configuration is readable by "
                         "every project viewer, use secrets instead")


def normalize_configuration(values: Any) -> dict[str, str]:
    """Validate configuration values before they can be stored or applied."""
    if not isinstance(values, dict):
        raise ValueError("configuration must be a map of names to string values")
    if len(values) > MAX_VALUES:
        raise ValueError(f"configuration allows at most {MAX_VALUES} values")
    for key, value in values.items():
        check_env_name(key)
        if not isinstance(value, str):
            raise ValueError(f"configuration value for {key} must be a string")
        if len(value) > MAX_VALUE_LENGTH or "\x00" in value:
            raise ValueError(f"configuration value for {key} is too long or contains NUL")
        if "-----BEGIN" in value:
            raise ValueError(f"configuration value for {key} looks like key material; use secrets instead")
    return dict(sorted(values.items()))


def env_list(values: Optional[dict[str, str]]) -> list[dict[str, str]]:
    return [{"name": k, "value": v} for k, v in sorted((values or {}).items())]


def _field(value: Any, name: str, default=None):
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def rollout_state(deployment: Any) -> dict[str, Any]:
    status = _field(deployment, "status", {}) or {}
    replicas = _field(_field(deployment, "spec", {}), "replicas", 1) or 1
    if (_field(status, "updatedReplicas", 0) or 0) >= replicas and (_field(status, "readyReplicas", 0) or 0) >= replicas \
            and (_field(status, "replicas", 0) or 0) <= replicas:
        return {"state": "active", "reason": None}
    return {"state": "rolling_out", "reason": "pods_not_ready"}


def observe_activation(runtime: Any, project: str, values: dict[str, str]) -> dict[str, Any]:
    """Whether the live Deployment carries the desired values and has finished rolling them out."""
    if runtime is None:
        return {"state": "unknown", "reason": "runtime_unavailable"}
    try:
        deployment = runtime.resources.get(api_version="apps/v1", kind="Deployment").get(
            name=project, namespace="project-" + project)
    except ApiException as exc:
        return {"state": "unknown", "reason": "not_found" if exc.status == 404 else "unavailable"}
    except Exception:
        return {"state": "unknown", "reason": "unavailable"}
    template = _field(_field(deployment, "spec", {}), "template", {})
    containers = _field(_field(template, "spec", {}), "containers", []) or []
    observed = {_field(e, "name"): _field(e, "value") for e in (_field(containers[0], "env", []) or [])} \
        if containers else {}
    if observed != values:
        return {"state": "pending", "reason": "deployment_not_updated"}
    return rollout_state(deployment)
