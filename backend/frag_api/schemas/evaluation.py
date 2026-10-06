"""Versioned synthetic Gold and deterministic evaluation report contracts."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from frag_api.schemas.common import ApiModel
from frag_api.schemas.governance import SourceBinding
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


class GoldResearchStep(ApiModel):
    """Bounded fixture instructions, never network or filesystem authority."""
    action: Literal["read", "search", "finish", "unknown-tool", "scope-escape", "malformed-call", "duplicate-call"]
    query: str = Field(default="synthetic", min_length=1, max_length=500)
    count: int = Field(default=1, ge=1, le=6, strict=True)
    missing_information: list[str] = Field(default_factory=list, alias="missingInformation", max_length=10)


class GoldResearchCase(ApiModel):
    id: str = Field(min_length=1, max_length=80)
    query: str = Field(min_length=3, max_length=500)
    steps: list[GoldResearchStep] = Field(min_length=1, max_length=3)
    expected_status: Literal["awaiting_context", "exhausted", "error"] = Field(alias="expectedStatus")
    expected_tool_names: list[Literal["kb.read", "kb.search"]] = Field(default_factory=list, alias="expectedToolNames", max_length=6)
    expected_tool_statuses: list[Literal["completed", "failed"]] = Field(default_factory=list, alias="expectedToolStatuses", max_length=6)
    required_missing_information: list[str] = Field(default_factory=list, alias="requiredMissingInformation", max_length=10)
    restart_after_turn: int | None = Field(default=None, alias="restartAfterTurn", ge=1, le=2, strict=True)
    tool_failure: Literal["TOOL_TIMEOUT", "TOOL_OUTPUT_LIMIT"] | None = Field(default=None, alias="toolFailure")

    @model_validator(mode="after")
    def paired_expectations(self):
        if self.expected_tool_statuses and len(self.expected_tool_statuses) != len(self.expected_tool_names):
            raise ValueError("Research tool statuses must pair with expected tool names.")
        if self.restart_after_turn is not None and self.restart_after_turn >= len(self.steps):
            raise ValueError("Research restart must precede a scripted continuation.")
        return self


class GoldSuite(ApiModel):
    schema_version: Literal[1] = Field(alias="schemaVersion")
    suite_id: str = Field(alias="suiteId", min_length=1, max_length=100)
    suite_version: str = Field(alias="suiteVersion", pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    source: GoldSource
    cases: list[GoldCase] = Field(default_factory=list, max_length=100)
    research_cases: list[GoldResearchCase] = Field(default_factory=list, alias="researchCases", max_length=30)

    @model_validator(mode="after")
    def unique_cases(self):
        combined = self.cases + self.research_cases
        if not combined or len({case.id for case in combined}) != len(combined):
            raise ValueError("Gold case identifiers must be unique.")
        return self


class CapturedGold(ApiModel):
    """Human-written expectations bound to one explicit selected-source capture."""
    schema_version: Literal[1] = Field(alias="schemaVersion")
    suite_id: str = Field(alias="suiteId", min_length=1, max_length=100)
    suite_version: str = Field(alias="suiteVersion", pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    run_id: str | None = Field(default=None, alias="runId", min_length=1, max_length=64)
    goal: str = Field(min_length=3, max_length=500)
    source_bindings: tuple[SourceBinding, ...] = Field(alias="sourceBindings", min_length=1, max_length=10)
    expected_evidence_ids: list[str] = Field(alias="expectedEvidenceIds", min_length=1, max_length=1000)
    facts: list[GoldFact] = Field(min_length=1, max_length=20)
    required_missing_information: list[str] = Field(default_factory=list, alias="requiredMissingInformation", max_length=20)

    @model_validator(mode="after")
    def unique_bound_expectations(self):
        for values in (self.expected_evidence_ids, [fact.id for fact in self.facts]):
            if len(set(values)) != len(values) or any(not item for item in values):
                raise ValueError("Captured Gold identifiers must be nonempty and unique.")
        allowed = {key for binding in self.source_bindings for key in binding.evidence_ids}
        if not set(self.expected_evidence_ids).issubset(allowed):
            raise ValueError("Captured Gold evidence must belong to its explicit source bindings.")
        if any(not item.strip() or len(item) > 500 for item in self.required_missing_information):
            raise ValueError("Missing-information expectations must contain bounded literal text.")
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
    secondary_observed_failures: list[str] = Field(default_factory=list, alias="secondaryObservedFailures")
    causal_attribution: Literal["UNDETERMINED"] = Field(default="UNDETERMINED", alias="causalAttribution")
    unknown_causes: list[str] = Field(default_factory=lambda: [
        "Unique root cause and causal contribution were not determined from this observed execution."], alias="unknownCauses")
    checks: list[EvalCheck]
    trace: dict[str, Any] = Field(default_factory=dict)


class EvalReport(ApiModel):
    schema_version: Literal[1] = Field(default=1, alias="schemaVersion")
    runner_version: Literal["1.1.0", "1.2.0"] = Field(default="1.1.0", alias="runnerVersion")
    scorer_version: Literal["literal-facts-v1"] = Field(default="literal-facts-v1", alias="scorerVersion")
    host_version: str = Field(alias="hostVersion")
    suite_id: str | None = Field(default=None, alias="suiteId")
    suite_version: str | None = Field(default=None, alias="suiteVersion")
    source_revision: str | None = Field(default=None, alias="sourceRevision")
    source_hash: str | None = Field(default=None, alias="sourceHash")
    provider: Literal["offline-scripted-fake", "captured-artifacts"] = "offline-scripted-fake"
    status: EvalStatus
    semantic_review_status: Literal["UNDETERMINED"] = Field(default="UNDETERMINED", alias="semanticReviewStatus")
    trajectory_status: EvalStatus = Field(default="NOT_RUN", alias="trajectoryStatus")
    counts: dict[EvalStatus, int]
    cases: list[EvalCaseReport]
    errors: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=lambda: [
        "PASS covers executed deterministic synthetic checks only; no real model or LLM judge was used.",
        "Literal facts are declared fixture checks, not proof of semantic support or factual truth.",
        "The earliest observed deviation does not establish a unique cause.",
        "Research trajectory covers declared synthetic paths only when explicitly requested; real semantic review is undetermined.",
    ])
