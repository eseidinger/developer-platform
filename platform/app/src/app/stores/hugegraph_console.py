"""Serve a lease-bound HugeGraph graph browser from fixed local assets."""

from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from fastapi import HTTPException
from fastapi.responses import FileResponse, JSONResponse

from . import catalog, hugegraph_access
from .hugegraph import basic

ASSETS = Path(__file__).resolve().parent / "console_assets" / "hugegraph"
FILES = {
    "__platform/hugegraph/": "index.html",
    "__platform/hugegraph/app.js": "app.js",
    "__platform/hugegraph/style.css": "style.css",
}
HEADERS = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": (
        "default-src 'none'; script-src 'self'; style-src 'self'; "
        "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    ),
}


def asset(path, method, row):
    """Only the fixed UI and this lease's public graph name are served."""
    if method not in {"GET", "HEAD"}:
        raise HTTPException(405)
    if path == "__platform/hugegraph/config":
        return JSONResponse(
            {"graph": catalog.identifier(row["resource_id"]), "mode": row["mode"]},
            headers=HEADERS,
        )
    name = FILES.get(path)
    if name is None:
        raise HTTPException(404)
    return FileResponse(ASSETS / name, headers=HEADERS)


def authorize(method, target, row):
    """Apply the graph boundary and cap browser list requests."""
    hugegraph_access.authorize(method, target, row)
    try:
        parsed = urlsplit(target.decode("ascii"))
        query = parse_qs(parsed.query, strict_parsing=True, max_num_fields=4)
    except (UnicodeError, ValueError):
        raise ValueError("Invalid HugeGraph console query") from None
    if parsed.path.endswith(("/graph/vertices", "/graph/edges")) and method in {
        b"GET",
        b"HEAD",
    }:
        if set(query) - {"limit", "page"} or len(query.get("limit", [])) != 1:
            raise ValueError("Bounded graph page required")
        if not query["limit"][0].isdigit() or not 1 <= int(query["limit"][0]) <= 50:
            raise ValueError("Graph page limit exceeded")
        if "page" in query and (
            len(query["page"]) != 1 or len(query["page"][0]) > 1024
        ):
            raise ValueError("Invalid graph page cursor")
    elif query:
        raise ValueError("Unsupported HugeGraph console query")


def authorization(row):
    """Keep the native password on the gateway; the relay checks it again."""
    credential_id = row["credential_id"]
    return basic(
        catalog.login(credential_id), catalog.secret_for(credential_id)
    ).encode()
