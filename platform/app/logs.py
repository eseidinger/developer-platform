from datetime import datetime, timezone
from typing import Any

from kubernetes.client import CoreV1Api
from kubernetes.client.exceptions import ApiException

from .audit import redact

MAX_LINE_CHARS = 2000
MAX_PODS = 10
MAX_BYTES_PER_CONTAINER = 262144


def _get(value: Any, name: str, default=None):
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _result(state: str, reason: str | None, now: datetime, lines=None, truncated=False, unavailable=0):
    return {"state": state, "reason": reason, "lines": lines or [], "truncated": truncated,
            "unavailable_containers": unavailable, "observed_at": now.isoformat()}


def _decode(response: Any) -> str:
    """The raw body is decoded here because the client's own str deserialisation can mangle logs."""
    data = response.data if hasattr(response, "data") else response
    return data.decode("utf-8", errors="replace") if isinstance(data, bytes) else str(data or "")


def _parse(text: str, pod: str, container: str, previous: bool) -> list[dict[str, Any]]:
    lines = []
    for raw in text.splitlines():
        timestamp, _, message = raw.partition(" ")
        lines.append({"timestamp": timestamp, "pod": pod, "container": container, "previous": previous,
                      "message": redact(message)[:MAX_LINE_CHARS]})
    return lines


def observe_logs(runtime: Any, project: str, log, tail: int, since_seconds: int | None,
                 api: Any = None, now: datetime | None = None, component: str | None = None) -> dict[str, Any]:
    """Read recent timestamped log lines for a project from the Kubernetes log API.

    `state` is `ok`, `no_pods`, `no_output` or `unavailable`. A container that has not started
    yet is read from its previous run, so a crash loop can still be diagnosed. Redaction is best
    effort: an application can print anything.
    """
    now = now or datetime.now(timezone.utc)
    if runtime is None:
        return _result("unavailable", "LogApiUnavailable", now)
    namespace = "project-" + project
    try:
        selector = ("platform.example/component=" + component if component
                    else "app.kubernetes.io/name=" + project)
        pods = _get(runtime.resources.get(api_version="v1", kind="Pod").get(
            namespace=namespace, label_selector=selector), "items") or []
        api = api or CoreV1Api(runtime.client)
    except Exception as exc:
        log.error("Pod log query failed project=%s error_type=%s", project, type(exc).__name__)
        return _result("unavailable", "LogApiUnavailable", now)
    if not pods:
        return _result("no_pods", "NoPodsForProject", now)

    options = {"_preload_content": False, "timestamps": True, "tail_lines": tail, "limit_bytes": MAX_BYTES_PER_CONTAINER}
    if since_seconds is not None:
        options["since_seconds"] = since_seconds
    lines, failed, waiting, attempted, truncated = [], 0, 0, 0, False
    for pod in sorted(pods, key=lambda p: _get(_get(p, "metadata"), "name"))[:MAX_PODS]:
        pod_name = _get(_get(pod, "metadata"), "name")
        for container in _get(_get(pod, "spec"), "containers") or []:
            container_name = _get(container, "name")
            attempted += 1
            for previous in (False, True):
                try:
                    text = api.read_namespaced_pod_log(
                        pod_name, namespace, container=container_name,
                        **options, **({"previous": True} if previous else {}))
                except ApiException as exc:
                    if exc.status == 400 and not previous:
                        continue
                    if exc.status == 400:
                        waiting += 1
                        break
                    failed += 1
                    log.error("Pod log read failed project=%s error_type=ApiException status=%s", project, exc.status)
                    break
                except Exception as exc:
                    failed += 1
                    log.error("Pod log read failed project=%s error_type=%s", project, type(exc).__name__)
                    break
                lines.extend(_parse(_decode(text), pod_name, container_name, previous))
                break
    if failed == attempted:
        return _result("unavailable", "LogApiUnavailable", now, unavailable=failed)
    failed += waiting
    lines.sort(key=lambda l: l["timestamp"])
    if len(lines) > tail:
        lines, truncated = lines[-tail:], True
    if not lines:
        return _result("no_output", "NoLogLines", now, unavailable=failed)
    return _result("ok", None, now, lines, truncated, failed)
