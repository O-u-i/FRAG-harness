from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHttpException

from frag_api.errors import (
    HarnessSourceError, PluginValidationError, RagFingerprintError, RagIndexBuildError,
    RagIndexNotReadyError, RagIndexStaleError, RagNotReadyError, RagOutputError,
    RagProviderError, RequestContractError,
    PolicyRejectedError, RequestBudgetError, RagRefusalError, RagIncompleteError, RagOutcomeUnknownError,
    RuntimeConflictError, RuntimeNotFoundError,
)
from frag_api.http import BodyLimitMiddleware, error_response, issue_path
from frag_api.plugin_host import DEFAULT_PLUGIN_ROOT, load_plugins
from frag_api.routers.context_sources import router as sources_router
from frag_api.routers.harness import router as harness_router
from frag_api.routers.health import router as health_router
from frag_api.routers.plugins import router as plugins_router
from frag_api.routers.rag import router as rag_router
from frag_api.routers.runtime import router as runtime_router
from frag_api.routers.tools import router as tools_router
from frag_api.routers.research import router as research_router
from frag_api.routers.memory import router as memory_router
from frag_api.routers.agents import router as agents_router
from frag_api.services.agent_host import AgentHost
from frag_api.services.memory_service import MemoryService
from frag_api.services.kb_tools import KBTools
from frag_api.services.research_flow import ResearchFlow
from frag_api.cli_client import host_cli_binding
from frag_api.repositories.runtime_repository import RuntimeRepository
from frag_api.services.context_source_service import ContextSourceService
from frag_api.services.harness_service import HarnessService
from frag_api.services.rag_service import RagService, create_rag_service
from frag_api.services.runtime_policy import redact, configured_secrets
from frag_api.services.runtime_service import RuntimeService
from frag_api.services.runtime_registry import CLIRegistry, ToolRegistry

if os.environ.get("FRAG_HOST_INSTALLED") != "1":
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def _plugin_ui(plugin):
    def ui() -> Response:
        plugin.ensure_current()
        return Response(plugin.ui_content, media_type="text/javascript")
    return ui


def create_app(
    *,
    context_source_root: str | Path | None = None,
    rag_service: RagService | None = None,
    harness_service: HarnessService | None = None,
    rag_index_path: str | Path | None = None,
    rag_source_root: str | Path | None = None,
    rag_eval_path: str | Path | None = None,
    plugin_root: str | Path = DEFAULT_PLUGIN_ROOT,
    runtime_path: str | Path | None = None,
    agent_host_enabled: bool | None = None,
    review_origin: str = "http://127.0.0.1:8787",
    workspace_root: Path | None = None,
    model_bridge=None,
    review_assets: Path | None = None,
    review_help: Path | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        source_service = ContextSourceService(
            context_source_root or Path(__file__).resolve().parents[2] / "local-sources",
            project_files=workspace_root is not None,
        )
        app.state.context_source_service = source_service
        app.state.harness_service = harness_service or HarnessService(source_service, plugins=plugins)
        app.state.rag_service = rag_service or create_rag_service(
            **({"index_path": rag_index_path} if rag_index_path is not None else {}),
            source_root=rag_source_root,
            eval_path=rag_eval_path,
        )
        app.state.rag_service.selected_source_service = source_service
        path = Path(runtime_path or os.environ.get("FRAG_RUNTIME_PATH") or Path(__file__).resolve().parents[2] / ".local-runtime/runtime.sqlite3")
        index_path = app.state.rag_service.repository.path
        if path.resolve() == index_path.resolve() or (path.exists() and index_path.exists() and path.samefile(index_path)):
            raise ValueError("Runtime storage must be separate from the RAG index.")
        if path.resolve().is_relative_to(app.state.rag_service.selected_cache_root.resolve()):
            raise ValueError("Runtime storage must be separate from selected RAG caches.")
        repository = RuntimeRepository(path)
        with repository.owner_lease():
            app.state.runtime = RuntimeService(repository)
            app.state.runtime.secret_values = tuple(set(configured_secrets(app.state.harness_service.settings) + configured_secrets(app.state.rag_service.settings)))
            app.state.runtime.memory = MemoryService(app.state.runtime)
            services = (("harness", app.state.harness_service), ("rag", app.state.rag_service))
            for kind, service in services:
                service.approvals.clear()
                service.pending_inference.clear()
                service.flow.runtime, service.flow.kind = app.state.runtime, kind
            app.state.harness_service.cli_registry = CLIRegistry()
            app.state.harness_service.tool_registry = ToolRegistry()
            app.state.kb_tools = KBTools(app.state.runtime, app.state.harness_service, app.state.rag_service)
            definition, execute = host_cli_binding(review_origin)
            app.state.harness_service.cli_registry.register(definition, execute)
            app.state.research = ResearchFlow(app.state.runtime, app.state.harness_service, app.state.rag_service, app.state.kb_tools)
            app.state.agent_host = AgentHost(app, review_origin,
                workspace=workspace_root.as_uri() if workspace_root else "file:///frag-workspace",
                bridge=model_bridge)
            try:
                yield
            finally:
                app.state.research.close()
                app.state.agent_host.pending.clear()
                for _, service in services:
                    service.approvals.clear()
                    service.pending_inference.clear()
                    service.flow.runtime = None
                app.state.runtime.close()

    app = FastAPI(title="FRAG-harness API", version="1.10.0", lifespan=lifespan)
    app.add_middleware(BodyLimitMiddleware)
    app.state.agent_host_enabled = agent_host_enabled if agent_host_enabled is not None else os.environ.get("FRAG_AGENT_HOST_ENABLED") == "1"
    app.state.project_name = workspace_root.name if workspace_root else "FRAG workspace"
    app.state.review_assets = review_assets or Path(__file__).resolve().parents[2] / "dist"
    app.state.review_help = review_help or Path(__file__).resolve().parents[2] / "src/agents/README.md"
    app.state.plugin_root = Path(plugin_root)
    app.state.plugin_hidden = set()
    app.state.plugin_management_lock = asyncio.Lock()

    @app.middleware("http")
    async def installed_boundary(request: Request, call_next):
        if workspace_root is not None:
            from frag_api.routers.agents import allowed
            if not allowed(request):
                return error_response(403, "LOCAL_ONLY", "This Host accepts loopback clients only.")
            origin = request.headers.get("origin")
            if origin and origin != review_origin:
                return error_response(403, "ORIGIN_REJECTED", "Use this Host's review page.")
            path = request.url.path
            if model_bridge and request.method == "POST" and (
                path in {"/api/harness/preview", "/api/harness/run", "/api/harness/inference/run",
                         "/api/rag/preview", "/api/rag/run", "/api/rag/inference/run", "/api/runtime/research/preview"}
                or path.endswith(("/research/preview", "/research/execute", "/resume/preview", "/reopen"))):
                return error_response(409, "NATIVE_SESSION_REQUIRED", "Prepare and approve stages in the native FRAG session.")
        response = await call_next(request)
        if workspace_root is not None:
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.middleware("http")
    async def hide_deactivated_plugin(request: Request, call_next):
        path = request.url.path
        plugin_id = None
        if path.startswith("/api/plugins/"):
            plugin_id = path.split("/", 4)[3]
        elif path.startswith("/plugins/"):
            plugin_id = path.split("/", 3)[2]
        if plugin_id is not None:
            installed = app.state.plugins.get(plugin_id)
            if installed is None or plugin_id in app.state.plugin_hidden:
                return error_response(404, "NOT_FOUND", "Endpoint was not found.")
            try:
                installed.ensure_current()
            except (PluginValidationError, OSError):
                app.state.plugins.pop(plugin_id, None)
                app.state.harness_service.plugins.pop(plugin_id, None)
                if plugin_id == "finance-core":
                    app.state.plugin = None
                    app.state.harness_service.plugin = None
                app.state.plugin_error = True
                return error_response(404, "NOT_FOUND", "Endpoint was not found.")
        return await call_next(request)
    plugins, plugin_errors = load_plugins(Path(plugin_root))
    app.state.plugins = plugins
    app.state.plugin = plugins.get("finance-core")
    app.state.plugin_error = bool(plugin_errors)
    app.include_router(health_router)
    app.include_router(sources_router)
    app.include_router(harness_router)
    app.include_router(rag_router)
    app.include_router(runtime_router)
    app.include_router(tools_router)
    app.include_router(research_router)
    app.include_router(memory_router)
    app.include_router(plugins_router)
    app.include_router(agents_router)
    assets = app.state.review_assets / "assets"
    if app.state.agent_host_enabled and assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="review-assets")
        if (assets.parent / "agents").is_dir():
            app.mount("/agents", StaticFiles(directory=assets.parent / "agents"), name="review-fonts-notices")
    for plugin in plugins.values():
        app.include_router(plugin.router)
        app.add_api_route(plugin.ui_url, _plugin_ui(plugin), methods=["GET"], include_in_schema=False)

    @app.exception_handler(RequestContractError)
    async def contract_error(_request: Request, error: RequestContractError) -> JSONResponse:
        return error_response(422, "INVALID_REQUEST", "The request does not match its contract.", error.issues)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, error: RequestValidationError) -> JSONResponse:
        if any(item.get("type") == "json_invalid" for item in error.errors()):
            return error_response(400, "MALFORMED_JSON", "Request body contains malformed JSON.")
        issues = [{"path": redact(issue_path(tuple(item.get("loc", ())))), "message": redact(str(item.get("msg", "Invalid value.")))}
                  for item in error.errors()]
        return error_response(422, "INVALID_REQUEST", "The request does not match its contract.", issues)

    @app.exception_handler(ResponseValidationError)
    async def response_error(_request: Request, _error: ResponseValidationError) -> JSONResponse:
        return error_response(500, "INVALID_SERVER_DATA", "The service returned invalid data.")

    failures = {
        HarnessSourceError: (422, "HARNESS_SOURCE_INVALID", "Selected evidence is unavailable or exceeds the budget."),
        RagIndexNotReadyError: (409, "RAG_INDEX_NOT_READY", "Build the demo index before searching."),
        RagIndexStaleError: (409, "RAG_INDEX_STALE", "The source changed; rebuild the index."),
        RagIndexBuildError: (500, "RAG_INDEX_BUILD_FAILED", "The index could not be built."),
        RagFingerprintError: (409, "CONTEXT_CHANGED", "The preview changed or its approval was already used."),
        RagNotReadyError: (503, "LLM_NOT_CONFIGURED", "Both model routes must be configured."),
        RagProviderError: (502, "LLM_PROVIDER_FAILED", "A model provider failed."),
        RagOutputError: (502, "INVALID_LLM_OUTPUT", "A model result failed validation."),
        PolicyRejectedError: (409, "POLICY_REJECTED", "Selected scope or blocking checklist does not permit this action."),
        RequestBudgetError: (422, "REQUEST_BUDGET_EXCEEDED", "The complete model request or cumulative run exceeds its budget."),
        RagRefusalError: (502, "LLM_REFUSED", "The model refused this request; a new preview and approval are required."),
        RagIncompleteError: (502, "LLM_INCOMPLETE", "The model result was incomplete; a new preview and approval are required."),
        RagOutcomeUnknownError: (502, "LLM_OUTCOME_UNKNOWN", "The external call outcome is unknown; it will not be resent automatically."),
        RuntimeNotFoundError: (404, "RUNTIME_NOT_FOUND", "The session or Run was not found."),
        RuntimeConflictError: (409, "RUNTIME_CONFLICT", "The saved Run state does not permit this action; inspect history and prepare a fresh request."),
    }
    for error_type, (status, code, message) in failures.items():
        async def handler(_request: Request, _error: Exception, s=status, c=code, m=message):
            return error_response(s, c, m)
        app.add_exception_handler(error_type, handler)

    @app.exception_handler(StarletteHttpException)
    async def http_error(_request: Request, error: StarletteHttpException) -> JSONResponse:
        if error.status_code == 405:
            return error_response(405, "METHOD_NOT_ALLOWED", "Method is not allowed.",
                                  headers={"Allow": error.headers.get("Allow", "") if error.headers else ""})
        if error.status_code == 404:
            return error_response(404, "NOT_FOUND", "Endpoint was not found.")
        return error_response(error.status_code, "HTTP_ERROR", "Request could not be completed.")

    @app.exception_handler(Exception)
    async def internal_error(_request: Request, _error: Exception) -> JSONResponse:
        return error_response(500, "INTERNAL_SERVER_ERROR", "The server could not complete the request.")

    return app


app = create_app()
