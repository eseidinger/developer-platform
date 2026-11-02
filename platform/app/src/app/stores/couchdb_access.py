"""Fail-closed CouchDB HTTP route policy for a single named database."""

import json
import re
from urllib.parse import unquote, urlsplit

from . import catalog

READ_POST = {"_all_docs", "_find", "_explain", "_changes", "_bulk_get"}
READ_GET = READ_POST | {"_index"}


def _unique_object(pairs):
    # The relay must not approve a different interpretation than CouchDB uses.
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate CouchDB index field")
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError("Invalid CouchDB index constant")


def authorize(method, target, lease):
    if not isinstance(method, bytes) or not isinstance(target, bytes):
        raise TypeError("Invalid CouchDB request")
    try:
        parsed = urlsplit(target.decode("ascii"))
        path = parsed.path
    except UnicodeDecodeError:
        raise ValueError("Invalid CouchDB target") from None
    if not re.fullmatch(r"(?:[^%]|%[0-9A-Fa-f]{2})*", path):
        raise ValueError("Invalid CouchDB encoding")
    if re.search(r"%(?:2f|5c|25|00)", path, re.IGNORECASE):
        raise ValueError("Ambiguous CouchDB path")
    path = unquote(path)
    if "\\" in path or "//" in path or any(p in {".", ".."} for p in path.split("/")):
        raise ValueError("Ambiguous CouchDB path")
    prefix = "/" + catalog.identifier(lease["resource_id"])
    if path == prefix:
        if method in {b"GET", b"HEAD"} or (
            method == b"POST" and lease["mode"] == "read-write"
        ):
            return
        raise ValueError("CouchDB operation is not granted")
    if not path.startswith(prefix + "/"):
        raise ValueError("CouchDB database is outside the lease")
    parts = path[len(prefix) + 1 :].split("/")
    first = parts[0]
    if first.startswith("_"):
        if first == "_index" and lease["mode"] == "read-write" and not parsed.query:
            if len(parts) == 1 and method == b"POST":
                return True
            suffix = parts[1:]
            if suffix[:1] == ["_design"]:
                suffix = suffix[1:]
            if (
                method == b"DELETE"
                and len(suffix) == 3
                and suffix[1] == "json"
                and all(
                    re.fullmatch(r"[A-Za-z0-9_-]{1,64}", s)
                    for s in (suffix[0], suffix[2])
                )
            ):
                return True
        if (
            len(parts) == 1
            and first in READ_GET
            and (
                method in {b"GET", b"HEAD"}
                or (method == b"POST" and first in READ_POST)
            )
        ):
            return
        if (
            len(parts) == 1
            and first == "_bulk_docs"
            and method == b"POST"
            and lease["mode"] == "read-write"
        ):
            return
        if (
            len(parts) == 4
            and first == "_design"
            and parts[2] == "_view"
            and method in {b"GET", b"HEAD", b"POST"}
        ):
            return
        raise ValueError("CouchDB administration is unavailable")
    if not first or len(parts) > 2:
        raise ValueError("Unsupported CouchDB document path")
    if method in {b"GET", b"HEAD"}:
        return
    if lease["mode"] == "read-write" and method in {b"PUT", b"DELETE"}:
        return
    raise ValueError("CouchDB operation is not granted")


def validate_index(body):
    if len(body) > 16384:
        raise ValueError("CouchDB index definition is too large")
    try:
        value = json.loads(
            body, object_pairs_hook=_unique_object, parse_constant=_invalid_constant
        )
    except (ValueError, TypeError):
        raise ValueError("Invalid CouchDB index definition") from None
    if not isinstance(value, dict) or set(value) - {"index", "name", "type"}:
        raise ValueError("Unsupported CouchDB index definition")
    name = value.get("name")
    if (
        value.get("type") != "json"
        or not isinstance(name, str)
        or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", name)
    ):
        raise ValueError("Named JSON index required")
    index = value.get("index")
    fields = index.get("fields") if isinstance(index, dict) else None
    if (
        not isinstance(index, dict)
        or set(index) != {"fields"}
        or not isinstance(fields, list)
        or not 1 <= len(fields) <= 16
        or any(
            not isinstance(field, str)
            or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,63}", field)
            for field in fields
        )
    ):
        raise ValueError("Unsupported CouchDB index fields")
