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
