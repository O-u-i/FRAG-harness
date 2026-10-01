from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from frag_api.errors import RagOutputError, RagProviderError
from frag_api.schemas.common import ProviderKind, ProviderUsage
from frag_api.schemas.rag import (
    RagClaim, RagCompressedEvidence, RagContextCompression, RagEvidence,
    RagGroundedAnswer,
)

OutputModel = TypeVar("OutputModel", bound=BaseModel)


@dataclass(frozen=True)
class LlmStageSettings:
    provider: ProviderKind
    model: str
    base_url: str | None
    api_key: str | None
    timeout_seconds: float

    @property
    def ready(self) -> bool:
        if self.provider == "fake":
            return True
        if not self.model:
            return False
        return bool(self.api_key) if self.provider == "openai" else bool(self.base_url)


@dataclass(frozen=True)
class LlmSettings:
    context: LlmStageSettings
    inference: LlmStageSettings

    @classmethod
    def from_environment(cls) -> "LlmSettings":
        timeout = float(os.environ.get("FRAG_LLM_TIMEOUT_SECONDS", "120"))

        def stage(name: str) -> LlmStageSettings:
            prefix = f"FRAG_{name}_LLM"
            provider = os.environ.get(f"{prefix}_PROVIDER", "fake").lower()
            if provider not in {"fake", "openai", "ollama"}:
                provider = "fake"
            base_url = os.environ.get(f"{prefix}_BASE_URL")
            if provider == "ollama" and not base_url:
                base_url = "http://127.0.0.1:11434/v1/"
            return LlmStageSettings(
                provider=provider,  # type: ignore[arg-type]
                model=os.environ.get(f"{prefix}_MODEL", f"fake-{name.lower()}-v1" if provider == "fake" else ""),
                base_url=base_url,
                api_key=os.environ.get("OPENAI_API_KEY") if provider == "openai" else "ollama",
                timeout_seconds=timeout,
            )

        return cls(context=stage("CONTEXT"), inference=stage("INFERENCE"))


@dataclass(frozen=True)
class LlmCallResult:
    output: BaseModel
    usage: ProviderUsage


class LlmProvider(Protocol):
    def generate_rag_context(self, evidence: list[RagEvidence], max_output_tokens: int) -> LlmCallResult: ...
    def generate_rag_answer(self, compressed: RagContextCompression, query: str, max_output_tokens: int) -> LlmCallResult: ...


class FakeLlmProvider:
    def generate_rag_context(self, evidence: list[RagEvidence], max_output_tokens: int) -> LlmCallResult:
        output = RagContextCompression(
            evidence=[RagCompressedEvidence(
                evidenceId=item.evidence_id, summary=item.text,
                preservedFacts=[item.text], uncertainty=[],
            ) for item in evidence],
            missingInformation=[],
        )
        return LlmCallResult(output, ProviderUsage(inputTokens=120, outputTokens=80))

    def generate_rag_answer(self, compressed: RagContextCompression, query: str, max_output_tokens: int) -> LlmCallResult:
        output = RagGroundedAnswer(
            answer=" ".join(item.summary for item in compressed.evidence),
            claims=[RagClaim(text=item.summary, evidenceIds=[item.evidence_id]) for item in compressed.evidence],
            missingInformation=compressed.missing_information,
            disclaimer="Review the cited evidence before relying on this answer.",
        )
        return LlmCallResult(output, ProviderUsage(inputTokens=90, outputTokens=70))


class OpenAICompatibleProvider:
    def __init__(self, settings: LlmStageSettings):
        self.settings = settings

    def _generate(self, instructions: str, payload: dict, output_model: type[OutputModel], max_output_tokens: int) -> LlmCallResult:
        try:
            from openai import OpenAI

            client = OpenAI(
                api_key=self.settings.api_key,
                base_url=self.settings.base_url,
                timeout=self.settings.timeout_seconds,
                max_retries=0,
            )
            request = {
                "model": self.settings.model,
                "instructions": instructions,
                "input": json.dumps(payload, ensure_ascii=False),
                "max_output_tokens": max_output_tokens,
            }
            if self.settings.provider == "openai":
                response = client.responses.parse(**request, store=False, text_format=output_model)
                parsed = response.output_parsed
                if parsed is None:
                    raise RagOutputError()
            else:
                response = client.responses.create(**request)
                parsed = output_model.model_validate(json.loads(response.output_text))
            usage = getattr(response, "usage", None)
            return LlmCallResult(parsed, ProviderUsage(
                inputTokens=getattr(usage, "input_tokens", None),
                outputTokens=getattr(usage, "output_tokens", None),
            ))
        except (json.JSONDecodeError, ValidationError) as error:
            raise RagOutputError() from error
        except RagOutputError:
            raise
        except Exception as error:
            raise RagProviderError() from error

    def generate_rag_context(self, evidence: list[RagEvidence], max_output_tokens: int) -> LlmCallResult:
        instructions, payload = context_input(evidence)
        return self._generate(
            instructions,
            payload,
            RagContextCompression, max_output_tokens,
        )

    def generate_rag_answer(self, compressed: RagContextCompression, query: str, max_output_tokens: int) -> LlmCallResult:
        instructions, payload = inference_input(compressed, query)
        return self._generate(
            instructions,
            payload,
            RagGroundedAnswer, max_output_tokens,
        )


def context_input(evidence: list[RagEvidence]) -> tuple[str, dict]:
    """The exact instructions and JSON payload passed to the Context provider."""
    return (
        "Compress only supplied evidence. Preserve each evidenceId and qualifier. Do not invent sources.",
        {"evidence": [item.model_dump(by_alias=True) for item in evidence],
         "outputSchema": RagContextCompression.model_json_schema(by_alias=True)},
    )


def inference_input(compressed: RagContextCompression, query: str) -> tuple[str, dict]:
    """The exact instructions and JSON payload passed to the inference provider."""
    return (
        "Answer only from supplied evidence. Every claim must cite supplied evidenceIds. State uncertainty and missing information.",
        {"query": query, "context": compressed.model_dump(by_alias=True),
         "outputSchema": RagGroundedAnswer.model_json_schema(by_alias=True)},
    )


def provider_for(settings: LlmStageSettings) -> LlmProvider:
    return FakeLlmProvider() if settings.provider == "fake" else OpenAICompatibleProvider(settings)
