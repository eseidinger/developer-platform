"""Provider-neutral hosted-application access intent and unambiguous route matching."""
import re
from typing import Literal
from urllib.parse import unquote

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .manifests import validate_name


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


def canonical_path(path: str) -> str:
    if not isinstance(path, str) or not path.startswith("/") or len(path) > 2048:
        raise ValueError("Invalid absolute path")
    if re.search(r"%(?![0-9a-fA-F]{2})", path) or re.search(r"%(?:2f|5c|25)", path, re.I):
        raise ValueError("Ambiguous path encoding")
    decoded = unquote(path, encoding="utf-8", errors="strict")
    if any(c in decoded for c in "\\?#") or any(ord(c) < 32 or ord(c) == 127 for c in decoded):
        raise ValueError("Invalid path characters")
    if "//" in decoded or any(p in {".", ".."} for p in decoded.split("/")):
        raise ValueError("Ambiguous path segments")
    return decoded


class GroupCreate(Strict):
    name: str
    displayName: str = Field(min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def name_valid(cls, value):
        return validate_name(value)


class RouteMatch(Strict):
    path: str | None = None
    pathPrefix: str | None = None
    methods: list[Literal["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]] = Field(min_length=1)

    @model_validator(mode="after")
    def check(self):
        if (self.path is None) == (self.pathPrefix is None):
            raise ValueError("Specify exactly one of path or pathPrefix")
        value = self.path if self.path is not None else self.pathPrefix
        if canonical_path(value) != value or value.startswith("/oauth2"):
            raise ValueError("Use canonical paths outside the reserved /oauth2 namespace")
        if len(self.methods) != len(set(self.methods)):
            raise ValueError("Methods must be unique; HEAD follows GET")
        return self


class Authentication(Strict):
    mode: Literal["browser-session", "bearer-token"]


class Authorization(Strict):
    anyOfGroups: list[str] = Field(min_length=1, max_length=50)

    @field_validator("anyOfGroups")
    @classmethod
    def groups_valid(cls, value):
        if len(set(value)) != len(value) or any(not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", v) for v in value):
            raise ValueError("Group references must be unique names or stable IDs")
        return value


class Route(Strict):
    name: str = Field(min_length=1, max_length=64)
    match: RouteMatch
    authentication: Authentication
    authorization: Authorization


def contains(match: dict, path: str) -> bool:
    if match.get("path") is not None:
        return path == match["path"]
    prefix = match["pathPrefix"].rstrip("/")
    return not prefix or path == prefix or path.startswith(prefix + "/")


def overlap(left: dict, right: dict) -> bool:
    if not set(left["methods"]) & set(right["methods"]):
        return False
    if left.get("path") is not None:
        return contains(right, left["path"])
    if right.get("path") is not None:
        return contains(left, right["path"])
    return contains(left, right["pathPrefix"].rstrip("/") or "/") or contains(
        right, left["pathPrefix"].rstrip("/") or "/")


class IdentityAttributes(Strict):
    displayName: bool = False
    email: bool = False


class PolicyCreate(Strict):
    component: str
    defaultDecision: Literal["deny"] = "deny"
    identityAttributes: IdentityAttributes = Field(default_factory=IdentityAttributes)
    routes: list[Route] = Field(min_length=1, max_length=100)

    @field_validator("component")
    @classmethod
    def component_valid(cls, value):
        return validate_name(value)

    @model_validator(mode="after")
    def disjoint_routes(self):
        if len({r.name for r in self.routes}) != len(self.routes):
            raise ValueError("Route names must be unique")
        browser = [r for r in self.routes if r.authentication.mode == "browser-session"]
        if browser and not any("GET" in r.match.methods for r in browser):
            raise ValueError("Browser authentication requires a GET entry route")
        for i, route in enumerate(self.routes):
            for other in self.routes[i + 1:]:
                if overlap(route.match.model_dump(), other.match.model_dump()):
                    raise ValueError("Overlapping route/method rules are not supported")
        return self


class Approval(Strict):
    groups: list[str] = Field(min_length=1, max_length=50)


class ServiceRequest(Strict):
    name: str
    providerProject: str
    application: str
    projectWideCredential: Literal[True]

    @field_validator("name", "providerProject", "application")
    @classmethod
    def name_valid(cls, value):
        return validate_name(value)


class Rotation(Strict):
    emergency: bool = False


class Governance(Strict):
    maximumDataClassification: Literal["Public", "Internal", "Confidential"]
    maximumTelemetryClassification: Literal["Public", "Internal", "Confidential"]
    personalData: bool
    domainRetentionOwner: str = Field(min_length=1, max_length=200)
    domainRetentionPolicy: str = Field(min_length=1, max_length=2000)
    purgeAuthority: str = Field(min_length=1, max_length=200)
    recoveryOwner: str = Field(min_length=1, max_length=200)


def match_route(policy: dict, raw_path: str, method: str) -> dict | None:
    path = canonical_path(raw_path)
    method = "GET" if method == "HEAD" else method
    return next((r for r in policy["routes"] if method in r["match"]["methods"]
                 and contains(r["match"], path)), None)
