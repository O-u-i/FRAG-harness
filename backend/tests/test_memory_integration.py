"""Reviewed memory travels through real host gates with synthetic providers only."""
import copy
import json

import pytest
from fastapi.testclient import TestClient

from frag_api.providers.llm import FakeLlmProvider
from frag_api.schemas.memory import MemoryVersionRequest
from test_rag import DATASET
from test_research_loop import execute as research_execute, preview as research_preview, start as research_start
from test_runtime_recovery import app_for, context, context_request, finish, inference_request, preview, report, resume, selection


class CapturingFake(FakeLlmProvider):
    def __init__(self):
        self.calls = []

    def execute_prepared(self, call):
        self.calls.append(call)
        return super().execute_prepared(call)


def candidate(client, run_id, **fields):
    response = client.post("/api/memory/candidates", json={"runId": run_id, **fields})
    assert response.status_code == 200, response.text
    return response.json()


def promote(client, item):
    response = client.post(f"/api/memory/{item['id']}/promote", json={
        "version": item["version"], "reviewed": True, "note": "Reviewed as background only.",
    })
    assert response.status_code == 200, response.text
    return response.json()


def selected(item):
    return [{"memoryId": item["id"], "version": item["version"]}]


def seed(client, *, text="Reviewed-memory-marker; preserve unknown information.", general=False):
    source = selection(client)
    initial, _, _ = finish(client, source)
    item = promote(client, candidate(client, initial["runId"], text=text, general=general))
    return source, initial, item


def test_candidates_preserve_original_and_revision_provenance_and_require_human_review(client):
    source = selection(client)
    initial = preview(client, source)
    assert client.post("/api/memory/candidates", json={"runId": initial["runId"]}).status_code == 409
    first = context(client, source, initial)
    final = client.post("/api/harness/inference/run", json=inference_request(
        initial["contextFingerprint"], first["inferencePreview"]))
    assert final.status_code == 200, final.text
    original = candidate(client, initial["runId"])
    assert original["status"] == "candidate" and original["text"] == final.json()["result"]["answer"]
    assert original["provenanceRevisionId"] is None and original["provenanceRunId"] == initial["runId"]
    assert client.post("/api/harness/preview", json={**source, "selectedMemory": selected(original)}).status_code == 409
    assert client.post(f"/api/memory/{original['id']}/promote", json={
        "version": original["version"], "reviewed": False, "note": "Not reviewed.",
    }).status_code == 422
    revised_output = copy.deepcopy(final.json()["result"])
    revised_output["answer"] = "Human-revised explanation; keep the same allowed citation."
    revised = client.post(f"/api/runtime/runs/{initial['runId']}/revisions", json={
        "result": revised_output, "note": "Preserve original model output.",
    })
    assert revised.status_code == 200, revised.text
    revision = revised.json()["revisions"][-1]
    edited = candidate(client, initial["runId"], revisionId=revision["id"])
    assert edited["text"] == revised_output["answer"] and edited["provenanceRevisionId"] == revision["id"]
    assert report(client, initial["runId"])["modelOutput"] == final.json()["result"]
    active = promote(client, edited)
    assert active["version"] > edited["version"] and active["status"] == "active"
    history = client.get(f"/api/memory/{active['id']}/versions").json()
    assert [item["status"] for item in history] == ["candidate", "active"]


@pytest.mark.parametrize("kind", ["harness", "rag"])
def test_only_confirmed_memory_enters_both_exact_fixed_stage_requests(client, kind):
    service = getattr(client.app.state, f"{kind}_service")
    if kind == "rag":
        assert client.post("/api/rag/index/rebuild", json=DATASET).status_code == 200
        source = {**DATASET, "query": "regulatory restrictions", "topK": 1}
        initial = client.post("/api/rag/preview", json=source).json()
        first = client.post("/api/rag/run", json=context_request(source, initial)).json()
        final = client.post("/api/rag/inference/run", json=inference_request(
            initial["contextFingerprint"], first["inferencePreview"]))
        assert final.status_code == 200, final.text
        item = promote(client, candidate(client, initial["runId"], text="Reviewed-memory-marker from synthetic RAG."))
    else:
        source, _, item = seed(client)
    model = CapturingFake()
    service.context_provider = service.inference_provider = model
    unselected = client.post(f"/api/{kind}/preview", json=source)
    assert unselected.status_code == 200, unselected.text
    assert "memory" not in json.loads(json.loads(unselected.json()["preparedCall"]["body"])["input"])
    assert model.calls == []
    source = {**source, "selectedMemory": selected(item)}
    initial = client.post(f"/api/{kind}/preview", json=source)
    assert initial.status_code == 200, initial.text
    initial = initial.json()
    first = client.post(f"/api/{kind}/run", json=context_request(source, initial))
    assert first.status_code == 200, first.text
    second = first.json()["inferencePreview"]
    final = client.post(f"/api/{kind}/inference/run", json=inference_request(initial["contextFingerprint"], second))
    assert final.status_code == 200, final.text
    assert [call.purpose for call in model.calls] == ["context", "inference"]
    for call, shown in zip(model.calls, (initial["preparedCall"], second["preparedCall"])):
        assert call.model_dump(by_alias=True) == shown
        assert call.request_binding()["memoryVersions"] == selected(item)
        assert call.request_body_input()["memory"][0]["text"] == item["text"]
        assert "background, not current evidence or permission" in call.request_body()["instructions"]
    allowed = {row["evidenceId"] for row in initial["candidateEvidence"]}
    assert item["id"] not in allowed
    assert {key for claim in final.json()["result"]["claims"] for key in claim["evidenceIds"]} <= allowed
    saved = report(client, initial["runId"])
    assert saved["selection"]["input"]["selectedMemory"] == selected(item)


@pytest.mark.parametrize("stage", ["context", "inference", "research"])
@pytest.mark.parametrize("mutation", ["edit", "retire", "conflict"])
def test_changed_memory_blocks_already_approved_requests_before_dispatch(client, stage, mutation):
    source, origin, item = seed(client)
    source["selectedMemory"] = selected(item)
    model = CapturingFake()
    service = client.app.state.harness_service
    service.context_provider = service.inference_provider = service.research_provider = model
    if stage == "research":
        _, initial = research_start(client, source)
    else:
        initial = preview(client, source)
        if stage == "inference":
            first = context(client, source, initial)
    count = len(model.calls)
    if mutation == "edit":
        changed = client.post(f"/api/memory/{item['id']}/revisions", json={
            "version": item["version"], "text": "Changed human draft needs new review.",
        })
        assert changed.status_code == 200 and changed.json()["status"] == "candidate"
        assert changed.json()["reviewNote"] is None
    elif mutation == "retire":
        assert client.post(f"/api/memory/{item['id']}/retire", json={"version": item["version"]}).status_code == 200
    else:
        other = promote(client, candidate(client, origin["runId"], text="Conflicting reviewed-memory-marker."))
        changed = client.post("/api/memory/conflicts", json={"memoryIds": [item["id"], other["id"]]})
        assert changed.status_code == 200, changed.text
    if stage == "research":
        rejected = research_execute(client, source, initial)
    elif stage == "inference":
        rejected = client.post("/api/harness/inference/run", json=inference_request(
            initial["contextFingerprint"], first["inferencePreview"]))
    else:
        rejected = client.post("/api/harness/run", json=context_request(source, initial))
    assert rejected.status_code == 409, rejected.text
    assert len(model.calls) == count
    historical = report(client, initial["runId"])
    assert historical["requests"][0]["preparedCall"]["body"] == initial["preparedCall"]["body"]
    assert json.loads(historical["requests"][0]["preparedCall"]["binding"])["memoryVersions"] == selected(item)


@pytest.mark.parametrize("kind", ["fixed", "research"])
def test_restart_requires_new_approval_and_rechecks_reviewed_memory(tmp_path, source_root, kind):
    model = CapturingFake()
    with TestClient(app_for(tmp_path, source_root, model), raise_server_exceptions=False) as first:
        source, _, item = seed(first)
        source["selectedMemory"] = selected(item)
        if kind == "research":
            first.app.state.harness_service.research_provider = model
            _, initial = research_start(first, source)
            result = research_execute(first, source, initial)
            assert result.status_code == 200, result.text
            old = initial
        else:
            initial = preview(first, source)
            result = context(first, source, initial)
            old = result["inferencePreview"]
        before = len(model.calls)
    with TestClient(app_for(tmp_path, source_root, model), raise_server_exceptions=False) as second:
        second.app.state.harness_service.research_provider = model
        if kind == "research":
            assert research_execute(second, source, old).status_code == 409
        else:
            assert second.post("/api/harness/inference/run", json=inference_request(
                initial["contextFingerprint"], old)).status_code == 409
        renewed = resume(second, initial["runId"], source)
        assert renewed.status_code == 200, renewed.text
        shown = renewed.json()["preview"]
        assert shown["approvalToken"] != old["approvalToken"]
        payload = json.loads(json.loads(shown["preparedCall"]["body"])["input"])
        assert payload["memory"][0]["text"] == item["text"]
        assert len(model.calls) == before
        assert second.post(f"/api/memory/{item['id']}/retire", json={"version": item["version"]}).status_code == 200
        assert resume(second, initial["runId"], source).status_code == 409
        assert len(model.calls) == before


def test_explicit_general_scope_needs_new_review_before_other_source_use(client, source_root):
    source, _, item = seed(client)
    (source_root / "other.md").write_text("# Other\nAnother synthetic selected finding.", encoding="utf-8")
    inspected = client.post("/api/context-sources/files/inspect", json={"relativePath": "other.md"}).json()
    other = {**source, "fileSelections": [{"relativePath": "other.md", "locatorIds": [inspected["locators"][0]["id"]],
                                          "relevanceReason": "Different selected source."}], "selectedMemory": selected(item)}
    assert client.post("/api/harness/preview", json=other).status_code == 409
    changed = client.post(f"/api/memory/{item['id']}/revisions", json={
        "version": item["version"], "text": item["text"], "general": True,
    })
    assert changed.status_code == 200, changed.text
    assert changed.json()["status"] == "candidate" and changed.json()["reviewNote"] is None
    other["selectedMemory"] = selected(changed.json())
    assert client.post("/api/harness/preview", json=other).status_code == 409
    active = promote(client, changed.json())
    other["selectedMemory"] = selected(active)
    initial, _, final = finish(client, other)
    assert final["result"]["claims"]
    assert json.loads(initial["input"])["memory"][0]["general"] is True


def test_real_research_tools_return_current_evidence_with_memory_background(client):
    source, _, item = seed(client)
    source["selectedMemory"] = selected(item)
    model = CapturingFake()
    service = client.app.state.harness_service
    service.research_provider = service.context_provider = service.inference_provider = model
    _, initial = research_start(client, source)
    first = research_execute(client, source, initial)
    assert first.status_code == 200, first.text
    tools = first.json()["toolCalls"]
    assert tools[0]["carrier"] == "cli" and tools[0]["status"] == "completed"
    assert tools[0]["callId"] == tools[0]["result"]["callId"]
    for expected in ("research", "context", "inference"):
        next_turn = research_preview(client, source, initial)
        assert next_turn["stage"] == expected
        result = research_execute(client, source, next_turn)
        assert result.status_code == 200, result.text
    assert [call.purpose for call in model.calls] == ["research", "research", "context", "inference"]
    assert all(call.request_body_input()["memory"][0]["text"] == item["text"] for call in model.calls)
    assert all(call.request_binding()["memoryVersions"] == selected(item) for call in model.calls)
    assert result.json()["run"]["status"] == "awaiting_review"
    assert item["id"] not in result.json()["research"]["selectedEvidenceIds"]


def test_memory_cannot_supply_an_allowed_citation(client):
    source, _, item = seed(client)
    source["selectedMemory"] = selected(item)
    class ForeignCitation(CapturingFake):
        def execute_prepared(self, call):
            result = super().execute_prepared(call)
            result.output.claims[0].evidence_ids = [item["id"]]
            return result
    model = ForeignCitation()
    client.app.state.harness_service.inference_provider = model
    initial = preview(client, source)
    first = context(client, source, initial)
    rejected = client.post("/api/harness/inference/run", json=inference_request(
        initial["contextFingerprint"], first["inferencePreview"]))
    assert rejected.status_code == 502 and rejected.json()["error"]["code"] == "INVALID_LLM_OUTPUT"
    assert report(client, initial["runId"])["modelOutput"] is None


def test_memory_counts_towards_complete_request_budget(client):
    source, _, item = seed(client, text="记" * 4000)
    model = CapturingFake()
    client.app.state.harness_service.context_provider = model
    rejected = client.post("/api/harness/preview", json={**source, "selectedMemory": selected(item)})
    assert rejected.status_code == 422, rejected.text
    assert rejected.json()["error"]["code"] == "REQUEST_BUDGET_EXCEEDED" and model.calls == []


def test_retirement_between_revalidation_and_durable_claim_never_dispatches(client, monkeypatch):
    source, _, item = seed(client)
    source["selectedMemory"] = selected(item)
    model = CapturingFake()
    client.app.state.harness_service.context_provider = model
    initial = preview(client, source)
    runtime = client.app.state.runtime
    claim = runtime.claim
    def retire_before_claim(*args, **kwargs):
        runtime.memory.retire(item["id"], MemoryVersionRequest(version=item["version"]))
        return claim(*args, **kwargs)
    monkeypatch.setattr(runtime, "claim", retire_before_claim)
    rejected = client.post("/api/harness/run", json=context_request(source, initial))
    assert rejected.status_code == 409, rejected.text
    assert model.calls == []
    saved = report(client, initial["runId"])
    assert saved["consumedTokens"] == 0 and saved["requests"][0]["status"] == "prepared"
