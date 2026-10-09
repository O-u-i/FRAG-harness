"""Human-reviewed background memory; records never confer evidence or authority."""
from typing import Literal

from pydantic import Field, field_validator, model_validator

from frag_api.schemas.context_source import ApiModel
from frag_api.schemas.governance import SourceIdentity


class MemorySelection(ApiModel):
    memory_id: str = Field(alias="memoryId", min_length=1, max_length=64)
    version: int = Field(ge=1, strict=True)


class MemoryRecord(ApiModel):
    id: str
    version: int = Field(ge=1)
    content_version: int = Field(default=1, alias="contentVersion", ge=1, strict=True)
    status: Literal["candidate", "active", "retired"]
    text: str = Field(min_length=1, max_length=4000)
    scope: list[SourceIdentity]
    general: bool = Field(strict=True)
    conflicts: list[str]
    provenance_run_id: str = Field(alias="provenanceRunId")
    provenance_revision_id: str | None = Field(default=None, alias="provenanceRevisionId")
    created_at: str = Field(alias="createdAt")
    review_note: str | None = Field(default=None, alias="reviewNote")


class MemoryCandidateRequest(ApiModel):
    run_id: str = Field(alias="runId", min_length=1, max_length=64)
    text: str = Field(min_length=1, max_length=4000)
    general: bool = Field(default=False, strict=True)


class MemoryVersionRequest(ApiModel):
    version: int = Field(ge=1, strict=True)


class MemoryRevisionRequest(MemoryVersionRequest):
    text: str = Field(min_length=1, max_length=4000)
    general: bool | None = Field(default=None, strict=True)


class MemoryPromotionRequest(MemoryVersionRequest):
    reviewed: Literal[True]
    note: str = Field(min_length=1, max_length=4000)

    @field_validator("reviewed", mode="before")
    @classmethod
    def explicit_review(cls, value):
        if value is not True:
            raise ValueError("Review must be the JSON boolean true.")
        return value

    @field_validator("note")
    @classmethod
    def nonblank_note(cls, value):
        if not value.strip():
            raise ValueError("A review note is required.")
        return value


class MemoryConflictRequest(ApiModel):
    memory_ids: list[str] = Field(alias="memoryIds", min_length=2, max_length=2)

    @model_validator(mode="after")
    def distinct_records(self):
        if any(not item or len(item) > 64 for item in self.memory_ids) or len(set(self.memory_ids)) != 2:
            raise ValueError("Choose two distinct memory records.")
        return self


class MemoryConflictResolutionRequest(MemoryConflictRequest):
    versions: list[MemorySelection] = Field(min_length=2, max_length=2)
    reviewed: Literal[True]
    note: str = Field(min_length=1, max_length=4000)

    @field_validator("reviewed", mode="before")
    @classmethod
    def explicit_review(cls, value):
        return MemoryPromotionRequest.explicit_review(value)

    @field_validator("note")
    @classmethod
    def nonblank_note(cls, value):
        return MemoryPromotionRequest.nonblank_note(value)

    @model_validator(mode="after")
    def reviewed_versions(self):
        if {item.memory_id for item in self.versions} != set(self.memory_ids):
            raise ValueError("Reviewed versions must identify both conflicting records.")
        return self


class MemoryRecommendRequest(ApiModel):
    query: str = Field(min_length=1, max_length=500)
    run_id: str = Field(alias="runId", min_length=1, max_length=64)
