"""Score exported original host artifacts without replaying a provider or source read."""
import copy
import json
import os
from pathlib import Path
import subprocess

import httpx
import pytest
from fastapi.testclient import TestClient

from frag_api.captured_evaluation import score_capture
from frag_api.evaluation import render_markdown
from frag_api.providers.llm import FakeLlmProvider, OpenAICompatibleProvider
from frag_api.request_spec import canonical_json, estimated_tokens, fingerprint
from test_research_loop import execute as research_execute, preview as research_preview, start as research_start
from test_runtime_recovery import app_for, finish, preview, report, selection

NOTE = "# Conditions\nOnly beta access. Writes are not allowed. Review date: 2026-10-05. Cap: 10 MiB. Launch date unknown."
FACTS = [
    {"id": "scope", "kind": "constraint", "alternatives": ["Only beta access"], "forbidden": ["All users have access"]},
    {"id": "write", "kind": "negation", "alternatives": ["Writes are not allowed"], "forbidden": ["Writes are allowed"]},
    {"id": "date", "kind": "date", "alternatives": ["2026-10-05"], "forbidden": ["2026-10-06"]},
    {"id": "unit", "kind": "unit", "alternatives": ["10 MiB"], "forbidden": ["10 GiB"]},
]


class MissingFake(FakeLlmProvider):
    def execute_prepared(self, call):
        result = super().execute_prepared(call)
        if call.purpose != "research":
            result.output.missing_information.append("Launch date unknown.")
        return result


def gold_for(saved):
    return {"schemaVersion": 1, "suiteId": "synthetic-captured-conditions", "suiteVersion": "1.0.0",
            "runId": saved["run"]["id"], "goal": saved["selection"]["goal"],
            "sourceBindings": copy.deepcopy(saved["selection"]["sourceBindings"]),
            "expectedEvidenceIds": [row["evidenceId"] for row in saved["selection"]["candidateEvidence"]],
            "facts": copy.deepcopy(FACTS), "requiredMissingInformation": ["Launch date unknown"]}


def write_inputs(tmp_path, saved, gold):
    capture_path, gold_path = tmp_path / "capture.json", tmp_path / "capture-gold.json"
    capture_path.write_text(json.dumps(saved, ensure_ascii=False), encoding="utf-8")
    gold_path.write_text(json.dumps(gold, ensure_ascii=False), encoding="utf-8")
    return gold_path, capture_path


def evaluate(tmp_path, saved, gold):
    return score_capture(*write_inputs(tmp_path, saved, gold))


def checks(result):
    return {item.id: item for item in result.cases[0].checks}


def rebind(call, *, body=None, binding=None):
    if body is not None:
        call["body"] = canonical_json(body)
        call["estimatedInputTokens"] = estimated_tokens(body)
    if binding is not None:
        call["binding"] = canonical_json(binding)
    call["fingerprint"] = fingerprint({key: value for key, value in call.items() if key != "fingerprint"})


@pytest.fixture
def captured(tmp_path):
    source = tmp_path / "selected-source"
    source.mkdir()
    (source / "evidence.md").write_text(NOTE, encoding="utf-8")
    with TestClient(app_for(tmp_path, source, MissingFake()), raise_server_exceptions=False) as client:
        initial, _, final = finish(client, selection(client))
        run_id = initial["runId"]
        assert client.post(f"/api/runtime/runs/{run_id}/review", json={
            "decision": "accepted", "checklist": {"templateId": "evidence-review-v1", "checklist": []},
            "note": "Synthetic review record; not live acceptance.",
        }).status_code == 200
        revision = copy.deepcopy(final["result"])
        revision["answer"] = "Separate human revision: 2026-10-06, 10 GiB, writes are allowed."
        assert client.post(f"/api/runtime/runs/{run_id}/revisions", json={
            "result": revision, "note": "Original model answer must remain the scorer input.",
        }).status_code == 200
        saved = report(client, run_id)
    return saved, gold_for(saved)


def test_capture_scores_original_artifacts_without_provider_source_or_runtime_calls(tmp_path, captured, monkeypatch):
    saved, gold = captured
    def forbidden(*args, **kwargs):
        pytest.fail("Capture scoring must not execute a provider, runtime or source read.")
    from frag_api.services.context_source_service import ContextSourceService
    from frag_api.services.runtime_service import RuntimeService
    monkeypatch.setattr(FakeLlmProvider, "execute_prepared", forbidden)
    monkeypatch.setattr(OpenAICompatibleProvider, "execute_prepared", forbidden)
    monkeypatch.setattr(httpx.Client, "send", forbidden)
    monkeypatch.setattr(ContextSourceService, "read_snapshot", forbidden)
    monkeypatch.setattr(RuntimeService, "__init__", forbidden)
    result = evaluate(tmp_path, saved, gold)
    assert result.status == "PASS", result.model_dump_json(indent=2)
    assert result.provider == "captured-artifacts" and result.runner_version == "1.2.0"
    assert result.semantic_review_status == "UNDETERMINED" and result.trajectory_status == "NOT_RUN"
    assert checks(result)["capture.approval"].status == "NOT_RUN"
    assert checks(result)["capture.current_source"].status == "NOT_RUN"
    trace = result.cases[0].trace
    assert trace["capture"] == saved and trace["recordedHumanSemanticReview"] == "NOT_RUN"
    assert trace["capture"]["modelOutput"]["answer"] != trace["capture"]["revisions"][-1]["result"]["answer"]


@pytest.mark.parametrize("original,replacement,fact", [
    ("Writes are not allowed", "Writes are allowed", "write"),
    ("2026-10-05", "2026-10-06", "date"),
    ("10 MiB", "10 GiB", "unit"),
    ("Only beta access", "All users have access", "scope"),
])
def test_actual_captured_literal_violation_fails_with_legal_citations(tmp_path, captured, original, replacement, fact):
    saved, gold = captured
    answer = saved["modelOutput"]
    answer["answer"] = answer["answer"].replace(original, replacement)
    for item in answer["claims"]:
        item["text"] = item["text"].replace(original, replacement)
    call = next(item for item in saved["requests"] if item["stage"] == "inference" and item["output"] is not None)
    call["output"] = copy.deepcopy(answer)
    call["outputDigest"] = fingerprint(call["output"])
    result = evaluate(tmp_path, saved, gold)
    assert result.status == "FAIL" and result.cases[0].host_enforcement_status == "PASS"
    assert checks(result)["citation.identifiers"].status == "PASS"
    assert checks(result)[f"inference.fact.{fact}"].status == "FAIL"
    assert result.semantic_review_status == "UNDETERMINED"


def test_missing_information_and_invalid_citation_fail_on_original_saved_output(tmp_path, captured):
    saved, gold = captured
    saved["modelOutput"]["missingInformation"] = []
    saved["modelOutput"]["claims"][0]["evidenceIds"] = ["not-current-evidence"]
    call = next(item for item in saved["requests"] if item["stage"] == "inference" and item["output"] is not None)
    call["output"] = copy.deepcopy(saved["modelOutput"])
    call["outputDigest"] = fingerprint(call["output"])
    result = evaluate(tmp_path, saved, gold)
    assert result.status == "FAIL"
    assert checks(result)["inference.missing.0"].status == "FAIL"
    assert checks(result)["citation.identifiers"].status == "FAIL"


@pytest.mark.parametrize("change", ["snapshot", "output", "request", "body", "revision", "duplicate-attempt", "context-link"])
def test_captured_record_tampering_is_error_not_pass(tmp_path, captured, change):
    saved, gold = captured
    if change == "snapshot":
        saved["selection"]["candidateEvidence"][0]["text"] += " changed"
    elif change == "output":
        saved["requests"][0]["outputDigest"] = "0" * 64
    elif change == "request":
        saved["requests"][0]["preparedCall"]["endpoint"] = "https://example.invalid/responses"
    elif change == "body":
        saved["requests"][0]["preparedCall"]["body"] = '{"model":"a","model":"b"}'
    elif change == "revision":
        saved["revisions"][0]["result"]["answer"] += " changed"
    elif change == "context-link":
        call = next(item["preparedCall"] for item in saved["requests"] if item["stage"] == "inference")
        binding = json.loads(call["binding"])
        binding["contextFingerprint"] = "0" * 64
        call["binding"] = canonical_json(binding)
        call["fingerprint"] = fingerprint({key:value for key,value in call.items() if key != "fingerprint"})
    else:
        saved["requests"].append(copy.deepcopy(saved["requests"][0]))
    result = evaluate(tmp_path, saved, gold)
    assert result.status == "ERROR" and result.cases == []
    assert result.counts["ERROR"] == 1 and result.semantic_review_status == "UNDETERMINED"


def test_recorded_human_semantic_pass_is_retained_but_not_inferred_by_literal_scorer(tmp_path, captured):
    saved, gold = captured
    saved["semanticReview"] = "PASS"
    result = evaluate(tmp_path, saved, gold)
    assert result.status == "PASS" and result.semantic_review_status == "UNDETERMINED"
    assert result.cases[0].trace["recordedHumanSemanticReview"] == "PASS"


@pytest.mark.parametrize("change", ["expanded-limit", "task", "unselected-memory"])
def test_rehashed_request_cannot_contradict_known_limits_checklist_or_memory(tmp_path, captured, change):
    saved, gold = captured
    context_call = next(item["preparedCall"] for item in saved["requests"] if item["stage"] == "context")
    body = json.loads(context_call["body"])
    if change == "expanded-limit":
        body["max_output_tokens"] = 100_000
    else:
        payload = json.loads(body["input"])
        if change == "task":
            payload["task"]["checklist"] = [{"id": "foreign", "text": "Unbound checklist item",
                "blocking": False, "status": "met", "reviewed": True}]
        else:
            payload["memory"] = [{"memoryId": "unselected", "version": 1, "text": "Unconfirmed background."}]
        body["input"] = canonical_json(payload)
    rebind(context_call, body=body)
    inference_call = next(item["preparedCall"] for item in saved["requests"] if item["stage"] == "inference")
    binding = json.loads(inference_call["binding"])
    binding["contextFingerprint"] = context_call["fingerprint"]
    rebind(inference_call, binding=binding)
    assert evaluate(tmp_path, saved, gold).status == "ERROR"


def test_original_context_must_fit_its_recorded_request_limit(tmp_path, captured):
    saved, gold = captured
    context_call = next(item["preparedCall"] for item in saved["requests"] if item["stage"] == "context")
    body = json.loads(context_call["body"])
    body["max_output_tokens"] = 1
    rebind(context_call, body=body)
    inference_call = next(item["preparedCall"] for item in saved["requests"] if item["stage"] == "inference")
    binding = json.loads(inference_call["binding"])
    binding["contextFingerprint"] = context_call["fingerprint"]
    rebind(inference_call, binding=binding)
    result = evaluate(tmp_path, saved, gold)
    assert result.status == "FAIL" and checks(result)["context.limit"].status == "FAIL"


@pytest.mark.parametrize("research", [False, True])
def test_captured_confirmed_memory_bindings_remain_historical_without_memory_access(tmp_path, research, monkeypatch):
    from test_memory_integration import candidate, promote, selected as memory_choice
    source = tmp_path / "selected-source"
    source.mkdir()
    (source / "evidence.md").write_text(NOTE, encoding="utf-8")
    model = MissingFake()
    with TestClient(app_for(tmp_path, source, model), raise_server_exceptions=False) as client:
        selected = selection(client)
        origin, _, _ = finish(client, selected)
        memory = promote(client, candidate(client, origin["runId"], text="Reviewed background; preserve current unknowns."))
        selected["selectedMemory"] = memory_choice(memory)
        if research:
            client.app.state.harness_service.research_provider = model
            _, initial = research_start(client, selected)
            assert research_execute(client, selected, initial).status_code == 200
            for expected in ("research", "context", "inference"):
                shown = research_preview(client, selected, initial)
                assert shown["stage"] == expected
                assert research_execute(client, selected, shown).status_code == 200
        else:
            initial, _, _ = finish(client, selected)
        saved = report(client, initial["runId"])
        assert client.post(f"/api/memory/{memory['id']}/retire", json={"version": memory["version"]}).status_code == 200
    from frag_api.services.memory_service import MemoryService
    monkeypatch.setattr(MemoryService, "select", lambda *args, **kwargs: pytest.fail("Capture must not consult live memory."))
    result = evaluate(tmp_path, saved, gold_for(saved))
    assert result.status == "PASS", result.model_dump_json(indent=2)
    assert result.cases[0].trace["capture"]["selection"]["input"]["selectedMemory"] == memory_choice(memory)


@pytest.mark.parametrize("change", ["foreign-evidence", "duplicate-fact", "version", "duplicate-key"])
def test_invalid_capture_gold_is_error_before_scoring(tmp_path, captured, change):
    saved, gold = captured
    if change == "foreign-evidence":
        gold["expectedEvidenceIds"] = ["not-in-bound-source"]
    elif change == "duplicate-fact":
        gold["facts"].append(copy.deepcopy(gold["facts"][0]))
    elif change == "version":
        gold["schemaVersion"] = 2
    gold_path, capture_path = write_inputs(tmp_path, saved, gold)
    if change == "duplicate-key":
        gold_path.write_text('{"schemaVersion":1,"schemaVersion":1}', encoding="utf-8")
    assert score_capture(gold_path, capture_path).status == "ERROR"


@pytest.mark.parametrize("change", ["goal", "revision", "run"])
def test_gold_must_match_actual_capture_selection_before_fact_scoring(tmp_path, captured, change):
    saved, gold = captured
    if change == "goal":
        gold["goal"] = "Different actual question"
    elif change == "revision":
        gold["sourceBindings"][0]["revision"] += "-changed"
    else:
        gold["runId"] = "another-run"
    result = evaluate(tmp_path, saved, gold)
    assert result.status == "FAIL" and checks(result)["gold.source_binding"].status == "FAIL"
    assert checks(result)["model.scoring"].status == "NOT_RUN"
    assert not any(item.id.startswith("inference.fact") for item in result.cases[0].checks)


@pytest.mark.parametrize("unknown", [False, True])
def test_unexecuted_or_unknown_capture_never_infers_output_or_resends(tmp_path, unknown):
    source = tmp_path / "selected-source"
    source.mkdir()
    (source / "evidence.md").write_text(NOTE, encoding="utf-8")
    with TestClient(app_for(tmp_path, source, MissingFake()), raise_server_exceptions=False) as client:
        initial = preview(client, selection(client))
        saved = report(client, initial["runId"])
    if unknown:
        saved["run"]["status"] = "outcome_unknown"
        saved["requests"][0]["status"] = "outcome_unknown"
    result = evaluate(tmp_path, saved, gold_for(saved))
    assert result.status == ("UNDETERMINED" if unknown else "NOT_RUN")
    assert result.cases[0].model_quality_status == result.status
    assert checks(result)["context.execution"].status == "NOT_RUN"
    assert checks(result)["inference.execution"].status == "NOT_RUN"
    assert result.cases[0].trace["capture"]["modelOutput"] is None


def research_capture(tmp_path, monkeypatch=None, profile="fake"):
    source = tmp_path / "selected-source"
    source.mkdir()
    (source / "evidence.md").write_text(NOTE, encoding="utf-8")
    model = MissingFake()
    with TestClient(app_for(tmp_path, source, model), raise_server_exceptions=False) as client:
        client.app.state.harness_service.research_provider = model
        if profile == "pi-native-v1":
            from test_pi_research import use_native
            use_native(client, monkeypatch)
        elif profile == "pi-sol-v2":
            from test_pi_sol_research import use_sol
            use_sol(client, monkeypatch)
        selected = selection(client)
        _, initial = research_start(client, selected)
        assert research_execute(client, selected, initial).status_code == 200
        for expected in ("research", "context", "inference"):
            shown = research_preview(client, selected, initial)
            assert shown["stage"] == expected
            assert research_execute(client, selected, shown).status_code == 200
        saved = report(client, initial["runId"])
    return saved


def test_completed_research_capture_reuses_recorded_policy_and_call_result_validation(tmp_path):
    saved = research_capture(tmp_path)
    result = evaluate(tmp_path, saved, gold_for(saved))
    assert result.status == "PASS", result.model_dump_json(indent=2)
    assert result.trajectory_status == "PASS"
    assert result.cases[0].trace["capture"]["toolCalls"][0]["carrier"] == "cli"
    saved["toolCalls"][0]["result"]["callId"] = "another-call"
    assert evaluate(tmp_path, saved, gold_for(saved)).status == "ERROR"


@pytest.mark.parametrize("profile", ["fake", "pi-native-v1", "pi-sol-v2"])
def test_captured_research_wire_preserves_actual_prior_results_and_rejects_removed_feedback(tmp_path, monkeypatch, profile):
    saved = research_capture(tmp_path, monkeypatch, profile)
    gold = gold_for(saved)
    result = evaluate(tmp_path, saved, gold)
    assert result.status == "PASS", result.model_dump_json(indent=2)
    assert result.trajectory_status == "PASS"
    second_call = [item["preparedCall"] for item in saved["requests"] if item["stage"] == "research"][1]
    body = json.loads(second_call["body"])
    if profile == "fake":
        payload = json.loads(body["input"])
        assert payload["observations"]
        payload["observations"] = []
        payload["decisions"] = []
        body["input"] = canonical_json(payload)
    else:
        assert any(item.get("type") == "function_call_output" for item in body["input"])
        body["input"] = body["input"][:1]
    rebind(second_call, body=body)
    # Sol's terminal raw receipt contains no proposed call, so rehashing the request
    # does not invalidate a host call ID; the wire-history check must reject it.
    assert evaluate(tmp_path, saved, gold).status == "ERROR"


def test_capture_cli_json_and_markdown_share_report_and_status(tmp_path, captured):
    saved, gold = captured
    gold_path, capture_path = write_inputs(tmp_path, saved, gold)
    environment = {**os.environ, "PYTHON_DOTENV_DISABLED": "1"}
    command = [os.sys.executable, "-m", "frag_api.evaluation", "--gold", str(gold_path), "--capture", str(capture_path)]
    result = subprocess.run(command, cwd=Path(__file__).resolve().parents[1], env=environment,
                            capture_output=True, text=True, encoding="utf-8", timeout=20)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["provider"] == "captured-artifacts" and payload["semanticReviewStatus"] == "UNDETERMINED"
    rendered = render_markdown(score_capture(gold_path, capture_path))
    assert json.loads(rendered.split("```json\n", 1)[1].rsplit("\n```", 1)[0]) == payload
    gold["requiredMissingInformation"] = ["Unknown undeclared fact"]
    gold_path.write_text(json.dumps(gold), encoding="utf-8")
    failed = subprocess.run(command, cwd=Path(__file__).resolve().parents[1], env=environment,
                            capture_output=True, text=True, encoding="utf-8", timeout=20)
    assert failed.returncode == 2 and json.loads(failed.stdout)["status"] == "FAIL"
