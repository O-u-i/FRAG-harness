"""Exercise approvals, complete requests and policy at the existing runtime boundary."""
import json
from dataclasses import replace

import httpx
import pytest
from fastapi.testclient import TestClient

from frag_api.errors import RagFingerprintError, RagNotReadyError
from frag_api.main import create_app
from frag_api.providers.llm import FakeLlmProvider, LlmSettings, LlmStageSettings
from frag_api.providers.prepared import verify_prepared
from frag_api.schemas.harness import HarnessRequest, HarnessRunRequest
from frag_api.schemas.rag import InferenceRunRequest
from frag_api.services import governed_flow, model_preview
from frag_api.services.harness_service import HarnessService
from frag_api.services.context_source_service import ContextSourceService
from test_harness import selection
from test_llm_provider import mock_wire, response_body


def approve_context(client, body, preview):
    return client.post("/api/harness/run", json={**body, "contextFingerprint": preview["contextFingerprint"],
                                                "approvalToken": preview["approvalToken"], "approved": True})


def approve_inference(client, context):
    return client.post("/api/harness/inference/run", json={"contextFingerprint": context["preview"]["contextFingerprint"],
        "inferenceFingerprint": context["inferencePreview"]["inferenceFingerprint"],
        "approvalToken": context["inferencePreview"]["approvalToken"], "approved": True})


def test_both_approved_requests_match_actual_sdk_transport(monkeypatch, source_root, tmp_path):
    wire = []
    def handler(request):
        body = json.loads(request.content)
        payload = json.loads(body["input"])
        if "evidence" in payload:
            output = {"evidence": [{"evidenceId": item["evidenceId"], "summary": item["text"],
                                   "preservedFacts": [item["text"]], "uncertainty": []} for item in payload["evidence"]],
                      "missingInformation": []}
        else:
            evidence = payload["context"]["evidence"]
            output = {"answer": evidence[0]["summary"], "claims": [{"text": evidence[0]["summary"],
                      "evidenceIds": [evidence[0]["evidenceId"]]}], "missingInformation": [], "disclaimer": "Review first."}
        wire.append((str(request.url), body))
        return httpx.Response(200, json=response_body(output))
    mock_wire(monkeypatch, handler)
    context_settings = LlmStageSettings("openai", "synthetic-context", "https://context.example/v1/", "synthetic-key", 120)
    inference_settings = replace(context_settings, model="synthetic-inference", base_url="https://inference.example/v1/")
    harness = HarnessService(ContextSourceService(source_root), settings=LlmSettings(context_settings, inference_settings))
    app = create_app(context_source_root=source_root, harness_service=harness,
                     rag_index_path=tmp_path / "rag.sqlite3", plugin_root=tmp_path / "plugins")
    with TestClient(app, raise_server_exceptions=False) as client:
        body = selection(client)
        body["goal"] = 'Summarize Contact analyst@example.org password="synthetic secret with spaces" Unmarked synthetic-key'
        preview = client.post("/api/harness/preview", json=body).json()
        assert wire == []
        first = approve_context(client, body, preview)
        assert first.status_code == 200, first.text
        context = first.json()
        assert wire == [(preview["preparedCall"]["endpoint"], json.loads(preview["preparedCall"]["body"]))]
        for secret in ("synthetic secret with spaces", "synthetic-key", "analyst@example.org"):
            assert secret not in json.dumps(context)
        assert len(wire) == 1  # Inference is only prepared, never sent with the first approval.
        final = approve_inference(client, context)
        assert final.status_code == 200, final.text
        second = context["inferencePreview"]["preparedCall"]
        assert wire[1] == (second["endpoint"], json.loads(second["body"]))
        assert len(wire) == 2
        assert approve_context(client, body, preview).status_code == 409
        assert approve_inference(client, context).status_code == 409
        assert len(wire) == 2


@pytest.mark.parametrize("change", ["goal", "checklist", "scope", "body", "fingerprint"])
def test_tampered_request_or_expanded_source_is_rejected(client, change):
    body = selection(client)
    preview = client.post("/api/harness/preview", json=body).json()
    if change == "goal":
        body["goal"] = "A changed goal"
    elif change == "checklist":
        body["task"] = {"templateId": "evidence-review-v1", "checklist": [{"id": "critical", "text": "Check support",
                       "blocking": True, "status": "met", "reviewed": True}]}
    elif change == "scope":
        body["fileSelections"][0]["locatorIds"].append("section-2")
    elif change == "body":
        body["preparedCall"] = {**preview["preparedCall"], "body": '{}'}
    else:
        preview["contextFingerprint"] = "0" * 64
    result = approve_context(client, body, preview)
    assert result.status_code in (409, 422)


def test_mutating_returned_preview_does_not_mutate_server_owned_call(client):
    service = client.app.state.harness_service
    body = HarnessRequest.model_validate(selection(client))
    preview = service.preview(body)
    original_text = preview.candidate_evidence[0].text
    preview.candidate_evidence[0].text = "Unapproved changed text"
    preview.input = '{"unapproved":true}'
    result = service.run(HarnessRunRequest(**body.model_dump(), contextFingerprint=preview.context_fingerprint,
                                         approvalToken=preview.approval_token, approved=True))
    assert result.preview.candidate_evidence[0].text == original_text
    assert result.compressed_context.evidence[0].summary == original_text


@pytest.mark.parametrize("field", ["model", "endpoint", "body", "timeout_seconds", "binding"])
def test_prepared_call_field_changes_fail_integrity_check(client, field):
    service = client.app.state.harness_service
    call = service.preview(HarnessRequest.model_validate(selection(client))).prepared_call
    value = 1.0 if field == "timeout_seconds" else '{}'
    changed = call.model_copy(update={field: value})
    with pytest.raises(RagFingerprintError):
        verify_prepared(changed, service.settings.context)


def test_context_prompt_and_inference_prompt_changes_invalidate_approval(client, monkeypatch):
    body = selection(client)
    preview = client.post("/api/harness/preview", json=body).json()
    old = model_preview.context_input
    monkeypatch.setattr(model_preview, "context_input", lambda evidence: ("Changed host instructions", old(evidence)[1]))
    assert approve_context(client, body, preview).status_code == 409
    monkeypatch.setattr(model_preview, "context_input", old)
    fresh = client.post("/api/harness/preview", json=body).json()
    context = approve_context(client, body, fresh).json()
    previous = governed_flow.inference_input
    monkeypatch.setattr(governed_flow, "inference_input", lambda *args: ("Changed Inference instructions", previous(*args)[1]))
    assert approve_inference(client, context).status_code == 409


@pytest.mark.parametrize(("status", "reviewed"), [("pending", False), ("met", False), ("missing", True), ("unknown", True)])
def test_blocking_checklist_never_issues_usable_approval(client, status, reviewed):
    body = selection(client)
    body["task"] = {"templateId": "evidence-review-v1", "checklist": [{"id": "critical", "text": "Check support",
                   "blocking": True, "status": status, "reviewed": reviewed}]}
    preview = client.post("/api/harness/preview", json=body).json()
    assert preview["canApprove"] is False and preview["approvalToken"] == ""
    preview["approvalToken"] = "not-an-issued-token-" * 3
    assert approve_context(client, body, preview).status_code == 409


def test_nonblocking_gap_remains_missing_and_source_quality_is_explicit(client):
    body = selection(client)
    body["task"] = {"templateId": "evidence-review-v1", "checklist": [{"id": "ordinary", "text": "Unknown freshness",
                   "blocking": False, "status": "unknown", "reviewed": False}]}
    preview = client.post("/api/harness/preview", json=body).json()
    assert preview["canApprove"] is True
    assert preview["task"]["checklist"][0]["status"] == "unknown"
    quality = preview["sourceBindings"][0]["assessment"]
    assert quality["authority"] == quality["freshness"] == {"status": "unknown", "detail": None}
    assert quality["provenance"]["status"] == "known"
    assert approve_context(client, body, preview).status_code == 200


def test_unknown_provider_fails_closed(monkeypatch):
    monkeypatch.setenv("FRAG_CONTEXT_LLM_PROVIDER", "typo-provider")
    with pytest.raises(RagNotReadyError):
        LlmSettings.from_environment()
