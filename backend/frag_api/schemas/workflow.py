"""Allowlisted recommendation diagnostics. Never a draft or evidence ToolRun."""
from typing import Annotated, Literal

from pydantic import ConfigDict, Field

from frag_api.schemas.context_source import ApiModel

OpaqueId = Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
EvidenceId = Annotated[str, Field(pattern=r"^[0-9a-f]{24}$")]
Reason = Literal[
    "CHECKS_PASSED", "CARRIER_UNAVAILABLE", "FEATURE_DISABLED", "EVIDENCE_MISSING",
    "EVIDENCE_STALE", "PLAN_MISSING", "CONSTRAINTS_MISSING", "FINANCIAL_FOUNDATION_MISSING",
    "REQUIRED_EVIDENCE_INCOMPLETE", "NUMBERS_CHECK_FAILED", "CONSTRAINTS_CHECK_FAILED",
    "REASONING_CHECK_FAILED", "SUITABILITY_CHECK_FAILED", "CHECK_UNKNOWN", "CHECK_EXCEPTION",
    "RESULT_CHANGED", "CONTEXT_CHANGED", "CANCELLED", "INTERRUPTED_UNKNOWN",
    "DEADLINE_EXCEEDED", "TOKEN_LIMIT", "COST_LIMIT", "MODEL_MISMATCH",
    "USAGE_UNKNOWN", "USAGE_EXCEEDED_RESERVATION", "REQUESTS_PENDING",
    "REMEDIATION_EXHAUSTED", "REPEATED_FAILURE", "PERSISTENCE_FAILED", "STATE_CONFLICT",
]


class SafeModel(ApiModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, frozen=True)


class EvidenceReference(SafeModel):
    run_id: OpaqueId = Field(alias="runId")
    result_digest: Digest = Field(alias="resultDigest")
    required_evidence_ids: tuple[EvidenceId, ...] = Field(alias="requiredEvidenceIds", min_length=1, max_length=10)


class SyntheticContext(SafeModel):
    """Synthetic assertions only; not a complete plan/financial-source contract."""
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=10)
    plan_revision: Digest | None = Field(default=None, alias="planRevision")
    constraints_revision: Digest | None = Field(default=None, alias="constraintsRevision")
    financial_foundation_complete: bool = Field(default=False, alias="financialFoundationComplete", strict=True)


class CheckResult(SafeModel):
    evidence: Literal["passed", "failed", "unknown"]
    numbers: Literal["passed", "failed", "unknown"]
    constraints: Literal["passed", "failed", "unknown"]
    reasoning: Literal["passed", "failed", "unknown"]
    suitability: Literal["passed", "failed", "unknown"]


class BudgetSnapshot(SafeModel):
    input_tokens: int = Field(alias="inputTokens", ge=0, strict=True)
    output_tokens: int = Field(alias="outputTokens", ge=0, strict=True)
    liability_micro_cny: int = Field(alias="liabilityMicroCny", ge=0, strict=True)
    pending_requests: int = Field(alias="pendingRequests", ge=0, strict=True)
    usage_unknown: bool = Field(alias="usageUnknown", strict=True)
    attempts: int = Field(ge=1, le=3, strict=True)
    remediation_rounds: int = Field(alias="remediationRounds", ge=0, le=2, strict=True)


class WorkflowReceipt(SafeModel):
    id: OpaqueId
    kind: Literal["recommendation_workflow"] = "recommendation_workflow"
    mode: Literal["synthetic"] = "synthetic"
    rule_version: Literal["recommendation-synthetic-v1"] = Field(default="recommendation-synthetic-v1", alias="ruleVersion")
    revision: int = Field(ge=1, strict=True)
    created_at: str = Field(alias="createdAt", pattern=r"^\d{4}-\d{2}-\d{2}T[0-9:.]+\+00:00$")
    updated_at: str = Field(alias="updatedAt", pattern=r"^\d{4}-\d{2}-\d{2}T[0-9:.]+\+00:00$")
    stage: Literal["evidence", "drafting", "checking", "remediation", "finished"]
    status: Literal["active", "checked", "refused", "cancelled", "interrupted"]
    reason_code: Reason | None = Field(default=None, alias="reasonCode")
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=10)
    plan_revision: Digest | None = Field(default=None, alias="planRevision")
    constraints_revision: Digest | None = Field(default=None, alias="constraintsRevision")
    budget: BudgetSnapshot
