"""Research previews dispatch exactly one approved model stage."""
from typing import Annotated
from fastapi import APIRouter, Body, Depends, Request
from pydantic import ValidationError
from frag_api.errors import RequestContractError
from frag_api.http import reject_query
from frag_api.schemas.harness import HarnessRequest
from frag_api.schemas.rag import RagQueryRequest
from frag_api.schemas.research import ResearchExecute, ResearchPreview, ResearchStart
from frag_api.schemas.runtime import ReselectionRequest, RunReport

router = APIRouter(prefix="/api/runtime")


def source_for(kind, value):
    try:
        return (HarnessRequest if kind == "harness" else RagQueryRequest).model_validate(value)
    except ValidationError as error:
        raise RequestContractError([{"path":"sourceRequest", "message":"Provide a valid explicit source selection."}]) from error


def runner(request, kind):
    service = request.app.state.harness_service if kind == "harness" else request.app.state.rag_service
    return service.flow.loops.get("research").runner


@router.post("/research/preview", response_model=ResearchPreview, dependencies=[Depends(reject_query)])
def start(request: Request, body: Annotated[ResearchStart, Body()]):
    return runner(request, body.kind).start(body.kind, source_for(body.kind, body.source_request))


@router.post("/runs/{run_id}/research/preview", response_model=ResearchPreview, dependencies=[Depends(reject_query)])
def preview(request: Request, run_id: str, body: Annotated[ReselectionRequest, Body()]):
    report = request.app.state.runtime.repository.get(run_id)
    return runner(request, report.run.kind).preview(run_id, source_for(report.run.kind, body.source_request))


@router.post("/runs/{run_id}/research/execute", response_model=RunReport, dependencies=[Depends(reject_query)])
def execute(request: Request, run_id: str, body: Annotated[ResearchExecute, Body()]):
    report = request.app.state.runtime.repository.get(run_id)
    return runner(request, report.run.kind).execute(run_id, source_for(report.run.kind, body.source_request),
                                            body.fingerprint, body.approval_token)
