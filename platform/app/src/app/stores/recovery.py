"""Restore quarantine: old catalog rows cannot activate data access automatically."""


def required(conn):
    row = conn.execute("SELECT recovery_required FROM store_control WHERE singleton").fetchone()
    # Missing/malformed metadata fails closed; initialize establishes the row.
    return row is None or row[0] is not False


def quarantine(conn):
    conn.execute("UPDATE store_control SET recovery_required=true WHERE singleton")
    # Desired grants are retained for review, but ALL recovered generations end.
    # A recovered human key never becomes a currently authorized lease by itself.
    conn.execute("UPDATE store_credentials SET expires_at=LEAST(expires_at,now()) WHERE state<>'revoked'")


def validate_manifest(value):
    """Strict non-secret resource disposition from the latest verified bundle."""
    from pydantic import BaseModel, ConfigDict, Field
    from typing import Literal
    from datetime import datetime
    from uuid import UUID
    from .contract import NAME

    class Resource(BaseModel):
        model_config = ConfigDict(extra='forbid')
        resource_id: UUID
        owner_project: str = Field(pattern=NAME, max_length=32)
        name: str = Field(pattern=NAME, max_length=32)
        provider: Literal['postgresql', 's3', 'opensearch', 'neo4j', 'qdrant']
        state: Literal['active', 'retired', 'purging', 'purged']
        version: int = Field(ge=1)
        quota_bytes: int = Field(gt=0)
        extensions: list[Literal['vector', 'age']]

    class Manifest(BaseModel):
        model_config = ConfigDict(extra='forbid')
        format: Literal[1]
        captured_at: datetime
        resources: list[Resource] = Field(max_length=100000)

    result = Manifest.model_validate(value).model_dump(mode='json')
    ids = [row['resource_id'] for row in result['resources']]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate recovery identity')
    return result


def reconcile(conn, manifest, apply=False):
    """Never restore an old grant. Fresh explicit approval follows recovery."""
    from . import catalog, providers
    manifest = validate_manifest(manifest)
    if not required(conn):
        raise catalog.Conflict('Recovery quarantine must be set before reconciliation')
    rows = [row[0] for row in conn.execute('SELECT row_to_json(r) FROM store_resources r').fetchall()]
    current = {row['resource_id']: row for row in rows}
    latest = {row['resource_id']: row for row in manifest['resources']}
    if set(current) - set(latest):
        raise catalog.Conflict('Latest verified recovery manifest does not cover this catalog')
    for identity, row in current.items():
        known = latest[identity]
        if (known['owner_project'] != row['owner_project'] or known['provider'] != row['provider']
                or known['version'] < row['version']):
            raise catalog.Conflict('Recovery identity, ownership or manifest version disagrees')
    # Later-created live resources missing from an older data snapshot are not
    # silently recreated as empty databases. Choose a sufficiently recent backup.
    if any(identity not in current and row['state'] not in {'purging','purged'}
           for identity, row in latest.items()):
        raise catalog.Conflict('Data snapshot predates a retained resource; choose a newer snapshot')
    plan = {'purge': [identity for identity, r in latest.items() if r['state'] in {'purging','purged'}],
        'retain': [identity for identity, r in latest.items() if r['state'] in {'active','retired'}],
        'grant_policy': 'revoke all recovered grants; require fresh explicit approval', 'applied': False}
    if not apply:
        return plan
    # Revoke even catalog tombstones: pg_dumpall does not snapshot role state and
    # every database at one instant, so a role restored earlier could be stale.
    credentials = conn.execute("""SELECT row_to_json(c),row_to_json(r) FROM store_credentials c
        JOIN store_grants g USING(grant_id) JOIN store_resources r USING(resource_id)""").fetchall()
    for credential, resource in credentials:
        providers.get(resource['provider']).revoke(resource, credential)
    conn.execute("""UPDATE store_credentials SET state='revoked',observed_state='revoked',
        expires_at=LEAST(expires_at,now()),error_code=NULL""")
    conn.execute("""UPDATE store_grants SET state='revoked',observed_state='revoked',
        version=version+1,delivered_credential_id=NULL,error_code=NULL WHERE state<>'revoked'""")
    # Avoid transient unique-name collisions when names changed between snapshots.
    conn.execute("UPDATE store_resources SET name='recovery-'||replace(resource_id::text,'-','') WHERE state<>'purged'")
    for identity, row in latest.items():
        provider = providers.get(row['provider'])
        if row['state'] in {'purging','purged'}:
            provider.purge(row)
            state = 'purged'
        else:
            provider.validate_recovery(row)
            state = row['state']
        if identity in current:
            conn.execute("""UPDATE store_resources SET name=%s,quota_bytes=%s,state=%s,
                observed_state=%s,version=%s,error_code=NULL,updated_at=now() WHERE resource_id=%s""",
                (row['name'], row['quota_bytes'], state, state, row['version'] + 1, identity))
    conn.execute('UPDATE store_control SET recovery_required=false WHERE singleton')
    plan['applied'] = True
    return plan


def main():
    import argparse
    import hashlib
    import json
    import os
    import sys
    import psycopg
    from . import catalog
    parser = argparse.ArgumentParser(description='Review/apply latest verified resource intents under restore quarantine; manifest JSON comes from stdin.')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--manifest-sha256', required=True)
    args = parser.parse_args()
    try:
        data = sys.stdin.buffer.read(16 * 1024 * 1024 + 1)
        if len(data) > 16 * 1024 * 1024 or hashlib.sha256(data).hexdigest() != args.manifest_sha256:
            raise ValueError('Recovery manifest checksum mismatch')
        manifest = json.loads(data)
        with psycopg.connect(host=os.environ['POSTGRES_HOST'], dbname='platform', user='postgres',
                password=os.environ['POSTGRES_PASSWORD'], connect_timeout=3) as conn, conn.transaction():
            catalog.lock(conn)
            plan = reconcile(conn, manifest, args.apply)
        print(json.dumps(plan, sort_keys=True))
    except Exception as error:
        # Provider/query errors can contain connection secrets or source data.
        message = str(error) if isinstance(error, catalog.Conflict) else type(error).__name__
        print('Store recovery remains quarantined: ' + message, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
