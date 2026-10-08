"""Layered settings resolve fresh requests, not standing approvals or source grants."""
import copy
import pytest
from test_agent_host import client_for, native_task, view, execute_body, recover
from test_runtime_recovery import app_for, selection, CountingProvider
from test_agent_host import initialize, rpc
from frag_api.services.agent_host import chat_uri


def settings(client, sid=None):
    response = client.get(f"/api/agents/sessions/{sid}/settings" if sid else "/api/agents/settings")
    assert response.status_code == 200, response.text
    return response.json()


def source_settings(client):
    return {"mode":"files", "file":selection(client)["fileSelections"][0], "plugin":None, "synthetic":False}


def configure(client):
    value = source_settings(client)
    response = client.put("/api/agents/settings/project",json={"revision":0,"settings":value})
    assert response.status_code == 200, response.text
    return value


def prepare_settings(client, sid, **changes):
    saved, current = settings(client,sid), view(client,sid)
    body = {"version":current["session"]["version"],"turnId":current["session"]["turns"][-1]["id"],
            **{name+"Revision":saved[name]["revision"] for name in ("application","project","conversation")}}
    response = client.post(f"/api/agents/sessions/{sid}/prepare-settings",json={**body,**changes})
    return response


def test_save_is_zero_model_and_frozen_request_survives_default_changes(tmp_path,source_root):
    provider = CountingProvider()
    with client_for(app_for(tmp_path,source_root,provider)) as client:
        sid,_ = native_task(client)
        assert prepare_settings(client,sid).status_code == 422
        configure(client)
        response = prepare_settings(client,sid)
        assert response.status_code == 200, response.text
        prepared = response.json()
        assert prepared["preview"]["stage"] == "context" and provider.calls == []
        assert prepared["report"]["configuration"]["origin"] == "defaults"
        frozen = copy.deepcopy(prepared["preview"])
        app = settings(client)["application"]
        app["settings"]["topK"] = 10
        assert client.put("/api/agents/settings/application",json=app).status_code == 200
        assert view(client,sid)["preview"] == frozen and provider.calls == []
        result = client.post(f"/api/agents/sessions/{sid}/execute",json=execute_body(prepared))
        assert result.status_code == 200, result.text
        assert provider.calls == ["context"]
        assert recover(client,sid).status_code == 200


def test_cas_and_strict_source_validation(tmp_path,source_root):
    with client_for(app_for(tmp_path,source_root,CountingProvider())) as client:
        sid,_ = native_task(client)
        source = configure(client)
        assert client.put("/api/agents/settings/project",json={"revision":0,"settings":source}).status_code == 409
        for invalid in ({**source,"path":"outside"}, {**source,"file":{**source["file"],"relativePath":"../private.md"}},
                        {**source,"synthetic":True}, {**source,"file":{**source["file"],"locatorIds":["a","a"]}}):
            assert client.put("/api/agents/settings/project",json={"revision":1,"settings":invalid}).status_code == 422
        assert prepare_settings(client,sid,projectRevision=0).status_code == 409
        assert client.get("/api/agents/settings?path=anything").status_code == 422
        assert client.put("/api/agents/settings/project",json={"revision":1,"settings":source},headers={"Origin":"https://outside.invalid"}).status_code == 403


def test_conversation_override_persists_without_history_or_approval(tmp_path,source_root):
    provider = CountingProvider()
    with client_for(app_for(tmp_path,source_root,provider)) as client:
        sid,_ = native_task(client)
        source = configure(client)
        current = view(client,sid)
        config = {"evidence":source,"topK":5,"research":False,"checklist":[]}
        body = {"version":current["session"]["version"],"turnId":"synthetic-turn","revision":0,"settings":config}
        assert client.put(f"/api/agents/sessions/{sid}/settings",json=body).status_code == 200
        assert client.put(f"/api/agents/sessions/{sid}/settings",json=body).status_code == 409
        result = prepare_settings(client,sid)
        assert result.status_code == 200, result.text
        prepared = result.json()
        assert prepared["report"]["configuration"]["origin"] == "conversation"
        assert prepared["report"]["selection"]["input"]["goal"] == "Explain the synthetic finding"
        assert provider.calls == [] and prepared["preview"]["preview"]["approvalToken"]
        run = prepare_settings(client,sid,override={**config,"topK":1})
        assert run.status_code == 200 and run.json()["report"]["configuration"]["origin"] == "run"
        assert settings(client,sid)["conversation"]["settings"]["topK"] == 5


def test_blocking_template_is_reset_for_every_preparation(tmp_path,source_root):
    provider = CountingProvider()
    with client_for(app_for(tmp_path,source_root,provider)) as client:
        sid,_ = native_task(client)
        configure(client)
        app = settings(client)["application"]
        app["settings"]["checklist"] = [{"id":"scope","text":"Review selected scope","blocking":True}]
        assert client.put("/api/agents/settings/application",json=app).status_code == 200
        result = prepare_settings(client,sid)
        assert result.status_code == 200, result.text
        value = result.json()
        assert value["report"]["selection"]["task"]["checklist"][0]["reviewed"] is False
        assert value["preview"]["preview"]["canApprove"] is False and provider.calls == []


def test_application_preferences_are_shared_project_evidence_is_not(tmp_path):
    from frag_api.repositories.review_settings import ReviewSettingsRepository
    from frag_api.errors import RuntimeConflictError
    shared = tmp_path / "application.sqlite3"
    a,b = ReviewSettingsRepository(shared),ReviewSettingsRepository(shared)
    assert a.put("application",0,{"topK":5})["revision"] == 1
    assert b.get("application",{})["settings"] == {"topK":5}
    with pytest.raises(RuntimeConflictError): b.put("application",0,{"topK":3})
    p1,p2 = ReviewSettingsRepository(tmp_path / "p1.sqlite3"),ReviewSettingsRepository(tmp_path / "p2.sqlite3")
    p1.put("project",0,{"file":"one"})
    assert p2.get("project",None)["settings"] is None


def test_next_conversation_task_rereads_sources_and_binds_a_fresh_request(tmp_path,source_root):
    provider = CountingProvider()
    with client_for(app_for(tmp_path,source_root,provider)) as client:
        sid,uri = native_task(client)
        source = configure(client)
        current = view(client,sid)
        config = {"evidence":source,"topK":3,"research":False,"checklist":[]}
        assert client.put(f"/api/agents/sessions/{sid}/settings",json={"version":current["session"]["version"],
            "turnId":"synthetic-turn","revision":0,"settings":config}).status_code == 200
        first = prepare_settings(client,sid).json()
        source_root.joinpath("evidence.md").write_text("# Finding\nA changed synthetic finding.\n# Limits\nEvidence is incomplete.",encoding="utf-8")
        assert client.post(f"/api/agents/sessions/{sid}/execute",json=execute_body(first)).status_code == 409
        with client.websocket_connect("ws://127.0.0.1:8787/api/agents/ahp") as socket:
            initialize(socket)
            rpc(socket,"subscribe",{"channel":chat_uri(uri)})
            response = rpc(socket,"dispatchAction",{"channel":chat_uri(uri),"clientSeq":2,
                "action":{"type":"chat/turnStarted","turnId":"next-turn","message":{"text":"Explain the changed synthetic finding","origin":{"kind":"user"}}}})
            assert "error" not in response
        second = prepare_settings(client,sid)
        assert second.status_code == 200, second.text
        updated = second.json()
        assert updated["preview"]["stage"] == "context" and provider.calls == []
        assert updated["report"]["selection"]["goal"] == "Explain the changed synthetic finding"
        assert updated["report"]["selection"]["sourceBindings"][0]["revision"] != first["report"]["selection"]["sourceBindings"][0]["revision"]
        assert updated["report"]["requests"][0]["preparedCall"]["fingerprint"] != first["report"]["requests"][0]["preparedCall"]["fingerprint"]
        assert updated["report"]["research"] is None and updated["report"]["context"] is None


def test_research_zero_hits_cannot_gain_approval_by_recovering(tmp_path,source_root):
    provider = CountingProvider()
    with client_for(app_for(tmp_path,source_root,provider)) as client:
        sid,_ = native_task(client,"zqxnonexistenttokenonly")
        client.app.state.rag_service.research_provider = provider
        assert client.post("/api/rag/index/rebuild",json={"datasetId":"synthetic-risk-review-v1"}).status_code == 200
        config = {"evidence":{"mode":"retrieval","file":None,"plugin":None,"synthetic":True},"topK":3,"research":True,"checklist":[]}
        result = prepare_settings(client,sid,override=config)
        assert result.status_code == 200, result.text
        value = result.json()
        assert value["preview"]["stage"] == "research" and not value["preview"]["preview"]["canApprove"]
        assert value["preview"]["preview"]["approvalToken"] is None
        assert any("No" in warning or "no" in warning for warning in value["preview"]["preview"]["warnings"])
        for _ in range(2): assert recover(client,sid).status_code == 409
        assert provider.calls == []
