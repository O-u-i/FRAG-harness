from __future__ import annotations

import hashlib
import json
import os
import re
from types import ModuleType
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from fastapi import APIRouter
from fastapi.routing import APIRoute

from frag_api.errors import PluginValidationError
from frag_api.schemas.plugin import (
    PLUGIN_ID_PATTERN, PluginEvidenceRequest, PluginEvidenceResponse, PluginScopes,
)

SUPPORTED_PLUGIN_MIN_HOST_VERSION = "1.0.0"
FC_API_VERSION = "3.1.1"
PLUGIN_ID = "finance-core"
PLUGIN_PROTOCOL = 1
PROTOCOL2_MIN_HOST_VERSION = "1.8.0"
DEFAULT_PLUGIN_ROOT = Path(__file__).resolve().parents[2] / ".local-plugins"
VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
PLUGIN_ID_RE = re.compile(PLUGIN_ID_PATTERN)
MAX_EVIDENCE_BYTES = 64 * 1024
FILE_LIMITS = {"manifest.json": 64 * 1024, "adapter.py": 2 * 1024 * 1024, "ui.js": 5 * 1024 * 1024}


def valid_plugin_id(value) -> bool:
    return isinstance(value, str) and len(value) <= 63 and PLUGIN_ID_RE.fullmatch(value) is not None


def _legacy_source_revision() -> str:
    value = {"apiUrl": os.environ.get("FINANCE_CORE_PLUGIN_API_URL", "http://127.0.0.1:8788").rstrip("/"),
             "recordsJson": os.environ.get("FINANCE_CORE_PLUGIN_RECORDS_JSON", "{}")}
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _is_reparse_point(path: Path) -> bool:
    try:
        return path.is_symlink() or bool(path.lstat().st_file_attributes & 0x400)
    except (AttributeError, OSError):
        return False


@dataclass(frozen=True)
class LoadedPlugin:
    version: str
    directory: Path
    router: APIRouter
    read_evidence: object
    id: str = PLUGIN_ID
    name: str = "Finance Core"
    protocol_version: int = 1
    digest: str = ""
    list_scopes: Callable | None = None
    ui_content: bytes = b""
    source_revision: str = ""
    revision_reader: Callable | None = None

    @property
    def ui_url(self) -> str:
        return f"/plugins/{self.id}/ui.js"

    def ensure_current(self) -> None:
        try:
            package = _checked_package(self.directory.parents[2], self.id)
            if (package is None or package[0]["version"] != self.version or package[2] != self.digest
                    or self.revision_reader() != self.source_revision):
                raise PluginValidationError()
        except Exception as error:
            raise PluginValidationError() from error

    def read_selected(self, scope_id: str, record_ids: list[str]) -> list[dict]:
        try:
            request = PluginEvidenceRequest(pluginId=self.id, scopeId=scope_id, recordIds=record_ids)
            self.ensure_current()
            if self.protocol_version == 1:
                response = {"protocolVersion": 2, "pluginId": self.id, "scopeId": scope_id,
                            "records": self.read_evidence(scope_id, record_ids)}
            else:
                response = self.read_evidence(request.model_dump(by_alias=True))
            if len(json.dumps(response, ensure_ascii=False, allow_nan=False).encode("utf-8")) > MAX_EVIDENCE_BYTES:
                raise PluginValidationError()
            parsed = PluginEvidenceResponse.model_validate(response)
            if (parsed.plugin_id != self.id or parsed.scope_id != scope_id
                    or {item.record_id for item in parsed.records} != set(record_ids)):
                raise PluginValidationError()
            self.ensure_current()
            by_id = {item.record_id: item.model_dump(by_alias=True) for item in parsed.records}
            return [by_id[value] for value in record_ids]
        except Exception as error:
            raise PluginValidationError() from error

    def selected_scopes(self, scope_id: str | None = None) -> dict:
        try:
            if scope_id is not None and (not isinstance(scope_id, str) or not scope_id or len(scope_id) > 500):
                raise PluginValidationError()
            self.ensure_current()
            response = self.list_scopes(scope_id)
            if len(json.dumps(response, ensure_ascii=False, allow_nan=False).encode("utf-8")) > MAX_EVIDENCE_BYTES:
                raise PluginValidationError()
            parsed = PluginScopes.model_validate(response)
            if scope_id is not None:
                parsed.scopes = [item for item in parsed.scopes if item.id == scope_id]
                if len(parsed.scopes) != 1:
                    raise PluginValidationError()
            self.ensure_current()
            return parsed.model_dump(by_alias=True)
        except Exception as error:
            raise PluginValidationError() from error


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as error:
        raise PluginValidationError() from error
    if not isinstance(value, dict):
        raise PluginValidationError()
    return value


def _checked_package(root: Path, plugin_id: str) -> tuple[dict, Path, str, dict[str, bytes]] | None:
    if not valid_plugin_id(plugin_id):
        raise PluginValidationError()
    current_path = root / plugin_id / "current.json"
    if not current_path.is_file():
        return None
    if any(_is_reparse_point(path) for path in (root, root / plugin_id, root / plugin_id / "versions", current_path)):
        raise PluginValidationError()
    if current_path.stat().st_size > 16 * 1024:
        raise PluginValidationError()
    current = _read_json(current_path)
    if not isinstance(current.get("enabled"), bool):
        raise PluginValidationError()
    if not current["enabled"]:
        return None
    version = current.get("version")
    if not isinstance(version, str) or not VERSION_PATTERN.fullmatch(version):
        raise PluginValidationError()
    directory = (root / plugin_id / "versions" / version).resolve()
    if _is_reparse_point(root / plugin_id / "versions" / version) or not directory.is_relative_to(root.resolve()) or not directory.is_dir():
        raise PluginValidationError()
    entries = list(directory.iterdir())
    if any(_is_reparse_point(item) or not item.is_file() for item in entries):
        raise PluginValidationError()
    if {item.name for item in entries} != {"manifest.json", "adapter.py", "ui.js"}:
        raise PluginValidationError()
    if any(item.stat().st_size > FILE_LIMITS[item.name] for item in entries):
        raise PluginValidationError()
    contents = {name: (directory / name).read_bytes() for name in FILE_LIMITS}
    if any(len(data) > FILE_LIMITS[name] for name, data in contents.items()):
        raise PluginValidationError()
    try:
        manifest = json.loads(contents["manifest.json"].decode("utf-8-sig"))
    except (UnicodeError, ValueError) as error:
        raise PluginValidationError() from error
    if not isinstance(manifest, dict):
        raise PluginValidationError()
    protocol = manifest.get("protocolVersion")
    if manifest.get("id") != plugin_id or type(protocol) is not int or protocol not in {1, 2}:
        raise PluginValidationError()
    minimum = SUPPORTED_PLUGIN_MIN_HOST_VERSION if protocol == 1 else PROTOCOL2_MIN_HOST_VERSION
    if manifest.get("version") != version or manifest.get("minHostVersion") != minimum:
        raise PluginValidationError()
    if protocol == 1 and plugin_id != PLUGIN_ID:
        raise PluginValidationError()
    if plugin_id == PLUGIN_ID and manifest.get("fcApiVersion") != FC_API_VERSION:
        raise PluginValidationError()
    if protocol == 2:
        allowed = {"id", "name", "protocolVersion", "version", "minHostVersion", "capabilities", "files"}
        if plugin_id == PLUGIN_ID:
            allowed.add("fcApiVersion")
        if (set(manifest) != allowed or not isinstance(manifest.get("name"), str)
                or not manifest["name"] or len(manifest["name"]) > 100
                or manifest.get("capabilities") != ["evidence.read"]):
            raise PluginValidationError()
    files = manifest.get("files")
    if not isinstance(files, dict) or set(files) != {"ui.js", "adapter.py"}:
        raise PluginValidationError()
    for name, expected in files.items():
        path = directory / name
        if _is_reparse_point(path) or not path.is_file() or not isinstance(expected, str) or re.fullmatch(r"[a-fA-F0-9]{64}", expected) is None:
            raise PluginValidationError()
        if hashlib.sha256(contents[name]).hexdigest() != expected.lower():
            raise PluginValidationError()
    digest = hashlib.sha256(b"\0".join(contents[name] for name in sorted(FILE_LIMITS))).hexdigest()
    return manifest, directory, digest, contents


def load_plugin(root: Path = DEFAULT_PLUGIN_ROOT, plugin_id: str = PLUGIN_ID) -> LoadedPlugin | None:
    package = _checked_package(root, plugin_id)
    if package is None:
        return None
    manifest, directory, digest, contents = package
    protocol = manifest["protocolVersion"]
    adapter_path = directory / "adapter.py"
    module = ModuleType(f"frag_plugin_{plugin_id.replace('-', '_')}")
    module.__file__ = str(adapter_path)
    try:
        exec(compile(contents["adapter.py"], str(adapter_path), "exec"), module.__dict__)
        router = module.create_router()
        reader = module.read_evidence if protocol == 1 else module.read_evidence_request
        scope_reader = None if protocol == 1 else module.list_scopes
        revision_reader = _legacy_source_revision if protocol == 1 else module.source_revision
    except Exception as error:
        raise PluginValidationError() from error
    if not isinstance(router, APIRouter):
        raise PluginValidationError()
    if not callable(reader) or not callable(revision_reader) or (protocol == 2 and not callable(scope_reader)):
        raise PluginValidationError()
    try:
        source_revision = revision_reader()
        if not isinstance(source_revision, str) or re.fullmatch(r"[a-f0-9]{64}", source_revision) is None:
            raise PluginValidationError()
    except Exception as error:
        raise PluginValidationError() from error
    for route in router.routes:
        if (not isinstance(route, APIRoute) or not route.path.startswith(f"/api/plugins/{plugin_id}/")
                or any(part in {".", ".."} for part in route.path.split("/")) or "\\" in route.path
                or "{" in route.path or "}" in route.path
                or route.path.rstrip("/") == f"/api/plugins/{plugin_id}/evidence-scopes"):
            raise PluginValidationError()
        if not route.methods or not route.methods.issubset({"GET", "HEAD"}):
            raise PluginValidationError()
    if protocol == 1:
        scopes_routes = [route for route in router.routes if route.path == f"/api/plugins/{plugin_id}/scopes"]
        if len(scopes_routes) > 1:
            raise PluginValidationError()
        endpoint = scopes_routes[0].endpoint if scopes_routes else None

        def scope_reader(_scope_id=None):
            if endpoint is None:
                raise PluginValidationError()
            value = endpoint()
            if not isinstance(value, dict) or set(value) != {"workspaces"}:
                raise PluginValidationError()
            return {"scopes": value["workspaces"]}

    return LoadedPlugin(version=manifest["version"], directory=directory, router=router, read_evidence=reader,
                        id=plugin_id, name=manifest.get("name", "Finance Core"), protocol_version=protocol,
                        digest=digest, list_scopes=scope_reader, ui_content=contents["ui.js"],
                        source_revision=source_revision, revision_reader=revision_reader)


def load_plugins(root: Path = DEFAULT_PLUGIN_ROOT) -> tuple[dict[str, LoadedPlugin], tuple[str, ...]]:
    if not root.exists():
        return {}, ()
    if _is_reparse_point(root) or not root.is_dir():
        return {}, ("invalid-root",)
    loaded, errors = {}, []
    for directory in sorted(root.iterdir(), key=lambda path: path.name):
        if not directory.is_dir():
            continue
        if not valid_plugin_id(directory.name):
            errors.append("invalid-package")
            continue
        try:
            plugin = load_plugin(root, directory.name)
            if plugin is not None:
                loaded[plugin.id] = plugin
        except (PluginValidationError, OSError):
            errors.append(directory.name)
    return loaded, tuple(errors)
