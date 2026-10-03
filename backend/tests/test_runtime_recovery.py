"""Adversarial durable lifecycle checks using local synthetic providers only."""
from __future__ import annotations

import copy
import json
import re
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from threading import Lock

import pytest
from fastapi.testclient import TestClient

from frag_api.errors import RagOutcomeUnknownError, RagOutputError
from frag_api.main import create_app
from frag_api.providers.llm import FakeLlmProvider, LlmSettings, LlmStageSettings
from frag_api.services.context_source_service import ContextSourceService
from frag_api.services.harness_service import HarnessService


class CountingProvider(FakeLlmProvider):
    def __init__(self, error=None, inject_text=""):
        self.calls = []
        self.error = error
        self.inject_text = inject_text
        self.lock = Lock()

    def execute_prepared(self, call):
        with self.lock:
            self.calls.append(call.purpose)
        if self.error:
            raise self.error
        result = super().execute_prepared(call)
        if self.inject_text:
            if call.purpose == "context":
                result.output.evidence[0].summary += self.inject_text
            else:
                result.output.answer += self.inject_text
        return result


def fake_settings():
    stage = LlmStageSettings("fake", "synthetic-context", None, None, 120)
    return LlmSettings(stage, replace(stage, model="synthetic-inference"))


def app_for(tmp_path, source_root, provider, *, settings=None):
    harness = HarnessService(
        ContextSourceService(source_root), settings=settings or fake_settings(),
        context_provider=provider, inference_provider=provider,
    )
    return create_app(
        context_source_root=source_root, harness_service=harness,
        runtime_path=tmp_path / "runtime.sqlite3", rag_index_path=tmp_path / "rag.sqlite3",
        plugin_root=tmp_path / "absent-plugins",
    )


def selection(client):
    response = client.post("/api/context-sources/files/inspect", json={"relativePath": "evidence.md"})
    assert response.status_code == 200, response.text
    return {
        "goal": "Explain the synthetic finding",
        "fileSelections": [{"relativePath": "evidence.md", "locatorIds": [response.json()["locators"][0]["id"]],
                            "relevanceReason": "Selected for review"}],
    }


def preview(client, source):
    response = client.post("/api/harness/preview", json=source)
    assert response.status_code == 200, response.text
    assert response.json()["runId"]
    return response.json()


def context_request(source, value):
    return {**source, "contextFingerprint": value["contextFingerprint"],
            "approvalToken": value["approvalToken"], "approved": True}


def inference_request(fingerprint, value):
    return {"contextFingerprint": fingerprint, "inferenceFingerprint": value["inferenceFingerprint"],
            "approvalToken": value["approvalToken"], "approved": True}


def context(client, source, value):
    response = client.post("/api/harness/run", json=context_request(source, value))
    assert response.status_code == 200, response.text
    return response.json()


def finish(client, source):
    initial = preview(client, source)
    first = context(client, source, initial)
    response = client.post("/api/harness/inference/run", json=inference_request(
        initial["contextFingerprint"], first["inferencePreview"]))
    assert response.status_code == 200, response.text
    return initial, first, response.json()


def report(client, run_id):
    response = client.get(f"/api/runtime/runs/{run_id}")
    assert response.status_code == 200, response.text
    return response.json()


def resume(client, run_id, source):
    return client.post(f"/api/runtime/runs/{run_id}/resume/preview", json={"sourceRequest": source})


def test_context_checkpoint_survives_restart_without_context_resend(tmp_path, source_root):
    provider = CountingProvider()
    with TestClient(app_for(tmp_path, source_root, provider), raise_server_exceptions=False) as first:
        source = selection(first)
        initial = preview(first, source)
        first_stage = context(first, source, initial)
        saved = report(first, initial["runId"])
        old_inference = inference_request(initial["contextFingerprint"], first_stage["inferencePreview"])
        assert saved["context"] == first_stage["compressedContext"]
        assert saved["consumedTokens"] == 200
        assert provider.calls == ["context"]
    with TestClient(app_for(tmp_path, source_root, provider), raise_server_exceptions=False) as second:
        assert report(second, initial["runId"])["context"] == saved["context"]
        assert second.post("/api/harness/run", json=context_request(source, initial)).status_code == 409
        assert second.post("/api/harness/inference/run", json=old_inference).status_code == 409
        recovered = resume(second, initial["runId"], source)
        assert recovered.status_code == 200, recovered.text
        recovery = recovered.json()
        assert recovery["stage"] == "inference"
        assert recovery["preview"]["approvalToken"] != first_stage["inferencePreview"]["approvalToken"]
        assert provider.calls == ["context"]
        completed = second.post("/api/harness/inference/run", json=inference_request(
            recovery["contextFingerprint"], recovery["preview"]))
        assert completed.status_code == 200, completed.text
        final = report(second, initial["runId"])
        assert provider.calls == ["context", "inference"]
        assert final["consumedTokens"] == 360
        assert final["run"]["status"] == "awaiting_review"
        assert final["structuralValidation"] == "PASS" and final["semanticReview"] == "NOT_RUN"
        assert final["requests"][0]["preparedCall"] == saved["requests"][0]["preparedCall"]
        completed_calls = [item for item in final["requests"] if item["status"] == "completed"]
        assert [item["stage"] for item in completed_calls] == ["context", "inference"]
        assert len({item["id"] for item in final["requests"]}) == len(final["requests"])


def test_selected_snapshot_restart_requires_fresh_context_approval(tmp_path, source_root):
    provider = CountingProvider()
    with TestClient(app_for(tmp_path, source_root, provider), raise_server_exceptions=False) as first:
        source = selection(first)
        initial = preview(first, source)
    with TestClient(app_for(tmp_path, source_root, provider), raise_server_exceptions=False) as second:
        assert second.post("/api/harness/run", json=context_request(source, initial)).status_code == 409
        assert provider.calls == []
        response = resume(second, initial["runId"], source)
        assert response.status_code == 200, response.text
        recovered = response.json()
        assert recovered["stage"] == "context" and recovered["runId"] == initial["runId"]
        assert recovered["preview"]["approvalToken"] != initial["approvalToken"]
        context(second, source, recovered["preview"])
        assert provider.calls == ["context"]


@pytest.mark.parametrize("change", ["bytes", "locator", "goal", "root", "model", "timeout", "task"])
def test_recovery_rejects_source_scope_or_configuration_changes(tmp_path, source_root, change):
    provider = CountingProvider()
    with TestClient(app_for(tmp_path, source_root, provider), raise_server_exceptions=False) as first:
        source = selection(first)
        initial = preview(first, source)
        context(first, source, initial)
    source = copy.deepcopy(source)
    settings = fake_settings()
    if change == "bytes":
        (source_root / "evidence.md").write_text("# Finding\nChanged synthetic finding.\n# Limits\nMissing.", encoding="utf-8")
    elif change == "locator":
        source["fileSelections"][0]["locatorIds"] = ["section-2"]
    elif change == "goal":
        source["goal"] = "Explain a different synthetic finding"
    elif change == "root":
        replacement = tmp_path / "different-source-root"
        replacement.mkdir()
        (replacement / "evidence.md").write_bytes((source_root / "evidence.md").read_bytes())
        source_root = replacement
    elif change == "model":
        settings = replace(settings, inference=replace(settings.inference, model="different-synthetic-inference"))
    elif change == "timeout":
        settings = replace(settings, context=replace(settings.context, timeout_seconds=119))
    else:
        source["task"] = {"templateId": "evidence-review-v1", "checklist": [
            {"id": "new-item", "text": "Different review scope", "blocking": False,
             "status": "unknown", "reviewed": True}]}
    with TestClient(app_for(tmp_path, source_root, provider, settings=settings), raise_server_exceptions=False) as second:
        if change == "locator":
            inspection = second.post("/api/context-sources/files/inspect", json={"relativePath": "evidence.md"}).json()
            source["fileSelections"][0]["locatorIds"] = [inspection["locators"][1]["id"]]
        rejected = resume(second, initial["runId"], source)
        assert rejected.status_code == 409, rejected.text
        assert provider.calls == ["context"]
        assert report(second, initial["runId"])["context"] is not None


def test_unknown_dispatch_is_never_resumed_but_explicit_reopen_links_new_run(tmp_path, source_root):
    failed_provider = CountingProvider(error=RagOutcomeUnknownError())
    with TestClient(app_for(tmp_path, source_root, failed_provider), raise_server_exceptions=False) as first:
        source = selection(first)
        initial = preview(first, source)
        response = first.post("/api/harness/run", json=context_request(source, initial))
        assert response.status_code == 502
        assert response.json()["error"]["code"] == "LLM_OUTCOME_UNKNOWN"
        assert report(first, initial["runId"])["run"]["status"] == "outcome_unknown"
    next_provider = CountingProvider()
    with TestClient(app_for(tmp_path, source_root, next_provider), raise_server_exceptions=False) as second:
        assert resume(second, initial["runId"], source).status_code == 409
        assert next_provider.calls == []
        response = second.post(f"/api/runtime/runs/{initial['runId']}/reopen", json={"sourceRequest": source})
        assert response.status_code == 200, response.text
        reopened = response.json()
        assert reopened["runId"] != initial["runId"] and reopened["stage"] == "context"
        new_report = report(second, reopened["runId"])
        assert new_report["run"]["parentRunId"] == initial["runId"]
        assert new_report["run"]["sessionId"] == initial["sessionId"]
        assert next_provider.calls == []
        new_source = {**source, "sessionId": initial["sessionId"], "parentRunId": initial["runId"]}
        context(second, new_source, reopened["preview"])
        assert next_provider.calls == ["context"]
        assert report(second, initial["runId"])["run"]["status"] == "outcome_unknown"


def test_response_lost_before_durable_completion_becomes_unknown_on_restart(tmp_path, source_root):
    provider = CountingProvider()
    with TestClient(app_for(tmp_path, source_root, provider), raise_server_exceptions=False) as first:
        source = selection(first)
        initial = preview(first, source)
        repository = first.app.state.runtime.repository
        with repository.connection() as db:
            db.execute("""CREATE TRIGGER synthetic_failed_completion BEFORE UPDATE ON runs
                WHEN json_extract(NEW.record, '$.requests[0].status') = 'completed'
                BEGIN SELECT RAISE(ABORT, 'synthetic commit failure'); END""")
        response = first.post("/api/harness/run", json=context_request(source, initial))
        assert response.status_code == 500
        unsettled = report(first, initial["runId"])
        assert unsettled["requests"][0]["status"] == "dispatching"
        assert unsettled["context"] is None and provider.calls == ["context"]
    with TestClient(app_for(tmp_path, source_root, provider), raise_server_exceptions=False) as second:
        saved = report(second, initial["runId"])
        assert saved["run"]["status"] == "outcome_unknown"
        assert saved["requests"][0]["status"] == "outcome_unknown"
        assert saved["requests"][0]["errorCode"] == "INTERRUPTED_CALL"
        assert resume(second, initial["runId"], source).status_code == 409
        assert provider.calls == ["context"]


def test_valid_context_is_saved_before_inference_preview_failure(tmp_path, source_root, monkeypatch):
    provider = CountingProvider()
    with TestClient(app_for(tmp_path, source_root, provider), raise_server_exceptions=False) as first:
        source = selection(first)
        initial = preview(first, source)
        def fail_preview(_state):
            raise RagOutputError()
        monkeypatch.setattr(first.app.state.harness_service.flow, "_prepare_inference", fail_preview)
        response = first.post("/api/harness/run", json=context_request(source, initial))
        assert response.status_code == 502
        saved = report(first, initial["runId"])
        assert saved["context"] is not None and saved["requests"][0]["structuralValidation"] == "PASS"
        assert saved["consumedTokens"] == 200 and provider.calls == ["context"]
    with TestClient(app_for(tmp_path, source_root, provider), raise_server_exceptions=False) as second:
        recovered = resume(second, initial["runId"], source)
        assert recovered.status_code == 200, recovered.text
        value = recovered.json()
        assert value["stage"] == "inference"
        response = second.post("/api/harness/inference/run", json=inference_request(value["contextFingerprint"], value["preview"]))
        assert response.status_code == 200, response.text
        assert provider.calls == ["context", "inference"]


def test_concurrent_fresh_approvals_cannot_dispatch_one_stage_twice(tmp_path, source_root):
    provider = CountingProvider()
    with TestClient(app_for(tmp_path, source_root, provider), raise_server_exceptions=False) as client:
        source = selection(client)
        initial = preview(client, source)
        earlier = resume(client, initial["runId"], source)
        later = resume(client, initial["runId"], source)
        assert earlier.status_code == later.status_code == 200
        first, second = earlier.json()["preview"], later.json()["preview"]
        assert first["approvalToken"] != second["approvalToken"]
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(client.post, "/api/harness/run", json=context_request(source, value))
                       for value in (first, second)]
            responses = [future.result(timeout=15) for future in futures]
        assert sorted(response.status_code for response in responses) == [200, 409]
        assert provider.calls == ["context"]
        saved = report(client, initial["runId"])
        assert len([call for call in saved["requests"] if call["stage"] == "context" and call["status"] == "completed"]) == 1


def test_runtime_storage_redacts_inputs_outputs_notes_and_never_stores_tokens(tmp_path, source_root):
    secret = "synthetic-unmarked-config-key"
    stage = LlmStageSettings("openai", "synthetic-context", "https://synthetic.invalid/v1/", secret, 120)
    settings = LlmSettings(stage, replace(stage, model="synthetic-inference"))
    provider = CountingProvider(inject_text=" password=synthetic-output-secret analyst@example.org " + secret)
    with TestClient(app_for(tmp_path, source_root, provider, settings=settings), raise_server_exceptions=False) as client:
        source = selection(client)
        source["goal"] += " password=synthetic-input-secret analyst@example.org " + secret
        session = client.post("/api/runtime/sessions", json={"title": "Review password=synthetic-title-secret " + secret}).json()
        source["sessionId"] = session["id"]
        initial, first, final = finish(client, source)
        request = {"decision": "paused", "checklist": {"templateId": "evidence-review-v1", "checklist": []},
                   "note": "password=synthetic-review-secret " + secret}
        review = client.post(f"/api/runtime/runs/{initial['runId']}/review", json=request)
        assert review.status_code == 200, review.text
        saved = report(client, initial["runId"])
        with sqlite3.connect(tmp_path / "runtime.sqlite3") as db:
            stored = "\n".join(row[0] for table in ("sessions", "runs") for row in db.execute(f"SELECT record FROM {table}"))
        exported = client.get(f"/api/runtime/runs/{initial['runId']}/report.md").text
        for leaked in (secret, "synthetic-input-secret", "synthetic-title-secret", "synthetic-review-secret",
                       "synthetic-output-secret", "analyst@example.org", initial["approvalToken"], first["inferencePreview"]["approvalToken"]):
            assert leaked not in stored and leaked not in exported and leaked not in json.dumps(saved)
        for leaked in (secret, "synthetic-input-secret", "synthetic-output-secret", "analyst@example.org"):
            assert leaked not in json.dumps(first) and leaked not in json.dumps(final)
        assert "approvalToken" not in stored and "apiKey" not in stored
        assert saved["selection"]["input"]["goal"] != source["goal"]
        assert saved["modelOutput"] is not None


def test_review_cannot_drop_blocking_items_and_revisions_need_independent_review(tmp_path, source_root):
    provider = CountingProvider()
    with TestClient(app_for(tmp_path, source_root, provider), raise_server_exceptions=False) as client:
        source = selection(client)
        task = {"templateId": "evidence-review-v1", "checklist": [
            {"id": "facts", "text": "Confirm key facts against selected evidence", "blocking": True,
             "status": "met", "reviewed": True},
            {"id": "coverage", "text": "Additional source coverage", "blocking": False,
             "status": "missing", "reviewed": True}]}
        source["task"] = task
        initial, _first, final = finish(client, source)
        run_id = initial["runId"]
        for removed in (True, False):
            forged = copy.deepcopy(task)
            if removed:
                forged["checklist"] = []
            else:
                forged["checklist"][0]["blocking"] = False
            assert client.post(f"/api/runtime/runs/{run_id}/review", json={"decision": "accepted", "checklist": forged}).status_code == 409
        unresolved = copy.deepcopy(task)
        unresolved["checklist"][0].update(status="unknown", reviewed=False)
        paused = client.post(f"/api/runtime/runs/{run_id}/review", json={"decision": "accepted", "checklist": unresolved})
        assert paused.status_code == 200, paused.text
        assert paused.json()["run"]["status"] == "paused"
        assert paused.json()["reviews"][-1]["decision"] == "paused"
        accepted = client.post(f"/api/runtime/runs/{run_id}/review", json={"decision": "accepted", "checklist": task})
        assert accepted.status_code == 200 and accepted.json()["semanticReview"] == "PASS"
        original = accepted.json()["modelOutput"]
        revised_result = copy.deepcopy(final["result"])
        revised_result["answer"] = "Human revision keeps the evidence limitation."
        revised = client.post(f"/api/runtime/runs/{run_id}/revisions", json={"result": revised_result, "note": "Human edit"})
        assert revised.status_code == 200, revised.text
        revision_id = revised.json()["revisions"][-1]["id"]
        assert revised.json()["modelOutput"] == original
        assert revised.json()["semanticReview"] == "NOT_RUN"
        assert revised.json()["revisions"][-1]["reviewStatus"] == "pending"
        original_review = client.post(f"/api/runtime/runs/{run_id}/review", json={"target": "model", "decision": "accepted", "checklist": task})
        assert original_review.status_code == 200
        assert original_review.json()["semanticReview"] == "NOT_RUN"
        assert original_review.json()["revisions"][-1]["reviewStatus"] == "pending"
        revision_review = client.post(f"/api/runtime/runs/{run_id}/review", json={"target": revision_id, "decision": "accepted", "checklist": task})
        assert revision_review.status_code == 200 and revision_review.json()["semanticReview"] == "PASS"
        assert revision_review.json()["modelOutput"] == original
        assert revision_review.json()["selection"]["task"]["checklist"][1]["status"] == "missing"
        invalid = copy.deepcopy(revised_result)
        invalid["claims"][0]["evidenceIds"] = ["unselected-evidence"]
        assert client.post(f"/api/runtime/runs/{run_id}/revisions", json={"result": invalid}).status_code == 409


def test_json_and_markdown_render_the_same_canonical_record_without_calls(tmp_path, source_root):
    provider = CountingProvider()
    with TestClient(app_for(tmp_path, source_root, provider), raise_server_exceptions=False) as client:
        initial, _first, final = finish(client, selection(client))
        revision = copy.deepcopy(final["result"])
        revision["answer"] = "Literal Markdown data: ```\n# Embedded heading\n```"
        response = client.post(f"/api/runtime/runs/{initial['runId']}/revisions", json={"result": revision})
        assert response.status_code == 200, response.text
        expected = report(client, initial["runId"])
        json_export = client.get(f"/api/runtime/runs/{initial['runId']}/report.json")
        markdown = client.get(f"/api/runtime/runs/{initial['runId']}/report.md")
        assert json_export.status_code == markdown.status_code == 200
        fenced = re.search(r"^(`{3,})json\n(.*)\n\1\n$", markdown.text, re.MULTILINE | re.DOTALL)
        assert fenced and len(fenced.group(1)) > 3
        assert json.loads(fenced.group(2)) == expected == json_export.json()
        assert provider.calls == ["context", "inference"]


def test_report_mutation_failure_rolls_back_the_whole_checkpoint(tmp_path, source_root):
    provider = CountingProvider()
    with TestClient(app_for(tmp_path, source_root, provider), raise_server_exceptions=False) as client:
        initial = preview(client, selection(client))
        repository = client.app.state.runtime.repository
        before = report(client, initial["runId"])
        def incomplete_update(value):
            value.run.status = "accepted"
            value.requests[0].status = "completed"
            value.consumed_tokens = 999
            raise RuntimeError("Synthetic crash before atomic commit")
        with pytest.raises(RuntimeError):
            repository.update(initial["runId"], incomplete_update)
        assert report(client, initial["runId"]) == before
        assert provider.calls == []


def test_multiple_runs_share_a_session_without_cross_run_approval(tmp_path, source_root):
    provider = CountingProvider()
    with TestClient(app_for(tmp_path, source_root, provider), raise_server_exceptions=False) as client:
        session = client.post("/api/runtime/sessions", json={"title": "Synthetic grouped review"}).json()
        source = {**selection(client), "sessionId": session["id"]}
        first = preview(client, source)
        second_source = {**source, "goal": "Review a different question"}
        second = preview(client, second_source)
        assert first["runId"] != second["runId"] and first["sessionId"] == second["sessionId"]
        runs = client.get("/api/runtime/runs", params={"sessionId": session["id"]}).json()
        assert {run["id"] for run in runs} == {first["runId"], second["runId"]}
        substituted = context_request(second_source, first)
        assert client.post("/api/harness/run", json=substituted).status_code == 409
        assert provider.calls == []
        assert report(client, second["runId"])["context"] is None


@pytest.mark.parametrize("stage", ["context", "inference"])
def test_committed_model_response_finishes_host_checks_on_restart_without_resend(tmp_path, source_root, monkeypatch, stage):
    provider = CountingProvider()
    with TestClient(app_for(tmp_path, source_root, provider), raise_server_exceptions=False) as first:
        source = selection(first)
        initial = preview(first, source)
        runtime = first.app.state.runtime
        original_checkpoint = runtime.checkpoint
        def interrupted_checkpoint(*args, **kwargs):
            if kwargs["stage"] == stage:
                raise RuntimeError("Synthetic interruption after durable response")
            return original_checkpoint(*args, **kwargs)
        monkeypatch.setattr(runtime, "checkpoint", interrupted_checkpoint)
        if stage == "context":
            response = first.post("/api/harness/run", json=context_request(source, initial))
        else:
            first_stage = context(first, source, initial)
            response = first.post("/api/harness/inference/run", json=inference_request(
                initial["contextFingerprint"], first_stage["inferencePreview"]))
        assert response.status_code == 500
        interrupted = report(first, initial["runId"])
        assert interrupted["requests"][-1]["status"] == "completed"
        assert interrupted["requests"][-1]["output"] is not None
        assert interrupted["requests"][-1]["structuralValidation"] == "UNDETERMINED"
        calls_before = list(provider.calls)
    with TestClient(app_for(tmp_path, source_root, provider), raise_server_exceptions=False) as second:
        restored = report(second, initial["runId"])
        assert provider.calls == calls_before
        assert restored["requests"][-1]["structuralValidation"] == "PASS"
        assert restored["context"] is not None
        if stage == "context":
            recovered = resume(second, initial["runId"], source)
            assert recovered.status_code == 200 and recovered.json()["stage"] == "inference"
        else:
            assert restored["modelOutput"] is not None
            assert restored["run"]["status"] == "awaiting_review"
            assert resume(second, initial["runId"], source).status_code == 409
        assert provider.calls == calls_before


def test_reusing_injected_service_across_lifespans_invalidates_old_tokens(tmp_path, source_root):
    provider = CountingProvider()
    app = app_for(tmp_path, source_root, provider)
    with TestClient(app, raise_server_exceptions=False) as first:
        source = selection(first)
        initial = preview(first, source)
        first_stage = context(first, source, initial)
        unused_context = preview(first, source)
        service = first.app.state.harness_service
    assert service.flow.runtime is None
    restarted = create_app(context_source_root=source_root, harness_service=service,
        runtime_path=tmp_path / "runtime.sqlite3", rag_index_path=tmp_path / "rag.sqlite3", plugin_root=tmp_path / "absent-plugins")
    with TestClient(restarted, raise_server_exceptions=False) as second:
        assert second.post("/api/harness/run", json=context_request(source, unused_context)).status_code == 409
        assert second.post("/api/harness/inference/run", json=inference_request(
            initial["contextFingerprint"], first_stage["inferencePreview"])).status_code == 409
        assert provider.calls == ["context"]
        assert resume(second, initial["runId"], source).status_code == 200


def test_active_runtime_owner_cannot_be_replaced_by_second_app(tmp_path, source_root):
    provider = CountingProvider()
    with TestClient(app_for(tmp_path, source_root, provider), raise_server_exceptions=False) as first:
        initial = preview(first, selection(first))
        with pytest.raises(OSError):
            with TestClient(app_for(tmp_path, source_root, provider)):
                pytest.fail("A second app must not acquire the active runtime database.")
        assert report(first, initial["runId"])["run"]["status"] == "ready_context"
        assert provider.calls == []
