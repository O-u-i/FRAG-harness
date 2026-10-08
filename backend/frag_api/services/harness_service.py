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
from frag_api.request_spec import fingerprint
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
        plugins: dict[str, LoadedPlugin] | None = None,
    ):
        self.source_service = source_service
        self.settings = settings or LlmSettings.from_environment()
        self.context_provider = context_provider or provider_for(self.settings.context)
        self.inference_provider = inference_provider or provider_for(self.settings.inference)
        self.approvals = ApprovalRegistry()
        self.pending_inference = PendingInferenceRegistry()
        self.plugin = plugin
        self.plugins = dict(plugins or {})
        if plugin is not None:
            self.plugins[plugin.id] = plugin
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
            context=StageConfig(provider=self.settings.context.provider, model=self.settings.context.model_name or self.settings.context.model or None,
                                ready=self.settings.context.ready),
            inference=StageConfig(provider=self.settings.inference.provider, model=self.settings.inference.model_name or self.settings.inference.model or None,
                                  ready=self.settings.inference.ready),
        )

    def preview(self, request: HarnessRequest, *, issue_approval: bool = True) -> HarnessPreview:
        return self.flow.loops.get("fixed").runner.preview(request, issue_approval=issue_approval)

    def capabilities(self) -> CapabilityCatalog:
        return CapabilityCatalog(cli=self.cli_registry.catalog(), tools=self.tool_registry.catalog(),
                                 loops=self.flow.loops.catalog(), planned=[] if hasattr(self, "research") else ["research"])

    def _prepare_preview(self, request: HarnessRequest) -> HarnessPreview:
        evidence: list[RagEvidence] = []
        bindings: list[SourceBinding] = []
        seen: set[tuple[str, str]] = set()
        try:
            if request.plugin_selection is not None:
                scope = request.plugin_selection
                plugin = self.plugins.get(scope.plugin_id)
                if plugin is None:
                    raise HarnessSourceError()
                try:
                    records = plugin.read_selected(scope.scope, scope.record_ids)
                except Exception as error:
                    raise HarnessSourceError() from error
                for record_id, item in zip(scope.record_ids, records, strict=True):
                    # Keep FC citation IDs stable; qualify memory scope by source configuration.
                    seed = "fc" if plugin.id == "finance-core" else plugin.id
                    evidence_id = hashlib.sha256(f"{seed}\0{scope.scope}\0{record_id}".encode()).hexdigest()[:24]
                    document_id = hashlib.sha256(scope.scope.encode()).hexdigest()[:24]
                    locator_id = hashlib.sha256(record_id.encode()).hexdigest()[:24]
                    evidence.append(RagEvidence(
                        evidenceId=evidence_id, documentId=document_id, sourceId=plugin.id,
                        locatorId=locator_id, locatorLabel=redact(item["label"]), text=redact(item["text"]),
                    ))
                    bindings.append(SourceBinding(
                        identity=SourceIdentity(kind="fc_record" if plugin.id == "finance-core" else "plugin_record",
                                                namespace=f"{plugin.id}/{plugin.source_revision}",
                                                resourceId=record_id, workspaceId=scope.scope),
                        revision=item["revision"], parserVersion=f"plugin-{plugin.protocol_version}/{plugin.version}/{plugin.digest}/{plugin.source_revision}",
                        locatorIds=(locator_id,), evidenceIds=(evidence_id,),
                        assessment=SourceAssessment(provenance=QualityFact(status="known", detail="Selected read-only plugin record; returned revision and package digest bound.")),
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
            goal=redact(request.goal, configured_secrets(self.settings) + (self.flow.runtime.redaction_secrets if self.flow.runtime else ())),
            **context_preview_fields(settings=self.settings, evidence=evidence, goal=request.goal, task=request.task,
                                     sources=tuple(bindings), selection_hash=fingerprint(request.model_dump(by_alias=True)),
                                     redaction_secrets=self.flow.runtime.redaction_secrets if self.flow.runtime else (),
                                     selected_memory=request.selected_memory,
                                     memory_service=self.flow.runtime.memory if self.flow.runtime else None,
                                     loop_definition=self.flow.loops.get("fixed").definition.model_dump(by_alias=True)),
            warnings=["Check every exact excerpt before approving the Context call.",
                      "Automatic redaction cannot identify every private value.",
                      "Authority and real-world freshness are unknown unless separately reviewed.",
                      "Input tokens are estimated for the complete request, including schema and instructions."],
        )

    def run(self, request: HarnessRunRequest) -> HarnessContextRun:
        source_request = HarnessRequest(goal=request.goal, fileSelections=request.file_selections,
                                        pluginSelection=request.plugin_selection, task=request.task, selectedMemory=request.selected_memory,
                                        sessionId=request.session_id, parentRunId=request.parent_run_id)
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
