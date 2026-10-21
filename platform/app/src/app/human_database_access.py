"""Project-scoped human PostgreSQL identities and SSH key authorization."""

import base64
import binascii
import hashlib
import re
import secrets

from psycopg import sql

KEY_PATTERN = re.compile(r"^ssh-ed25519 ([A-Za-z0-9+/]+={0,2})$")
FINGERPRINT_PATTERN = re.compile(r"^SHA256:[A-Za-z0-9+/]{43}$")


def role_name(project: str, issuer: str, subject: str) -> str:
    digest = hashlib.sha256(f"{project}\0{issuer}\0{subject}".encode()).hexdigest()[:32]
    return f"human_{digest}"


def parse_public_key(value: str) -> tuple[str, str]:
    match = KEY_PATTERN.fullmatch(value.strip())
    if not match:
        raise ValueError("Only an ssh-ed25519 public key without options is supported")
    try:
        blob = base64.b64decode(match.group(1), validate=True)
    except binascii.Error:
        raise ValueError("Invalid SSH public key") from None
    if (
        len(blob) != 51
        or blob[:15] != b"\x00\x00\x00\x0bssh-ed25519"
        or blob[15:19] != b"\x00\x00\x00 "
    ):
        raise ValueError("Invalid SSH public key")
    fingerprint = base64.b64encode(hashlib.sha256(blob).digest()).decode().rstrip("=")
    return f"ssh-ed25519 {match.group(1)}", f"SHA256:{fingerprint}"


def initialize(conn) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS human_database_access (
        project TEXT NOT NULL REFERENCES projects(name),
        issuer TEXT NOT NULL,
        subject TEXT NOT NULL,
        role_name TEXT NOT NULL UNIQUE,
        public_key TEXT NOT NULL,
        fingerprint TEXT NOT NULL,
        active BOOLEAN NOT NULL DEFAULT true,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        PRIMARY KEY(project, issuer, subject)
    )""")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS human_database_access_fingerprint_idx "
        "ON human_database_access(fingerprint) WHERE active"
    )
    conn.execute("REVOKE ALL ON TABLE human_database_access FROM PUBLIC")


def new_password() -> str:
    return secrets.token_urlsafe(48)


def prepare_role(conn, role: str, password: str) -> None:
    exists = conn.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,)).fetchone()
    if exists:
        conn.execute(
            sql.SQL("ALTER ROLE {} LOGIN PASSWORD {}").format(
                sql.Identifier(role), sql.Literal(password)
            )
        )
    else:
        conn.execute(
            sql.SQL(
                "CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION"
            ).format(sql.Identifier(role), sql.Literal(password))
        )


def grant_read_only(conn, database: str, owner: str, role: str) -> None:
    """Run on the project database, after prepare_role on the catalog connection."""
    # On older PostgreSQL databases PUBLIC could create in the public schema.
    # The project owner retains its implicit owner rights.
    conn.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
    conn.execute(
        sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
            sql.Identifier(database), sql.Identifier(role)
        )
    )
    conn.execute(
        sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(role))
    )
    conn.execute(
        sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA public TO {}").format(
            sql.Identifier(role)
        )
    )
    conn.execute(
        sql.SQL(
            "ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA public GRANT SELECT ON TABLES TO {}"
        ).format(sql.Identifier(owner), sql.Identifier(role))
    )


def deny_role(conn, role: str) -> None:
    conn.execute(
        sql.SQL("ALTER ROLE {} NOLOGIN PASSWORD NULL").format(sql.Identifier(role))
    )
    conn.execute(
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
        "WHERE usename=%s AND pid <> pg_backend_pid()",
        (role,),
    )


def authorized_key(
    conn, fingerprint: str, destination: str
) -> tuple[str, str, str, str] | None:
    if not FINGERPRINT_PATTERN.fullmatch(fingerprint):
        return None
    row = conn.execute(
        """SELECT public_key, project, issuer, subject FROM human_database_access
        WHERE fingerprint=%s AND active ORDER BY project LIMIT 1""",
        (fingerprint,),
    ).fetchone()
    if row is None:
        return None
    # The host sshd also restricts forwarding. This option binds the key itself.
    return (
        f'restrict,port-forwarding,permitopen="{destination}" {row[0]}',
        row[1],
        row[2],
        row[3],
    )
