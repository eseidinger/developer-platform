"""Non-persistent authentication configuration for the first CLI increment."""

from __future__ import annotations

from dataclasses import dataclass
import os


class ConfigurationError(ValueError):
    """Raised when CLI authentication environment is incomplete or invalid."""


@dataclass(frozen=True)
class AccessTokenAuth:
    access_token: str


@dataclass(frozen=True)
class DeploymentCredentialAuth:
    token_endpoint: str
    client_id: str
    client_secret: str


@dataclass(frozen=True)
class RuntimeConfig:
    api_url: str
    ca_bundle: str | None
    access_token_auth: AccessTokenAuth | None
    deployment_credential_auth: DeploymentCredentialAuth | None


def runtime_config(environment: dict[str, str] | None = None) -> RuntimeConfig:
    """Read the non-persistent command configuration from an environment mapping."""
    env = os.environ if environment is None else environment
    api_url = env.get("PLATFORM_API_URL", "").rstrip("/")
    if not api_url:
        raise ConfigurationError("PLATFORM_API_URL is required")

    token = env.get("PLATFORM_ACCESS_TOKEN")
    if token:
        return RuntimeConfig(
            api_url=api_url,
            ca_bundle=env.get("PLATFORM_CA_BUNDLE") or None,
            access_token_auth=AccessTokenAuth(token),
            deployment_credential_auth=None,
        )

    credential_values = {
        "PLATFORM_TOKEN_ENDPOINT": env.get("PLATFORM_TOKEN_ENDPOINT"),
        "PLATFORM_CLIENT_ID": env.get("PLATFORM_CLIENT_ID"),
        "PLATFORM_CLIENT_SECRET": env.get("PLATFORM_CLIENT_SECRET"),
    }
    present = {name for name, value in credential_values.items() if value}
    if present and len(present) != len(credential_values):
        missing = sorted(set(credential_values) - present)
        raise ConfigurationError("deployment credential environment is incomplete; missing " + ", ".join(missing))

    credential = None
    if len(present) == len(credential_values):
        credential = DeploymentCredentialAuth(
            token_endpoint=credential_values["PLATFORM_TOKEN_ENDPOINT"] or "",
            client_id=credential_values["PLATFORM_CLIENT_ID"] or "",
            client_secret=credential_values["PLATFORM_CLIENT_SECRET"] or "",
        )
    return RuntimeConfig(
        api_url=api_url,
        ca_bundle=env.get("PLATFORM_CA_BUNDLE") or None,
        access_token_auth=None,
        deployment_credential_auth=credential,
    )


def authentication_source(config: RuntimeConfig) -> str:
    if config.access_token_auth is not None:
        return "access-token-environment"
    if config.deployment_credential_auth is not None:
        return "deployment-credential-environment"
    raise ConfigurationError(
        "set PLATFORM_ACCESS_TOKEN or PLATFORM_TOKEN_ENDPOINT, PLATFORM_CLIENT_ID, and PLATFORM_CLIENT_SECRET"
    )
