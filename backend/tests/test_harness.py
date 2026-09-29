from pathlib import Path

from fastapi.testclient import TestClient
from frag_api.providers.llm import LlmCallResult
from frag_api.schemas.common import ProviderUsage
from frag_api.schemas.rag import RagGroundedAnswer


def selection(client: TestClient) -> dict:
    inventory = client.get("/api/context-sources/files")
    assert inventory.status_code == 200
    assert len(inventory.json()) == 1
    inspected = client.post("/api/context-sources/files/inspect", json={"relativePath": "evidence.md"})
    assert inspected.status_code == 200
    locator = inspected.json()["locators"][0]["id"]
    return {"goal": "Explain the finding", "fileSelections": [{"relativePath": "evidence.md", "locatorIds": [locator], "relevanceReason": "Selected for review"}]}


def test_core_starts_without_finance_core(client: TestClient):
    assert client.get("/api/health").json() == {"status": "ok", "service": "frag-harness", "serviceVersion": "1.1.0"}
    assert client.get("/api/harness/config").json()["context"]["provider"] == "fake"
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/harness/preview" in paths
    assert "/api/plugins/finance-core/dashboard" not in paths
    assert not any("finance" in path for path in paths)
    assert client.get("/api/plugins").json()["plugins"][0]["installed"] is False


def test_preview_redacts_and_approval_is_single_use(client: TestClient, source_root: Path):
    (source_root / "evidence.md").write_text("# Finding\nA synthetic finding. Password=do-not-send\nContact analyst@example.org", encoding="utf-8")
    body = selection(client)
    preview = client.post("/api/harness/preview", json=body)
    assert preview.status_code == 200, preview.text
    value = preview.json()
    outbound = str(value["candidateEvidence"])
    assert "do-not-send" not in outbound and "analyst@example.org" not in outbound
    run_body = {**body, "contextFingerprint": value["contextFingerprint"], "approvalToken": value["approvalToken"], "approved": True}
    run = client.post("/api/harness/run", json=run_body)
    assert run.status_code == 200, run.text
    assert run.json()["contextStage"]["provider"] == "fake"
    assert "inferenceStage" not in run.json()
    second = run.json()["inferencePreview"]
    assert "[REDACTED_SECRET]" in second["input"]
    assert "do-not-send" not in second["input"]
    inference_body = {"contextFingerprint": value["contextFingerprint"], "inferenceFingerprint": second["inferenceFingerprint"],
                      "approvalToken": second["approvalToken"], "approved": True}
    final = client.post("/api/harness/inference/run", json=inference_body)
    assert final.status_code == 200, final.text
    assert final.json()["inferenceStage"]["provider"] == "fake"
    allowed = {e["chunkId"] for e in value["candidateEvidence"]}
    assert {c for claim in final.json()["result"]["claims"] for c in claim["chunkIds"]} <= allowed
    assert client.post("/api/harness/run", json=run_body).status_code == 409
    assert client.post("/api/harness/inference/run", json=inference_body).status_code == 409


def test_changed_source_rejects_previous_approval(client: TestClient, source_root: Path):
    body = selection(client)
    preview = client.post("/api/harness/preview", json=body).json()
    (source_root / "evidence.md").write_text("# Finding\nChanged evidence.", encoding="utf-8")
    run = client.post("/api/harness/run", json={**body, "contextFingerprint": preview["contextFingerprint"], "approvalToken": preview["approvalToken"], "approved": True})
    assert run.status_code in (409, 422)


def test_source_paths_are_confined(client: TestClient):
    assert client.post("/api/context-sources/files/inspect", json={"relativePath": "../outside.txt"}).status_code == 422


def test_foreign_citation_is_rejected(client: TestClient):
    class InvalidInference:
        def generate_rag_answer(self, *_args):
            return LlmCallResult(RagGroundedAnswer(
                answer="Unverified answer", claims=[{"text": "Unverified", "chunkIds": ["foreign-chunk"]}],
                missingInformation=[], disclaimer="Review first"), ProviderUsage(inputTokens=1, outputTokens=1))
    client.app.state.harness_service.inference_provider = InvalidInference()
    body = selection(client)
    preview = client.post("/api/harness/preview", json=body).json()
    context = client.post("/api/harness/run", json={**body, "contextFingerprint": preview["contextFingerprint"],
                                                      "approvalToken": preview["approvalToken"], "approved": True}).json()
    second = context["inferencePreview"]
    run = client.post("/api/harness/inference/run", json={"contextFingerprint": preview["contextFingerprint"],
        "inferenceFingerprint": second["inferenceFingerprint"], "approvalToken": second["approvalToken"], "approved": True})
    assert run.status_code == 502
    assert run.json()["error"]["code"] == "INVALID_LLM_OUTPUT"


def test_changed_source_blocks_second_stage(client: TestClient, source_root: Path):
    body = selection(client)
    preview = client.post("/api/harness/preview", json=body).json()
    context = client.post("/api/harness/run", json={**body, "contextFingerprint": preview["contextFingerprint"],
        "approvalToken": preview["approvalToken"], "approved": True}).json()
    (source_root / "evidence.md").write_text("# Finding\nChanged after Context.", encoding="utf-8")
    second = context["inferencePreview"]
    result = client.post("/api/harness/inference/run", json={"contextFingerprint": preview["contextFingerprint"],
        "inferenceFingerprint": second["inferenceFingerprint"], "approvalToken": second["approvalToken"], "approved": True})
    assert result.status_code == 409
