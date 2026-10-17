"""Reconcile resources and every credential generation after restart or interruption."""
from datetime import datetime, timedelta, timezone
from . import catalog, providers


def credentials_to_revoke(conn):
    return conn.execute("""SELECT row_to_json(c),row_to_json(r) FROM store_credentials c
        JOIN store_grants g USING(grant_id) JOIN store_resources r USING(resource_id)
        WHERE c.state<>'revoked' AND (c.expires_at<=now() OR g.state<>'active' OR r.state<>'active'
            OR c.grant_version<>g.version OR EXISTS(SELECT 1 FROM projects p WHERE
                p.name IN (r.owner_project,g.consumer_project) AND p.status='retired'))
        ORDER BY c.expires_at LIMIT 256""").fetchall()


def reconcile(conn):
    """The caller holds the common lifecycle lock for this short batch."""
    for credential, resource in credentials_to_revoke(conn):
        providers.get(resource["provider"]).revoke(resource, credential)
        conn.execute("UPDATE store_credentials SET state='revoked',observed_state='revoked',error_code=NULL WHERE credential_id=%s",
                     (credential["credential_id"],))
    resources = conn.execute("""SELECT row_to_json(r) FROM store_resources r
        WHERE state<>'purged' AND observed_state<>state ORDER BY created_at LIMIT 128""").fetchall()
    for (resource,) in resources:
        provider = providers.get(resource["provider"])
        if resource["state"] == "active":
            provider.provision(resource)
        elif resource["state"] in {"retired", "purging"}:
            held = conn.execute("""SELECT 1 FROM store_credentials c JOIN store_grants g USING(grant_id)
                WHERE g.resource_id=%s AND c.state<>'revoked' LIMIT 1""", (resource["resource_id"],)).fetchone()
            if held:
                continue
            if resource["state"] == "purging":
                provider.purge(resource)
        state = "purged" if resource["state"] == "purging" else resource["state"]
        conn.execute("UPDATE store_resources SET state=%s,observed_state=%s,error_code=NULL WHERE resource_id=%s",
                     (state, state, resource["resource_id"]))
    pending = conn.execute("""SELECT row_to_json(c),row_to_json(r) FROM store_credentials c
        JOIN store_grants g USING(grant_id) JOIN store_resources r USING(resource_id)
        WHERE c.state='issuing' AND c.grant_version=g.version AND g.state='active' AND r.state='active'
            AND r.observed_state='active' AND c.expires_at>now() ORDER BY c.issued_at LIMIT 64""").fetchall()
    for credential, resource in pending:
        providers.get(resource["provider"]).issue(resource, credential)
        conn.execute("UPDATE store_credentials SET state='active',observed_state='active',error_code=NULL WHERE credential_id=%s",
                     (credential["credential_id"],))
    # One replacement generation at a time: an interrupted issuance is retried,
    # never replaced by a third generation that could extend the handover window.
    due = conn.execute("""SELECT row_to_json(g) FROM store_grants g JOIN store_resources r USING(resource_id)
        WHERE g.kind='binding' AND g.state='active' AND r.state='active' AND r.observed_state='active'
        AND NOT EXISTS(SELECT 1 FROM store_credentials c WHERE c.grant_id=g.grant_id
            AND c.grant_version=g.version AND c.state IN ('issuing','active')
            AND c.issued_at>now()-interval '30 days' AND c.expires_at>now())
        ORDER BY g.updated_at LIMIT 64""").fetchall()
    for (grant,) in due:
        catalog.issue(conn, grant)
    conn.execute("""UPDATE store_grants g SET observed_state=state,error_code=NULL
        WHERE NOT EXISTS(SELECT 1 FROM store_credentials c WHERE c.grant_id=g.grant_id
            AND c.state<>'revoked' AND (g.state<>'active' OR c.grant_version<>g.version))""")


def loop(stop, control):
    while not stop.is_set():
        try:
            with control.connect() as conn, conn.transaction():
                # Avoid blocking API transactions if deployments own the lifecycle.
                if not conn.execute("SELECT pg_try_advisory_xact_lock(731904)").fetchone()[0]:
                    stop.wait(1)
                    continue
                reconcile(conn)
        except Exception as exc:
            control.log.error("Store reconciliation failed error_type=%s", type(exc).__name__)
        stop.wait(2)
