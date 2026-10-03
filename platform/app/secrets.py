"""Write-only application secrets kept only in a Kubernetes Secret in the project namespace.

Values are never returned, stored in revisions or written to audit records. Every change
stamps the Secret's resourceVersion onto the pod template so the pods restart and pick it up.
"""
from datetime import datetime, timezone
from typing import Any, Optional

from kubernetes.client.exceptions import ApiException

from .config import _field, check_env_name, rollout_state
from .manifests import SECRET_NAME

MAX_NAME_LENGTH = 50
MAX_VALUE_LENGTH = 8192
MAX_SECRETS = 50
VERSION_ANNOTATION = "platform.example/secrets-version"
_CHANGED_PREFIX = "platform.example/changed-"
_MERGE = "application/merge-patch+json"


class SecretsUnavailable(Exception):
    pass


def validate_secret_name(name: Any) -> None:
    check_env_name(name, allow_secret_like=True)
    if len(name) > MAX_NAME_LENGTH:
        raise ValueError(f"secret names allow at most {MAX_NAME_LENGTH} characters")


def validate_secret_value(value: Any) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError("value must be a non-empty string")
    if len(value) > MAX_VALUE_LENGTH or "\x00" in value:
        raise ValueError(f"value is too long (max {MAX_VALUE_LENGTH}) or contains NUL")


def _plain(value: Any) -> Any:
    return value.to_dict() if hasattr(value, "to_dict") else value


def _api(runtime: Any, kind: str, api_version: str):
    return runtime.resources.get(api_version=api_version, kind=kind)


def read_secret(runtime: Any, project: str) -> Optional[dict[str, Any]]:
    """Names, change times and version of the project's Secret; None when it does not exist."""
    if runtime is None:
        raise SecretsUnavailable()
    try:
        found = _plain(_api(runtime, "Secret", "v1").get(name=SECRET_NAME, namespace="project-" + project))
    except ApiException as exc:
        if exc.status == 404:
            return None
        raise SecretsUnavailable() from None
    except Exception:
        raise SecretsUnavailable() from None
    try:
        metadata = found.get("metadata") or {}
        annotations = metadata.get("annotations") or {}
        names = sorted((found.get("data") or {}).keys())
        return {"version": metadata.get("resourceVersion"),
                "secrets": [{"name": n, "changed_at": annotations.get(_CHANGED_PREFIX + n)} for n in names]}
    except (AttributeError, TypeError):
        raise SecretsUnavailable() from None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_secret(runtime: Any, project: str, name: str, value: str) -> str:
    """Create or update one key; returns the Secret's new resourceVersion."""
    namespace = "project-" + project
    body = {"metadata": {"annotations": {_CHANGED_PREFIX + name: _now()}}, "stringData": {name: value}}
    secrets = _api(runtime, "Secret", "v1")
    try:
        try:
            result = secrets.patch(body=body, name=SECRET_NAME, namespace=namespace, content_type=_MERGE)
        except ApiException as exc:
            if exc.status != 404:
                raise
            created = {"apiVersion": "v1", "kind": "Secret", "type": "Opaque",
                       "metadata": {"name": SECRET_NAME, "namespace": namespace,
                                    "labels": {"platform.example/managed": "true"},
                                    "annotations": body["metadata"]["annotations"]},
                       "stringData": body["stringData"]}
            try:
                result = secrets.create(body=created, namespace=namespace)
            except ApiException as race:
                if race.status != 409:
                    raise
                result = secrets.patch(body=body, name=SECRET_NAME, namespace=namespace, content_type=_MERGE)
    except ApiException:
        raise SecretsUnavailable() from None
    return (_plain(result).get("metadata") or {}).get("resourceVersion")


def remove_secret(runtime: Any, project: str, name: str) -> str:
    body = {"metadata": {"annotations": {_CHANGED_PREFIX + name: None}}, "data": {name: None}}
    try:
        result = _api(runtime, "Secret", "v1").patch(
            body=body, name=SECRET_NAME, namespace="project-" + project, content_type=_MERGE)
    except ApiException:
        raise SecretsUnavailable() from None
    return (_plain(result).get("metadata") or {}).get("resourceVersion")


def roll_pods(runtime: Any, project: str, version: str) -> bool:
    """Stamp the Secret version on the pod template; False when no Deployment exists yet."""
    body = {"spec": {"template": {"metadata": {"annotations": {VERSION_ANNOTATION: version}}}}}
    try:
        _api(runtime, "Deployment", "apps/v1").patch(
            body=body, name=project, namespace="project-" + project, content_type=_MERGE,
            field_manager="developer-platform-secrets")
    except ApiException as exc:
        if exc.status == 404:
            return False
        raise SecretsUnavailable() from None
    return True


def observe_secret_activation(runtime: Any, project: str, version: Optional[str]) -> dict[str, Any]:
    """Whether the pods run with the current Secret version."""
    try:
        deployment = _plain(_api(runtime, "Deployment", "apps/v1").get(
            name=project, namespace="project-" + project))
    except ApiException as exc:
        return {"state": "unknown", "reason": "not_found" if exc.status == 404 else "unavailable"}
    except Exception:
        return {"state": "unknown", "reason": "unavailable"}
    template = _field(_field(deployment, "spec", {}), "template", {})
    annotations = (_field(_field(template, "metadata", {}), "annotations", {}) or {})
    if annotations.get(VERSION_ANNOTATION) != version:
        return {"state": "pending", "reason": "deployment_not_updated"}
    return rollout_state(deployment)
