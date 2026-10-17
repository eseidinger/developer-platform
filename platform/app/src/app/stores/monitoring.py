"""Measured logical usage and bounded, secret-free node-exporter textfile metrics."""
import json
import os
from pathlib import Path
import time
from . import providers


def sample(conn):
    # Eight bounded provider calls per turn; failures retain the last successful
    # reading and have their own attempt timestamp instead of reporting zero.
    rows = conn.execute("""SELECT row_to_json(r) FROM store_resources r
        WHERE state IN ('active','retired') AND observed_state=state
        AND (usage_attempt_at IS NULL OR usage_attempt_at<now()-interval '60 seconds')
        ORDER BY usage_attempt_at NULLS FIRST LIMIT 8""").fetchall()
    for (resource,) in rows:
        try:
            used = providers.get(resource['provider']).usage(resource)
            if isinstance(used, bool) or not isinstance(used, int) or used < 0:
                raise ValueError('Invalid usage')
        except Exception:
            conn.execute("""UPDATE store_resources SET usage_attempt_at=now(),usage_error=true
                WHERE resource_id=%s""", (resource['resource_id'],))
        else:
            conn.execute("""UPDATE store_resources SET used_bytes=%s,usage_measured_at=now(),
                usage_attempt_at=now(),usage_error=false WHERE resource_id=%s""", (used, resource['resource_id']))


def exposition(resources, credentials, now=None, quarantined=False):
    """Only stable UUIDs, validated project names and finite provider IDs are labels."""
    lines = []
    def gauge(name, help_text):
        full = 'platform_store_' + name
        lines.extend(['# HELP ' + full + ' ' + help_text, '# TYPE ' + full + ' gauge'])
        return full
    series = {
        'quota_bytes': gauge('quota_bytes', 'Approved logical bytes; not a provider hard-limit guarantee.'),
        'used_bytes': gauge('used_bytes', 'Last successfully measured logical usage; inspect measurement age/error.'),
        'usage_measured_timestamp_seconds': gauge('usage_measured_timestamp_seconds', 'Last successful measurement, zero when unknown.'),
        'usage_error': gauge('usage_error', 'Last usage attempt failed; retained usage may be stale.'),
        'reconcile_pending': gauge('reconcile_pending', 'Desired resource state differs from observed state.'),
        'hard_quota': gauge('hard_quota', 'One only for verified provider hard enforcement; zero means advisory.'),
        'credentials_active': gauge('credentials_active', 'Current non-expired active credential generations.'),
        'credentials_cleanup_pending': gauge('credentials_cleanup_pending', 'Expired, revoked-grant or stale-version provider identities awaiting cleanup.'),
    }
    counts = {r['resource_id']: r for r in credentials}
    for row in resources:
        labels = '{' + ','.join(key + '=' + json.dumps(str(value)) for key, value in {
            'project': row['owner_project'], 'resource_id': row['resource_id'], 'provider': row['provider']}.items()) + '}'
        stamp = row.get('usage_measured_at')
        if isinstance(stamp, str):
            from datetime import datetime
            stamp = datetime.fromisoformat(stamp)
        values = {'quota_bytes': row['quota_bytes'], 'used_bytes': row.get('used_bytes'),
            'usage_measured_timestamp_seconds': stamp.timestamp() if stamp else 0,
            'usage_error': int(bool(row.get('usage_error'))),
            'reconcile_pending': int(row['state'] != row['observed_state']),
            # Extend only after provider-specific hard growth-denial fixtures pass.
            'hard_quota': int(row['provider'] == 's3'),
            'credentials_active': counts.get(row['resource_id'], {}).get('active', 0),
            'credentials_cleanup_pending': counts.get(row['resource_id'], {}).get('cleanup', 0)}
        for key, value in values.items():
            if value is not None:
                lines.append(f'{series[key]}{labels} {value}')
    guard = gauge('recovery_required', 'Restored access remains quarantined pending verified intent and source reconciliation.')
    lines.append(f'{guard} {int(quarantined)}')
    heartbeat = gauge('worker_last_success_timestamp_seconds', 'Last committed successful store worker pass and metrics publication.')
    lines.append(f'{heartbeat} {time.time() if now is None else now}')
    return '\n'.join(lines) + '\n'


def publish(conn):
    from ..monitoring import atomic_write
    resources = [r[0] for r in conn.execute("SELECT row_to_json(r) FROM store_resources r WHERE state<>'purged' ORDER BY resource_id LIMIT 128").fetchall()]
    credentials = [r[0] for r in conn.execute("""SELECT row_to_json(counts) FROM (
        SELECT g.resource_id::text AS resource_id,
        count(*) FILTER(WHERE c.state IN ('active','retiring') AND c.expires_at>now()
            AND g.state='active' AND r.state='active' AND c.grant_version=g.version) AS active,
        count(*) FILTER(WHERE c.state<>'revoked' AND (c.expires_at<=now()
            OR g.state<>'active' OR r.state<>'active' OR c.grant_version<>g.version)) AS cleanup
        FROM store_credentials c JOIN store_grants g USING(grant_id) JOIN store_resources r USING(resource_id)
        GROUP BY g.resource_id) counts""").fetchall()]
    directory = Path(os.environ.get('MONITORING_DISCOVERY_DIR', '/var/lib/platform-monitoring'))
    directory.mkdir(parents=True, exist_ok=True)
    from . import recovery
    atomic_write(directory / 'stores.prom', exposition(resources, credentials, quarantined=recovery.required(conn)))
