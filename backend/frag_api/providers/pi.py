"""Pi adapts one approved model request; the Python host retains all authority."""
from __future__ import annotations

from pydantic import ValidationError

from frag_api.errors import (RagIncompleteError, RagOutputError, RagOutcomeUnknownError,
                             RagProviderError, RagRefusalError)
from frag_api.providers.llm import LlmCallResult
from frag_api.providers.pi_process import execute_worker
from frag_api.providers.prepared import output_model_for, strict_json, verify_prepared
from frag_api.schemas.common import ProviderUsage
from frag_api.providers.response_items import SOL_MODEL, validate_sol_response

ERRORS = {"RAG_REFUSAL": RagRefusalError, "RAG_INCOMPLETE": RagIncompleteError,
          "RAG_OUTPUT_INVALID": RagOutputError, "RAG_PROVIDER_ERROR": RagProviderError,
          "RAG_OUTCOME_UNKNOWN": RagOutcomeUnknownError}


class PiProvider:
    def __init__(self, settings):
        self.settings = settings

    def execute_prepared(self, call) -> LlmCallResult:
        verify_prepared(call, self.settings)
        model = output_model_for(call)
        result = execute_worker(call, self.settings.api_key)
        if not result["ok"]:
            raise ERRORS.get(result["errorCode"], RagOutcomeUnknownError)()
        response = result["response"]
        try:
            keys = {"status", "outputText", "calls", "usage"} | ({"outputItems"} if call.model == SOL_MODEL else set())
            if (not isinstance(response, dict) or set(response) != keys
                    or response["status"] != "completed" or not isinstance(response["outputText"], str)
                    or not isinstance(response["calls"], list)):
                raise ValueError()
            usage = ProviderUsage.model_validate(response["usage"], strict=True)
            if usage.input_tokens is None or usage.output_tokens is None:
                raise ValueError()
            if call.purpose == "research":
                from frag_api.providers.research_native import normalize_pi_research
                output, replay = normalize_pi_research(call, response)
                return LlmCallResult(output, usage, native_replay=replay)
            if response["calls"]:
                raise ValueError()
            if call.model == SOL_MODEL:
                validate_sol_response(call, response)
            output = model.model_validate(strict_json(response["outputText"]))
            return LlmCallResult(output, usage)
        except (ValueError, TypeError, KeyError, ValidationError):
            raise RagOutputError() from None
