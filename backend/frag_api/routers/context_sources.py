from typing import Annotated

from fastapi import APIRouter, Body, Depends, Request

from frag_api.errors import RequestContractError
from frag_api.http import reject_body, reject_query
from frag_api.schemas.context_source import (
    LocalFileInspectRequest,
    LocalFileInspectResponse,
    LocalFileSource,
)
from frag_api.services.context_source_service import ContextSourceError

router = APIRouter()


def service(request: Request):
    return request.app.state.context_source_service


@router.get(
    "/api/context-sources/files",
    response_model=list[LocalFileSource],
    response_model_by_alias=True,
    dependencies=[Depends(reject_query), Depends(reject_body)],
)
def files(request: Request) -> list[LocalFileSource]:
    return service(request).list_files()


@router.post(
    "/api/context-sources/files/inspect",
    response_model=LocalFileInspectResponse,
    response_model_by_alias=True,
    dependencies=[Depends(reject_query)],
)
def inspect_file(
    request: Request, input_data: Annotated[LocalFileInspectRequest, Body()]
) -> LocalFileInspectResponse:
    try:
        return service(request).inspect(input_data.relative_path)
    except (ContextSourceError, OSError, ValueError) as error:
        raise RequestContractError([
            {"path": "body.relativePath", "message": str(error)}
        ]) from error
