"""Durable runtime history and human review; no executable approval is persisted."""
from __future__ import annotations

from typing import Any, Literal
from pydantic import Field
from frag_api.schemas.common import ApiModel, ProviderUsage
from frag_api.schemas.governance import PreparedCall, SourceBinding, TaskContract
from frag_api.schemas.rag import RagContextCompression, RagEvidence, RagGroundedAnswer

RunStatus = Literal["ready_context", "awaiting_inference", "awaiting_review", "paused", "accepted", "rejected", "error", "outcome_unknown"]
Outcome = Literal["PASS", "FAIL", "ERROR", "NOT_RUN", "UNDETERMINED"]


class RunLink(ApiModel):
    session_id: str | None = Field(default=None, alias="sessionId", max_length=64)
    parent_run_id: str | None = Field(default=None, alias="parentRunId", max_length=64)


class SessionCreate(ApiModel):
    title: str = Field(default="Evidence review", min_length=1, max_length=200)


class SessionRecord(ApiModel):
    id: str
    title: str
    created_at: str = Field(alias="createdAt")


class RunRecord(ApiModel):
    id: str
    session_id: str = Field(alias="sessionId")
    parent_run_id: str | None = Field(alias="parentRunId")
    kind: Literal["harness", "rag"]
    status: RunStatus
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")
    version: int = Field(ge=1)
    active_call_id: str | None = Field(alias="activeCallId")


class SelectionSnapshot(ApiModel):
    goal: str
    source_bindings: tuple[SourceBinding, ...] = Field(alias="sourceBindings")
    candidate_evidence: list[RagEvidence] = Field(alias="candidateEvidence")
    task: TaskContract
    input: dict[str, Any]


class AttemptRecord(ApiModel):
    id: str
    stage: Literal["context", "inference"]
    status: Literal["prepared", "dispatching", "completed", "failed", "outcome_unknown"]
    prepared_call: PreparedCall = Field(alias="preparedCall")
    created_at: str = Field(alias="createdAt")
    finished_at: str | None = Field(default=None, alias="finishedAt")
    usage: ProviderUsage | None = None
    output: dict[str, Any] | None = None
    output_digest: str | None = Field(default=None, alias="outputDigest", min_length=64, max_length=64)
    error_code: str | None = Field(default=None, alias="errorCode")
    structural_validation: Outcome = Field(default="NOT_RUN", alias="structuralValidation")


class ReviewRequest(ApiModel):
    target: str = Field(default="model", min_length=1, max_length=64)
    decision: Literal["accepted", "rejected", "paused"]
    checklist: TaskContract
    note: str = Field(default="", max_length=4000)


class ReviewRecord(ReviewRequest):
    id: str
    created_at: str = Field(alias="createdAt")


class RevisionRequest(ApiModel):
    result: RagGroundedAnswer
    note: str = Field(default="", max_length=4000)


class RevisionRecord(RevisionRequest):
    content_digest: str | None = Field(default=None, alias="contentDigest", min_length=64, max_length=64)
    id: str
    created_at: str = Field(alias="createdAt")
    review_status: Literal["pending", "accepted", "rejected", "paused"] = Field(default="pending", alias="reviewStatus")


class RunReport(ApiModel):
    snapshot_digest: str | None = Field(default=None, alias="snapshotDigest", min_length=64, max_length=64)
    schema_version: Literal[1] = Field(default=1, alias="schemaVersion")
    session: SessionRecord
    run: RunRecord
    selection: SelectionSnapshot
    requests: list[AttemptRecord]
    context: RagContextCompression | None
    model_output: RagGroundedAnswer | None = Field(alias="modelOutput")
    reviews: list[ReviewRecord]
    revisions: list[RevisionRecord]
    consumed_tokens: int = Field(alias="consumedTokens", ge=0)
    run_token_limit: int = Field(alias="runTokenLimit", gt=0)
    structural_validation: Outcome = Field(alias="structuralValidation")
    semantic_review: Outcome = Field(alias="semanticReview")
    limitations: list[str]


class ReselectionRequest(ApiModel):
    source_request: dict[str, Any] = Field(alias="sourceRequest")


class RecoveryPreview(ApiModel):
    run_id: str = Field(alias="runId")
    kind: Literal["harness", "rag"]
    stage: Literal["context", "inference"]
    context_fingerprint: str = Field(alias="contextFingerprint")
    preview: dict[str, Any]
