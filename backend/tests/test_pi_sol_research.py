"""Synthetic Sol terminal items exercise raw persistence, CLI feedback and recovery."""
from copy import deepcopy
from dataclasses import replace
import json

import pytest

from frag_api.errors import RagOutputError
from frag_api.providers.llm import LlmCallResult, LlmStageSettings
from frag_api.providers.pi import PiProvider
from frag_api.providers.research_native import normalize_pi_research
from frag_api.request_spec import fingerprint
from frag_api.schemas.common import ProviderUsage
from frag_api.schemas.research import NativeResearchReplay, NativeResearchReplayV2
from frag_api.services.runtime_service import RuntimeService
from test_pi_research import response_for
from test_research_loop import execute, preview, start


def message(identifier, text, phase="final_answer"):
    return {"type": "message", "id": identifier, "role": "assistant", "status": "completed", "phase": phase,
            "content": [{"type": "output_text", "text": text, "annotations": []}]}


def sol_response(call, *, number=1, finish=False, reused_reasoning=None):
    reasoning = {"type": "reasoning", "id": reused_reasoning or f"rs_{number}", "summary": [],
                 "encrypted_content": f"opaque-synthetic-{number}"}
    if finish:
        observations = [json.loads(item["output"]) for item in call.request_body()["input"]
                        if item.get("type") == "function_call_output"]
        ids = list(dict.fromkeys(row["evidenceId"] for item in observations if item["result"]
                                for row in item["result"]["evidence"]))
        text = json.dumps({"action": "finish", "evidenceIds": ids, "missingInformation": []})
        calls, items = [], [reasoning, message(f"msg_{number}", text, None)]
    else:
        calls = response_for(call, number=number)["calls"]
        raw = calls[0]
        items = [reasoning, message(f"msg_{number}", "Read only the selected evidence.", "commentary"),
                 {"type": "function_call", "id": raw["itemId"], "call_id": raw["callId"],
                  "name": raw["name"], "arguments": raw["argumentsText"]}]
        text = ""
    return {"status": "completed", "outputText": text, "calls": calls, "outputItems": items,
            "usage": {"inputTokens": 150, "outputTokens": 100}}


class SolScript:
    def __init__(self, mutation=None, *, continue_twice=False):
        self.calls, self.responses, self.mutation, self.continue_twice = [], [], mutation, continue_twice

    def execute_prepared(self, call):
        self.calls.append(call)
        number = len(self.calls)
        response = sol_response(call, number=number, finish=number > (2 if self.continue_twice else 1))
        if self.mutation:
            self.mutation(response)
        self.responses.append(deepcopy(response))
        output, replay = normalize_pi_research(call, response)
        return LlmCallResult(output, ProviderUsage(**response["usage"]), native_replay=replay)


def use_sol(client, monkeypatch, script=None):
    monkeypatch.setattr(LlmStageSettings, "ready", property(lambda _self: True))
    service = client.app.state.harness_service
    stage = replace(service.settings.context, provider="openai", model="gpt-6.1-sol", adapter="pi",
                    api_key="sk-synthetic-worker-key")
    service.settings = replace(service.settings, research=stage)
    service.research_provider = script or SolScript()
    return service.research_provider, stage


def test_sol_keeps_raw_absent_fields_and_order_then_actual_cli_feedback(client, monkeypatch):
    script, _ = use_sol(client, monkeypatch)
    source, first = start(client)
    prepared = json.loads(first["preparedCall"]["body"])
    assert prepared["reasoning"] == {"effort": "low"}
    assert prepared["include"] == ["reasoning.encrypted_content"]
    assert json.loads(first["preparedCall"]["binding"])["nativeReplayVersion"] == 2
    one = execute(client, source, first)
    assert one.status_code == 200, one.text
    saved = client.app.state.runtime.repository.get(first["runId"])
    replay = saved.requests[0].native_replay
    assert replay.version == 2 and replay.output_items == script.responses[0]["outputItems"]
    assert "status" not in replay.output_items[0] and "status" not in replay.output_items[2]
    assert saved.requests[0].native_replay_digest == fingerprint(replay.model_dump(by_alias=True))
    assert saved.tool_calls[0].carrier == "cli" and saved.tool_calls[0].status == "completed"
    second = preview(client, source, first)
    wire = json.loads(second["preparedCall"]["body"])["input"]
    assert wire[1:4] == replay.output_items
    assert wire[4]["type"] == "function_call_output" and wire[4]["call_id"] == replay.calls[0].call_id
    assert json.loads(wire[4]["output"]) == {"status": "completed", "errorCode": None,
                                           "result": saved.tool_calls[0].result.model_dump(by_alias=True)}
    assert len(script.calls) == 1 and second["approvalToken"] != first["approvalToken"]
    assert execute(client, source, first).status_code == 409
    finished = execute(client, source, second)
    assert finished.status_code == 200, finished.text
    assert finished.json()["requests"][-1]["nativeReplay"]["calls"] == []
    assert finished.json()["requests"][-1]["nativeReplay"]["outputItems"] == script.responses[-1]["outputItems"]
    assert finished.json()["research"]["status"] == "awaiting_context"
    for expected in ("context", "inference"):
        formal = preview(client, source, first)
        assert formal["stage"] == expected
        result = execute(client, source, formal)
        assert result.status_code == 200, result.text
    assert result.json()["run"]["status"] == "awaiting_review"
    assert result.json()["semanticReview"] == "NOT_RUN" and len(script.calls) == 2


@pytest.mark.parametrize("invalid", ["ciphertext", "partial-status", "call-status", "unknown-field", "unknown-type",
                                   "duplicate-item", "wrong-call-map", "mixed-final", "wrong-text", "bad-phase"])
def test_sol_invalid_complete_metadata_never_dispatches_a_tool(client, monkeypatch, invalid):
    def mutate(response):
        items = response["outputItems"]
        if invalid == "ciphertext":
            items[0]["encrypted_content"] = None
        elif invalid == "partial-status":
            items[0]["status"] = "in_progress"
        elif invalid == "call-status":
            items[2]["status"] = "incomplete"
        elif invalid == "unknown-field":
            items[0]["headers"] = {"authorization": "private"}
        elif invalid == "unknown-type":
            items[0]["type"] = "web_search_call"
        elif invalid == "duplicate-item":
            items.append(deepcopy(items[0]))
        elif invalid == "wrong-call-map":
            response["calls"][0]["itemId"] = "fc_foreign"
        elif invalid == "mixed-final":
            items[1]["phase"] = "final_answer"
            response["outputText"] = items[1]["content"][0]["text"]
        elif invalid == "bad-phase":
            items[1]["phase"] = "unknown"
        else:
            response["outputText"] = "not the actual text"
    script, _ = use_sol(client, monkeypatch, SolScript(mutate))
    source, first = start(client)
    result = execute(client, source, first)
    assert result.status_code == 502, result.text
    report = client.app.state.runtime.repository.get(first["runId"])
    assert report.tool_calls == [] and report.requests[0].native_replay is None and len(script.calls) == 1


@pytest.mark.parametrize("changed", ["digest", "ciphertext", "order", "missing-digest"])
def test_sol_replay_tamper_rejects_before_fresh_source_read(client, monkeypatch, changed):
    script, _ = use_sol(client, monkeypatch)
    source, first = start(client)
    assert execute(client, source, first).status_code == 200
    def tamper(report):
        attempt = report.requests[0]
        if changed == "ciphertext":
            attempt.native_replay.output_items[0]["encrypted_content"] = "modified-opaque"
        elif changed == "order":
            attempt.native_replay.output_items.reverse()
        attempt.native_replay_digest = None if changed == "missing-digest" else "0" * 64
    client.app.state.runtime.repository.update(first["runId"], tamper)
    monkeypatch.setattr(client.app.state.harness_service.flow, "prepare_preview", lambda *_: pytest.fail("Fresh source read"))
    response = client.post(f"/api/runtime/runs/{first['runId']}/research/preview", json={"sourceRequest": source})
    assert response.status_code == 409 and len(script.calls) == 1


def test_sol_duplicate_noncall_history_id_rejects_before_fresh_source_read(client, monkeypatch):
    script, _ = use_sol(client, monkeypatch, SolScript(continue_twice=True))
    source, first = start(client)
    assert execute(client, source, first).status_code == 200
    second = preview(client, source, first)
    assert execute(client, source, second).status_code == 200
    def tamper(report):
        first_id = report.requests[0].native_replay.output_items[0]["id"]
        attempt = report.requests[1]
        attempt.native_replay.output_items[0]["id"] = first_id
        attempt.native_replay_digest = fingerprint(attempt.native_replay.model_dump(by_alias=True))
    client.app.state.runtime.repository.update(first["runId"], tamper)
    monkeypatch.setattr(client.app.state.harness_service.flow, "prepare_preview", lambda *_: pytest.fail("Fresh source read"))
    response = client.post(f"/api/runtime/runs/{first['runId']}/research/preview", json={"sourceRequest": source})
    assert response.status_code == 409 and len(script.calls) == 2


def test_sol_returned_output_restores_offline_then_waits_for_explicit_tool_resume(client, monkeypatch):
    script, _ = use_sol(client, monkeypatch)
    source, first = start(client)
    runtime = client.app.state.runtime
    report = runtime.repository.get(first["runId"])
    attempt = report.requests[0]
    runtime.claim(report.run.id, attempt.id, attempt.prepared_call)
    result = script.execute_prepared(attempt.prepared_call)
    runtime.returned(report.run.id, attempt.id, result.output, result.usage, native_replay=result.native_replay)
    RuntimeService(runtime.repository)
    restored = runtime.repository.get(report.run.id)
    assert restored.research.turns[0].status == "tools_pending" and restored.tool_calls == []
    assert restored.requests[0].native_replay.output_items == script.responses[0]["outputItems"]
    second = preview(client, source, first)
    assert second["stage"] == "research" and len(script.calls) == 1
    assert runtime.repository.get(report.run.id).tool_calls[0].status == "completed"


def test_sol_formal_provider_checks_raw_phase_and_ignores_commentary_for_json(client, monkeypatch):
    _, stage = use_sol(client, monkeypatch)
    service = client.app.state.harness_service
    service.settings = replace(service.settings, context=stage)
    source, first = start(client)
    assert execute(client, source, first).status_code == 200
    assert execute(client, source, preview(client, source, first)).status_code == 200
    formal = preview(client, source, first)
    from frag_api.schemas.governance import PreparedCall
    call = PreparedCall.model_validate(formal["preparedCall"])
    from frag_api.providers.llm import FakeLlmProvider
    from frag_api.schemas.rag import RagEvidence
    output = FakeLlmProvider().generate_rag_context(
        [RagEvidence.model_validate(item) for item in call.request_body_input()["evidence"]],
        call.request_body()["max_output_tokens"],
    ).output.model_dump(by_alias=True)
    text = json.dumps(output)
    response = {"status": "completed", "outputText": text, "calls": [], "usage": {"inputTokens": 20, "outputTokens": 10},
                "outputItems": [{"type": "reasoning", "id": "rs_formal", "summary": [], "encrypted_content": None},
                                message("msg_commentary", "This is commentary, not JSON.", "commentary"),
                                message("msg_final", text)]}
    monkeypatch.setattr("frag_api.providers.pi.execute_worker", lambda *_: {"ok": True, "response": response})
    actual = PiProvider(stage).execute_prepared(call)
    assert actual.output.model_dump(by_alias=True) == output and actual.native_replay is None
    response["outputItems"][-1]["content"][0]["text"] = "changed final text"
    with pytest.raises(RagOutputError):
        PiProvider(stage).execute_prepared(call)


def test_v1_serialization_digest_stays_exact_and_v2_keeps_absent_optional_fields():
    value = {"version": 1, "calls": [{"callId": "call_legacy", "itemId": "fc_legacy", "name": "kb_read",
             "argumentsText": "{}", "hostCallId": "pi_" + "a" * 64}]}
    assert NativeResearchReplay.model_validate(value).model_dump(by_alias=True) == value
    assert fingerprint(value) == fingerprint(NativeResearchReplay.model_validate_json(json.dumps(value)).model_dump(by_alias=True))
    raw = {"version": 2, "calls": [], "outputItems": [{"type": "reasoning", "id": "rs_final", "summary": []},
           message("msg_final", '{"action":"finish","evidenceIds":[],"missingInformation":[]}', None)]}
    assert NativeResearchReplayV2.model_validate_json(json.dumps(raw)).model_dump(by_alias=True) == raw


def test_sol_raw_argument_cap_counts_utf8_bytes_before_host_tool_dispatch():
    from frag_api.providers.response_items import validate_output_items
    item = {"type": "function_call", "id": "fc_utf8", "call_id": "call_utf8", "name": "kb_read",
            "arguments": '"' + "\u4e2d" * 6000 + '"'}
    assert len(item["arguments"]) < 16384 < len(item["arguments"].encode("utf-8"))
    with pytest.raises(ValueError):
        validate_output_items([item])
