"""Provider observations for v1alpha2 application components."""
from datetime import datetime, timedelta, timezone
from typing import Any

from kubernetes.client.exceptions import ApiException

from .readiness import observe_deployment


def _field(value: Any, name: str, default=None):
    return value.get(name, default) if isinstance(value, dict) else getattr(value, name, default)


def _cron_field_matches(value: int, expression: str, low: int, high: int) -> bool:
    for option in expression.split(","):
        base, *step_part = option.split("/")
        step = int(step_part[0]) if step_part else 1
        if base == "*":
            start, end = low, high
        elif "-" in base:
            start, end = (int(item) for item in base.split("-", 1))
        else:
            start = end = int(base)
        if start <= value <= end and (value - start) % step == 0:
            return True
    return False


def next_run(schedule: str, now: datetime) -> str | None:
    """Calculate the next UTC time for the validated portable five-field cron subset."""
    minute, hour, day, month, weekday = schedule.split()
    candidate = now.astimezone(timezone.utc).replace(second=0, microsecond=0) + timedelta(minutes=1)
    for _ in range(366 * 24 * 60):
        # Kubernetes accepts both Sunday encodings, while Python's Monday is zero.
        cron_weekday = (candidate.weekday() + 1) % 7
        if (_cron_field_matches(candidate.minute, minute, 0, 59)
                and _cron_field_matches(candidate.hour, hour, 0, 23)
                and _cron_field_matches(candidate.day, day, 1, 31)
                and _cron_field_matches(candidate.month, month, 1, 12)
                and _cron_field_matches(cron_weekday, weekday, 0, 7)):
            return candidate.isoformat()
        candidate += timedelta(minutes=1)
    return None


def _scheduled_status(runtime: Any, project: str, component: dict, log, now: datetime) -> dict:
    base = {"name": component["name"], "type": "scheduled", "schedule": component["schedule"],
            "next_run": next_run(component["schedule"], now), "active_runs": 0,
            "last_run_time": None, "last_completion_time": None, "last_result": None,
            "failure": None}
    if runtime is None:
        return {**base, "state": "unknown", "reason": "ObserverUnavailable"}
    try:
        cronjob = runtime.resources.get(api_version="batch/v1", kind="CronJob").get(
            name=component["name"], namespace="project-" + project)
    except ApiException as exc:
        if exc.status == 404:
            return {**base, "state": "not_found", "reason": "CronJobNotFound"}
        log.error("CronJob status query failed project=%s component=%s error_type=%s", project, component["name"], type(exc).__name__)
        return {**base, "state": "unknown", "reason": "ObserverUnavailable"}
    except Exception as exc:
        log.error("CronJob status query failed project=%s component=%s error_type=%s", project, component["name"], type(exc).__name__)
        return {**base, "state": "unknown", "reason": "ObserverUnavailable"}
    status = _field(cronjob, "status", {}) or {}
    active = _field(status, "active", []) or []
    last_success = _field(status, "lastSuccessfulTime")
    last_schedule = _field(status, "lastScheduleTime")
    latest_failure = None
    try:
        jobs = runtime.resources.get(api_version="batch/v1", kind="Job").get(
            namespace="project-" + project,
            label_selector="platform.example/component=" + component["name"])
        for job in _field(jobs, "items", []) or []:
            job_status = _field(job, "status", {}) or {}
            for condition in _field(job_status, "conditions", []) or []:
                if _field(condition, "type") == "Failed" and str(_field(condition, "status")) == "True":
                    completed = _field(job_status, "completionTime") or _field(condition, "lastTransitionTime")
                    candidate = (str(completed or ""), _field(condition, "reason") or "JobFailed")
                    if latest_failure is None or candidate[0] > latest_failure[0]:
                        latest_failure = candidate
    except Exception as exc:
        log.error("Job status query failed project=%s component=%s error_type=%s", project, component["name"], type(exc).__name__)
    if latest_failure and (not last_success or latest_failure[0] >= str(last_success)):
        return {**base, "state": "active" if active else "failed", "reason": None, "active_runs": len(active),
                "last_run_time": str(last_schedule) if last_schedule else latest_failure[0] or None,
                "last_completion_time": latest_failure[0] or None, "last_result": "failed",
                "failure": {"reason": latest_failure[1]}}
    return {**base, "state": "active" if active else "idle", "reason": None, "active_runs": len(active),
            "last_run_time": str(last_schedule) if last_schedule else None,
            "last_completion_time": str(last_success) if last_success else None,
            "last_result": "succeeded" if last_success else None}


def observe_components(runtime: Any, project: str, components: list[dict], log,
                       now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    observed = []
    for component in components:
        if component["type"] == "service":
            readiness = observe_deployment(runtime, project, component["resolved_image"], log, component["name"])
            observed.append({"name": component["name"], "type": "service", "status": readiness})
        else:
            observed.append(_scheduled_status(runtime, project, component, log, now))
    return {"components": observed, "observed_at": now.isoformat()}
