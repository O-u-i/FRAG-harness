import pytest

from frag_api.providers.llm import LlmCallResult
from frag_api.schemas.common import ProviderUsage
from frag_api.schemas.rag import RagContextCompression
from frag_api.services import model_preview
from test_governance import approve_context
from test_harness import selection


@pytest.mark.parametrize("value", [1, "true", False])
def test_approval_requires_explicit_boolean_true(client, value):
    body = selection(client)
    preview = client.post("/api/harness/preview", json=body).json()
    request = {**body, "contextFingerprint": preview["contextFingerprint"], "approvalToken": preview["approvalToken"], "approved": value}
    assert client.post("/api/harness/run", json=request).status_code == 422
    assert approve_context(client, body, preview).status_code == 200


@pytest.mark.parametrize("ids", [[], ["foreign"], ["selected", "selected"]])
def test_context_dropped_foreign_or_duplicate_id_is_invalid(client, ids):
    class InvalidContext:
        def execute_prepared(self, call):
            allowed = call.request_body_input()["evidence"][0]["evidenceId"]
            returned = [allowed if item == "selected" else item for item in ids]
            return LlmCallResult(RagContextCompression(evidence=[{
                "evidenceId": item, "summary": "Synthetic fact", "preservedFacts": [], "uncertainty": []
            } for item in returned], missingInformation=[]), ProviderUsage(inputTokens=1, outputTokens=1))
    client.app.state.harness_service.context_provider = InvalidContext()
    body = selection(client)
    preview = client.post("/api/harness/preview", json=body).json()
    response = approve_context(client, body, preview)
    assert response.status_code == 502 and response.json()["error"]["code"] == "INVALID_LLM_OUTPUT"


def test_schema_change_invalidates_old_preview(client, monkeypatch):
    body = selection(client)
    preview = client.post("/api/harness/preview", json=body).json()
    previous = model_preview.context_input
    def changed_schema(evidence):
        instructions, payload = previous(evidence)
        payload["outputSchema"] = {"type": "object", "additionalProperties": False}
        return instructions, payload
    monkeypatch.setattr(model_preview, "context_input", changed_schema)
    assert approve_context(client, body, preview).status_code == 409


def test_windows_path_case_alias_cannot_duplicate_a_selected_file(client):
    body = selection(client)
    body["fileSelections"].append({**body["fileSelections"][0], "relativePath": "EVIDENCE.md"})
    response = client.post("/api/harness/preview", json=body)
    assert response.status_code == 422


def test_rag_preview_uses_matching_rows_and_cached_parents_from_one_snapshot(client, monkeypatch):
    from frag_api.schemas.rag import RagDatasetRequest, RagQueryRequest
    service = client.app.state.rag_service
    service.rebuild(RagDatasetRequest(datasetId="synthetic-risk-review-v1"))
    monkeypatch.setattr(service.repository, "parent", lambda _id: (_ for _ in ()).throw(AssertionError("Live parent read after snapshot")))
    preview = service.preview(RagQueryRequest(datasetId="synthetic-risk-review-v1", query="regulatory restrictions", topK=1))
    assert preview.candidate_evidence and preview.source_bindings[0].revision == preview.index_revision


def test_validation_errors_do_not_echo_synthetic_secret_field_names(client):
    body = selection(client)
    body['password="synthetic diagnostic with spaces"'] = "unused"
    response = client.post("/api/harness/preview", json=body)
    assert response.status_code == 422 and "synthetic diagnostic" not in response.text
