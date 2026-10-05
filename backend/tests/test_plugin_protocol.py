"""Synthetic public plugin boundary tests; no real FC, KB or model access."""
import hashlib
import json
import shutil
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from frag_api.errors import PluginValidationError
from frag_api.main import create_app
from frag_api.plugin_host import load_plugin, load_plugins


def package(root: Path, plugin_id="research-notes", *, manifest_changes=None, route=None):
    directory = root / plugin_id / "versions" / "1.0.0"
    directory.mkdir(parents=True)
    path = route or f"/api/plugins/{plugin_id}/status"
    adapter = f'''from fastapi import APIRouter
PLUGIN_ID = {plugin_id!r}
RECORDS = [{{"recordId": "record-1", "label": "Synthetic one", "text": "First synthetic fact.", "revision": "revision-1"}},
           {{"recordId": "record-2", "label": "Synthetic two", "text": "Second synthetic fact.", "revision": "revision-2"}}]
SOURCE_REVISION = "a" * 64

def source_revision():
    return SOURCE_REVISION

def create_router():
    router = APIRouter()
    @router.get({path!r})
    def status():
        return {{"readOnly": True}}
    return router

def read_evidence_request(request):
    if request["scopeId"] != "selected":
        raise ValueError("Invalid scope")
    return {{"protocolVersion": 2, "pluginId": PLUGIN_ID, "scopeId": request["scopeId"],
            "records": [record for record in reversed(RECORDS) if record["recordId"] in request["recordIds"]]}}

def list_scopes(scope_id=None):
    return {{"scopes": [{{"id": "selected", "label": "Synthetic scope", "records": [
        {{"id": record["recordId"], "label": record["label"]}} for record in RECORDS]}}]}}
'''
    (directory / "adapter.py").write_text(adapter, encoding="utf-8")
    (directory / "ui.js").write_text("export function mount(element) { element.textContent = 'Synthetic plugin'; }", encoding="utf-8")
    manifest = {"id": plugin_id, "name": "Synthetic plugin", "protocolVersion": 2,
                "version": "1.0.0", "minHostVersion": "1.8.0", "capabilities": ["evidence.read"],
                "files": {name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
                          for name in ("adapter.py", "ui.js")}}
    if plugin_id == "finance-core":
        manifest["fcApiVersion"] = "3.1.1"
    manifest.update(manifest_changes or {})
    (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (root / plugin_id / "current.json").write_text(json.dumps({"version": "1.0.0", "enabled": True}), encoding="utf-8")
    return directory


def client_for(root, tmp_path):
    return TestClient(create_app(plugin_root=root, rag_index_path=tmp_path / "rag.sqlite3",
                                runtime_path=tmp_path / "runtime.sqlite3"))


def test_protocol_two_has_ordered_selected_reads_and_generic_scopes(tmp_path):
    root = tmp_path / "plugins"
    package(root)
    plugin = load_plugin(root, "research-notes")
    records = plugin.read_selected("selected", ["record-1", "record-2"])
    assert [item["recordId"] for item in records] == ["record-1", "record-2"]
    with client_for(root, tmp_path) as client:
        item = next(item for item in client.get("/api/plugins").json()["plugins"] if item["id"] == "research-notes")
        assert item["installed"] and item["protocolVersion"] == 2 and item["capabilities"] == ["evidence.read"]
        assert client.get("/api/plugins/research-notes/evidence-scopes?scopeId=selected").json()["scopes"][0]["records"][0]["id"] == "record-1"
        assert client.get("/api/plugins/research-notes/evidence-scopes?scopeId=missing").status_code == 422
        assert client.get("/api/plugins/research-notes/evidence-scopes?scopeId=selected&scopeId=other").status_code == 404
        assert client.get("/api/plugins/research-notes/status").status_code == 200
        assert client.post("/api/plugins/research-notes/status").status_code == 405
        assert client.get("/plugins/research-notes/ui.js").content == plugin.ui_content


def test_adapter_execution_uses_the_exact_hash_checked_byte_snapshot(tmp_path, monkeypatch):
    root = tmp_path / "plugins"
    directory = package(root)
    original = Path.read_bytes
    reads = []
    def changed_bytes(path):
        if path == directory / "adapter.py":
            reads.append(path)
            if len(reads) > 1:
                return b"raise RuntimeError('Unchecked adapter bytes were executed')"
        return original(path)
    with monkeypatch.context() as patch:
        patch.setattr(Path, "read_bytes", changed_bytes)
        plugin = load_plugin(root, "research-notes")
    assert len(reads) == 1
    assert plugin.read_selected("selected", ["record-1"])[0]["text"] == "First synthetic fact."


@pytest.mark.parametrize("change", [
    {"protocolVersion": True}, {"protocolVersion": 2.0}, {"protocolVersion": 3},
    {"minHostVersion": "1.9.0"}, {"capabilities": ["finance.write"]}, {"capabilities": "evidence.read"},
    {"name": 123}, {"name": ""}, {"unreviewed": True}, {"id": "../escaped"},
])
def test_protocol_two_manifest_fails_closed(tmp_path, change):
    root = tmp_path / "plugins"
    package(root, manifest_changes=change)
    with pytest.raises(PluginValidationError):
        load_plugin(root, "research-notes")
    with client_for(root, tmp_path) as client:
        assert client.get("/api/plugins/research-notes/status").status_code == 404
        assert client.get("/plugins/research-notes/ui.js").status_code == 404


@pytest.mark.parametrize("value", [None, 123, "short", "A" * 64])
def test_protocol_two_requires_a_nonsecret_configuration_fingerprint(tmp_path, value):
    root = tmp_path / "plugins"
    directory = package(root)
    adapter = directory / "adapter.py"
    adapter.write_text(adapter.read_text(encoding="utf-8").replace('SOURCE_REVISION = "a" * 64', f"SOURCE_REVISION = {value!r}"), encoding="utf-8")
    manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"]["adapter.py"] = hashlib.sha256(adapter.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(PluginValidationError):
        load_plugin(root, "research-notes")


def test_protocol_one_loading_keeps_its_original_optional_scopes_route(tmp_path):
    from test_plugins import install_synthetic
    root = tmp_path / "plugins"
    install_synthetic(root)
    directory = root / "finance-core" / "versions" / "1.0.0"
    adapter = directory / "adapter.py"
    text = adapter.read_text(encoding="utf-8")
    start = text.index('    @router.get("/api/plugins/finance-core/scopes")')
    end = text.index("    return router", start)
    adapter.write_text(text[:start] + text[end:], encoding="utf-8")
    manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"]["adapter.py"] = hashlib.sha256(adapter.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    plugin = load_plugin(root)
    assert plugin.read_selected("synthetic-workspace", ["record-1"])[0]["revision"] == "revision-1"
    with pytest.raises(PluginValidationError):
        plugin.selected_scopes()


@pytest.mark.parametrize("route", ["/api/harness/status", "/api/plugins/research-notes/evidence-scopes",
                                   "/api/plugins/research-notes/../escaped", "/api/plugins/research-notes/{path:path}"])
def test_router_cannot_claim_host_or_other_plugin_routes(tmp_path, route):
    root = tmp_path / "plugins"
    package(root, route=route)
    with pytest.raises(PluginValidationError):
        load_plugin(root, "research-notes")


@pytest.mark.parametrize("scope,ids", [("selected", []), ("selected", ["record-1"] * 2),
                                       ("selected", ["record-1"] * 11), (123, ["record-1"]),
                                       ("other", ["record-1"]), ("selected", [123]), ("selected", ["missing"])])
def test_input_and_unselected_record_requests_are_rejected(tmp_path, scope, ids):
    root = tmp_path / "plugins"
    package(root)
    with pytest.raises(PluginValidationError):
        load_plugin(root, "research-notes").read_selected(scope, ids)


@pytest.mark.parametrize("mutation", ["plugin", "scope", "protocol", "wire_alias", "coerced", "duplicate", "missing", "extra", "oversized", "record_extra"])
def test_reader_output_is_checked_before_use(tmp_path, mutation):
    root = tmp_path / "plugins"
    package(root)
    plugin = load_plugin(root, "research-notes")
    response = {"protocolVersion": 2, "pluginId": plugin.id, "scopeId": "selected",
                "records": [{"recordId": "record-1", "label": "One", "text": "Synthetic fact.", "revision": "v1"}]}
    if mutation == "plugin":
        response["pluginId"] = "another-plugin"
    elif mutation == "scope":
        response["scopeId"] = "other"
    elif mutation == "protocol":
        response["protocolVersion"] = 2.0
    elif mutation == "wire_alias":
        response["protocol_version"] = response.pop("protocolVersion")
    elif mutation == "coerced":
        response["records"][0]["revision"] = 1
    elif mutation == "duplicate":
        response["records"] *= 2
    elif mutation == "missing":
        response["records"] = []
    elif mutation == "extra":
        response["records"].append({**response["records"][0], "recordId": "unselected"})
    elif mutation == "oversized":
        response["records"][0]["text"] = "中" * 25_000
    else:
        response["records"][0]["authority"] = "unverified assertion"
    object.__setattr__(plugin, "read_evidence", lambda _request: response)
    with pytest.raises(PluginValidationError):
        plugin.read_selected("selected", ["record-1"])


@pytest.mark.parametrize("mutation", ["file", "manifest", "state", "during_read"])
def test_loaded_plugin_integrity_is_rechecked_for_reads_routes_and_ui(tmp_path, mutation):
    root = tmp_path / "plugins"
    directory = package(root)
    with client_for(root, tmp_path) as client:
        plugin = client.app.state.plugins["research-notes"]
        target = directory / "adapter.py"
        if mutation == "during_read":
            original = plugin.read_evidence
            def changed_reader(request):
                response = original(request)
                target.write_text(target.read_text(encoding="utf-8") + "\n# synthetic change\n", encoding="utf-8")
                return response
            object.__setattr__(plugin, "read_evidence", changed_reader)
            with pytest.raises(PluginValidationError):
                plugin.read_selected("selected", ["record-1"])
        else:
            if mutation == "file":
                target.write_text(target.read_text(encoding="utf-8") + "\n# synthetic change\n", encoding="utf-8")
            elif mutation == "manifest":
                path = directory / "manifest.json"
                value = json.loads(path.read_text(encoding="utf-8"))
                value["name"] = "Changed name"
                path.write_text(json.dumps(value), encoding="utf-8")
            else:
                (root / plugin.id / "current.json").write_text(json.dumps({"version": "1.0.0", "enabled": False}), encoding="utf-8")
            with pytest.raises(PluginValidationError):
                plugin.read_selected("selected", ["record-1"])
        assert client.get("/api/plugins/research-notes/status").status_code == 404
        assert client.get("/plugins/research-notes/ui.js").status_code == 404


@pytest.mark.parametrize("during_read", [False, True])
def test_source_configuration_change_rejects_same_record_revision(tmp_path, during_read):
    root = tmp_path / "plugins"
    package(root)
    plugin = load_plugin(root, "research-notes")
    original = plugin.read_evidence
    def change_configuration(request):
        response = original(request)
        plugin.revision_reader.__globals__["SOURCE_REVISION"] = "b" * 64
        return response
    if during_read:
        object.__setattr__(plugin, "read_evidence", change_configuration)
    else:
        plugin.revision_reader.__globals__["SOURCE_REVISION"] = "b" * 64
    with pytest.raises(PluginValidationError):
        plugin.read_selected("selected", ["record-1"])


@pytest.mark.parametrize("variable,value", [("FINANCE_CORE_PLUGIN_API_URL", "http://127.0.0.1:9999"),
                                           ("FINANCE_CORE_PLUGIN_RECORDS_JSON", '{"different":["record-1"]}')])
def test_protocol_one_source_configuration_is_bound_without_credentials(tmp_path, monkeypatch, variable, value):
    from test_plugins import install_synthetic
    root = tmp_path / "plugins"
    monkeypatch.delenv("FINANCE_CORE_PLUGIN_API_URL", raising=False)
    monkeypatch.delenv("FINANCE_CORE_PLUGIN_RECORDS_JSON", raising=False)
    install_synthetic(root)
    plugin = load_plugin(root)
    monkeypatch.setenv("FINANCE_CORE_PLUGIN_API_KEY", "synthetic-secret-one")
    plugin.read_selected("synthetic-workspace", ["record-1"])
    monkeypatch.setenv("FINANCE_CORE_PLUGIN_API_KEY", "synthetic-secret-two")
    assert plugin.read_selected("synthetic-workspace", ["record-1"])[0]["revision"] == "revision-1"
    monkeypatch.setenv(variable, value)
    with pytest.raises(PluginValidationError):
        plugin.read_selected("synthetic-workspace", ["record-1"])


def test_invalid_plugin_does_not_hide_an_independent_valid_plugin(tmp_path):
    root = tmp_path / "plugins"
    package(root, "research-notes")
    package(root, "finance-core", manifest_changes={"fcApiVersion": "wrong"})
    loaded, errors = load_plugins(root)
    assert set(loaded) == {"research-notes"} and errors == ("finance-core",)
    with client_for(root, tmp_path) as client:
        assert client.get("/api/plugins/finance-core/status").status_code == 404
        assert client.get("/plugins/finance-core/ui.js").status_code == 404
        assert client.get("/api/plugins/research-notes/status").status_code == 200
        assert client.get("/plugins/research-notes/ui.js").status_code == 200


def test_disable_is_targeted_and_manual_removal_never_deletes(tmp_path):
    if not shutil.which("powershell"):
        pytest.skip("PowerShell is unavailable")
    root = tmp_path / "plugins"
    package(root, "research-notes")
    package(root, "finance-core")
    with client_for(root, tmp_path) as client:
        response = client.post("/api/plugin-management/state", json={"pluginId": "research-notes", "enabled": False},
                               headers={"X-FRAG-Plugin-Action": "state"})
        assert response.status_code == 200, response.text
        assert client.get("/api/plugins/research-notes/status").status_code == 404
        assert client.get("/api/plugins/finance-core/status").status_code == 200
        before = {path.relative_to(root).as_posix(): path.read_bytes() for path in root.rglob("*") if path.is_file()}
        rejected = client.post("/api/plugin-management/uninstall", json={"pluginId": "research-notes"},
                               headers={"X-FRAG-Plugin-Action": "uninstall"})
        assert rejected.status_code == 409
        assert rejected.json()["error"]["code"] == "PLUGIN_MANUAL_REMOVAL_REQUIRED"
        assert before == {path.relative_to(root).as_posix(): path.read_bytes() for path in root.rglob("*") if path.is_file()}
        assert client.post("/api/plugin-management/uninstall", json={"pluginId": "../escaped"},
                           headers={"X-FRAG-Plugin-Action": "uninstall"}).status_code == 422


@pytest.mark.parametrize("entries", [("manifest.json", "adapter.py", "ui.js", "../escaped.py"),
                                    ("manifest.json", "adapter.py", "adapter.py")])
def test_pinned_archive_rejects_extra_or_duplicate_entries_without_activation(tmp_path, entries):
    root = tmp_path / "plugins"
    directory = package(tmp_path / "source")
    archive = tmp_path / "invalid.zip"
    with zipfile.ZipFile(archive, "w") as output:
        for name in entries:
            value = (directory / name).read_bytes() if name in {"manifest.json", "adapter.py", "ui.js"} else b"synthetic"
            if name in output.namelist():
                with pytest.warns(UserWarning, match="Duplicate name"):
                    output.writestr(name, value)
            else:
                output.writestr(name, value)
    body = archive.read_bytes()
    with client_for(root, tmp_path) as client:
        response = client.post("/api/plugin-management/install", content=body, headers={
            "Content-Type": "application/zip", "X-FRAG-Plugin-Action": "install",
            "X-Expected-Sha256": hashlib.sha256(body).hexdigest()})
        assert response.status_code == 422
        assert not (root / "research-notes" / "current.json").exists()
        assert not (tmp_path / "escaped.py").exists()
