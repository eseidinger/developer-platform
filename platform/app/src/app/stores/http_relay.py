"""One credential-bound HTTP exchange per connection; no reusable auth tunnel.

Backends authenticate the original credential/signature and enforce native resource
permissions. The relay additionally binds identity to the port's lease and closes
streams on revocation/expiry, including a request whose response is still streaming.
No URL, header, body or provider diagnostic is logged.
"""

import asyncio
import base64
import contextlib
import hashlib
import hmac
import json
import re
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

import h11

from . import catalog


def access_key(credential_id):
    return "P" + UUID(str(credential_id)).hex[:19].upper()


def console_user(credential_id):
    return "console-" + UUID(str(credential_id)).hex


def identity(request, lease):
    """Inspect only a bounded identity; backend still verifies its authentication."""
    headers = {}
    for key, value in request.headers:
        if key in headers:
            raise ValueError("Repeated HTTP header")
        headers[key] = value
    if any(
        key in headers
        for key in (b"upgrade", b"proxy-authorization", b"proxy-connection")
    ):
        raise ValueError("Unsupported HTTP protocol")
    target = request.target.decode("ascii")
    if not target.startswith("/") or target.startswith("//") or "#" in target:
        raise ValueError("Origin-form target required")
    auth = headers.get(b"authorization", b"").decode("ascii")
    if lease["provider"] == "s3":
        query = parse_qs(
            urlsplit(target).query, keep_blank_values=True, max_num_fields=64
        )
        credentials = query.get("X-Amz-Credential", [])
        if credentials:
            if auth or len(credentials) != 1:
                raise ValueError("Ambiguous S3 authentication")
            key = credentials[0].split("/")[0]
        else:
            match = re.fullmatch(
                r"AWS4-HMAC-SHA256 Credential=([^/ ,]+)/[^,]+,\s*SignedHeaders=[^,]+,\s*Signature=[a-f0-9]{64}",
                auth,
            )
            if not match:
                raise ValueError("Signed S3 request required")
            key = match[1]
        if key == access_key(lease["credential_id"]):
            pass
        elif lease.get("kind") == "human" and key == console_user(
            lease["credential_id"]
        ):
            headers["_console_login"] = True
        else:
            session = (
                lease.get("s3_sessions", {}).get(key)
                if lease.get("kind") == "human"
                else None
            )
            tokens = query.get("X-Amz-Security-Token", [])
            if b"x-amz-security-token" in headers:
                if tokens:
                    raise ValueError("Ambiguous session token")
                tokens = [headers[b"x-amz-security-token"].decode("ascii")]
            if (
                session is None
                or len(tokens) != 1
                or session["expires_at"] <= datetime.now(UTC)
                or not hmac.compare_digest(
                    hashlib.sha256(tokens[0].encode()).hexdigest(),
                    session["token_sha256"],
                )
            ):
                raise ValueError("Lease identity mismatch")
            headers["_session"] = (key, session["token_sha256"])
    elif lease["provider"] in {"opensearch", "neo4j", "couchdb", "hugegraph"}:
        if not auth.startswith("Basic "):
            raise ValueError("Basic authentication required")
        raw = base64.b64decode(auth[6:], validate=True)
        if (
            b":" not in raw
            or raw.split(b":", 1)[0] != catalog.login(lease["credential_id"]).encode()
        ):
            raise ValueError("Lease identity mismatch")
        if lease["provider"] in {"neo4j", "couchdb", "hugegraph"}:
            from .neo4j import admission

            if lease["provider"] == "neo4j" and b"impersonated-user" in headers:
                raise ValueError("Impersonation unavailable")
            admission(raw.split(b":", 1)[1].decode("ascii"), lease)
    elif lease["provider"] == "qdrant":
        token = headers.get(b"api-key")
        if token and auth:
            raise ValueError("Ambiguous JWT authentication")
        token = token.decode("ascii") if token else auth.removeprefix("Bearer ")
        pieces = token.split(".")
        if len(pieces) != 3:
            raise ValueError("JWT required")
        payload = json.loads(
            base64.urlsafe_b64decode(pieces[1] + "=" * (-len(pieces[1]) % 4))
        )
        if payload.get("jti") != str(lease["credential_id"]):
            raise ValueError("Lease identity mismatch")
        # This untrusted inspection never grants authentication. The native
        # Qdrant service must verify the JWT signature and collection permissions.
    else:
        raise ValueError("Unsupported HTTP provider")
    return headers


async def _event(connection, reader):
    while True:
        event = connection.next_event()
        if event is not h11.NEED_DATA:
            return event
        data = await reader.read(65536)
        connection.receive_data(data)


async def exchange(reader, writer, lease, backend, tls=None, authorized=None):
    front = h11.Connection(h11.SERVER, max_incomplete_event_size=16384)
    request = await asyncio.wait_for(_event(front, reader), 5)
    if not isinstance(request, h11.Request):
        raise TypeError("HTTP request required")
    headers = identity(request, lease)
    admin_index = False
    if lease["provider"] == "couchdb":
        from .couchdb_access import authorize, validate_index

        admin_index = bool(authorize(request.method, request.target, lease))
        allowed_headers = {
            b"host",
            b"authorization",
            b"content-type",
            b"accept",
            b"content-length",
            b"transfer-encoding",
            b"if-match",
            b"if-none-match",
            b"user-agent",
            b"accept-encoding",
            b"range",
            b"prefer",
            b"connection",
            b"expect",
        }
        if any(key not in allowed_headers for key in headers if isinstance(key, bytes)):
            raise ValueError("Unsupported CouchDB request header")
        if admin_index and b"expect" in headers:
            raise ValueError("Index requests cannot use Expect")
    if lease["provider"] == "hugegraph":
        from .hugegraph_access import authorize

        authorize(request.method, request.target, lease)
        allowed_headers = {
            b"host",
            b"authorization",
            b"content-type",
            b"accept",
            b"content-length",
            b"transfer-encoding",
            b"user-agent",
            b"accept-encoding",
            b"connection",
        }
        if any(key not in allowed_headers for key in headers):
            raise ValueError("Unsupported HugeGraph request header")
    if authorized is not None:
        authorized(headers.get("_session"))
    # Forbid pipelining/reuse. Every subsequent request must open its own socket
    # and pass fresh catalog/identity checks. Never proxy WebSocket or CONNECT.
    if request.method not in {
        b"GET",
        b"HEAD",
        b"POST",
        b"PUT",
        b"PATCH",
        b"DELETE",
        b"OPTIONS",
    }:
        raise ValueError("Unsupported HTTP method")
    hops = {b"connection", b"keep-alive", b"te", b"trailer", b"expect"}
    named = {
        value.strip().lower() for value in headers.get(b"connection", b"").split(b",")
    }
    if named - {b"", b"close", b"keep-alive"}:
        raise ValueError("Unsupported connection options")
    index_body = None
    if admin_index:
        index_body = bytearray()
        while True:
            event = await _event(front, reader)
            if isinstance(event, h11.Data):
                index_body.extend(event.data)
                if len(index_body) > 16384:
                    raise ValueError("CouchDB index definition is too large")
            elif isinstance(event, h11.EndOfMessage):
                break
            else:
                raise TypeError("Unexpected index request event")
        if request.method == b"POST":
            validate_index(index_body)
        elif index_body:
            raise ValueError("Index deletion has no request body")
    excluded = (
        hops
        | ({b"host"} if lease["provider"] in {"couchdb", "hugegraph"} else set())
        | (
            {b"authorization", b"content-type", b"content-length", b"transfer-encoding"}
            if admin_index
            else set()
        )
    )
    forwarded = [(k, v) for k, v in request.headers if k not in excluded]
    if lease["provider"] in {"couchdb", "hugegraph"}:
        # A client-chosen Host must not alter backend routing.
        forwarded.append((b"host", f"{backend[0]}:{backend[1]}".encode()))
    if admin_index:
        import os

        from .couchdb import basic

        forwarded.extend(
            [
                (
                    b"authorization",
                    basic(
                        os.environ.get("COUCHDB_ADMIN_USER", "platform_admin"),
                        os.environ["COUCHDB_ADMIN_PASSWORD"],
                    ).encode(),
                ),
                (b"content-type", b"application/json"),
                (b"content-length", str(len(index_body)).encode()),
            ]
        )
    forwarded.append((b"connection", b"close"))
    remote_reader, remote_writer = await asyncio.wait_for(
        asyncio.open_connection(*backend, ssl=tls), 3
    )
    remote = h11.Connection(h11.CLIENT, max_incomplete_event_size=32768)
    try:
        remote_writer.write(
            remote.send(
                h11.Request(
                    method=request.method, target=request.target, headers=forwarded
                )
            )
        )
        await remote_writer.drain()
        if headers.get(b"expect", b"").lower() == b"100-continue":
            writer.write(
                front.send(h11.InformationalResponse(status_code=100, headers=[]))
            )
            await writer.drain()
        elif b"expect" in headers:
            raise ValueError("Unsupported expectation")

        async def upload():
            if admin_index:
                if index_body:
                    remote_writer.write(remote.send(h11.Data(data=bytes(index_body))))
                remote_writer.write(remote.send(h11.EndOfMessage()))
                await remote_writer.drain()
                return
            while True:
                event = await _event(front, reader)
                if isinstance(event, h11.Data):
                    remote_writer.write(remote.send(event))
                    await remote_writer.drain()
                elif isinstance(event, h11.EndOfMessage):
                    remote_writer.write(remote.send(event))
                    await remote_writer.drain()
                    return
                else:
                    raise TypeError("Unexpected request event")

        async def download():
            while True:
                event = await _event(remote, remote_reader)
                if isinstance(event, h11.Response):
                    safe = [
                        (k, v)
                        for k, v in event.headers
                        if k
                        not in (
                            {b"connection", b"keep-alive", b"set-cookie", b"location"}
                            if admin_index
                            else {b"connection", b"keep-alive"}
                        )
                    ]
                    event = h11.Response(
                        status_code=event.status_code,
                        headers=[*safe, (b"connection", b"close")],
                    )
                if isinstance(
                    event,
                    (
                        h11.Response,
                        h11.InformationalResponse,
                        h11.Data,
                        h11.EndOfMessage,
                    ),
                ):
                    writer.write(front.send(event))
                    await writer.drain()
                    if isinstance(event, h11.EndOfMessage):
                        return
                else:
                    raise TypeError("Unexpected response event")

        sender, receiver = (
            asyncio.create_task(upload()),
            asyncio.create_task(download()),
        )
        try:
            done, _ = await asyncio.wait(
                [sender, receiver], return_when=asyncio.FIRST_COMPLETED
            )
            if sender in done:
                sender.result()
            await receiver
        finally:
            sender.cancel()
            receiver.cancel()
            await asyncio.gather(sender, receiver, return_exceptions=True)
    finally:
        remote_writer.close()
        with contextlib.suppress(Exception):
            await remote_writer.wait_closed()
