from typing import Annotated

from fastapi import APIRouter, Body, Depends, Request

from frag_api.http import reject_body, reject_query
from frag_api.schemas.common import HarnessConfig
from frag_api.schemas.governance import CapabilityCatalog
from frag_api.schemas.harness import HarnessContextRun, HarnessPreview, HarnessRequest, HarnessRun, HarnessRunRequest
from frag_api.schemas.rag import InferenceRunRequest

router = APIRouter(prefix="/api/harness")


@router.get("/capabilities", response_model=CapabilityCatalog, response_model_by_alias=True,
            dependencies=[Depends(reject_query), Depends(reject_body)])
def capabilities(request: Request) -> CapabilityCatalog:
    return request.app.state.harness_service.capabilities()


@router.get("/config", response_model=HarnessConfig, response_model_by_alias=True,
            dependencies=[Depends(reject_query), Depends(reject_body)])
def config(request: Request) -> HarnessConfig:
    return request.app.state.harness_service.config()


@router.post("/preview", response_model=HarnessPreview, response_model_by_alias=True,
             dependencies=[Depends(reject_query)])
def preview(request: Request, input_data: Annotated[HarnessRequest, Body()]) -> HarnessPreview:
    return request.app.state.harness_service.preview(input_data)


@router.post("/run", response_model=HarnessContextRun, response_model_by_alias=True,
             dependencies=[Depends(reject_query)])
def run(request: Request, input_data: Annotated[HarnessRunRequest, Body()]) -> HarnessContextRun:
    return request.app.state.harness_service.run(input_data)


@router.post("/inference/run", response_model=HarnessRun, response_model_by_alias=True,
             dependencies=[Depends(reject_query)])
def run_inference(request: Request, input_data: Annotated[InferenceRunRequest, Body()]) -> HarnessRun:
    return request.app.state.harness_service.run_inference(input_data)
