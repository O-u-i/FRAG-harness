import json
from dataclasses import replace

import httpx
import openai
import pytest

from frag_api.errors import RagIncompleteError, RagOutcomeUnknownError, RagOutputError, RagRefusalError
from frag_api.providers.llm import LlmStageSettings, OpenAICompatibleProvider, context_input
from frag_api.providers.prepared import prepare_call
from frag_api.schemas.rag import RagContextCompression, RagEvidence


def response_body(output: dict, *, status="completed", refusal=False) -> dict:
    content = {"type": "refusal", "refusal": "Synthetic refusal"} if refusal else {
        "type": "output_text", "text": json.dumps(output), "annotations": []}
    return {"id": "resp_synthetic", "object": "response", "created_at": 0, "model": "test-model",
            "status": status, "output": [{"id": "msg_synthetic", "type": "message", "role": "assistant",
                                         "status": "completed", "content": [content]}],
            "usage": {"input_tokens": 12, "output_tokens": 8, "total_tokens": 20}}


def mock_wire(monkeypatch, handler):
    original = openai.OpenAI
    constructors = []
    def constructor(**kwargs):
        constructors.append({key: value for key, value in kwargs.items() if key != "http_client"})
        kwargs["http_client"] = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
        return original(**kwargs)
    monkeypatch.setattr(openai, "OpenAI", constructor)
    return constructors


def prepared_context(settings):
    evidence = [RagEvidence(evidenceId="selected", documentId="doc", sourceId="source", locatorId="one",
                            locatorLabel="Finding", text="Synthetic fact")]
    instructions, payload = context_input(evidence)
    return prepare_call(settings=settings, purpose="context", instructions=instructions, payload=payload,
                        output_model=RagContextCompression, max_output_tokens=1500, binding={})


SETTINGS = LlmStageSettings(provider="openai", model="test-model", base_url=None,
                            api_key="synthetic-backend-key", timeout_seconds=30)
OUTPUT = {"evidence": [{"evidenceId": "selected", "summary": "Synthetic fact",
                         "preservedFacts": ["Synthetic fact"], "uncertainty": []}], "missingInformation": []}


def test_openai_context_uses_backend_only_key_and_no_storage(monkeypatch):
    captured = []
    def handler(request):
        captured.append(request)
        return httpx.Response(200, json=response_body(OUTPUT))
    clients = mock_wire(monkeypatch, handler)
    # Neither SDK environment settings nor redirects can silently replace the approved route.
    monkeypatch.setenv("OPENAI_BASE_URL", "https://unapproved.example/v1/")
    call = prepared_context(SETTINGS)
    result = OpenAICompatibleProvider(SETTINGS).execute_prepared(call)
    assert result.output.evidence[0].evidence_id == "selected"
    assert len(captured) == 1 and str(captured[0].url) == call.endpoint
    assert json.loads(captured[0].content) == call.request_body()
    assert captured[0].headers["Authorization"] == "Bearer synthetic-backend-key"
    assert clients[0]["max_retries"] == 0 and clients[0]["timeout"] == call.timeout_seconds
    assert call.request_body()["store"] is False
    assert "synthetic-backend-key" not in call.model_dump_json()
    assert call.request_body()["text"]["format"]["schema"] == RagContextCompression.model_json_schema(by_alias=True)


@pytest.mark.parametrize(("status", "refusal", "output", "failure"), [
    ("incomplete", False, OUTPUT, RagIncompleteError),
    ("completed", True, OUTPUT, RagRefusalError),
    ("completed", False, {"extra": "password=synthetic-diagnostic"}, RagOutputError),
])
def test_provider_failures_are_explicit_without_retry(monkeypatch, status, refusal, output, failure):
    attempts = []
    def handler(request):
        attempts.append(request)
        return httpx.Response(200, json=response_body(output, status=status, refusal=refusal))
    mock_wire(monkeypatch, handler)
    with pytest.raises(failure):
        OpenAICompatibleProvider(SETTINGS).execute_prepared(prepared_context(SETTINGS))
    assert len(attempts) == 1


def test_timeout_outcome_is_unknown_and_is_not_retried(monkeypatch):
    attempts = []
    def handler(request):
        attempts.append(request)
        raise httpx.ReadTimeout("Synthetic timeout", request=request)
    mock_wire(monkeypatch, handler)
    with pytest.raises(RagOutcomeUnknownError):
        OpenAICompatibleProvider(SETTINGS).execute_prepared(prepared_context(SETTINGS))
    assert len(attempts) == 1


def test_ollama_dispatches_the_same_prepared_body(monkeypatch):
    captured = []
    def handler(request):
        captured.append(request)
        return httpx.Response(200, json=response_body(OUTPUT))
    mock_wire(monkeypatch, handler)
    settings = replace(SETTINGS, provider="ollama", base_url="http://127.0.0.1:11434/v1/", api_key="ollama")
    call = prepared_context(settings)
    assert OpenAICompatibleProvider(settings).execute_prepared(call).output.evidence[0].evidence_id == "selected"
    assert str(captured[0].url) == call.endpoint and json.loads(captured[0].content) == call.request_body()
