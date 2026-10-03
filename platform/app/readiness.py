"""Live readiness observations for the supported single-container workload."""
from datetime import datetime, timezone
from typing import Any

from kubernetes.client.exceptions import ApiException


def _field(value: Any, name: str, default=None):
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _snapshot(state: str, desired_image: str, *, desired_replicas: int = 1,
              ready_replicas: int = 0, deployment_image: str | None = None,
              active_images: list[str] | None = None, active_image_ids: list[str] | None = None,
              reason: str | None = None) -> dict[str, Any]:
    return {
        "state": state,
        "desired_replicas": desired_replicas,
        "ready_replicas": ready_replicas,
        "desired_image": desired_image,
        "deployment_image": deployment_image,
        "active_images": active_images or [],
        "active_image_ids": active_image_ids or [],
        "reason": reason,
        "observed_at": datetime.now(timezone.utc).isoformat(),
    }


def _pod_diagnostic(pods: list[Any]) -> str | None:
    for pod in pods:
        status = _field(pod, "status", {})
        for condition in _field(status, "conditions", []) or []:
            if (_field(condition, "type") == "PodScheduled"
                    and _field(condition, "status") == "False"):
                return _field(condition, "reason") or "PodNotScheduled"
    for pod in pods:
        status = _field(pod, "status", {})
        for container in _field(status, "containerStatuses", []) or []:
            waiting = _field(_field(container, "state", {}), "waiting")
            if waiting is not None:
                return _field(waiting, "reason") or "ContainerWaiting"
    for pod in pods:
        status = _field(pod, "status", {})
        for condition in _field(status, "conditions", []) or []:
            if _field(condition, "type") == "Ready" and _field(condition, "status") == "False":
                return _field(condition, "reason") or "ContainersNotReady"
    return None


def _active_images(pods: list[Any]) -> tuple[list[str], list[str]]:
    images = set()
    image_ids = set()
    for pod in pods:
        status = _field(pod, "status", {})
        for container in _field(status, "containerStatuses", []) or []:
            image = _field(container, "image")
            if _field(container, "ready") and image:
                images.add(image)
                image_id = _field(container, "imageID")
                if image_id:
                    image_ids.add(image_id)
    return sorted(images), sorted(image_ids)


def observe_deployment(runtime: Any, project: str, desired_image: str,
                       log) -> dict[str, Any]:
    namespace = "project-" + project
    if runtime is None:
        log.error("Deployment readiness observer unavailable project=%s", project)
        return _snapshot("unknown", desired_image, reason="ObserverUnavailable")

    try:
        deployment = runtime.resources.get(
            api_version="apps/v1", kind="Deployment"
        ).get(name=project, namespace=namespace)
    except ApiException as exc:
        if exc.status == 404:
            return _snapshot("not_found", desired_image, reason="DeploymentNotFound")
        log.error("Deployment readiness query failed project=%s error_type=%s",
                  project, type(exc).__name__)
        return _snapshot("unknown", desired_image, reason="ObserverUnavailable")
    except Exception as exc:
        log.error("Deployment readiness query failed project=%s error_type=%s",
                  project, type(exc).__name__)
        return _snapshot("unknown", desired_image, reason="ObserverUnavailable")

    spec = _field(deployment, "spec", {})
    status = _field(deployment, "status", {})
    metadata = _field(deployment, "metadata", {})
    desired_replicas = _field(spec, "replicas", 1)
    desired_replicas = 1 if desired_replicas is None else desired_replicas
    ready_replicas = _field(status, "readyReplicas", 0) or 0
    template_spec = _field(_field(spec, "template", {}), "spec", {})
    containers = _field(template_spec, "containers", []) or []
    deployment_image = _field(containers[0], "image") if containers else None
    base = {
        "desired_replicas": desired_replicas,
        "ready_replicas": ready_replicas,
        "deployment_image": deployment_image,
    }

    try:
        response = runtime.resources.get(api_version="v1", kind="Pod").get(
            namespace=namespace,
            label_selector="app.kubernetes.io/name=" + project,
        )
        pods = _field(response, "items", []) or []
    except Exception as exc:
        log.error("Deployment pod observation failed project=%s error_type=%s",
                  project, type(exc).__name__)
        return _snapshot("unknown", desired_image, **base, reason="ObserverUnavailable")

    images, image_ids = _active_images(pods)
    if deployment_image != desired_image:
        return _snapshot("progressing", desired_image, **base, active_images=images,
                         active_image_ids=image_ids, reason="DeploymentImageMismatch")

    conditions = _field(status, "conditions", []) or []
    for condition in conditions:
        condition_type = _field(condition, "type")
        condition_status = _field(condition, "status")
        condition_reason = _field(condition, "reason")
        if condition_type == "Progressing" and condition_status == "False":
            if condition_reason == "ProgressDeadlineExceeded":
                return _snapshot("failed", desired_image, **base, reason=condition_reason)
        if condition_type == "ReplicaFailure" and condition_status == "True":
            return _snapshot("failed", desired_image, **base,
                             reason=condition_reason or "ReplicaFailure")

    generation = _field(metadata, "generation", 0) or 0
    observed_generation = _field(status, "observedGeneration", 0) or 0
    updated_replicas = _field(status, "updatedReplicas", 0) or 0
    total_replicas = _field(status, "replicas", 0) or 0
    if (desired_replicas > 0 and ready_replicas >= desired_replicas
            and updated_replicas >= desired_replicas
            and total_replicas <= updated_replicas
            and observed_generation >= generation
            and deployment_image == desired_image):
        return _snapshot("ready", desired_image, **base, active_images=images,
                         active_image_ids=image_ids)

    return _snapshot("progressing", desired_image, **base, active_images=images,
                     active_image_ids=image_ids, reason=_pod_diagnostic(pods) or "RolloutInProgress")
