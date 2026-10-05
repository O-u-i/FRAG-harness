from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path

from frag_api.errors import (
    RagIndexNotReadyError,
    RagIndexStaleError,
    RagOutputError,
    RequestContractError,
)
from frag_api.providers.llm import FakeLlmProvider, LlmProvider, LlmSettings, provider_for
from frag_api.repositories.rag_index_repository import (
    DEFAULT_RAG_INDEX_PATH,
    IndexChunk,
    IndexDocument,
    IndexParent,
    RagIndexRepository,
    SearchRow,
)
from frag_api.schemas.governance import QualityFact, SourceAssessment, SourceBinding, SourceIdentity
from frag_api.schemas.rag import (
    RagChunkResult,
    RagContextRun,
    RagContextCompression,
    RagDatasetRequest,
    RagEvaluationCase,
    RagEvaluationGates,
    RagEvaluationReport,
    RagEvidence,
    RagGroundedAnswer,
    InferenceRunRequest,
    RagIndexStatus,
    RagPreview,
    RagQueryRequest,
    RagRetrievalMetrics,
    RagRun,
    RagRunRequest,
    RagSearchResponse,
)
from frag_api.services.context_source_service import ContextSourceError, ContextSourceService
from frag_api.services.rag_markdown import sections_from_markdown, children_for
from frag_api.services.approval import ApprovalRegistry, PendingInferenceRegistry
from frag_api.services.governed_flow import GovernedFlow
from frag_api.services.model_preview import context_preview_fields
from frag_api.services.runtime_policy import configured_secrets, redact
from frag_api.services.governed_context import (
    CONTEXT_OUTPUT_LIMIT,
    INFERENCE_OUTPUT_LIMIT,
    INPUT_BUDGET,
    RESERVED_PERCENT,
)
from frag_api.request_spec import estimated_tokens, fingerprint

DATASET_ID = "synthetic-risk-review-v1"
SOURCE_FILE = "synthetic-risk-review.md"
SOURCE_ID = "synthetic-risk-review-source-v1"
DOCUMENT_ID = "rag-synthetic-risk-review-v1"
CHUNK_STRATEGY_VERSION = "markdown-hierarchy-v2"
STOP_WORDS = {
    "a", "an", "and", "are", "did", "do", "does", "how", "in", "is", "of",
    "on", "source", "the", "to", "was", "were", "what", "which",
}


def _match_expression(query: str) -> str:
    tokens = [token.casefold() for token in re.findall(r"[A-Za-z0-9]+", query)]
    chinese: list[str] = []
    for sequence in re.findall(r"[\u3400-\u9fff]+", query):
        chinese.extend(sequence[i:i + 2] for i in range(len(sequence) - 1))
        if len(sequence) == 1:
            chinese.append(sequence)
    selected = [token for token in tokens if token not in STOP_WORDS]
    if not selected and not chinese:
        raise RequestContractError([{"path": "body.query", "message": "Query has no searchable terms."}])
    english = " OR ".join(f'"{token}"' for token in dict.fromkeys(selected))
    cjk = " AND ".join(f'"{token}"' for token in dict.fromkeys(chinese))
    return " OR ".join(f"({part})" for part in (english, cjk) if part)


def _search_text(text: str) -> str:
    bigrams = [sequence[i:i + 2] for sequence in re.findall(r"[\u3400-\u9fff]+", text)
               for i in range(len(sequence) - 1)]
    return text + "\n" + " ".join(bigrams)


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
        self.pending_inference = PendingInferenceRegistry()
        self.flow = GovernedFlow(
            prepare_preview=self._prepare_preview, goal_for=lambda request: redact(request.query, configured_secrets(self.settings)),
            settings=self.settings, context_provider=lambda: self.context_provider,
            inference_provider=lambda: self.inference_provider, approvals=self.approvals,
            pending_inference=self.pending_inference,
        )

    def status(self) -> RagIndexStatus:
        source_hash = self._source_hash()
        snapshot = self.repository.snapshot()
        if snapshot.index_revision is None:
            state = "not_built"
        elif snapshot.schema_version != "2" or snapshot.source_hash != source_hash:
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
        source_text, source_hash = self._parse_source()
        parents, chunks = self._chunks_for(source_text)
        if not chunks:
            raise RagOutputError()
        revision = fingerprint({
            "datasetId": request.dataset_id,
            "sourceHash": source_hash,
            "strategy": CHUNK_STRATEGY_VERSION,
            "chunks": [chunk.text_hash for chunk in chunks],
        })
        self.repository.rebuild(
            IndexDocument(
                document_id=DOCUMENT_ID,
                dataset_id=request.dataset_id,
                source_id=SOURCE_ID,
                source_hash=source_hash,
            ),
            chunks,
            parents,
            revision,
        )
        return self.status()

    def search(self, request: RagQueryRequest) -> RagSearchResponse:
        status = self._require_ready()
        snapshot, rows, _parents = self.repository.search_snapshot(_match_expression(request.query), request.top_k)
        if snapshot.index_revision != status.index_revision or snapshot.source_hash != self._source_hash():
            raise RagIndexStaleError()
        return self._search_response(request, status.index_revision or "", rows)

    def preview(self, request: RagQueryRequest, *, issue_approval: bool = True) -> RagPreview:
        return self.flow.loops.get("fixed").runner.preview(request, issue_approval=issue_approval)

    def _prepare_preview(self, request: RagQueryRequest) -> RagPreview:
        status = self._require_ready()
        snapshot, rows, parents = self.repository.search_snapshot(_match_expression(request.query), request.top_k)
        if snapshot.index_revision != status.index_revision or snapshot.source_hash != self._source_hash():
            raise RagIndexStaleError()
        search = self._search_response(request, snapshot.index_revision or "", rows)
        evidence, matched_ids = self._expanded_evidence(rows, parents)
        for result in search.results:
            result.evidence_id = matched_ids.get(result.chunk_id)
        sources = (SourceBinding(
            identity=SourceIdentity(kind="synthetic", namespace=fingerprint(str(self.source_service.root)), resourceId=DOCUMENT_ID),
            revision=search.index_revision, parserVersion=CHUNK_STRATEGY_VERSION,
            locatorIds=tuple(dict.fromkeys(item.locator_id for item in evidence)),
            evidenceIds=tuple(item.evidence_id for item in evidence),
            assessment=SourceAssessment(provenance=QualityFact(status="known", detail="Bundled synthetic dataset and selected index revision.")),
        ),) if evidence else ()
        warnings = [
            "This index contains only the bundled synthetic Markdown dataset.",
            "Search and Preview make no model call. Run requires one-time approval.",
            "FTS ranking is a keyword baseline, not proof of authority or factual correctness.",
            "Input tokens estimate the complete request, including instructions and output schema.",
        ]
        if not evidence:
            warnings.append("No matching chunks were retrieved; Run is unavailable.")
        return RagPreview(
            datasetId=request.dataset_id,
            query=redact(request.query, configured_secrets(self.settings) + (self.flow.runtime.redaction_secrets if self.flow.runtime else ())),
            topK=request.top_k,
            indexRevision=search.index_revision,
            retrievalResults=search.results,
            **context_preview_fields(settings=self.settings, evidence=evidence, goal=request.query, task=request.task,
                                     sources=sources, selection_hash=fingerprint(request.model_dump(by_alias=True)),
                                     redaction_secrets=self.flow.runtime.redaction_secrets if self.flow.runtime else (),
                                     selected_memory=request.selected_memory,
                                     memory_service=self.flow.runtime.memory if self.flow.runtime else None,
                                     loop_definition=self.flow.loops.get("fixed").definition.model_dump(by_alias=True)),
            warnings=warnings,
        )

    def run(self, request: RagRunRequest) -> RagContextRun:
        query_request = RagQueryRequest.model_validate(
            request.model_dump(exclude={"context_fingerprint", "approval_token", "approved"})
        )
        state = self.flow.loops.get("fixed").runner.run_context(query_request, request)
        return RagContextRun(
            preview=state["preview"], compressedContext=state["compressed"],
            contextStage=state["context_stage"], inferencePreview=state["inference_preview"],
        )

    def run_inference(self, request: InferenceRunRequest) -> RagRun:
        state = self.flow.loops.get("fixed").runner.run_inference(request)
        return RagRun(
            preview=state["preview"], compressedContext=state["compressed"],
            result=state["answer"], contextStage=state["context_stage"],
            inferenceStage=state["inference_stage"],
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
            context_ids = {item.evidence_id for item in preview.candidate_evidence}
            expected_evidence = next((item.evidence_id for item in preview.retrieval_results
                                      if item.chunk_id == expected), None)
            context_hits += int(expected_evidence in context_ids)
            compressed = fake.generate_rag_context(preview.candidate_evidence, CONTEXT_OUTPUT_LIMIT).output
            if not isinstance(compressed, RagContextCompression):
                continue
            answer = fake.generate_rag_answer(compressed, case["query"], INFERENCE_OUTPUT_LIMIT).output
            if not isinstance(answer, RagGroundedAnswer):
                continue
            cited = {evidence_id for claim in answer.claims for evidence_id in claim.evidence_ids}
            valid_citations += int(cited.issubset(context_ids) and bool(cited))
            expected_citations += int(expected_evidence in cited)
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
                self._chunks_for(self._parse_source()[0])[1]
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
        return self._parse_source()[1]

    def _parse_source(self) -> tuple[str, str]:
        try:
            metadata, data = self.source_service.read_snapshot(SOURCE_FILE)
            return data.decode("utf-8-sig"), metadata.sha256 or ""
        except (ContextSourceError, OSError, UnicodeError, ValueError) as error:
            raise RagOutputError() from error

    @staticmethod
    def _chunks_for(source: str) -> tuple[list[IndexParent], list[IndexChunk]]:
        parents: list[IndexParent] = []
        chunks: list[IndexChunk] = []
        for section in sections_from_markdown(source):
            parent_id = f"{DOCUMENT_ID}-{section.parent_id}"
            parents.append(IndexParent(parent_id, DOCUMENT_ID, section.locator_id,
                                       section.label, section.title_path, section.text))
            for child in children_for(section):
                number = len(chunks) + 1
                chunks.append(IndexChunk(
                    chunk_id=f"{DOCUMENT_ID}-c{number:03d}", document_id=DOCUMENT_ID,
                    source_id=SOURCE_ID, locator_id=section.locator_id,
                    locator_label=section.title_path, ordinal=number,
                    text=child.text, text_hash=hashlib.sha256(child.text.encode("utf-8")).hexdigest(), parent_id=parent_id,
                    search_text=_search_text(child.text),
                ))
        return parents, chunks

    def _require_ready(self) -> RagIndexStatus:
        status = self.status()
        if status.state == "not_built":
            raise RagIndexNotReadyError()
        if status.state == "stale":
            raise RagIndexStaleError()
        return status

    def _expanded_evidence(self, rows: list[SearchRow], parents: dict[str, IndexParent] | None = None) -> tuple[list[RagEvidence], dict[str, str]]:
        selected: dict[str, SearchRow] = {}
        for row in rows:
            selected.setdefault(row.parent_id, row)
        limit = 1400
        while True:
            evidence: list[RagEvidence] = []
            parent_evidence: dict[str, str] = {}
            for parent_id, row in selected.items():
                parent = parents[parent_id] if parents is not None else self.repository.parent(parent_id)
                full = f"Title path: {parent.title_path}\n{parent.text}"
                if len(full) <= limit:
                    evidence_id, content = parent_id, full
                else:
                    hit_text = row.text.split("\n", 1)[-1].strip()
                    anchor = parent.text.find(hit_text[:min(60, len(hit_text))]) if hit_text else -1
                    if anchor < 0:
                        anchor = 0
                    start = max(0, min(anchor - limit // 3, len(parent.text) - limit))
                    end = min(len(parent.text), start + max(100, limit - len(parent.title_path) - 65))
                    evidence_id = f"{parent_id}@{start}-{end}"
                    content = (f"Title path: {parent.title_path}\n"
                               f"[Parent section window {start}:{end}; matched child {row.chunk_id}]\n"
                               f"{parent.text[start:end]}")
                parent_evidence[parent_id] = evidence_id
                evidence.append(RagEvidence(
                    evidenceId=evidence_id, documentId=row.document_id, sourceId=row.source_id,
                    locatorId=parent.locator_id, locatorLabel=redact(parent.title_path), text=redact(content),
                ))
            payload = {"candidateEvidence": [item.model_dump(by_alias=True) for item in evidence]}
            if estimated_tokens(payload) <= INPUT_BUDGET * (100 - RESERVED_PERCENT) // 100 or limit <= 180:
                return evidence, {row.chunk_id: parent_evidence[row.parent_id] for row in rows}
            limit = int(limit * 0.75)

    @staticmethod
    def _search_response(
        request: RagQueryRequest, revision: str, rows: list[SearchRow]
    ) -> RagSearchResponse:
        return RagSearchResponse(
            datasetId=request.dataset_id,
            query=redact(request.query),
            topK=request.top_k,
            indexRevision=revision,
            results=[
                RagChunkResult(
                    rank=index,
                    bm25Score=row.bm25_score,
                    chunkId=row.chunk_id,
                    parentId=row.parent_id,
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
