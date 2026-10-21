"""OIDC Device Authorization with PKCE and keyring-backed refresh sessions."""

from __future__ import annotations

import base64
import hashlib
import secrets
import time
from urllib.parse import urlsplit

import httpx
from pydantic import ValidationError

from .errors import ApiError
from .models import TokenResponse
from .profiles import Profile, SessionStore, validate_url


class HumanAuthentication:
    def __init__(self, profile: Profile, sessions: SessionStore, http: httpx.Client):
        self.profile, self.sessions, self.http = profile, sessions, http
        self._metadata = None

    def metadata(self) -> dict:
        if self._metadata is None:
            response = self.http.get(
                self.profile.issuer.rstrip("/") + "/.well-known/openid-configuration",
                follow_redirects=False,
            )
            if not response.is_success:
                raise ApiError(503, "Unable to discover the identity provider.")
            try:
                metadata = response.json()
                if metadata["issuer"].rstrip("/") != self.profile.issuer.rstrip("/"):
                    raise ValueError()
                for field in (
                    "token_endpoint",
                    "device_authorization_endpoint",
                    "userinfo_endpoint",
                ):
                    endpoint = validate_url(metadata[field])
                    issuer_url = urlsplit(self.profile.issuer)
                    if (
                        urlsplit(endpoint).scheme != issuer_url.scheme
                        or urlsplit(endpoint).netloc != issuer_url.netloc
                    ):
                        raise ValueError()
                self._metadata = metadata
            except (KeyError, TypeError, ValueError):
                raise ApiError(
                    503, "The identity provider returned invalid discovery metadata."
                ) from None
        return self._metadata

    def tokens(self, response: httpx.Response) -> TokenResponse:
        if not response.is_success:
            raise ApiError(401, "Human authentication failed; sign in again.")
        try:
            result = TokenResponse.model_validate(response.json())
            if result.token_type.lower() != "bearer":
                raise ValueError()
            return result
        except (ValueError, ValidationError):
            raise ApiError(
                503, "The identity provider returned an invalid token response."
            ) from None

    def subject(self, token: str) -> str:
        response = self.http.get(
            self.metadata()["userinfo_endpoint"],
            headers={"Authorization": "Bearer " + token},
            follow_redirects=False,
        )
        try:
            subject = response.json()["sub"]
            if not response.is_success or not isinstance(subject, str) or not subject:
                raise ValueError()
            return subject
        except (ValueError, KeyError, TypeError):
            raise ApiError(
                401, "Unable to verify the human session identity."
            ) from None

    def login(
        self, notify, timeout: float = 300, clock=time.monotonic, sleep=time.sleep
    ) -> str:
        self.sessions.backend()  # Fail before initiating a flow we cannot persist.
        metadata = self.metadata()
        verifier = secrets.token_urlsafe(64)
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .rstrip(b"=")
            .decode()
        )
        response = self.http.post(
            metadata["device_authorization_endpoint"],
            data={
                "client_id": self.profile.client_id,
                "scope": "openid",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            },
            follow_redirects=False,
        )
        try:
            device = response.json()
            if not response.is_success or not all(
                isinstance(device[k], str) and device[k]
                for k in ("device_code", "user_code", "verification_uri")
            ):
                raise ValueError()
            validate_url(device["verification_uri"])
            interval = max(1.0, float(device.get("interval", 5)))
            deadline = clock() + min(timeout, float(device["expires_in"]))
        except (KeyError, TypeError, ValueError):
            raise ApiError(
                503,
                "The identity provider returned an invalid device authorization response.",
            ) from None
        notify(device["verification_uri"], device["user_code"])
        while clock() < deadline:
            sleep(min(interval, max(0, deadline - clock())))
            if clock() >= deadline:
                break
            response = self.http.post(
                metadata["token_endpoint"],
                data={
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    "client_id": self.profile.client_id,
                    "device_code": device["device_code"],
                    "code_verifier": verifier,
                },
                follow_redirects=False,
            )
            try:
                error = response.json().get("error")
            except (ValueError, AttributeError):
                raise ApiError(
                    503, "Invalid device authorization polling response."
                ) from None
            if error == "authorization_pending":
                continue
            if error == "slow_down":
                interval += 5
                continue
            tokens = self.tokens(response)
            if not tokens.refresh_token:
                raise ApiError(
                    401,
                    "The provider did not issue a refresh token; use an externally supplied access token.",
                )
            subject = self.subject(tokens.access_token)
            self.sessions.set(subject, tokens.refresh_token)
            return subject
        raise ApiError(401, "Device authorization expired; sign in again.")

    def refresh(self) -> TokenResponse:
        session = self.sessions.get()
        if not session:
            raise ApiError(401, "No human session; run devplat auth login.")
        response = self.http.post(
            self.metadata()["token_endpoint"],
            data={
                "grant_type": "refresh_token",
                "client_id": self.profile.client_id,
                "refresh_token": session["refresh_token"],
            },
            follow_redirects=False,
        )
        if response.status_code in {400, 401}:
            self.sessions.delete()
        tokens = self.tokens(response)
        if self.subject(tokens.access_token) != session["subject"]:
            self.sessions.delete()
            raise ApiError(401, "Session identity changed; sign in again.")
        if tokens.refresh_token:
            self.sessions.set(session["subject"], tokens.refresh_token)
        return tokens

    def logout(self) -> None:
        session = self.sessions.get()
        self.sessions.delete()
        if session:
            endpoint = self.metadata().get("revocation_endpoint")
            if endpoint:
                endpoint = validate_url(endpoint)
                if (
                    urlsplit(endpoint).netloc != urlsplit(self.profile.issuer).netloc
                    or urlsplit(endpoint).scheme != urlsplit(self.profile.issuer).scheme
                ):
                    raise ApiError(
                        503,
                        "Local session cleared; unsafe provider revocation endpoint rejected.",
                    )
                response = self.http.post(
                    endpoint,
                    data={
                        "client_id": self.profile.client_id,
                        "token": session["refresh_token"],
                        "token_type_hint": "refresh_token",
                    },
                    follow_redirects=False,
                )
                if not response.is_success:
                    raise ApiError(
                        503,
                        "Local session cleared; provider session revocation failed.",
                    )
