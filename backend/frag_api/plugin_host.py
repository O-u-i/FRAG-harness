from __future__ import annotations

import hashlib
import importlib.util
import json
import re
from dataclasses import dataclass
from pathlib import Path

from fastapi import APIRouter

from frag_api.errors import PluginValidationError

HOST_VERSION = "1.0.0"
FC_API_VERSION = "3.1.1"
PLUGIN_ID = "finance-core"
PLUGIN_PROTOCOL = 1
DEFAULT_PLUGIN_ROOT = Path(__file__).resolve().parents[2] / ".local-plugins"
VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")


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
    current = _read_json(current_path)
    if current.get("enabled") is False:
        return None
    version = current.get("version")
    if not isinstance(version, str) or not VERSION_PATTERN.fullmatch(version):
        raise PluginValidationError()
    directory = (root / PLUGIN_ID / "versions" / version).resolve()
    if not directory.is_relative_to(root.resolve()) or not directory.is_dir():
        raise PluginValidationError()
    if {item.name for item in directory.iterdir() if item.is_file()} != {"manifest.json", "adapter.py", "ui.js"}:
        raise PluginValidationError()
    manifest = _read_json(directory / "manifest.json")
    if manifest.get("id") != PLUGIN_ID or manifest.get("protocolVersion") != PLUGIN_PROTOCOL:
        raise PluginValidationError()
    if manifest.get("version") != version or manifest.get("minHostVersion") != HOST_VERSION:
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
    spec = importlib.util.spec_from_file_location(f"frag_plugin_{PLUGIN_ID.replace('-', '_')}", directory / "adapter.py")
    if spec is None or spec.loader is None:
        raise PluginValidationError()
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
        router = module.create_router()
        reader = module.read_evidence
    except Exception as error:
        raise PluginValidationError() from error
    if not isinstance(router, APIRouter):
        raise PluginValidationError()
    if not callable(reader):
        raise PluginValidationError()
    for route in router.routes:
        if not route.path.startswith(f"/api/plugins/{PLUGIN_ID}/"):
            raise PluginValidationError()
        if not getattr(route, "methods", set()).issubset({"GET", "HEAD"}):
            raise PluginValidationError()
    return LoadedPlugin(version=version, directory=directory, router=router, read_evidence=reader)
