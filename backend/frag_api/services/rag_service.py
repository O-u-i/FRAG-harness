from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path

from frag_api.errors import (
    RagFingerprintError,
    RagIndexNotReadyError,
    RagIndexStaleError,
    RagNotReadyError,
    RagOutputError,
    RagProviderError,
    RequestContractError,
)
from frag_api.providers.llm import FakeLlmProvider, LlmProvider, LlmSettings, provider_for
from frag_api.repositories.rag_index_repository import (
    DEFAULT_RAG_INDEX_PATH,
    IndexChunk,
    IndexDocument,
    RagIndexRepository,
    SearchRow,
)
from frag_api.schemas.context_source import ParsedLocalFile
from frag_api.schemas.common import StageResult, TokenBudget
from frag_api.schemas.rag import (
    RagChunkResult,
    RagContextCompression,
    RagDatasetRequest,
    RagEvaluationCase,
    RagEvaluationGates,
    RagEvaluationReport,
    RagEvidence,
    RagGroundedAnswer,
    RagIndexStatus,
    RagPreview,
    RagQueryRequest,
    RagRetrievalMetrics,
    RagRun,
    RagRunRequest,
    RagSearchResponse,
)
from frag_api.services.context_source_service import ContextSourceError, ContextSourceService
from frag_api.services.approval import ApprovalRegistry
from frag_api.services.governed_context import (
    CONTEXT_OUTPUT_LIMIT,
    INFERENCE_OUTPUT_LIMIT,
    INPUT_BUDGET,
    RESERVED_PERCENT,
    estimated_tokens,
    fingerprint,
)

DATASET_ID = "synthetic-risk-review-v1"
SOURCE_FILE = "synthetic-risk-review.md"
SOURCE_ID = "synthetic-risk-review-source-v1"
DOCUMENT_ID = "rag-synthetic-risk-review-v1"
CHUNK_STRATEGY_VERSION = "markdown-section-v1"
STOP_WORDS = {
    "a", "an", "and", "are", "did", "do", "does", "how", "in", "is", "of",
    "on", "source", "the", "to", "was", "were", "what", "which",
}


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _match_expression(query: str) -> str:
    tokens = [token.casefold() for token in re.findall(r"[A-Za-z0-9]+", query)]
    selected = [token for token in tokens if token not in STOP_WORDS]
    if not selected:
        raise RequestContractError([{"path": "body.query", "message": "Query has no searchable terms."}])
    return " OR ".join(f'"{token}"' for token in dict.fromkeys(selected))


def _excerpt(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()[:240]


class RagService:
    def __init__(
        self,
        source_service: ContextSourceService,
        repository: RagIndexRepository,
        settings: LlmSettings,
        context_provider: LlmProvider | None = None,
        inference_provider: LlmProvider | None = None,
        eval_path: str | Path | None = None,
    ):
        self.source_service = source_service
        self.repository = repository
        self.settings = settings
        self.context_provider = context_provider or provider_for(settings.context)
        self.inference_provider = inference_provider or provider_for(settings.inference)
        self.eval_path = Path(eval_path) if eval_path else Path(source_service.root) / "eval-cases.json"
        self.approvals = ApprovalRegistry()

    def status(self) -> RagIndexStatus:
        source_hash = self._source_hash()
        snapshot = self.repository.snapshot()
        if snapshot.index_revision is None:
            state = "not_built"
        elif snapshot.source_hash != source_hash:
            state = "stale"
        else:
            state = "ready"
        return RagIndexStatus(
            datasetId=DATASET_ID,
            state=state,
            documentCount=snapshot.document_count,
            chunkCount=snapshot.chunk_count,
            indexRevision=snapshot.index_revision,
            sourceHash=snapshot.source_hash,
        )

    def rebuild(self, request: RagDatasetRequest) -> RagIndexStatus:
        parsed = self._parse_source()
        chunks = self._chunks_for(parsed)
        if not chunks:
            raise RagOutputError()
        revision = fingerprint({
            "datasetId": request.dataset_id,
            "sourceHash": parsed.source.sha256,
            "strategy": CHUNK_STRATEGY_VERSION,
            "chunks": [chunk.text_hash for chunk in chunks],
        })
        self.repository.rebuild(
            IndexDocument(
                document_id=DOCUMENT_ID,
                dataset_id=request.dataset_id,
                source_id=SOURCE_ID,
                source_hash=parsed.source.sha256 or "",
            ),
            chunks,
            revision,
        )
        return self.status()

    def search(self, request: RagQueryRequest) -> RagSearchResponse:
        status = self._require_ready()
        rows = self.repository.search(_match_expression(request.query), request.top_k)
        return self._search_response(request, status.index_revision or "", rows)

    def preview(self, request: RagQueryRequest, *, issue_approval: bool = True) -> RagPreview:
        search = self.search(request)
        rows = self.repository.search(_match_expression(request.query), request.top_k)
        evidence = [self._evidence(row) for row in rows]
        payload = {
            "datasetId": request.dataset_id,
            "query": request.query,
            "topK": request.top_k,
            "indexRevision": search.index_revision,
            "candidateEvidence": [item.model_dump(by_alias=True) for item in evidence],
        }
        estimate = estimated_tokens(payload)
        usable = INPUT_BUDGET * (100 - RESERVED_PERCENT) // 100
        if estimate > usable:
            raise RequestContractError([{"path": "body.topK", "message": "Retrieved evidence exceeds the Context budget."}])
        context_fingerprint = fingerprint({
            **payload,
            "providerRoute": {
                "context": [self.settings.context.provider, self.settings.context.model],
                "inference": [self.settings.inference.provider, self.settings.inference.model],
            },
        })
        warnings = [
            "This index contains only the bundled synthetic Markdown dataset.",
            "Search and Preview make no model call. Run requires one-time approval.",
            "FTS ranking is a keyword baseline, not proof of authority or factual correctness.",
        ]
        if not evidence:
            warnings.append("No matching chunks were retrieved; Run is unavailable.")
        return RagPreview(
            datasetId=request.dataset_id,
            query=request.query,
            topK=request.top_k,
            indexRevision=search.index_revision,
            retrievalResults=search.results,
            candidateEvidence=evidence,
            budget=TokenBudget(
                estimatedInputTokens=estimate,
                inputBudget=INPUT_BUDGET,
                reservedPercent=RESERVED_PERCENT,
                contextOutputLimit=CONTEXT_OUTPUT_LIMIT,
                inferenceOutputLimit=INFERENCE_OUTPUT_LIMIT,
            ),
            warnings=warnings,
            contextFingerprint=context_fingerprint,
            approvalToken=self.approvals.issue(context_fingerprint) if issue_approval else "",
        )

    def run(self, request: RagRunRequest) -> RagRun:
        query_request = RagQueryRequest.model_validate(
            request.model_dump(exclude={"context_fingerprint", "approval_token", "approved"})
        )
        preview = self.preview(query_request, issue_approval=False)
        if request.context_fingerprint != preview.context_fingerprint:
            raise RagFingerprintError()
        if not preview.candidate_evidence:
            raise RagOutputError()
        if not self.settings.context.ready or not self.settings.inference.ready:
            raise RagNotReadyError()
        if not self.approvals.consume(request.approval_token, preview.context_fingerprint):
            raise RagFingerprintError()
        preview.approval_token = request.approval_token
        try:
            context_call = self.context_provider.generate_rag_context(
                preview.candidate_evidence, CONTEXT_OUTPUT_LIMIT
            )
        except RagOutputError as error:
            raise RagOutputError() from error
        except RagProviderError as error:
            raise RagProviderError() from error
        compressed = context_call.output
        if not isinstance(compressed, RagContextCompression):
            raise RagOutputError()
        allowed = {item.chunk_id for item in preview.candidate_evidence}
        returned = {item.chunk_id for item in compressed.evidence}
        if returned != allowed or estimated_tokens(compressed.model_dump(by_alias=True)) > CONTEXT_OUTPUT_LIMIT:
            raise RagOutputError()
        try:
            inference_call = self.inference_provider.generate_rag_answer(
                compressed, request.query, INFERENCE_OUTPUT_LIMIT
            )
        except RagOutputError as error:
            raise RagOutputError() from error
        except RagProviderError as error:
            raise RagProviderError() from error
        result = inference_call.output
        if not isinstance(result, RagGroundedAnswer):
            raise RagOutputError()
        cited = {chunk_id for claim in result.claims for chunk_id in claim.chunk_ids}
        if not cited.issubset(returned) or not cited:
            raise RagOutputError()
        return RagRun(
            preview=preview,
            compressedContext=compressed,
            result=result,
            contextStage=StageResult(
                provider=self.settings.context.provider,
                model=self.settings.context.model,
                usage=context_call.usage,
            ),
            inferenceStage=StageResult(
                provider=self.settings.inference.provider,
                model=self.settings.inference.model,
                usage=inference_call.usage,
            ),
        )

    def evaluate(self, request: RagDatasetRequest) -> RagEvaluationReport:
        self._require_ready()
        try:
            suite = json.loads(self.eval_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise RagOutputError() from error
        if suite.get("datasetId") != request.dataset_id:
            raise RagOutputError()
        results: list[RagEvaluationCase] = []
        context_hits = 0
        valid_citations = 0
        expected_citations = 0
        reciprocal_ranks: list[float] = []
        ndcg_values: list[float] = []
        fake = FakeLlmProvider()
        for case in suite.get("cases", []):
            query = RagQueryRequest(datasetId=request.dataset_id, query=case["query"], topK=3)
            preview = self.preview(query, issue_approval=False)
            actual = [item.chunk_id for item in preview.retrieval_results]
            expected = case["expectedChunkId"]
            rank = actual.index(expected) + 1 if expected in actual else None
            results.append(RagEvaluationCase(
                id=case["id"], query=case["query"], expectedChunkId=expected,
                actualChunkIds=actual, expectedRank=rank, passed=rank == 1,
            ))
            reciprocal_ranks.append(1 / rank if rank and rank <= 3 else 0)
            ndcg_values.append(1 / math.log2(rank + 1) if rank and rank <= 3 else 0)
            context_ids = {item.chunk_id for item in preview.candidate_evidence}
            context_hits += int(expected in context_ids)
            compressed = fake.generate_rag_context(preview.candidate_evidence, CONTEXT_OUTPUT_LIMIT).output
            if not isinstance(compressed, RagContextCompression):
                continue
            answer = fake.generate_rag_answer(compressed, case["query"], INFERENCE_OUTPUT_LIMIT).output
            if not isinstance(answer, RagGroundedAnswer):
                continue
            cited = {chunk_id for claim in answer.claims for chunk_id in claim.chunk_ids}
            valid_citations += int(cited.issubset(context_ids) and bool(cited))
            expected_citations += int(expected in cited)
        count = len(results)
        if count != 3:
            raise RagOutputError()
        metrics = RagRetrievalMetrics(
            hitAt1=sum(item.expected_rank == 1 for item in results) / count,
            recallAt3=sum(item.expected_rank is not None and item.expected_rank <= 3 for item in results) / count,
            mrrAt3=sum(reciprocal_ranks) / count,
            ndcgAt3=sum(ndcg_values) / count,
        )
        gates = RagEvaluationGates(
            contextCoverage=context_hits / count,
            citationValidity=valid_citations / count,
            expectedCitationCoverage=expected_citations / count,
            staleResidualCount=self.repository.stale_residual_count(
                self._chunks_for(self._parse_source())
            ),
        )
        passed = all(value == 1.0 for value in (
            metrics.hit_at_1, metrics.recall_at_3, metrics.mrr_at_3, metrics.ndcg_at_3,
            gates.context_coverage, gates.citation_validity, gates.expected_citation_coverage,
        )) and gates.stale_residual_count == 0
        return RagEvaluationReport(
            suiteVersion=suite["suiteVersion"], datasetId=request.dataset_id,
            cases=results, metrics=metrics, gates=gates, status="PASS" if passed else "FAIL",
        )

    def _source_hash(self) -> str:
        return self._parse_source().source.sha256 or ""

    def _parse_source(self) -> ParsedLocalFile:
        try:
            return self.source_service.parse(SOURCE_FILE)
        except (ContextSourceError, OSError, ValueError) as error:
            raise RagOutputError() from error

    @staticmethod
    def _chunks_for(parsed: ParsedLocalFile) -> list[IndexChunk]:
        return [
            IndexChunk(
                chunk_id=f"{DOCUMENT_ID}-c{index:03d}",
                document_id=DOCUMENT_ID,
                source_id=SOURCE_ID,
                locator_id=section.locator.id,
                locator_label=section.locator.label,
                ordinal=index,
                text=section.text,
                text_hash=_sha256(section.text),
            )
            for index, section in enumerate(parsed.sections, start=1)
        ]

    def _require_ready(self) -> RagIndexStatus:
        status = self.status()
        if status.state == "not_built":
            raise RagIndexNotReadyError()
        if status.state == "stale":
            raise RagIndexStaleError()
        return status

    @staticmethod
    def _evidence(row: SearchRow) -> RagEvidence:
        return RagEvidence(
            chunkId=row.chunk_id, documentId=row.document_id, sourceId=row.source_id,
            locatorId=row.locator_id, locatorLabel=row.locator_label, text=row.text,
        )

    @staticmethod
    def _search_response(
        request: RagQueryRequest, revision: str, rows: list[SearchRow]
    ) -> RagSearchResponse:
        return RagSearchResponse(
            datasetId=request.dataset_id,
            query=request.query,
            topK=request.top_k,
            indexRevision=revision,
            results=[
                RagChunkResult(
                    rank=index,
                    bm25Score=row.bm25_score,
                    chunkId=row.chunk_id,
                    documentId=row.document_id,
                    sourceId=row.source_id,
                    locatorId=row.locator_id,
                    locatorLabel=row.locator_label,
                    excerpt=_excerpt(row.text),
                )
                for index, row in enumerate(rows, start=1)
            ],
        )


def create_rag_service(
    *, index_path: str | Path = DEFAULT_RAG_INDEX_PATH,
    source_root: str | Path | None = None,
    eval_path: str | Path | None = None,
) -> RagService:
    root = Path(source_root) if source_root else Path(__file__).resolve().parents[3] / "shared" / "demo" / "rag"
    settings = LlmSettings.from_environment()
    return RagService(
        ContextSourceService(root),
        RagIndexRepository(index_path),
        settings,
        eval_path=eval_path,
    )
