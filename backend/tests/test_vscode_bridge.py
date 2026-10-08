"""Offline native-model API route checks; no paid model or real personal source."""
import json
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from frag_api.main import create_app
from frag_api.host import checked_paths
from frag_api.providers.vscode import ModelBridge
from frag_api.providers.llm import FakeLlmProvider
from frag_api.schemas.rag import RagEvidence, RagContextCompression
from frag_api.schemas.research import ResearchDecision
from frag_api.services.context_source_service import ContextSourceService, ContextSourceError
from test_agent_host import rpc, initialize, view, prepare, recover, execute_body
from test_runtime_recovery import selection


@pytest.fixture
def bridge(monkeypatch):
    model = {"id": "synthetic-model", "name": "Synthetic", "vendor": "customendpoint",
             "revision": "a" * 64, "effort": "high", "maxInputTokens": 8192}
    calls = []

    def request(self, path, payload=None, timeout=3):
        if path == "/models":
            return [dict(model)]
        assert payload["revision"] == model["revision"]
        calls.append(payload)
        body = payload["body"]
        data = json.loads(body["messages"][1]["content"])
        fake = FakeLlmProvider()
        if "manifest" in data:
            observed = [row["evidenceId"] for item in data["observations"] if item.get("result")
                        for row in item["result"]["evidence"]]
            source = data["manifest"][0]
            output = ResearchDecision(action="finish" if observed else "continue", evidenceIds=observed,
                missingInformation=[], toolCalls=[] if observed else [{"callId": "synthetic-read", "name": "kb.read",
                    "arguments": {"identity": source["identity"], "revision": source["revision"],
                                  "locatorIds": source["locatorIds"], "evidenceIds": source["evidenceIds"]}}])
        elif "evidence" in data:
            output = fake.generate_rag_context([RagEvidence.model_validate(row) for row in data["evidence"]], 1500).output
        else:
            output = fake.generate_rag_answer(RagContextCompression.model_validate(data["context"]), data["query"], 2000).output
        return {"text": output.model_dump_json(by_alias=True)}

    monkeypatch.setattr(ModelBridge, "request", request)
    return ModelBridge("http://127.0.0.1:59001", "synthetic-secret-" + "z" * 32), model, calls


def native(client, root):
    uri = "frag:/" + str(uuid4())
    with client.websocket_connect("ws://127.0.0.1:8787/api/agents/ahp") as socket:
        initialize(socket)
        assert "error" not in rpc(socket, "createSession", {"channel": uri, "provider": "frag",
            "workingDirectories": [root.as_uri()], "model": {"id": "synthetic-model"}})
        from frag_api.services.agent_host import chat_uri
        channel = chat_uri(uri)
        rpc(socket, "subscribe", {"channel": channel})
        socket.send_json({"jsonrpc": "2.0", "method": "dispatchAction", "params": {"channel": channel, "clientSeq": 1,
            "action": {"type": "chat/turnStarted", "turnId": "synthetic-turn", "message": {
                "text": "Explain the synthetic finding", "model": {"id": "synthetic-model"}, "origin": {"kind": "user"}}}}})
        assert socket.receive_json()["params"]["action"]["type"] == "chat/turnStarted"
    return uri[6:].replace("-", "")


def client_for(tmp_path, root, bridge):
    app = create_app(context_source_root=root, workspace_root=root, model_bridge=bridge,
        runtime_path=tmp_path / "state/runtime.sqlite3", rag_index_path=tmp_path / "state/rag.sqlite3",
        plugin_root=tmp_path / "state/plugins", agent_host_enabled=True)
    return TestClient(app, base_url="http://127.0.0.1:8787", client=("127.0.0.1", 59002), raise_server_exceptions=False)


@pytest.mark.parametrize("research", [False, True])
def test_native_selected_model_every_stage_and_separate_approval(tmp_path, source_root, bridge, research):
    transport, _, calls = bridge
    with client_for(tmp_path, source_root, transport) as client:
        sid = native(client, source_root)
        assert calls == []  # Send never dispatches.
        current = prepare(client, sid, {"goal": "Explain the synthetic finding", **selection(client)}, research=research)
        for number in range(4 if research else 2):
            call = current["preview"]["preview"]["preparedCall"]
            assert call["transport"] == "vscode-lm-v1"
            assert json.loads(call["binding"])["configuredEffort"] == "high"
            assert current["config"]["context"]["provider"] == "vscode"
            assert len(calls) == number
            body = execute_body(current)
            response = client.post(f"/api/agents/sessions/{sid}/execute", json=body)
            assert response.status_code == 200, response.text
            assert client.post(f"/api/agents/sessions/{sid}/execute", json=body).status_code == 409
            current = response.json()
            if number < (3 if research else 1):
                response = recover(client, sid)
                assert response.status_code == 200, response.text
                current = response.json()
        assert current["report"]["modelOutput"]
        assert current["report"]["semanticReview"] == "NOT_RUN"
        assert all(row["modelId"] == "synthetic-model" for row in calls)
        assert transport.key not in json.dumps(current)
        from test_captured_evaluation import evaluate, gold_for
        gold = gold_for(current["report"])
        gold.update(facts=[{"id": "finding", "kind": "constraint", "alternatives": ["A synthetic finding is supported"], "forbidden": []}],
                    requiredMissingInformation=[])
        scored = evaluate(tmp_path, current["report"], gold)
        assert scored.status == "PASS", scored.model_dump_json(indent=2)


def test_changed_model_configuration_rejects_old_approval(tmp_path, source_root, bridge):
    transport, model, calls = bridge
    with client_for(tmp_path, source_root, transport) as client:
        sid = native(client, source_root)
        current = prepare(client, sid, {"goal": "Explain the synthetic finding", **selection(client)})
        model["revision"] = "b" * 64
        assert client.post(f"/api/agents/sessions/{sid}/execute", json=execute_body(current)).status_code == 409
        assert calls == []


def test_installed_host_blocks_generic_dispatch_and_cross_origin(tmp_path, source_root, bridge):
    with client_for(tmp_path, source_root, bridge[0]) as client:
        assert client.post("/api/harness/run", json={}).status_code == 409
        assert client.post("/api/runtime/research/preview", json={}).status_code == 409
        assert client.get("/api/context-sources/files", headers={"Origin": "https://example.invalid"}).status_code == 403
        assert client.get("/api/health", headers={"Host": "example.invalid"}).status_code == 403


def test_directory_separation_and_project_private_file_exclusion(tmp_path, source_root):
    install = tmp_path / "program"; install.mkdir()
    assert checked_paths(source_root, tmp_path / "state", install)[0] == source_root
    with pytest.raises(ValueError):
        checked_paths(source_root, source_root / "state", install)
    (source_root / ".private").mkdir(); (source_root / ".private/note.md").write_text("Private")
    (source_root / "AGENTS.md").write_text("Private rules")
    sources = ContextSourceService(source_root, project_files=True)
    assert [row.relative_path for row in sources.list_files()] == ["evidence.md"]
    with pytest.raises(ContextSourceError):
        sources.inspect(".private/note.md")
