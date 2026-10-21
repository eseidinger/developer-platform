"""Versioned ApplicationSpec envelope mapped onto the flat project contract."""

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .config import normalize_configuration
from .egress import resolve as resolve_egress_dns
from .egress import validate as validate_egress
from .manifests import normalize_resources
from .project_policy import validate_component_capacity
from .stores.contract import ResourceBinding

API_VERSION = "platform.example/v1alpha1"
COMPONENT_API_VERSION = "platform.example/v1alpha2"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Metadata(_Strict):
    name: str
    project: str | None = None
    environment: Literal["default"] | None = None


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
    # A profile keeps the original externally monitored root-path contract.  A
    # path is an application readiness endpoint used by Kubernetes.
    profile: Literal["status", "hello-world"] | None = None
    path: str | None = Field(
        default=None,
        min_length=1,
        max_length=256,
        pattern=r"^/[A-Za-z0-9._~!$&'()*+,;=:@%/-]*$",
    )
    port: int | None = Field(default=None, ge=1024, le=65535)

    @model_validator(mode="after")
    def exactly_one_probe_kind(self):
        if (self.profile is None) == (self.path is None):
            raise ValueError("readiness requires exactly one of profile or path")
        return self


class Health(_Strict):
    readiness: Readiness


class Application(_Strict):
    runtime: Runtime
    endpoints: list[Endpoint] | None = Field(default=None, min_length=1, max_length=1)
    scaling: Scaling | None = None
    resources: dict | None = None
    health: Health | None = None

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
    configuration: Configuration | None = None


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
    image: str = Field(
        min_length=1, max_length=512, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9./_:@-]+$"
    )
    command: list[str] | None = Field(default=None, max_length=20)
    args: list[str] | None = Field(default=None, max_length=50)


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
    resources: dict | None = None
    bindings: list[ResourceBinding] = Field(default_factory=list, max_length=8)
    outbound: list["OutboundDestination"] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def unique_bindings(self):
        ids = [entry.bindingId for entry in self.bindings]
        if len(set(ids)) != len(ids):
            raise ValueError("each component binding must be declared once")
        return self

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

    @field_validator("outbound")
    @classmethod
    def check_outbound(cls, value):
        for item in value:
            if item.cidr is not None:
                validate_egress(item.model_dump(exclude_none=True))
            else:
                resolve_egress_dns(item.model_dump(exclude_none=True))
        return value


class MetricsDeclaration(_Strict):
    port: str = Field(pattern=r"^[a-z][a-z0-9-]{0,14}$")
    path: str = Field(min_length=1, max_length=128, pattern=r"^/[A-Za-z0-9._~/-]*$")

    @field_validator("path")
    @classmethod
    def safe_path(cls, value):
        if "//" in value or any(segment in {".", ".."} for segment in value.split("/")):
            raise ValueError("metrics path cannot contain empty or dot segments")
        return value


class TracingDeclaration(_Strict):
    enabled: bool = False


class ServiceTelemetry(_Strict):
    metrics: MetricsDeclaration | None = None
    tracing: TracingDeclaration | None = None


class ScheduledTelemetry(_Strict):
    tracing: TracingDeclaration | None = None


class OutboundDestination(_Strict):
    """One operator-approved TCP egress exception for any component."""

    cidr: str | None = None
    dns: str | None = Field(default=None, min_length=1, max_length=253)
    port: int = Field(ge=1, le=65535)

    @model_validator(mode="after")
    def exactly_one_destination(self):
        if (self.cidr is None) == (self.dns is None):
            raise ValueError("outbound requires exactly one of cidr or dns")
        return self


class ServiceComponent(_Component):
    type: Literal["service"]
    ports: list[InternalPort] | None = Field(default=None, max_length=10)
    replicas: int = Field(default=1, ge=1, le=5)
    exposure: Literal["private", "public"] = "private"
    health: Health | None = None
    telemetry: ServiceTelemetry | None = None

    @model_validator(mode="after")
    def unique_ports(self):
        if self.ports and len({port.name for port in self.ports}) != len(self.ports):
            raise ValueError("service port names must be unique")
        if self.health and self.health.readiness.path:
            if not self.ports:
                raise ValueError("HTTP readiness requires a declared service port")
            declared = {port.port for port in self.ports}
            if (
                self.health.readiness.port is not None
                and self.health.readiness.port not in declared
            ):
                raise ValueError(
                    "readiness port must be one of the declared service ports"
                )
        if (self.telemetry and self.telemetry.metrics) and (
            not self.ports
            or self.telemetry.metrics.port not in {port.name for port in self.ports}
        ):
            raise ValueError("metrics port must name a declared HTTP service port")
        return self


class ScheduledComponent(_Component):
    type: Literal["scheduled"]
    schedule: str
    timeZone: Literal["UTC"] = "UTC"
    concurrencyPolicy: Literal["Forbid"] = "Forbid"
    retryLimit: int = Field(default=6, ge=0, le=10)
    maxRunSeconds: int | None = Field(default=None, ge=60, le=86400)
    telemetry: ScheduledTelemetry | None = None

    @field_validator("schedule")
    @classmethod
    def check_schedule(cls, value):
        return _check_cron(value)


Component = ServiceComponent | ScheduledComponent


class ComponentSpec(_Strict):
    components: list[Component] = Field(min_length=1, max_length=5)
    configuration: Configuration | None = None

    @model_validator(mode="after")
    def unique_names(self):
        names = [component.name for component in self.components]
        if len(set(names)) != len(names):
            raise ValueError("component names must be unique")
        public = [
            c
            for c in self.components
            if isinstance(c, ServiceComponent) and c.exposure == "public"
        ]
        if len(public) > 1:
            raise ValueError("only one public service component is supported")
        if public and not public[0].ports:
            raise ValueError(
                "a public service component requires an internal HTTP port"
            )
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
        validate_component_capacity(
            self.metadata.name,
            [component.model_dump() for component in self.spec.components],
        )
        return self


CAPABILITIES = {
    "apiVersion": API_VERSION,
    "apiVersions": [API_VERSION, COMPONENT_API_VERSION],
    "environments": {
        "default": {
            "runtime": {"types": ["container"], "registries": "see imageRegistries"},
            "endpoints": {"protocols": ["http"], "exposure": ["public"], "maxCount": 1},
            "scaling": {"minInstances": 1, "maxInstances": 1, "autoscaling": False},
            "resources": {
                "requests": "up to 1 CPU / 1Gi",
                "limits": "up to 2 CPU / 2Gi",
                "requestsMustNotExceedLimits": True,
            },
            "health": {
                "readiness": {"profiles": ["status", "hello-world"], "customPath": True}
            },
            "externalResources": {
                "lifecycle": "independent named resources",
                "componentBindings": True,
                "implicitDatabase": False,
            },
            "configuration": {
                "values": True,
                "maxValues": 50,
                "maxValueLength": 1024,
                "secrets": True,
                "bindings": ["PG"],
            },
            "components": {
                "types": ["service", "scheduled"],
                "maxCount": 5,
                "outbound": {
                    "cidrOrDnsAndTcpPort": True,
                    "maxDestinations": 5,
                    "operatorAllowListRequired": True,
                    "dnsResolvedAtApply": True,
                },
                "service": {"internalHttpPorts": True, "maxReplicas": 5},
                "scheduled": {
                    "cronFields": 5,
                    "timeZone": ["UTC"],
                    "concurrencyPolicy": ["Forbid"],
                },
            },
            "applicationMetrics": {
                "serviceOptIn": True,
                "prometheusFormat": True,
                "port": "declared HTTP service port",
                "maxPathLength": 128,
                "collection": "private Kubernetes service proxy",
            },
            "applicationTracing": {
                "serviceOptIn": True,
                "scheduledOptIn": True,
                "protocol": "OTLP HTTP protobuf",
                "tokenAudience": "platform-telemetry",
            },
        }
    },
}


def error_code(body, errors):
    """Stable machine-readable code for a rejected PUT body."""
    if any(
        "operator project quota policy is invalid" in str(error.get("msg", ""))
        for error in errors
    ):
        return "policy_unavailable"
    if any(
        "not allowed by operator policy" in str(error.get("msg", ""))
        for error in errors
    ):
        return "policy_denied"
    envelope = isinstance(body, dict) and ("apiVersion" in body or "kind" in body)
    if envelope and (
        body.get("apiVersion") not in {API_VERSION, COMPONENT_API_VERSION}
        or body.get("kind") != "Application"
    ):
        return "invalid_spec"
    for error in errors:
        # Union validation tags each error's location with the branch it came from.
        loc = tuple(str(part) for part in error.get("loc", ()))
        branch = next(
            (
                part
                for part in loc
                if "ApplicationEnvelope" in part or "Project" in part
            ),
            "",
        )
        if envelope and "ApplicationEnvelope" in branch:
            if loc[-1] not in ("apiVersion", "kind") and error.get("type") in (
                "extra_forbidden",
                "literal_error",
            ):
                return "unsupported_capability"
        elif (
            not envelope
            and "Project" in branch
            and error.get("type") == "extra_forbidden"
        ):
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
                if component.ports:
                    flat_component["ports"] = [
                        port.model_dump() for port in component.ports
                    ]
                if component.health:
                    readiness = component.health.readiness
                    if readiness.profile:
                        flat_component["probe_profile"] = readiness.profile
                    else:
                        flat_component["readiness_path"] = readiness.path
                        if readiness.port is not None:
                            flat_component["readiness_port"] = readiness.port
                if component.telemetry and component.telemetry.metrics:
                    metrics = component.telemetry.metrics
                    flat_component["metrics"] = {
                        "port": metrics.port,
                        "path": metrics.path,
                    }
            else:
                flat_component.update(
                    {
                        "schedule": component.schedule,
                        "time_zone": component.timeZone,
                        "concurrency_policy": component.concurrencyPolicy,
                        "retry_limit": component.retryLimit,
                    }
                )
                if component.maxRunSeconds is not None:
                    flat_component["max_run_seconds"] = component.maxRunSeconds
            if component.bindings:
                flat_component["bindings"] = [
                    binding.model_dump(mode="json") for binding in component.bindings
                ]
            if component.outbound:
                flat_component["outbound"] = [
                    destination.model_dump(exclude_none=True)
                    for destination in component.outbound
                ]
            if (
                component.telemetry
                and component.telemetry.tracing
                and component.telemetry.tracing.enabled
            ):
                flat_component["tracing"] = {"enabled": True}
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
        readiness = application.health.readiness
        if readiness.profile:
            flat["probe_profile"] = readiness.profile
        else:
            flat["readiness_path"] = readiness.path
            if readiness.port is not None:
                flat["readiness_port"] = readiness.port
    if application.resources is not None:
        flat["resources"] = application.resources
    if envelope.spec.configuration is not None:
        flat["configuration"] = envelope.spec.configuration.values
    return flat
