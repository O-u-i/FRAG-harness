from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from frag_api.schemas.common import ApiModel, ExplicitApproval, HarnessConfig, StageResult, TokenBudget
from frag_api.schemas.context_source import FileSourceSelection
from frag_api.schemas.governance import PreparedCall, SourceBinding, TaskContract
from frag_api.schemas.rag import InferencePreview, RagContextCompression, RagEvidence, RagGroundedAnswer


class PluginEvidenceSelection(ApiModel):
    plugin_id: Literal["finance-core"] = Field(alias="pluginId")
    workspace_id: str = Field(alias="workspaceId", min_length=1, max_length=128)
    record_ids: list[str] = Field(alias="recordIds", min_length=1, max_length=10)


class HarnessRequest(ApiModel):
    goal: str = Field(min_length=3, max_length=500)
    file_selections: list[FileSourceSelection] = Field(alias="fileSelections", default_factory=list, max_length=3)
    plugin_selection: PluginEvidenceSelection | None = Field(alias="pluginSelection", default=None)
    task: TaskContract = Field(default_factory=TaskContract)

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


__all__ = ["HarnessConfig", "HarnessRequest", "HarnessRunRequest", "HarnessPreview", "HarnessRun"]
