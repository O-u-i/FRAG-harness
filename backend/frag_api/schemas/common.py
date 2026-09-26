from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


ProviderKind = Literal["fake", "openai", "ollama"]


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class StageConfig(ApiModel):
    provider: ProviderKind
    model: str | None
    ready: bool


class HarnessConfig(ApiModel):
    context: StageConfig
    inference: StageConfig


class TokenBudget(ApiModel):
    estimated_input_tokens: int = Field(alias="estimatedInputTokens", ge=0)
    input_budget: int = Field(alias="inputBudget", gt=0)
    reserved_percent: int = Field(alias="reservedPercent", ge=0, le=100)
    context_output_limit: int = Field(alias="contextOutputLimit", gt=0)
    inference_output_limit: int = Field(alias="inferenceOutputLimit", gt=0)
    approximate: Literal[True] = True


class ProviderUsage(ApiModel):
    input_tokens: int | None = Field(default=None, alias="inputTokens", ge=0)
    output_tokens: int | None = Field(default=None, alias="outputTokens", ge=0)


class StageResult(ApiModel):
    provider: ProviderKind
    model: str
    usage: ProviderUsage
