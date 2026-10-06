"""Explicit selected-file indexing and the complete offline governed trajectory."""
import copy
import hashlib
import json
import os
import sqlite3

import pytest
from fastapi.testclient import TestClient

from frag_api.main import create_app
from frag_api.providers.llm import FakeLlmProvider, LlmCallResult
from frag_api.repositories.rag_index_repository import RagIndexRepository
from frag_api.schemas.common import ProviderUsage
from frag_api.schemas.rag import RagContextCompression, RagGroundedAnswer, RagDatasetRequest
from frag_api.schemas.research import ResearchDecision
from frag_api.services.cli_executor import ControlledCLI
from frag_api.services.context_source_service import ContextSourceService
from test_memory_integration import candidate, promote, selected
from test_runtime_recovery import context_request, inference_request

POLICY = ("Only synthetic datasets may be exported. Deletion is not enabled. "
          "Retention is limited to at most 14 days. The result limit is 8 MiB. "
          "The policy became effective on 2026-10-01. The maintenance owner is unknown. "
          "删除未启用；保留期限最多十四天。")
MISSING = ["maintenance owner identity"]


@pytest.fixture
def selected_root(tmp_path):
    root = tmp_path / "selected-sources"
    root.mkdir()
    (root / "selected-policy.md").write_text("# Policy\n" + POLICY + "\n# Excluded\nUNSELECTED_NEEDLE must never appear.", encoding="utf-8")
    (root / "never-read.md").write_text("UNSELECTED_FILE_NEEDLE", encoding="utf-8")
    return root


def app_for(tmp_path, root):
    return create_app(context_source_root=root, runtime_path=tmp_path / "runtime.sqlite3",
        rag_index_path=tmp_path / "synthetic-index.sqlite3", plugin_root=tmp_path / "no-plugins")


def source_for(client):
    inspected = client.post("/api/context-sources/files/inspect", json={"relativePath": "selected-policy.md"})
    assert inspected.status_code == 200, inspected.text
    return {"datasetId": "selected-local-v1", "sourceSelection": {"relativePath": "selected-policy.md",
        "locatorIds": [inspected.json()["locators"][0]["id"]], "relevanceReason": "Selected synthetic policy"}}


def ok(response):
    assert response.status_code == 200, response.text
    return response.json()


def execute(client, source, preview):
    return client.post(f"/api/runtime/runs/{preview['runId']}/research/execute", json={"sourceRequest": source,
        "fingerprint": preview["fingerprint"], "approvalToken": preview["approvalToken"], "approved": True})


def next_preview(client, source, run_id):
    return ok(client.post(f"/api/runtime/runs/{run_id}/research/preview", json={"sourceRequest": source}))


class ScriptedPolicy(FakeLlmProvider):
    def __init__(self):
        self.calls = []

    def execute_prepared(self, call):
        self.calls.append(call)
        payload = call.request_body_input()
        if call.purpose == "research":
            binding = payload["manifest"][0]
            scope = {key: binding[key] for key in ("identity", "revision", "locatorIds")}
            if payload["turn"] == 1:
                output = ResearchDecision(action="continue", toolCalls=[{"callId": "selected-search", "name": "kb.search",
                    "arguments": {**scope, "query": "Deletion", "limit": 10}}], evidenceIds=[], missingInformation=MISSING)
            elif payload["turn"] == 2:
                output = ResearchDecision(action="continue", toolCalls=[{"callId": "selected-read", "name": "kb.read",
                    "arguments": {**scope, "evidenceIds": binding["evidenceIds"]}}], evidenceIds=[], missingInformation=MISSING)
            else:
                output = ResearchDecision(action="finish", toolCalls=[], evidenceIds=binding["evidenceIds"], missingInformation=MISSING)
        elif call.purpose == "context":
            output = RagContextCompression(evidence=[{"evidenceId": row["evidenceId"], "summary": row["text"],
                "preservedFacts": [POLICY], "uncertainty": MISSING} for row in payload["evidence"]], missingInformation=MISSING)
        else:
            output = RagGroundedAnswer(answer=POLICY, claims=[{"text": POLICY,
                "evidenceIds": [row["evidenceId"] for row in payload["context"]["evidence"]]}],
                missingInformation=MISSING, disclaimer="Synthetic scripted output; requires human semantic review.")
        return LlmCallResult(output, ProviderUsage(inputTokens=120, outputTokens=100))


def bind(client, model):
    service = client.app.state.rag_service
    service.research_provider = service.context_provider = service.inference_provider = model


def test_selected_locator_cache_is_separate_and_never_indexes_excluded_content(tmp_path, selected_root, monkeypatch):
    parsed = []
    original = ContextSourceService.parse
    def capture(self, path):
        parsed.append(path)
        return original(self, path)
    monkeypatch.setattr(ContextSourceService, "parse", capture)
    with TestClient(app_for(tmp_path, selected_root)) as client:
        source = source_for(client)
        assert ok(client.post("/api/rag/status", json=source))["state"] == "not_built"
        assert not (tmp_path / "selected").exists()
        assert client.post("/api/rag/search", json={**source, "query": "Deletion"}).status_code == 409
        status = ok(client.post("/api/rag/index/rebuild", json=source))
        assert status["state"] == "ready" and status["documentCount"] == 1
        assert ok(client.get("/api/rag/status"))["state"] == "not_built"
        for query in ("Deletion", "删除未启用"):
            result = ok(client.post("/api/rag/search", json={**source, "query": query}))
            assert result["results"] and all(item["locatorId"] == "section-1" for item in result["results"])
        for query in ("UNSELECTED_NEEDLE", "UNSELECTED_FILE_NEEDLE"):
            assert ok(client.post("/api/rag/search", json={**source, "query": query}))["results"] == []
        preview = ok(client.post("/api/rag/preview", json={**source, "query": "Deletion"}))
        assert POLICY in preview["candidateEvidence"][0]["text"]
        assert "UNSELECTED" not in json.dumps(preview)
        assert preview["sourceBindings"][0]["identity"]["kind"] == "local_file"
        assert hashlib.sha256((selected_root / "selected-policy.md").read_bytes()).hexdigest() in preview["sourceBindings"][0]["assessment"]["provenance"]["detail"]
        assert client.post("/api/rag/evaluations/run", json=source).status_code == 422
    assert set(parsed) == {"selected-policy.md"}
    caches = list((tmp_path / "selected").glob("*.sqlite3"))
    assert len(caches) == 1 and not (tmp_path / "synthetic-index.sqlite3").exists()
    with sqlite3.connect(caches[0]) as db:
        text = " ".join(row[0] for row in db.execute("SELECT content FROM rag_parents"))
        assert POLICY in text and "UNSELECTED" not in text


def test_selected_source_browser_metadata_redacts_credentials_before_truncation(tmp_path, selected_root, monkeypatch):
    configured = "opaque-synthetic-api-credential-593411"
    runtime_secret = "runtime-synthetic-secret-" + "Z" * 280
    monkeypatch.setenv("OPENAI_API_KEY", configured)
    monkeypatch.setenv("FRAG_CONTEXT_LLM_PROVIDER", "openai")
    monkeypatch.setenv("FRAG_CONTEXT_LLM_MODEL", "synthetic-model")
    monkeypatch.setenv("FRAG_CONTEXT_LLM_BASE_URL", "https://example.test/v1/")
    title = f"Policy user@example.test {configured}"
    text = f"# {title}\nDeletion api_key=synthetic_pattern_secret {runtime_secret}\n# Excluded\nUNSELECTED_NEEDLE"
    (selected_root / "selected-policy.md").write_text(text, encoding="utf-8")
    with TestClient(app_for(tmp_path, selected_root)) as client:
        client.app.state.runtime.secret_values += (runtime_secret,)
        inspection = ok(client.post("/api/context-sources/files/inspect", json={"relativePath": "selected-policy.md"}))
        source = {"datasetId": "selected-local-v1", "sourceSelection": {"relativePath": "selected-policy.md",
            "locatorIds": [inspection["locators"][0]["id"]], "relevanceReason": f"Policy {configured} {runtime_secret}"}}
        ok(client.post("/api/rag/index/rebuild", json=source))
        query = {**source, "query": "Deletion " + configured}
        search = ok(client.post("/api/rag/search", json=query))
        preview = ok(client.post("/api/rag/preview", json=query))
        report = ok(client.get(f"/api/runtime/runs/{preview['runId']}/report.json"))
        for response in (inspection, search, preview, report):
            encoded = json.dumps(response)
            for secret in (configured, "runtime-synthetic-secret-", "synthetic_pattern_secret", "user@example.test"):
                assert secret not in encoded
        assert inspection["locators"][0]["id"] == search["results"][0]["locatorId"] == "section-1"
        assert inspection["source"]["relativePath"] == "selected-policy.md"
        assert "[REDACTED_SECRET]" in search["results"][0]["excerpt"]
        assert "[REDACTED_EMAIL]" in search["results"][0]["locatorLabel"]
        assert json.loads(preview["preparedCall"]["binding"])["sources"] == preview["sourceBindings"]
        assert all(call["status"] == "prepared" and call["output"] is None and call["usage"] is None
                   for call in report["requests"])
    assert (selected_root / "selected-policy.md").read_text(encoding="utf-8") == text
    cache = next((tmp_path / "selected").glob("*.sqlite3"))
    with sqlite3.connect(cache) as db:
        assert runtime_secret in db.execute("SELECT content FROM rag_parents").fetchone()[0]


@pytest.mark.parametrize("operation", ["search", "preview", "index/rebuild"])
def test_selected_source_change_during_index_operation_rejects_result(tmp_path, selected_root, monkeypatch, operation):
    source_file = selected_root / "selected-policy.md"
    method = "rebuild" if operation == "index/rebuild" else "search_snapshot"
    original = getattr(RagIndexRepository, method)
    with TestClient(app_for(tmp_path, selected_root)) as client:
        source = source_for(client)
        ok(client.post("/api/rag/index/rebuild", json=source))
        def mutate_after_read(self, *args, **kwargs):
            result = original(self, *args, **kwargs)
            source_file.write_text("# Policy\nChanged policy bytes.\n# Excluded\nUNSELECTED_NEEDLE", encoding="utf-8")
            return result
        monkeypatch.setattr(RagIndexRepository, method, mutate_after_read)
        body = source if operation == "index/rebuild" else {**source, "query": "Deletion"}
        response = client.post(f"/api/rag/{operation}", json=body)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "RAG_INDEX_STALE"
        assert ok(client.post("/api/rag/status", json=source))["state"] == "stale"
        assert ok(client.get("/api/runtime/runs")) == []


@pytest.mark.parametrize("name,text", [
    ("policy.txt", "Deletion is not enabled.\n\nUNSELECTED_NEEDLE"),
    ("policy.html", "<p>Deletion is not enabled.</p><p>UNSELECTED_NEEDLE</p>"),
    ("policy.csv", "policy,Deletion is not enabled.\n" + "allowed,Selected row.\n" * 49 + "excluded,UNSELECTED_NEEDLE\n" * 50),
])
def test_selected_index_reuses_non_markdown_parser_locators(tmp_path, selected_root, name, text):
    (selected_root / name).write_text(text, encoding="utf-8")
    with TestClient(app_for(tmp_path, selected_root)) as client:
        inspection = ok(client.post("/api/context-sources/files/inspect", json={"relativePath": name}))
        locator = inspection["locators"][0]["id"]
        source = {"datasetId": "selected-local-v1", "sourceSelection": {"relativePath": name,
            "locatorIds": [locator], "relevanceReason": "Selected first parsed locator"}}
        ok(client.post("/api/rag/index/rebuild", json=source))
        preview = ok(client.post("/api/rag/preview", json={**source, "query": "Deletion"}))
        assert preview["candidateEvidence"][0]["locatorId"] == locator
        assert "Deletion is not enabled." in preview["candidateEvidence"][0]["text"]
        assert "UNSELECTED_NEEDLE" not in json.dumps(preview)


@pytest.mark.parametrize("change", ["missing", "synthetic-selection", "duplicate", "empty", "too-many", "escape", "unknown", "extra"])
def test_selected_source_contract_rejects_invalid_scope_without_build(tmp_path, selected_root, change):
    with TestClient(app_for(tmp_path, selected_root), raise_server_exceptions=False) as client:
        source = source_for(client)
        if change == "missing": source.pop("sourceSelection")
        if change == "synthetic-selection": source["datasetId"] = "synthetic-risk-review-v1"
        if change == "duplicate": source["sourceSelection"]["locatorIds"] *= 2
        if change == "empty": source["sourceSelection"]["locatorIds"] = []
        if change == "too-many": source["sourceSelection"]["locatorIds"] = [f"section-{index}" for index in range(21)]
        if change == "escape": source["sourceSelection"]["relativePath"] = "../outside.md"
        if change == "unknown": source["sourceSelection"]["locatorIds"] = ["not-selected"]
        if change == "extra": source["sourceSelection"]["authority"] = "granted"
        assert client.post("/api/rag/index/rebuild", json=source).status_code == 422
        assert not (tmp_path / "selected").exists()


def test_oversized_selected_title_fails_before_creating_cache(tmp_path, selected_root):
    (selected_root / "selected-policy.md").write_text("# " + "L" * 600 + "\nDeletion is not enabled.", encoding="utf-8")
    with TestClient(app_for(tmp_path, selected_root), raise_server_exceptions=False) as client:
        source = source_for(client)
        assert client.post("/api/rag/index/rebuild", json=source).status_code == 422
        assert not (tmp_path / "selected").exists()


def test_selected_fts_research_memory_restart_and_canonical_report(tmp_path, selected_root, monkeypatch):
    carrier_calls = []
    original = ControlledCLI.execute
    def capture(self, payload):
        carrier_calls.append((self.definition, payload))
        return original(self, payload)
    monkeypatch.setattr(ControlledCLI, "execute", capture)
    seed_model, model = ScriptedPolicy(), ScriptedPolicy()
    with TestClient(app_for(tmp_path, selected_root), raise_server_exceptions=False) as client:
        source = source_for(client)
        ok(client.post("/api/rag/index/rebuild", json=source))
        query = {**source, "query": "synthetic Deletion policy", "topK": 3}
        bind(client, seed_model)
        initial = ok(client.post("/api/rag/preview", json=query))
        first = ok(client.post("/api/rag/run", json=context_request(query, initial)))
        final_seed = ok(client.post("/api/rag/inference/run", json=inference_request(initial["contextFingerprint"], first["inferencePreview"])))
        memory = candidate(client, initial["runId"], text="Candidate preserve unknown information.")
        assert client.post("/api/rag/preview", json={**query, "selectedMemory": selected(memory)}).status_code == 409
        memory = ok(client.post(f"/api/memory/{memory['id']}/revisions", json={"version": memory["version"],
            "text": "Reviewed background: preserve unknown policy information. 保留未知信息。"}))
        memory = promote(client, memory)
        recommendation = ok(client.post("/api/memory/recommend", json={"runId": initial["runId"], "query": "unknown policy 未知信息"}))
        assert [item["id"] for item in recommendation] == [memory["id"]]
        query["selectedMemory"] = selected(memory)
        bind(client, model)
        preview = ok(client.post("/api/runtime/research/preview", json={"kind": "rag", "sourceRequest": query}))
        run_id = preview["runId"]
        assert not model.calls and not carrier_calls
        approved = []
        for stage in ("research", "research", "research", "context"):
            assert preview["stage"] == stage
            approved.append(preview["preparedCall"])
            response = execute(client, query, preview)
            result = ok(response)
            assert execute(client, query, preview).status_code == 409
            preview = next_preview(client, query, run_id)
        old_inference = preview
        assert old_inference["stage"] == "inference" and len(model.calls) == 4
        assert [item["carrier"] for item in result["toolCalls"]] == ["native", "cli"]
        assert result["context"]["missingInformation"] == MISSING
        assert len(carrier_calls) == 1 and carrier_calls[0][0].name == "kb.read.cli"
        assert carrier_calls[0][1]["callId"] == result["toolCalls"][1]["result"]["callId"]
        assert final_seed["result"]["answer"] == POLICY
    with TestClient(app_for(tmp_path, selected_root), raise_server_exceptions=False) as restarted:
        bind(restarted, model)
        assert execute(restarted, query, old_inference).status_code == 409 and len(model.calls) == 4
        preview = next_preview(restarted, query, run_id)
        assert preview["stage"] == "inference" and preview["approvalToken"] != old_inference["approvalToken"]
        approved.append(preview["preparedCall"])
        final = ok(execute(restarted, query, preview))
        assert [call.purpose for call in model.calls] == ["research"] * 3 + ["context", "inference"]
        assert [call.model_dump(by_alias=True) for call in model.calls] == approved
        assert all(call.request_body_input()["memory"][0]["text"] == memory["text"] for call in model.calls)
        assert len(carrier_calls) == 1 and final["run"]["status"] == "awaiting_review"
        assert final["semanticReview"] == "NOT_RUN" and final["modelOutput"]["answer"] == POLICY
        assert final["modelOutput"]["missingInformation"] == MISSING
        assert memory["id"] not in final["research"]["selectedEvidenceIds"]
        allowed = set(final["research"]["selectedEvidenceIds"])
        assert all(set(claim["evidenceIds"]).issubset(allowed) for claim in final["modelOutput"]["claims"])
        assert "UNSELECTED" not in json.dumps(final)
        report = ok(restarted.get(f"/api/runtime/runs/{run_id}/report.json"))
        markdown = restarted.get(f"/api/runtime/runs/{run_id}/report.md").text
        assert json.loads(markdown.split("```json\n", 1)[1].rsplit("\n```", 1)[0]) == report == final
        assert all(item["approvalToken"] not in markdown for item in (old_inference, preview))
        paused = ok(restarted.post(f"/api/runtime/runs/{run_id}/review", json={"decision": "paused",
            "checklist": final["selection"]["task"], "note": "Human semantic acceptance deferred."}))
        assert paused["run"]["status"] == "paused" and paused["semanticReview"] == "UNDETERMINED"
        original_output = copy.deepcopy(paused["modelOutput"])
        revision = ok(restarted.post(f"/api/runtime/runs/{run_id}/revisions", json={
            "result": {**original_output, "answer": original_output["answer"] + " Human synthetic revision."},
            "note": "Synthetic human revision; original retained."}))
        assert revision["modelOutput"] == original_output and revision["revisions"][-1]["result"]["answer"].endswith("Human synthetic revision.")


@pytest.mark.parametrize("change", ["bytes", "locators", "root"])
def test_selection_changes_reject_old_approval_recovery_and_memory(tmp_path, selected_root, change):
    model = ScriptedPolicy()
    with TestClient(app_for(tmp_path, selected_root)) as client:
        source = source_for(client)
        ok(client.post("/api/rag/index/rebuild", json=source))
        query = {**source, "query": "Deletion"}
        bind(client, model)
        initial = ok(client.post("/api/rag/preview", json=query))
        context = ok(client.post("/api/rag/run", json=context_request(query, initial)))
        ok(client.post("/api/rag/inference/run", json=inference_request(initial["contextFingerprint"], context["inferencePreview"])))
        memory = promote(client, candidate(client, initial["runId"], text="Selected source policy background."))
        query["selectedMemory"] = selected(memory)
        pending = ok(client.post("/api/rag/preview", json=query))
        if change == "bytes":
            (selected_root / "selected-policy.md").write_text("# Policy\n" + POLICY + " Additional detail.\n# Excluded\nUNSELECTED_NEEDLE", encoding="utf-8")
            assert ok(client.post("/api/rag/status", json=source))["state"] == "stale"
        if change == "locators":
            query["sourceSelection"] = {**source["sourceSelection"], "locatorIds": ["section-1", "section-2"]}
        if change == "root":
            other = tmp_path / "other-source-root"
            other.mkdir()
            (other / "selected-policy.md").write_bytes((selected_root / "selected-policy.md").read_bytes())
            client.app.state.rag_service.selected_source_service = ContextSourceService(other)
        assert client.post("/api/rag/run", json=context_request(query, pending)).status_code == 409
        assert client.post(f"/api/runtime/runs/{pending['runId']}/resume/preview", json={"sourceRequest": query}).status_code == 409
        clean = {**query, "selectedMemory": []}
        ok(client.post("/api/rag/index/rebuild", json={key: clean[key] for key in ("datasetId", "sourceSelection")}))
        assert client.post("/api/rag/preview", json=query).status_code == 409
        assert ok(client.post("/api/rag/preview", json=clean))["sourceBindings"][0]["identity"] != pending["sourceBindings"][0]["identity"]


def test_runtime_database_cannot_be_a_selected_index_cache(tmp_path, selected_root):
    with pytest.raises(ValueError, match="selected RAG caches"):
        with TestClient(create_app(context_source_root=selected_root, rag_index_path=tmp_path / "rag.sqlite3",
            runtime_path=tmp_path / "selected" / "runtime.sqlite3", plugin_root=tmp_path / "no-plugins")):
            pass


@pytest.mark.parametrize("target", ["runtime", "synthetic"])
def test_selected_cache_cannot_alias_another_database(tmp_path, selected_root, target):
    with TestClient(app_for(tmp_path, selected_root), raise_server_exceptions=False) as client:
        source = source_for(client)
        if target == "synthetic":
            ok(client.post("/api/rag/index/rebuild", json={"datasetId": "synthetic-risk-review-v1"}))
        cache = client.app.state.rag_service._selected(RagDatasetRequest.model_validate(source)).repository.path
        cache.parent.mkdir()
        protected = tmp_path / ("runtime.sqlite3" if target == "runtime" else "synthetic-index.sqlite3")
        os.link(protected, cache)
        original = protected.read_bytes()
        assert client.post("/api/rag/index/rebuild", json=source).status_code == 422
        assert protected.read_bytes() == original
