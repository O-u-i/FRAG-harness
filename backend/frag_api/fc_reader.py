"""Pinned official FC reader only. No plugin catalog, mounted routes or plugin UI."""
from __future__ import annotations

import hashlib
import json
import re
from types import ModuleType
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


from frag_api.errors import PluginValidationError
from frag_api.schemas.plugin import (
    PluginEvidenceRequest, PluginEvidenceResponse, PluginScopes,
)

FC_API_VERSION = "3.2.0"
PLUGIN_ID = "finance-core"
PROTOCOL2_MIN_HOST_VERSION = "1.12.1"
MAX_EVIDENCE_BYTES = 64 * 1024
FILE_LIMITS = {"manifest.json": 64 * 1024, "adapter.py": 2 * 1024 * 1024, "ui.js": 5 * 1024 * 1024}


def _is_reparse_point(path: Path) -> bool:
    try:
        return path.is_symlink() or bool(path.lstat().st_file_attributes & 0x400)
    except (AttributeError, OSError):
        return False


@dataclass(frozen=True)
class FcReader:
    version: str
    directory: Path
    read_evidence: object
    id: str = PLUGIN_ID
    name: str = "Finance Core"
    digest: str = ""
    list_scopes: Callable | None = None
    source_revision: str = ""
    revision_reader: Callable | None = None

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
    if plugin_id != PLUGIN_ID:
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
    if version != "1.2.0":
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
    if manifest.get("id") != plugin_id or type(protocol) is not int or protocol != 2:
        raise PluginValidationError()
    minimum = PROTOCOL2_MIN_HOST_VERSION
    if manifest.get("version") != version or manifest.get("minHostVersion") != minimum:
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
    if digest != "f87866a23d3ed926ae96213f0b457d909f33ec3e841c9fe21a2f4c4e808bd5ab":
        raise PluginValidationError()
    return manifest, directory, digest, contents


def load_fc(root: Path) -> FcReader | None:
    plugin_id = PLUGIN_ID
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
        reader = module.read_evidence_request
        scope_reader = module.list_scopes
        revision_reader = module.source_revision
    except Exception as error:
        raise PluginValidationError() from error
    if not callable(reader) or not callable(revision_reader) or (protocol == 2 and not callable(scope_reader)):
        raise PluginValidationError()
    try:
        source_revision = revision_reader()
        if not isinstance(source_revision, str) or re.fullmatch(r"[a-f0-9]{64}", source_revision) is None:
            raise PluginValidationError()
    except Exception as error:
        raise PluginValidationError() from error
    return FcReader(version=manifest["version"], directory=directory, read_evidence=reader,
                        id=plugin_id, name=manifest.get("name", "Finance Core"),
                        digest=digest, list_scopes=scope_reader,
                        source_revision=source_revision, revision_reader=revision_reader)


def install_fc(archive: Path, state: Path):
    """Install only the byte-pinned released FC artifact, never an arbitrary plugin."""
    import zipfile
    expected = "9d4f66b101183b19d5e50d807386c276cc77937517a6f7d59be813971ccd1ee6"
    state = state.absolute()
    if any(_is_reparse_point(path) for path in (state, *state.parents)) or not state.is_dir():
        raise PluginValidationError()
    if archive.stat().st_size > 20 * 1024 * 1024 or _is_reparse_point(archive):
        raise PluginValidationError()
    data = archive.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected:
        raise PluginValidationError()
    import io
    with zipfile.ZipFile(io.BytesIO(data)) as source:
        if len(source.namelist()) != 3 or set(source.namelist()) != set(FILE_LIMITS):
            raise PluginValidationError()
        contents = {name: source.read(name) for name in FILE_LIMITS}
    root = state / "plugins"
    directory = root / PLUGIN_ID / "versions" / "1.2.0"
    current = root / PLUGIN_ID / "current.json"
    if any(_is_reparse_point(path) for path in (directory, *directory.parents, current)):
        raise PluginValidationError()
    if directory.exists():
        if set(p.name for p in directory.iterdir()) != set(contents) or any(_is_reparse_point(directory/name) or (directory/name).read_bytes() != value for name,value in contents.items()):
            raise PluginValidationError()
    else:
        directory.mkdir(parents=True)
        for name, value in contents.items():
            (directory / name).write_bytes(value)
    # Token/record configuration is separate; installation grants no read scope.
    current.write_text(json.dumps({"enabled":True,"version":"1.2.0"}), encoding="utf8")
    _checked_package(root, PLUGIN_ID)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Install the pinned official FC 1.2.0 reader. Stop this project's backend first.")
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    args = parser.parse_args()
    install_fc(args.archive, args.state_dir)
    print("FC reader installed. Configure backend-only fc.env and explicitly enable finance-core in Settings.")
