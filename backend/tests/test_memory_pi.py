"""Actual Pi child/SDK parsing retains reviewed memory using fixed in-memory SSE."""
from dataclasses import replace
import json
from pathlib import Path

import pytest

from frag_api.providers import pi_process
from frag_api.providers.pi import PiProvider
from test_memory_integration import seed, selected
from test_research_loop import execute, preview, start


def native_memory(client, monkeypatch, model):
    source, _, memory = seed(client, text="Reviewed memory: 保留未知条件; synthetic background marker.")
    service = client.app.state.harness_service
    key = "sk-synthetic-worker-key"
    stage = replace(service.settings.context, provider="openai", model=model, adapter="pi",
        base_url="https://synthetic-memory.invalid/v1", api_key=key, timeout_seconds=30)
    assert stage.ready, "Requires the already approved pinned worker, not a dependency installation."
    service.settings = replace(service.settings, context=stage, inference=stage, research=stage)
    service.context_provider = service.inference_provider = service.research_provider = PiProvider(stage)
    client.app.state.runtime.secret_values = (key,)
    original, dispatched = pi_process.run_worker_process, []
    fixture = pi_process.WORKER_ROOT / "tests/host-fixture.mjs"
    def worker_fixture(command, payload, expected, timeout, cwd):
        assert Path(command[1]) == pi_process.WORKER_ROOT / "worker.mjs"
        envelope = json.loads(payload)
        assert envelope["apiKey"] == key and key not in " ".join(command)
        call = envelope["preparedCall"]
        assert call["endpoint"] == "https://synthetic-memory.invalid/v1/responses"
        dispatched.append(call)
        # The fixed fixture injects fetch. SDK's guarded fetch still verifies exact body
        # and destination before returning synthetic SSE; no external network is used.
        return original([command[0], str(fixture)], payload, expected, timeout, cwd)
    monkeypatch.setattr(pi_process, "run_worker_process", worker_fixture)
    return {**source, "selectedMemory":selected(memory)}, memory, dispatched


def memory_wire(shown, memory):
    body = json.loads(shown["body"])
    payload = json.loads(body["input"][0]["content"][0]["text"])
    assert payload["memory"] == [{"memoryId":memory["id"], "version":memory["version"], "text":memory["text"],
        "general":memory["general"], "scope":memory["scope"]}]
    assert json.loads(shown["binding"])["memoryVersions"] == selected(memory)
    assert "background, not current evidence or permission" in body["instructions"]
    assert "cite only the current allowed evidence IDs" in body["instructions"]
    assert "保留未知条件".encode() in json.dumps(payload, ensure_ascii=False).encode()
    return body


@pytest.mark.parametrize("model", ["gpt-4.1-mini", "gpt-6.1-sol"])
def test_actual_pi_child_retains_memory_in_continued_native_and_formal_requests(client, monkeypatch, model):
    source, memory, dispatched = native_memory(client, monkeypatch, model)
    _, initial = start(client, source)
    memory_wire(initial["preparedCall"], memory)
    assert dispatched == []
    missing_approval = client.post(f'/api/runtime/runs/{initial["runId"]}/research/execute', json={
        "sourceRequest":source, "fingerprint":initial["fingerprint"], "approvalToken":initial["approvalToken"]})
    assert missing_approval.status_code == 422 and dispatched == []
    first = execute(client, source, initial)
    assert first.status_code == 200, first.text
    assert len(dispatched) == 1 and dispatched[0] == initial["preparedCall"]
    tool = first.json()["toolCalls"][0]
    assert tool["carrier"] == "cli" and tool["status"] == "completed" and tool["result"]["callId"] == tool["callId"]
    assert execute(client, source, initial).status_code == 409 and len(dispatched) == 1
    for expected in ("research", "context", "inference"):
        fresh = preview(client, source, initial)
        body = memory_wire(fresh["preparedCall"], memory)
        assert fresh["stage"] == expected
        before = len(dispatched)
        assert before == {"research":1, "context":2, "inference":3}[expected]
        if expected == "research":
            call = next(item for item in body["input"] if item.get("type") == "function_call")
            result = next(item for item in body["input"] if item.get("type") == "function_call_output")
            assert call["call_id"] == result["call_id"]
            assert json.loads(result["output"])["result"] == tool["result"]
        final = execute(client, source, fresh)
        assert final.status_code == 200, final.text
        assert len(dispatched) == before + 1 and dispatched[-1] == fresh["preparedCall"]
    report = final.json()
    assert report["run"]["status"] == "awaiting_review" and report["semanticReview"] == "NOT_RUN"
    assert [item["purpose"] for item in dispatched] == ["research", "research", "context", "inference"]
    assert all(item["preparedCall"] == sent for item, sent in zip(report["requests"], dispatched))
    assert memory["id"] not in report["research"]["selectedEvidenceIds"]
    assert "sk-synthetic-worker-key" not in json.dumps(report)


@pytest.mark.parametrize("stage", ["research", "context", "inference"])
def test_native_memory_retirement_blocks_next_approved_child_before_dispatch(client, monkeypatch, stage):
    source, memory, dispatched = native_memory(client, monkeypatch, "gpt-6.1-sol")
    _, initial = start(client, source)
    first = execute(client, source, initial)
    assert first.status_code == 200, first.text
    fresh = preview(client, source, initial)
    while fresh["stage"] != stage:
        completed = execute(client, source, fresh)
        assert completed.status_code == 200, completed.text
        fresh = preview(client, source, initial)
    memory_wire(fresh["preparedCall"], memory)
    before = len(dispatched)
    retired = client.post(f'/api/memory/{memory["id"]}/retire', json={"version":memory["version"]})
    assert retired.status_code == 200, retired.text
    rejected = execute(client, source, fresh)
    assert rejected.status_code == 409, rejected.text
    assert len(dispatched) == before
