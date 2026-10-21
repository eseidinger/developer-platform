"""Non-persistent authentication configuration for the first CLI increment."""

from __future__ import annotations

import os
from dataclasses import dataclass


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
    profile_name: str | None = None
    profile: object | None = None
    insecure: bool = False


def runtime_config(
    environment: dict[str, str] | None = None,
    *,
    profile_name: str | None = None,
    api_url_override: str | None = None,
    insecure: bool = False,
) -> RuntimeConfig:
    """Read the non-persistent command configuration from an environment mapping."""
    env = os.environ if environment is None else environment
    from .profiles import ProfileStore, validate_url

    environment_auth = bool(
        env.get("PLATFORM_ACCESS_TOKEN")
        or env.get("PLATFORM_TOKEN_ENDPOINT")
        or env.get("PLATFORM_CLIENT_ID")
        or env.get("PLATFORM_CLIENT_SECRET")
    )
    selected, profile = (
        (None, None)
        if not profile_name and env.get("PLATFORM_API_URL") and environment_auth
        else ProfileStore().selected(profile_name)
    )
    api_url = (
        api_url_override
        or env.get("PLATFORM_API_URL")
        or (profile.api_url if profile else "")
    ).rstrip("/")
    if not api_url:
        raise ConfigurationError("PLATFORM_API_URL is required")
    validate_url(api_url)
    ca_bundle = env.get("PLATFORM_CA_BUNDLE") or (
        profile.ca_bundle if profile else None
    )

    token = env.get("PLATFORM_ACCESS_TOKEN")
    if token:
        return RuntimeConfig(
            api_url=api_url,
            ca_bundle=ca_bundle,
            access_token_auth=AccessTokenAuth(token),
            deployment_credential_auth=None,
            profile_name=selected,
            profile=profile,
            insecure=insecure,
        )

    credential_values = {
        "PLATFORM_TOKEN_ENDPOINT": env.get("PLATFORM_TOKEN_ENDPOINT"),
        "PLATFORM_CLIENT_ID": env.get("PLATFORM_CLIENT_ID"),
        "PLATFORM_CLIENT_SECRET": env.get("PLATFORM_CLIENT_SECRET"),
    }
    present = {name for name, value in credential_values.items() if value}
    if present and len(present) != len(credential_values):
        missing = sorted(set(credential_values) - present)
        raise ConfigurationError(
            "deployment credential environment is incomplete; missing "
            + ", ".join(missing)
        )

    credential = None
    if len(present) == len(credential_values):
        credential = DeploymentCredentialAuth(
            token_endpoint=credential_values["PLATFORM_TOKEN_ENDPOINT"] or "",
            client_id=credential_values["PLATFORM_CLIENT_ID"] or "",
            client_secret=credential_values["PLATFORM_CLIENT_SECRET"] or "",
        )
    return RuntimeConfig(
        api_url=api_url,
        ca_bundle=ca_bundle,
        access_token_auth=None,
        deployment_credential_auth=credential,
        profile_name=selected,
        profile=profile,
        insecure=insecure,
    )


def authentication_source(config: RuntimeConfig) -> str:
    if config.access_token_auth is not None:
        return "access-token-environment"
    if config.deployment_credential_auth is not None:
        return "deployment-credential-environment"
    if config.profile is not None:
        return "human-profile-session"
    raise ConfigurationError(
        "set PLATFORM_ACCESS_TOKEN or PLATFORM_TOKEN_ENDPOINT, PLATFORM_CLIENT_ID, and PLATFORM_CLIENT_SECRET"
    )
