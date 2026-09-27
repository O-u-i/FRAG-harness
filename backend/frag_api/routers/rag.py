from typing import Annotated

from fastapi import APIRouter, Body, Depends, Request

from frag_api.http import reject_body, reject_query
from frag_api.schemas.rag import (
    RagDatasetRequest,
    RagContextRun,
    InferenceRunRequest,
    RagEvaluationReport,
    RagIndexStatus,
    RagPreview,
    RagQueryRequest,
    RagRun,
    RagRunRequest,
    RagSearchResponse,
)

router = APIRouter(prefix="/api/rag")


def service(request: Request):
    return request.app.state.rag_service


@router.get(
    "/status",
    response_model=RagIndexStatus,
    response_model_by_alias=True,
    dependencies=[Depends(reject_query), Depends(reject_body)],
)
def status(request: Request) -> RagIndexStatus:
    return service(request).status()


@router.post(
    "/index/rebuild",
    response_model=RagIndexStatus,
    response_model_by_alias=True,
    dependencies=[Depends(reject_query)],
)
def rebuild(
    request: Request, input_data: Annotated[RagDatasetRequest, Body()]
) -> RagIndexStatus:
    return service(request).rebuild(input_data)


@router.post(
    "/search",
    response_model=RagSearchResponse,
    response_model_by_alias=True,
    dependencies=[Depends(reject_query)],
)
def search(
    request: Request, input_data: Annotated[RagQueryRequest, Body()]
) -> RagSearchResponse:
    return service(request).search(input_data)


@router.post(
    "/preview",
    response_model=RagPreview,
    response_model_by_alias=True,
    dependencies=[Depends(reject_query)],
)
def preview(
    request: Request, input_data: Annotated[RagQueryRequest, Body()]
) -> RagPreview:
    return service(request).preview(input_data)


@router.post(
    "/run",
    response_model=RagContextRun,
    response_model_by_alias=True,
    dependencies=[Depends(reject_query)],
)
def run(
    request: Request, input_data: Annotated[RagRunRequest, Body()]
) -> RagContextRun:
    return service(request).run(input_data)


@router.post(
    "/inference/run",
    response_model=RagRun,
    response_model_by_alias=True,
    dependencies=[Depends(reject_query)],
)
def run_inference(
    request: Request, input_data: Annotated[InferenceRunRequest, Body()]
) -> RagRun:
    return service(request).run_inference(input_data)


@router.post(
    "/evaluations/run",
    response_model=RagEvaluationReport,
    response_model_by_alias=True,
    dependencies=[Depends(reject_query)],
)
def evaluate(
    request: Request, input_data: Annotated[RagDatasetRequest, Body()]
) -> RagEvaluationReport:
    return service(request).evaluate(input_data)
