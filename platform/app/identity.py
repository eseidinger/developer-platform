"""Provider-neutral OpenID Connect access-token validation."""
from dataclasses import dataclass
import os
from typing import Any

import jwt
from jwt import PyJWKClient
from jwt.exceptions import PyJWTError


class AuthenticationError(Exception):
    """The bearer credential cannot establish a platform principal."""


@dataclass(frozen=True)
class Principal:
    issuer: str
    subject: str
    display_name: str | None = None

    @property
    def audit_id(self) -> str:
        return self.issuer + "|" + self.subject


class OIDCVerifier:
    """Validate an access token without taking authorization facts from its claims."""

    def __init__(self, issuer: str, audience: str, jwks_url: str, algorithms: tuple[str, ...] = ("RS256",)):
        self.issuer = issuer.rstrip("/")
        self.audience = audience
        self.algorithms = algorithms
        self.jwks = PyJWKClient(jwks_url, cache_jwk_set=True, lifespan=300)

    def verify(self, token: str) -> Principal:
        try:
            key = self.jwks.get_signing_key_from_jwt(token)
            claims: dict[str, Any] = jwt.decode(token, key.key, algorithms=list(self.algorithms),
                                                 audience=self.audience, issuer=self.issuer,
                                                 options={"require": ["exp", "iat", "iss", "sub"]})
        except (PyJWTError, ValueError, TypeError) as exc:
            raise AuthenticationError("Invalid OIDC access token") from exc
        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject:
            raise AuthenticationError("OIDC access token has no subject")
        display_name = next((claims.get(name) for name in ("preferred_username", "name", "email")
                             if isinstance(claims.get(name), str) and claims.get(name)), None)
        return Principal(self.issuer, subject, display_name)


def configured_verifier() -> OIDCVerifier:
    issuer = os.environ["OIDC_ISSUER"].rstrip("/")
    audience = os.environ["OIDC_AUDIENCE"]
    jwks_url = os.environ["OIDC_JWKS_URL"]
    if not issuer or not audience or not jwks_url:
        raise RuntimeError("OIDC_ISSUER, OIDC_AUDIENCE, and OIDC_JWKS_URL must be configured")
    return OIDCVerifier(issuer, audience, jwks_url)
