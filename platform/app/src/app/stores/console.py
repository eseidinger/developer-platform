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
from pathlib import Path
from http.cookies import SimpleCookie
from datetime import datetime, timezone
from xml.etree import ElementTree
from urllib.parse import parse_qs
from uuid import UUID

import httpx2 as httpx
import h11
import jwt
from fastapi import FastAPI, HTTPException, Request, WebSocket
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from . import catalog, recovery, dashboards

COOKIE = '__Host-store-console'
PROVIDERS = {'s3', 'qdrant', 'opensearch', 'neo4j'}
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
    row = conn.execute("""SELECT c.credential_id,c.relay_port,c.expires_at,g.issuer,g.subject,r.provider,r.resource_id,r.created_at,c.admission_sha256,host(i.host)
        FROM store_credentials c JOIN store_grants g USING(grant_id) JOIN store_resources r USING(resource_id)
        LEFT JOIN store_instances i USING(resource_id)
        JOIN projects p ON p.name=r.owner_project
        WHERE c.credential_id=%s AND c.state='active' AND c.expires_at>now() AND c.grant_version=g.version
        AND g.kind='human' AND g.state='active' AND r.state='active' AND r.observed_state='active'
        AND p.status<>'retired' AND c.relay_port IS NOT NULL
        AND NOT EXISTS(SELECT 1 FROM store_project_retirements WHERE project=r.owner_project)""",
        (credential_id,)).fetchone()
    if not row or not enabled(row[5]):
        return None
    value = dict(zip(('credential_id', 'relay_port', 'expires_at', 'issuer', 'subject', 'provider', 'resource_id', 'created_at', 'admission_sha256', 'native_host'), row))
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
    if row['provider'] == 'neo4j': return row['native_host'], 7474
    if row['provider'] == 'opensearch':
        return os.environ['OPENSEARCH_DASHBOARDS_IP'], 5601
    if not static:
        return os.environ['STORE_RELAY_IP'], row['relay_port']
    return (os.environ['RUSTFS_IP'], 9001) if row['provider'] == 's3' else (os.environ['QDRANT_IP'], 6333)


def landing(provider):
    return {'s3': '/rustfs/console/', 'qdrant': '/dashboard/', 'opensearch': '/', 'neo4j': '/browser/'}[provider]


def dashboards_cookie(value):
    # Exactly one native encrypted cookie, never the portal cookie or a caller's
    # arbitrary cookie. Scope/security attributes are set by the gateway.
    if len(value) > 16384 or any(character in value for character in '\r\n;'):
        raise ValueError('Invalid native console cookie')
    return value


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


def create_gateway(load, destination=backend, register=None, acknowledge=acknowledged, observe_socket=None):
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    slots = asyncio.Semaphore(32)

    @app.exception_handler(HTTPException)
    async def failed(request, error):
        result = JSONResponse({'detail': error.detail}, status_code=error.status_code,
            headers={'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer'})
        if error.status_code == 401:
            result.headers['Clear-Site-Data'] = '"cache", "storage"'
            result.delete_cookie(COOKIE, secure=True, httponly=True, samesite='strict', path='/')
            result.delete_cookie(dashboards.COOKIE, secure=True, httponly=True, samesite='strict', path='/')
        return result

    async def authorize(token, kind, port):
        try:
            claims = jwt.decode(token, key(), algorithms=['HS256'], audience='store-console-' + kind,
                issuer=ISSUER, options={'require': ['exp', 'iat', 'sub', 'credential_id', 'port', 'identity_issuer']})
            if claims['port'] != port:
                raise ValueError('Different console')
            row = await asyncio.to_thread(load, UUID(claims['credential_id']))
            if (not row or row['relay_port'] != port or row['issuer'] != claims['identity_issuer']
                    or row['subject'] != claims['sub'] or row['expires_at'] <= datetime.now(timezone.utc)
                    or claims['exp'] <= time.time()):
                raise ValueError('Inactive human lease')
            return row
        except Exception:
            raise HTTPException(401, 'Open an active console lease from the platform portal') from None

    @app.websocket('/{path:path}')
    async def bolt_socket(socket: WebSocket, path: str):
        upstream = None
        tasks = []
        acquired = False
        phase = 'request-boundary'
        try:
            port = int(socket.path_params['port'])
            base = origin(port)
            proxied = socket.client and socket.client.host == os.environ.get('PROXY_IP') and socket.headers.get('x-forwarded-proto') == 'https'
            for phase, valid in [
                    ('request-path',not path),
                    ('request-host',socket.headers.get('host') in {base[8:],base[8:]+':443'}),
                    ('request-origin',socket.headers.get('origin') == base),
                    ('request-tls',socket.url.scheme == 'wss' or proxied),
                    ('request-subprotocol',socket.headers.get('sec-websocket-protocol') in {None,'bolt'})]:
                if not valid: raise ValueError()
            phase = 'catalog-authentication'
            row = await authorize(socket.cookies.get(COOKIE), 'session', port)
            if row['provider'] != 'neo4j': raise ValueError()
            await asyncio.wait_for(slots.acquire(), .1)
            acquired = True
            address = str(ipaddress.IPv4Address(os.environ['STORE_RELAY_IP']))
            phase = 'private-relay-connect'
            reader, upstream = await asyncio.wait_for(asyncio.open_connection(address, port), 3)
            phase = 'protocol-forwarding'
            await socket.accept(subprotocol='bolt' if socket.headers.get('sec-websocket-protocol') else None)
            async def requests():
                while True:
                    data = await socket.receive_bytes()
                    if not data or len(data) > 1056768: return
                    upstream.write(data)
                    await upstream.drain()
            async def responses():
                while data := await reader.read(65536): await socket.send_bytes(data)
            async def guard():
                while True:
                    remaining = row['expires_at'].timestamp() - time.time()
                    if remaining <= 0: return
                    try: await asyncio.wait_for(authorize(socket.cookies.get(COOKIE), 'session', port), min(.5,remaining))
                    except Exception: return
                    await asyncio.sleep(min(.25,remaining))
            tasks = [asyncio.create_task(requests()),asyncio.create_task(responses()),asyncio.create_task(guard())]
            done,_=await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            if observe_socket:
                for task in done:
                    error=task.exception()
                    observe_socket('request' if task is tasks[0] else 'response' if task is tasks[1] else 'guard',type(error).__name__ if error else 'Completed')
        except Exception as error:
            if observe_socket: observe_socket(phase,type(error).__name__)
        finally:
            for task in tasks: task.cancel()
            await asyncio.gather(*tasks,return_exceptions=True)
            if upstream: upstream.close()
            with contextlib.suppress(Exception): await socket.close(code=1008)
            if acquired: slots.release()

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
            target = landing(row['provider'])
            response = RedirectResponse(target, status_code=303, headers={'Cache-Control': 'no-store',
                'Referrer-Policy': 'no-referrer', 'Clear-Site-Data': '"cache", "storage"'})
            response.set_cookie(COOKIE, assertion(row, 'session', 86400), secure=True, httponly=True,
                samesite='strict', path='/', max_age=max(0, int(row['expires_at'].timestamp() - time.time())))
            if row['provider'] == 'opensearch':
                response.delete_cookie(dashboards.COOKIE, secure=True, httponly=True, samesite='strict', path='/')
            return response
        row = await authorize(request.cookies.get(COOKIE), 'session', port)
        frontend = row['provider'] == 'opensearch'
        if row['provider'] == 'neo4j' and path == '' and request.method == 'GET':
            # Catalog-authorized connection discovery; never leak raw native addresses.
            return JSONResponse({'bolt_direct': 'bolt+s://' + base[8:] + ':443',
                'bolt_routing': 'bolt+s://' + base[8:] + ':443'}, headers={'Cache-Control':'no-store'})
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
        static = ((row['provider'] == 'neo4j' and (path == 'browser' or path.startswith('browser/')))
                  or (row['provider'] == 's3' and (path == 'rustfs/console' or path.startswith('rustfs/console/')))
                  or (row['provider'] == 'qdrant' and (path == 'dashboard' or path.startswith('dashboard/'))))
        native_auth = (request.headers.get('authorization') or request.headers.get('api-key')
            or b'X-Amz-Credential=' in request.scope['query_string'])
        if path == '' and request.method in {'GET', 'HEAD'} and not native_auth and not frontend:
            return RedirectResponse(landing(row['provider']), 303)
        if static:
            if any(part in {'.', '..'} for part in path.split('/')):
                raise HTTPException(400)
            if request.method not in {'GET', 'HEAD'}:
                raise HTTPException(405)
            if row['provider'] == 's3':
                root = Path(os.environ.get('STORE_RUSTFS_CONSOLE_DIR', '/app/store-consoles/rustfs')).resolve()
                target = (root / path.removeprefix('rustfs/console').lstrip('/')).resolve()
                if not target.is_relative_to(root):
                    raise HTTPException(400)
                if target.is_dir():
                    target = target / 'index.html'
                if not target.is_file():
                    target = root / 'index.html'
                if not target.is_file():
                    raise HTTPException(503, 'Pinned console assets are unavailable')
                return FileResponse(target, headers={'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer',
                    'X-Content-Type-Options': 'nosniff', 'X-Frame-Options': 'DENY',
                    'Content-Security-Policy': "frame-ancestors 'none'; object-src 'none'; frame-src 'none'; base-uri 'self'"})
        address, backend_port = destination(row, static)
        address = str(ipaddress.IPv4Address(address))
        raw = request.scope['raw_path'] + (b'?' + request.scope['query_string'] if request.scope['query_string'] else b'')
        authorization = {}
        if not static and not frontend:
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
                   and not name.lower().startswith(('x-forwarded-', 'x-platform-store-'))]
        headers.append(('Host', request.headers['host']))
        if frontend:
            from .opensearch import tenant
            headers.append((dashboards.HEADER, str(row['credential_id'])))
            headers = [(name, value) for name, value in headers if name.lower() != 'securitytenant']
            headers.append(('securitytenant', tenant(row)))
            headers.append(('X-Forwarded-Proto', 'https'))
            if dashboards.COOKIE in request.cookies:
                headers.append(('Cookie', dashboards.COOKIE + '=' + dashboards_cookie(request.cookies[dashboards.COOKIE])))
        if request.method in {'GET', 'HEAD'} and (request.headers.get('transfer-encoding')
                or request.headers.get('content-length', '0') != '0'):
            raise HTTPException(400, 'Console reads cannot carry a body')
        # Preserve native signed paths/headers and stream bytes without buffering.
        # The relay enforces native identity, connection limits and hard deadlines.
        try:
            await asyncio.wait_for(slots.acquire(), 5)
        except TimeoutError:
            raise HTTPException(503, 'Console capacity is occupied') from None
        transport = httpx.AsyncClient(trust_env=False, follow_redirects=False, timeout=httpx.Timeout(60, connect=3))
        upstream = None
        native_cookies = []
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
            if frontend:
                for raw_cookie in upstream.headers.get_list('set-cookie'):
                    parsed = SimpleCookie(); parsed.load(raw_cookie)
                    if dashboards.COOKIE in parsed:
                        native_cookies.append(dashboards_cookie(parsed[dashboards.COOKIE].value))
        except BaseException as error:
            slots.release()
            with contextlib.suppress(asyncio.CancelledError, TimeoutError):
                await asyncio.shield(asyncio.wait_for(transport.aclose(), 3))
            if isinstance(error, asyncio.CancelledError):
                raise
            raise HTTPException(502, 'Console connection unavailable') from None

        async def stream():
            async def alive():
                while True:
                    remaining = (row['expires_at'] - datetime.now(timezone.utc)).total_seconds()
                    if remaining <= 0: return
                    try:
                        current = await asyncio.wait_for(asyncio.to_thread(load, UUID(str(row['credential_id']))), min(.5, remaining))
                    except Exception:
                        return
                    deadline = min(current['expires_at'], row['expires_at']) if current else datetime.now(timezone.utc)
                    if deadline <= datetime.now(timezone.utc):
                        return
                    await asyncio.sleep(min(.5, max(0, (deadline - datetime.now(timezone.utc)).total_seconds())))
            # Dashboards loads dozens of immutable frontend bundles at once.
            # They contain no tenant data and are authorized when requested;
            # repeated catalog probes can truncate a bundle under burst load.
            asset = (path.startswith(('9054/bundles/', 'ui/')) or path in {'startup.js', 'bootstrap.js'})
            guard = asyncio.create_task(alive()) if frontend and not asset else None
            pending = None
            try:
                iterator = upstream.aiter_raw().__aiter__()
                while True:
                    pending = asyncio.create_task(anext(iterator))
                    if guard:
                        done, _ = await asyncio.wait((guard, pending), return_when=asyncio.FIRST_COMPLETED)
                        if guard in done: return
                    try:
                        yield await pending
                    except StopAsyncIteration:
                        break
            finally:
                for task in (guard, pending):
                    if task: task.cancel()
                await asyncio.gather(*(task for task in (guard, pending) if task), return_exceptions=True)
                slots.release()
                async def close():
                    with contextlib.suppress(Exception):
                        await upstream.aclose()
                    await transport.aclose()
                with contextlib.suppress(asyncio.CancelledError, TimeoutError):
                    await asyncio.shield(asyncio.wait_for(close(), 3))

        result = StreamingResponse(stream(), status_code=upstream.status_code)
        # Uvicorn supplies Date. Forwarding the provider's Date adds a second
        # value, which browsers combine into an invalid timestamp. AWS SDK then
        # poisons its clock offset and cannot sign subsequent object uploads.
        result.raw_headers = [(name, value) for name, value in upstream.headers.raw
            if name.decode('latin1').lower() not in HOP | {'date', 'set-cookie', 'access-control-allow-origin', 'access-control-allow-credentials'}]
        result.headers.update({'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer',
            'X-Content-Type-Options': 'nosniff', 'Cross-Origin-Resource-Policy': 'same-origin',
            'X-Frame-Options': 'DENY'})
        policy = ("frame-ancestors 'none'; object-src 'none'; frame-src 'none'; base-uri 'self'"
            if static or frontend else "sandbox; default-src 'none'; frame-ancestors 'none'")
        if (static or frontend) and upstream.headers.get('content-security-policy'):
            # Multiple policies intersect: retain the official console's script,
            # worker and nonce restrictions while adding the platform boundary.
            result.headers.append('Content-Security-Policy', policy)
        else:
            result.headers['Content-Security-Policy'] = policy
        for value in native_cookies:
            result.set_cookie(dashboards.COOKIE, value, path='/', secure=True, httponly=True, samesite='strict',
                max_age=max(0, int(row['expires_at'].timestamp() - time.time())) if value else 0)
        if not static and row['provider'] == 's3' and not result.headers.get('content-type', '').startswith(('application/json', 'application/xml')):
            result.headers['Content-Disposition'] = 'attachment'
        return result
    return app
