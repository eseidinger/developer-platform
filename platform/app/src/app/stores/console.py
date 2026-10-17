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
import re
from datetime import datetime, timezone
from xml.etree import ElementTree
from urllib.parse import parse_qs
from uuid import UUID

import httpx2 as httpx
import h11
import jwt
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response, StreamingResponse
from . import catalog, recovery

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
    row = conn.execute("""SELECT c.credential_id,c.relay_port,c.expires_at,g.issuer,g.subject,r.provider,r.resource_id,r.created_at
        FROM store_credentials c JOIN store_grants g USING(grant_id) JOIN store_resources r USING(resource_id)
        JOIN projects p ON p.name=r.owner_project
        WHERE c.credential_id=%s AND c.state='active' AND c.expires_at>now() AND c.grant_version=g.version
        AND g.kind='human' AND g.state='active' AND r.state='active' AND r.observed_state='active'
        AND p.status<>'retired' AND c.relay_port IS NOT NULL
        AND NOT EXISTS(SELECT 1 FROM store_project_retirements WHERE project=r.owner_project)""",
        (credential_id,)).fetchone()
    if not row or not enabled(row[5]):
        return None
    value = dict(zip(('credential_id', 'relay_port', 'expires_at', 'issuer', 'subject', 'provider', 'resource_id', 'created_at'), row))
    return {**value, 'kind': 'human', 's3_sessions': catalog.console_sessions(conn, row[0]) if row[5] == 's3' else {}}


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


def session_metadata(raw, row):
    """Only public key IDs and a token hash leave the transient STS response."""
    from .http_relay import console_user
    fields = ElementTree.fromstring(raw).find('.//{*}Credentials')
    if fields is None:
        raise ValueError('Missing native credentials')
    access = fields.findtext('{*}AccessKeyId')
    token = fields.findtext('{*}SessionToken')
    expiry = datetime.fromisoformat(fields.findtext('{*}Expiration').replace('Z', '+00:00'))
    if not access or not re.fullmatch('[A-Za-z0-9]{20}', access) or not token or len(token) > 16384:
        raise ValueError('Invalid native session')
    claims = jwt.decode(token, options={'verify_signature': False})
    if claims.get('parent') != console_user(row['credential_id']) or expiry.tzinfo is None or expiry <= datetime.now(timezone.utc):
        raise ValueError('Different native parent')
    return access, hashlib.sha256(token.encode()).hexdigest(), min(expiry, row['expires_at'])


def record_session(conn, row, access, digest, expiry):
    conn.execute("SET LOCAL statement_timeout='3000ms'")
    conn.execute("SET LOCAL lock_timeout='2000ms'")
    catalog.lock(conn)
    current = lease(conn, row['credential_id'])
    if not current or current['provider'] != 's3':
        raise ValueError('Inactive console grant')
    existing = conn.execute('SELECT credential_id,token_sha256 FROM store_console_sessions WHERE native_access_key=%s', (access,)).fetchone()
    if existing and (str(existing[0]) != str(row['credential_id']) or existing[1] != digest):
        raise ValueError('Native session ownership mismatch')
    if not existing and len(current['s3_sessions']) >= 16:
        raise ValueError('Console session capacity is occupied')
    conn.execute("""INSERT INTO store_console_sessions(native_access_key,credential_id,token_sha256,expires_at)
        VALUES(%s,%s,%s,%s) ON CONFLICT(native_access_key) DO UPDATE SET expires_at=LEAST(store_console_sessions.expires_at,excluded.expires_at)""",
        (access, row['credential_id'], digest, min(expiry, current['expires_at'])))


async def acknowledged(row, access, digest):
    address = str(ipaddress.IPv4Address(os.environ['STORE_RELAY_IP']))
    url = f'http://{address}:19999/session/{row["relay_port"]}/{access}/{digest}'
    async with httpx.AsyncClient(trust_env=False, timeout=.5) as client:
        for _ in range(30):
            try:
                if (await client.get(url)).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(.1)
    raise ValueError('Private relay did not observe the native session')


def create_gateway(load, destination=backend, register=None, acknowledge=acknowledged):
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
        row = await authorize(request.cookies.get(COOKIE), 'session', port)
        if row['provider'] == 's3' and path == 'rustfs/admin/v3/is-admin':
            # Every platform console identity is a non-administrator. Native
            # admin discovery itself requires global rights in this release;
            # report the adapter's invariant without granting those rights.
            if request.method != 'GET' or request.scope['query_string']:
                raise HTTPException(405)
            return JSONResponse({'is_admin': False}, headers={'Cache-Control': 'no-store'})
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
        authorization = {}
        if not static:
            from .http_relay import identity
            try:
                authorization = identity(h11.Request(method=request.method, target=raw, headers=request.headers.raw), row)
            except (ValueError, h11.LocalProtocolError):
                # Native consoles need an authentication response to display
                # their login form. Keep the separate portal session intact.
                return JSONResponse({'detail': 'Enter the native credential for this lease'},
                    status_code=401, headers={'Cache-Control': 'no-store'})
        if row['provider'] == 's3' and not static and path == '' and request.method == 'GET':
            # A named-resource console lists its one catalog-authorized bucket.
            # This is portal metadata, already available through the resource API;
            # native signatures still authorize every actual object/data request.
            # Do not grant global ListAllMyBuckets merely to populate navigation.
            from .s3 import bucket
            tree = ElementTree.Element('ListAllMyBucketsResult', xmlns='http://s3.amazonaws.com/doc/2006-03-01/')
            buckets = ElementTree.SubElement(tree, 'Buckets')
            entry = ElementTree.SubElement(buckets, 'Bucket')
            ElementTree.SubElement(entry, 'Name').text = bucket(row)
            ElementTree.SubElement(entry, 'CreationDate').text = row['created_at'].isoformat()
            return Response(ElementTree.tostring(tree), media_type='application/xml', headers={'Cache-Control': 'no-store'})
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
            if path == '' and request.method == 'POST' and authorization.get('_console_login') and upstream.status_code == 200:
                if register is None:
                    raise ValueError('Native console sessions are not configured')
                raw_session = bytearray()
                async for part in upstream.aiter_bytes(chunk_size=16384):
                    raw_session.extend(part)
                    if len(raw_session) > 65536:
                        raise ValueError('Native session response exceeded its limit')
                access, digest, expiry = session_metadata(raw_session, row)
                await asyncio.to_thread(register, row, access, digest, expiry)
                await acknowledge(row, access, digest)
                result = Response(bytes(raw_session), media_type='application/xml', headers={'Cache-Control': 'no-store',
                    'Content-Security-Policy': "sandbox; default-src 'none'; frame-ancestors 'none'"})
                await upstream.aclose()
                await transport.aclose()
                slots.release()
                return result
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
