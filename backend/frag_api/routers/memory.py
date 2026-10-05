"""Explicit human operations on curated application memory."""
from typing import Annotated

from fastapi import APIRouter, Body, Depends, Request

from frag_api.http import reject_body, reject_query
from frag_api.schemas.memory import (
    MemoryCandidateRequest, MemoryConflictRequest, MemoryConflictResolutionRequest,
    MemoryPromotionRequest, MemoryRecommendRequest, MemoryRecord, MemoryRevisionRequest,
    MemoryVersionRequest,
)

router = APIRouter(prefix="/api/memory")
read_only = [Depends(reject_body), Depends(reject_query)]
write_only = [Depends(reject_query)]


@router.get("", response_model=list[MemoryRecord], dependencies=read_only)
def records(request: Request):
    return request.app.state.runtime.memory.records()


@router.get("/{memory_id}/versions", response_model=list[MemoryRecord], dependencies=read_only)
def versions(request: Request, memory_id: str):
    return request.app.state.runtime.memory.versions(memory_id)


@router.post("/candidates", response_model=MemoryRecord, dependencies=write_only)
def candidate(request: Request, body: Annotated[MemoryCandidateRequest, Body()]):
    return request.app.state.runtime.memory.candidate(body)


@router.post("/{memory_id}/revisions", response_model=MemoryRecord, dependencies=write_only)
def revise(request: Request, memory_id: str, body: Annotated[MemoryRevisionRequest, Body()]):
    return request.app.state.runtime.memory.revise(memory_id, body)


@router.post("/{memory_id}/promote", response_model=MemoryRecord, dependencies=write_only)
def promote(request: Request, memory_id: str, body: Annotated[MemoryPromotionRequest, Body()]):
    return request.app.state.runtime.memory.promote(memory_id, body)


@router.post("/{memory_id}/retire", response_model=MemoryRecord, dependencies=write_only)
def retire(request: Request, memory_id: str, body: Annotated[MemoryVersionRequest, Body()]):
    return request.app.state.runtime.memory.retire(memory_id, body)


@router.post("/conflicts", response_model=list[MemoryRecord], dependencies=write_only)
def conflict(request: Request, body: Annotated[MemoryConflictRequest, Body()]):
    return request.app.state.runtime.memory.conflict(body)


@router.post("/resolve-conflict", response_model=list[MemoryRecord], dependencies=write_only)
def resolve_conflict(request: Request, body: Annotated[MemoryConflictResolutionRequest, Body()]):
    return request.app.state.runtime.memory.conflict(body, resolve=True)


@router.post("/recommend", response_model=list[MemoryRecord], dependencies=write_only)
def recommend(request: Request, body: Annotated[MemoryRecommendRequest, Body()]):
    service = request.app.state.runtime.memory
    report = request.app.state.runtime.repository.get(body.run_id)
    return service.recommend(body.query, service.sources(report))
