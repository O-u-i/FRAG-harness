import asyncio
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from frag_api.http import error_response
from frag_api.services.plugin_management import (
    MAX_ARCHIVE_BYTES, SHA256_PATTERN, PluginManagementError,
    install_archive, package_state, set_plugin_enabled, uninstall_plugin,
)

router = APIRouter()


class PluginStateInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    enabled: bool


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


def _deactivate_until_restart(request: Request) -> None:
    request.app.state.plugin_hidden = True
    request.app.state.plugin = None
    request.app.state.harness_service.plugin = None


@router.get("/api/plugins")
def plugins(request: Request) -> dict:
    installed = request.app.state.plugin
    root = Path(request.app.state.plugin_root)
    version, enabled = package_state(root)
    return {
        "protocolVersion": 1,
        "error": "Installed plugin failed validation." if request.app.state.plugin_error else None,
        "plugins": [{
            "id": "finance-core",
            "name": "Finance Core",
            "installed": installed is not None,
            "version": installed.version if installed else None,
            "uiUrl": installed.ui_url if installed else None,
            "packageVersion": version,
            "packageEnabled": enabled,
        }],
    }


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
            await asyncio.to_thread(install_archive, Path(request.app.state.plugin_root), archive, expected)
        except PluginManagementError as error:
            return error_response(error.status, error.code, error.message)
        _deactivate_until_restart(request)
    return JSONResponse({"status": "installed", "restartRequired": True})


@router.post("/api/plugin-management/uninstall")
async def uninstall(request: Request) -> JSONResponse:
    if not _management_request_valid(request, "uninstall") or await request.body():
        return error_response(403, "PLUGIN_ACTION_REJECTED", "Local plugin action was rejected.")
    async with request.app.state.plugin_management_lock:
        try:
            await asyncio.to_thread(uninstall_plugin, Path(request.app.state.plugin_root))
        except PluginManagementError as error:
            return error_response(error.status, error.code, error.message)
        _deactivate_until_restart(request)
    return JSONResponse({"status": "uninstalled", "restartRequired": True})


@router.post("/api/plugin-management/state")
async def set_state(request: Request, input_data: PluginStateInput) -> JSONResponse:
    if not _management_request_valid(request, "state"):
        return error_response(403, "PLUGIN_ACTION_REJECTED", "Local plugin action was rejected.")
    async with request.app.state.plugin_management_lock:
        try:
            await asyncio.to_thread(set_plugin_enabled, Path(request.app.state.plugin_root), input_data.enabled)
        except PluginManagementError as error:
            return error_response(error.status, error.code, error.message)
        _deactivate_until_restart(request)
    return JSONResponse({"status": "enabled" if input_data.enabled else "disabled", "restartRequired": True})
