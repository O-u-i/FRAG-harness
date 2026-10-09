"""Composer edits, completed native receipts and cancelled Review task replacement."""
from uuid import uuid4
import pytest
from frag_api.services.agent_host import ROOT, WORKSPACE, chat_uri
from test_agent_host import client_for, initialize, rpc, view, native_task, prepare, execute_body, recover
from test_runtime_recovery import CountingProvider, app_for, selection


def send(socket, channel, turn_id, message, seq=1):
    return rpc(socket, "dispatchAction", {"channel": channel, "clientSeq": seq,
        "action": {"type": "chat/turnStarted", "turnId": turn_id, "message": message}})


def task(text="Explain the synthetic finding", **kwargs):
    return {"text": text, "origin": {"kind": "user"}, **kwargs}


def test_composer_edits_echo_exactly_and_reconnect_without_disk_or_source_reads(tmp_path, source_root, monkeypatch):
    provider = CountingProvider()
    app = app_for(tmp_path, source_root, provider)
    # Native attachment URIs must never be resolved or inspected as evidence.
    with client_for(app) as client:
        monkeypatch.setattr(app.state.context_source_service, "inspect", lambda *args: pytest.fail("Native attachment read"))
        sid, uri = native_task(client)
        saved = view(client, sid)["session"]
        channel = chat_uri(uri)
        with client.websocket_connect("ws://127.0.0.1:8787/api/agents/ahp") as socket:
            initialize(socket)
            rpc(socket, "subscribe", {"channel": channel})
            edits = [task("UNSENT_DRAFT"), task("UNSENT_DRAFT continued"),
                task("UNSENT_DRAFT pasted\ntext"), task("UNSENT_DRAFT pasted\ntext", attachments=[{
                    "type": "file", "uri": "file:///UNREAD_ATTACHMENT.md", "label": "UNREAD_ATTACHMENT"}]),
                task("UNSENT_DRAFT pasted\ntext", attachments=[])]
            for seq, draft in enumerate(edits, 1):
                action = {"type": "chat/draftChanged", "draft": draft}
                socket.send_json({"jsonrpc": "2.0", "method": "dispatchAction", "params": {
                    "channel": channel, "clientSeq": seq, "action": action}})
                event = socket.receive_json()["params"]
                assert event["action"] == action
                assert event["origin"] == {"clientId": "synthetic-client", "clientSeq": seq}
            assert view(client, sid)["session"] == saved
            assert "error" not in rpc(socket, "ping", {"channel": ROOT})
        with client.websocket_connect("ws://127.0.0.1:8787/api/agents/ahp") as socket:
            restored = rpc(socket, "reconnect", {"clientId": "synthetic-client",
                "lastSeenServerSeq": 1, "subscriptions": [channel]})["result"]["snapshots"][0]["state"]
            assert restored["draft"] == edits[-1] and "activeTurn" not in restored
            assert "error" not in send(socket, channel, "next-task", task(), seq=6)
            assert "draft" not in rpc(socket, "subscribe", {"channel": channel})["result"]["snapshot"]["state"]
            # Clear is explicit, including the AHP omitted-field form.
            for action in [{"type": "chat/draftChanged", "draft": task("UNSENT_CLEAR")},
                           {"type": "chat/draftChanged"}]:
                assert "error" not in rpc(socket, "dispatchAction", {"channel": channel, "clientSeq": 7, "action": action})
            assert "draft" not in rpc(socket, "subscribe", {"channel": channel})["result"]["snapshot"]["state"]
        assert saved["turns"][0]["state"] == "running" and provider.calls == []
        raw = app.state.runtime.repository.path.read_bytes()
        assert b"UNSENT_" not in raw and b"UNREAD_ATTACHMENT" not in raw
        assert client.get("/api/runtime/runs").json() == []


def test_native_receipt_ends_before_review_and_cancelled_task_can_restart(tmp_path, source_root):
    provider = CountingProvider()
    with client_for(app_for(tmp_path, source_root, provider)) as client:
        uri = "frag:/" + str(uuid4())
        sid, channel = uri[6:].replace("-", ""), chat_uri(uri)
        with client.websocket_connect("ws://127.0.0.1:8787/api/agents/ahp") as socket:
            initialize(socket)
            rpc(socket, "createSession", {"channel": uri, "provider": "frag", "workingDirectories": [WORKSPACE]})
            rpc(socket, "subscribe", {"channel": channel})
            socket.send_json({"jsonrpc": "2.0", "method": "dispatchAction", "params": {"channel": channel,
                "clientSeq": 1, "action": {"type": "chat/turnStarted", "turnId": "original", "message": task()}}})
            actions = [socket.receive_json()["params"]["action"] for _ in range(4)]
            assert [a["type"] for a in actions] == ["chat/turnStarted", "chat/responsePart", "chat/turnComplete", "chat/activityChanged"]
            assert "Waiting for task configuration" in actions[1]["part"]["content"]
            assert "activity" not in actions[-1] and provider.calls == []
            prepared = prepare(client, sid, selection(client))
            check = {"version": prepared["session"]["version"], "turnId": "original"}
            assert client.post(f"/api/agents/sessions/{sid}/cancel", json={**check, "version": 1}).status_code == 409
            cancelled = client.post(f"/api/agents/sessions/{sid}/cancel", json=check)
            assert cancelled.status_code == 200 and cancelled.json()["preview"] is None
            assert cancelled.json()["session"]["turns"][-1]["state"] == "cancelled"
            old_preview = prepared["preview"]["preview"]
            assert not client.app.state.harness_service.approvals.consume(old_preview["approvalToken"], old_preview["contextFingerprint"])
            assert recover(client, sid).status_code == 409
            assert "error" not in send(socket, channel, "replacement", task(), seq=2)
            current = view(client, sid)
            assert [t["state"] for t in current["session"]["turns"]] == ["cancelled", "running"]
            assert current["report"] is None and current["preview"] is None
            old = execute_body(prepared)
            path = f"/api/agents/sessions/{sid}/execute"
            assert client.post(path, json=old).status_code == 409
            assert provider.calls == []
            fresh = prepare(client, sid, selection(client))
            body = execute_body(fresh)
            assert client.post(path, json=body).status_code == 200
            assert client.post(path, json=body).status_code == 409
            assert provider.calls == ["context"]
            snapshot = rpc(socket, "subscribe", {"channel": channel})["result"]["snapshot"]["state"]
            assert "activeTurn" not in snapshot and snapshot["turns"][-1]["id"] == "replacement"
            assert snapshot["turns"][0]["state"] == "cancelled"


def test_new_task_supersedes_waiting_task_and_revokes_old_approval(tmp_path, source_root):
    provider = CountingProvider()
    with client_for(app_for(tmp_path, source_root, provider)) as client:
        sid, uri = native_task(client)
        prepared = prepare(client, sid, selection(client))
        with client.websocket_connect("ws://127.0.0.1:8787/api/agents/ahp") as socket:
            initialize(socket)
            assert "error" not in send(socket, chat_uri(uri), "replacement", task())
        current = view(client, sid)
        assert current["session"]["turns"][0]["state"] == "cancelled"
        assert client.post(f"/api/agents/sessions/{sid}/execute", json=execute_body(prepared)).status_code == 409
        assert current["report"] is None and provider.calls == []


@pytest.mark.parametrize("research,next_stage", [(False, True), (True, False), (True, True)])
def test_cancel_revokes_each_stage_registry(tmp_path, source_root, research, next_stage):
    provider = CountingProvider()
    with client_for(app_for(tmp_path, source_root, provider)) as client:
        client.app.state.harness_service.research_provider = provider
        sid, _ = native_task(client)
        current = prepare(client, sid, selection(client), research=research)
        if next_stage:
            while current["preview"]["stage"] != ("context" if research else "inference"):
                response = client.post(f"/api/agents/sessions/{sid}/execute", json=execute_body(current))
                assert response.status_code == 200
                current = recover(client, sid).json()
        previous_calls = list(provider.calls)
        response = client.post(f"/api/agents/sessions/{sid}/cancel", json={
            "version": current["session"]["version"], "turnId": current["session"]["turns"][-1]["id"]})
        assert response.status_code == 200
        value = current["preview"]["preview"]
        registry = client.app.state.research.approvals if research else client.app.state.harness_service.pending_inference
        fingerprint = value.get("fingerprint") or value.get("inferenceFingerprint") or value.get("contextFingerprint")
        assert not registry.consume(value["approvalToken"], fingerprint)
        assert client.post(f"/api/agents/sessions/{sid}/execute", json=execute_body(current)).status_code == 409
        assert provider.calls == previous_calls


@pytest.mark.parametrize("message,turn_id,expected", [
    (task("ab"), "new", "3–500"), (task("a" * 501), "new", "3–500"),
    (task(attachments=[{"uri": "file:///UNREAD.md"}]), "new", "Context attachments"),
    ({"text": "A legal task", "origin": "user"}, "new", "message format"),
    (task(attachments={}), "new", "message format"), (task(), "", "message format"),
    (task("Different saved task"), "synthetic-turn", "turn ID already"),
])
def test_send_errors_identify_condition_without_length_catchall(tmp_path, source_root, message, turn_id, expected):
    provider = CountingProvider()
    with client_for(app_for(tmp_path, source_root, provider)) as client:
        sid, uri = native_task(client)
        saved = view(client, sid)["session"]
        with client.websocket_connect("ws://127.0.0.1:8787/api/agents/ahp") as socket:
            initialize(socket)
            response = send(socket, chat_uri(uri), turn_id, message)
            assert expected in response["error"]["message"]
            if expected != "3–500":
                assert "3–500" not in response["error"]["message"]
            assert rpc(socket, "ping", {"channel": ROOT})["result"] == {}
        assert view(client, sid)["session"] == saved and provider.calls == []


def test_notification_send_error_has_native_error_type_and_allows_text_retry(tmp_path, source_root, monkeypatch):
    provider = CountingProvider()
    with client_for(app_for(tmp_path, source_root, provider)) as client:
        sid, uri = native_task(client)
        saved = view(client, sid)["session"]
        monkeypatch.setattr(client.app.state.context_source_service, "inspect", lambda *args: pytest.fail("Attachment read"))
        with client.websocket_connect("ws://127.0.0.1:8787/api/agents/ahp") as socket:
            initialize(socket)
            channel = chat_uri(uri)
            rpc(socket, "subscribe", {"channel": channel})
            socket.send_json({"jsonrpc": "2.0", "method": "dispatchAction", "params": {"channel": channel,
                "clientSeq": 1, "action": {"type": "chat/turnStarted", "turnId": "rejected",
                    "message": task(attachments=[{"type": "resource", "uri": "file:///UNREAD.md"}])}}})
            event = socket.receive_json()["params"]["action"]
            assert event["type"] == "chat/error" and event["turnId"] == "rejected"
            assert event["part"]["error"]["errorType"] == "invalidRequest"
            assert "Context attachments" in event["part"]["error"]["message"]
            assert event["part"]["resumable"] is False
            assert view(client, sid)["session"] == saved
            assert "error" not in send(socket, channel, "retry", task(attachments=[]), seq=2)
        assert view(client, sid)["session"]["turns"][-1]["id"] == "retry"
        assert client.get("/api/runtime/runs").json() == [] and provider.calls == []
