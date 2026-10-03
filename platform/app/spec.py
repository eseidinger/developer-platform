"""Versioned ApplicationSpec envelope mapped onto the flat project contract."""
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .config import normalize_configuration
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


class Configuration(_Strict):
    values: dict

    @field_validator("values")
    @classmethod
    def check_values(cls, value):
        return normalize_configuration(value)


class Spec(_Strict):
    application: Application
    configuration: Optional[Configuration] = None
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


CAPABILITIES = {
    "apiVersion": API_VERSION,
    "environments": {"default": {
        "runtime": {"types": ["container"], "registries": "see imageRegistries"},
        "endpoints": {"protocols": ["http"], "exposure": ["public"], "maxCount": 1},
        "scaling": {"minInstances": 1, "maxInstances": 1, "autoscaling": False},
        "resources": {"requests": "up to 1 CPU / 1Gi", "limits": "up to 2 CPU / 2Gi", "requestsMustNotExceedLimits": True},
        "health": {"readiness": {"profiles": ["status", "hello-world"], "customPath": False}},
        "externalResources": [{"type": "postgres", "profiles": ["shared-dev"], "deletionPolicies": ["retain"], "maxCount": 1}],
        "configuration": {"values": True, "maxValues": 50, "maxValueLength": 1024, "secrets": False, "bindings": ["PG"]},
    }},
}


def error_code(body, errors):
    """Stable machine-readable code for a rejected PUT body."""
    envelope = isinstance(body, dict) and ("apiVersion" in body or "kind" in body)
    for error in errors:
        # Union validation tags each error's location with the branch it came from.
        loc = tuple(str(part) for part in error.get("loc", ()))
        branch = loc[1] if len(loc) > 1 else ""
        if envelope and "ApplicationEnvelope" in branch:
            if loc[-1] not in ("apiVersion", "kind") and error.get("type") in ("extra_forbidden", "literal_error"):
                return "unsupported_capability"
        elif not envelope and branch == "Project" and error.get("type") == "extra_forbidden":
            return "unsupported_capability"
    return "invalid_spec"


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
    if envelope.spec.configuration is not None:
        flat["configuration"] = envelope.spec.configuration.values
    return flat
