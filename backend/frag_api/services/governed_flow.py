"""Embedded LangGraph for the two separately approved model stages."""
from __future__ import annotations

from typing import Any, Callable, TypedDict

from langgraph.graph import END, START, StateGraph
from langsmith import tracing_context

from frag_api.errors import RagFingerprintError, RagNotReadyError, RagOutputError
from frag_api.providers.llm import LlmProvider, LlmSettings, inference_input
from frag_api.providers.prepared import prepare_call, verify_prepared
from frag_api.schemas.common import StageResult
from frag_api.schemas.governance import LoopDefinition, PreparedCall
from frag_api.schemas.rag import (
    InferencePreview, RagContextCompression, RagGroundedAnswer,
)
from frag_api.services.approval import ApprovalRegistry, PendingInferenceRegistry
from frag_api.services.governed_context import (
    CONTEXT_OUTPUT_LIMIT, INFERENCE_OUTPUT_LIMIT, estimated_tokens,
)
from frag_api.services.runtime_policy import HostPolicy, RunBudget, configured_secrets, redact_value
from frag_api.services.runtime_registry import LoopRegistry


class FlowState(TypedDict, total=False):
    source_request: Any
    request: Any
    preview: Any
    issue_approval: bool
    compressed: RagContextCompression
    context_stage: StageResult
    inference_preview: InferencePreview
    answer: RagGroundedAnswer
    inference_stage: StageResult
    goal: str
    inference_prepared: PreparedCall
    run_budget: RunBudget


class GovernedFlow:
    def __init__(
        self,
        *,
        prepare_preview: Callable[[Any], Any],
        goal_for: Callable[[Any], str],
        settings: LlmSettings,
        context_provider: Callable[[], LlmProvider],
        inference_provider: Callable[[], LlmProvider],
        approvals: ApprovalRegistry,
        pending_inference: PendingInferenceRegistry,
    ):
        self.prepare_preview = prepare_preview
        self.goal_for = goal_for
        self.settings = settings
        self.context_provider = context_provider
        self.inference_provider = inference_provider
        self.approvals = approvals
        self.pending_inference = pending_inference
        self.preview_graph = self._compile([("prepare", self._prepare), ("issue", self._issue)])
        self.context_graph = self._compile([
            ("prepare", self._prepare), ("authorize", self._authorize),
            ("context_call", self._context_call), ("context_check", self._context_check),
            ("inference_preview", self._inference_preview),
        ])
        self.inference_graph = self._compile([
            ("consume", self._consume), ("revalidate", self._revalidate),
            ("inference_call", self._inference_call), ("citation_check", self._citation_check),
        ])
        self.loops = LoopRegistry()
        self.loops.register(LoopDefinition(name="fixed", version="1.0.0", stages=("context", "inference")), self)

    @staticmethod
    def _compile(nodes: list[tuple[str, Callable[[FlowState], FlowState]]]):
        graph = StateGraph(FlowState)
        for name, node in nodes:
            graph.add_node(name, node)
        graph.add_edge(START, nodes[0][0])
        for current, following in zip(nodes, nodes[1:]):
            graph.add_edge(current[0], following[0])
        graph.add_edge(nodes[-1][0], END)
        return graph.compile()  # No checkpointer or persistent graph state.

    @staticmethod
    def _invoke(graph: Any, state: FlowState) -> FlowState:
        with tracing_context(enabled=False):
            return graph.invoke(state, config={"callbacks": []})

    def preview(self, source_request: Any, *, issue_approval: bool = True) -> Any:
        state = self._invoke(self.preview_graph, {
            "source_request": source_request, "issue_approval": issue_approval,
        })
        return state["preview"]

    def run_context(self, source_request: Any, request: Any) -> FlowState:
        return self._invoke(self.context_graph, {"source_request": source_request, "request": request})

    def run_inference(self, request: Any) -> FlowState:
        return self._invoke(self.inference_graph, {"request": request})

    def _prepare(self, state: FlowState) -> FlowState:
        return {"preview": self.prepare_preview(state["source_request"]),
                "goal": self.goal_for(state["source_request"])}

    def _issue(self, state: FlowState) -> FlowState:
        if state["issue_approval"] and state["preview"].can_approve:
            # The caller receives a copy; only this server-owned snapshot may execute.
            pending = (state["source_request"].model_copy(deep=True), state["preview"].model_copy(deep=True))
            state["preview"].approval_token = self.approvals.issue(state["preview"].context_fingerprint, pending)
        return {"preview": state["preview"]}

    def _authorize(self, state: FlowState) -> FlowState:
        request = state["request"]
        valid, pending = self.approvals.consume_state(request.approval_token, request.context_fingerprint)
        if not valid or pending is None:
            raise RagFingerprintError()
        source_request, preview = pending
        if request.context_fingerprint != state["preview"].context_fingerprint:
            raise RagFingerprintError()
        HostPolicy.require_task(preview.task)
        if not preview.candidate_evidence:
            raise RagOutputError()
        if not self.settings.context.ready or not self.settings.inference.ready:
            raise RagNotReadyError()
        verify_prepared(preview.prepared_call, self.settings.context)
        budget = RunBudget(limit=preview.prepared_call.run_token_limit)
        budget.reserve(preview.prepared_call)
        preview.approval_token = request.approval_token
        return {"source_request": source_request, "preview": preview, "run_budget": budget,
                "goal": self.goal_for(source_request)}

    def _context_call(self, state: FlowState) -> FlowState:
        prepared = state["preview"].prepared_call
        call = self.context_provider().execute_prepared(prepared)
        return {"compressed": call.output, "run_budget": state["run_budget"].charge(prepared, call.usage),
                "context_stage": StageResult(provider=self.settings.context.provider,
                                             model=self.settings.context.model, usage=call.usage)}

    @staticmethod
    def _context_check(state: FlowState) -> FlowState:
        compressed = state["compressed"]
        if not isinstance(compressed, RagContextCompression):
            raise RagOutputError()
        allowed = {item.evidence_id for item in state["preview"].candidate_evidence}
        returned = {item.evidence_id for item in compressed.evidence}
        if (returned != allowed or len(returned) != len(compressed.evidence)
                or estimated_tokens(compressed.model_dump(by_alias=True)) > CONTEXT_OUTPUT_LIMIT):
            raise RagOutputError()
        return {}

    def _prepare_inference(self, state: FlowState) -> PreparedCall:
        instructions, payload = inference_input(state["compressed"], state["goal"])
        payload["task"] = state["preview"].task.model_dump(by_alias=True)
        return prepare_call(
            settings=self.settings.inference, purpose="inference", instructions=instructions,
            payload=redact_value(payload, configured_secrets(self.settings)), output_model=RagGroundedAnswer,
            max_output_tokens=INFERENCE_OUTPUT_LIMIT,
            binding={**state["preview"].prepared_call.request_binding(),
                     "contextFingerprint": state["preview"].context_fingerprint},
        )
    def _inference_preview(self, state: FlowState) -> FlowState:
        prepared = self._prepare_inference(state)
        state["run_budget"].reserve(prepared)
        pending = (state["source_request"].model_copy(deep=True), state["preview"].model_copy(deep=True),
                   state["compressed"].model_copy(deep=True), state["context_stage"].usage.model_copy(deep=True),
                   prepared, state["run_budget"])
        token = self.pending_inference.issue(prepared.fingerprint, pending)
        body = prepared.request_body()
        return {"inference_preview": InferencePreview(
            provider=self.settings.inference.provider, model=self.settings.inference.model,
            instructions=body["instructions"], input=body["input"], maxOutputTokens=INFERENCE_OUTPUT_LIMIT,
            inferenceFingerprint=prepared.fingerprint, approvalToken=token, preparedCall=prepared,
        )}

    def _consume(self, state: FlowState) -> FlowState:
        request = state["request"]
        pending = self.pending_inference.consume(request.approval_token, request.inference_fingerprint)
        if pending is None:
            raise RagFingerprintError()
        source_request, preview, compressed, usage, prepared, budget = pending
        if request.context_fingerprint != preview.context_fingerprint:
            raise RagFingerprintError()
        return {"source_request": source_request, "preview": preview, "compressed": compressed,
                "context_stage": StageResult(provider=self.settings.context.provider,
                                             model=self.settings.context.model, usage=usage),
                "goal": self.goal_for(source_request), "inference_prepared": prepared, "run_budget": budget}

    def _revalidate(self, state: FlowState) -> FlowState:
        current = self.prepare_preview(state["source_request"])
        if current.context_fingerprint != state["preview"].context_fingerprint:
            raise RagFingerprintError()
        HostPolicy.require_task(current.task)
        verify_prepared(state["inference_prepared"], self.settings.inference)
        if self._prepare_inference(state).fingerprint != state["inference_prepared"].fingerprint:
            raise RagFingerprintError()
        state["run_budget"].reserve(state["inference_prepared"])
        return {}

    def _inference_call(self, state: FlowState) -> FlowState:
        prepared = state["inference_prepared"]
        call = self.inference_provider().execute_prepared(prepared)
        return {"answer": call.output, "run_budget": state["run_budget"].charge(prepared, call.usage),
                "inference_stage": StageResult(provider=self.settings.inference.provider,
                                               model=self.settings.inference.model, usage=call.usage)}

    @staticmethod
    def _citation_check(state: FlowState) -> FlowState:
        answer = state["answer"]
        if not isinstance(answer, RagGroundedAnswer):
            raise RagOutputError()
        allowed = {item.evidence_id for item in state["compressed"].evidence}
        cited = {evidence_id for claim in answer.claims for evidence_id in claim.evidence_ids}
        if (not cited or not cited.issubset(allowed)
                or estimated_tokens(answer.model_dump(by_alias=True)) > INFERENCE_OUTPUT_LIMIT):
            raise RagOutputError()
        return {}
