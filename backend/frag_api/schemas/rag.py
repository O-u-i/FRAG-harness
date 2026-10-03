from __future__ import annotations

from typing import Literal

from pydantic import Field

from frag_api.schemas.common import ApiModel, ExplicitApproval, StageResult, TokenBudget
from frag_api.schemas.governance import PreparedCall, SourceBinding, TaskContract

RagDatasetId = Literal["synthetic-risk-review-v1"]
RagIndexState = Literal["not_built", "ready", "stale"]


class RagDatasetRequest(ApiModel):
    dataset_id: RagDatasetId = Field(alias="datasetId")


class RagQueryRequest(RagDatasetRequest):
    query: str = Field(min_length=3, max_length=500)
    top_k: int = Field(default=3, alias="topK", ge=1, le=10)
    task: TaskContract = Field(default_factory=TaskContract)


class RagRunRequest(RagQueryRequest, ExplicitApproval):
    context_fingerprint: str = Field(alias="contextFingerprint", min_length=64, max_length=64)
    approval_token: str = Field(alias="approvalToken", min_length=32)
    approved: Literal[True]


class InferenceRunRequest(ExplicitApproval):
    context_fingerprint: str = Field(alias="contextFingerprint", min_length=64, max_length=64)
    inference_fingerprint: str = Field(alias="inferenceFingerprint", min_length=64, max_length=64)
    approval_token: str = Field(alias="approvalToken", min_length=32)
    approved: Literal[True]


class InferencePreview(ApiModel):
    provider: str
    model: str
    instructions: str
    input: str
    max_output_tokens: int = Field(alias="maxOutputTokens")
    inference_fingerprint: str = Field(alias="inferenceFingerprint")
    approval_token: str = Field(alias="approvalToken")
    prepared_call: PreparedCall = Field(alias="preparedCall")


class RagIndexStatus(ApiModel):
    dataset_id: RagDatasetId = Field(alias="datasetId")
    schema_version: Literal[2] = Field(default=2, alias="schemaVersion")
    chunk_strategy_version: Literal["markdown-hierarchy-v2"] = Field(
        default="markdown-hierarchy-v2", alias="chunkStrategyVersion"
    )
    state: RagIndexState
    document_count: int = Field(alias="documentCount", ge=0)
    chunk_count: int = Field(alias="chunkCount", ge=0)
    index_revision: str | None = Field(default=None, alias="indexRevision")
    source_hash: str | None = Field(default=None, alias="sourceHash")


class RagChunkResult(ApiModel):
    rank: int = Field(ge=1)
    bm25_score: float = Field(alias="bm25Score")
    chunk_id: str = Field(alias="chunkId")
    parent_id: str = Field(alias="parentId")
    evidence_id: str | None = Field(default=None, alias="evidenceId")
    document_id: str = Field(alias="documentId")
    source_id: str = Field(alias="sourceId")
    locator_id: str = Field(alias="locatorId")
    locator_label: str = Field(alias="locatorLabel")
    excerpt: str


class RagSearchResponse(ApiModel):
    dataset_id: RagDatasetId = Field(alias="datasetId")
    query: str
    top_k: int = Field(alias="topK")
    index_revision: str = Field(alias="indexRevision", min_length=64, max_length=64)
    results: list[RagChunkResult]


class RagEvidence(ApiModel):
    evidence_id: str = Field(alias="evidenceId", min_length=1)
    document_id: str = Field(alias="documentId", min_length=1)
    source_id: str = Field(alias="sourceId", min_length=1)
    locator_id: str = Field(alias="locatorId", min_length=1)
    locator_label: str = Field(alias="locatorLabel", min_length=1)
    text: str = Field(min_length=1)


class RagPreview(ApiModel):
    dataset_id: RagDatasetId = Field(alias="datasetId")
    query: str
    top_k: int = Field(alias="topK")
    index_revision: str = Field(alias="indexRevision")
    retrieval_results: list[RagChunkResult] = Field(alias="retrievalResults")
    candidate_evidence: list[RagEvidence] = Field(alias="candidateEvidence")
    instructions: str
    input: str
    budget: TokenBudget
    warnings: list[str]
    context_fingerprint: str = Field(alias="contextFingerprint", min_length=64, max_length=64)
    approval_token: str = Field(alias="approvalToken")
    prepared_call: PreparedCall = Field(alias="preparedCall")
    source_bindings: tuple[SourceBinding, ...] = Field(alias="sourceBindings")
    task: TaskContract
    can_approve: bool = Field(alias="canApprove")


class RagCompressedEvidence(ApiModel):
    evidence_id: str = Field(alias="evidenceId", min_length=1)
    summary: str = Field(min_length=1)
    preserved_facts: list[str] = Field(alias="preservedFacts")
    uncertainty: list[str]


class RagContextCompression(ApiModel):
    evidence: list[RagCompressedEvidence]
    missing_information: list[str] = Field(alias="missingInformation")


class RagClaim(ApiModel):
    text: str = Field(min_length=1)
    evidence_ids: list[str] = Field(alias="evidenceIds", min_length=1)


class RagGroundedAnswer(ApiModel):
    answer: str = Field(min_length=1)
    claims: list[RagClaim] = Field(min_length=1)
    missing_information: list[str] = Field(alias="missingInformation")
    disclaimer: str = Field(min_length=1)


class RagRun(ApiModel):
    preview: RagPreview
    compressed_context: RagContextCompression = Field(alias="compressedContext")
    result: RagGroundedAnswer
    context_stage: StageResult = Field(alias="contextStage")
    inference_stage: StageResult = Field(alias="inferenceStage")


class RagContextRun(ApiModel):
    preview: RagPreview
    compressed_context: RagContextCompression = Field(alias="compressedContext")
    context_stage: StageResult = Field(alias="contextStage")
    inference_preview: InferencePreview = Field(alias="inferencePreview")


class RagEvaluationCase(ApiModel):
    id: str
    query: str
    expected_chunk_id: str = Field(alias="expectedChunkId")
    actual_chunk_ids: list[str] = Field(alias="actualChunkIds")
    expected_rank: int | None = Field(alias="expectedRank")
    passed: bool


class RagRetrievalMetrics(ApiModel):
    hit_at_1: float = Field(alias="hitAt1", ge=0, le=1)
    recall_at_3: float = Field(alias="recallAt3", ge=0, le=1)
    mrr_at_3: float = Field(alias="mrrAt3", ge=0, le=1)
    ndcg_at_3: float = Field(alias="ndcgAt3", ge=0, le=1)


class RagEvaluationGates(ApiModel):
    context_coverage: float = Field(alias="contextCoverage", ge=0, le=1)
    citation_validity: float = Field(alias="citationValidity", ge=0, le=1)
    expected_citation_coverage: float = Field(alias="expectedCitationCoverage", ge=0, le=1)
    stale_residual_count: int = Field(alias="staleResidualCount", ge=0)


class RagEvaluationReport(ApiModel):
    suite_version: str = Field(alias="suiteVersion")
    dataset_id: RagDatasetId = Field(alias="datasetId")
    cases: list[RagEvaluationCase]
    metrics: RagRetrievalMetrics
    gates: RagEvaluationGates
    status: Literal["PASS", "FAIL"]
