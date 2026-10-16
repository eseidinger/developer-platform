"""Bounded application log signatures; raw messages never leave this module."""

import json
import re
from datetime import datetime, timezone

from kubernetes.client import CoreV1Api

from .manifests import validate_name
from .readiness import _field

MAX_PODS = 2
MAX_BYTES = 8192
UNKNOWN_FLAG = re.compile(r"flag provided but not defined: -{1,2}[A-Za-z][A-Za-z0-9_-]{0,63}\Z")
HOST_RESOLUTION = re.compile(
    r'could not translate host name "[^"\r\n]{1,253}" to address: '
    r'(?:Name or service not known|Temporary failure in name resolution|nodename nor servname provided, or not known)\Z')
QUEUE_POOL = re.compile(
    r"QueuePool limit of size [0-9]{1,7} overflow [0-9]{1,7} reached, connection timed out, timeout [0-9]{1,7}(?:\.[0-9]{1,6})?"
    r"(?: \(Background on this error at: https://sqlalche\.me/e/[0-9]{1,2}/[a-z0-9]{1,12}\))?\Z")
HIKARI = re.compile(
    r"[A-Za-z0-9_.-]{1,64} - Connection is not available, request timed out after [0-9]{1,9}ms"
    r"(?:\.| \(total=[0-9]{1,7}, active=[0-9]{1,7}, idle=[0-9]{1,7}, waiting=[0-9]{1,7}\))?\Z")
PREFIXES = ("psycopg.OperationalError: ", "psycopg2.OperationalError: ",
            "sqlalchemy.exc.OperationalError: (psycopg2.OperationalError) ",
            "sqlalchemy.exc.OperationalError: (psycopg.OperationalError) ",
            "sqlalchemy.exc.TimeoutError: ", "java.sql.SQLTransientConnectionException: ",
            "java.sql.SQLException: ", "java.util.concurrent.TimeoutException: ", "psql: error: ")


def failure_codes(raw):
    """Recognize English driver signatures, not arbitrary timeout/DNS prose."""
    if not isinstance(raw, bytes) or len(raw) > MAX_BYTES:
        return []
    codes = set()
    for line in raw.decode("utf-8", errors="replace").splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                value = json.loads(line)
                line = value.get("message", "") if isinstance(value, dict) else ""
                if not isinstance(line, str):
                    continue
            except ValueError:
                continue
        if line.startswith("Caused by: "):
            line = line.removeprefix("Caused by: ")
        agroal_context = line.startswith(("java.sql.SQLException: ", "java.util.concurrent.TimeoutException: "))
        for prefix in PREFIXES:
            if line.startswith(prefix):
                line = line.removeprefix(prefix)
                break
        if UNKNOWN_FLAG.fullmatch(line):
            codes.add("unrecognized_startup_option")
        if HOST_RESOLUTION.fullmatch(line):
            codes.add("database_hostname_resolution_failed")
        if QUEUE_POOL.fullmatch(line):
            codes.add("database_pool_capacity_timeout")
        if HIKARI.fullmatch(line) or agroal_context and line in {
                "Acquisition timeout while waiting for connection", "Sorry, acquisition timeout!"}:
            codes.add("database_pool_acquisition_timeout")
    return sorted(codes)


def observe_failure_signals(runtime, project, component, revision, *, api=None,
                            require_nonzero_exit=False, startup_only=False):
    validate_name(project)
    validate_name(component)
    result = {"state": "no_match", "revision": revision, "component": component, "failure_codes": [],
              "source": "bounded-container-log-signatures", "checked_containers": 0,
              "unavailable_reads": 0, "truncated": False, "window_seconds": 3600,
              "coverage": "sampled_recent_output", "observed_at": datetime.now(timezone.utc).isoformat()}
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
                failed = any(type(_field(t, "exitCode")) is int and _field(t, "exitCode") != 0
                             for t in terminated)
                running = _field(_field(status, "state", {}), "running") is not None
                if failed or not require_nonzero_exit and running:
                    restarts = _field(status, "restartCount", 0)
                    has_previous = bool(_field(status, "lastState", {})) or type(restarts) is int and restarts > 0
                    pods.append((pod, has_previous))
                    break
        api = api or CoreV1Api(runtime.client)
    except Exception:
        return {**result, "state": "unavailable"}
    result["truncated"] = len(pods) > MAX_PODS
    codes = set()
    for pod, has_previous in pods[:MAX_PODS]:
        result["checked_containers"] += 1
        for previous in ((False, True) if has_previous else (False,)):
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
                codes.update(code for code in failure_codes(raw)
                             if not startup_only or code == "unrecognized_startup_option")
                if codes and startup_only:
                    result.update(state="ok", failure_codes=sorted(codes))
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
    result["failure_codes"] = sorted(codes)
    result["state"] = "ok" if codes else "incomplete" if result["unavailable_reads"] else "no_match"
    return result
