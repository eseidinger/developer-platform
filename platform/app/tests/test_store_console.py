import os
import asyncio
from pathlib import Path
import tempfile
from datetime import datetime, timedelta, timezone
from unittest import TestCase, IsolatedAsyncioTestCase
from unittest.mock import Mock, patch
from uuid import uuid4

import httpx2 as httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.routing import Host
from starlette.requests import Request
from app.stores import console


class Bytes(httpx.AsyncByteStream):
    def __init__(self, value): self.value = value
    async def __aiter__(self): yield self.value


class ConsoleBoundaryTests(TestCase):
    def setUp(self):
        self.patch = patch.dict(os.environ, {'DATABASE_KEY': 's' * 32, 'APPS_DOMAIN': 'apps.fixture.invalid',
            'PLATFORM_DOMAIN': 'platform.fixture.invalid', 'STORE_CONSOLE_HTTP_ENABLED': 'true',
            'STORE_ENABLED_PROVIDERS': 's3,qdrant', 'STORE_RELAY_IP': '127.0.0.1',
            'RUSTFS_IP': '127.0.0.2', 'QDRANT_IP': '127.0.0.3'})
        self.patch.start(); self.addCleanup(self.patch.stop)
        self.row = {'credential_id': str(uuid4()), 'relay_port': 20000,
            'expires_at': datetime.now(timezone.utc) + timedelta(hours=24),
            'issuer': 'https://identity.fixture.invalid', 'subject': 'human', 'provider': 's3',
            'resource_id': str(uuid4()), 'created_at': datetime.now(timezone.utc)}
        self.current = self.row
        self.app = FastAPI()
        self.app.router.routes.append(Host('console-{port:int}.apps.fixture.invalid',
            app=console.create_gateway(lambda cid: self.current if str(cid) == self.row['credential_id'] else None)))
        self.client = TestClient(self.app, base_url=console.origin(20000))
        self.addCleanup(self.client.close)

    def launch(self, token=None, port=20000, origin='https://platform.fixture.invalid'):
        return self.client.post(console.origin(port) + '/__platform/start', data={
            'launch': token or console.assertion(self.row, 'launch', 30)}, headers={'Origin': origin}, follow_redirects=False)

    def test_cookie_requires_portal_launch_then_remains_bound_to_live_human_and_generation(self):
        self.assertEqual(self.client.get('/').status_code, 401)
        response = self.launch()
        self.assertEqual(response.status_code, 303)
        cookie = response.headers['set-cookie']
        for flag in ('Secure', 'HttpOnly', 'SameSite=strict', 'Path=/'):
            self.assertIn(flag, cookie)
        self.assertNotIn('Domain=', cookie)
        self.assertEqual(self.client.get('/', follow_redirects=False).status_code, 303)
        self.current = None
        self.assertEqual(self.client.get('/').status_code, 401)

    def test_foreign_console_origin_identity_and_expired_assertions_are_denied(self):
        self.assertEqual(self.launch(origin='https://foreign.invalid').status_code, 403)
        self.assertEqual(self.launch(port=20001).status_code, 401)
        token = console.assertion(self.row, 'launch', 30)
        self.current = {**self.row, 'subject': 'other'}
        self.assertEqual(self.launch(token).status_code, 401)
        self.current = self.row
        expired = console.assertion({**self.row, 'expires_at': datetime.now(timezone.utc) - timedelta(seconds=2)}, 'launch', 30)
        self.assertEqual(self.launch(expired).status_code, 401)
        self.assertEqual(self.launch(console.assertion(self.row, 'session', 30)).status_code, 401)

    def test_no_http_launch_unbounded_body_or_cross_origin_writes(self):
        self.assertEqual(self.client.post('http://console-20000.apps.fixture.invalid/__platform/start').status_code, 400)
        self.assertEqual(self.client.post('/__platform/start', content=b'x' * 4097,
            headers={'Origin': 'https://platform.fixture.invalid', 'Content-Type': 'application/x-www-form-urlencoded'}).status_code, 413)
        self.launch()
        self.assertEqual(self.client.put('/bucket/key', content=b'body').status_code, 403)
        self.assertEqual(self.client.get('/rustfs/console/%2e%2e/private').status_code, 400)

    def test_proxy_preserves_signed_path_host_native_auth_and_body_without_forwarding_session(self):
        self.launch()
        seen = []
        async def handler(request):
            seen.append((str(request.url), dict(request.headers), await request.aread()))
            return httpx.Response(200, stream=Bytes(b'chunk'), headers={'Set-Cookie': 'unsafe=1', 'X-Native': 'ok'})
        real_client = httpx.AsyncClient
        from app.stores.http_relay import access_key
        auth = f'AWS4-HMAC-SHA256 Credential={access_key(self.row["credential_id"])}/20261017/us-east-1/s3/aws4_request, SignedHeaders=host, Signature=' + 'a' * 64
        with patch('app.stores.console.httpx.AsyncClient', side_effect=lambda **kw: real_client(
                transport=httpx.MockTransport(handler), **kw)):
            response = self.client.put('/resource/key%20with%20spaces?versionId=abc%2Bdef', content=b'payload',
                headers={'Origin': console.origin(20000), 'Authorization': auth,
                    'X-Forwarded-Host': 'attacker.invalid', 'Baggage': 'secret=bad'})
            listing = self.client.get('/', headers={'Authorization': auth}, follow_redirects=False)
            self.assertEqual(listing.status_code, 200)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b'chunk')
        self.assertNotIn('set-cookie', response.headers)
        url, headers, body = seen[0]
        self.assertEqual(url, 'http://127.0.0.1:20000/resource/key%20with%20spaces?versionId=abc%2Bdef')
        self.assertEqual(headers['host'], 'console-20000.apps.fixture.invalid')
        self.assertEqual(headers['authorization'], auth)
        self.assertEqual(body, b'payload')
        for name in ('cookie', 'x-forwarded-host', 'baggage'):
            self.assertNotIn(name, headers)
        self.assertEqual(len(seen), 1)
        from app.stores.s3 import bucket
        self.assertIn(bucket(self.row), listing.text)
        self.assertNotIn('transfer-encoding', listing.headers)
        self.assertEqual(response.headers['content-disposition'], 'attachment')
        self.assertIn("default-src 'none'", response.headers['content-security-policy'])

    def test_native_login_challenge_does_not_revoke_the_distinct_portal_session(self):
        self.launch()
        response = self.client.get('/bucket')
        self.assertEqual(response.status_code, 401)
        self.assertNotIn('clear-site-data', response.headers)
        self.assertIsNotNone(self.client.cookies.get(console.COOKIE))
        self.assertEqual(self.client.get('/', follow_redirects=False).status_code, 303)

    def test_static_asset_routes_are_read_only_and_never_use_the_data_relay(self):
        self.row['provider'] = 'qdrant'
        response = self.launch()
        self.assertEqual(response.headers['location'], '/dashboard/')
        seen = []
        async def handler(request):
            seen.append(str(request.url)); return httpx.Response(200, stream=Bytes(b'asset'))
        real_client = httpx.AsyncClient
        with patch('app.stores.console.httpx.AsyncClient', side_effect=lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw)):
            self.assertEqual(self.client.get('/dashboard/assets/index.js').status_code, 200)
        self.assertEqual(seen, ['http://127.0.0.3:6333/dashboard/assets/index.js'])
        self.assertEqual(self.client.put('/dashboard/assets/index.js', headers={'Origin': console.origin(20000)}).status_code, 405)

    def test_web_native_requests_and_assets_always_require_the_portal_cookie(self):
        from app.stores.http_relay import access_key
        auth = f'AWS4-HMAC-SHA256 Credential={access_key(self.row["credential_id"])}/20261017/us-east-1/s3/aws4_request, SignedHeaders=host, Signature=' + 'a' * 64
        self.assertEqual(self.client.get('/', headers={'Authorization': auth}).status_code, 401)
        self.assertEqual(self.client.get('/rustfs/console/', headers={'Authorization': auth}).status_code, 401)

    def test_pinned_rustfs_assets_require_a_live_session_and_cannot_escape_asset_root(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'STORE_RUSTFS_CONSOLE_DIR': directory}):
            root = Path(directory)
            (root / 'index.html').write_text('reviewed console')
            (root / 'browser').mkdir()
            (root / 'browser/index.html').write_text('bucket browser')
            (root / 'escape').symlink_to(root.parent)
            self.assertEqual(self.client.get('/rustfs/console/').status_code, 401)
            self.launch()
            response = self.client.get('/rustfs/console/browser/')
            self.assertEqual(response.text, 'bucket browser')
            self.assertEqual(response.headers['cache-control'], 'no-store')
            self.assertEqual(self.client.get('/rustfs/console/escape/private').status_code, 400)
            self.assertEqual(self.client.post('/rustfs/console/', headers={'Origin': console.origin(20000)}).status_code, 405)
            (root / 'index.html').unlink()
            self.assertEqual(self.client.get('/rustfs/console/').status_code, 503)
            self.current = None
            self.assertEqual(self.client.get('/rustfs/console/browser/').status_code, 401)

    def test_dashboards_forwards_only_native_cookie_and_injects_authoritative_lease(self):
        from app.stores import dashboards
        self.row['provider'] = 'opensearch'
        seen = []
        async def handler(request):
            seen.append(dict(request.headers))
            return httpx.Response(200, stream=Bytes(b'console'), headers={
                'Set-Cookie': dashboards.COOKIE + '=Fe26.2*native; Path=/wrong; Domain=foreign.invalid'})
        real_client = httpx.AsyncClient
        with patch.dict(os.environ, {'OPENSEARCH_DASHBOARDS_IP': '127.0.0.4'}), patch(
                'app.stores.console.httpx.AsyncClient', side_effect=lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw)):
            self.launch()
            self.client.cookies.set('unrelated', 'never-forward')
            response = self.client.get('/', headers={dashboards.HEADER: str(uuid4())})
            self.assertEqual(response.status_code, 200)
            self.assertIn('Secure', response.headers['set-cookie'])
            self.assertNotIn('Domain=', response.headers['set-cookie'])
            self.assertIn('Path=/', response.headers['set-cookie'])
            self.client.get('/')
        self.assertNotIn('cookie', seen[0])
        self.assertEqual(seen[0][dashboards.HEADER], self.row['credential_id'])
        self.assertEqual(seen[1]['cookie'], dashboards.COOKIE + '=Fe26.2*native')
        self.assertNotIn(console.COOKIE, seen[1]['cookie'])


class DashboardsStreamingTests(IsolatedAsyncioTestCase):
    async def check_fence(self, expire):
        class Held(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield b'first'
                await asyncio.Event().wait()
        cid = str(uuid4())
        row = {'credential_id': cid, 'relay_port': 20000, 'provider': 'opensearch',
            'issuer': 'https://identity.fixture.invalid', 'subject': 'human',
            'expires_at': datetime.now(timezone.utc) + timedelta(hours=24)}
        current = [dict(row)]
        with patch.dict(os.environ, {'DATABASE_KEY': 's' * 32, 'APPS_DOMAIN': 'apps.fixture.invalid',
                'OPENSEARCH_DASHBOARDS_IP': '127.0.0.4'}):
            app = console.create_gateway(lambda cid: current[0])
            request = Request({'type': 'http', 'method': 'GET', 'scheme': 'https', 'path': '/held',
                'raw_path': b'/held', 'query_string': b'', 'path_params': {'port': 20000},
                'headers': [(b'host', b'console-20000.apps.fixture.invalid'),
                    (b'cookie', (console.COOKIE + '=' + console.assertion(row, 'session', 86400)).encode())],
                'client': ('127.0.0.1', 12345)})
            async def handler(request): return httpx.Response(200, stream=Held())
            real_client = httpx.AsyncClient
            with patch('app.stores.console.httpx.AsyncClient', side_effect=lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw)):
                endpoint = next(route.endpoint for route in app.routes if getattr(route, 'path', None) == '/{path:path}')
                response = await endpoint(request, 'held')
                iterator = response.body_iterator
                self.assertEqual(await asyncio.wait_for(anext(iterator), 1), b'first')
                if expire:
                    current[0]['expires_at'] = datetime.now(timezone.utc) + timedelta(milliseconds=100)
                else:
                    current[0] = None
                with self.assertRaises(StopAsyncIteration):
                    await asyncio.wait_for(anext(iterator), 1)

    async def test_already_streaming_frontend_closes_on_revocation(self):
        await self.check_fence(False)

    async def test_already_streaming_frontend_closes_at_lease_deadline(self):
        await self.check_fence(True)
