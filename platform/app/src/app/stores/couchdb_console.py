"""Serve the project-scoped CouchDB browser and bind its data requests to a lease."""

from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse, JSONResponse

from . import catalog, couchdb_access
from .couchdb import basic

ASSETS = Path(__file__).resolve().parent / "console_assets" / "couchdb"
FILES = {
    "__platform/couchdb/": "index.html",
    "__platform/couchdb/app.js": "app.js",
    "__platform/couchdb/style.css": "style.css",
}
POLICY = (
    "default-src 'none'; script-src 'self'; style-src 'self'; "
    "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)
HEADERS = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": POLICY,
}


def asset(path, method, row):
    """Only fixed, local assets and this lease's public metadata are served."""
    if method not in {"GET", "HEAD"}:
        raise HTTPException(405)
    if path == "__platform/couchdb/config":
        return JSONResponse(
            {"database": catalog.identifier(row["resource_id"]), "mode": row["mode"]},
            headers=HEADERS,
        )
    name = FILES.get(path)
    if name is None:
        raise HTTPException(404)
    return FileResponse(ASSETS / name, headers=HEADERS)


def authorize(method, target, row):
    """Reject server and foreign database paths before contacting the relay."""
    return couchdb_access.authorize(method, target, row)


def authorization(row):
    """Native credentials stay server-side; the relay checks them again."""
    credential_id = row["credential_id"]
    return basic(
        catalog.login(credential_id), catalog.secret_for(credential_id)
    ).encode()
