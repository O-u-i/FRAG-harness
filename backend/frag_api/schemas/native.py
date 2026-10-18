"""Contracts for evidence tools, not model orchestration or native chat history."""
from typing import Literal
from pydantic import Field, model_validator, field_validator
from frag_api.schemas.context_source import ApiModel
from frag_api.schemas.governance import SourceBinding
from frag_api.schemas.memory import MemorySelection


class ConfirmedPlan(ApiModel):
    relative_path: str = Field(alias="relativePath", min_length=1, max_length=1000)
    revision: str = Field(pattern=r"^[0-9a-f]{64}$")


class PlanConfirmationInput(ApiModel):
    run_id: str = Field(alias="runId", min_length=1, max_length=64)
    evidence_id: str = Field(alias="evidenceId", pattern=r"^[0-9a-f]{24}$")
    confirmed: bool = Field(strict=True)

    @model_validator(mode="after")
    def explicit_confirmation(self):
        if self.confirmed is not True:
            raise ValueError("Plan confirmation requires the JSON boolean true.")
        return self


class SourceProfile(ApiModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,62}$")
    kind: Literal["local", "fc"] = "local"
    root: str | None = Field(default=None, max_length=1000)
    excluded_paths: list[str] = Field(default_factory=list, alias="excludedPaths", max_length=100)
    enabled: bool = Field(default=True, strict=True)
    approved: Literal[True]
    revision: int = Field(default=0, ge=0, strict=True)
    selected_memory: list[MemorySelection] = Field(default_factory=list, alias="selectedMemory", max_length=3)
    confirmed_plans: list[ConfirmedPlan] = Field(default_factory=list, alias="confirmedPlans", max_length=10)

    @field_validator("approved", mode="before")
    @classmethod
    def explicit_approval(cls, value):
        if value is not True:
            raise ValueError("Source approval must be the JSON boolean true.")
        return value

    @model_validator(mode="after")
    def source_kind(self):
        if (self.kind == "local") != bool(self.root):
            raise ValueError("Local sources require a root; FC sources do not accept filesystem roots.")
        if self.kind == "fc" and (self.id != "finance-core" or self.excluded_paths or self.confirmed_plans):
            raise ValueError("Only the named Finance Core source is supported.")
        if len({m.memory_id for m in self.selected_memory}) != len(self.selected_memory):
            raise ValueError("Memory selections must be distinct.")
        if len({p.relative_path for p in self.confirmed_plans}) != len(self.confirmed_plans):
            raise ValueError("Confirmed plans must be distinct.")
        return self


class SearchInput(ApiModel):
    source_id: str = Field(default="kb", alias="sourceId", min_length=1, max_length=63)
    query: str = Field(min_length=3, max_length=500)
    top_k: int = Field(default=3, alias="topK", ge=1, le=10, strict=True)


class ReadInput(ApiModel):
    search_run_id: str = Field(alias="searchRunId", min_length=1, max_length=64)
    evidence_ids: list[str] = Field(alias="evidenceIds", min_length=1, max_length=10)
    require_complete_plan: bool = Field(default=False, alias="requireCompletePlan", strict=True)

    @model_validator(mode="after")
    def distinct(self):
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("Evidence IDs must be distinct.")
        return self


class FcInput(ApiModel):
    operation: Literal["list", "read"]
    workspace_id: str | None = Field(default=None, alias="workspaceId", max_length=500)
    record_ids: list[str] = Field(default_factory=list, alias="recordIds", max_length=10)

    @model_validator(mode="after")
    def bounded_read(self):
        if self.operation == "list" and (self.workspace_id or self.record_ids):
            raise ValueError("Discovery does not accept a selected record request.")
        if self.operation == "read" and (not self.workspace_id or not self.record_ids or len(set(self.record_ids)) != len(self.record_ids)):
            raise ValueError("Read requires one Workspace and distinct configured records.")
        return self


class ToolRun(ApiModel):
    id: str
    schema_version: Literal[2] = Field(default=2, alias="schemaVersion")
    tool: Literal["frag_search", "frag_read", "frag_fc_read"]
    input: dict
    source_id: str | None = Field(default=None, alias="sourceId")
    source_revision: int | None = Field(default=None, alias="sourceRevision")
    created_at: str = Field(alias="createdAt")
    status: Literal["prepared", "completed", "failed", "cancelled", "interrupted"]
    source_bindings: list[SourceBinding] = Field(default_factory=list, alias="sourceBindings")
    pack: dict | None = None
    result_digest: str | None = Field(default=None, alias="resultDigest")
    output_tokens: int | None = Field(default=None, alias="outputTokens")
    error_code: str | None = Field(default=None, alias="errorCode")


class CompleteInput(ApiModel):
    run_id: str = Field(alias="runId", min_length=1, max_length=64)
    omitted_evidence_ids: list[str] = Field(default_factory=list, alias="omittedEvidenceIds", max_length=10)
    token_count: int | None = Field(default=None, alias="tokenCount", ge=0, strict=True)
    cancelled: bool = Field(default=False, strict=True)
    failure: Literal["TOOL_TOKEN_BUDGET_TOO_SMALL", "TOOL_RESULT_FAILED"] | None = None


class RunLookupInput(ApiModel):
    run_id: str = Field(alias="runId", min_length=1, max_length=64)
