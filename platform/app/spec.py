"""Versioned ApplicationSpec envelope mapped onto the flat project contract."""
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .manifests import normalize_resources

API_VERSION = "platform.example/v1alpha1"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Metadata(_Strict):
    name: str
    project: Optional[str] = None
    environment: Optional[Literal["default"]] = None


class Runtime(_Strict):
    type: Literal["container"]
    image: str


class Endpoint(_Strict):
    name: str
    protocol: Literal["http"]
    port: int
    exposure: Literal["public"]


class Scaling(_Strict):
    minInstances: Literal[1]
    maxInstances: Literal[1]


class Readiness(_Strict):
    profile: Literal["status", "hello-world"]


class Health(_Strict):
    readiness: Readiness


class Application(_Strict):
    runtime: Runtime
    endpoints: Optional[List[Endpoint]] = Field(default=None, min_length=1, max_length=1)
    scaling: Optional[Scaling] = None
    resources: Optional[dict] = None
    health: Optional[Health] = None

    @field_validator("resources")
    @classmethod
    def check_resources(cls, value):
        return None if value is None else normalize_resources(value)


class ExternalResource(_Strict):
    name: str
    type: Literal["postgres"]
    profile: Literal["shared-dev"]
    deletionPolicy: Literal["retain"]


class Spec(_Strict):
    application: Application
    resources: Optional[List[ExternalResource]] = Field(default=None, max_length=1)


class ApplicationEnvelope(_Strict):
    apiVersion: Literal["platform.example/v1alpha1"]
    kind: Literal["Application"]
    metadata: Metadata
    spec: Spec

    @model_validator(mode="after")
    def check_project(self):
        if self.metadata.project not in (None, self.metadata.name):
            raise ValueError("metadata.project must equal metadata.name")
        return self


def to_flat(body):
    """Return the flat project fields for an envelope; flat bodies pass through unchanged."""
    if not isinstance(body, dict) or "apiVersion" not in body and "kind" not in body:
        return body
    envelope = ApplicationEnvelope.model_validate(body)
    application = envelope.spec.application
    flat = {"name": envelope.metadata.name, "image": application.runtime.image}
    if application.endpoints:
        flat["port"] = application.endpoints[0].port
    if application.health:
        flat["probe_profile"] = application.health.readiness.profile
    if application.resources is not None:
        flat["resources"] = application.resources
    return flat
