from typing import Annotated
from fastapi import APIRouter, Body, Depends, Query, Request
from fastapi.responses import Response
from pydantic import ValidationError
from frag_api.errors import RequestContractError, RuntimeConflictError
from frag_api.http import reject_body, reject_query
from frag_api.schemas.harness import HarnessRequest
from frag_api.schemas.rag import RagQueryRequest
from frag_api.schemas.runtime import (
    RecoveryPreview, ReselectionRequest, ReviewRequest, RevisionRequest,
    RunRecord, RunReport, SessionCreate, SessionRecord,
)
from frag_api.services.runtime_report import report_markdown

router = APIRouter(prefix="/api/runtime")
read_only = [Depends(reject_body), Depends(reject_query)]


@router.get("/sessions", response_model=list[SessionRecord], dependencies=read_only)
def sessions(request: Request):
    return request.app.state.runtime.repository.sessions()


@router.post("/sessions", response_model=SessionRecord, dependencies=[Depends(reject_query)])
def create_session(request: Request, body: Annotated[SessionCreate, Body()]):
    return request.app.state.runtime.create_session(body.title)


@router.get("/runs", response_model=list[RunRecord], dependencies=[Depends(reject_body)])
def runs(request: Request, session_id: Annotated[str | None, Query(alias="sessionId", max_length=64)] = None):
    if set(request.query_params) - {"sessionId"} or len(request.query_params.getlist("sessionId")) > 1:
        raise RequestContractError([{"path":"query", "message":"Only one sessionId filter is supported."}])
    return request.app.state.runtime.repository.runs(session_id)


@router.get("/runs/{run_id}", response_model=RunReport, dependencies=read_only)
@router.get("/runs/{run_id}/report.json", response_model=RunReport, dependencies=read_only)
def report(request: Request, run_id: str):
    return request.app.state.runtime.repository.get(run_id)


@router.get("/runs/{run_id}/report.md", dependencies=read_only)
def markdown(request: Request, run_id: str):
    value = request.app.state.runtime.repository.get(run_id)
    return Response(report_markdown(value), media_type="text/markdown", headers={"Content-Disposition":f'attachment; filename="run-{value.run.id}.md"'})


@router.post("/runs/{run_id}/review", response_model=RunReport, dependencies=[Depends(reject_query)])
def review(request: Request, run_id: str, body: Annotated[ReviewRequest, Body()]):
    return request.app.state.runtime.review(run_id, body)


@router.post("/runs/{run_id}/revisions", response_model=RunReport, dependencies=[Depends(reject_query)])
def revision(request: Request, run_id: str, body: Annotated[RevisionRequest, Body()]):
    return request.app.state.runtime.revise(run_id, body)


def reselect(request, run_id, body):
    saved = request.app.state.runtime.repository.get(run_id)
    service = request.app.state.harness_service if saved.run.kind == "harness" else request.app.state.rag_service
    model = HarnessRequest if saved.run.kind == "harness" else RagQueryRequest
    try:
        selected = model.model_validate(body.source_request)
    except ValidationError as error:
        raise RequestContractError([{"path":"sourceRequest", "message":"Provide an explicit valid source selection for this Run kind."}]) from error
    return saved, service, selected


@router.post("/runs/{run_id}/resume/preview", response_model=RecoveryPreview, dependencies=[Depends(reject_query)])
def resume_preview(request: Request, run_id: str, body: Annotated[ReselectionRequest, Body()]):
    saved, service, selected = reselect(request, run_id, body)
    if ((selected.session_id and selected.session_id != saved.run.session_id)
            or (selected.parent_run_id and selected.parent_run_id != saved.run.parent_run_id)):
        raise RuntimeConflictError()
    stage, preview, fingerprint = service.flow.resume_preview(run_id, selected)
    return RecoveryPreview(runId=run_id, kind=saved.run.kind, stage=stage, contextFingerprint=fingerprint, preview=preview.model_dump(by_alias=True))


@router.post("/runs/{run_id}/reopen", response_model=RecoveryPreview, dependencies=[Depends(reject_query)])
def reopen(request: Request, run_id: str, body: Annotated[ReselectionRequest, Body()]):
    saved, service, selected = reselect(request, run_id, body)
    selected.session_id, selected.parent_run_id = saved.run.session_id, saved.run.id
    preview = service.preview(selected)
    return RecoveryPreview(runId=preview.run_id, kind=saved.run.kind, stage="context", contextFingerprint=preview.context_fingerprint, preview=preview.model_dump(by_alias=True))
