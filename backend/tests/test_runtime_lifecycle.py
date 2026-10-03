"""Controlled interleavings verify durable human decisions and carried budgets."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from fastapi.testclient import TestClient

from frag_api.errors import RagProviderError
from frag_api.providers.llm import LlmCallResult
from frag_api.schemas.common import ProviderUsage
from test_runtime_recovery import (
    CountingProvider, app_for, context_request, inference_request, preview,
    report, resume, selection,
)


@pytest.mark.parametrize("boundary", ["dispatching", "returned"])
@pytest.mark.parametrize("decision", ["paused", "rejected"])
def test_live_host_processing_cannot_resume_or_overwrite_human_control(
    tmp_path, source_root, monkeypatch, boundary, decision,
):
    provider = CountingProvider()
    entered, released = Event(), Event()
    with TestClient(app_for(tmp_path, source_root, provider), raise_server_exceptions=False) as client:
        source = selection(client)
        initial = preview(client, source)
        if boundary == "dispatching":
            execute = provider.execute_prepared
            def held_response(call):
                value = execute(call)
                entered.set()
                assert released.wait(10), "Synthetic response barrier timed out."
                return value
            monkeypatch.setattr(provider, "execute_prepared", held_response)
        else:
            returned = client.app.state.runtime.returned
            def held_host_checks(*args, **kwargs):
                value = returned(*args, **kwargs)
                entered.set()
                assert released.wait(10), "Synthetic validation barrier timed out."
                return value
            monkeypatch.setattr(client.app.state.runtime, "returned", held_host_checks)
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(client.post, "/api/harness/run", json=context_request(source, initial))
            try:
                assert entered.wait(5), "Model execution did not reach the controlled boundary."
                live = report(client, initial["runId"])
                assert live["requests"][0]["status"] == ("dispatching" if boundary == "dispatching" else "completed")
                assert live["context"] is None
                # A known return still being validated is not an available recovery checkpoint.
                before = len(live["requests"])
                assert resume(client, initial["runId"], source).status_code == 409
                assert len(report(client, initial["runId"])["requests"]) == before
                checklist = {"templateId": "evidence-review-v1", "checklist": []}
                assert client.post(f"/api/runtime/runs/{initial['runId']}/review", json={
                    "decision": "accepted", "checklist": checklist,
                }).status_code == 409
                controlled = client.post(f"/api/runtime/runs/{initial['runId']}/review", json={
                    "decision": decision, "checklist": checklist, "note": "Stop at the next safe boundary.",
                })
                assert controlled.status_code == 200, controlled.text
                assert controlled.json()["run"]["status"] == decision
            finally:
                released.set()
            completed = future.result(timeout=10)
        assert completed.status_code == 409, completed.text
        saved = report(client, initial["runId"])
        assert saved["context"] is not None
        assert saved["requests"][0]["structuralValidation"] == "PASS"
        assert saved["run"]["status"] == decision
        assert saved["semanticReview"] == "NOT_RUN"
        assert len(saved["requests"]) == 1 and provider.calls == ["context"]
        recovered = resume(client, initial["runId"], source)
        if decision == "rejected":
            assert recovered.status_code == 409
            reopened = client.post(f"/api/runtime/runs/{initial['runId']}/reopen", json={"sourceRequest": source})
            assert reopened.status_code == 200 and reopened.json()["runId"] != initial["runId"]
            assert provider.calls == ["context"]
        else:
            assert recovered.status_code == 200, recovered.text
            value = recovered.json()
            assert value["stage"] == "inference" and provider.calls == ["context"]
            response = client.post("/api/harness/inference/run", json=inference_request(
                value["contextFingerprint"], value["preview"]))
            assert response.status_code == 200, response.text
            assert provider.calls == ["context", "inference"]


class ExpensiveFirstFailure(CountingProvider):
    def execute_prepared(self, call):
        value = super().execute_prepared(call)
        if len(self.calls) == 1:
            value.output.evidence[0].evidence_id = "unselected-synthetic-evidence"
        return LlmCallResult(value.output, ProviderUsage(inputTokens=20_000, outputTokens=0))


def test_known_failed_context_usage_carries_into_approved_retry_and_blocks_further_calls(tmp_path, source_root):
    provider = ExpensiveFirstFailure()
    with TestClient(app_for(tmp_path, source_root, provider), raise_server_exceptions=False) as client:
        source = selection(client)
        initial = preview(client, source)
        failed = client.post("/api/harness/run", json=context_request(source, initial))
        assert failed.status_code == 502 and failed.json()["error"]["code"] == "INVALID_LLM_OUTPUT"
        saved = report(client, initial["runId"])
        assert saved["consumedTokens"] == 20_000
        assert saved["requests"][0]["structuralValidation"] == "FAIL"
        recovered = resume(client, initial["runId"], source)
        assert recovered.status_code == 200, recovered.text
        value = recovered.json()
        assert value["stage"] == "context" and provider.calls == ["context"]
        retry = client.post("/api/harness/run", json=context_request(source, value["preview"]))
        # The second known return consumes another 20k. A fresh attempt must not reset RunBudget.
        assert retry.status_code == 422 and retry.json()["error"]["code"] == "REQUEST_BUDGET_EXCEEDED"
        exhausted = report(client, initial["runId"])
        assert exhausted["consumedTokens"] == 40_000 and exhausted["context"] is None
        assert exhausted["requests"][-1]["errorCode"] == "REQUEST_BUDGET_EXCEEDED"
        attempts = len(exhausted["requests"])
        assert resume(client, initial["runId"], source).status_code == 422
        assert len(report(client, initial["runId"])["requests"]) == attempts
        assert provider.calls == ["context", "context"]


@pytest.mark.parametrize("kind", ["invalid_citation", "provider_error"])
def test_known_invalid_output_and_provider_failure_have_distinct_validation_outcomes(tmp_path, source_root, kind):
    provider = CountingProvider(error=RagProviderError()) if kind == "provider_error" else ExpensiveFirstFailure()
    with TestClient(app_for(tmp_path, source_root, provider), raise_server_exceptions=False) as client:
        source = selection(client)
        initial = preview(client, source)
        response = client.post("/api/harness/run", json=context_request(source, initial))
        assert response.status_code == 502
        saved = report(client, initial["runId"])
        expected = "ERROR" if kind == "provider_error" else "FAIL"
        assert saved["structuralValidation"] == saved["requests"][0]["structuralValidation"] == expected
        assert saved["requests"][0]["status"] == "failed"
        assert saved["run"]["status"] == "error"
        assert saved["semanticReview"] == "NOT_RUN" and saved["context"] is None
        assert provider.calls == ["context"]
