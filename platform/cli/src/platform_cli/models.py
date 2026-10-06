"""Strict boundary models for the first deployment workflow."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TokenResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    access_token: str = Field(min_length=1)
    token_type: str = Field(min_length=1)


class OperationAccepted(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_id: str = Field(min_length=1)
    state: str = Field(min_length=1)
    revision: int = Field(ge=0)
    status_url: str = Field(min_length=1)


class Readiness(BaseModel):
    model_config = ConfigDict(extra="allow")

    state: str = Field(min_length=1)
    reason: str | None = None


class OperationStatus(BaseModel):
    model_config = ConfigDict(extra="allow")

    operation_id: str = Field(min_length=1)
    state: str = Field(min_length=1)
    revision: int = Field(ge=0)
    error_code: str | None = None
    readiness: Readiness


def application_body(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("application specification must be a JSON object")
    return value
