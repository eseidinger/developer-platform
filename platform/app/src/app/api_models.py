"""Validated HTTP request bodies for the control-plane API.

Keep transport schemas separate from endpoint wiring and runtime state. These
models reuse domain validators; they do not open connections or start workers.
"""

from typing import Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)

from . import human_database_access
from .config import normalize_configuration
from .manifests import normalize_resources, validate_name
from .project_policy import validate_component_capacity


class Project(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    image: str | None = Field(
        default=None,
        min_length=1,
        max_length=512,
        pattern=r"^[a-zA-Z0-9][a-zA-Z0-9./_:@-]+$",
    )
    port: int = Field(default=8080, ge=1024, le=65535)
    probe_profile: Literal["status", "hello-world"] = "status"
    readiness_path: str | None = Field(
        default=None,
        min_length=1,
        max_length=256,
        pattern=r"^/[A-Za-z0-9._~!$&'()*+,;=:@%/-]*$",
    )
    readiness_port: int | None = Field(default=None, ge=1024, le=65535)
    resources: dict | None = None
    configuration: dict | None = None
    components: list[dict] | None = None

    @field_validator("components")
    @classmethod
    def components_require_versioned_envelope(cls, value, info: ValidationInfo):
        if value is not None and not (info.context or {}).get("versioned_envelope"):
            raise ValueError("components require a versioned Application envelope")
        return value

    @model_validator(mode="after")
    def one_workload_shape(self):
        if (self.image is None) == (self.components is None):
            raise ValueError("provide either image or components")
        if (
            self.readiness_port is not None
            and self.image is not None
            and self.readiness_port != self.port
        ):
            raise ValueError("readiness_port must equal the application port")
        components = (
            self.components
            if self.components is not None
            else [{"type": "service", "resources": self.resources}]
        )
        validate_component_capacity(self.name, components)
        return self

    @field_validator("resources")
    @classmethod
    def check_resources(cls, value):
        return None if value is None else normalize_resources(value)

    @field_validator("configuration")
    @classmethod
    def check_configuration(cls, value):
        return None if value is None else normalize_configuration(value)

    @field_validator("name")
    @classmethod
    def check_name(cls, value):
        return validate_name(value)


class DataServiceRecoveryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: Literal["unavailable", "access", "data_integrity", "other"]


class AIProjectPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    classification: Literal["public", "internal", "confidential", "restricted"]


class AIRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal[
        "explain_application", "investigate_incident", "development_assistance"
    ]


class AIProposalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: UUID


class AIApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    diff_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class DataServiceRecoveryReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["acknowledged", "resolved"]


class HumanDatabaseGrant(BaseModel):
    model_config = ConfigDict(extra="forbid")
    issuer: str = Field(min_length=1, max_length=2048)
    subject: str = Field(min_length=1, max_length=1024)
    public_key: str = Field(min_length=1, max_length=256)

    @field_validator("public_key")
    @classmethod
    def valid_public_key(cls, value: str) -> str:
        return human_database_access.parse_public_key(value)[0]


class HumanDatabaseKey(BaseModel):
    model_config = ConfigDict(extra="forbid")
    public_key: str = Field(min_length=1, max_length=256)

    @field_validator("public_key")
    @classmethod
    def valid_public_key(cls, value: str) -> str:
        return human_database_access.parse_public_key(value)[0]


class HumanDatabaseReference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    issuer: str = Field(min_length=1, max_length=2048)
    subject: str = Field(min_length=1, max_length=1024)


class DeploymentCredentialCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(
        min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$"
    )
    expires_in_days: int = Field(default=30, ge=1, le=90)


class DeploymentCredentialRotate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expires_in_days: int = Field(default=30, ge=1, le=90)
    overlap_hours: int = Field(default=1, ge=0, le=24)


class EmptyProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str

    @field_validator("name")
    @classmethod
    def check_name(cls, value):
        return validate_name(value)


class TestRunnerCredentialCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(
        min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$"
    )
    expires_in_days: int = Field(default=7, ge=1, le=30)


class TestIdentityCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(
        min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$"
    )
    role: Literal["viewer", "developer", "project-admin", "platform-admin"]
    project: str | None = None
    test_run_id: str = Field(
        min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$"
    )
    expires_in_hours: int = Field(default=2, ge=1, le=24)

    @model_validator(mode="after")
    def role_scope(self):
        if self.role == "platform-admin" and self.project is not None:
            raise ValueError("platform-admin must use platform scope")
        if self.role != "platform-admin" and self.project is None:
            raise ValueError("project roles require a project")
        if self.project is not None:
            self.project = validate_name(self.project)
        return self


class ConfigurationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    values: dict


class Rollback(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(gt=0)


class Retirement(BaseModel):
    confirm_name: str
    scope_token: str | None = Field(default=None, max_length=128)


class ProjectPurge(BaseModel):
    """Explicit confirmation required to permanently purge a retired project."""

    model_config = ConfigDict(extra="forbid")
    confirm_name: str = Field(min_length=1, max_length=63)
    scope_token: str = Field(min_length=32, max_length=128)


class ProjectGrant(BaseModel):
    issuer: str = Field(min_length=1, max_length=2048)
    subject: str = Field(min_length=1, max_length=1024)
    role: Literal["viewer", "developer", "project-admin"]
    display_name: str | None = Field(default=None, max_length=512)


class GrantReference(BaseModel):
    issuer: str = Field(min_length=1, max_length=2048)
    subject: str = Field(min_length=1, max_length=1024)


class PlatformGrant(ProjectGrant):
    role: Literal["platform-admin"]
