"""Private loopback API for the extension; not a standalone browser application."""
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
import hmac
from uuid import uuid4
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from frag_api import errors
from frag_api.fc_connection import configured_reader, prepare_configuration, validate_selection, ensure_bundled_reader
from frag_api.request_spec import strict_json
from frag_api.repositories.tool_store import ToolStore
from frag_api.repositories.workflow_store import WorkflowStore
from frag_api.schemas import memory as m
from frag_api.schemas.native import SourceProfile, SearchInput, ReadInput, FcInput, CompleteInput, ToolRun, RunLookupInput, PlanConfirmationInput
from frag_api.services.context_source_service import ContextSourceError
from frag_api.services.evidence_tools import EvidenceTools
from frag_api.services.runtime_policy import redact_value

VERSION = "1.14.0"
ERROR_CODES = {
    errors.PolicyRejectedError: (403, "POLICY_REJECTED"),
    errors.RuntimeConflictError: (409, "REVISION_CONFLICT"),
    errors.RuntimeNotFoundError: (404, "NOT_FOUND"),
    errors.RagIndexNotReadyError: (409, "INDEX_NOT_BUILT"),
    errors.RagIndexStaleError: (409, "INDEX_STALE_REFRESH_REQUIRED"),
    errors.RagIndexBuildError: (409, "INDEX_INVALID_REBUILD_REQUIRED"),
    errors.PluginValidationError: (409, "FC_ARTIFACT_OR_CONFIG_INVALID"),
    ContextSourceError: (422, "SOURCE_UNREADABLE"),
    ValidationError: (422, "INVALID_INPUT"),
    ValueError: (422, "INVALID_INPUT"),
}

def error_reply(error):
    status, code = ERROR_CODES.get(type(error), (500, "LOCAL_OPERATION_FAILED"))
    return JSONResponse({"error": {"code": code}}, status_code=status)

def create_app(state: Path, secret: str, *, installation: Path | None = None):
    if len(secret) < 32:
        raise ValueError("An ephemeral extension token is required.")
    store = ToolStore(state / "runtime.sqlite3")
    try:
        if installation is not None:
            # Obtain the project's sole-owner lease before changing reader files.
            ensure_bundled_reader(installation, state)
        try:
            profile = store.profile('finance-core')
        except errors.RuntimeNotFoundError:
            profile = None
        fc, fc_secrets = configured_reader(state, profile)
        fc_state = ("available" if any(fc_secrets) else "connection_required") if fc else "not_installed_or_disabled"
    except (errors.PluginValidationError, OSError, ValueError):
        fc, fc_secrets, fc_state = None, (), "connection_required"
    tools = EvidenceTools(store, state / "rag/native", fc)
    tools.redaction_secrets += fc_secrets
    workflows = WorkflowStore(store)
    @asynccontextmanager
    async def lifespan(_):
        try:
            yield
        finally:
            store.close()
    app = FastAPI(title="FRAG Evidence Tools", version=VERSION, lifespan=lifespan,
        docs_url=None, redoc_url=None, openapi_url=None)
    app.state.tools = tools
    app.state.workflows = workflows
    @app.middleware("http")
    async def private_api(request: Request, call_next):
        if request.headers.get("origin") or not hmac.compare_digest(request.headers.get("authorization", ""), "Bearer " + secret):
            return JSONResponse({"error": {"code": "PRIVATE_EXTENSION_API"}}, status_code=403)
        body = bytearray()
        async for part in request.stream():
            body.extend(part)
            if len(body) > 64 * 1024:
                return JSONResponse({"error": {"code": "INPUT_TOO_LARGE"}}, status_code=413)
        request._body = bytes(body)
        try:
            return await call_next(request)
        except Exception as error:
            return error_reply(error)
    @app.post("/api/tools/{name}")
    async def invoke(name: str, request: Request):
        body = strict_json(await request.body())
        if name == "complete":
            complete = CompleteInput.model_validate(body)
            try:
                return tools.complete(complete)
            except Exception as error:
                run = store.get(complete.run_id)
                if run.status == "prepared":
                    store.save(run.model_copy(update={"status": "failed", "pack": None,
                        "error_code": ERROR_CODES.get(type(error), (500, "LOCAL_OPERATION_FAILED"))[1]}))
                raise
        schemas = {"frag_search": SearchInput, "frag_read": ReadInput, "frag_fc_read": FcInput}
        methods = {"frag_search": tools.search, "frag_read": tools.read, "frag_fc_read": tools.fc_read}
        if name not in schemas:
            raise errors.RuntimeNotFoundError()
        value = schemas[name].model_validate(body)
        try:
            return methods[name](value)
        except Exception as error:
            store.save(ToolRun(id=uuid4().hex, tool=name, input=redact_value(body, tools.redaction_secrets),
                createdAt=datetime.now(timezone.utc).isoformat(), status="failed",
                errorCode=ERROR_CODES.get(type(error), (500, "LOCAL_OPERATION_FAILED"))[1]))
            raise
    @app.post("/api/manage/{action}")
    async def manage(action: str, request: Request):
        nonlocal fc_state
        body = strict_json(await request.body())
        if not isinstance(body, dict):
            raise ValueError()
        if action == "overview" and not body:
            memory = tools.memory.records()
            with store.connection() as db:
                records = [{**item.model_dump(by_alias=True), "legacyReadOnly": not bool(db.execute("SELECT 1 FROM tool_runs WHERE id=?", (item.provenance_run_id,)).fetchone())} for item in memory]
            return {"version": VERSION, "sources": store.profiles(), "runs": store.runs(),
                "memory": records, "fcState": fc_state, "workflowReceipts": workflows.receipts(),
                "recommendations": {"available": False, "reasonCode": "CARRIER_UNAVAILABLE"}}
        if action == 'fc-connection-prepare' and not body:
            return prepare_configuration(state)
        if action == 'fc-connection-check' and not body:
            # A changed/failed connection never inherits the previous authorization.
            # Invalidate pending deliveries before inspecting the new credentials.
            try:
                previous = store.profile('finance-core')
            except errors.RuntimeNotFoundError:
                previous = None
            if previous is not None:
                store.save_profile(previous.model_copy(update={'enabled': False, 'fc_selection': None}))
            tools.fc, fc_state = None, 'connection_required'
            candidate, secrets = configured_reader(state, require_file=True)
            if candidate is None:
                raise errors.PluginValidationError()
            options = candidate.connection_options()
            tools.fc, fc_state = candidate, 'connected_selection_required'
            tools.redaction_secrets += secrets
            return options
        if action == "run-get":
            return store.get(RunLookupInput.model_validate(body).run_id)
        if action == "plan-confirm":
            return tools.confirm_plan(PlanConfirmationInput.model_validate(body))
        if action == "source-save":
            profile = SourceProfile.model_validate(body)
            candidate = None
            if profile.kind == "local":
                from frag_api.services.source_index import SourceIndex
                SourceIndex(profile, tools.index_root)
            elif profile.enabled and (profile.fc_selection is not None or (state / 'fc.env').exists()):
                if profile.fc_selection is None:
                    raise errors.PolicyRejectedError()
                candidate, secrets = configured_reader(state, profile, require_file=True)
                if candidate is None:
                    raise errors.PluginValidationError()
                validate_selection(candidate, profile)
            saved = store.save_profile(profile)
            if candidate is not None:
                tools.fc, fc_state = candidate, 'available'
                tools.redaction_secrets += secrets
            return saved
        if action in {"source-status", "source-build"} and set(body) == {"sourceId"} and isinstance(body["sourceId"], str):
            index = tools.index(body["sourceId"])
            return index.build() if action == "source-build" else index.status()
        if action == "memory-candidate":
            return tools.memory.candidate(m.MemoryCandidateRequest.model_validate(body))
        if action == "memory-conflict":
            return tools.memory.conflict(m.MemoryConflictRequest.model_validate(body))
        if action == "memory-resolve":
            return tools.memory.conflict(m.MemoryConflictResolutionRequest.model_validate(body), resolve=True)
        if action == "memory-recommend":
            value = m.MemoryRecommendRequest.model_validate(body)
            return tools.memory.recommend(value.query, tools.memory.sources(store.get(value.run_id)))
        if action.startswith("memory-") and isinstance(body.get("memoryId"), str):
            memory_id = body.pop("memoryId")
            if action == "memory-versions" and not body:
                return tools.memory.versions(memory_id)
            if action == "memory-revise":
                return tools.memory.revise(memory_id, m.MemoryRevisionRequest.model_validate(body))
            if action == "memory-promote":
                return tools.memory.promote(memory_id, m.MemoryPromotionRequest.model_validate(body))
            if action == "memory-retire":
                return tools.memory.retire(memory_id, m.MemoryVersionRequest.model_validate(body))
        raise errors.PolicyRejectedError()
    @app.get("/api/health")
    def health():
        return {"service": "frag-harness", "serviceVersion": VERSION}
    return app
