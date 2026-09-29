from __future__ import annotations

import hashlib
import json
import re
from types import ModuleType
from dataclasses import dataclass
from pathlib import Path

from fastapi import APIRouter
from fastapi.routing import APIRoute

from frag_api.errors import PluginValidationError

SUPPORTED_PLUGIN_MIN_HOST_VERSION = "1.0.0"
FC_API_VERSION = "3.1.1"
PLUGIN_ID = "finance-core"
PLUGIN_PROTOCOL = 1
DEFAULT_PLUGIN_ROOT = Path(__file__).resolve().parents[2] / ".local-plugins"
VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")


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

    @property
    def ui_url(self) -> str:
        return f"/plugins/{PLUGIN_ID}/ui.js"


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as error:
        raise PluginValidationError() from error
    if not isinstance(value, dict):
        raise PluginValidationError()
    return value


def load_plugin(root: Path = DEFAULT_PLUGIN_ROOT) -> LoadedPlugin | None:
    current_path = root / PLUGIN_ID / "current.json"
    if not current_path.is_file():
        return None
    if any(_is_reparse_point(path) for path in (root, root / PLUGIN_ID, root / PLUGIN_ID / "versions", current_path)):
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
    directory = (root / PLUGIN_ID / "versions" / version).resolve()
    if _is_reparse_point(root / PLUGIN_ID / "versions" / version) or not directory.is_relative_to(root.resolve()) or not directory.is_dir():
        raise PluginValidationError()
    entries = list(directory.iterdir())
    if any(item.is_symlink() or not item.is_file() for item in entries):
        raise PluginValidationError()
    if {item.name for item in entries} != {"manifest.json", "adapter.py", "ui.js"}:
        raise PluginValidationError()
    limits = {"manifest.json": 64 * 1024, "adapter.py": 2 * 1024 * 1024, "ui.js": 5 * 1024 * 1024}
    if any(item.stat().st_size > limits[item.name] for item in entries):
        raise PluginValidationError()
    manifest = _read_json(directory / "manifest.json")
    if manifest.get("id") != PLUGIN_ID or manifest.get("protocolVersion") != PLUGIN_PROTOCOL:
        raise PluginValidationError()
    if manifest.get("version") != version or manifest.get("minHostVersion") != SUPPORTED_PLUGIN_MIN_HOST_VERSION:
        raise PluginValidationError()
    if manifest.get("fcApiVersion") != FC_API_VERSION:
        raise PluginValidationError()
    files = manifest.get("files")
    if not isinstance(files, dict) or set(files) != {"ui.js", "adapter.py"}:
        raise PluginValidationError()
    for name, expected in files.items():
        path = directory / name
        if path.is_symlink() or not path.is_file() or not isinstance(expected, str):
            raise PluginValidationError()
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected.lower():
            raise PluginValidationError()
    adapter_path = directory / "adapter.py"
    module = ModuleType(f"frag_plugin_{PLUGIN_ID.replace('-', '_')}")
    module.__file__ = str(adapter_path)
    try:
        exec(compile(adapter_path.read_bytes(), str(adapter_path), "exec"), module.__dict__)
        router = module.create_router()
        reader = module.read_evidence
    except Exception as error:
        raise PluginValidationError() from error
    if not isinstance(router, APIRouter):
        raise PluginValidationError()
    if not callable(reader):
        raise PluginValidationError()
    for route in router.routes:
        if not isinstance(route, APIRoute) or not route.path.startswith(f"/api/plugins/{PLUGIN_ID}/"):
            raise PluginValidationError()
        if not route.methods or not route.methods.issubset({"GET", "HEAD"}):
            raise PluginValidationError()
    return LoadedPlugin(version=version, directory=directory, router=router, read_evidence=reader)
