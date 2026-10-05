from __future__ import annotations

from typing import Literal

from pydantic import ConfigDict, Field, model_validator

from frag_api.schemas.common import ApiModel, ExplicitApproval, StageResult, TokenBudget
from frag_api.schemas.context_source import FileSourceSelection
from frag_api.schemas.governance import PreparedCall, SourceBinding, TaskContract
from frag_api.schemas.rag import InferencePreview, RagContextCompression, RagEvidence, RagGroundedAnswer
from frag_api.schemas.runtime import RunLink
from frag_api.schemas.memory import MemorySelection


class PluginEvidenceSelection(ApiModel):
    model_config = ConfigDict(extra="forbid", strict=True, populate_by_name=True)
    plugin_id: str = Field(alias="pluginId", pattern=r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$", max_length=63)
    workspace_id: str | None = Field(default=None, alias="workspaceId", min_length=1, max_length=128)
    scope_id: str | None = Field(default=None, alias="scopeId", min_length=1, max_length=500)
    record_ids: list[str] = Field(alias="recordIds", min_length=1, max_length=10)

    @model_validator(mode="after")
    def selected_scope(self):
        if bool(self.workspace_id) == bool(self.scope_id):
            raise ValueError("Select exactly one scopeId or legacy Workspace.")
        if self.workspace_id and self.plugin_id != "finance-core":
            raise ValueError("Legacy Workspace selection is Finance Core only.")
        if len(set(self.record_ids)) != len(self.record_ids) or any(not value or len(value) > 128 for value in self.record_ids):
            raise ValueError("Record IDs must be distinct, nonempty and bounded.")
        return self

    @property
    def scope(self) -> str:
        return self.scope_id or self.workspace_id



class HarnessRequest(RunLink):
    goal: str = Field(min_length=3, max_length=500)
    file_selections: list[FileSourceSelection] = Field(alias="fileSelections", default_factory=list, max_length=3)
    plugin_selection: PluginEvidenceSelection | None = Field(alias="pluginSelection", default=None)
    task: TaskContract = Field(default_factory=TaskContract)
    selected_memory: list[MemorySelection] = Field(default_factory=list, alias="selectedMemory", max_length=3)

    @model_validator(mode="after")
    def exactly_one_source(self):
        if bool(self.file_selections) == bool(self.plugin_selection):
            raise ValueError("Select local files or one plugin evidence scope.")
        return self


class HarnessRunRequest(HarnessRequest, ExplicitApproval):
    context_fingerprint: str = Field(alias="contextFingerprint", min_length=64, max_length=64)
    approval_token: str = Field(alias="approvalToken", min_length=32)
    approved: Literal[True]


class HarnessPreview(ApiModel):
    run_id: str | None = Field(default=None, alias="runId")
    session_id: str | None = Field(default=None, alias="sessionId")
    goal: str
    candidate_evidence: list[RagEvidence] = Field(alias="candidateEvidence")
    instructions: str
    input: str
    budget: TokenBudget
    warnings: list[str]
    context_fingerprint: str = Field(alias="contextFingerprint")
    approval_token: str = Field(alias="approvalToken")
    prepared_call: PreparedCall = Field(alias="preparedCall")
    source_bindings: tuple[SourceBinding, ...] = Field(alias="sourceBindings")
    task: TaskContract
    can_approve: bool = Field(alias="canApprove")


class HarnessRun(ApiModel):
    preview: HarnessPreview
    compressed_context: RagContextCompression = Field(alias="compressedContext")
    result: RagGroundedAnswer
    context_stage: StageResult = Field(alias="contextStage")
    inference_stage: StageResult = Field(alias="inferenceStage")


class HarnessContextRun(ApiModel):
    preview: HarnessPreview
    compressed_context: RagContextCompression = Field(alias="compressedContext")
    context_stage: StageResult = Field(alias="contextStage")
    inference_preview: InferencePreview = Field(alias="inferencePreview")


__all__ = ["HarnessRequest", "HarnessRunRequest", "HarnessPreview", "HarnessRun"]
