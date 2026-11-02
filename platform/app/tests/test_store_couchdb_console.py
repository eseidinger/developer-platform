"""Project-scoped CouchDB browser access through the shared console gateway."""

import hashlib
import os
from datetime import UTC, datetime, timedelta
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

import httpx2 as httpx
from app.stores import catalog, console
from app.stores.couchdb import basic
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.routing import Host


class Bytes(httpx.AsyncByteStream):
    def __init__(self, value):
        self.value = value

    async def __aiter__(self):
        yield self.value


class CouchDBConsoleTests(TestCase):
    def setUp(self):
        environment = patch.dict(
            os.environ,
            {
                "DATABASE_KEY": "c" * 32,
                "APPS_DOMAIN": "apps.fixture.invalid",
                "PLATFORM_DOMAIN": "platform.fixture.invalid",
                "STORE_CONSOLE_HTTP_ENABLED": "true",
                "STORE_ENABLED_PROVIDERS": "couchdb",
                "STORE_RELAY_IP": "127.0.0.1",
            },
        )
        environment.start()
        self.addCleanup(environment.stop)
        credential_id = uuid4()
        self.row = {
            "credential_id": credential_id,
            "relay_port": 20000,
            "expires_at": datetime.now(UTC) + timedelta(hours=1),
            "issuer": "https://identity.fixture.invalid",
            "subject": "human",
            "provider": "couchdb",
            "resource_id": uuid4(),
            "created_at": datetime.now(UTC),
            "mode": "read-only",
            "admission_sha256": hashlib.sha256(
                catalog.secret_for(credential_id).encode()
            ).hexdigest(),
        }
        self.current = self.row
        app = FastAPI()
        app.router.routes.append(
            Host(
                "console-{port:int}.apps.fixture.invalid",
                app=console.create_gateway(
                    lambda credential: (
                        self.current if credential == credential_id else None
                    )
                ),
            )
        )
        self.client = TestClient(app, base_url=console.origin(20000))
        self.addCleanup(self.client.close)

    def launch(self):
        return self.client.post(
            "/__platform/start",
            data={"launch": console.assertion(self.row, "launch", 30)},
            headers={"Origin": "https://platform.fixture.invalid"},
        )

    def test_assets_and_config_require_a_live_human_lease(self):
        self.assertEqual(self.client.get("/__platform/couchdb/").status_code, 401)
        response = self.launch()
        self.assertEqual(response.status_code, 200)
        self.assertIn("/__platform/couchdb/", response.text)
        page = self.client.get("/__platform/couchdb/")
        self.assertEqual(page.status_code, 200)
        self.assertIn("connect-src 'self'", page.headers["content-security-policy"])
        self.assertIn("Project database", page.text)
        self.assertEqual(
            self.client.get("/__platform/couchdb/config").json(),
            {
                "database": catalog.identifier(self.row["resource_id"]),
                "mode": "read-only",
            },
        )
        self.assertEqual(
            self.client.post(
                "/__platform/couchdb/config", headers={"Origin": console.origin(20000)}
            ).status_code,
            405,
        )
        self.assertEqual(
            self.client.get("/__platform/couchdb/unknown").status_code, 404
        )
        self.current = None
        self.assertEqual(self.client.get("/__platform/couchdb/").status_code, 401)

    def test_scoped_requests_use_native_credential_only_inside_private_relay(self):
        self.launch()
        requests = []

        async def handler(request):
            requests.append((str(request.url), dict(request.headers)))
            return httpx.Response(
                200,
                stream=Bytes(b'{"rows": []}'),
                headers={"content-type": "application/json"},
            )

        real_client = httpx.AsyncClient
        database = catalog.identifier(self.row["resource_id"])
        other = catalog.identifier(uuid4())
        with patch(
            "app.stores.console.httpx.AsyncClient",
            side_effect=lambda **options: real_client(
                transport=httpx.MockTransport(handler), **options
            ),
        ):
            response = self.client.get(
                f"/{database}/_all_docs",
                headers={"X-Forwarded-Host": "attacker.invalid"},
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {"rows": []})
            self.assertEqual(self.client.get(f"/{other}/_all_docs").status_code, 403)
            self.assertEqual(self.client.get("/_all_dbs").status_code, 403)
            self.assertEqual(
                self.client.put(
                    f"/{database}/item",
                    json={"value": 1},
                    headers={"Origin": console.origin(20000)},
                ).status_code,
                403,
            )
            self.assertEqual(
                self.client.get(
                    f"/{database}/_all_docs",
                    headers={"Authorization": "Basic attacker"},
                ).status_code,
                400,
            )
        self.assertEqual(len(requests), 1)
        url, headers = requests[0]
        self.assertEqual(url, f"http://127.0.0.1:20000/{database}/_all_docs")
        self.assertEqual(
            headers["authorization"],
            basic(
                catalog.login(self.row["credential_id"]),
                catalog.secret_for(self.row["credential_id"]),
            ),
        )
        self.assertNotIn("cookie", headers)
        self.assertNotIn("x-forwarded-host", headers)

    def test_writer_can_send_document_and_index_requests(self):
        self.row["mode"] = "read-write"
        self.launch()
        requests = []

        async def handler(request):
            requests.append((request.method, str(request.url), await request.aread()))
            return httpx.Response(
                201,
                stream=Bytes(b'{"ok": true}'),
                headers={"content-type": "application/json"},
            )

        real_client = httpx.AsyncClient
        database = catalog.identifier(self.row["resource_id"])
        with patch(
            "app.stores.console.httpx.AsyncClient",
            side_effect=lambda **options: real_client(
                transport=httpx.MockTransport(handler), **options
            ),
        ):
            for path, body in (
                (f"/{database}/item", {"_id": "item", "value": 1}),
                (
                    f"/{database}/_index",
                    {
                        "index": {"fields": ["value"]},
                        "name": "by_value",
                        "type": "json",
                    },
                ),
            ):
                method = "POST" if path.endswith("/_index") else "PUT"
                response = self.client.request(
                    method,
                    path,
                    json=body,
                    headers={"Origin": console.origin(20000)},
                )
                self.assertEqual(response.status_code, 201)
        self.assertEqual([request[0] for request in requests], ["PUT", "POST"])
