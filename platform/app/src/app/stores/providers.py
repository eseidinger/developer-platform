"""Operator-owned provider registry. Never infer an enabled service from a request."""
import json
import os
from .postgres import Postgres


class ProviderUnavailable(Exception):
    pass


def get(name):
    if name == "postgresql":
        return Postgres()
    raise ProviderUnavailable("Provider has not been configured and verified")


def budget(name):
    values = json.loads((os.environ.get("STORE_CAPACITY_BYTES") or '{"postgresql":17179869184}'))
    amount = values.get(name)
    if type(amount) is not int or amount <= 0:
        raise ProviderUnavailable("Operator store capacity allocation is unavailable")
    return amount


def check_capacity(conn, provider, quota, resource_id=None):
    used = conn.execute("""SELECT COALESCE(sum(quota_bytes),0) FROM store_resources
        WHERE provider=%s AND state<>'purged' AND (%s::uuid IS NULL OR resource_id<>%s)""",
        (provider, resource_id, resource_id)).fetchone()[0]
    if used + quota > budget(provider):
        from .catalog import Conflict
        raise Conflict("Requested allocation exceeds operator-owned store capacity")


def connection(resource, credential):
    import ipaddress
    fields = get(resource["provider"]).credentials(resource, credential)
    if resource["provider"] == "postgresql":
        fields.update({"PGHOST": str(ipaddress.ip_address(os.environ.get("STORE_RELAY_IP", "172.30.80.15"))),
                       "PGPORT": str(credential["relay_port"]), "PGSSLMODE": "disable"})
    return fields


def console_url(provider):
    if provider == "postgresql" and os.environ.get("STORE_CONSOLE_POSTGRES_ENABLED") == "true":
        return "/store-console/postgresql/"
    return None
