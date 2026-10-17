"""Private lease-bound TCP relay. PostgreSQL startup is bound to the issued identity.

The SSH account may forward only to these lease ports. Provider authentication
still checks passwords; relay ports cannot be exchanged to extend another lease.
No protocol payload, username, credential or query is logged.
"""
import asyncio
import contextlib
import logging
import os
import struct
import time
from datetime import datetime, timezone
import psycopg
from . import catalog

log = logging.getLogger(__name__)
MAX_CONNECTIONS = 128


def connect():
    return psycopg.connect(host=os.environ["POSTGRES_HOST"], dbname="platform", user="platform_store_relay",
        password=os.environ["STORE_RELAY_PASSWORD"], autocommit=True, connect_timeout=2,
        options="-c statement_timeout=2000")


def snapshot():
    with connect() as conn:
        rows = conn.execute("""SELECT c.relay_port,c.credential_id,c.expires_at,r.resource_id,r.provider
            FROM store_credentials c JOIN store_grants g USING(grant_id) JOIN store_resources r USING(resource_id)
            JOIN projects p ON p.name=r.owner_project
            LEFT JOIN projects consumer ON consumer.name=g.consumer_project
            WHERE c.state IN ('active','retiring') AND c.expires_at>now() AND c.grant_version=g.version
            AND g.state='active' AND r.state='active' AND r.observed_state='active' AND p.status<>'retired'
            AND (consumer.name IS NULL OR consumer.status<>'retired')
            AND c.relay_port IS NOT NULL LIMIT 512""").fetchall()
    return {row[0]: {"credential_id": str(row[1]), "expires_at": row[2], "resource_id": str(row[3]), "provider": row[4]}
            for row in rows}


def initialize_identity(conn):
    from psycopg import sql
    password = os.environ.get("STORE_RELAY_PASSWORD", "")
    if len(password) < 32:
        raise RuntimeError("STORE_RELAY_PASSWORD must contain at least 32 characters")
    if not conn.execute("SELECT 1 FROM pg_roles WHERE rolname='platform_store_relay'").fetchone():
        conn.execute("CREATE ROLE platform_store_relay LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 4")
    conn.execute(sql.SQL("ALTER ROLE platform_store_relay PASSWORD {}").format(sql.Literal(password)))
    conn.execute("GRANT CONNECT ON DATABASE platform TO platform_store_relay")
    conn.execute("GRANT USAGE ON SCHEMA public TO platform_store_relay")
    conn.execute("GRANT SELECT ON store_credentials,store_grants,store_resources TO platform_store_relay")
    conn.execute("GRANT SELECT(name,status) ON projects TO platform_store_relay")


async def postgres_startup(reader, writer, lease):
    # SSH is the transport encryption boundary. Reject/decline PG TLS/GSS so
    # identity binding cannot be hidden inside an opaque encrypted stream.
    for _ in range(3):
        header = await reader.readexactly(8)
        size, protocol = struct.unpack("!II", header)
        if size == 8 and protocol in {80877103, 80877104}:
            writer.write(b"N")
            await writer.drain()
            continue
        if protocol != 196608 or not 8 < size <= 10000:
            raise ValueError("Unsupported startup")
        body = await reader.readexactly(size - 8)
        items = body.rstrip(b"\0").split(b"\0")
        if len(items) % 2:
            raise ValueError("Invalid startup")
        fields = {}
        for key, value in zip(items[::2], items[1::2]):
            if key in fields or key == b"options":
                raise ValueError("Invalid startup options")
            fields[key] = value
        if fields.get(b"user") != catalog.login(lease["credential_id"]).encode():
            raise ValueError("Lease identity mismatch")
        if fields.get(b"database") != catalog.identifier(lease["resource_id"]).encode():
            raise ValueError("Lease resource mismatch")
        return header + body
    raise ValueError("Invalid startup negotiation")


class Relay:
    def __init__(self, load=snapshot, backend=None, host="0.0.0.0"):
        self.load = load
        self.backend = backend or (lambda lease: (os.environ["POSTGRES_IP"], 5432))
        self.host = host
        self.leases = {}
        self.servers = {}
        self.connections = 0
        self.by_credential = {}
        self.last_success = 0.0

    def allowed(self, port, lease):
        current = self.leases.get(port)
        return (current is not None and current["credential_id"] == lease["credential_id"]
                and current["expires_at"] > datetime.now(timezone.utc)
                and time.monotonic() - self.last_success < 3)

    async def handle(self, port, reader, writer):
        lease = self.leases.get(port)
        if lease is None or self.connections >= MAX_CONNECTIONS or self.by_credential.get(lease["credential_id"], 0) >= 20 or not self.allowed(port, lease):
            writer.close()
            return
        self.connections += 1
        self.by_credential[lease["credential_id"]] = self.by_credential.get(lease["credential_id"], 0) + 1
        backend_writer = None
        tasks = []
        try:
            if lease["provider"] != "postgresql":
                raise ValueError("Unsupported relay provider")
            startup = await asyncio.wait_for(postgres_startup(reader, writer, lease), 5)
            backend_reader, backend_writer = await asyncio.wait_for(asyncio.open_connection(*self.backend(lease)), 3)
            backend_writer.write(startup)
            await backend_writer.drain()

            async def copy(source, target):
                while chunk := await source.read(65536):
                    target.write(chunk)
                    await target.drain()

            async def guard():
                while self.allowed(port, lease):
                    await asyncio.sleep(.25)

            tasks = [asyncio.create_task(copy(reader, backend_writer)), asyncio.create_task(copy(backend_reader, writer)),
                     asyncio.create_task(guard())]
            remaining = max(0, (lease["expires_at"] - datetime.now(timezone.utc)).total_seconds())
            await asyncio.wait_for(asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED), remaining)
        except (Exception, asyncio.CancelledError):
            # Fixed silence; errors/payloads must not escape to logs.
            pass
        finally:
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            for stream in (writer, backend_writer):
                if stream is not None:
                    stream.close()
                    with contextlib.suppress(Exception):
                        await stream.wait_closed()
            self.connections -= 1
            self.by_credential[lease["credential_id"]] -= 1
            if self.by_credential[lease["credential_id"]] == 0:
                del self.by_credential[lease["credential_id"]]

    async def refresh(self):
        try:
            leases = await asyncio.to_thread(self.load)
            self.last_success = time.monotonic()
        except Exception:
            leases = {}  # Catalog outage fails closed, including existing sessions.
        self.leases = leases
        for port in list(self.servers):
            if port not in leases:
                self.servers.pop(port).close()
        for port in leases:
            if not 20000 <= port <= 20511:
                raise ValueError("Invalid managed lease port")
            if port not in self.servers:
                self.servers[port] = await asyncio.start_server(
                    lambda reader, writer, selected=port: self.handle(selected, reader, writer), self.host, port)

    async def health(self, reader, writer):
        try:
            await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 2)
            ready = time.monotonic() - self.last_success < 3
            code = b"200 OK" if ready else b"503 Service Unavailable"
            writer.write(b"HTTP/1.1 " + code + b"\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
            await writer.drain()
        except Exception:
            pass
        finally:
            writer.close()

    async def run(self):
        health = await asyncio.start_server(self.health, "127.0.0.1", 19999)
        try:
            while True:
                await self.refresh()
                await asyncio.sleep(1)
        finally:
            self.leases = {}
            health.close()
            for server in self.servers.values():
                server.close()


if __name__ == "__main__":
    asyncio.run(Relay().run())
