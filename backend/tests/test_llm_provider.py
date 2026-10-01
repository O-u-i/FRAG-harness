import sys
from types import SimpleNamespace

from frag_api.providers.llm import LlmStageSettings, OpenAICompatibleProvider
from frag_api.schemas.rag import RagContextCompression, RagEvidence


def test_openai_context_uses_backend_only_key_and_no_storage(monkeypatch):
    captured = {}
    class Responses:
        def parse(self, **kwargs):
            captured["request"] = kwargs
            return SimpleNamespace(output_parsed=RagContextCompression(
                evidence=[{"evidenceId": "selected", "summary": "Synthetic fact", "preservedFacts": ["Synthetic fact"], "uncertainty": []}],
                missingInformation=[]), usage=SimpleNamespace(input_tokens=12, output_tokens=8))
    def constructor(**kwargs):
        captured["client"] = kwargs
        return SimpleNamespace(responses=Responses())
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=constructor))
    provider = OpenAICompatibleProvider(LlmStageSettings(
        provider="openai", model="test-model", base_url=None, api_key="synthetic-backend-key", timeout_seconds=30))
    evidence = [RagEvidence(evidenceId="selected", documentId="doc", sourceId="source", locatorId="one",
                            locatorLabel="Finding", text="Synthetic fact")]
    result = provider.generate_rag_context(evidence, 1500)
    assert result.output.evidence[0].evidence_id == "selected"
    assert captured["client"]["api_key"] == "synthetic-backend-key"
    assert captured["request"]["store"] is False
    assert "synthetic-backend-key" not in str(captured["request"])
