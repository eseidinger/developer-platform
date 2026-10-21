"""Reconcile resources and every credential generation after restart or interruption."""

from . import catalog, providers, recovery


def _attempt(conn, table, field, identity, operation):
    # All identifiers here are module literals. Savepoints isolate provider
    # failures so one broken store cannot starve another store's cleanup.
    try:
        with conn.transaction():
            operation()
        return True
    except Exception as error:
        code = (
            "ProviderUnavailable"
            if isinstance(error, providers.ProviderUnavailable)
            else "ProviderOperationFailed"
        )
        conn.execute(
            f"UPDATE {table} SET error_code=%s WHERE {field}=%s", (code, identity)
        )
        return False


def _deny(conn, credential, resource):
    providers.get(resource["provider"]).revoke(resource, credential)
    conn.execute(
        "UPDATE store_credentials SET state='revoked',observed_state='revoked',error_code=NULL WHERE credential_id=%s",
        (credential["credential_id"],),
    )


def deny_stale(conn, rows):
    # A full-access native user can damage its instance's admin account. Attempt
    # one failed cleanup per resource/pass, rather than holding the global lock
    # through every outstanding generation of the same broken instance.
    failed = set()
    for credential, resource in rows:
        identity = resource["resource_id"]
        if identity in failed:
            continue
        if not _attempt(
            conn,
            "store_credentials",
            "credential_id",
            credential["credential_id"],
            lambda c=credential, r=resource: _deny(conn, c, r),
        ):
            failed.add(identity)


def reconcile(conn, control=None):
    """Caller holds the common lifecycle lock. Relay enforces deadlines independently."""
    if recovery.required(conn):
        recovered = conn.execute("""SELECT row_to_json(c),row_to_json(r) FROM store_credentials c
            JOIN store_grants g USING(grant_id) JOIN store_resources r USING(resource_id)
            WHERE c.state<>'revoked' LIMIT 256""").fetchall()
        deny_stale(conn, recovered)
        return
    conn.execute("""UPDATE store_resources r SET state='retired',observed_state='pending',version=version+1
        FROM projects p WHERE p.name=r.owner_project AND r.state='active' AND (p.status='retired'
            OR EXISTS(SELECT 1 FROM store_project_retirements t WHERE t.project=p.name))""")
    conn.execute("""UPDATE store_grants g SET state='revoked',observed_state='pending',version=version+1
        WHERE g.state IN ('pending','active') AND (EXISTS(SELECT 1 FROM store_resources r
            WHERE r.resource_id=g.resource_id AND r.state<>'active') OR EXISTS(SELECT 1 FROM projects p
            WHERE p.name=g.consumer_project AND (p.status='retired'
                OR EXISTS(SELECT 1 FROM store_project_retirements t WHERE t.project=p.name))))""")
    stale = conn.execute("""SELECT row_to_json(c),row_to_json(r) FROM store_credentials c
        JOIN store_grants g USING(grant_id) JOIN store_resources r USING(resource_id)
        WHERE c.state<>'revoked' AND (c.expires_at<=now() OR g.state<>'active' OR r.state<>'active'
            OR c.grant_version<>g.version)
        ORDER BY c.expires_at LIMIT 256""").fetchall()
    deny_stale(conn, stale)
    resources = conn.execute("""SELECT row_to_json(r) FROM store_resources r
        WHERE state<>'purged' AND observed_state<>state ORDER BY updated_at LIMIT 128""").fetchall()
    for (resource,) in resources:

        def apply_resource(res=resource):
            provider = providers.get(res["provider"])
            if res["state"] == "active":
                instance = provider.provision(res)
                if res["provider"] == "neo4j":
                    conn.execute(
                        """INSERT INTO store_instances(resource_id,host,port) VALUES(%s,%s,7687)
                        ON CONFLICT(resource_id) DO UPDATE SET host=excluded.host,port=excluded.port""",
                        (res["resource_id"], instance["host"]),
                    )
            elif res["state"] in {"retired", "purging"}:
                held = conn.execute(
                    """SELECT 1 FROM store_credentials c JOIN store_grants g USING(grant_id)
                    WHERE g.resource_id=%s AND c.state<>'revoked' LIMIT 1""",
                    (res["resource_id"],),
                ).fetchone()
                pending_grant = conn.execute(
                    """SELECT 1 FROM store_grants WHERE resource_id=%s
                    AND observed_state<>state LIMIT 1""",
                    (res["resource_id"],),
                ).fetchone()
                if held or pending_grant:
                    return
                if res["provider"] == "neo4j" and res["state"] == "retired":
                    provider.retire(res)
                if res["state"] == "purging":
                    if res.get("purge_backup_version") != res["version"] or not res.get(
                        "purge_backup_snapshot"
                    ):
                        conn.execute(
                            "UPDATE store_resources SET error_code='PurgeAwaitingVerifiedBackup' WHERE resource_id=%s",
                            (res["resource_id"],),
                        )
                        return
                    provider.purge(res)
            state = "purged" if res["state"] == "purging" else res["state"]
            conn.execute(
                "UPDATE store_resources SET state=%s,observed_state=%s,error_code=NULL WHERE resource_id=%s",
                (state, state, res["resource_id"]),
            )

        _attempt(
            conn,
            "store_resources",
            "resource_id",
            resource["resource_id"],
            apply_resource,
        )
    conn.execute("""DELETE FROM store_console_sessions s USING store_credentials c
        WHERE s.credential_id=c.credential_id AND (s.expires_at<=now() OR c.state='revoked')""")
    pending = conn.execute("""SELECT row_to_json(c),row_to_json(r),g.kind FROM store_credentials c
        JOIN store_grants g USING(grant_id) JOIN store_resources r USING(resource_id)
        WHERE c.state='issuing' AND c.grant_version=g.version AND g.state='active' AND r.state='active'
            AND r.observed_state='active' AND c.expires_at>now() ORDER BY c.issued_at LIMIT 64""").fetchall()
    for credential, resource, kind in pending:
        credential = {**credential, "kind": kind}

        def activate(c=credential, r=resource):
            providers.get(r["provider"]).issue(r, c)
            conn.execute(
                "UPDATE store_credentials SET state='active',observed_state='active',error_code=NULL WHERE credential_id=%s",
                (c["credential_id"],),
            )

        _attempt(
            conn,
            "store_credentials",
            "credential_id",
            credential["credential_id"],
            activate,
        )
    due = conn.execute("""SELECT row_to_json(g) FROM store_grants g JOIN store_resources r USING(resource_id)
        WHERE g.kind='binding' AND g.state='active' AND r.state='active' AND r.observed_state='active'
        AND NOT EXISTS(SELECT 1 FROM store_credentials c WHERE c.grant_id=g.grant_id
            AND c.grant_version=g.version AND c.state IN ('issuing','active')
            AND c.issued_at>now()-interval '30 days' AND c.expires_at>now())
        ORDER BY g.updated_at LIMIT 64""").fetchall()
    for (grant,) in due:
        _attempt(
            conn,
            "store_grants",
            "grant_id",
            grant["grant_id"],
            lambda g=grant: catalog.issue(conn, g),
        )
    ready = set()
    runtime_ok = control is None
    if control is not None:
        try:
            from .workloads import reconcile_runtime

            ready = reconcile_runtime(conn, control)
            runtime_ok = True
        except Exception:
            control.log.error(
                "Store consumer reconciliation failed error_type=RuntimeReconcileFailed"
            )
    for project, component in ready:
        conn.execute(
            """UPDATE store_grants g SET delivered_credential_id=(SELECT credential_id
            FROM store_credentials c WHERE c.grant_id=g.grant_id AND c.state='active' AND c.grant_version=g.version
            ORDER BY c.issued_at DESC LIMIT 1) WHERE g.kind='binding' AND g.consumer_project=%s
            AND g.component=%s AND g.state='active'""",
            (project, component),
        )
    # Retire old generations early only after fresh credentials work and the
    # consumer has picked them up. The hard expiry deadline never moves on retry.
    rotating = conn.execute("""SELECT row_to_json(old),row_to_json(fresh),row_to_json(r),row_to_json(g)
        FROM store_credentials old JOIN store_grants g USING(grant_id) JOIN store_resources r USING(resource_id)
        JOIN LATERAL(SELECT c.* FROM store_credentials c WHERE c.grant_id=g.grant_id
            AND c.state='active' AND c.grant_version=g.version AND c.expires_at>now()
            ORDER BY c.issued_at DESC LIMIT 1) fresh ON true
        WHERE old.state='retiring' AND old.expires_at>now() AND g.state='active' LIMIT 64""").fetchall()
    for old, fresh, resource, grant in rotating:
        if (
            grant["bound_once"]
            and (grant["consumer_project"], grant["component"]) not in ready
        ):
            continue

        def finish_handover(previous=old, new=fresh, res=resource, g=grant):
            providers.get(res["provider"]).probe(res, new)
            _deny(conn, previous, res)
            conn.execute(
                "UPDATE store_grants SET delivered_credential_id=%s WHERE grant_id=%s",
                (new["credential_id"], g["grant_id"]),
            )

        _attempt(
            conn,
            "store_credentials",
            "credential_id",
            old["credential_id"],
            finish_handover,
        )
    if runtime_ok:
        conn.execute("""UPDATE store_grants g SET observed_state=state,error_code=NULL
            WHERE NOT EXISTS(SELECT 1 FROM store_credentials c WHERE c.grant_id=g.grant_id
                AND c.state<>'revoked' AND (g.state<>'active' OR c.grant_version<>g.version))
            AND (g.kind='human' OR g.state<>'active' OR EXISTS(SELECT 1 FROM store_credentials c
                WHERE c.grant_id=g.grant_id AND c.grant_version=g.version AND c.state='active' AND c.expires_at>now()))""")


def loop(stop, control):
    while not stop.is_set():
        try:
            with control.connect() as conn, conn.transaction():
                if not conn.execute(
                    "SELECT pg_try_advisory_xact_lock(731904)"
                ).fetchone()[0]:
                    stop.wait(1)
                    continue
                reconcile(conn, control)
                from .monitoring import sample

                sample(conn)
            # Export only after the catalog transaction commits. Failure leaves
            # the previous file and heartbeat to become visibly stale.
            from .monitoring import publish

            with control.connect() as conn:
                publish(conn)
        except Exception as exc:
            control.log.error(
                "Store reconciliation failed error_type=%s", type(exc).__name__
            )
        stop.wait(2)
