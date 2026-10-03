"""Versioned synthetic Gold and deterministic evaluation report contracts."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from frag_api.schemas.common import ApiModel
from frag_api.schemas.rag import RagContextCompression, RagGroundedAnswer

EvalStatus = Literal["PASS", "FAIL", "ERROR", "NOT_RUN", "UNDETERMINED"]
EvalCategory = Literal["retrieval", "evidence", "tool", "model_quality", "host_enforcement", "semantic_review", "trajectory"]


class GoldSource(ApiModel):
    kind: Literal["synthetic"]
    revision: str = Field(min_length=1, max_length=80)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    markdown: str = Field(min_length=1, max_length=20_000)


class GoldFact(ApiModel):
    id: str = Field(min_length=1, max_length=80)
    kind: Literal["fact", "negation", "constraint", "date", "unit"]
    alternatives: list[str] = Field(min_length=1, max_length=10)
    forbidden: list[str] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def nonempty_patterns(self):
        patterns = self.alternatives + self.forbidden
        if any(not text.strip() or len(text) > 500 for text in patterns):
            raise ValueError("Fact patterns must contain bounded literal text.")
        return self


class GoldCase(ApiModel):
    id: str = Field(min_length=1, max_length=80)
    query: str = Field(min_length=3, max_length=500)
    top_k: int = Field(default=3, alias="topK", ge=1, le=10)
    mode: Literal["retrieval", "full"] = "full"
    evaluate_tools: bool = Field(default=False, alias="evaluateTools", strict=True)
    expected_chunk_ids: list[str] = Field(alias="expectedChunkIds", min_length=1)
    expected_evidence_ids: list[str] = Field(alias="expectedEvidenceIds", min_length=1)
    facts: list[GoldFact] = Field(min_length=1, max_length=20)
    required_missing_information: list[str] = Field(default_factory=list, alias="requiredMissingInformation")
    sample_context: RagContextCompression | None = Field(default=None, alias="sampleContext")
    sample_answer: RagGroundedAnswer | None = Field(default=None, alias="sampleAnswer")

    @model_validator(mode="after")
    def unique_expectations(self):
        for values in (self.expected_chunk_ids, self.expected_evidence_ids, [fact.id for fact in self.facts]):
            if len(set(values)) != len(values) or any(not value for value in values):
                raise ValueError("Gold identifiers must be nonempty and unique.")
        return self


class GoldSuite(ApiModel):
    schema_version: Literal[1] = Field(alias="schemaVersion")
    suite_id: str = Field(alias="suiteId", min_length=1, max_length=100)
    suite_version: str = Field(alias="suiteVersion", pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    source: GoldSource
    cases: list[GoldCase] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_cases(self):
        if len({case.id for case in self.cases}) != len(self.cases):
            raise ValueError("Gold case identifiers must be unique.")
        return self


class EvalCheck(ApiModel):
    id: str
    stage: str
    category: EvalCategory
    status: EvalStatus
    detail: str
    observed: dict[str, Any] = Field(default_factory=dict)


class EvalCaseReport(ApiModel):
    id: str
    query: str
    status: EvalStatus
    host_enforcement_status: EvalStatus = Field(alias="hostEnforcementStatus")
    model_quality_status: EvalStatus = Field(alias="modelQualityStatus")
    earliest_observed_deviation: str | None = Field(default=None, alias="earliestObservedDeviation")
    checks: list[EvalCheck]
    trace: dict[str, Any] = Field(default_factory=dict)


class EvalReport(ApiModel):
    schema_version: Literal[1] = Field(default=1, alias="schemaVersion")
    runner_version: Literal["1.0.0"] = Field(default="1.0.0", alias="runnerVersion")
    scorer_version: Literal["literal-facts-v1"] = Field(default="literal-facts-v1", alias="scorerVersion")
    host_version: str = Field(alias="hostVersion")
    suite_id: str | None = Field(default=None, alias="suiteId")
    suite_version: str | None = Field(default=None, alias="suiteVersion")
    source_revision: str | None = Field(default=None, alias="sourceRevision")
    source_hash: str | None = Field(default=None, alias="sourceHash")
    provider: Literal["offline-scripted-fake"] = "offline-scripted-fake"
    status: EvalStatus
    semantic_review_status: Literal["UNDETERMINED"] = Field(default="UNDETERMINED", alias="semanticReviewStatus")
    trajectory_status: Literal["NOT_RUN"] = Field(default="NOT_RUN", alias="trajectoryStatus")
    counts: dict[EvalStatus, int]
    cases: list[EvalCaseReport]
    errors: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=lambda: [
        "PASS covers executed deterministic synthetic checks only; no real model or LLM judge was used.",
        "Literal facts are declared fixture checks, not proof of semantic support or factual truth.",
        "The earliest observed deviation does not establish a unique cause.",
        "Research trajectory is not implemented in Phase 3; real semantic review is undetermined.",
    ])
