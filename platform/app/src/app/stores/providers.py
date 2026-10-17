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
    values = json.loads(os.environ.get("STORE_CAPACITY_BYTES", '{"postgresql":17179869184}'))
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
