"""Resolve a human-facing username to the stable platform principal."""

import os

from fastapi import HTTPException

from .keycloak_credentials import ProviderError, resolve_username


def resolve(
    issuer: str | None, subject: str | None, username: str | None
) -> tuple[str, str]:
    if username is None:
        if issuer and subject:
            return issuer, subject
        raise HTTPException(
            422, "Provide a preferred username or an issuer and subject"
        )

    if issuer is not None or subject is not None:
        raise HTTPException(
            422, "Use either a preferred username or an issuer and subject"
        )
    username = username.strip()
    if not username:
        raise HTTPException(422, "Preferred username must not be empty")
    try:
        resolved_subject = resolve_username(username)
    except ProviderError as exc:
        raise HTTPException(503, "Identity provider lookup failed") from exc
    if resolved_subject is None:
        raise HTTPException(404, "No unique enabled user has that preferred username")
    return os.environ["OIDC_ISSUER"].rstrip("/"), resolved_subject
