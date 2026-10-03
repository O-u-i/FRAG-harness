from __future__ import annotations

import hashlib
import os

from frag_api.errors import HarnessSourceError
from frag_api.plugin_host import LoadedPlugin
from frag_api.providers.llm import LlmProvider, LlmSettings, provider_for
from frag_api.schemas.common import HarnessConfig, StageConfig
from frag_api.schemas.governance import CapabilityCatalog, QualityFact, SourceAssessment, SourceBinding, SourceIdentity
from frag_api.schemas.harness import HarnessContextRun, HarnessPreview, HarnessRequest, HarnessRun, HarnessRunRequest
from frag_api.schemas.rag import InferenceRunRequest, RagEvidence
from frag_api.services.approval import ApprovalRegistry, PendingInferenceRegistry
from frag_api.services.context_source_service import PARSER_VERSION, ContextSourceError, ContextSourceService
from frag_api.services.governed_flow import GovernedFlow
from frag_api.services.governed_context import fingerprint
from frag_api.services.model_preview import context_preview_fields
from frag_api.services.runtime_policy import configured_secrets, redact
from frag_api.services.runtime_registry import CLIRegistry, ToolRegistry


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
        self.pending_inference = PendingInferenceRegistry()
        self.plugin = plugin
        self.cli_registry = CLIRegistry()
        self.tool_registry = ToolRegistry()
        self.flow = GovernedFlow(
            prepare_preview=self._prepare_preview, goal_for=lambda request: redact(request.goal, configured_secrets(self.settings)),
            settings=self.settings, context_provider=lambda: self.context_provider,
            inference_provider=lambda: self.inference_provider, approvals=self.approvals,
            pending_inference=self.pending_inference,
        )

    def config(self) -> HarnessConfig:
        return HarnessConfig(
            context=StageConfig(provider=self.settings.context.provider, model=self.settings.context.model or None,
                                ready=self.settings.context.ready),
            inference=StageConfig(provider=self.settings.inference.provider, model=self.settings.inference.model or None,
                                  ready=self.settings.inference.ready),
        )

    def preview(self, request: HarnessRequest, *, issue_approval: bool = True) -> HarnessPreview:
        return self.flow.loops.get("fixed").runner.preview(request, issue_approval=issue_approval)

    def capabilities(self) -> CapabilityCatalog:
        return CapabilityCatalog(cli=self.cli_registry.catalog(), tools=self.tool_registry.catalog(),
                                 loops=self.flow.loops.catalog(), planned=["cli", "kb_tools", "research"])

    def _prepare_preview(self, request: HarnessRequest) -> HarnessPreview:
        evidence: list[RagEvidence] = []
        bindings: list[SourceBinding] = []
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
                    evidence_id = hashlib.sha256(f"fc\0{scope.workspace_id}\0{record_id}".encode()).hexdigest()[:24]
                    document_id = hashlib.sha256(scope.workspace_id.encode()).hexdigest()[:24]
                    locator_id = hashlib.sha256(record_id.encode()).hexdigest()[:24]
                    evidence.append(RagEvidence(
                        evidenceId=evidence_id, documentId=document_id, sourceId="finance-core",
                        locatorId=locator_id, locatorLabel=redact(item["label"]), text=redact(item["text"]),
                    ))
                    bindings.append(SourceBinding(
                        identity=SourceIdentity(kind="fc_record", namespace="finance-core", resourceId=record_id,
                                                workspaceId=scope.workspace_id), revision=item["revision"],
                        parserVersion=f"released-http-v1/plugin-{self.plugin.version}",
                        locatorIds=(locator_id,), evidenceIds=(evidence_id,),
                        assessment=SourceAssessment(provenance=QualityFact(status="known", detail="Released read-only plugin record and revision.")),
                    ))
            selected_files: set[str] = set()
            for selection in request.file_selections:
                parsed = self.source_service.parse(selection.relative_path)
                if parsed.source.status != "ready" or not parsed.source.sha256:
                    raise HarnessSourceError()
                sections = {section.locator.id: section for section in parsed.sections}
                relative = parsed.source.relative_path
                normalized = relative.casefold() if os.name == "nt" else relative
                if normalized in selected_files:
                    raise HarnessSourceError()
                selected_files.add(normalized)
                selected_evidence: list[str] = []
                for locator_id in selection.locator_ids:
                    identity = (normalized, locator_id)
                    if identity in seen or locator_id not in sections:
                        raise HarnessSourceError()
                    seen.add(identity)
                    section = sections[locator_id]
                    document_id = hashlib.sha256(normalized.encode()).hexdigest()[:24]
                    evidence_id = hashlib.sha256(f"{normalized}\0{locator_id}".encode()).hexdigest()[:24]
                    evidence.append(RagEvidence(
                        evidenceId=evidence_id, documentId=document_id,
                        sourceId=f"file-{document_id}", locatorId=locator_id,
                        locatorLabel=redact(section.locator.label),
                        text=redact(section.text),
                    ))
                    selected_evidence.append(evidence_id)
                bindings.append(SourceBinding(
                    identity=SourceIdentity(kind="local_file", namespace=fingerprint(str(self.source_service.root)),
                                            resourceId=document_id), revision=parsed.source.sha256,
                    parserVersion=PARSER_VERSION, locatorIds=tuple(selection.locator_ids),
                    evidenceIds=tuple(selected_evidence), assessment=SourceAssessment(
                        relevance=QualityFact(status="known", detail="User selection reason: " + redact(selection.relevance_reason)),
                        provenance=QualityFact(status="known", detail="Selected file byte snapshot; SHA-256 and parser version bound.")),
                ))
        except (ContextSourceError, OSError, ValueError) as error:
            raise HarnessSourceError() from error
        if not evidence:
            raise HarnessSourceError()
        return HarnessPreview(
            goal=redact(request.goal, configured_secrets(self.settings)),
            **context_preview_fields(settings=self.settings, evidence=evidence, goal=request.goal, task=request.task,
                                     sources=tuple(bindings), selection_hash=fingerprint(request.model_dump(by_alias=True)),
                                     loop_definition=self.flow.loops.get("fixed").definition.model_dump(by_alias=True)),
            warnings=["Check every exact excerpt before approving the Context call.",
                      "Automatic redaction cannot identify every private value.",
                      "Authority and real-world freshness are unknown unless separately reviewed.",
                      "Input tokens are estimated for the complete request, including schema and instructions."],
        )

    def run(self, request: HarnessRunRequest) -> HarnessContextRun:
        source_request = HarnessRequest(goal=request.goal, fileSelections=request.file_selections,
                                        pluginSelection=request.plugin_selection, task=request.task)
        state = self.flow.loops.get("fixed").runner.run_context(source_request, request)
        return HarnessContextRun(
            preview=state["preview"], compressedContext=state["compressed"],
            contextStage=state["context_stage"], inferencePreview=state["inference_preview"],
        )

    def run_inference(self, request: InferenceRunRequest) -> HarnessRun:
        state = self.flow.loops.get("fixed").runner.run_inference(request)
        return HarnessRun(
            preview=state["preview"], compressedContext=state["compressed"],
            result=state["answer"], contextStage=state["context_stage"],
            inferenceStage=state["inference_stage"],
        )
