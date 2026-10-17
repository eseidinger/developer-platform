"""Actual local streams prove lease expiry and identity binding without real stores."""
import asyncio
import struct
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from unittest import IsolatedAsyncioTestCase, main
from app.stores import catalog
from app.stores.relay import Relay, postgres_startup


def startup(credential, resource, **extra):
    fields = {"user": catalog.login(credential), "database": catalog.identifier(resource), **extra}
    body = b"".join(k.encode() + b"\0" + v.encode() + b"\0" for k, v in fields.items()) + b"\0"
    return struct.pack("!II", len(body) + 8, 196608) + body


class RelayTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.credential, self.resource = uuid4(), uuid4()
        self.lease = {"credential_id": str(self.credential), "resource_id": str(self.resource),
            "provider": "postgresql", "expires_at": datetime.now(timezone.utc) + timedelta(seconds=5)}
        self.backend_connections = 0
        async def backend(reader, writer):
            self.backend_connections += 1
            try:
                while data := await reader.read(65536):
                    writer.write(data)
                    await writer.drain()
            finally:
                writer.close()
        self.backend = await asyncio.start_server(backend, "127.0.0.1", 0)
        self.relay = Relay(backend=lambda lease: ("127.0.0.1", self.backend.sockets[0].getsockname()[1]))
        self.relay.leases = {20000: self.lease}
        self.relay.last_success = time.monotonic()
        self.server = await asyncio.start_server(lambda r, w: self.relay.handle(20000, r, w), "127.0.0.1", 0)

    async def asyncTearDown(self):
        self.relay.leases = {}
        await asyncio.sleep(.3)
        for server in (self.server, self.backend):
            server.close()
            await server.wait_closed()

    async def connection(self, packet=None):
        reader, writer = await asyncio.open_connection("127.0.0.1", self.server.sockets[0].getsockname()[1])
        packet = packet or startup(self.credential, self.resource)
        writer.write(packet)
        await writer.drain()
        return reader, writer, packet

    async def test_deadline_ends_an_established_session_without_backend_admin_cleanup(self):
        self.lease["expires_at"] = datetime.now(timezone.utc) + timedelta(seconds=.6)
        reader, writer, packet = await self.connection()
        self.assertEqual(await asyncio.wait_for(reader.readexactly(len(packet)), 1), packet)
        writer.write(b"seed-private-query")
        self.assertEqual(await reader.readexactly(18), b"seed-private-query")
        self.assertEqual(await asyncio.wait_for(reader.read(), 1.5), b"")
        writer.close(); await writer.wait_closed()

    async def test_other_credential_cannot_borrow_a_longer_lived_port(self):
        reader, writer, packet = await self.connection(startup(uuid4(), self.resource))
        self.assertEqual(await asyncio.wait_for(reader.read(), 1), b"")
        self.assertEqual(self.backend_connections, 0)
        writer.close(); await writer.wait_closed()

    async def test_foreign_database_never_reaches_backend(self):
        reader, writer, packet = await self.connection(startup(self.credential, uuid4()))
        self.assertEqual(await asyncio.wait_for(reader.read(), 1), b"")
        self.assertEqual(self.backend_connections, 0)
        writer.close(); await writer.wait_closed()

    async def test_revocation_closes_existing_stream(self):
        reader, writer, packet = await self.connection()
        await reader.readexactly(len(packet))
        self.relay.leases.clear()
        self.assertEqual(await asyncio.wait_for(reader.read(), 1), b"")
        writer.close(); await writer.wait_closed()

    async def test_catalog_outage_fails_closed_for_existing_stream(self):
        reader, writer, packet = await self.connection()
        await reader.readexactly(len(packet))
        def unavailable():
            raise RuntimeError("seed-private-database-error")
        self.relay.load = unavailable
        await self.relay.refresh()
        self.assertEqual(await asyncio.wait_for(reader.read(), 1), b"")
        writer.close(); await writer.wait_closed()

    async def test_native_ssl_negotiation_declined_before_identity_check(self):
        reader, writer, packet = await self.connection(struct.pack("!II", 8, 80877103))
        self.assertEqual(await reader.readexactly(1), b"N")
        packet = startup(self.credential, self.resource)
        writer.write(packet); await writer.drain()
        self.assertEqual(await reader.readexactly(len(packet)), packet)
        writer.close(); await writer.wait_closed()


if __name__ == "__main__":
    main()
