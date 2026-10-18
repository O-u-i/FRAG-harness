"""Versioned host contracts. Registration and source text never grant authority."""
from __future__ import annotations

from typing import Literal

from pydantic import ConfigDict, Field, model_validator

from frag_api.schemas.context_source import ApiModel

HOST_VERSION = "1.13.4"


class FrozenModel(ApiModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, frozen=True)


class QualityFact(FrozenModel):
    status: Literal["known", "unknown"] = "unknown"
    detail: str | None = None

    @model_validator(mode="after")
    def explicit_unknown(self):
        if (self.status == "known") != bool(self.detail):
            raise ValueError("Known metadata requires detail; unknown metadata has no asserted detail.")
        return self


class SourceAssessment(FrozenModel):
    authority: QualityFact = Field(default_factory=QualityFact)
    freshness: QualityFact = Field(default_factory=QualityFact)
    relevance: QualityFact = Field(default_factory=QualityFact)
    provenance: QualityFact = Field(default_factory=QualityFact)
    permission: Literal["selected_read_only"] = "selected_read_only"


class SourceIdentity(FrozenModel):
    kind: Literal["local_file", "synthetic", "fc_record", "plugin_record"]
    namespace: str = Field(min_length=1)
    resource_id: str = Field(alias="resourceId", min_length=1)
    workspace_id: str | None = Field(default=None, alias="workspaceId")

    @model_validator(mode="after")
    def workspace_scope(self):
        if (self.kind in {"fc_record", "plugin_record"}) != bool(self.workspace_id):
            raise ValueError("Plugin records require a source scope; other source kinds have none.")
        return self


class SourceBinding(FrozenModel):
    identity: SourceIdentity
    revision: str = Field(min_length=1)
    parser_version: str = Field(alias="parserVersion", min_length=1)
    locator_ids: tuple[str, ...] = Field(alias="locatorIds", min_length=1)
    evidence_ids: tuple[str, ...] = Field(alias="evidenceIds", min_length=1)
    assessment: SourceAssessment = Field(default_factory=SourceAssessment)

    @model_validator(mode="after")
    def unique_scope(self):
        for values in (self.locator_ids, self.evidence_ids):
            if any(not value for value in values) or len(set(values)) != len(values):
                raise ValueError("Selected scope identifiers must be nonempty and unique.")
        return self
