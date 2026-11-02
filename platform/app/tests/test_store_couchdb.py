import asyncio
import base64
import json
import os
import time
from datetime import UTC, datetime, timedelta
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import Mock, patch
from uuid import uuid4

from app.stores import catalog
from app.stores.couchdb import CouchDB, database
from app.stores.couchdb_access import authorize, validate_index
from app.stores.relay import Relay
from app.stores.s3 import StoreError


class CouchDBAccessTests(TestCase):
    def setUp(self):
        self.lease = {
            "resource_id": str(uuid4()),
            "mode": "read-only",
        }
        self.prefix = "/" + catalog.identifier(self.lease["resource_id"])

    def allowed(self, method, suffix):
        return authorize(method.encode(), (self.prefix + suffix).encode(), self.lease)

    def test_reader_can_query_but_cannot_write_or_reach_system_apis(self):
        for method, suffix in [
            ("GET", ""),
            ("GET", "/document"),
            ("POST", "/_find"),
            ("POST", "/_all_docs"),
            ("GET", "/_changes"),
            ("GET", "/_design/report/_view/by_date"),
        ]:
            with self.subTest(method=method, suffix=suffix):
                self.allowed(method, suffix)
        for method, suffix in [
            ("PUT", "/document"),
            ("POST", ""),
            ("POST", "/_bulk_docs"),
            ("POST", "/_index"),
            ("GET", "/_security"),
            ("GET", "/../_users"),
            ("GET", "/%5fsecurity"),
            ("GET", "/%2e%2e/_users"),
            ("GET", "/file%2Fother"),
            ("GET", "/file%25name"),
            ("GET", "/file//other"),
        ]:
            with (
                self.subTest(method=method, suffix=suffix),
                self.assertRaises(ValueError),
            ):
                self.allowed(method, suffix)
        with self.assertRaises(ValueError):
            authorize(b"GET", b"/_users", self.lease)

    def test_writer_index_operations_are_narrow_and_validated(self):
        self.lease["mode"] = "read-write"
        self.assertTrue(self.allowed("POST", "/_index"))
        self.assertTrue(self.allowed("DELETE", "/_index/profiles/json/by_name"))
        self.assertTrue(
            self.allowed("DELETE", "/_index/_design/generated/json/by_name")
        )
        for suffix in [
            "/_index?admin=true",
            "/_index/_bulk_delete",
            "/_index/../json/name",
            "/_security",
            "/_design/security",
        ]:
            with self.subTest(suffix=suffix), self.assertRaises(ValueError):
                self.allowed("POST", suffix)
        validate_index(
            json.dumps(
                {
                    "index": {"fields": ["profile.name"]},
                    "name": "by_name",
                    "type": "json",
                }
            ).encode()
        )
        for body in [
            b'{"index":{"fields":["name"]},"type":"text","name":"x"}',
            b'{"index":{"fields":["name"]},"type":"json","name":"x","ddoc":"_auth"}',
            b'{"index":{"fields":[]},"type":"json","name":"x"}',
            b'{"index":{"fields":["name"]},"type":"json","name":"x","name":"y"}',
            b'{"index":{"fields":["name"]},"type":"json","name":42}',
        ]:
            with self.subTest(body=body), self.assertRaises(ValueError):
                validate_index(body)


class CouchDBProviderTests(TestCase):
    def test_provision_issues_and_revokes_only_scoped_member(self):
        resource = {"resource_id": str(uuid4())}
        credential = {"credential_id": str(uuid4()), "mode": "read-only"}
        native = Mock()
        native.request.side_effect = [
            None,
            {},
            {"admins": {"names": [], "roles": ["_admin"]}, "members": {"names": []}},
            {},
        ]
        with (
            patch("app.stores.couchdb.PrivateJSON", return_value=native),
            patch.dict(os.environ, {"DATABASE_KEY": "k" * 32}),
        ):
            provider = CouchDB(endpoint="http://127.0.0.1:5984", password="s" * 32)
            provider.provision(resource)
            connection = provider.credentials(resource, credential)
        name = database(resource)
        native.request.assert_any_call(
            "PUT",
            "/" + name + "/_security",
            {
                "admins": {"names": [], "roles": []},
                "members": {"names": ["platform_reserved"], "roles": []},
            },
        )
        self.assertEqual(provider.quota_enforcement, "advisory")
        self.assertEqual(connection["COUCHDB_DATABASE"], name)

    def test_recovery_requires_managed_membership_without_extra_roles(self):
        resource = {"resource_id": str(uuid4())}
        native = Mock()
        native.request.side_effect = [
            {},
            {
                "admins": {"names": [], "roles": []},
                "members": {"names": ["platform_reserved"], "roles": ["outsider"]},
            },
        ]
        with patch("app.stores.couchdb.PrivateJSON", return_value=native):
            provider = CouchDB(endpoint="http://127.0.0.1:5984", password="s" * 32)
            with self.assertRaises(StoreError):
                provider.validate_recovery(resource)


class CouchDBRelayTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.lease = {
            "credential_id": str(uuid4()),
            "resource_id": str(uuid4()),
            "provider": "couchdb",
            "kind": "human",
            "mode": "read-write",
            "expires_at": datetime.now(UTC) + timedelta(seconds=10),
        }
        import hashlib

        self.password = "synthetic-secret"
        self.lease["admission_sha256"] = hashlib.sha256(
            self.password.encode()
        ).hexdigest()
        self.requests = []
        self.bodies = []

        async def backend(reader, writer):
            try:
                request = await reader.readuntil(b"\r\n\r\n")
                self.requests.append(request)
                length = int(
                    next(
                        line.split(b":", 1)[1].strip()
                        for line in request.split(b"\r\n")
                        if line.lower().startswith(b"content-length:")
                    )
                )
                self.bodies.append(await reader.readexactly(length))
                writer.write(
                    b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n"
                    b"Set-Cookie: admin=secret\r\nLocation: /_users\r\n\r\n{}"
                )
                await writer.drain()
            finally:
                writer.close()

        self.backend = await asyncio.start_server(backend, "127.0.0.1", 0)
        self.relay = Relay(
            backend=lambda lease: (
                "127.0.0.1",
                self.backend.sockets[0].getsockname()[1],
            )
        )
        self.relay.leases = {20000: self.lease}
        self.relay.last_success = time.monotonic()
        self.server = await asyncio.start_server(
            lambda reader, writer: self.relay.handle(20000, reader, writer),
            "127.0.0.1",
            0,
        )
        self.env = patch.dict(os.environ, {"COUCHDB_ADMIN_PASSWORD": "a" * 32})
        self.env.start()

    async def asyncTearDown(self):
        self.relay.leases.clear()
        self.env.stop()
        for server in (self.server, self.backend):
            server.close()
            await server.wait_closed()

    async def send(self, method, suffix, password=None, body=b""):
        prefix = "/" + catalog.identifier(self.lease["resource_id"])
        authorization = base64.b64encode(
            (
                catalog.login(self.lease["credential_id"])
                + ":"
                + (password or self.password)
            ).encode()
        )
        reader, writer = await asyncio.open_connection(
            "127.0.0.1", self.server.sockets[0].getsockname()[1]
        )
        writer.write(
            method.encode()
            + b" "
            + (prefix + suffix).encode()
            + b" HTTP/1.1\r\nHost: fixture\r\nAuthorization: Basic "
            + authorization
            + b"\r\nContent-Length: "
            + str(len(body)).encode()
            + b"\r\n\r\n"
            + body
        )
        await writer.drain()
        response = await asyncio.wait_for(reader.read(), 2)
        writer.close()
        await writer.wait_closed()
        return response

    async def test_reader_write_and_foreign_database_do_not_reach_backend(self):
        self.lease["mode"] = "read-only"
        self.assertEqual(await self.send("PUT", "/doc"), b"")
        self.assertEqual(await self.send("GET", "/_security"), b"")
        self.assertEqual(await self.send("GET", "/doc", "wrong-secret"), b"")
        self.assertEqual(self.requests, [])
        self.assertIn(b"200", await self.send("GET", "/doc"))
        self.assertEqual(len(self.requests), 1)

    async def test_writer_index_uses_admin_only_for_validated_request(self):
        body = json.dumps(
            {"index": {"fields": ["profile.name"]}, "name": "by_name", "type": "json"}
        ).encode()
        self.assertEqual(await self.send("POST", "/_index", body=b"{}"), b"")
        self.assertEqual(self.requests, [])

        response = await self.send("POST", "/_index", body=body)
        self.assertIn(b"200", response)
        self.assertNotIn(b"set-cookie", response.lower())
        self.assertNotIn(b"location", response.lower())
        admin = base64.b64encode(("platform_admin:" + "a" * 32).encode())
        self.assertIn(b"authorization: Basic " + admin, self.requests[0])
        self.assertIn(b"content-type: application/json", self.requests[0])
        self.assertNotIn(b"host: fixture", self.requests[0].lower())
        self.assertEqual(self.bodies[0], body)

        await self.send("GET", "/doc")
        native = base64.b64encode(
            (catalog.login(self.lease["credential_id"]) + ":" + self.password).encode()
        )
        self.assertIn(b"authorization: Basic " + native, self.requests[1])
