"""Publish bounded, non-secret security-event metrics from durable audit records."""
import time
from pathlib import Path

from .audit import audit_reader_connect
from .monitoring import atomic_write


WINDOW_SECONDS = 15 * 60
MAX_SERIES = 200


def _escape(value) -> str:
    return str(value or "").replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _labels(**values) -> str:
    return ",".join(f'{key}="{_escape(value)}"' for key, value in values.items())


def security_event_rows(conn):
    """Return recent security evidence grouped by stable affected-resource labels."""
    return conn.execute("""WITH categorized AS (
            SELECT id, occurred_at, target_kind, target_id,
                   COALESCE(scope->>'project', '') AS project,
                   CASE
                     WHEN action = 'authentication' AND result = 'denied' THEN 'authentication_failure'
                     WHEN action = 'authorization' AND result = 'denied' THEN 'access_denial'
                     WHEN action LIKE 'membership.%' AND result = 'succeeded' THEN 'privileged_change'
                   END AS category
            FROM platform_audit.events
            WHERE occurred_at >= now() - make_interval(secs => %s)
        )
        SELECT category, target_kind, target_id, project, count(*)::bigint,
               max(id)::bigint, extract(epoch FROM max(occurred_at))::bigint
        FROM categorized
        WHERE category IS NOT NULL
        GROUP BY category, target_kind, target_id, project
        ORDER BY max(occurred_at) DESC
        LIMIT %s""", (WINDOW_SECONDS, MAX_SERIES)).fetchall()


def render(rows, now=None) -> str:
    """Render Prometheus text format without identities, credentials, or event detail."""
    lines = [
        "# HELP platform_security_events_in_window Recent security-relevant audit events by category and resource.",
        "# TYPE platform_security_events_in_window gauge",
        "# HELP platform_security_latest_event_id Latest durable audit event ID for a security-event series.",
        "# TYPE platform_security_latest_event_id gauge",
        "# HELP platform_security_latest_event_timestamp_seconds Occurrence time of the latest security event.",
        "# TYPE platform_security_latest_event_timestamp_seconds gauge",
    ]
    for category, target_kind, target_id, project, count, event_id, occurred_at in rows:
        labels = _labels(category=category, target_kind=target_kind, target_id=target_id, project=project)
        lines.append(f"platform_security_events_in_window{{{labels}}} {count}")
        lines.append(f"platform_security_latest_event_id{{{labels}}} {event_id}")
        lines.append(f"platform_security_latest_event_timestamp_seconds{{{labels}}} {occurred_at}")
    lines.extend([
        "# HELP platform_security_audit_collection_success Timestamp of the latest successful security-audit collection.",
        "# TYPE platform_security_audit_collection_success gauge",
        f"platform_security_audit_collection_success {int(time.time() if now is None else now)}",
    ])
    return "\n".join(lines) + "\n"


def publish(directory: str, now=None) -> None:
    """Replace metrics only after a successful restricted-reader query."""
    with audit_reader_connect() as conn:
        content = render(security_event_rows(conn), now)
    Path(directory).mkdir(parents=True, exist_ok=True)
    atomic_write(Path(directory) / "security-events.prom", content)


def security_alert_loop(stop, directory: str, log) -> None:
    while not stop.is_set():
        try:
            publish(directory)
        except Exception:
            # Audit data and database errors can contain sensitive context.
            log.error("Security audit metric collection failed; retaining previous metrics")
        stop.wait(30)
