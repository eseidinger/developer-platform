import os
from datetime import datetime, timedelta, timezone
from unittest import TestCase
from unittest.mock import Mock, patch
from uuid import uuid4

import httpx2 as httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.routing import Host
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
            'issuer': 'https://identity.fixture.invalid', 'subject': 'human', 'provider': 's3'}
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
        self.assertEqual(seen[1][0], 'http://127.0.0.1:20000/')
        self.assertNotIn('transfer-encoding', seen[1][1])
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

    def test_cookie_omitting_s3_sdk_still_requires_native_identity_and_a_current_human_lease(self):
        find = Mock(return_value=self.row)
        app = FastAPI()
        app.router.routes.append(Host('console-{port:int}.apps.fixture.invalid', app=console.create_gateway(lambda cid: None, find=find)))
        client = TestClient(app, base_url=console.origin(20000))
        self.addCleanup(client.close)
        from app.stores.http_relay import access_key
        auth = f'AWS4-HMAC-SHA256 Credential={access_key(self.row["credential_id"])}/20261017/us-east-1/s3/aws4_request, SignedHeaders=host, Signature=' + 'a' * 64
        seen = []
        async def handler(request):
            seen.append(request.headers['authorization'])
            return httpx.Response(200, stream=Bytes(b'native-result'))
        real_client = httpx.AsyncClient
        with patch('app.stores.console.httpx.AsyncClient', side_effect=lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw)):
            self.assertEqual(client.get('/', headers={'Authorization': auth}).status_code, 200)
            self.assertEqual(client.get('/rustfs/console/', headers={'Authorization': auth}).status_code, 401)
            self.assertEqual(client.get('/bucket').status_code, 401)
            foreign = auth.replace(access_key(self.row['credential_id']), access_key(uuid4()))
            self.assertEqual(client.get('/bucket', headers={'Authorization': foreign}).status_code, 401)
            find.return_value = None  # Revoked/expired/application grants never qualify.
            self.assertEqual(client.get('/', headers={'Authorization': auth}).status_code, 401)
        self.assertEqual(seen, [auth])
