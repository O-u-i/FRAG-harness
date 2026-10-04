"""Bounded evidence-collection decisions and durable, approval-free checkpoints."""
from typing import Literal
from pydantic import Field, model_validator
from frag_api.schemas.common import ApiModel, ExplicitApproval
from frag_api.schemas.governance import PreparedCall
from frag_api.schemas.tools import ToolCall


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
