from typing import Annotated
import re

from fastapi import APIRouter, Body, Depends, Request

from frag_api.errors import RequestContractError
from frag_api.http import reject_body, reject_query
from frag_api.schemas.context_source import (
    LocalFileInspectRequest,
    LocalFileInspectResponse,
    LocalFileSource,
)
from frag_api.services.context_source_service import ContextSourceError
from frag_api.services.runtime_policy import redact

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
        parsed = service(request).parse(input_data.relative_path)
        secrets = request.app.state.runtime.redaction_secrets
        return LocalFileInspectResponse(
            source=parsed.source,
            locators=[section.locator.model_copy(update={
                "label": redact(section.locator.label, secrets),
                "excerpt": re.sub(r"\s+", " ", redact(section.text, secrets)).strip()[:240],
            }) for section in parsed.sections],
            warnings=[redact(warning, secrets) for warning in parsed.warnings],
        )
    except (ContextSourceError, OSError, ValueError) as error:
        raise RequestContractError([
            {"path": "body.relativePath", "message": str(error)}
        ]) from error
