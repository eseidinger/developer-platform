"""Versioned data resource requests; endpoints and admin credentials are operator owned."""
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator

NAME = r"^[a-z][a-z0-9-]{0,30}[a-z0-9]$|^[a-z]$"
Mode = Literal["read-only", "read-write"]
Provider = Literal["postgresql", "s3", "opensearch", "neo4j", "qdrant"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VectorConfiguration(Strict):
    vector_size: int = Field(default=384, ge=1, le=65536)
    distance: Literal['Cosine', 'Dot', 'Euclid', 'Manhattan'] = 'Cosine'


class ResourceCreate(Strict):
    name: str = Field(pattern=NAME, max_length=32)
    provider: Provider
    quota_bytes: int = Field(default=1_073_741_824, ge=1_048_576, le=1_099_511_627_776)
    extensions: list[Literal["vector", "age"]] = Field(default_factory=list, max_length=2)
    configuration: VectorConfiguration | None = None

    @model_validator(mode="after")
    def extensions_only_on_postgres(self):
        if self.extensions and (self.provider != "postgresql" or len(set(self.extensions)) != len(self.extensions)):
            raise ValueError("unique extensions apply only to PostgreSQL resources")
        if self.configuration is not None and self.provider != 'qdrant':
            raise ValueError('Vector configuration applies only to Qdrant resources')
        if self.provider == 'qdrant' and self.configuration is None:
            self.configuration = VectorConfiguration()
        return self


class ResourceRename(Strict):
    name: str = Field(pattern=NAME, max_length=32)
    version: int = Field(ge=1)


class Version(Strict):
    version: int = Field(ge=1)


class Purge(Version):
    confirm_resource_id: UUID
    confirm_owner_project: str = Field(pattern=NAME, max_length=32)


class HumanGrant(Strict):
    issuer: str = Field(min_length=1, max_length=512)
    subject: str = Field(min_length=1, max_length=256)
    mode: Mode


class BindingRequest(Strict):
    resource_id: UUID
    component: str = Field(pattern=NAME, max_length=32)
    mode: Mode


class Approval(Version):
    approve: bool


class GrantUpdate(Version):
    mode: Mode


class QuotaChange(Version):
    quota_bytes: int = Field(ge=1_048_576, le=1_099_511_627_776)


class ResourceBinding(Strict):
    bindingId: UUID
    envPrefix: str = Field(default="", max_length=32, pattern=r"^([A-Z][A-Z0-9_]*_)?$")


class PublicKey(Strict):
    public_key: str = Field(min_length=1, max_length=256)
