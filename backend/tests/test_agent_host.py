"""Native Send, review approvals and durable replay with synthetic providers only."""
import asyncio
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from frag_api.errors import RagOutcomeUnknownError
from frag_api.services.agent_host import ROOT, WORKSPACE, chat_uri
from test_runtime_recovery import CountingProvider, app_for, selection


def client_for(app):
    app.state.agent_host_enabled = True
    return TestClient(app, base_url="http://127.0.0.1:8787", client=("127.0.0.1", 50000), raise_server_exceptions=False)


def rpc(socket, method, params, number=1):
    socket.send_json({"jsonrpc": "2.0", "id": number, "method": method, "params": params})
    for _ in range(100):
        response = socket.receive_json()
        if response.get("id") == number:
            return response
    raise AssertionError("RPC response did not arrive")


def initialize(socket):
    return rpc(socket, "initialize", {"channel": ROOT, "clientId": "synthetic-client",
        "protocolVersions": ["0.9.0"], "initialSubscriptions": [ROOT]})


def native_task(client, text="Explain the synthetic finding", uri=None):
    uri = uri or "frag:/" + str(uuid4())
    with client.websocket_connect("ws://127.0.0.1:8787/api/agents/ahp") as socket:
        assert initialize(socket)["result"]["protocolVersion"] == "0.9.0"
        assert "error" not in rpc(socket, "createSession", {"channel": uri, "provider": "frag", "workingDirectories": [WORKSPACE]})
        channel = chat_uri(uri)
        assert "error" not in rpc(socket, "subscribe", {"channel": channel})
        socket.send_json({"jsonrpc": "2.0", "method": "dispatchAction", "params": {"channel": channel, "clientSeq": 1,
            "action": {"type": "chat/turnStarted", "turnId": "synthetic-turn", "message": {"text": text, "origin": {"kind": "user"}}}}})
        assert socket.receive_json()["params"]["action"]["type"] == "chat/turnStarted"
    return uri[6:].replace("-", ""), uri


def view(client, sid):
    response = client.get(f"/api/agents/sessions/{sid}")
    assert response.status_code == 200, response.text
    return response.json()


def prepare(client, sid, source, **kwargs):
    current = view(client, sid)
    turn = current["session"]["turns"][-1]
    source = {**source, "sessionId": sid, "parentRunId": turn["runId"]}
    response = client.post(f"/api/agents/sessions/{sid}/prepare", json={"version": current["session"]["version"],
        "turnId": turn["id"], "kind": "harness", "sourceRequest": source, **kwargs})
    assert response.status_code == 200, response.text
    return response.json()


def execute_body(current):
    value = current["preview"]["preview"]
    return {"version": current["session"]["version"], "turnId": current["session"]["turns"][-1]["id"],
        "runId": current["report"]["run"]["id"], "runVersion": current["report"]["run"]["version"],
        "fingerprint": value.get("fingerprint") or value.get("inferenceFingerprint") or value.get("contextFingerprint"),
        "approvalToken": value["approvalToken"], "approved": True}


def recover(client, sid):
    current = view(client, sid)
    return client.post(f"/api/agents/sessions/{sid}/recover", json={"version": current["session"]["version"],
        "turnId": current["session"]["turns"][-1]["id"]})


def test_native_send_is_durable_without_source_access_or_model_approval(tmp_path, source_root):
    provider = CountingProvider()
    app = app_for(tmp_path, source_root, provider)
    with client_for(app) as client:
        sid, uri = native_task(client)
        saved = view(client, sid)
        assert saved["report"] is None and saved["preview"] is None and provider.calls == []
        assert client.get("/api/runtime/sessions").json()[0]["id"] == sid
        assert client.get("/api/runtime/runs").json() == []
        with client.websocket_connect("ws://127.0.0.1:8787/api/agents/ahp") as socket:
            initialize(socket)
            listed = rpc(socket, "listSessions", {"channel": ROOT})["result"]["items"]
            assert listed[0]["resource"] == uri
            snapshot = rpc(socket, "subscribe", {"channel": chat_uri(uri)})["result"]["snapshot"]["state"]
            assert snapshot["activeTurn"]["message"]["text"] == "Explain the synthetic finding"
            # Duplicate native turn ID after reconnect cannot create another task or run.
            assert "error" not in rpc(socket, "dispatchAction", {"channel": chat_uri(uri), "clientSeq": 2,
                "action": {"type": "chat/turnStarted", "turnId": "synthetic-turn",
                    "message": {"text": "Explain the synthetic finding", "origin": {"kind": "user"}}}})
        assert view(client, sid)["session"] == saved["session"] and provider.calls == []


def test_two_exact_approvals_and_native_result_are_same_runtime_run(tmp_path, source_root):
    provider = CountingProvider()
    with client_for(app_for(tmp_path, source_root, provider)) as client:
        sid, uri = native_task(client)
        prepared = prepare(client, sid, selection(client))
        assert provider.calls == [] and prepared["preview"]["stage"] == "context"
        path = f"/api/agents/sessions/{sid}/execute"
        first = execute_body(prepared)
        assert client.post(path, json={**first, "approved": False}).status_code == 422
        assert client.post(path, json={**first, "runVersion": first["runVersion"] + 1}).status_code == 409
        assert provider.calls == []
        result = client.post(path, json=first)
        assert result.status_code == 200, result.text
        assert provider.calls == ["context"] and result.json()["preview"] is None
        assert client.post(path, json=first).status_code == 409 and provider.calls == ["context"]
        second = recover(client, sid)
        assert second.status_code == 200, second.text
        assert second.json()["preview"]["stage"] == "inference" and provider.calls == ["context"]
        finished = client.post(path, json=execute_body(second.json()))
        assert finished.status_code == 200, finished.text
        report = finished.json()["report"]
        assert provider.calls == ["context", "inference"]
        assert client.get(f"/api/runtime/runs/{report['run']['id']}").json() == report
        with client.websocket_connect("ws://127.0.0.1:8787/api/agents/ahp") as socket:
            initialize(socket)
            snapshot = rpc(socket, "subscribe", {"channel": chat_uri(uri)})["result"]["snapshot"]["state"]
            parts = snapshot["activeTurn"]["responseParts"]
            assert [p["id"] for p in parts] == ["frag-synthetic-turn", "result-synthetic-turn"]
            assert report["modelOutput"]["answer"] not in parts[0]["content"]
            assert report["modelOutput"]["answer"] in parts[1]["content"]
            # Actual observer completes the native turn from the saved result.
            for _ in range(8):
                message = socket.receive_json()
                if message.get("params", {}).get("action", {}).get("type") == "chat/responsePart":
                    assert message["params"]["action"]["part"]["id"] == parts[1]["id"]
                if message.get("params", {}).get("action", {}).get("type") == "chat/turnComplete":
                    break
            else:
                pytest.fail("Saved result did not complete the native turn")


def test_prepare_invalidates_previous_controls_and_source_change_blocks_dispatch(tmp_path, source_root):
    provider = CountingProvider()
    with client_for(app_for(tmp_path, source_root, provider)) as client:
        sid, _ = native_task(client)
        source = selection(client)
        old = prepare(client, sid, source)
        new = prepare(client, sid, source)
        assert new["report"]["run"]["parentRunId"] == old["report"]["run"]["id"]
        path = f"/api/agents/sessions/{sid}/execute"
        assert client.post(path, json=execute_body(old)).status_code == 409
        (source_root / "evidence.md").write_text("# Finding\nChanged synthetic evidence", encoding="utf-8")
        assert client.post(path, json=execute_body(new)).status_code == 409
        assert provider.calls == []


def test_restart_and_unknown_outcome_never_resend(tmp_path, source_root):
    provider = CountingProvider(error=RagOutcomeUnknownError())
    with client_for(app_for(tmp_path, source_root, provider)) as client:
        sid, uri = native_task(client)
        prepared = prepare(client, sid, selection(client))
        body = execute_body(prepared)
        assert client.post(f"/api/agents/sessions/{sid}/execute", json=body).status_code == 502
        assert view(client, sid)["report"]["run"]["status"] == "outcome_unknown"
    with client_for(app_for(tmp_path, source_root, provider)) as client:
        assert view(client, sid)["preview"] is None
        assert recover(client, sid).status_code == 409
        assert client.post(f"/api/agents/sessions/{sid}/execute", json=body).status_code == 409
        with client.websocket_connect("ws://127.0.0.1:8787/api/agents/ahp") as socket:
            initialize(socket)
            assert rpc(socket, "listSessions", {"channel": ROOT})["result"]["items"][0]["resource"] == uri
        assert provider.calls == ["context"]


def test_host_is_opt_in_origin_bound_and_has_no_file_terminal_bridge(tmp_path, source_root):
    app = app_for(tmp_path, source_root, CountingProvider())
    with TestClient(app, base_url="http://127.0.0.1:8787", client=("127.0.0.1", 1)) as client:
        assert client.get("/api/agents/sessions").status_code == 404
    with client_for(app) as client:
        assert client.get("/api/agents/sessions", headers={"Host": "foreign.example"}).status_code == 404
        assert client.post("/api/agents/sessions/x/recover", json={}, headers={"Origin": "https://foreign.example"}).status_code == 403
        with pytest.raises(Exception):
            with client.websocket_connect("ws://127.0.0.1:8787/api/agents/ahp", headers={"Origin": "https://foreign.example"}):
                pass
        with client.websocket_connect("ws://127.0.0.1:8787/api/agents/ahp") as socket:
            assert rpc(socket, "initialize", {"channel": ROOT, "clientId": "x", "protocolVersions": ["0.7.0"]})["error"]["code"] == -32005
            initialize(socket)
            assert rpc(socket, "resourceRead", {"channel": ROOT, "uri": "file:///private.env"})["error"]["code"] == -32008
            assert rpc(socket, "createTerminal", {"channel": ROOT})["error"]["code"] == -32601
            assert rpc(socket, "createSession", {"channel": "frag:/" + str(uuid4()), "provider": "frag", "workingDirectories": ["file:///private"]})["error"]["code"] == -32602


def test_research_reuses_one_approval_per_turn_then_formal_stages(tmp_path, source_root):
    provider = CountingProvider()
    with client_for(app_for(tmp_path, source_root, provider)) as client:
        client.app.state.harness_service.research_provider = provider
        sid, _ = native_task(client)
        current = prepare(client, sid, selection(client), research=True)
        stages = []
        for _ in range(5):
            stage = current["preview"]["stage"]
            stages.append(stage)
            before = len(provider.calls)
            response = client.post(f"/api/agents/sessions/{sid}/execute", json=execute_body(current))
            assert response.status_code == 200, response.text
            assert len(provider.calls) == before + 1
            assert response.json()["preview"] is None
            if response.json()["report"]["modelOutput"]:
                break
            next_stage = recover(client, sid)
            assert next_stage.status_code == 200, next_stage.text
            assert len(provider.calls) == before + 1
            current = next_stage.json()
        assert stages == ["research", "research", "context", "inference"]
        assert provider.calls == stages
        assert response.json()["report"]["toolCalls"][0]["status"] == "completed"


def test_selected_rag_uses_the_same_native_review_and_runtime_binding(tmp_path, source_root):
    provider = CountingProvider()
    with client_for(app_for(tmp_path, source_root, provider)) as client:
        client.app.state.rag_service.context_provider = client.app.state.rag_service.inference_provider = provider
        sid, _ = native_task(client)
        source = selection(client)
        dataset = {"datasetId": "selected-local-v1", "sourceSelection": source["fileSelections"][0]}
        assert client.post("/api/rag/index/rebuild", json=dataset).status_code == 200
        current = view(client, sid)
        response = client.post(f"/api/agents/sessions/{sid}/prepare", json={"version": current["session"]["version"],
            "turnId": "synthetic-turn", "kind": "rag", "sourceRequest": {**dataset, "query": source["goal"], "topK": 3, "sessionId": sid}})
        assert response.status_code == 200, response.text
        assert response.json()["report"]["run"]["kind"] == "rag" and provider.calls == []
        first = client.post(f"/api/agents/sessions/{sid}/execute", json=execute_body(response.json()))
        assert first.status_code == 200, first.text
        second = recover(client, sid)
        assert second.status_code == 200, second.text
        finished = client.post(f"/api/agents/sessions/{sid}/execute", json=execute_body(second.json()))
        assert finished.status_code == 200, finished.text
        assert provider.calls == ["context", "inference"]


def test_native_stop_invalidates_approval_and_metadata_is_not_persisted(tmp_path, source_root):
    provider = CountingProvider()
    with client_for(app_for(tmp_path, source_root, provider)) as client:
        sid, uri = native_task(client)
        prepared = prepare(client, sid, selection(client))
        with client.websocket_connect("ws://127.0.0.1:8787/api/agents/ahp") as socket:
            initialize(socket)
            rpc(socket, "subscribe", {"channel": uri})
            response = rpc(socket, "dispatchAction", {"channel": uri, "clientSeq": 2,
                "action": {"type": "session/activeClientSet", "activeClient": {"clientId": "synthetic-client",
                    "tools": [{"name": "UNTRUSTED_TOOL_METADATA"}], "customizations": [{"uri": "file:///UNTRUSTED_CUSTOMIZATION"}]}}})
            assert "error" not in response
            assert "error" not in rpc(socket, "dispatchAction", {"channel": chat_uri(uri), "clientSeq": 3,
                "action": {"type": "chat/turnCancelled", "turnId": "synthetic-turn"}})
        assert view(client, sid)["report"]["run"]["status"] == "paused"
        assert client.post(f"/api/agents/sessions/{sid}/execute", json=execute_body(prepared)).status_code == 409
        raw = client.app.state.runtime.repository.path.read_bytes()
        assert b"UNTRUSTED_TOOL_METADATA" not in raw and b"UNTRUSTED_CUSTOMIZATION" not in raw
        assert provider.calls == []


def test_malformed_carrier_input_is_rejected_without_disconnect_or_execution(tmp_path, source_root):
    provider = CountingProvider()
    app = app_for(tmp_path, source_root, provider)
    with client_for(app) as client:
        with client.websocket_connect("ws://127.0.0.1:8787/api/agents/ahp") as socket:
            initialize(socket)
            for method, params in [
                ("subscribe", {"channel": 7}),
                ("createSession", {"provider": "frag", "workingDirectories": [WORKSPACE], "model": None}),
                ("dispatchAction", {"channel": ROOT, "clientSeq": 1, "action": None}),
                ("resourceResolve", {"channel": ROOT, "uri": []}),
            ]:
                assert rpc(socket, method, params)["error"]["code"] == -32602
                assert rpc(socket, "ping", {"channel": ROOT})["result"] == {}
            assert rpc(socket, "createTerminal", {"channel": "ahp-terminal://unsupported"})["error"]["code"] == -32601
        assert provider.calls == []
        assert client.get("/api/runtime/runs").json() == []


def test_native_reconnect_and_restart_handshakes_restore_without_dispatch(tmp_path, source_root):
    provider = CountingProvider()
    with client_for(app_for(tmp_path, source_root, provider)) as client:
        sid, uri = native_task(client)
        prepared = prepare(client, sid, selection(client))
        resources = [ROOT, uri, chat_uri(uri)]
        with client.websocket_connect("ws://127.0.0.1:8787/api/agents/ahp") as socket:
            restored = rpc(socket, "reconnect", {"clientId": "synthetic-client",
                "lastSeenServerSeq": 1, "subscriptions": resources})["result"]
            assert restored["type"] == "snapshot"
            assert {s["resource"] for s in restored["snapshots"]} == set(resources)
            assert rpc(socket, "ping", {"channel": ROOT})["result"] == {}
        assert view(client, sid)["report"]["run"]["id"] == prepared["report"]["run"]["id"]
        assert provider.calls == []
    with client_for(app_for(tmp_path, source_root, provider)) as client:
        with client.websocket_connect("ws://127.0.0.1:8787/api/agents/ahp") as socket:
            assert rpc(socket, "reconnect", {"clientId": "synthetic-client",
                "lastSeenServerSeq": 100, "subscriptions": resources})["error"]["code"] == -32008
            restored = rpc(socket, "initialize", {"channel": ROOT, "clientId": "synthetic-client",
                "protocolVersions": ["0.9.0"], "initialSubscriptions": resources})["result"]
            assert {s["resource"] for s in restored["snapshots"]} == set(resources)
            assert restored["snapshots"][-1]["state"]["activeTurn"]["id"] == "synthetic-turn"
        assert view(client, sid)["preview"] is None
        assert client.post(f"/api/agents/sessions/{sid}/execute", json=execute_body(prepared)).status_code == 409
        assert provider.calls == []
