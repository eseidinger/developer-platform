"""Operator-owned provider registry. Never infer an enabled service from a request."""

import json
import os

from .postgres import Postgres
from .s3 import StoreError


class ProviderUnavailable(Exception):
    pass


def get(name):
    if name == "postgresql":
        return Postgres()
    selected = {
        value.strip()
        for value in os.environ.get("STORE_ENABLED_PROVIDERS", "postgresql").split(",")
    }
    if name not in selected:
        raise ProviderUnavailable("Provider is not selected by the operator")
    if name == "neo4j":
        if len(os.environ.get("NEO4J_CONTROLLER_KEY", "")) < 32:
            raise ProviderUnavailable("Dedicated instance controller is not configured")
        from .neo4j import Neo4j

        try:
            return Neo4j()
        except (ValueError, KeyError):
            raise ProviderUnavailable(
                "Dedicated instance controller configuration is invalid"
            ) from None
    definitions = {
        "s3": ("RUSTFS_IP", ("RUSTFS_ACCESS_KEY", "RUSTFS_SECRET_KEY")),
        "opensearch": ("OPENSEARCH_IP", ("OPENSEARCH_ADMIN_PASSWORD",)),
        "qdrant": ("QDRANT_IP", ("QDRANT_API_KEY",)),
    }
    if name not in definitions:
        raise ProviderUnavailable(
            "Provider cannot satisfy the configured resource contract"
        )
    try:
        import ipaddress

        address, secrets = definitions[name]
        ipaddress.IPv4Address(os.environ[address])
        if any(
            len(os.environ[key]) < (20 if key == "RUSTFS_ACCESS_KEY" else 32)
            for key in secrets
        ):
            raise ValueError("Unconfigured administration credentials")
        if name == "s3":
            from .s3 import S3

            return S3()
        if name == "qdrant":
            from .qdrant import Qdrant

            return Qdrant()
        from .opensearch import OpenSearch

        return OpenSearch()
    except (KeyError, ValueError, OSError, StoreError):
        raise ProviderUnavailable(
            "Selected provider configuration is incomplete"
        ) from None


def capabilities(name):
    if name not in {"postgresql", "s3", "opensearch", "qdrant", "neo4j"}:
        raise ProviderUnavailable("Unknown provider")
    full = name == "neo4j"
    return {
        "access_model": "full-instance" if full else "named-resource",
        "supported_modes": ["read-write"] if full else ["read-only", "read-write"],
        "native_account_management": full,
        "dedicated_instance": full,
        **({"max_resources_per_project": 1} if full else {}),
    }


def availability():
    result = []
    for name in ("postgresql", "s3", "opensearch", "qdrant", "neo4j"):
        try:
            get(name)
            budget(name)
            enabled = True
        except ProviderUnavailable:
            enabled = False
        result.append(
            {"id": name, "enabled": enabled, "capabilities": capabilities(name)}
        )
    return result


def budget(name):
    try:
        values = json.loads(
            os.environ.get("STORE_CAPACITY_BYTES") or '{"postgresql":17179869184}'
        )
        amount = values.get(name)
    except (ValueError, AttributeError, TypeError):
        raise ProviderUnavailable(
            "Operator store capacity allocation is invalid"
        ) from None
    if type(amount) is not int or amount <= 0:
        raise ProviderUnavailable("Operator store capacity allocation is unavailable")
    return amount


def check_capacity(conn, provider, quota, resource_id=None):
    if provider == "neo4j" and resource_id is None:
        try:
            limit = int(os.environ.get("NEO4J_MAX_INSTANCES", "4"))
        except ValueError:
            raise ProviderUnavailable(
                "Dedicated instance allocation is invalid"
            ) from None
        if not 1 <= limit <= 64:
            raise ProviderUnavailable("Dedicated instance allocation is invalid")
        if (
            conn.execute(
                "SELECT count(*) FROM store_resources WHERE provider='neo4j' AND state<>'purged'"
            ).fetchone()[0]
            >= limit
        ):
            from .catalog import Conflict

            raise Conflict(
                "Operator dedicated instance allocation exhausted, including retained resources"
            )
    used = conn.execute(
        """SELECT COALESCE(sum(GREATEST(quota_bytes,COALESCE(used_bytes,0))),0) FROM store_resources
        WHERE provider=%s AND state<>'purged' AND (%s::uuid IS NULL OR resource_id<>%s)""",
        (provider, resource_id, resource_id),
    ).fetchone()[0]
    if resource_id is not None:
        measured = conn.execute(
            "SELECT used_bytes FROM store_resources WHERE resource_id=%s",
            (resource_id,),
        ).fetchone()
        quota = max(quota, (measured[0] if measured else 0) or 0)
    if used + quota > budget(provider):
        from .catalog import Conflict

        raise Conflict("Requested allocation exceeds operator-owned store capacity")


def connection(resource, credential):
    import ipaddress

    fields = get(resource["provider"]).credentials(resource, credential)
    if resource["provider"] == "postgresql":
        fields.update(
            {
                "PGHOST": str(
                    ipaddress.ip_address(
                        os.environ.get("STORE_RELAY_IP", "172.30.80.15")
                    )
                ),
                "PGPORT": str(credential["relay_port"]),
                "PGSSLMODE": "disable",
            }
        )
    elif resource["provider"] == "neo4j":
        address = str(
            ipaddress.ip_address(os.environ.get("STORE_RELAY_IP", "172.30.80.15"))
        )
        fields["NEO4J_URI"] = f"bolt://{address}:{credential['relay_port']}"
    else:
        address = str(
            ipaddress.ip_address(os.environ.get("STORE_RELAY_IP", "172.30.80.15"))
        )
        endpoint = f"http://{address}:{credential['relay_port']}"
        key = {
            "s3": "AWS_ENDPOINT_URL_S3",
            "qdrant": "QDRANT_URL",
            "opensearch": "OPENSEARCH_URL",
        }[resource["provider"]]
        fields[key] = endpoint
    return fields


def console_url(provider):
    if (
        provider == "postgresql"
        and os.environ.get("STORE_CONSOLE_POSTGRES_ENABLED") == "true"
    ):
        return "/store-console/postgresql/"
    from .console import enabled

    if enabled(provider):
        return "/store-access"
    return None


def ssh_connection(credential):
    """Advertise only an operator-selected reachable bastion, never assume public DNS."""
    import ipaddress
    import re

    host = os.environ.get("STORE_SSH_HOST", "")
    if not host:
        return None
    try:
        address = ipaddress.ip_address(host)
        if address.is_unspecified:
            raise ProviderUnavailable("A reachable private access host is required")
    except ValueError:
        if len(host) > 253 or not re.fullmatch(
            r"[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?", host
        ):
            raise ProviderUnavailable("Invalid private access configuration") from None
    try:
        port = int(os.environ.get("STORE_SSH_PORT", "2222"))
    except ValueError:
        raise ProviderUnavailable("Invalid private access configuration") from None
    if not 1024 <= port <= 65535:
        raise ProviderUnavailable("Invalid private access configuration")
    return {
        "user": "platform-db",
        "host": host,
        "port": port,
        "destination": str(
            ipaddress.ip_address(os.environ.get("STORE_RELAY_IP", "172.30.80.15"))
        ),
        "destination_port": credential["relay_port"],
    }
