"""HTTP and OIDC client boundary for deployment credentials."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
from pydantic import ValidationError

from .config import DeploymentCredentialAuth, RuntimeConfig, authentication_source
from .errors import ApiError, safe_error_body
from .models import OperationAccepted, OperationStatus, TokenResponse


class PlatformClient:
    def __init__(self, config: RuntimeConfig, http_client: httpx.Client | None = None):
        self.config = config
        self._http = http_client or httpx.Client(timeout=httpx.Timeout(30.0), verify=config.ca_bundle or True)
        self._owns_http = http_client is None

    def close(self) -> None:
        if self._owns_http:
            self._http.close()

    def access_token(self) -> str:
        source = authentication_source(self.config)
        if source == "access-token-environment":
            assert self.config.access_token_auth is not None
            return self.config.access_token_auth.access_token
        assert self.config.deployment_credential_auth is not None
        return self._client_credentials_token(self.config.deployment_credential_auth)

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
        if not status_url.startswith("/") or status_url.startswith("//"):
            raise RuntimeError("The platform returned an unsafe operation status URL.")
        response = self._request("GET", status_url, headers={"Authorization": f"Bearer {access_token}"})
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
        return token.access_token

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            response = self._http.request(method, self.config.api_url + path, **kwargs)
        except httpx.HTTPError as error:
            raise RuntimeError("Unable to reach the Platform API.") from error
        self._raise_for_error(response)
        return response

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
        if status.state == "succeeded" and status.readiness.state == "ready":
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
