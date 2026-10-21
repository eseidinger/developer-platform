"""Reviewed local pricing; never fetch rates or rewrite historical estimates."""

from dataclasses import dataclass

VERSION = "2026-10-17-v1"
# Existing accepted Standard rates, USD per million tokens. Cached-input rate
# has not been verified: a cached call is unknown until a reviewed rate is added.
RATES = {"openai:gpt-6.1-sol": (2.0, None, 10.0)}


@dataclass(frozen=True)
class Estimate:
    usd: float | None
    complete: bool
    input_tokens: int | None
    cached_tokens: int | None
    output_tokens: int | None
    pricing_version: str = VERSION


def estimate(model, usage, multiplier=1.0):
    usage = usage if isinstance(usage, dict) else {}
    details = usage.get("input_token_details") or {}
    values = (
        usage.get("input_tokens"),
        details.get("cache_read", 0),
        usage.get("output_tokens"),
    )
    if any(type(v) is not int or v < 0 for v in values) or values[1] > values[0]:
        return Estimate(None, False, None, None, None)
    incoming, cached, outgoing = values
    rates = RATES.get(model)
    if rates is None or (cached and rates[1] is None):
        return Estimate(None, False, incoming, cached, outgoing)
    cost = (
        (incoming - cached) * rates[0] + cached * (rates[1] or 0) + outgoing * rates[2]
    )
    return Estimate(
        round(cost * multiplier / 1_000_000, 8), True, incoming, cached, outgoing
    )
