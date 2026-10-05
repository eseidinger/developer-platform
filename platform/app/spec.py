"""Versioned ApplicationSpec envelope mapped onto the flat project contract."""
import re
from typing import List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .config import normalize_configuration
from .manifests import normalize_resources
from .egress import validate as validate_egress
from .project_policy import validate_component_capacity

API_VERSION = "platform.example/v1alpha1"
COMPONENT_API_VERSION = "platform.example/v1alpha2"


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


class ComponentRuntime(_Strict):
    type: Literal["container"]
    image: str = Field(min_length=1, max_length=512, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9./_:@-]+$")
    command: Optional[List[str]] = Field(default=None, max_length=20)
    args: Optional[List[str]] = Field(default=None, max_length=50)


class InternalPort(_Strict):
    name: str = Field(pattern=r"^[a-z][a-z0-9-]{0,14}$")
    protocol: Literal["http"]
    port: int = Field(ge=1024, le=65535)


def _check_cron(schedule: str) -> str:
    """Validate the portable five-field cron subset Kubernetes accepts."""
    fields = schedule.split()
    if len(fields) != 5:
        raise ValueError("schedule must use exactly five cron fields")
    limits = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 7))
    for field, (low, high) in zip(fields, limits):
        for part in field.split(","):
            match = re.fullmatch(r"(\*|\d+|\d+-\d+)(?:/(\d+))?", part)
            if not match:
                raise ValueError("schedule contains an unsupported cron expression")
            base, step = match.groups()
            if step is not None and not 1 <= int(step) <= high - low + 1:
                raise ValueError("schedule step is outside its allowed range")
            if base != "*":
                values = base.split("-")
                if any(not low <= int(value) <= high for value in values):
                    raise ValueError("schedule field is outside its allowed range")
                if len(values) == 2 and int(values[0]) > int(values[1]):
                    raise ValueError("schedule range must increase")
    return schedule


class _Component(_Strict):
    name: str
    runtime: ComponentRuntime
    resources: Optional[dict] = None

    @field_validator("name")
    @classmethod
    def check_name(cls, value):
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,30}[a-z0-9]|[a-z]", value):
            raise ValueError("component name must be a Kubernetes-compatible name")
        return value

    @field_validator("resources")
    @classmethod
    def check_resources(cls, value):
        return None if value is None else normalize_resources(value)


class OutboundDestination(_Strict):
    """One operator-approved TCP egress exception for a service component."""
    cidr: str
    port: int = Field(ge=1, le=65535)


class ServiceComponent(_Component):
    type: Literal["service"]
    ports: Optional[List[InternalPort]] = Field(default=None, max_length=10)
    replicas: int = Field(default=1, ge=1, le=5)
    exposure: Literal["private", "public"] = "private"
    outbound: List[OutboundDestination] = Field(default_factory=list, max_length=5)

    @field_validator("outbound")
    @classmethod
    def check_outbound(cls, value):
        for item in value:
            validate_egress(item.model_dump())
        return value
    health: Optional[Health] = None

    @model_validator(mode="after")
    def unique_ports(self):
        if self.ports and len({port.name for port in self.ports}) != len(self.ports):
            raise ValueError("service port names must be unique")
        return self


class ScheduledComponent(_Component):
    type: Literal["scheduled"]
    schedule: str
    timeZone: Literal["UTC"] = "UTC"
    concurrencyPolicy: Literal["Forbid"] = "Forbid"

    @field_validator("schedule")
    @classmethod
    def check_schedule(cls, value):
        return _check_cron(value)


Component = Union[ServiceComponent, ScheduledComponent]


class ComponentSpec(_Strict):
    components: List[Component] = Field(min_length=1, max_length=5)
    configuration: Optional[Configuration] = None
    resources: Optional[List[ExternalResource]] = Field(default=None, max_length=1)

    @model_validator(mode="after")
    def unique_names(self):
        names = [component.name for component in self.components]
        if len(set(names)) != len(names):
            raise ValueError("component names must be unique")
        public = [c for c in self.components if isinstance(c, ServiceComponent) and c.exposure == "public"]
        if len(public) > 1:
            raise ValueError("only one public service component is supported")
        if public and not public[0].ports:
            raise ValueError("a public service component requires an internal HTTP port")
        return self


class ApplicationEnvelopeV1Alpha2(_Strict):
    apiVersion: Literal["platform.example/v1alpha2"]
    kind: Literal["Application"]
    metadata: Metadata
    spec: ComponentSpec

    @model_validator(mode="after")
    def check_project(self):
        if self.metadata.project not in (None, self.metadata.name):
            raise ValueError("metadata.project must equal metadata.name")
        validate_component_capacity(self.metadata.name, [component.model_dump() for component in self.spec.components])
        return self


CAPABILITIES = {
    "apiVersion": API_VERSION,
    "apiVersions": [API_VERSION, COMPONENT_API_VERSION],
    "environments": {"default": {
        "runtime": {"types": ["container"], "registries": "see imageRegistries"},
        "endpoints": {"protocols": ["http"], "exposure": ["public"], "maxCount": 1},
        "scaling": {"minInstances": 1, "maxInstances": 1, "autoscaling": False},
        "resources": {"requests": "up to 1 CPU / 1Gi", "limits": "up to 2 CPU / 2Gi", "requestsMustNotExceedLimits": True},
        "health": {"readiness": {"profiles": ["status", "hello-world"], "customPath": False}},
        "externalResources": [{"type": "postgres", "profiles": ["shared-dev"], "deletionPolicies": ["retain"], "maxCount": 1}],
        "configuration": {"values": True, "maxValues": 50, "maxValueLength": 1024, "secrets": True, "bindings": ["PG"]},
        "components": {"types": ["service", "scheduled"], "maxCount": 5,
                       "service": {"internalHttpPorts": True, "maxReplicas": 5,
                                   "outbound": {"cidrAndTcpPort": True, "maxDestinations": 5,
                                                "operatorAllowListRequired": True}},
                       "scheduled": {"cronFields": 5, "timeZone": ["UTC"], "concurrencyPolicy": ["Forbid"]}},
    }},
}


def error_code(body, errors):
    """Stable machine-readable code for a rejected PUT body."""
    if any("operator project quota policy is invalid" in str(error.get("msg", "")) for error in errors):
        return "policy_unavailable"
    if any("not allowed by operator policy" in str(error.get("msg", "")) for error in errors):
        return "policy_denied"
    envelope = isinstance(body, dict) and ("apiVersion" in body or "kind" in body)
    if envelope and (body.get("apiVersion") not in {API_VERSION, COMPONENT_API_VERSION}
                     or body.get("kind") != "Application"):
        return "invalid_spec"
    for error in errors:
        # Union validation tags each error's location with the branch it came from.
        loc = tuple(str(part) for part in error.get("loc", ()))
        branch = next((part for part in loc
                       if "ApplicationEnvelope" in part or "Project" in part), "")
        if envelope and "ApplicationEnvelope" in branch:
            if loc[-1] not in ("apiVersion", "kind") and error.get("type") in ("extra_forbidden", "literal_error"):
                return "unsupported_capability"
        elif not envelope and "Project" in branch and error.get("type") == "extra_forbidden":
            return "unsupported_capability"
    return "invalid_spec"


def to_flat(body):
    """Return the flat project fields for an envelope; flat bodies pass through unchanged."""
    if not isinstance(body, dict) or "apiVersion" not in body and "kind" not in body:
        return body
    if body.get("apiVersion") == COMPONENT_API_VERSION:
        envelope = ApplicationEnvelopeV1Alpha2.model_validate(body)
        components = []
        for component in envelope.spec.components:
            flat_component = {
                "name": component.name,
                "type": component.type,
                "image": component.runtime.image,
            }
            for key in ("command", "args"):
                value = getattr(component.runtime, key)
                if value is not None:
                    flat_component[key] = value
            if component.resources is not None:
                flat_component["resources"] = component.resources
            if isinstance(component, ServiceComponent):
                flat_component["replicas"] = component.replicas
                if component.exposure == "public":
                    flat_component["exposure"] = "public"
                if component.outbound:
                    flat_component["outbound"] = [destination.model_dump() for destination in component.outbound]
                if component.ports:
                    flat_component["ports"] = [port.model_dump() for port in component.ports]
                if component.health:
                    flat_component["probe_profile"] = component.health.readiness.profile
            else:
                flat_component.update({"schedule": component.schedule, "time_zone": component.timeZone,
                                       "concurrency_policy": component.concurrencyPolicy})
            components.append(flat_component)
        flat = {"name": envelope.metadata.name, "components": components}
        if envelope.spec.configuration is not None:
            flat["configuration"] = envelope.spec.configuration.values
        return flat
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
