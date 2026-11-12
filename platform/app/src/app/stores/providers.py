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
    if name != "s3":
        raise ProviderUnavailable("Only PostgreSQL and S3 are supported")
    selected = {
        value.strip()
        for value in os.environ.get("STORE_ENABLED_PROVIDERS", "postgresql").split(",")
    }
    if name not in selected:
        raise ProviderUnavailable("Provider is not selected by the operator")
    try:
        import ipaddress

        ipaddress.IPv4Address(os.environ["RUSTFS_IP"])
        if (
            len(os.environ["RUSTFS_ACCESS_KEY"]) < 20
            or len(os.environ["RUSTFS_SECRET_KEY"]) < 32
        ):
            raise ValueError("Unconfigured administration credentials")
        from .s3 import S3

        return S3()
    except (KeyError, ValueError, OSError, StoreError):
        raise ProviderUnavailable(
            "Selected provider configuration is incomplete"
        ) from None


def capabilities(name):
    if name not in {
        "postgresql",
        "s3",
        "opensearch",
        "qdrant",
        "neo4j",
        "couchdb",
        "hugegraph",
    }:
        raise ProviderUnavailable("Unknown provider")
    full = name == "neo4j"
    return {
        "access_model": "full-instance" if full else "named-resource",
        "supported_modes": ["read-write"] if full else ["read-only", "read-write"],
        "native_account_management": full,
        "dedicated_instance": full,
        **({"max_resources_per_project": 1} if full else {}),
    }


def quota_enforcement(name):
    """Report historical rows without reopening a removed native provider."""
    if name in {"postgresql", "s3"}:
        return get(name).quota_enforcement
    capabilities(name)
    return "advisory"


def availability():
    result = []
    for name in ("postgresql", "s3"):
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
    if provider not in {"postgresql", "s3"}:
        raise ProviderUnavailable("Only PostgreSQL and S3 are supported")
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
    else:
        address = str(
            ipaddress.ip_address(os.environ.get("STORE_RELAY_IP", "172.30.80.15"))
        )
        endpoint = f"http://{address}:{credential['relay_port']}"
        fields["AWS_ENDPOINT_URL_S3"] = endpoint
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
