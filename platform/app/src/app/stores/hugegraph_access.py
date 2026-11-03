"""Allow only graph data and schema operations for one HugeGraph lease.

HugeGraph 1.7 graph-scoped READ grants still allow graph enumeration and reads
from other graphs. This route boundary is therefore required for every client,
including writers. Query languages, graph management and auth APIs stay closed.
"""

import re
from urllib.parse import unquote, urlsplit

from . import catalog

SCHEMA_COLLECTIONS = {"propertykeys", "vertexlabels", "edgelabels", "indexlabels"}
DATA_COLLECTIONS = {"vertices", "edges"}
READ_METHODS = {b"GET", b"HEAD"}
WRITE_METHODS = {b"POST", b"PUT", b"PATCH", b"DELETE"}


def authorize(method, target, lease):
    """Reject ambiguous paths before they reach HugeGraph's URL parser."""
    if not isinstance(method, bytes) or not isinstance(target, bytes):
        raise TypeError("Invalid HugeGraph request")
    try:
        text = target.decode("ascii")
        parsed = urlsplit(text)
    except UnicodeDecodeError:
        raise ValueError("Invalid HugeGraph target") from None
    if (
        parsed.scheme
        or parsed.netloc
        or parsed.fragment
        or not parsed.path.startswith("/")
    ):
        raise ValueError("Origin-form HugeGraph target required")
    if not re.fullmatch(r"(?:[^%]|%[0-9A-Fa-f]{2})*", parsed.path):
        raise ValueError("Invalid HugeGraph encoding")
    if re.search(r"%(?:2f|5c|25|00)", parsed.path, re.IGNORECASE):
        raise ValueError("Ambiguous HugeGraph path")
    path = unquote(parsed.path)
    if (
        "\\" in path
        or "//" in path
        or any(part in {"", ".", ".."} for part in path.removeprefix("/").split("/"))
    ):
        raise ValueError("Ambiguous HugeGraph path")

    parts = path.split("/")[1:]
    graph = catalog.identifier(lease["resource_id"])
    if len(parts) < 4 or parts[:2] != ["graphs", graph]:
        raise ValueError("HugeGraph graph is outside the lease")
    section, collection = parts[2:4]
    if section == "graph" and collection in DATA_COLLECTIONS:
        if len(parts) > 5:
            raise ValueError("Unsupported HugeGraph data path")
    elif section == "schema" and collection in SCHEMA_COLLECTIONS:
        if len(parts) > 5:
            raise ValueError("Unsupported HugeGraph schema path")
    else:
        raise ValueError("HugeGraph administration is unavailable")
    if len(parts) == 5 and not parts[4]:
        raise ValueError("Invalid HugeGraph object identifier")
    if method in READ_METHODS:
        return
    if method in WRITE_METHODS and lease["mode"] == "read-write":
        return
    raise ValueError("HugeGraph operation is outside this lease")
