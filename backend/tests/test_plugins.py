import hashlib
import json
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from frag_api.errors import PluginValidationError
from frag_api.main import create_app
from frag_api.plugin_host import load_plugin

ADAPTER = '''from fastapi import APIRouter

def create_router():
    router = APIRouter()
    @router.get("/api/plugins/finance-core/dashboard")
    def dashboard():
        return {"workspaceId": "synthetic-workspace", "balance": "12.00", "readOnly": True}
    @router.get("/api/plugins/finance-core/scopes")
    def scopes():
        return {"workspaces": [{"id": "synthetic-workspace", "label": "Synthetic Workspace", "records": [{"id": "record-1", "label": "Synthetic record"}]}]}
    return router

def read_evidence(workspace_id, record_ids):
    if workspace_id != "synthetic-workspace" or record_ids != ["record-1"]:
        raise ValueError("Invalid scope")
    return [{"recordId": "record-1", "label": "Synthetic record", "text": "A selected synthetic fact.", "revision": "revision-1"}]
'''
UI = 'export function mount(element) { element.textContent = "Synthetic dashboard"; }'


def install_synthetic(root: Path, *, enabled=True, corrupt=False):
    directory = root / "finance-core" / "versions" / "1.0.0"
    directory.mkdir(parents=True)
    (directory / "adapter.py").write_text(ADAPTER, encoding="utf-8")
    (directory / "ui.js").write_text(UI, encoding="utf-8")
    files = {name: hashlib.sha256((directory / name).read_bytes()).hexdigest() for name in ("adapter.py", "ui.js")}
    if corrupt:
        files["ui.js"] = "0" * 64
    (directory / "manifest.json").write_text(json.dumps({
        "id": "finance-core", "protocolVersion": 1, "version": "1.0.0",
        "minHostVersion": "1.0.0", "fcApiVersion": "3.1.1", "files": files,
    }), encoding="utf-8")
    (root / "finance-core" / "current.json").write_text(json.dumps({"version": "1.0.0", "enabled": enabled}), encoding="utf-8")


def test_disabled_and_corrupt_plugins_expose_no_routes(tmp_path: Path):
    install_synthetic(tmp_path, enabled=False)
    with TestClient(create_app(plugin_root=tmp_path, rag_index_path=tmp_path / "rag.sqlite3")) as client:
        assert client.get("/api/plugins/finance-core/dashboard").status_code == 404
        assert client.get("/api/plugins").json()["plugins"][0]["installed"] is False
    current = tmp_path / "finance-core" / "current.json"
    current.write_text(json.dumps({"version": "1.0.0", "enabled": "false"}), encoding="utf-8")
    with pytest.raises(PluginValidationError):
        load_plugin(tmp_path)
    with TestClient(create_app(plugin_root=tmp_path, rag_index_path=tmp_path / "rag-invalid.sqlite3")) as client:
        assert client.get("/api/plugins/finance-core/dashboard").status_code == 404
    current.write_text(json.dumps({"version": "1.0.0", "enabled": True}), encoding="utf-8")
    manifest = tmp_path / "finance-core" / "versions" / "1.0.0" / "manifest.json"
    value = json.loads(manifest.read_text(encoding="utf-8"))
    value["files"]["ui.js"] = "0" * 64
    manifest.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(PluginValidationError):
        load_plugin(tmp_path)
    with TestClient(create_app(plugin_root=tmp_path, rag_index_path=tmp_path / "rag2.sqlite3")) as client:
        assert client.get("/api/plugins/finance-core/dashboard").status_code == 404
        assert client.get("/api/plugins").json()["error"] == "Installed plugin failed validation."


def test_protocol_and_host_version_rejection(tmp_path: Path):
    install_synthetic(tmp_path)
    manifest_path = tmp_path / "finance-core" / "versions" / "1.0.0" / "manifest.json"
    for change in ({"protocolVersion": 2}, {"minHostVersion": "2.0.0"}, {"fcApiVersion": "3.1.0"}):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest.update(change)
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with pytest.raises(PluginValidationError):
            load_plugin(tmp_path)
        manifest.update({"protocolVersion": 1, "minHostVersion": "1.0.0", "fcApiVersion": "3.1.1"})
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")


def test_plugin_rejects_websocket_routes(tmp_path: Path):
    install_synthetic(tmp_path)
    directory = tmp_path / "finance-core" / "versions" / "1.0.0"
    adapter = directory / "adapter.py"
    adapter.write_text(ADAPTER.replace("    return router", "    @router.websocket('/api/plugins/finance-core/stream')\n"
                       "    async def stream(_websocket):\n        pass\n    return router"), encoding="utf-8")
    manifest = directory / "manifest.json"
    value = json.loads(manifest.read_text(encoding="utf-8"))
    value["files"]["adapter.py"] = hashlib.sha256(adapter.read_bytes()).hexdigest()
    manifest.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(PluginValidationError):
        load_plugin(tmp_path)


def test_plugin_dashboard_and_bounded_evidence(tmp_path: Path):
    install_synthetic(tmp_path)
    assert load_plugin(tmp_path) is not None
    assert load_plugin(tmp_path) is not None
    assert not (tmp_path / "finance-core" / "versions" / "1.0.0" / "__pycache__").exists()
    with TestClient(create_app(plugin_root=tmp_path, rag_index_path=tmp_path / "rag.sqlite3"), raise_server_exceptions=False) as client:
        assert client.get("/api/plugins/finance-core/dashboard").json() == {
            "workspaceId": "synthetic-workspace", "balance": "12.00", "readOnly": True,
        }
        assert client.get("/api/plugins/finance-core/scopes").json()["workspaces"][0]["id"] == "synthetic-workspace"
        assert client.post("/api/plugins/finance-core/dashboard").status_code == 405
        assert client.get("/plugins/finance-core/ui.js").status_code == 200
        assert client.get("/plugins/finance-core/adapter.py").status_code == 404
        assert client.get("/plugins/finance-core/manifest.json").status_code == 404
        body = {"goal": "Explain the record", "fileSelections": [], "pluginSelection": {
            "pluginId": "finance-core", "workspaceId": "synthetic-workspace", "recordIds": ["record-1"],
        }}
        preview = client.post("/api/harness/preview", json=body)
        assert preview.status_code == 200, preview.text
        assert preview.json()["candidateEvidence"][0]["sourceId"] == "finance-core"
        run = client.post("/api/harness/run", json={**body, "contextFingerprint": preview.json()["contextFingerprint"],
                                                        "approvalToken": preview.json()["approvalToken"], "approved": True})
        assert run.status_code == 200, run.text
        second = run.json()["inferencePreview"]
        assert client.post("/api/harness/inference/run", json={"contextFingerprint": preview.json()["contextFingerprint"],
            "inferenceFingerprint": second["inferenceFingerprint"], "approvalToken": second["approvalToken"], "approved": True}).status_code == 200
        assert client.post("/api/harness/preview", json={**body, "pluginSelection": {**body["pluginSelection"], "workspaceId": "other"}}).status_code == 422
        assert client.post("/api/harness/preview", json={**body, "pluginSelection": {**body["pluginSelection"], "recordIds": ["record-1"] * 11}}).status_code == 422


def test_powershell_installer_hash_activation_and_disable(tmp_path: Path):
    if not shutil.which("powershell"):
        pytest.skip("PowerShell is unavailable")
    repo = Path(__file__).resolve().parents[2]
    install_root = tmp_path / "installed"
    archive = tmp_path / "synthetic-plugin.zip"
    manifest = {
        "id": "finance-core", "protocolVersion": 1, "version": "1.0.0", "minHostVersion": "1.0.0", "fcApiVersion": "3.1.1",
        "files": {"adapter.py": hashlib.sha256(ADAPTER.encode()).hexdigest(),
                  "ui.js": hashlib.sha256(UI.encode()).hexdigest()},
    }
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr("manifest.json", json.dumps(manifest))
        package.writestr("adapter.py", ADAPTER)
        package.writestr("ui.js", UI)
    command = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(repo / "scripts" / "install-plugin.ps1"),
               "-ArchivePath", str(archive), "-ExpectedSha256", "0" * 64, "-InstallRoot", str(install_root)]
    rejected = subprocess.run(command, cwd=repo, capture_output=True, text=True, check=False)
    assert rejected.returncode != 0
    assert not (install_root / "finance-core" / "current.json").exists()
    incompatible_archive = tmp_path / "incompatible.zip"
    with zipfile.ZipFile(incompatible_archive, "w") as package:
        package.writestr("manifest.json", json.dumps({**manifest, "minHostVersion": "2.0.0"}))
        package.writestr("adapter.py", ADAPTER)
        package.writestr("ui.js", UI)
    incompatible = command.copy()
    incompatible[incompatible.index(str(archive))] = str(incompatible_archive)
    incompatible[incompatible.index("0" * 64)] = hashlib.sha256(incompatible_archive.read_bytes()).hexdigest()
    rejected_version = subprocess.run(incompatible, cwd=repo, capture_output=True, text=True, check=False)
    assert rejected_version.returncode != 0
    assert not (install_root / "finance-core" / "current.json").exists()
    oversized_archive = tmp_path / "oversized.zip"
    oversized_ui = "x" * (5 * 1024 * 1024 + 1)
    oversized_manifest = {**manifest, "files": {**manifest["files"],
        "ui.js": hashlib.sha256(oversized_ui.encode()).hexdigest()}}
    with zipfile.ZipFile(oversized_archive, "w") as package:
        package.writestr("manifest.json", json.dumps(oversized_manifest))
        package.writestr("adapter.py", ADAPTER)
        package.writestr("ui.js", oversized_ui)
    oversized_command = command.copy()
    oversized_command[oversized_command.index(str(archive))] = str(oversized_archive)
    oversized_command[oversized_command.index("0" * 64)] = hashlib.sha256(oversized_archive.read_bytes()).hexdigest()
    oversized = subprocess.run(oversized_command, cwd=repo, capture_output=True, text=True, check=False)
    assert oversized.returncode != 0
    assert not (install_root / "finance-core" / "current.json").exists()
    command[command.index("0" * 64)] = hashlib.sha256(archive.read_bytes()).hexdigest()
    installed = subprocess.run(command, cwd=repo, capture_output=True, text=True, check=False)
    assert installed.returncode == 0, installed.stderr
    assert load_plugin(install_root) is not None
    disabled = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(repo / "scripts" / "install-plugin.ps1"),
                               "-Disable", "-InstallRoot", str(install_root)], cwd=repo, capture_output=True, text=True, check=False)
    assert disabled.returncode == 0, disabled.stderr
    assert load_plugin(install_root) is None
    enabled = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                              str(repo / "scripts" / "install-plugin.ps1"), "-Enable", "-InstallRoot", str(install_root)],
                             cwd=repo, capture_output=True, text=True, check=False)
    assert enabled.returncode == 0, enabled.stderr
    assert load_plugin(install_root) is not None
    older = install_root / "finance-core" / "versions" / "0.9.0"
    shutil.copytree(install_root / "finance-core" / "versions" / "1.0.0", older)
    unexpected = older / "unexpected.txt"
    unexpected.write_text("synthetic", encoding="utf-8")
    uninstall_command = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                         str(repo / "scripts" / "install-plugin.ps1"), "-Uninstall", "-InstallRoot", str(install_root)]
    rejected_uninstall = subprocess.run(uninstall_command, cwd=repo, capture_output=True, text=True, check=False)
    assert rejected_uninstall.returncode != 0
    assert (install_root / "finance-core" / "current.json").exists()
    unexpected.unlink()
    uninstalled = subprocess.run(uninstall_command, cwd=repo, capture_output=True, text=True, check=False)
    assert uninstalled.returncode == 0, uninstalled.stderr
    assert not (install_root / "finance-core").exists()


def test_browser_plugin_install_and_uninstall_are_pinned_and_restart_gated(tmp_path: Path):
    if not shutil.which("powershell"):
        pytest.skip("PowerShell is unavailable")
    root = tmp_path / "managed"
    archive = tmp_path / "synthetic-plugin.zip"
    manifest = {
        "id": "finance-core", "protocolVersion": 1, "version": "1.0.0",
        "minHostVersion": "1.0.0", "fcApiVersion": "3.1.1",
        "files": {"adapter.py": hashlib.sha256(ADAPTER.encode()).hexdigest(),
                  "ui.js": hashlib.sha256(UI.encode()).hexdigest()},
    }
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr("manifest.json", json.dumps(manifest))
        package.writestr("adapter.py", ADAPTER)
        package.writestr("ui.js", UI)
    body = archive.read_bytes()
    headers = {"Content-Type": "application/zip", "X-FRAG-Plugin-Action": "install",
               "X-Expected-Sha256": hashlib.sha256(body).hexdigest()}
    with TestClient(create_app(plugin_root=root, rag_index_path=tmp_path / "rag.sqlite3")) as client:
        assert client.post("/api/plugin-management/install", content=body,
                           headers={**headers, "Origin": "https://untrusted.example"}).status_code == 403
        assert client.post("/api/plugin-management/install", content=body,
                           headers={**headers, "Origin": "http://127.0.0.1:5174",
                                    "X-Expected-Sha256": "0" * 64}).json()["error"]["code"] == "ARCHIVE_HASH_MISMATCH"
        assert not (root / "finance-core" / "current.json").exists()
        installed = client.post("/api/plugin-management/install", content=body, headers=headers)
        assert installed.status_code == 200, installed.text
        assert installed.json() == {"status": "installed", "restartRequired": True}
        assert client.get("/api/plugins").json()["plugins"][0]["packageVersion"] == "1.0.0"
        assert client.get("/api/plugins/finance-core/dashboard").status_code == 404
    with TestClient(create_app(plugin_root=root, rag_index_path=tmp_path / "rag2.sqlite3")) as client:
        assert client.get("/api/plugins/finance-core/dashboard").status_code == 200
        assert client.get("/plugins/finance-core/ui.js").status_code == 200
        disabled = client.post("/api/plugin-management/state", json={"enabled": False},
                               headers={"X-FRAG-Plugin-Action": "state"})
        assert disabled.status_code == 200, disabled.text
        assert disabled.json() == {"status": "disabled", "restartRequired": True}
        assert client.get("/api/plugins").json()["plugins"][0]["packageEnabled"] is False
        assert client.get("/api/plugins/finance-core/dashboard").status_code == 404
    with TestClient(create_app(plugin_root=root, rag_index_path=tmp_path / "rag3.sqlite3")) as client:
        assert client.get("/api/plugins/finance-core/dashboard").status_code == 404
        assert client.post("/api/plugin-management/state", json={"enabled": "true"},
                           headers={"X-FRAG-Plugin-Action": "state"}).status_code == 422
        enabled = client.post("/api/plugin-management/state", json={"enabled": True},
                              headers={"X-FRAG-Plugin-Action": "state"})
        assert enabled.status_code == 200, enabled.text
        assert enabled.json() == {"status": "enabled", "restartRequired": True}
        assert client.get("/api/plugins/finance-core/dashboard").status_code == 404
    with TestClient(create_app(plugin_root=root, rag_index_path=tmp_path / "rag4.sqlite3")) as client:
        assert client.get("/api/plugins/finance-core/dashboard").status_code == 200
        assert client.post("/api/plugin-management/uninstall").status_code == 403
        removed = client.post("/api/plugin-management/uninstall",
                              headers={"X-FRAG-Plugin-Action": "uninstall"})
        assert removed.status_code == 200, removed.text
        assert removed.json() == {"status": "uninstalled", "restartRequired": True}
        assert client.get("/api/plugins/finance-core/dashboard").status_code == 404
        assert client.get("/plugins/finance-core/ui.js").status_code == 404
        assert client.get("/api/plugins").json()["plugins"][0]["packageVersion"] is None
    assert not (root / "finance-core" / "current.json").exists()
    assert not (root / "finance-core" / "versions" / "1.0.0" / "adapter.py").exists()
    with TestClient(create_app(plugin_root=root, rag_index_path=tmp_path / "rag5.sqlite3")) as client:
        assert client.get("/api/plugins/finance-core/dashboard").status_code == 404
