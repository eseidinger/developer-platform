import base64
import os
from datetime import UTC, datetime, timedelta
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

import httpx2 as httpx
from app.stores import catalog, dashboards
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request


class DashboardsBridgeTests(TestCase):
    def setUp(self):
        self.environ = patch.dict(
            os.environ,
            {
                "OPENSEARCH_DASHBOARDS_IP": "172.30.80.31",
                "OPENSEARCH_IP": "172.30.80.17",
                "OPENSEARCH_CA_FILE": "/public/ca.pem",
                "STORE_RELAY_IP": "172.30.80.15",
                "OPENSEARCH_DASHBOARDS_PASSWORD": "s" * 32,
            },
        )
        self.environ.start()
        self.addCleanup(self.environ.stop)
        self.cid = uuid4()
        self.row = {
            "credential_id": str(self.cid),
            "resource_id": str(uuid4()),
            "provider": "opensearch",
            "kind": "human",
            "relay_port": 20000,
            "expires_at": datetime.now(UTC) + timedelta(hours=24),
        }

    def request(self, user=None, selected=True, source="172.30.80.31", extra=()):
        auth = (
            "Basic "
            + base64.b64encode(
                ((user or catalog.login(self.cid)) + ":native-password").encode()
            ).decode()
        )
        headers = [
            (b"host", dashboards.HOST.encode()),
            (b"authorization", auth.encode()),
            *extra,
        ]
        if selected:
            headers.append((dashboards.HEADER.encode(), str(self.cid).encode()))
        return Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/_search",
                "raw_path": b"/_search",
                "query_string": b"",
                "headers": headers,
                "client": (source, 12345),
            }
        )

    def test_matching_human_uses_only_its_native_lease_and_never_an_operator_key(self):
        target, verify, row = dashboards.native_target(
            self.request(), lambda cid: self.row if cid == self.cid else None
        )
        self.assertEqual(target, "http://172.30.80.15:20000")
        self.assertTrue(verify)
        self.assertEqual(row, self.row)

    def test_foreign_login_cannot_borrow_the_launched_human_lease(self):
        with self.assertRaises(HTTPException) as denied:
            dashboards.native_target(
                self.request(user=catalog.login(uuid4())), lambda cid: self.row
            )
        self.assertEqual(denied.exception.status_code, 403)

    def test_expired_revoked_nonhuman_wrong_provider_and_invalid_port_are_denied(self):
        for row in (
            None,
            {**self.row, "kind": "application"},
            {**self.row, "provider": "s3"},
            {**self.row, "relay_port": 9200},
            {**self.row, "expires_at": datetime.now(UTC) - timedelta(seconds=1)},
        ):
            with self.assertRaises(HTTPException):
                dashboards.native_target(self.request(), lambda cid, row=row: row)

    def test_only_fixed_console_service_can_call_bridge_and_forwarded_source_is_ignored(
        self,
    ):
        for source in ("172.30.80.20", "127.0.0.1"):
            request = self.request(
                source=source, extra=((b"x-forwarded-for", b"172.30.80.31"),)
            )
            with self.assertRaises(HTTPException):
                dashboards.native_target(request, lambda cid: self.row)

    def test_server_identity_has_no_human_header_and_retains_verified_native_tls(self):
        target, verify, row = dashboards.native_target(
            self.request(user="kibanaserver", selected=False), lambda cid: None
        )
        self.assertEqual(
            (target, verify, row), ("https://172.30.80.17:9200", "/public/ca.pem", None)
        )
        for request in (
            self.request(user="admin", selected=False),
            self.request(user="kibanaserver"),
            self.request(selected=False),
        ):
            with self.assertRaises(HTTPException):
                dashboards.native_target(request, lambda cid: self.row)

    def test_duplicate_authentication_and_upgrade_are_denied(self):
        for extra in (
            ((b"authorization", b"Basic invalid"),),
            ((b"upgrade", b"websocket"),),
        ):
            with self.assertRaises(HTTPException):
                dashboards.native_target(
                    self.request(extra=extra), lambda cid: self.row
                )

    def test_login_page_server_metadata_read_still_requires_its_active_human_lease(
        self,
    ):
        request = self.request(user="kibanaserver")
        request.scope.update(
            path="/_plugins/_security/dashboardsinfo",
            raw_path=b"/_plugins/_security/dashboardsinfo",
        )
        self.assertEqual(
            dashboards.native_target(request, lambda cid: self.row)[0],
            "https://172.30.80.17:9200",
        )
        with self.assertRaises(HTTPException):
            dashboards.native_target(request, lambda cid: None)
        request.scope["method"] = "POST"
        with self.assertRaises(HTTPException):
            dashboards.native_target(request, lambda cid: self.row)

    def test_anonymous_native_login_settings_are_preserved_only_for_a_launched_lease(
        self,
    ):
        request = self.request()
        request.scope.update(
            path="/_plugins/_security/dashboardsinfo",
            raw_path=b"/_plugins/_security/dashboardsinfo",
        )
        request.scope["headers"] = [
            (key, value)
            for key, value in request.scope["headers"]
            if key != b"authorization"
        ]
        self.assertEqual(
            dashboards.native_target(request, lambda cid: self.row)[0],
            "https://172.30.80.17:9200",
        )
        with self.assertRaises(HTTPException):
            dashboards.native_target(request, lambda cid: None)
        request.scope["raw_path"] = b"/_search"
        with self.assertRaises(HTTPException):
            dashboards.native_target(request, lambda cid: self.row)

    def test_only_prelogin_settings_use_restricted_server_key_and_data_keeps_human_auth(
        self,
    ):
        from app.stores.opensearch import authorization, tenant

        seen = []

        class Bytes(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield b"{}"

        async def handler(request):
            seen.append(
                (
                    str(request.url),
                    request.headers.get("authorization"),
                    request.headers.get("securitytenant"),
                )
            )
            return httpx.Response(200, stream=Bytes())

        real_client = httpx.AsyncClient

        def transport(**kwargs):
            kwargs.pop("verify")  # Mock transport performs no TLS or socket I/O.
            return real_client(transport=httpx.MockTransport(handler), **kwargs)

        app = dashboards.create_backend(lambda cid: self.row)
        with (
            TestClient(
                app,
                base_url="http://" + dashboards.HOST,
                client=("172.30.80.31", 12345),
            ) as client,
            patch("app.stores.dashboards.httpx.AsyncClient", side_effect=transport),
        ):
            header = {dashboards.HEADER: str(self.cid)}
            self.assertEqual(
                client.get(
                    "/_plugins/_security/dashboardsinfo", headers=header
                ).status_code,
                200,
            )
            self.assertEqual(client.get("/_search", headers=header).status_code, 403)
            self.assertEqual(
                client.get("/_plugins/_security/dashboardsinfo").status_code, 403
            )
            human = authorization(catalog.login(self.cid), "own-secret")
            self.assertEqual(
                client.get(
                    "/_search",
                    headers={
                        **header,
                        "Authorization": human,
                        "securitytenant": "foreign",
                    },
                ).status_code,
                200,
            )
        self.assertEqual(
            seen,
            [
                (
                    "https://172.30.80.17:9200/_plugins/_security/dashboardsinfo",
                    authorization("kibanaserver", "s" * 32),
                    None,
                ),
                ("http://172.30.80.15:20000/_search", human, tenant(self.row)),
            ],
        )

    def test_generic_console_discovery_is_scoped_to_its_named_index(self):
        from app.stores.opensearch import authorization, index

        seen = []

        class Bytes(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield b"{}"

        async def handler(request):
            seen.append(str(request.url))
            return httpx.Response(200, stream=Bytes())

        real_client = httpx.AsyncClient

        def transport(**kwargs):
            kwargs.pop("verify")
            return real_client(transport=httpx.MockTransport(handler), **kwargs)

        with (
            TestClient(
                dashboards.create_backend(lambda cid: self.row),
                base_url="http://" + dashboards.HOST,
                client=("172.30.80.31", 12345),
            ) as client,
            patch("app.stores.dashboards.httpx.AsyncClient", side_effect=transport),
        ):
            headers = {
                dashboards.HEADER: str(self.cid),
                "Authorization": authorization(
                    catalog.login(self.cid), "native-secret"
                ),
            }
            self.assertEqual(
                client.get(
                    "/_resolve/index/*?expand_wildcards=all", headers=headers
                ).status_code,
                200,
            )
            self.assertEqual(
                client.get("/_resolve/index/foreign", headers=headers).status_code, 200
            )
        self.assertEqual(
            seen,
            [
                "http://172.30.80.15:20000/_resolve/index/"
                + index(self.row)
                + "?expand_wildcards=all",
                "http://172.30.80.15:20000/_resolve/index/foreign",
            ],
        )

    def test_unbound_server_cannot_recreate_resource_metadata_after_lease_cleanup(self):
        from app.stores.opensearch import authorization, tenant

        physical = ".kibana_123_" + tenant(self.row) + "_1"
        headers = {"Authorization": authorization("kibanaserver", "s" * 32)}
        with (
            TestClient(
                dashboards.create_backend(lambda cid: None),
                base_url="http://" + dashboards.HOST,
                client=("172.30.80.31", 12345),
            ) as client,
            patch("app.stores.dashboards.httpx.AsyncClient") as upstream,
        ):
            self.assertEqual(
                client.get("/" + physical, headers=headers).status_code, 403
            )
            self.assertEqual(
                client.get(
                    "/.kibana", headers={**headers, "securitytenant": tenant(self.row)}
                ).status_code,
                403,
            )
            self.assertEqual(
                client.post(
                    "/_bulk",
                    headers=headers,
                    content=(
                        '{"index":{"_index":"'
                        + physical
                        + '"}}\n{"type":"synthetic"}\n'
                    ),
                ).status_code,
                403,
            )
            escaped = physical.replace(".", r"\u002e", 1)
            self.assertEqual(
                client.post(
                    "/_bulk",
                    headers=headers,
                    content=(
                        '{"index":{"_index":"' + escaped + '"}}\n{"type":"synthetic"}\n'
                    ),
                ).status_code,
                403,
            )
            self.assertEqual(
                client.post(
                    "/_bulk", headers=headers, content=b"x" * (1024 * 1024 + 1)
                ).status_code,
                413,
            )
        upstream.assert_not_called()
