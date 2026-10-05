"""Actual KB archive and generic host stages; all sources/providers are synthetic."""
import hashlib
import json
import os
from pathlib import Path

from fastapi.testclient import TestClient
import httpx
import pytest

from frag_api.main import create_app
from frag_api.providers.llm import FakeLlmProvider
from frag_api.services.plugin_management import install_archive

ROOT = Path(__file__).resolve().parents[2]


class CapturingFake(FakeLlmProvider):
    def __init__(self):
        self.calls = []

    def execute_prepared(self, call):
        self.calls.append(call)
        return super().execute_prepared(call)


@pytest.fixture
def kb_client(tmp_path, source_root, monkeypatch):
    monkeypatch.setenv("FRAG_KB_SOURCE_ROOT", str(source_root))
    package = (ROOT / "docs/release/kb-frag-plugin-v1.0.0.zip").read_bytes()
    install_archive(tmp_path / "plugins", package, hashlib.sha256(package).hexdigest())
    app = create_app(plugin_root=tmp_path / "plugins", context_source_root=source_root,
                     rag_index_path=tmp_path / "rag.sqlite3")
    with TestClient(app) as client:
        provider = CapturingFake()
        app.state.harness_service.context_provider = provider
        app.state.harness_service.inference_provider = provider
        yield client, provider, source_root


def selection(client):
    response = client.get("/api/plugins/kb/evidence-scopes", params={"scopeId": "evidence.md"})
    assert response.status_code == 200, response.text
    locator = response.json()["scopes"][0]["records"][0]["id"]
    return {"goal": "Explain the selected synthetic finding", "fileSelections": [],
            "pluginSelection": {"pluginId": "kb", "scopeId": "evidence.md", "recordIds": [locator]}}


def context(client, request, preview):
    return client.post("/api/harness/run", json={**request, "approved": True,
        "contextFingerprint": preview["contextFingerprint"], "approvalToken": preview["approvalToken"]})


def inference(client, preview, first):
    return client.post("/api/harness/inference/run", json={"approved": True,
        "contextFingerprint": preview["contextFingerprint"],
        "inferenceFingerprint": first["inferencePreview"]["inferenceFingerprint"],
        "approvalToken": first["inferencePreview"]["approvalToken"]})


def test_real_kb_archive_scopes_and_exact_two_stage_calls(kb_client):
    client, provider, _ = kb_client
    catalog = client.get("/api/plugins").json()
    assert catalog["protocolVersion"] == 2
    assert next(item for item in catalog["plugins"] if item["id"] == "kb")["installed"]
    assert client.get("/plugins/kb/ui.js").status_code == 200
    scopes = client.get("/api/plugins/kb/evidence-scopes").json()["scopes"]
    assert scopes[0]["records"] == []  # Listing files does not parse unselected documents.
    request = selection(client)
    response = client.post("/api/harness/preview", json=request)
    assert response.status_code == 200, response.text
    preview = response.json()
    assert not provider.calls
    binding = preview["sourceBindings"][0]
    assert binding["identity"]["kind"] == "plugin_record"
    assert binding["identity"]["namespace"].startswith("kb/")
    first = context(client, request, preview)
    assert first.status_code == 200, first.text
    second = inference(client, preview, first.json())
    assert second.status_code == 200, second.text
    assert len(provider.calls) == 2
    assert provider.calls[0].model_dump(by_alias=True) == preview["preparedCall"]
    assert provider.calls[1].model_dump(by_alias=True) == first.json()["inferencePreview"]["preparedCall"]
    assert context(client, request, preview).status_code == 409


@pytest.mark.parametrize("stage", ["context", "inference"])
def test_package_mutation_blocks_old_approval(kb_client, stage):
    client, provider, _ = kb_client
    request = selection(client)
    preview = client.post("/api/harness/preview", json=request).json()
    first = context(client, request, preview).json() if stage == "inference" else None
    plugin = client.app.state.plugins["kb"]
    adapter = plugin.directory / "adapter.py"
    adapter.write_bytes(adapter.read_bytes() + b"\n# changed package\n")
    result = inference(client, preview, first) if first else context(client, request, preview)
    assert result.status_code in {409, 422}, result.text
    assert len(provider.calls) == (1 if first else 0)
    assert client.get("/plugins/kb/ui.js").status_code == 404


def test_source_revision_and_scope_escape_stop_dispatch(kb_client):
    client, provider, source = kb_client
    request = selection(client)
    preview = client.post("/api/harness/preview", json=request).json()
    (source / "evidence.md").write_text("# Finding\nChanged synthetic finding.", encoding="utf-8")
    assert context(client, request, preview).status_code == 409
    bad = {**request, "pluginSelection": {**request["pluginSelection"], "scopeId": "../outside.md"}}
    assert client.post("/api/harness/preview", json=bad).status_code == 422
    assert client.post("/api/runtime/research/preview", json={"kind": "harness", "sourceRequest": request}).status_code == 409
    assert not provider.calls


def test_memory_requires_same_plugin_and_source_scope(kb_client):
    client, _, source = kb_client
    request = selection(client)
    preview = client.post("/api/harness/preview", json=request).json()
    first = context(client, request, preview)
    assert inference(client, preview, first.json()).status_code == 200
    item = client.post("/api/memory/candidates", json={"runId": preview["runId"], "text": "Synthetic finding background."}).json()
    active = client.post(f"/api/memory/{item['id']}/promote", json={"version": item["version"],
        "reviewed": True, "note": "Reviewed synthetic background."})
    assert active.status_code == 200, active.text
    chosen = [{"memoryId": item["id"], "version": active.json()["version"]}]
    assert client.post("/api/harness/preview", json={**request, "selectedMemory": chosen}).status_code == 200
    (source / "other.md").write_text("# Finding\nAnother synthetic finding.", encoding="utf-8")
    other = {**request, "pluginSelection": {**request["pluginSelection"], "scopeId": "other.md"}, "selectedMemory": chosen}
    assert client.post("/api/harness/preview", json=other).status_code == 409
    local = {"goal": request["goal"], "fileSelections": [{"relativePath": "evidence.md",
        "locatorIds": request["pluginSelection"]["recordIds"], "relevanceReason": "Selected synthetic source."}], "selectedMemory": chosen}
    assert client.post("/api/harness/preview", json=local).status_code == 409


@pytest.mark.parametrize("change", ["none", "package", "configuration"])
def test_kb_context_checkpoint_recovery_requires_new_approval(tmp_path, source_root, monkeypatch, change):
    monkeypatch.setenv("FRAG_KB_SOURCE_ROOT", str(source_root))
    package = (ROOT / "docs/release/kb-frag-plugin-v1.0.0.zip").read_bytes()
    install_archive(tmp_path / "plugins", package, hashlib.sha256(package).hexdigest())
    provider = CapturingFake()

    def app():
        return create_app(plugin_root=tmp_path / "plugins", context_source_root=source_root,
                          rag_index_path=tmp_path / "rag.sqlite3", runtime_path=tmp_path / "saved.sqlite3")

    with TestClient(app()) as first:
        first.app.state.harness_service.context_provider = provider
        request = selection(first)
        preview = first.post("/api/harness/preview", json=request).json()
        completed = context(first, request, preview)
        assert completed.status_code == 200, completed.text
    if change == "configuration":
        other = tmp_path / "other-source-root"
        other.mkdir()
        (other / "evidence.md").write_bytes((source_root / "evidence.md").read_bytes())
        monkeypatch.setenv("FRAG_KB_SOURCE_ROOT", str(other))
    if change == "package":
        adapter = tmp_path / "plugins/kb/versions/1.0.0/adapter.py"
        adapter.write_bytes(adapter.read_bytes() + b"\n# changed after checkpoint\n")
    with TestClient(app()) as second:
        second.app.state.harness_service.inference_provider = provider
        assert inference(second, preview, completed.json()).status_code == 409
        restored = second.post(f"/api/runtime/runs/{preview['runId']}/resume/preview", json={"sourceRequest": request})
        if change != "none":
            assert restored.status_code in {409, 422}, restored.text
            assert len(provider.calls) == 1
        else:
            assert restored.status_code == 200, restored.text
            value = restored.json()
            assert value["stage"] == "inference"
            assert value["preview"]["approvalToken"] != completed.json()["inferencePreview"]["approvalToken"]
            resumed = inference(second, {"contextFingerprint": value["contextFingerprint"]}, {"inferencePreview": value["preview"]})
            assert resumed.status_code == 200, resumed.text
            assert [call.purpose for call in provider.calls] == ["context", "inference"]


def test_fc_owned_protocol2_archive_uses_released_reads(kb_client, monkeypatch, tmp_path):
    archive = os.environ.get("FRAG_TEST_FC_PLUGIN_ARCHIVE")
    if not archive:
        pytest.skip("Set FRAG_TEST_FC_PLUGIN_ARCHIVE to the separately verified FC-owned protocol2 artifact.")
    client, provider, _ = kb_client
    package = Path(archive).read_bytes()
    assert hashlib.sha256(package).hexdigest() == "a96d5d2c4c8e4c8a7232db4be825925d37fb80052e74f6eab450744c62ccfacb"
    install_archive(client.app.state.plugin_root, package, hashlib.sha256(package).hexdigest())
    monkeypatch.setenv("FINANCE_CORE_PLUGIN_READ_TOKEN", "synthetic-read-token")
    monkeypatch.setenv("FINANCE_CORE_PLUGIN_RECORDS_JSON", json.dumps({"synthetic-workspace": ["entry:record-1"]}))
    app = create_app(plugin_root=client.app.state.plugin_root, rag_index_path=tmp_path / "fc-rag.sqlite3",
                     runtime_path=tmp_path / "fc-runtime.sqlite3")
    with TestClient(app) as client:
        provider = CapturingFake()
        app.state.harness_service.context_provider = provider
        app.state.harness_service.inference_provider = provider
        plugin = app.state.plugins["finance-core"]
        assert client.get("/plugins/finance-core/ui.js").status_code == 200
        seen = []

        def upstream(request):
            seen.append(request.url.path)
            assert request.method == "GET"
            assert request.headers["authorization"] == "Bearer synthetic-read-token"
            if request.url.path == "/api/v3/health":
                data = {"status": "ok", "service": "finance-core", "apiVersion": "3.1.1"}
            elif request.url.path == "/api/v3/workspaces":
                data = {"data": [{"id": "synthetic-workspace", "status": "active", "displayName": "Synthetic scope"}]}
            else:
                assert request.url.path == "/api/v3/workspaces/synthetic-workspace/journal-entries/record-1"
                data = {"workspaceId": "synthetic-workspace", "data": {"id": "record-1", "date": "2026-10-05",
                    "description": "Synthetic Released record", "postings": [{"accountId": "cash", "side": "debit",
                    "units": "12.34", "commodityCode": "CNY"}]}}
            return httpx.Response(200, json=data)

        monkeypatch.setitem(plugin.read_evidence.__globals__, "_client", lambda base, token:
            httpx.Client(base_url=base, headers={"Authorization": f"Bearer {token}"}, transport=httpx.MockTransport(upstream)))
        scope = plugin.selected_scopes("synthetic-workspace")
        assert scope["scopes"][0]["records"][0]["id"] == "entry:record-1"
        request = {"goal": "Explain the synthetic Released record", "fileSelections": [],
            "pluginSelection": {"pluginId": "finance-core", "scopeId": "synthetic-workspace", "recordIds": ["entry:record-1"]}}
        response = client.post("/api/harness/preview", json=request)
        assert response.status_code == 200, response.text
        preview = response.json()
        assert preview["sourceBindings"][0]["identity"]["kind"] == "fc_record"
        assert "12.34" in preview["candidateEvidence"][0]["text"]
        first = context(client, request, preview)
        assert first.status_code == 200, first.text
        assert inference(client, preview, first.json()).status_code == 200
        assert len(provider.calls) == 2
        before = len(seen)
        wrong = {**request, "pluginSelection": {**request["pluginSelection"], "scopeId": "other-workspace"}}
        assert client.post("/api/harness/preview", json=wrong).status_code == 422
        assert len(seen) == before


def test_official_protocol_one_memory_cannot_cross_fc_origin_after_restart(tmp_path, monkeypatch):
    configured = os.environ.get("FRAG_TEST_FC_PLUGIN_ARCHIVE")
    if not configured:
        pytest.skip("Set FRAG_TEST_FC_PLUGIN_ARCHIVE beside the separately verified protocol1 artifact.")
    archive = Path(configured).with_name("finance-core-frag-plugin-v1.0.0.zip")
    package = archive.read_bytes()
    assert hashlib.sha256(package).hexdigest() == "79918f940b29dd6def5a3702bf043719eebbe0a9ece28da67f0d806a0428a6bd"
    install_archive(tmp_path / "plugins", package, hashlib.sha256(package).hexdigest())
    monkeypatch.setenv("FINANCE_CORE_PLUGIN_READ_TOKEN", "synthetic-read-token")
    monkeypatch.setenv("FINANCE_CORE_PLUGIN_RECORDS_JSON", json.dumps({"synthetic-workspace": ["entry:record-1"]}))
    monkeypatch.setenv("FINANCE_CORE_PLUGIN_API_URL", "http://127.0.0.1:9781")
    provider = CapturingFake()
    upstream_calls = []

    def upstream(request):
        upstream_calls.append((str(request.url), request.method))
        assert request.method == "GET"
        assert request.headers["authorization"] == "Bearer synthetic-read-token"
        if request.url.path == "/api/v3/health":
            data = {"status": "ok", "service": "finance-core", "apiVersion": "3.1.1"}
        elif request.url.path == "/api/v3/workspaces":
            data = {"data": [{"id": "synthetic-workspace", "status": "active", "displayName": "Synthetic scope"}]}
        else:
            assert request.url.path == "/api/v3/workspaces/synthetic-workspace/journal-entries/record-1"
            # Both mocked origins deliberately return identical Workspace, record, text and revision.
            data = {"workspaceId": "synthetic-workspace", "data": {"id": "record-1", "date": "2026-10-05",
                "description": "Identical synthetic Released record", "postings": [{"accountId": "cash", "side": "debit",
                "units": "12.34", "commodityCode": "CNY"}]}}
        return httpx.Response(200, json=data)

    def app():
        value = create_app(plugin_root=tmp_path / "plugins", rag_index_path=tmp_path / "rag.sqlite3",
                           runtime_path=tmp_path / "runtime.sqlite3")
        plugin = value.state.plugins["finance-core"]
        monkeypatch.setitem(plugin.read_evidence.__globals__, "_client", lambda base, token:
            httpx.Client(base_url=base, headers={"Authorization": f"Bearer {token}"}, transport=httpx.MockTransport(upstream)))
        return value

    request = {"goal": "Explain the synthetic Released record", "fileSelections": [], "pluginSelection": {
        "pluginId": "finance-core", "workspaceId": "synthetic-workspace", "recordIds": ["entry:record-1"]}}
    with TestClient(app()) as first:
        first.app.state.harness_service.context_provider = provider
        first.app.state.harness_service.inference_provider = provider
        response = first.post("/api/harness/preview", json=request)
        assert response.status_code == 200, response.text
        initial = response.json()
        completed = context(first, request, initial)
        assert completed.status_code == 200, completed.text
        assert inference(first, initial, completed.json()).status_code == 200
        response = first.post("/api/memory/candidates", json={"runId": initial["runId"],
            "text": "Synthetic Released background conditions."})
        assert response.status_code == 200, response.text
        candidate = response.json()
        response = first.post(f"/api/memory/{candidate['id']}/promote", json={"version": candidate["version"],
            "reviewed": True, "note": "Reviewed for the first synthetic FC origin."})
        assert response.status_code == 200, response.text
        promoted = response.json()
        choices = [{"memoryId": promoted["id"], "version": promoted["version"]}]
        assert first.post("/api/memory/recommend", json={"runId": initial["runId"], "query": "conditions"}).json() == [promoted]
        assert first.post("/api/harness/preview", json={**request, "selectedMemory": choices}).status_code == 200

    monkeypatch.setenv("FINANCE_CORE_PLUGIN_API_URL", "http://127.0.0.1:9782")
    with TestClient(app()) as second:
        second.app.state.harness_service.context_provider = provider
        second.app.state.harness_service.inference_provider = provider
        response = second.post("/api/harness/preview", json=request)
        assert response.status_code == 200, response.text
        changed = response.json()
        before, after = initial["sourceBindings"][0], changed["sourceBindings"][0]
        assert before["revision"] == after["revision"]
        assert initial["candidateEvidence"] == changed["candidateEvidence"]
        assert second.post("/api/memory/recommend", json={"runId": changed["runId"], "query": "conditions"}).json() == []
        assert second.post("/api/harness/preview", json={**request, "selectedMemory": choices}).status_code == 409
        assert before["identity"]["namespace"] != after["identity"]["namespace"]
        assert second.get(f"/api/memory/{promoted['id']}/versions").json()[-1] == promoted
        assert second.get(f"/api/runtime/runs/{initial['runId']}").status_code == 200
        assert len(provider.calls) == 2
    assert {httpx.URL(url).port for url, _ in upstream_calls} == {9781, 9782}
