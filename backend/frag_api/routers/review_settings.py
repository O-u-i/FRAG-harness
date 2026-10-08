"""Review-only defaults APIs use the same origin/loopback guards as approvals."""
from typing import Annotated
from fastapi import APIRouter, Body, Depends, Request
from frag_api.http import reject_body
from frag_api.routers.agents import guards
from frag_api.errors import RequestContractError
from pydantic import ValidationError
from frag_api.schemas.review_settings import ApplicationUpdate, ProjectUpdate, ConversationUpdate, SettingsPrepare

router = APIRouter(prefix="/api/agents", dependencies=guards)


@router.get("/settings", dependencies=[Depends(reject_body)])
def settings(request: Request):
    return request.app.state.review_settings.view()


@router.put("/settings/application")
def application(request: Request, body: Annotated[ApplicationUpdate, Body()]):
    return request.app.state.review_settings.put_application(body)


@router.put("/settings/project")
def project(request: Request, body: Annotated[ProjectUpdate, Body()]):
    return request.app.state.review_settings.put_project(body)


@router.get("/sessions/{session_id}/settings", dependencies=[Depends(reject_body)])
def conversation(request: Request, session_id: str):
    return request.app.state.review_settings.view(session_id)


@router.put("/sessions/{session_id}/settings")
def update_conversation(request: Request, session_id: str, body: Annotated[ConversationUpdate, Body()]):
    return request.app.state.review_settings.put_conversation(session_id, body)


@router.post("/sessions/{session_id}/prepare-settings")
def prepare(request: Request, session_id: str, body: Annotated[SettingsPrepare, Body()]):
    try:
        return request.app.state.review_settings.prepare(session_id, body)
    except ValidationError as error:
        raise RequestContractError([{"path": "settings", "message": "Select valid evidence for the current native task."}]) from error
