from typing import Annotated
from fastapi import APIRouter, Body, Depends, Request
from frag_api.http import reject_query
from frag_api.schemas.tools import ToolCallRecord, ToolExecutionRequest

router = APIRouter(prefix="/api/runtime/runs")


@router.post("/{run_id}/tools/execute", response_model=ToolCallRecord, response_model_by_alias=True,
             dependencies=[Depends(reject_query)])
def execute(request: Request, run_id: str, body: Annotated[ToolExecutionRequest, Body()]):
    return request.app.state.kb_tools.execute(run_id, body.source_request, body.call)
