"""Lease and graph boundaries for the HugeGraph browser console."""

import hashlib
import os
from datetime import UTC, datetime, timedelta
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

import httpx2 as httpx
from app.stores import catalog, console
from app.stores.hugegraph import basic
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.routing import Host


class Bytes(httpx.AsyncByteStream):
    def __init__(self, value):
        self.value = value

    async def __aiter__(self):
        yield self.value


class HugeGraphConsoleTests(TestCase):
    def setUp(self):
        environment = patch.dict(
            os.environ,
            {
                "DATABASE_KEY": "h" * 32,
                "APPS_DOMAIN": "apps.fixture.invalid",
                "PLATFORM_DOMAIN": "platform.fixture.invalid",
                "STORE_CONSOLE_HTTP_ENABLED": "true",
                "STORE_ENABLED_PROVIDERS": "hugegraph",
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
            "provider": "hugegraph",
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

    def test_assets_and_config_require_active_lease(self):
        self.assertEqual(self.client.get("/__platform/hugegraph/").status_code, 401)
        self.assertIn("/__platform/hugegraph/", self.launch().text)
        page = self.client.get("/__platform/hugegraph/")
        self.assertEqual(page.status_code, 200)
        self.assertIn("connect-src 'self'", page.headers["content-security-policy"])
        self.assertIn("Project graph", page.text)
        self.assertEqual(
            self.client.get("/__platform/hugegraph/config").json(),
            {
                "graph": catalog.identifier(self.row["resource_id"]),
                "mode": "read-only",
            },
        )
        self.assertEqual(
            self.client.get("/__platform/hugegraph/missing").status_code, 404
        )
        self.current = None
        self.assertEqual(self.client.get("/__platform/hugegraph/").status_code, 401)

    def test_scoped_relay_and_bounded_graph_pages(self):
        self.launch()
        requests = []

        async def handler(request):
            requests.append((str(request.url), dict(request.headers)))
            return httpx.Response(
                200,
                stream=Bytes(b'{"vertices": [], "page": null}'),
                headers={"content-type": "application/json"},
            )

        real_client = httpx.AsyncClient
        graph = catalog.identifier(self.row["resource_id"])
        foreign = catalog.identifier(uuid4())
        with patch(
            "app.stores.console.httpx.AsyncClient",
            side_effect=lambda **options: real_client(
                transport=httpx.MockTransport(handler), **options
            ),
        ):
            self.assertEqual(
                self.client.get(f"/graphs/{graph}/graph/vertices?limit=50").status_code,
                200,
            )
            for path in (
                f"/graphs/{foreign}/graph/vertices?limit=50",
                f"/graphs/{graph}/graph/vertices?limit=1000",
                f"/graphs/{graph}/graph/vertices",
                f"/graphs/{graph}/gremlin",
                "/graphs",
            ):
                self.assertEqual(self.client.get(path).status_code, 403)
            self.assertEqual(
                self.client.post(
                    f"/graphs/{graph}/graph/vertices",
                    json={"label": "person"},
                    headers={"Origin": console.origin(20000)},
                ).status_code,
                403,
            )
            self.assertEqual(
                self.client.get(
                    f"/graphs/{graph}/schema/propertykeys",
                    headers={"Authorization": "Basic attacker"},
                ).status_code,
                400,
            )
        self.assertEqual(len(requests), 1)
        url, headers = requests[0]
        self.assertEqual(
            url, f"http://127.0.0.1:20000/graphs/{graph}/graph/vertices?limit=50"
        )
        self.assertEqual(
            headers["authorization"],
            basic(
                catalog.login(self.row["credential_id"]),
                catalog.secret_for(self.row["credential_id"]),
            ),
        )
        self.assertNotIn("cookie", headers)

    def test_writer_can_create_and_delete_with_origin(self):
        self.row["mode"] = "read-write"
        self.launch()
        requests = []

        async def handler(request):
            requests.append((request.method, str(request.url)))
            return httpx.Response(
                200,
                stream=Bytes(b'{"id": "1"}'),
                headers={"content-type": "application/json"},
            )

        real_client = httpx.AsyncClient
        graph = catalog.identifier(self.row["resource_id"])
        with patch(
            "app.stores.console.httpx.AsyncClient",
            side_effect=lambda **options: real_client(
                transport=httpx.MockTransport(handler), **options
            ),
        ):
            self.assertEqual(
                self.client.post(
                    f"/graphs/{graph}/graph/vertices", json={"label": "person"}
                ).status_code,
                403,
            )
            self.assertEqual(
                self.client.post(
                    f"/graphs/{graph}/graph/vertices",
                    json={"label": "person"},
                    headers={"Origin": console.origin(20000)},
                ).status_code,
                200,
            )
            self.assertEqual(
                self.client.delete(
                    f"/graphs/{graph}/graph/vertices/1",
                    headers={"Origin": console.origin(20000)},
                ).status_code,
                200,
            )
        self.assertEqual([method for method, _ in requests], ["POST", "DELETE"])
