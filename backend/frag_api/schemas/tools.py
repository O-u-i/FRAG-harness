"""Selected KB read contracts; scope is host-owned, never supplied as authority."""
from typing import Literal
from pydantic import Field, model_validator
from frag_api.schemas.common import ApiModel
from frag_api.schemas.governance import FrozenModel, SourceIdentity
from frag_api.schemas.rag import RagEvidence


class SelectedArguments(FrozenModel):
    identity: SourceIdentity
    revision: str = Field(min_length=1, max_length=128)
    locator_ids: tuple[str, ...] = Field(alias="locatorIds", min_length=1, max_length=200)

    @model_validator(mode="after")
    def unique_locators(self):
        if any(not item for item in self.locator_ids) or len(set(self.locator_ids)) != len(self.locator_ids):
            raise ValueError("Selected locators must be nonempty and unique.")
        return self


class SearchArguments(SelectedArguments):
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=3, ge=1, le=10, strict=True)


class ReadArguments(SelectedArguments):
    evidence_ids: tuple[str, ...] = Field(alias="evidenceIds", min_length=1, max_length=10)

    @model_validator(mode="after")
    def unique_evidence(self):
        if any(not item for item in self.evidence_ids) or len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("Selected evidence identifiers must be nonempty and unique.")
        return self


class ToolCall(FrozenModel):
    call_id: str = Field(alias="callId", pattern=r"^[A-Za-z0-9_-]{1,80}$")
    name: str = Field(pattern=r"^[a-z][a-z0-9_.-]{1,79}$")
    arguments: dict


class ToolResult(ApiModel):
    call_id: str = Field(alias="callId", min_length=1, max_length=80)
    evidence: list[RagEvidence]
    missing_information: list[str] = Field(alias="missingInformation", max_length=20)


class ReadCarrierInput(ApiModel):
    call_id: str = Field(alias="callId", min_length=1, max_length=80)
    arguments: ReadArguments
    evidence: list[RagEvidence]


class ToolCallRecord(ApiModel):
    call_id: str = Field(alias="callId")
    name: str
    tool_version: str = Field(alias="toolVersion")
    carrier: Literal["native", "cli"]
    arguments: dict
    status: Literal["dispatching", "completed", "failed", "outcome_unknown"]
    created_at: str = Field(alias="createdAt")
    finished_at: str | None = Field(default=None, alias="finishedAt")
    duration_ms: int | None = Field(default=None, alias="durationMs", ge=0)
    result: ToolResult | None = None
    error_code: str | None = Field(default=None, alias="errorCode")

    @model_validator(mode="after")
    def bound_result(self):
        if (self.status == "completed") != (self.result is not None):
            raise ValueError("Only a completed call owns a result.")
        if self.result is not None and self.result.call_id != self.call_id:
            raise ValueError("Result and owning call identifiers must match.")
        return self


class ToolExecutionRequest(ApiModel):
    source_request: dict = Field(alias="sourceRequest")
    call: ToolCall
