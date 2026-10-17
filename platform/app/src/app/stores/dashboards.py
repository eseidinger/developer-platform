"""Private Dashboards-to-OpenSearch bridge with exact human lease binding.

Only the fixed console service may call this host. Human requests retain native
Basic authentication and traverse the same credential-bound data relay as native
clients. The server account can initialize only its native system metadata.
"""
import asyncio
import base64
import contextlib
import ipaddress
import os
from datetime import datetime, timezone
from uuid import UUID

import h11
import httpx2 as httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse

from . import catalog
from .http_relay import identity

HOST = 'opensearch-store-backend.internal'
HEADER = 'x-platform-store-lease'
COOKIE = '__Host-store-dashboards-auth'


def native_target(request, load):
    if not request.client or request.client.host != os.environ.get('OPENSEARCH_DASHBOARDS_IP'):
        raise HTTPException(403)
    names = [key for key, _ in request.headers.raw]
    if len(set(names)) != len(names) or request.headers.get('upgrade'):
        raise HTTPException(400)
    try:
        metadata = (request.method == 'GET' and request.scope['raw_path'] == b'/_plugins/_security/dashboardsinfo'
            and not request.scope['query_string'])
        auth = request.headers.get('authorization', '')
        if not auth and metadata:
            user = ''
        else:
            if not auth.startswith('Basic '): raise ValueError()
            user = base64.b64decode(auth[6:], validate=True).split(b':', 1)[0].decode('ascii')
        if user == 'kibanaserver' and HEADER not in request.headers:
            address = str(ipaddress.IPv4Address(os.environ['OPENSEARCH_IP']))
            return f'https://{address}:9200', os.environ['OPENSEARCH_CA_FILE'], None
        selected = UUID(request.headers[HEADER])
        row = load(selected)
        if (not row or row['provider'] != 'opensearch' or row.get('kind') != 'human'
                or row['expires_at'] <= datetime.now(timezone.utc)
                or not 20000 <= row['relay_port'] <= 20511):
            raise ValueError()
        # The official login page makes this public native configuration read
        # before a user has signed in. Preserve its anonymous request (or the
        # restricted server identity), still requiring the launched human lease.
        if metadata and user in {'', 'kibanaserver'}:
            address = str(ipaddress.IPv4Address(os.environ['OPENSEARCH_IP']))
            return f'https://{address}:9200', os.environ['OPENSEARCH_CA_FILE'], None
        if user != catalog.login(selected): raise ValueError()
        identity(h11.Request(method=request.method, target=request.scope['raw_path'], headers=request.headers.raw), row)
        address = str(ipaddress.IPv4Address(os.environ['STORE_RELAY_IP']))
        return f'http://{address}:{row["relay_port"]}', True, row
    except (KeyError, ValueError, UnicodeError, h11.LocalProtocolError):
        raise HTTPException(403, 'Matching active human store lease required') from None


def create_backend(load, server=None):
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    slots = asyncio.Semaphore(32)

    @app.api_route('/{path:path}', methods=['GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE'])
    async def native(request: Request, path: str):
        target, verify, row = await asyncio.to_thread(native_target, request, load)
        if row is None and server is not None:  # Disposable provider endpoint only.
            target, verify = server
        raw = request.scope['raw_path'] + (b'?' + request.scope['query_string'] if request.scope['query_string'] else b'')
        # Fixed native destinations only; no caller-controlled upstream URL or
        # operator credential injection. Native roles authenticate every request.
        url = httpx.URL(target).copy_with(raw_path=raw)
        headers = {name: request.headers[name] for name in ('authorization', 'content-type', 'securitytenant') if name in request.headers}
        try:
            await asyncio.wait_for(slots.acquire(), .1)
        except TimeoutError:
            raise HTTPException(503, 'Console capacity is occupied') from None
        transport = None
        try:
            transport = httpx.AsyncClient(trust_env=False, follow_redirects=False, verify=verify, timeout=httpx.Timeout(60, connect=3))
            response = await transport.send(transport.build_request(request.method, url, headers=headers,
                content=None if request.method in {'GET', 'HEAD'} else request.stream()), stream=True)
        except BaseException as error:
            slots.release()
            if transport: await transport.aclose()
            if isinstance(error, asyncio.CancelledError): raise
            raise HTTPException(502, 'Native console connection unavailable') from None

        async def stream():
            try:
                async for part in response.aiter_raw():
                    yield part
            finally:
                slots.release()
                with contextlib.suppress(Exception): await response.aclose()
                await transport.aclose()
        result = StreamingResponse(stream(), status_code=response.status_code)
        result.raw_headers = [(name, value) for name, value in response.headers.raw
            if name.lower() not in {b'connection', b'keep-alive', b'transfer-encoding', b'set-cookie',
                b'access-control-allow-origin', b'access-control-allow-credentials'}]
        result.headers['Cache-Control'] = 'no-store'
        return result
    return app
