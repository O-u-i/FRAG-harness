"""Native Pi-shaped mock responses exercise actual governed tools without network calls."""
import json
from dataclasses import replace
from pathlib import Path

import pytest

from frag_api.errors import RagOutputError
from frag_api.providers.llm import LlmCallResult, LlmStageSettings
from frag_api.providers.research_native import host_call_id, normalize_pi_research
from frag_api.providers import pi_process
from frag_api.providers.pi import PiProvider
from frag_api.request_spec import fingerprint
from frag_api.schemas.common import ProviderUsage
from frag_api.services.runtime_service import RuntimeService
from frag_api.services.cli_executor import ToolExecutionError
from test_research_loop import execute, preview, start


def response_for(call, *, name="kb_read", number=1):
    manifest = call.request_body_input()["manifest"][0]
    arguments = {"identity": manifest["identity"], "revision": manifest["revision"],
                 "locatorIds": manifest["locatorIds"]}
    if name == "kb_read":
        arguments["evidenceIds"] = manifest["evidenceIds"][:10]
    else:
        arguments.update(query="synthetic", limit=3)
    return {"status": "completed", "outputText": "", "calls": [{"callId": f"call_{number}",
            "itemId": f"fc_{number}", "name": name, "argumentsText": json.dumps(arguments)}]}


class NativeScript:
    def __init__(self, mutation=None):
        self.calls, self.mutation = [], mutation

    def execute_prepared(self, call):
        self.calls.append(call)
        observations = [json.loads(item["output"]) for item in call.request_body()["input"]
                        if item.get("type") == "function_call_output"]
        if observations:
            value = {"status": "completed", "calls": [], "outputText": json.dumps({"action": "finish",
                     "evidenceIds": [row["evidenceId"] for item in observations if item["result"]
                                     for row in item["result"]["evidence"]], "missingInformation": []})}
        else:
            value = response_for(call)
        if self.mutation:
            self.mutation(value)
        decision, replay = normalize_pi_research(call, value)
        return LlmCallResult(decision, ProviderUsage(inputTokens=150, outputTokens=100), native_replay=replay)


def use_native(client, monkeypatch, provider=None):
    # This fixture verifies host integration, not installed worker/key readiness.
    monkeypatch.setattr(LlmStageSettings, "ready", property(lambda _self: True))
    service = client.app.state.harness_service
    stage = replace(service.settings.context, provider="openai", model="gpt-4.1-mini",
                    adapter="pi", api_key="synthetic-transport-token")
    service.settings = replace(service.settings, research=stage)
    service.research_provider = provider or NativeScript()
    return service.research_provider


def test_native_tool_wire_replays_actual_cli_result_under_fresh_approvals(client, monkeypatch):
    model = use_native(client, monkeypatch)
    source, first = start(client)
    wire = json.loads(first["preparedCall"]["body"])
    assert wire["parallel_tool_calls"] is False and wire["tool_choice"] == "auto"
    assert {item["name"] for item in wire["tools"]} == {"kb_read", "kb_search"}
    for tool in wire["tools"]:
        schema = tool["parameters"]
        assert tool["strict"] and schema["additionalProperties"] is False
        assert set(schema["required"]) == set(schema["properties"])
        identity = schema["$defs"]["SourceIdentity"]
        assert "workspaceId" in identity["required"]
        if tool["name"] == "kb_search":
            assert "limit" in schema["required"] and "default" not in schema["properties"]["limit"]
    assert "A synthetic finding is supported." not in json.dumps(wire)
    assert execute(client, source, first).status_code == 200
    saved = client.app.state.runtime.repository.get(first["runId"])
    attempt = saved.requests[0]
    native = attempt.native_replay.calls[0]
    assert attempt.native_replay_digest == fingerprint(attempt.native_replay.model_dump(by_alias=True))
    assert native.host_call_id == host_call_id(attempt.prepared_call, "call_1", "fc_1")
    assert saved.tool_calls[0].call_id == native.host_call_id and saved.tool_calls[0].carrier == "cli"
    assert saved.tool_calls[0].result.call_id == native.host_call_id
    assert execute(client, source, first).status_code == 409 and len(model.calls) == 1
    second = preview(client, source, first)
    transcript = json.loads(second["preparedCall"]["body"])["input"]
    assert transcript[1]["call_id"] == "call_1" and transcript[1]["id"] == "fc_1"
    assert transcript[1]["arguments"] == native.arguments_text
    assert transcript[2]["call_id"] == "call_1"
    result = json.loads(transcript[2]["output"])["result"]
    assert result == saved.tool_calls[0].result.model_dump(by_alias=True)
    assert "A synthetic finding is supported." in result["evidence"][0]["text"]
    assert len(model.calls) == 1 and second["approvalToken"] != first["approvalToken"]
    finished = execute(client, source, second)
    assert finished.status_code == 200, finished.text
    assert finished.json()["research"]["status"] == "awaiting_context"
    assert finished.json()["requests"][-1]["nativeReplay"] is None
    for stage in ("context", "inference"):
        formal = preview(client, source, first)
        assert formal["stage"] == stage
        result = execute(client, source, formal)
        assert result.status_code == 200, result.text
    assert result.json()["run"]["status"] == "awaiting_review"
    assert result.json()["semanticReview"] == "NOT_RUN" and len(model.calls) == 2


@pytest.mark.parametrize("invalid", ["duplicate-json", "nan", "partial", "extra-auth", "missing-workspace",
                                   "unknown-tool", "duplicate-id", "mixed", "wrong-limit",
                                   "extra-id", "non-string-id", "no-item"])
def test_invalid_native_proposals_are_known_failures_without_tool_execution(client, monkeypatch, invalid):
    def mutation(value):
        row = value["calls"][0]
        if invalid == "duplicate-json":
            row["argumentsText"] = '{"revision":"a","revision":"b"}'
        elif invalid == "nan":
            row["argumentsText"] = '{"query":NaN}'
        elif invalid == "partial":
            row["argumentsText"] = '{"identity":'
        elif invalid == "unknown-tool":
            row["name"] = "shell_run"
        elif invalid == "duplicate-id":
            value["calls"] *= 2
        elif invalid == "mixed":
            value["outputText"] = '{"action":"finish","evidenceIds":[],"missingInformation":[]}'
        elif invalid == "extra-id":
            row["hostCallId"] = "spoofed"
        elif invalid == "non-string-id":
            row["callId"] = 12
        elif invalid == "no-item":
            row.pop("itemId")
        else:
            arguments = json.loads(row["argumentsText"])
            if invalid == "extra-auth":
                arguments["authorization"] = "private-synthetic-token"
            elif invalid == "missing-workspace":
                arguments["identity"].pop("workspaceId")
            else:
                row["name"] = "kb_search"
                arguments.pop("evidenceIds")
                arguments.update(query="synthetic", limit="3")
            row["argumentsText"] = json.dumps(arguments)
    model = use_native(client, monkeypatch, NativeScript(mutation))
    source, first = start(client)
    response = execute(client, source, first)
    assert response.status_code == 502, response.text
    saved = client.app.state.runtime.repository.get(first["runId"])
    assert saved.run.status == "error" and saved.tool_calls == [] and len(model.calls) == 1
    assert saved.requests[0].output is None and saved.requests[0].native_replay is None


@pytest.mark.parametrize("change", ["call-id", "arguments", "digest", "missing-digest"])
def test_native_receipt_tampering_rejects_before_fresh_read_or_model_call(client, monkeypatch, change):
    model = use_native(client, monkeypatch)
    source, first = start(client)
    assert execute(client, source, first).status_code == 200
    def tamper(report):
        attempt = report.requests[0]
        native = attempt.native_replay.calls[0]
        if change == "call-id":
            native.call_id = "call_foreign"
        if change == "arguments":
            arguments = json.loads(native.arguments_text)
            arguments["evidenceIds"] = ["foreign"]
            native.arguments_text = json.dumps(arguments)
        attempt.native_replay_digest = (None if change == "missing-digest" else "0" * 64 if change == "digest"
                                        else fingerprint(attempt.native_replay.model_dump(by_alias=True)))
    client.app.state.runtime.repository.update(first["runId"], tamper)
    monkeypatch.setattr(client.app.state.harness_service.flow, "prepare_preview",
                        lambda *_: pytest.fail("Unexpected fresh source read"))
    response = client.post(f"/api/runtime/runs/{first['runId']}/research/preview", json={"sourceRequest": source})
    assert response.status_code == 409, response.text
    assert len(model.calls) == 1


def test_committed_native_response_restores_checkpoint_but_waits_for_explicit_tool_resume(client, monkeypatch):
    model = use_native(client, monkeypatch)
    source, first = start(client)
    runtime = client.app.state.runtime
    saved = runtime.repository.get(first["runId"])
    attempt = saved.requests[0]
    runtime.claim(saved.run.id, attempt.id, attempt.prepared_call)
    result = model.execute_prepared(attempt.prepared_call)
    runtime.returned(saved.run.id, attempt.id, result.output, result.usage, native_replay=result.native_replay)
    RuntimeService(runtime.repository)
    restored = runtime.repository.get(saved.run.id)
    assert restored.research.turns[0].status == "tools_pending" and restored.tool_calls == []
    second = preview(client, source, first)
    assert len(model.calls) == 1 and second["stage"] == "research"
    assert runtime.repository.get(saved.run.id).tool_calls[0].status == "completed"


def test_native_raw_secret_metadata_is_rejected_instead_of_saved_with_changed_ids(client, monkeypatch):
    model = use_native(client, monkeypatch)
    source, first = start(client)
    runtime = client.app.state.runtime
    runtime.secret_values = ("call_1",)
    response = execute(client, source, first)
    assert response.status_code == 502, response.text
    report = runtime.repository.get(first["runId"])
    assert report.requests[0].native_replay is None and report.requests[0].output is None
    assert report.tool_calls == [] and len(model.calls) == 1


def test_native_failure_observation_is_bound_to_actual_call_and_next_approval(client, monkeypatch):
    model = use_native(client, monkeypatch)
    registry = client.app.state.kb_tools.registry
    binding = registry.get("kb.read")
    def timeout(_payload):
        raise ToolExecutionError("TOOL_TIMEOUT")
    registry._bindings["kb.read"] = replace(binding, execute=timeout)
    source, first = start(client)
    response = execute(client, source, first)
    assert response.status_code == 200, response.text
    record = response.json()["toolCalls"][0]
    assert record["status"] == "failed" and record["result"] is None and record["errorCode"] == "TOOL_TIMEOUT"
    following = preview(client, source, first)
    transcript = json.loads(following["preparedCall"]["body"])["input"]
    assert transcript[1]["call_id"] == transcript[2]["call_id"] == "call_1"
    assert json.loads(transcript[2]["output"]) == {"status": "failed", "result": None, "errorCode": "TOOL_TIMEOUT"}
    assert len(model.calls) == 1 and following["approvalToken"] != first["approvalToken"]


def test_reordered_native_results_reject_before_any_fresh_read(client, monkeypatch):
    class Batch(NativeScript):
        def execute_prepared(self, call):
            self.calls.append(call)
            value = response_for(call)
            value["calls"].append({**value["calls"][0], "callId": "call_2", "itemId": "fc_2"})
            decision, replay = normalize_pi_research(call, value)
            return LlmCallResult(decision, ProviderUsage(inputTokens=150, outputTokens=200), native_replay=replay)
    model = use_native(client, monkeypatch, Batch())
    source, first = start(client)
    response = execute(client, source, first)
    assert response.status_code == 200, response.text
    assert len(response.json()["toolCalls"]) == 2
    client.app.state.runtime.repository.update(first["runId"], lambda report: report.tool_calls.reverse())
    monkeypatch.setattr(client.app.state.harness_service.flow, "prepare_preview",
                        lambda *_: pytest.fail("Unexpected fresh source read"))
    response = client.post(f"/api/runtime/runs/{first['runId']}/research/preview", json={"sourceRequest": source})
    assert response.status_code == 409, response.text
    assert len(model.calls) == 1


def test_tampered_committed_native_receipt_fails_offline_startup_without_tool_dispatch(client, monkeypatch):
    model = use_native(client, monkeypatch)
    source, first = start(client)
    runtime = client.app.state.runtime
    report = runtime.repository.get(first["runId"])
    attempt = report.requests[0]
    runtime.claim(report.run.id, attempt.id, attempt.prepared_call)
    result = model.execute_prepared(attempt.prepared_call)
    runtime.returned(report.run.id, attempt.id, result.output, result.usage, native_replay=result.native_replay)
    def tamper(current):
        current.requests[0].native_replay.calls[0].call_id = "call_foreign"
        current.requests[0].native_replay_digest = fingerprint(current.requests[0].native_replay.model_dump(by_alias=True))
    runtime.repository.update(report.run.id, tamper)
    RuntimeService(runtime.repository)
    saved = runtime.repository.get(report.run.id)
    assert saved.requests[0].error_code == "INVALID_PERSISTED_OUTPUT"
    assert saved.run.status == "error" and saved.tool_calls == [] and len(model.calls) == 1


@pytest.mark.parametrize("model", ["gpt-4.1-mini", "gpt-6.1-sol"])
def test_python_pi_node_sdk_sse_tool_and_formal_stages_share_the_governed_path(client, monkeypatch, model):
    """Real worker/Pi/SDK use a fixed in-memory SSE fixture; every host call is approved."""
    service = client.app.state.harness_service
    key = "sk-synthetic-worker-key"
    stage = replace(service.settings.context, provider="openai", model=model, adapter="pi",
                    api_key=key, timeout_seconds=30)
    assert stage.ready, "The already approved pinned worker must be installed for this integration check."
    service.settings = replace(service.settings, context=stage, inference=stage, research=stage)
    service.context_provider = service.inference_provider = service.research_provider = PiProvider(stage)
    client.app.state.runtime.secret_values = (key,)
    original, dispatched = pi_process.run_worker_process, []
    fixture = pi_process.WORKER_ROOT / "tests/host-fixture.mjs"
    def fixed_fixture(command, payload, expected, timeout, cwd):
        assert len(command) == 2 and Path(command[1]) == pi_process.WORKER_ROOT / "worker.mjs"
        assert key not in " ".join(command)
        envelope = json.loads(payload)
        assert envelope["apiKey"] == key
        dispatched.append(envelope["preparedCall"])
        return original([command[0], str(fixture)], payload, expected, timeout, cwd)
    monkeypatch.setattr(pi_process, "run_worker_process", fixed_fixture)
    source, first = start(client)
    assert dispatched == []
    first_result = execute(client, source, first)
    assert first_result.status_code == 200, first_result.text
    assert first_result.json()["toolCalls"][0]["carrier"] == "cli"
    assert first_result.json()["toolCalls"][0]["status"] == "completed"
    assert execute(client, source, first).status_code == 409 and len(dispatched) == 1
    final = first_result
    for expected_stage in ("research", "context", "inference"):
        next_request = preview(client, source, first)
        assert next_request["stage"] == expected_stage
        before = len(dispatched)
        assert before == {"research": 1, "context": 2, "inference": 3}[expected_stage]
        if expected_stage == "research":
            wire = json.loads(next_request["preparedCall"]["body"])
            native_call = next(item for item in wire["input"] if item.get("type") == "function_call")
            observation = next(item for item in wire["input"] if item.get("type") == "function_call_output")
            assert native_call["call_id"] == observation["call_id"]
            assert "A synthetic finding is supported." in observation["output"]
            if model == "gpt-6.1-sol":
                replay = first_result.json()["requests"][0]["nativeReplay"]
                assert replay["version"] == 2 and wire["input"][1:1 + len(replay["outputItems"])] == replay["outputItems"]
                assert "status" not in native_call
                assert any(item.get("phase") == "commentary" for item in wire["input"])
        final = execute(client, source, next_request)
        assert final.status_code == 200, final.text
        assert len(dispatched) == before + 1
    report = final.json()
    assert report["run"]["status"] == "awaiting_review" and report["semanticReview"] == "NOT_RUN"
    assert report["consumedTokens"] == 240 and len(report["toolCalls"]) == 1
    assert all(item["usage"] == {"inputTokens": 40, "outputTokens": 20} for item in report["requests"])
    assert len(dispatched) == 4 and all(item["transport"] == "pi-responses-v1" for item in dispatched)
    assert key not in json.dumps(report) and key not in json.dumps(dispatched)
    if model == "gpt-6.1-sol":
        assert all(json.loads(item["binding"])["nativeReplayVersion"] == 2 for item in dispatched)
        assert all(json.loads(item["body"])["reasoning"] == {"effort": "low"} for item in dispatched)
