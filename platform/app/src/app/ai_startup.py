"""Reduce bounded, scoped startup logs to fixed codes before model context."""

import re

from kubernetes.client import CoreV1Api

from .manifests import validate_name
from .readiness import _field

MAX_PODS = 2
MAX_BYTES = 8192
UNKNOWN_FLAG = re.compile(r"flag provided but not defined: -{1,2}[A-Za-z][A-Za-z0-9_-]{0,63}\Z")


def observe_startup_failure(runtime, project, component, revision, *, api=None):
    """No model-controlled query, returned log text, or stored provider content."""
    validate_name(project)
    validate_name(component)
    result = {"state": "no_match", "revision": revision, "failure_codes": [],
              "source": "bounded-container-log-signatures", "checked_containers": 0,
              "unavailable_reads": 0, "truncated": False}
    if runtime is None:
        return {**result, "state": "unavailable"}
    namespace = "project-" + project
    try:
        response = runtime.resources.get(api_version="v1", kind="Pod").get(
            namespace=namespace, label_selector="platform.example/component=" + component)
        pods = []
        for pod in _field(response, "items", []) or []:
            metadata = _field(pod, "metadata", {})
            labels = _field(metadata, "labels", {}) or {}
            annotations = _field(metadata, "annotations", {}) or {}
            if (_field(metadata, "namespace") != namespace
                    or labels.get("app.kubernetes.io/name") != project
                    or labels.get("platform.example/component") != component
                    or annotations.get("platform.example/revision") != str(revision)):
                continue
            for status in _field(_field(pod, "status", {}), "containerStatuses", []) or []:
                if _field(status, "name") != component:
                    continue
                terminated = [_field(_field(status, state, {}), "terminated", {}) or {}
                              for state in ("state", "lastState")]
                if any(type(_field(t, "exitCode")) is int and _field(t, "exitCode") != 0 for t in terminated):
                    pods.append(pod)
        api = api or CoreV1Api(runtime.client)
    except Exception:
        return {**result, "state": "unavailable"}
    result["truncated"] = len(pods) > MAX_PODS
    for pod in pods[:MAX_PODS]:
        result["checked_containers"] += 1
        for previous in (False, True):
            response = None
            try:
                response = api.read_namespaced_pod_log(
                    _field(_field(pod, "metadata"), "name"), namespace, container=component,
                    previous=previous, timestamps=False, tail_lines=20, limit_bytes=MAX_BYTES,
                    since_seconds=3600, _preload_content=False, _request_timeout=(2, 3))
                raw = response.read(MAX_BYTES + 1)
                if len(raw) > MAX_BYTES:
                    result["truncated"] = True
                    continue
                # Ignore arbitrary messages, values, paths and instructions.
                if any(UNKNOWN_FLAG.fullmatch(line) for line in raw.decode("utf-8", errors="replace").splitlines()):
                    result.update(state="ok", failure_codes=["unrecognized_startup_option"])
                    return result
            except Exception:
                result["unavailable_reads"] += 1
            finally:
                if response is not None:
                    try:
                        response.close()
                        response.release_conn()
                    except Exception:
                        pass
    if result["unavailable_reads"]:
        result["state"] = "incomplete"
    return result
