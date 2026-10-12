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
_VERSION_PREFIX = "platform.example/version-"
PREVIOUS_SECRET_NAME = "app-secrets-previous"
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


def _get(runtime: Any, secret_name: str, project: str) -> Optional[dict[str, Any]]:
    if runtime is None:
        raise SecretsUnavailable()
    try:
        return _plain(_api(runtime, "Secret", "v1").get(name=secret_name, namespace="project-" + project))
    except ApiException as exc:
        if exc.status == 404:
            return None
        raise SecretsUnavailable() from None
    except Exception:
        raise SecretsUnavailable() from None


def _annotations(found: Optional[dict[str, Any]]) -> dict[str, str]:
    return ((found or {}).get("metadata") or {}).get("annotations") or {}


def _version_of(annotations: dict[str, str], name: str) -> int:
    try:
        return int(annotations.get(_VERSION_PREFIX + name, 1))
    except (TypeError, ValueError):
        return 1


def read_secret(runtime: Any, project: str) -> Optional[dict[str, Any]]:
    """Names, change times, versions and version of the project's Secret; None when it does not exist."""
    found = _get(runtime, SECRET_NAME, project)
    if found is None:
        return None
    held = _get(runtime, PREVIOUS_SECRET_NAME, project)
    try:
        previous = set((held or {}).get("data") or {})
        metadata = found.get("metadata") or {}
        annotations = metadata.get("annotations") or {}
        names = sorted((found.get("data") or {}).keys())
        return {"version": metadata.get("resourceVersion"),
                "secrets": [{"name": n, "version": _version_of(annotations, n),
                             "state": "rotating" if n in previous else "active",
                             "changed_at": annotations.get(_CHANGED_PREFIX + n)} for n in names]}
    except (AttributeError, TypeError):
        raise SecretsUnavailable() from None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _upsert(runtime: Any, project: str, secret_name: str, annotations: dict[str, Any],
            data: Optional[dict[str, Any]] = None, string_data: Optional[dict[str, Any]] = None) -> Optional[str]:
    """Patch one key set of a project Secret, creating the Secret when it does not exist."""
    namespace = "project-" + project
    body: dict[str, Any] = {"metadata": {"annotations": annotations}}
    if data is not None:
        body["data"] = data
    if string_data is not None:
        body["stringData"] = string_data
    secrets = _api(runtime, "Secret", "v1")
    try:
        try:
            result = secrets.patch(body=body, name=secret_name, namespace=namespace, content_type=_MERGE)
        except ApiException as exc:
            if exc.status != 404:
                raise
            created = {"apiVersion": "v1", "kind": "Secret", "type": "Opaque",
                       "metadata": {"name": secret_name, "namespace": namespace,
                                    "labels": {"platform.example/managed": "true"},
                                    "annotations": {k: v for k, v in annotations.items() if v is not None}}}
            if data:
                created["data"] = {k: v for k, v in data.items() if v is not None}
            if string_data:
                created["stringData"] = string_data
            try:
                result = secrets.create(body=created, namespace=namespace)
            except ApiException as race:
                if race.status != 409:
                    raise
                result = secrets.patch(body=body, name=secret_name, namespace=namespace, content_type=_MERGE)
    except ApiException:
        raise SecretsUnavailable() from None
    return (_plain(result).get("metadata") or {}).get("resourceVersion")


def _drop_previous(runtime: Any, project: str, name: str) -> None:
    previous = _get(runtime, PREVIOUS_SECRET_NAME, project)
    if previous is not None and name in (previous.get("data") or {}):
        _upsert(runtime, project, PREVIOUS_SECRET_NAME, {_VERSION_PREFIX + name: None}, data={name: None})


def write_secret(runtime: Any, project: str, name: str, value: str) -> str:
    """Create or rotate one key; the replaced value is kept in the unmounted previous Secret.

    Returns the Secret's new resourceVersion.
    """
    current = _get(runtime, SECRET_NAME, project)
    held = (current or {}).get("data") or {}
    version = _version_of(_annotations(current), name) + 1 if name in held else 1
    if name in held:
        _upsert(runtime, project, PREVIOUS_SECRET_NAME,
                {_VERSION_PREFIX + name: str(version - 1)}, data={name: held[name]})
    else:
        _drop_previous(runtime, project, name)
    return _upsert(runtime, project, SECRET_NAME,
                   {_CHANGED_PREFIX + name: _now(), _VERSION_PREFIX + name: str(version)},
                   string_data={name: value})


def confirm_secret(runtime: Any, project: str, name: str) -> bool:
    """Revoke the previous value; False when no previous value is held."""
    previous = _get(runtime, PREVIOUS_SECRET_NAME, project)
    if previous is None or name not in (previous.get("data") or {}):
        return False
    _drop_previous(runtime, project, name)
    return True


def revert_secret(runtime: Any, project: str, name: str) -> Optional[str]:
    """Make the previous value current again; None when no previous value is held."""
    previous = _get(runtime, PREVIOUS_SECRET_NAME, project)
    held = (previous or {}).get("data") or {}
    if name not in held:
        return None
    current = _get(runtime, SECRET_NAME, project)
    version = _version_of(_annotations(current), name) + 1
    result = _upsert(runtime, project, SECRET_NAME,
                     {_CHANGED_PREFIX + name: _now(), _VERSION_PREFIX + name: str(version)},
                     data={name: held[name]})
    _drop_previous(runtime, project, name)
    return result


def remove_secret(runtime: Any, project: str, name: str) -> str:
    _drop_previous(runtime, project, name)
    return _upsert(runtime, project, SECRET_NAME,
                   {_CHANGED_PREFIX + name: None, _VERSION_PREFIX + name: None}, data={name: None})


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
