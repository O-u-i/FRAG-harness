"""Native carrier metadata; model requests and outputs remain runtime records."""
from typing import Any, Literal
from pydantic import Field, ConfigDict
from frag_api.schemas.common import ApiModel, ExplicitApproval


class AgentTurn(ApiModel):
    id: str
    text: str
    created_at: str = Field(alias="createdAt")
    state: Literal["running", "complete", "cancelled"] = "running"
    run_id: str | None = Field(default=None, alias="runId")
    model_id: str | None = Field(default=None, alias="modelId")


class AgentSession(ApiModel):
    session_id: str = Field(alias="sessionId")
    resource: str
    version: int = 1
    turns: list[AgentTurn] = Field(default_factory=list)
    model_id: str | None = Field(default=None, alias="modelId")


class BridgeModel(ApiModel):
    id: str = Field(min_length=1, max_length=300)
    name: str = Field(min_length=1, max_length=200)
    vendor: str = Field(min_length=1, max_length=100)
    revision: str = Field(pattern=r"^[a-f0-9]{64}$")
    effort: str | None = Field(default=None, max_length=30)
    max_input_tokens: int = Field(alias="maxInputTokens", gt=0)


class AgentCheck(ApiModel):
    model_config = ConfigDict(extra="forbid", strict=True, populate_by_name=True)
    version: int = Field(ge=1)
    turn_id: str = Field(alias="turnId", min_length=1, max_length=128)


class AgentPrepare(AgentCheck):
    kind: Literal["harness", "rag"]
    source_request: dict[str, Any] = Field(alias="sourceRequest")
    research: bool = False


class AgentExecute(ExplicitApproval):
    version: int = Field(ge=1, strict=True)
    turn_id: str = Field(alias="turnId", min_length=1, max_length=128)
    run_id: str = Field(alias="runId", max_length=64)
    run_version: int = Field(alias="runVersion", ge=1, strict=True)
    fingerprint: str = Field(min_length=64, max_length=64)
    approval_token: str = Field(alias="approvalToken", min_length=32, max_length=128)
