import asyncio
import base64
import json
import time
from datetime import UTC, datetime, timedelta
from unittest import IsolatedAsyncioTestCase
from uuid import UUID, uuid4

import h11
from app.stores import catalog
from app.stores.http_relay import access_key, identity
from app.stores.relay import Relay


class HTTPRelayTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.lease = {
            "credential_id": str(uuid4()),
            "resource_id": str(uuid4()),
            "provider": "opensearch",
            "expires_at": datetime.now(UTC) + timedelta(seconds=10),
        }
        self.observed = []

        async def backend(reader, writer):
            try:
                header = await reader.readuntil(b"\r\n\r\n")
                self.observed.append(header)
                writer.write(
                    b"HTTP/1.1 200 OK\r\nContent-Length: 65536\r\n\r\n" + b"x" * 1024
                )
                await writer.drain()
                await asyncio.sleep(5)
            finally:
                writer.close()

        self.backend = await asyncio.start_server(backend, "127.0.0.1", 0)
        self.relay = Relay(
            backend=lambda lease: (
                "127.0.0.1",
                self.backend.sockets[0].getsockname()[1],
            )
        )
        # Plain fixture backend: production OpenSearch uses a verified private CA.
        self.patch = __import__("unittest.mock", fromlist=["patch"]).patch(
            "app.stores.relay.http_tls", return_value=None
        )
        self.patch.start()
        self.relay.leases = {20000: self.lease}
        self.relay.last_success = time.monotonic()
        self.server = await asyncio.start_server(
            lambda r, w: self.relay.handle(20000, r, w), "127.0.0.1", 0
        )

    async def asyncTearDown(self):
        self.relay.leases.clear()
        await asyncio.sleep(0.3)
        self.patch.stop()
        for server in (self.server, self.backend):
            server.close()
            await server.wait_closed()

    def packet(self, credential=None):
        login = catalog.login(credential or self.lease["credential_id"])
        value = base64.b64encode((login + ":synthetic-password").encode())
        return (
            b"GET /resource/_search HTTP/1.1\r\nHost: fixture\r\nAuthorization: Basic "
            + value
            + b"\r\n\r\n"
        )

    async def client(self, packet):
        reader, writer = await asyncio.open_connection(
            "127.0.0.1", self.server.sockets[0].getsockname()[1]
        )
        writer.write(packet)
        await writer.drain()
        self.addCleanup(writer.close)
        return reader, writer

    async def test_foreign_identity_never_reaches_the_native_backend(self):
        reader, _ = await self.client(self.packet(uuid4()))
        self.assertEqual(await asyncio.wait_for(reader.read(), 1), b"")
        self.assertEqual(self.observed, [])

    async def test_expiry_cuts_off_an_in_progress_response_without_worker_cleanup(self):
        self.lease["expires_at"] = datetime.now(UTC) + timedelta(seconds=0.6)
        reader, _ = await self.client(self.packet())
        data = await asyncio.wait_for(reader.read(), 1.5)
        self.assertIn(b"HTTP/1.1 200", data)
        self.assertEqual(data.count(b"x"), 1024)
        self.assertIn(b"connection: close", data.lower())

    async def test_catalog_failure_cuts_off_the_response(self):
        reader, _ = await self.client(self.packet())
        await reader.readuntil(b"\r\n\r\n")
        self.relay.last_success = 0
        self.assertLess(len(await asyncio.wait_for(reader.read(), 1)), 65536)

    async def test_signed_s3_request_and_presign_are_bound_to_the_same_lease(self):
        self.lease["provider"] = "s3"
        key = access_key(self.lease["credential_id"])
        auth = (
            f"AWS4-HMAC-SHA256 Credential={key}/20261017/us-east-1/s3/aws4_request, SignedHeaders=host;x-amz-date, Signature="
            + "a" * 64
        )
        request = h11.Request(
            method="GET",
            target="/bucket/key",
            headers=[("host", "fixture"), ("authorization", auth)],
        )
        identity(request, self.lease)
        presign = h11.Request(
            method="GET",
            target="/bucket/key?X-Amz-Credential=" + key + "%2Fscope",
            headers=[("host", "fixture")],
        )
        identity(presign, self.lease)
        self.lease["credential_id"] = str(uuid4())
        with self.assertRaises(ValueError):
            identity(request, self.lease)
        with self.assertRaises(ValueError):
            identity(presign, self.lease)

    async def test_qdrant_requires_signed_payload_identity_before_forwarding(self):
        self.lease["provider"] = "qdrant"
        payload = (
            base64.urlsafe_b64encode(
                json.dumps({"jti": self.lease["credential_id"]}).encode()
            )
            .decode()
            .rstrip("=")
        )
        # Signature verification belongs to Qdrant; the relay cannot mint a token.
        request = h11.Request(
            method="GET",
            target="/collections",
            headers=[
                ("host", "fixture"),
                ("api-key", "header." + payload + ".signature"),
            ],
        )
        identity(request, self.lease)
        self.lease["credential_id"] = UUID(self.lease["credential_id"])
        identity(request, self.lease)
        self.lease["credential_id"] = str(uuid4())
        with self.assertRaises(ValueError):
            identity(request, self.lease)

    async def test_http_upgrade_and_repeated_authorization_never_reach_backend(self):
        for packet in (
            self.packet().replace(b"\r\n\r\n", b"\r\nUpgrade: websocket\r\n\r\n"),
            self.packet().replace(
                b"\r\n\r\n", b"\r\nAuthorization: Basic duplicate\r\n\r\n"
            ),
        ):
            reader, _ = await self.client(packet)
            self.assertEqual(await asyncio.wait_for(reader.read(), 1), b"")
        self.assertEqual(self.observed, [])

    async def test_registered_child_session_revocation_closes_an_existing_stream_without_revoking_its_parent(
        self,
    ):
        import hashlib

        token, child = "synthetic-native-session-token", "A" * 20
        self.lease.update(
            {
                "provider": "s3",
                "kind": "human",
                "s3_sessions": {
                    child: {
                        "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
                        "expires_at": datetime.now(UTC) + timedelta(seconds=5),
                    }
                },
            }
        )
        auth = (
            f"AWS4-HMAC-SHA256 Credential={child}/20261017/us-east-1/s3/aws4_request, SignedHeaders=host;x-amz-security-token, Signature="
            + "a" * 64
        )
        reader, _ = await self.client(
            (
                "GET /bucket/file HTTP/1.1\r\nHost: fixture\r\nAuthorization: "
                + auth
                + "\r\nX-Amz-Security-Token: "
                + token
                + "\r\n\r\n"
            ).encode()
        )
        await reader.readuntil(b"\r\n\r\n")
        self.lease["s3_sessions"].clear()
        self.assertLess(len(await asyncio.wait_for(reader.read(), 1)), 65536)
        self.assertTrue(self.relay.allowed(20000, self.lease))

    async def test_private_session_acknowledgment_requires_the_exact_current_key_hash_and_fresh_catalog(
        self,
    ):
        import hashlib

        child, digest = "A" * 20, hashlib.sha256(b"synthetic-token").hexdigest()
        self.lease["s3_sessions"] = {}
        health = await asyncio.start_server(self.relay.health, "127.0.0.1", 0)
        self.addAsyncCleanup(health.wait_closed)
        self.addCleanup(health.close)

        async def status():
            reader, writer = await asyncio.open_connection(
                "127.0.0.1", health.sockets[0].getsockname()[1]
            )
            writer.write(
                f"GET /session/20000/{child}/{digest} HTTP/1.1\r\nHost: private-relay\r\n\r\n".encode()
            )
            await writer.drain()
            result = await reader.read()
            writer.close()
            await writer.wait_closed()
            return result.split(b"\r\n", 1)[0]

        self.assertIn(b"503", await status())
        self.lease["s3_sessions"][child] = {
            "token_sha256": digest,
            "expires_at": datetime.now(UTC) + timedelta(seconds=5),
        }
        self.assertIn(b"200", await status())
        self.lease["s3_sessions"][child]["token_sha256"] = "0" * 64
        self.assertIn(b"503", await status())
        self.lease["s3_sessions"][child]["token_sha256"] = digest
        self.relay.last_success = 0
        self.assertIn(b"503", await status())
