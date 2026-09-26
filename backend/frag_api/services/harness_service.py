from __future__ import annotations

import hashlib
import re

from frag_api.errors import HarnessSourceError, RagFingerprintError, RagNotReadyError, RagOutputError
from frag_api.plugin_host import LoadedPlugin
from frag_api.providers.llm import LlmProvider, LlmSettings, provider_for
from frag_api.schemas.common import HarnessConfig, StageConfig, StageResult, TokenBudget
from frag_api.schemas.harness import HarnessPreview, HarnessRequest, HarnessRun, HarnessRunRequest
from frag_api.schemas.rag import RagContextCompression, RagEvidence, RagGroundedAnswer
from frag_api.services.approval import ApprovalRegistry
from frag_api.services.context_source_service import ContextSourceError, ContextSourceService
from frag_api.services.governed_context import (
    CONTEXT_OUTPUT_LIMIT, INFERENCE_OUTPUT_LIMIT, INPUT_BUDGET,
    RESERVED_PERCENT, estimated_tokens, fingerprint,
)

SECRET = re.compile(r"(?i)(api[_ -]?key|password|secret|access[_ -]?token)\s*[:=]\s*\S+")
EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")


def redact(text: str) -> str:
    return EMAIL.sub("[REDACTED_EMAIL]", SECRET.sub("[REDACTED_SECRET]", text))


class HarnessService:
    def __init__(
        self,
        source_service: ContextSourceService,
        settings: LlmSettings | None = None,
        context_provider: LlmProvider | None = None,
        inference_provider: LlmProvider | None = None,
        plugin: LoadedPlugin | None = None,
    ):
        self.source_service = source_service
        self.settings = settings or LlmSettings.from_environment()
        self.context_provider = context_provider or provider_for(self.settings.context)
        self.inference_provider = inference_provider or provider_for(self.settings.inference)
        self.approvals = ApprovalRegistry()
        self.plugin = plugin

    def config(self) -> HarnessConfig:
        return HarnessConfig(
            context=StageConfig(provider=self.settings.context.provider, model=self.settings.context.model or None,
                                ready=self.settings.context.ready),
            inference=StageConfig(provider=self.settings.inference.provider, model=self.settings.inference.model or None,
                                  ready=self.settings.inference.ready),
        )

    def preview(self, request: HarnessRequest, *, issue_approval: bool = True) -> HarnessPreview:
        evidence: list[RagEvidence] = []
        revisions: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        try:
            if request.plugin_selection is not None:
                if self.plugin is None:
                    raise HarnessSourceError()
                scope = request.plugin_selection
                if len(set(scope.record_ids)) != len(scope.record_ids):
                    raise HarnessSourceError()
                try:
                    records = self.plugin.read_evidence(scope.workspace_id, scope.record_ids)
                except Exception as error:
                    raise HarnessSourceError() from error
                if not isinstance(records, list) or len(records) != len(scope.record_ids):
                    raise HarnessSourceError()
                by_id = {item.get("recordId"): item for item in records if isinstance(item, dict)}
                if set(by_id) != set(scope.record_ids):
                    raise HarnessSourceError()
                for record_id in scope.record_ids:
                    item = by_id[record_id]
                    if not all(isinstance(item.get(key), str) and item[key] for key in ("label", "text", "revision")):
                        raise HarnessSourceError()
                    chunk_id = hashlib.sha256(f"fc\0{scope.workspace_id}\0{record_id}".encode()).hexdigest()[:24]
                    document_id = hashlib.sha256(scope.workspace_id.encode()).hexdigest()[:24]
                    locator_id = hashlib.sha256(record_id.encode()).hexdigest()[:24]
                    evidence.append(RagEvidence(
                        chunkId=chunk_id, documentId=document_id, sourceId="finance-core",
                        locatorId=locator_id, locatorLabel=redact(item["label"]), text=redact(item["text"]),
                    ))
                    revisions.append((record_id, item["revision"]))
            for selection in request.file_selections:
                parsed = self.source_service.parse(selection.relative_path)
                if parsed.source.status != "ready" or not parsed.source.sha256:
                    raise HarnessSourceError()
                sections = {section.locator.id: section for section in parsed.sections}
                revisions.append((selection.relative_path, parsed.source.sha256))
                for locator_id in selection.locator_ids:
                    identity = (selection.relative_path, locator_id)
                    if identity in seen or locator_id not in sections:
                        raise HarnessSourceError()
                    seen.add(identity)
                    section = sections[locator_id]
                    document_id = hashlib.sha256(selection.relative_path.encode()).hexdigest()[:24]
                    chunk_id = hashlib.sha256(f"{selection.relative_path}\0{locator_id}".encode()).hexdigest()[:24]
                    evidence.append(RagEvidence(
                        chunkId=chunk_id, documentId=document_id,
                        sourceId=f"file-{document_id}", locatorId=locator_id,
                        locatorLabel=redact(section.locator.label),
                        text=redact(section.text),
                    ))
        except (ContextSourceError, OSError, ValueError) as error:
            raise HarnessSourceError() from error
        if not evidence:
            raise HarnessSourceError()
        payload = {
            "goal": request.goal,
            "candidateEvidence": [item.model_dump(by_alias=True) for item in evidence],
            "sourceRevisions": revisions,
            "pluginScope": request.plugin_selection.model_dump(by_alias=True) if request.plugin_selection else None,
            "providerRoute": [[self.settings.context.provider, self.settings.context.model],
                              [self.settings.inference.provider, self.settings.inference.model]],
        }
        estimate = estimated_tokens(payload)
        if estimate > INPUT_BUDGET * (100 - RESERVED_PERCENT) // 100:
            raise HarnessSourceError()
        context_fingerprint = fingerprint(payload)
        return HarnessPreview(
            goal=request.goal, candidateEvidence=evidence,
            budget=TokenBudget(
                estimatedInputTokens=estimate, inputBudget=INPUT_BUDGET,
                reservedPercent=RESERVED_PERCENT, contextOutputLimit=CONTEXT_OUTPUT_LIMIT,
                inferenceOutputLimit=INFERENCE_OUTPUT_LIMIT,
            ),
            warnings=["Check every exact excerpt before approving this model run.",
                      "Automatic redaction cannot identify every private value."],
            contextFingerprint=context_fingerprint,
            approvalToken=self.approvals.issue(context_fingerprint) if issue_approval else "",
        )

    def run(self, request: HarnessRunRequest) -> HarnessRun:
        preview = self.preview(HarnessRequest(goal=request.goal, fileSelections=request.file_selections,
                                              pluginSelection=request.plugin_selection), issue_approval=False)
        if request.context_fingerprint != preview.context_fingerprint:
            raise RagFingerprintError()
        if not self.settings.context.ready or not self.settings.inference.ready:
            raise RagNotReadyError()
        if not self.approvals.consume(request.approval_token, preview.context_fingerprint):
            raise RagFingerprintError()
        preview.approval_token = request.approval_token
        context_call = self.context_provider.generate_rag_context(preview.candidate_evidence, CONTEXT_OUTPUT_LIMIT)
        compressed = context_call.output
        if not isinstance(compressed, RagContextCompression):
            raise RagOutputError()
        allowed = {item.chunk_id for item in preview.candidate_evidence}
        returned = {item.chunk_id for item in compressed.evidence}
        if returned != allowed or estimated_tokens(compressed.model_dump(by_alias=True)) > CONTEXT_OUTPUT_LIMIT:
            raise RagOutputError()
        inference_call = self.inference_provider.generate_rag_answer(compressed, request.goal, INFERENCE_OUTPUT_LIMIT)
        result = inference_call.output
        if not isinstance(result, RagGroundedAnswer):
            raise RagOutputError()
        cited = {item for claim in result.claims for item in claim.chunk_ids}
        if not cited or not cited.issubset(returned):
            raise RagOutputError()
        return HarnessRun(
            preview=preview, compressedContext=compressed, result=result,
            contextStage=StageResult(provider=self.settings.context.provider,
                                     model=self.settings.context.model, usage=context_call.usage),
            inferenceStage=StageResult(provider=self.settings.inference.provider,
                                       model=self.settings.inference.model, usage=inference_call.usage),
        )
