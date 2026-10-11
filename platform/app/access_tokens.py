"""Access-token validation at the hosted-application boundary."""
import re

import jwt
from fastapi import HTTPException
from jwt import PyJWKClient
from jwt.exceptions import PyJWTError


class TokenVerifier:
    def __init__(self, issuer, audience, jwks_url):
        self.issuer, self.audience = issuer, audience
        self.jwks = PyJWKClient(jwks_url, cache_jwk_set=True, lifespan=300, timeout=5)

    def verify(self, token):
        try:
            if not isinstance(token, str) or not 1 <= len(token) <= 16384:
                raise ValueError("Invalid token")
            key = self.jwks.get_signing_key_from_jwt(token)
            claims = jwt.decode(token, key.key, algorithms=["RS256"], issuer=self.issuer, audience=self.audience,
                                options={"require": ["iss", "sub", "aud", "iat", "exp", "azp", "typ"]})
            aud = claims["aud"]
            if aud != self.audience and aud != [self.audience]:
                raise ValueError("Unexpected audience")
            if claims["typ"] != "Bearer" or not 0 < claims["exp"] - claims["iat"] <= 300:
                raise ValueError("Expected a bounded access token")
            for name in ("sub", "azp", "iss"):
                if not isinstance(claims[name], str) or not claims[name] or any(ord(c) < 32 or ord(c) > 126 for c in claims[name]):
                    raise ValueError("Invalid identity")
            groups = claims.get("groups", [])
            if groups is None:
                groups = []
            if not isinstance(groups, list) or len(groups) > 100 or any(
                not isinstance(g, str) or not re.fullmatch(r"grp_[0-9a-f]{32}", g) for g in groups):
                raise ValueError("Invalid group context")
            claims["groups"] = sorted(set(groups))
            return claims
        except (PyJWTError, ValueError, TypeError, KeyError, OSError):
            raise HTTPException(401, "Invalid application access token", headers={"WWW-Authenticate": "Bearer"}) from None
