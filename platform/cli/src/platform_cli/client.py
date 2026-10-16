"""HTTP and OIDC client boundary for deployment credentials."""

from __future__ import annotations

from collections.abc import Callable
import time
import sys
from typing import Any
from urllib.parse import urlsplit

import httpx
from pydantic import ValidationError

from .config import DeploymentCredentialAuth, RuntimeConfig, authentication_source
from .errors import ApiError, safe_error_body
from .models import OperationAccepted, OperationStatus, TokenResponse
from .authentication import HumanAuthentication
from .profiles import SessionStore


class PlatformClient:
    def __init__(self, config: RuntimeConfig, http_client: httpx.Client | None = None):
        self.config = config
        self._http = http_client or httpx.Client(timeout=httpx.Timeout(30.0),
            verify=False if config.insecure else config.ca_bundle or True, follow_redirects=False)
        self._owns_http = http_client is None
        self._token: str | None = None
        self._expires_at = 0.0
        self.debug = False

    def close(self) -> None:
        if self._owns_http:
            self._http.close()

    def human_authentication(self) -> HumanAuthentication:
        if self.config.profile is None or self.config.profile_name is None:
            raise ApiError(401, "Create and select a profile before human login.")
        return HumanAuthentication(self.config.profile,
            SessionStore(self.config.profile_name, self.config.profile), self._http)

    def access_token(self, force: bool = False) -> str:
        source = authentication_source(self.config)
        if source == "access-token-environment":
            assert self.config.access_token_auth is not None
            return self.config.access_token_auth.access_token
        if not force and self._token and time.monotonic() < self._expires_at:
            return self._token
        if source == "human-profile-session":
            tokens = self.human_authentication().refresh()
            self._remember(tokens)
            return tokens.access_token
        assert self.config.deployment_credential_auth is not None
        return self._client_credentials_token(self.config.deployment_credential_auth)

    def _remember(self, tokens: TokenResponse) -> None:
        self._token = tokens.access_token
        self._expires_at = time.monotonic() + max(0, tokens.expires_in - 10)

    def request_json(self, method: str, path: str, *, body=None, params=None, headers=None) -> tuple[Any, str | None]:
        request_headers = {"Authorization": "Bearer " + self.access_token(), **(headers or {})}
        try:
            response = self._request(method, path, headers=request_headers, params=params, **({"json": body} if body is not None else {}))
        except ApiError as error:
            if error.status_code != 401 or method != "GET" or self.config.access_token_auth is not None:
                raise
            request_headers["Authorization"] = "Bearer " + self.access_token(force=True)
            response = self._request(method, path, headers=request_headers, params=params)
        if response.status_code == 204:
            return None, response.headers.get("etag")
        try:
            return response.json(), response.headers.get("etag")
        except ValueError:
            raise ApiError(503, "The platform returned invalid JSON.") from None

    def request_text(self, method: str, path: str, *, params=None) -> str:
        """Read a bounded public text response, including CSV audit exports."""
        headers = {"Authorization": "Bearer " + self.access_token()}
        try:
            response = self._request(method, path, headers=headers, params=params)
        except ApiError as error:
            if error.status_code != 401 or method != "GET" or self.config.access_token_auth is not None:
                raise
            headers["Authorization"] = "Bearer " + self.access_token(force=True)
            response = self._request(method, path, headers=headers, params=params)
        return response.text

    def deploy(self, project: str, body: dict[str, Any], access_token: str, if_match: str | None = None) -> OperationAccepted:
        headers = {"Authorization": f"Bearer {access_token}"}
        if if_match is not None:
            headers["If-Match"] = if_match
        response = self._request("PUT", f"/projects/{project}", headers=headers, json=body)
        try:
            return OperationAccepted.model_validate(response.json())
        except (ValidationError, ValueError) as error:
            raise RuntimeError("The platform returned an invalid deployment operation.") from error

    def operation(self, status_url: str, access_token: str) -> OperationStatus:
        try:
            response = self._request("GET", status_url, headers={"Authorization": f"Bearer {access_token}"})
        except ApiError as error:
            if error.status_code != 401 or self.config.access_token_auth is not None:
                raise
            response = self._request("GET", status_url, headers={"Authorization": "Bearer " + self.access_token(force=True)})
        try:
            return OperationStatus.model_validate(response.json())
        except (ValidationError, ValueError) as error:
            raise RuntimeError("The platform returned an invalid operation status.") from error

    def _client_credentials_token(self, credential: DeploymentCredentialAuth) -> str:
        try:
            response = self._http.post(
                credential.token_endpoint,
                data={
                    "grant_type": "client_credentials",
                    "client_id": credential.client_id,
                    "client_secret": credential.client_secret,
                },
                follow_redirects=False,
            )
        except httpx.HTTPError as error:
            raise RuntimeError("Unable to reach the OIDC token endpoint.") from error
        self._raise_for_error(response)
        try:
            token = TokenResponse.model_validate(response.json())
        except (ValidationError, ValueError) as error:
            raise RuntimeError("The OIDC provider returned an invalid token response.") from error
        if token.token_type.casefold() != "bearer":
            raise RuntimeError("The OIDC provider returned an unsupported token type.")
        self._remember(token)
        return token.access_token

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        parsed = urlsplit(path)
        if not path.startswith("/") or path.startswith("//") or parsed.scheme or parsed.netloc or "\\" in path or parsed.fragment or parsed.query:
            raise ApiError(503, "The platform returned an unsafe API path.")
        attempts = 3 if method == "GET" else 1
        if (method == "POST" and len(parsed.path.split("/")) == 5
                and parsed.path.startswith("/projects/") and parsed.path.endswith("/ai/runs")):
            # Synchronous AI investigations have a 90-second server budget.
            kwargs["timeout"] = httpx.Timeout(120.0, connect=5.0)
        for attempt in range(attempts):
            started = time.monotonic()
            try:
                with self._http.stream(method, self.config.api_url + path, follow_redirects=False, **kwargs) as streamed:
                    content = bytearray()
                    for chunk in streamed.iter_bytes():
                        content.extend(chunk)
                        if len(content) > 8 * 1024 * 1024:
                            raise ApiError(503, "The API response exceeded the size limit.")
                    headers = {key: value for key, value in streamed.headers.items()
                               if key.lower() not in {"content-encoding", "content-length"}}
                    response = httpx.Response(streamed.status_code, headers=headers,
                                              content=bytes(content), request=streamed.request)
            except httpx.HTTPError:
                if attempt + 1 < attempts:
                    time.sleep(0.25 * (2 ** attempt))
                    continue
                raise ApiError(503, "Unable to reach the Platform API.") from None
            if response.status_code in {429, 502, 503, 504} and attempt + 1 < attempts:
                try:
                    delay = min(30, max(0, float(response.headers.get("retry-after", 0.25 * (2 ** attempt)))))
                except ValueError:
                    delay = 0.25 * (2 ** attempt)
                time.sleep(delay)
                continue
            if self.debug:
                request_id = response.headers.get("x-request-id") or response.headers.get("x-correlation-id") or "-"
                print(f"{method} {parsed.path} -> {response.status_code} in {time.monotonic()-started:.2f}s (request {request_id})",
                      file=sys.stderr)
            self._raise_for_error(response)
            return response
        raise ApiError(503, "Unable to reach the Platform API.")

    @staticmethod
    def _raise_for_error(response: httpx.Response) -> None:
        if response.is_success:
            return
        try:
            detail, code = safe_error_body(response.json())
        except ValueError:
            detail, code = "The platform returned an error without a safe detail.", None
        request_id = response.headers.get("x-request-id") or response.headers.get("x-correlation-id")
        raise ApiError(response.status_code, detail, code, request_id)


def wait_for_operation(
    client: PlatformClient,
    accepted: OperationAccepted,
    access_token: str,
    timeout_seconds: float,
    interval_seconds: float,
    clock: Callable[[], float],
    sleep: Callable[[float], None],
    on_update: Callable[[OperationStatus], None],
) -> OperationStatus:
    """Wait for apply success and live readiness without cancelling a durable operation."""
    deadline = clock() + timeout_seconds
    while True:
        status = client.operation(accepted.status_url, access_token)
        on_update(status)
        if status.state in {"failed", "cancelled"}:
            raise OperationFailed(status)
        if status.state == "succeeded" and status.readiness.state in {"ready", "not_applicable"}:
            return status
        if clock() >= deadline:
            raise OperationTimeout(accepted.operation_id)
        sleep(interval_seconds)


class OperationFailed(RuntimeError):
    def __init__(self, status: OperationStatus):
        super().__init__(status.error_code or "The platform operation failed.")
        self.status = status


class OperationTimeout(TimeoutError):
    def __init__(self, operation_id: str):
        super().__init__(f"Timed out while waiting for operation {operation_id}.")
        self.operation_id = operation_id
