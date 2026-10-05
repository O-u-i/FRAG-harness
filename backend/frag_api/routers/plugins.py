import asyncio
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from frag_api.http import error_response
from frag_api.errors import PluginValidationError
from frag_api.plugin_host import PLUGIN_ID, valid_plugin_id
from frag_api.schemas.plugin import PLUGIN_ID_PATTERN
from frag_api.services.plugin_management import (
    MAX_ARCHIVE_BYTES, SHA256_PATTERN, PluginManagementError,
    install_archive, package_state, set_plugin_enabled, uninstall_plugin,
)

router = APIRouter()


class PluginStateInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    enabled: bool
    plugin_id: str = Field(default=PLUGIN_ID, alias="pluginId", pattern=PLUGIN_ID_PATTERN, max_length=63)


class PluginRemovalInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    plugin_id: str = Field(alias="pluginId", pattern=PLUGIN_ID_PATTERN, max_length=63)


def _management_request_valid(request: Request, action: str) -> bool:
    origin = request.headers.get("origin")
    if origin:
        try:
            parsed = urlsplit(origin)
            if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
                    or parsed.port is None or parsed.path or parsed.query or parsed.fragment
                    or parsed.username or parsed.password):
                return False
        except ValueError:
            return False
    return request.headers.get("x-frag-plugin-action") == action and not request.query_params


def _deactivate_until_restart(request: Request, plugin_id: str) -> None:
    request.app.state.plugin_hidden.add(plugin_id)
    request.app.state.plugins.pop(plugin_id, None)
    request.app.state.harness_service.plugins.pop(plugin_id, None)
    if plugin_id == PLUGIN_ID:
        request.app.state.plugin = None
        request.app.state.harness_service.plugin = None


@router.get("/api/plugins")
def plugins(request: Request) -> dict:
    root = Path(request.app.state.plugin_root)
    ids = set(request.app.state.plugins) | {PLUGIN_ID}
    if root.is_dir() and not root.is_symlink() and not root.is_junction():
        ids.update(path.name for path in root.iterdir() if valid_plugin_id(path.name))
    catalog = []
    for plugin_id in sorted(ids):
        installed = request.app.state.plugins.get(plugin_id)
        version, enabled = package_state(root, plugin_id)
        if installed is not None:
            try:
                installed.ensure_current()
            except (PluginValidationError, OSError):
                _deactivate_until_restart(request, plugin_id)
                installed = None
                request.app.state.plugin_error = True
        catalog.append({
            "id": plugin_id, "name": installed.name if installed else ("Finance Core" if plugin_id == PLUGIN_ID else plugin_id),
            "installed": installed is not None, "version": installed.version if installed else None,
            "uiUrl": installed.ui_url if installed else None, "packageVersion": version,
            "packageEnabled": enabled, "protocolVersion": installed.protocol_version if installed else None,
            "capabilities": ["evidence.read"] if installed else [],
        })
    return {
        "protocolVersion": 2,
        "error": "Installed plugin failed validation." if request.app.state.plugin_error else None,
        "plugins": catalog,
    }


@router.get("/api/plugins/{plugin_id}/evidence-scopes")
def evidence_scopes(request: Request, plugin_id: str, scopeId: str | None = None):
    plugin = request.app.state.plugins.get(plugin_id)
    if plugin is None or set(request.query_params) - {"scopeId"} or len(request.query_params.getlist("scopeId")) > 1:
        return error_response(404, "NOT_FOUND", "Endpoint was not found.")
    try:
        return plugin.selected_scopes(scopeId)
    except PluginValidationError:
        return error_response(422, "PLUGIN_SCOPE_INVALID", "Selected plugin scope is unavailable.")


@router.post("/api/plugin-management/install")
async def install(request: Request) -> JSONResponse:
    if not _management_request_valid(request, "install") or request.headers.get("content-type") != "application/zip":
        return error_response(403, "PLUGIN_ACTION_REJECTED", "Local plugin action was rejected.")
    expected = request.headers.get("x-expected-sha256", "")
    if not SHA256_PATTERN.fullmatch(expected):
        return error_response(422, "INVALID_SHA256", "Enter a 64-character SHA-256 value.")
    archive = await request.body()
    if not archive or len(archive) > MAX_ARCHIVE_BYTES:
        return error_response(413, "ARCHIVE_SIZE_INVALID", "Archive must be at most 20 MiB.")
    async with request.app.state.plugin_management_lock:
        try:
            plugin_id = await asyncio.to_thread(install_archive, Path(request.app.state.plugin_root), archive, expected)
        except PluginManagementError as error:
            return error_response(error.status, error.code, error.message)
        _deactivate_until_restart(request, plugin_id)
    return JSONResponse({"status": "installed", "restartRequired": True, "pluginId": plugin_id})


@router.post("/api/plugin-management/uninstall")
async def uninstall(request: Request) -> JSONResponse:
    if not _management_request_valid(request, "uninstall"):
        return error_response(403, "PLUGIN_ACTION_REJECTED", "Local plugin action was rejected.")
    plugin_id = request.headers.get("x-frag-plugin-id", PLUGIN_ID)
    body = await request.body()
    if body:
        try:
            value = PluginRemovalInput.model_validate_json(body)
            if "x-frag-plugin-id" in request.headers and plugin_id != value.plugin_id:
                raise ValueError()
            plugin_id = value.plugin_id
        except (ValidationError, ValueError):
            return error_response(422, "INVALID_REQUEST", "The request does not match its contract.")
    if not valid_plugin_id(plugin_id):
        return error_response(422, "INVALID_REQUEST", "The request does not match its contract.")
    async with request.app.state.plugin_management_lock:
        try:
            await asyncio.to_thread(uninstall_plugin, Path(request.app.state.plugin_root), plugin_id)
        except PluginManagementError as error:
            return error_response(error.status, error.code, error.message)


@router.post("/api/plugin-management/state")
async def set_state(request: Request, input_data: PluginStateInput) -> JSONResponse:
    if not _management_request_valid(request, "state"):
        return error_response(403, "PLUGIN_ACTION_REJECTED", "Local plugin action was rejected.")
    async with request.app.state.plugin_management_lock:
        try:
            await asyncio.to_thread(set_plugin_enabled, Path(request.app.state.plugin_root), input_data.enabled, input_data.plugin_id)
        except PluginManagementError as error:
            return error_response(error.status, error.code, error.message)
        _deactivate_until_restart(request, input_data.plugin_id)
    return JSONResponse({"status": "enabled" if input_data.enabled else "disabled", "restartRequired": True})
