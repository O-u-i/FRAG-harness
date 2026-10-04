from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel, ValidationError

from frag_api.errors import (
    RagIncompleteError, RagNotReadyError, RagOutcomeUnknownError, RagOutputError,
    RagProviderError, RagRefusalError,
)
from frag_api.providers.prepared import output_model_for, verify_prepared
from frag_api.request_spec import strict_json
from frag_api.schemas.common import ProviderKind, ProviderUsage
from frag_api.schemas.governance import PreparedCall
from frag_api.schemas.rag import (
    RagClaim, RagCompressedEvidence, RagContextCompression, RagEvidence,
    RagGroundedAnswer,
)

@dataclass(frozen=True)
class LlmStageSettings:
    provider: ProviderKind
    model: str
    base_url: str | None
    api_key: str | None
    timeout_seconds: float
    adapter: str = "native"

    @property
    def ready(self) -> bool:
        if self.adapter == "pi":
            from frag_api.providers.pi_process import worker_ready
            return self.provider == "openai" and bool(self.api_key) and worker_ready(self.model, self.base_url)
        if self.provider == "fake":
            return True
        if not self.model:
            return False
        return bool(self.api_key) if self.provider == "openai" else bool(self.base_url)


@dataclass(frozen=True)
class LlmSettings:
    context: LlmStageSettings
    inference: LlmStageSettings
    research: LlmStageSettings | None = None

    @classmethod
    def from_environment(cls) -> "LlmSettings":
        timeout = float(os.environ.get("FRAG_LLM_TIMEOUT_SECONDS", "120"))

        def stage(name: str) -> LlmStageSettings:
            prefix = f"FRAG_{name}_LLM"
            provider = os.environ.get(f"{prefix}_PROVIDER", "fake").lower()
            adapter = os.environ.get(f"{prefix}_ADAPTER", "native").lower()
            if adapter not in {"native", "pi"} or (adapter == "pi" and provider != "openai"):
                raise RagNotReadyError()
            if provider not in {"fake", "openai", "ollama"}:
                raise RagNotReadyError()
            base_url = os.environ.get(f"{prefix}_BASE_URL")
            if provider == "ollama" and not base_url:
                base_url = "http://127.0.0.1:11434/v1/"
            return LlmStageSettings(
                provider=provider,  # type: ignore[arg-type]
                model=os.environ.get(f"{prefix}_MODEL", f"fake-{name.lower()}-v1" if provider == "fake" else ""),
                base_url=base_url,
                api_key=os.environ.get("OPENAI_API_KEY") if provider == "openai" else "ollama",
                timeout_seconds=timeout,
                adapter=adapter,
            )

        return cls(context=stage("CONTEXT"), inference=stage("INFERENCE"), research=stage("RESEARCH"))


@dataclass(frozen=True)
class LlmCallResult:
    output: BaseModel
    usage: ProviderUsage
    native_replay: dict | None = None


class LlmProvider(Protocol):
    def execute_prepared(self, call: PreparedCall) -> LlmCallResult: ...


class FakeLlmProvider:
    def execute_prepared(self, call: PreparedCall) -> LlmCallResult:
        output_model_for(call)
        payload = json.loads(call.request_body()["input"])
        if call.purpose == "research":
            from frag_api.schemas.research import ResearchDecision
            observed = sorted({row["evidenceId"] for tool in payload["observations"]
                               if tool.get("result") for row in tool["result"]["evidence"]})
            if observed:
                decision = ResearchDecision(action="finish", toolCalls=[], evidenceIds=observed, missingInformation=[])
            else:
                source = payload["manifest"][0]
                decision = ResearchDecision(action="continue", toolCalls=[{
                    "callId":f"fake-read-{payload['turn']}", "name":"kb.read", "arguments":{
                        "identity":source["identity"], "revision":source["revision"],
                        "locatorIds":source["locatorIds"], "evidenceIds":source["evidenceIds"][:10]}}],
                    evidenceIds=[], missingInformation=[])
            return LlmCallResult(decision, ProviderUsage(inputTokens=120, outputTokens=80))
        if call.purpose == "context":
            result = self.generate_rag_context([RagEvidence.model_validate(item) for item in payload["evidence"]],
                                               call.request_body()["max_output_tokens"])
        else:
            result = self.generate_rag_answer(RagContextCompression.model_validate(payload["context"]),
                                              payload["query"], call.request_body()["max_output_tokens"])
        result.output.missing_information = list(dict.fromkeys(result.output.missing_information + payload.get("researchMissingInformation", [])))
        return result

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

    def execute_prepared(self, call: PreparedCall) -> LlmCallResult:
        verify_prepared(call, self.settings)
        output_model = output_model_for(call)
        try:
            import httpx
            from openai import OpenAI

            # Explicit base_url prevents SDK environment routing. Redirects cannot change the approved endpoint.
            with httpx.Client(follow_redirects=False, trust_env=False) as transport:
                with OpenAI(api_key=self.settings.api_key, base_url=call.endpoint.removesuffix("responses"),
                            timeout=call.timeout_seconds, max_retries=call.max_retries,
                            http_client=transport) as client:
                    response = client.responses.create(**call.request_body())
            if any(getattr(content, "type", None) == "refusal" for item in getattr(response, "output", [])
                   for content in getattr(item, "content", [])):
                raise RagRefusalError()
            if getattr(response, "status", None) == "incomplete":
                raise RagIncompleteError()
            if getattr(response, "status", None) != "completed":
                raise RagOutputError()
            parsed = output_model.model_validate(strict_json(response.output_text))
            usage = getattr(response, "usage", None)
            return LlmCallResult(parsed, ProviderUsage(
                inputTokens=getattr(usage, "input_tokens", None),
                outputTokens=getattr(usage, "output_tokens", None),
            ))
        except (ValueError, TypeError, ValidationError) as error:
            raise RagOutputError() from error
        except RagOutputError:
            raise
        except Exception as error:
            # Timeout/connection errors cannot prove whether an external request was executed.
            if error.__class__.__name__ in {"APITimeoutError", "APIConnectionError", "ReadTimeout", "ConnectError"}:
                raise RagOutcomeUnknownError() from error
            raise RagProviderError() from error


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
    if settings.adapter == "pi":
        from frag_api.providers.pi import PiProvider
        return PiProvider(settings)
    return FakeLlmProvider() if settings.provider == "fake" else OpenAICompatibleProvider(settings)
