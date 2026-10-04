"""Bounded evidence-collection decisions and durable, approval-free checkpoints."""
from typing import Annotated, Any, Literal
from pydantic import Field, field_validator, model_validator
from frag_api.schemas.common import ApiModel, ExplicitApproval
from frag_api.schemas.governance import PreparedCall
from frag_api.schemas.tools import ToolCall


class ResearchFinish(ApiModel):
    action: Literal["finish"]
    evidence_ids: list[str] = Field(alias="evidenceIds", max_length=60)
    missing_information: list[str] = Field(alias="missingInformation", max_length=20)


class NativeResearchCall(ApiModel):
    call_id: str = Field(alias="callId", min_length=1, max_length=256, strict=True)
    item_id: str = Field(alias="itemId", min_length=1, max_length=256, strict=True)
    name: Literal["kb_read", "kb_search"]
    arguments_text: str = Field(alias="argumentsText", min_length=2, max_length=16 * 1024, strict=True)
    host_call_id: str = Field(alias="hostCallId", pattern=r"^pi_[a-f0-9]{64}$")


class NativeResearchReplay(ApiModel):
    version: Literal[1]
    calls: list[NativeResearchCall] = Field(min_length=1, max_length=6)

    @model_validator(mode="after")
    def unique_calls(self):
        for field in ("call_id", "item_id", "host_call_id"):
            values = [getattr(call, field) for call in self.calls]
            if len(values) != len(set(values)):
                raise ValueError("Native call identifiers must be unique.")
        return self


class NativeResearchReplayV2(ApiModel):
    version: Literal[2]
    calls: list[NativeResearchCall] = Field(max_length=6)
    output_items: list[dict[str, Any]] = Field(alias="outputItems", min_length=1, max_length=64)

    @field_validator("output_items", mode="before")
    @classmethod
    def raw_items(cls, value):
        from frag_api.providers.response_items import validate_output_items
        try:
            return validate_output_items(value)
        except (ValueError, TypeError, RecursionError, UnicodeError) as error:
            raise ValueError("Invalid raw Responses output items") from error

    @model_validator(mode="after")
    def unique_calls(self):
        for field in ("call_id", "item_id", "host_call_id"):
            values = [getattr(call, field) for call in self.calls]
            if len(values) != len(set(values)):
                raise ValueError("Native call identifiers must be unique.")
        return self


NativeResearchReplayRecord = Annotated[NativeResearchReplay | NativeResearchReplayV2, Field(discriminator="version")]


class ResearchDecision(ApiModel):
    action: Literal["continue", "finish"]
    tool_calls: list[ToolCall] = Field(alias="toolCalls", max_length=6)
    evidence_ids: list[str] = Field(alias="evidenceIds", max_length=60)
    missing_information: list[str] = Field(alias="missingInformation", max_length=20)

    @model_validator(mode="after")
    def complete_decision(self):
        if self.action == "continue" and (not self.tool_calls or self.evidence_ids):
            raise ValueError("Continue requires complete tool calls and no final evidence selection.")
        if self.action == "finish" and self.tool_calls:
            raise ValueError("Finish cannot propose tool execution.")
        for values in (self.evidence_ids, [call.call_id for call in self.tool_calls]):
            if any(not value for value in values) or len(values) != len(set(values)):
                raise ValueError("Decision identifiers must be nonempty and unique.")
        return self


class ResearchTurn(ApiModel):
    number: int = Field(ge=1, le=3)
    attempt_id: str = Field(alias="attemptId")
    status: Literal["model_pending", "tools_pending", "completed", "failed", "outcome_unknown"]
    decision: ResearchDecision | None = None
    error_code: str | None = Field(default=None, alias="errorCode")


class ResearchState(ApiModel):
    status: Literal["ready", "awaiting_context", "exhausted", "error", "outcome_unknown"] = "ready"
    turns: list[ResearchTurn] = Field(default_factory=list, max_length=3)
    selected_evidence_ids: list[str] = Field(default_factory=list, alias="selectedEvidenceIds")
    missing_information: list[str] = Field(default_factory=list, alias="missingInformation")
    max_turns: Literal[3] = Field(default=3, alias="maxTurns")
    max_tool_calls: Literal[6] = Field(default=6, alias="maxToolCalls")
    configuration_hash: str = Field(alias="configurationHash", min_length=64, max_length=64)


class ResearchPreview(ApiModel):
    run_id: str = Field(alias="runId")
    session_id: str = Field(alias="sessionId")
    stage: Literal["research", "context", "inference"]
    prepared_call: PreparedCall = Field(alias="preparedCall")
    fingerprint: str
    approval_token: str | None = Field(alias="approvalToken")
    can_approve: bool = Field(alias="canApprove")
    turn: int = Field(ge=1, le=3)
    max_turns: Literal[3] = Field(default=3, alias="maxTurns")
    warnings: list[str]
    context_fingerprint: str | None = Field(default=None, alias="contextFingerprint")


class ResearchStart(ApiModel):
    kind: Literal["harness", "rag"]
    source_request: dict = Field(alias="sourceRequest")


class ResearchExecute(ExplicitApproval):
    source_request: dict = Field(alias="sourceRequest")
    fingerprint: str = Field(min_length=64, max_length=64)
    approval_token: str = Field(alias="approvalToken", min_length=1)
