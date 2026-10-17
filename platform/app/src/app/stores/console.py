"""Portal-authenticated, lease-bound official RustFS/Qdrant console gateway.

Launch assertions travel only in POST bodies. Host-only cookies authorize one
human credential generation; native requests still authenticate at the relay.
The gateway never injects a backend credential or rewrites a signed S3 path.
"""
import asyncio
import contextlib
import hashlib
import hmac
import ipaddress
import os
import time
from urllib.parse import parse_qs
from uuid import UUID

import httpx2 as httpx
import h11
import jwt
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
from . import recovery

COOKIE = '__Host-store-console'
PROVIDERS = {'qdrant'}  # RustFS native-key → STS session binding is not yet accepted.
ISSUER = 'developer-platform-store-console'
HOP = {'host', 'cookie', 'connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization',
       'te', 'trailer', 'transfer-encoding', 'upgrade', 'forwarded', 'x-forwarded-host',
       'x-forwarded-for', 'x-forwarded-proto', 'x-platform-trace-id', 'traceparent', 'tracestate', 'baggage'}


def key():
    value = os.environ['DATABASE_KEY']
    if len(value) < 32:
        raise ValueError('Console signing configuration unavailable')
    return hmac.digest(value.encode(), b'store-console-session-v1', 'sha256')


def enabled(provider):
    return (provider in PROVIDERS and os.environ.get('STORE_CONSOLE_HTTP_ENABLED') == 'true'
        and provider in os.environ.get('STORE_ENABLED_PROVIDERS', '').split(','))


def lease(conn, credential_id):
    if recovery.required(conn):
        return None
    if conn.execute('SELECT COALESCE(backup_until>now(),false) FROM store_control WHERE singleton').fetchone()[0]:
        return None
    row = conn.execute("""SELECT c.credential_id,c.relay_port,c.expires_at,g.issuer,g.subject,r.provider
        FROM store_credentials c JOIN store_grants g USING(grant_id) JOIN store_resources r USING(resource_id)
        JOIN projects p ON p.name=r.owner_project
        WHERE c.credential_id=%s AND c.state='active' AND c.expires_at>now() AND c.grant_version=g.version
        AND g.kind='human' AND g.state='active' AND r.state='active' AND r.observed_state='active'
        AND p.status<>'retired' AND c.relay_port IS NOT NULL
        AND NOT EXISTS(SELECT 1 FROM store_project_retirements WHERE project=r.owner_project)""",
        (credential_id,)).fetchone()
    if not row or not enabled(row[5]):
        return None
    return dict(zip(('credential_id', 'relay_port', 'expires_at', 'issuer', 'subject', 'provider'), row))


def origin(port):
    if not 20000 <= port <= 20511:
        raise ValueError('Invalid lease port')
    return f'https://console-{port}.' + os.environ['APPS_DOMAIN']


def lease_at_port(conn, port):
    row = conn.execute("SELECT credential_id FROM store_credentials WHERE relay_port=%s AND state='active' AND expires_at>now()", (port,)).fetchone()
    return lease(conn, row[0]) if row else None


def assertion(row, kind, lifetime):
    now = int(time.time())
    return jwt.encode({'iss': ISSUER, 'aud': 'store-console-' + kind, 'iat': now,
        'exp': min(now + lifetime, int(row['expires_at'].timestamp())),
        'sub': row['subject'], 'identity_issuer': row['issuer'],
        'credential_id': str(row['credential_id']), 'port': row['relay_port']}, key(), algorithm='HS256')


def backend(row, static):
    if not static:
        return os.environ['STORE_RELAY_IP'], row['relay_port']
    return (os.environ['RUSTFS_IP'], 9001) if row['provider'] == 's3' else (os.environ['QDRANT_IP'], 6333)


def create_gateway(load, destination=backend, find=None):
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    slots = asyncio.Semaphore(32)

    @app.exception_handler(HTTPException)
    async def failed(request, error):
        result = JSONResponse({'detail': error.detail}, status_code=error.status_code,
            headers={'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer'})
        if error.status_code == 401:
            result.headers['Clear-Site-Data'] = '"cache", "storage"'
            result.delete_cookie(COOKIE, secure=True, httponly=True, samesite='strict', path='/')
        return result

    async def authorize(token, kind, port):
        try:
            claims = jwt.decode(token, key(), algorithms=['HS256'], audience='store-console-' + kind,
                issuer=ISSUER, options={'require': ['exp', 'iat', 'sub', 'credential_id', 'port', 'identity_issuer']})
            if claims['port'] != port:
                raise ValueError('Different console')
            row = await asyncio.to_thread(load, UUID(claims['credential_id']))
            if (not row or row['relay_port'] != port or row['issuer'] != claims['identity_issuer']
                    or row['subject'] != claims['sub']):
                raise ValueError('Inactive human lease')
            return row
        except Exception:
            raise HTTPException(401, 'Open an active console lease from the platform portal') from None

    @app.api_route('/{path:path}', methods=['GET', 'HEAD', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS'])
    async def console(request: Request, path: str):
        try:
            port = int(request.path_params['port'])
            base = origin(port)
            if request.headers.get('host') not in {base[8:], base[8:] + ':443'}:
                raise ValueError('Invalid host')
        except (ValueError, KeyError):
            raise HTTPException(404) from None
        proxied_tls = (request.client is not None and request.client.host == os.environ.get('PROXY_IP')
            and request.headers.get('x-forwarded-proto') == 'https')
        if request.url.scheme != 'https' and not proxied_tls:
            raise HTTPException(400, 'Console access requires HTTPS')
        if path == '__platform/start':
            if (request.method != 'POST' or request.headers.get('origin') != 'https://' + os.environ['PLATFORM_DOMAIN']
                    or request.headers.get('content-type', '').split(';', 1)[0] != 'application/x-www-form-urlencoded'):
                raise HTTPException(403, 'Open consoles from the platform portal')
            body = bytearray()
            async for part in request.stream():
                body.extend(part)
                if len(body) > 4096:
                    raise HTTPException(413)
            try:
                fields = parse_qs(body.decode('ascii'), strict_parsing=True, max_num_fields=1)
                token = fields['launch'][0]
            except (ValueError, UnicodeError, KeyError):
                raise HTTPException(400) from None
            row = await authorize(token, 'launch', port)
            target = '/rustfs/console/' if row['provider'] == 's3' else '/dashboard/'
            response = RedirectResponse(target, status_code=303, headers={'Cache-Control': 'no-store',
                'Referrer-Policy': 'no-referrer', 'Clear-Site-Data': '"cache", "storage"'})
            response.set_cookie(COOKIE, assertion(row, 'session', 86400), secure=True, httponly=True,
                samesite='strict', path='/', max_age=max(0, int(row['expires_at'].timestamp() - time.time())))
            return response
        signed_s3 = (request.headers.get('authorization', '').startswith('AWS4-HMAC-SHA256 ')
            or b'X-Amz-Credential=' in request.scope['query_string'])
        if not request.cookies.get(COOKIE) and signed_s3 and find is not None:
            # Browser S3 SDKs explicitly omit cookies. Their native signature
            # authenticates data requests; never inject a credential or expose
            # console assets through this path. Only current human leases qualify.
            try:
                row = await asyncio.to_thread(find, port)
            except Exception:
                row = None
            if not row or row['provider'] != 's3' or path.startswith('rustfs/console'):
                raise HTTPException(401, 'An active human S3 lease is required')
        else:
            row = await authorize(request.cookies.get(COOKIE), 'session', port)
        if row['provider'] == 's3' and path == 'rustfs/admin/v3/oidc/providers':
            # The platform portal supplies OIDC. This adapter supports only
            # the explicitly granted native resource login, so advertise no
            # alternate RustFS-wide OIDC identities to the official login UI.
            if request.method != 'GET' or request.scope['query_string']:
                raise HTTPException(405)
            return JSONResponse([], headers={'Cache-Control': 'no-store'})
        if request.method not in {'GET', 'HEAD'} and request.headers.get('origin') != base:
            raise HTTPException(403, 'Console origin required')
        if request.headers.get('upgrade') or request.method == 'OPTIONS':
            raise HTTPException(400, 'Unsupported console protocol')
        static = ((row['provider'] == 's3' and (path == 'rustfs/console' or path.startswith('rustfs/console/')))
                  or (row['provider'] == 'qdrant' and (path == 'dashboard' or path.startswith('dashboard/'))))
        native_auth = (request.headers.get('authorization') or request.headers.get('api-key')
            or b'X-Amz-Credential=' in request.scope['query_string'])
        if path == '' and request.method in {'GET', 'HEAD'} and not native_auth:
            return RedirectResponse('/rustfs/console/' if row['provider'] == 's3' else '/dashboard/', 303)
        if static:
            if any(part in {'.', '..'} for part in path.split('/')):
                raise HTTPException(400)
            if request.method not in {'GET', 'HEAD'}:
                raise HTTPException(405)
        address, backend_port = destination(row, static)
        address = str(ipaddress.IPv4Address(address))
        raw = request.scope['raw_path'] + (b'?' + request.scope['query_string'] if request.scope['query_string'] else b'')
        if not static:
            from .http_relay import identity
            try:
                identity(h11.Request(method=request.method, target=raw, headers=request.headers.raw), row)
            except (ValueError, h11.LocalProtocolError):
                # Native consoles need an authentication response to display
                # their login form. Keep the separate portal session intact.
                return JSONResponse({'detail': 'Enter the native credential for this lease'},
                    status_code=401, headers={'Cache-Control': 'no-store'})
        url = httpx.URL(scheme='http', host=address, port=backend_port, raw_path=raw)
        headers = [(name, value) for name, value in request.headers.items() if name.lower() not in HOP
                   and not name.lower().startswith('x-forwarded-')]
        headers.append(('Host', request.headers['host']))
        if request.method in {'GET', 'HEAD'} and (request.headers.get('transfer-encoding')
                or request.headers.get('content-length', '0') != '0'):
            raise HTTPException(400, 'Console reads cannot carry a body')
        # Preserve native signed paths/headers and stream bytes without buffering.
        # The relay enforces native identity, connection limits and hard deadlines.
        try:
            await asyncio.wait_for(slots.acquire(), .1)
        except TimeoutError:
            raise HTTPException(503, 'Console capacity is occupied') from None
        transport = httpx.AsyncClient(trust_env=False, follow_redirects=False, timeout=httpx.Timeout(60, connect=3))
        upstream = None
        try:
            upstream = await transport.send(transport.build_request(request.method, url, headers=headers,
                content=None if request.method in {'GET', 'HEAD'} else request.stream()), stream=True)
        except BaseException as error:
            slots.release()
            with contextlib.suppress(asyncio.CancelledError, TimeoutError):
                await asyncio.shield(asyncio.wait_for(transport.aclose(), 3))
            if isinstance(error, asyncio.CancelledError):
                raise
            raise HTTPException(502, 'Console connection unavailable') from None

        async def stream():
            try:
                async for part in upstream.aiter_raw():
                    yield part
            finally:
                slots.release()
                async def close():
                    with contextlib.suppress(Exception):
                        await upstream.aclose()
                    await transport.aclose()
                with contextlib.suppress(asyncio.CancelledError, TimeoutError):
                    await asyncio.shield(asyncio.wait_for(close(), 3))

        result = StreamingResponse(stream(), status_code=upstream.status_code)
        result.raw_headers = [(name, value) for name, value in upstream.headers.raw
            if name.decode('latin1').lower() not in HOP | {'set-cookie', 'access-control-allow-origin', 'access-control-allow-credentials'}]
        result.headers.update({'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer',
            'X-Content-Type-Options': 'nosniff', 'Cross-Origin-Resource-Policy': 'same-origin',
            'Content-Security-Policy': ("frame-ancestors 'none'; object-src 'none'; frame-src 'none'; base-uri 'self'"
                if static else "sandbox; default-src 'none'; frame-ancestors 'none'"), 'X-Frame-Options': 'DENY'})
        if not static and row['provider'] == 's3' and not result.headers.get('content-type', '').startswith(('application/json', 'application/xml')):
            result.headers['Content-Disposition'] = 'attachment'
        return result
    return app
